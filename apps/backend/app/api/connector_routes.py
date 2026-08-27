import os
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.schemas.connector_schema import (
    FilterUpdate,
    OAuthStartResponse,
    ProviderResponse,
    SyncStartResponse,
)
from app.services import connector_service, connector_sync_service
from app.services.connectors import (
    ConnectorAuthError,
    ConnectorError,
    available_providers,
    get_connector,
)

router = APIRouter()


def _frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers():
    return available_providers()


@router.get("")
async def list_connections():
    return [connector_service.public_view(c) for c in await connector_service.list_connections()]


@router.post("/{provider}/oauth/start", response_model=OAuthStartResponse)
async def start_oauth(provider: str):
    try:
        connection_id, url = await connector_service.begin_oauth(provider)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return OAuthStartResponse(connection_id=connection_id, authorization_url=url)


@router.get("/{provider}/oauth/callback")
async def oauth_callback(provider: str, code: str = "", state: str = "", error: str = ""):
    """Where the provider sends the user back after consent.

    The token exchange stays on the backend so the client secret never reaches
    the browser or the Next.js process. Ends in a redirect to the UI either way.
    """
    destination = f"{_frontend_url()}/connectors"
    if error:
        return RedirectResponse(f"{destination}?{urlencode({'error': error})}")
    if not code or not state:
        return RedirectResponse(f"{destination}?{urlencode({'error': 'Missing authorisation code'})}")
    try:
        connection = await connector_service.complete_oauth(provider, code=code, state=state)
    except (ConnectorAuthError, ConnectorError) as e:
        return RedirectResponse(f"{destination}?{urlencode({'error': str(e)})}")
    return RedirectResponse(f"{destination}?{urlencode({'connected': connection['provider']})}")


@router.get("/{connection_id}/folders")
async def list_folders(connection_id: str):
    """Selectable labels/folders for the filter dropdown."""
    connection = await connector_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    try:
        connector = get_connector(connection["provider"])
        token = await connector_service.get_valid_access_token(connection_id)
        return await connector.list_folders(token)
    except ConnectorAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{connection_id}/filters")
async def update_filters(connection_id: str, payload: FilterUpdate):
    connection = await connector_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    await connector_service.update_connection(connection_id, **fields)
    return connector_service.public_view(await connector_service.get_connection(connection_id))


@router.post("/{connection_id}/disconnect")
async def disconnect(connection_id: str):
    connection = await connector_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    await connector_service.disconnect(connection_id)
    return {"status": "DISCONNECTED"}


@router.post("/{connection_id}/sync", response_model=SyncStartResponse, status_code=202)
async def start_sync(connection_id: str):
    try:
        run = await connector_sync_service.start_sync(connection_id)
    except connector_sync_service.SyncAlreadyRunning as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SyncStartResponse(run_id=run["id"], status=run["status"])


@router.get("/{connection_id}/sync-runs")
async def list_sync_runs(connection_id: str):
    return await connector_sync_service.list_runs(connection_id)


@router.get("/{connection_id}/stats")
async def get_connection_stats(connection_id: str):
    """Mailbox and invoice counts for the connection, plus its most recent run.

    The page needs these on load, before — and long after — any sync of its own.
    """
    connection = await connector_service.get_connection(connection_id)
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    return await connector_sync_service.get_connection_stats(connection_id)


@router.get("/sync-runs/{run_id}")
async def get_sync_run(run_id: str):
    run = await connector_sync_service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return run


@router.get("/sync-runs/{run_id}/items")
async def get_sync_run_items(run_id: str):
    return await connector_sync_service.list_run_items(run_id)
