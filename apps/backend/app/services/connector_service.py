"""Connector connections: storage, OAuth handshake state, and token lifecycle."""

import asyncio
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.db.mongo import get_database, with_id
from app.services import crypto_service
from app.services.connectors import ConnectorAuthError, ConnectorError, get_connector
from app.services.connectors.base import OAuthTokens
from app.services.ingest_service import COUNTRY_INDIA, normalize_country

STATE_TTL_MINUTES = 10
REFRESH_MARGIN_SECONDS = 120

STATUS_PENDING = "PENDING"
STATUS_CONNECTED = "CONNECTED"
STATUS_NEEDS_REAUTH = "NEEDS_REAUTH"
STATUS_ERROR = "ERROR"
STATUS_DISCONNECTED = "DISCONNECTED"

# Serialise refreshes per connection so two callers don't race to spend the
# same authorisation code and invalidate each other's token. This is a
# per-process dict, so it only holds while the backend runs as one instance.
_refresh_locks: dict[str, asyncio.Lock] = {}

# Fields that must never leave the backend.
_SECRET_FIELDS = {"access_token", "refresh_token", "oauth_state"}

# Written on insert so every reader sees the same keys a `SELECT *` used to give.
_CONNECTION_DEFAULTS: dict = {
    "account_email": None,
    "access_token": None,
    "refresh_token": None,
    "token_expires_at": None,
    "scopes": None,
    "oauth_state": None,
    "oauth_state_created_at": None,
    "filter_label": None,
    "filter_label_name": None,
    "filter_query": "has:attachment",
    "max_messages_per_sync": 1,
    "last_sync_at": None,
    "last_error": None,
}


def _now() -> str:
    return datetime.utcnow().isoformat()


def redirect_uri(provider: str) -> str:
    configured = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if configured and provider.upper() == "GMAIL":
        return configured
    base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/connectors/{provider.lower()}/oauth/callback"


def connection_country(connection: dict) -> str:
    """The regime a connection's attachments are processed under.

    Records written before the field existed carry nothing, which is India.
    """
    return normalize_country(connection.get("country") or COUNTRY_INDIA)


def public_view(row: dict) -> dict:
    """A connection as the frontend may see it — tokens stripped."""
    return {k: v for k, v in row.items() if k not in _SECRET_FIELDS}


def _sanitize(fields: dict) -> dict:
    bad = [key for key in fields if key.startswith("$") or "." in key]
    if bad:
        raise ValueError(f"Invalid field name(s) for update: {', '.join(bad)}")
    return fields


# -- reads -----------------------------------------------------------------


async def get_connection(connection_id: str) -> Optional[dict]:
    doc = await get_database().connector_connections.find_one({"_id": connection_id})
    return with_id(doc)


async def list_connections() -> list[dict]:
    """Connections the user actually has.

    PENDING records are mid-handshake — every abandoned "Connect" click leaves
    one — so they are not connections yet and are not listed.
    """
    cursor = get_database().connector_connections.find(
        {"status": {"$nin": [STATUS_DISCONNECTED, STATUS_PENDING]}}
    ).sort("created_at", -1)
    return [with_id(doc) async for doc in cursor]


async def purge_stale_pending():
    """Drop handshakes that were never completed within the state window."""
    cutoff = (datetime.utcnow() - timedelta(minutes=STATE_TTL_MINUTES)).isoformat()
    await get_database().connector_connections.delete_many({
        "status": STATUS_PENDING,
        # A missing field and an explicit null both match None here, which is
        # what `oauth_state_created_at IS NULL` covered.
        "$or": [
            {"oauth_state_created_at": None},
            {"oauth_state_created_at": {"$lt": cutoff}},
        ],
    })


async def is_already_ingested(connection_id: str, source_ref: str) -> Optional[dict]:
    """The document this attachment produced on an earlier sync, if any."""
    doc = await get_database().documents.find_one(
        {"source_connector_id": connection_id, "source_ref": source_ref},
        {"status": 1},
    )
    return with_id(doc)


# -- writes ----------------------------------------------------------------


async def update_connection(connection_id: str, **fields):
    if not fields:
        return
    # An unrecognised country would send the attachments down neither pipeline.
    if "country" in fields:
        fields["country"] = normalize_country(fields["country"])
    fields["updated_at"] = _now()
    await get_database().connector_connections.update_one(
        {"_id": connection_id}, {"$set": _sanitize(fields)}
    )


async def begin_oauth(provider: str, country: Optional[str] = None) -> tuple[str, str]:
    """Create a pending connection and return (connection_id, authorization_url).

    The country is fixed at connect time from whichever regime the user is
    working in, and everything the mailbox later pulls is processed under it.
    It stays editable on the connection afterwards.
    """
    provider = provider.upper()
    connector = get_connector(provider)
    if not connector.is_configured():
        raise ConnectorError(f"{connector.label} is not configured on this server.")

    await purge_stale_pending()

    connection_id = str(uuid.uuid4())
    state = secrets.token_urlsafe(32)
    now = _now()

    await get_database().connector_connections.insert_one({
        **_CONNECTION_DEFAULTS,
        "_id": connection_id,
        "provider": provider,
        "country": normalize_country(country),
        "status": STATUS_PENDING,
        "oauth_state": state,
        "oauth_state_created_at": now,
        "scopes": " ".join(connector.default_scopes),
        "filter_query": "has:attachment",
        "max_messages_per_sync": int(os.getenv("CONNECTOR_MAX_MESSAGES_PER_SYNC", "1")),
        "created_at": now,
        "updated_at": now,
    })

    url = connector.build_authorization_url(state=state, redirect_uri=redirect_uri(provider))
    return connection_id, url


async def complete_oauth(provider: str, *, code: str, state: str) -> dict:
    """Exchange the authorisation code and mark the connection connected."""
    provider = provider.upper()
    connector = get_connector(provider)

    pending = with_id(await get_database().connector_connections.find_one({
        "provider": provider,
        "oauth_state": state,
        "status": STATUS_PENDING,
    }))

    if not pending:
        raise ConnectorAuthError("This sign-in link is not valid. Start the connection again.")

    started = pending.get("oauth_state_created_at")
    if started and datetime.fromisoformat(started) < datetime.utcnow() - timedelta(minutes=STATE_TTL_MINUTES):
        raise ConnectorAuthError("This sign-in link has expired. Start the connection again.")

    tokens = await connector.exchange_code(code=code, redirect_uri=redirect_uri(provider))
    email = tokens.account_email or await connector.get_account_email(tokens.access_token)

    await update_connection(
        pending["id"],
        status=STATUS_CONNECTED,
        account_email=email,
        access_token=crypto_service.encrypt(tokens.access_token),
        refresh_token=crypto_service.encrypt(tokens.refresh_token),
        token_expires_at=tokens.expires_at,
        scopes=" ".join(tokens.scopes) if tokens.scopes else pending.get("scopes"),
        oauth_state=None,
        oauth_state_created_at=None,
        last_error=None,
    )
    return await get_connection(pending["id"])


async def disconnect(connection_id: str):
    await update_connection(
        connection_id,
        status=STATUS_DISCONNECTED,
        access_token=None,
        refresh_token=None,
        token_expires_at=None,
        oauth_state=None,
        oauth_state_created_at=None,
    )


async def get_valid_access_token(connection_id: str) -> str:
    """Return a usable access token, refreshing it first if it is about to expire."""
    lock = _refresh_locks.setdefault(connection_id, asyncio.Lock())
    async with lock:
        connection = await get_connection(connection_id)
        if not connection:
            raise ConnectorError("Connection not found")
        if connection["status"] == STATUS_DISCONNECTED:
            raise ConnectorAuthError("This account has been disconnected.")

        access_token = crypto_service.decrypt(connection.get("access_token"))
        expires_at = connection.get("token_expires_at")

        if access_token and expires_at:
            try:
                if datetime.fromisoformat(expires_at) - timedelta(seconds=REFRESH_MARGIN_SECONDS) > datetime.utcnow():
                    return access_token
            except ValueError:
                pass  # unparseable expiry — refresh rather than guess

        refresh_token = crypto_service.decrypt(connection.get("refresh_token"))
        if not refresh_token:
            await update_connection(
                connection_id, status=STATUS_NEEDS_REAUTH,
                last_error="No refresh token stored. Reconnect the account.",
            )
            raise ConnectorAuthError("No refresh token stored. Reconnect the account.")

        connector = get_connector(connection["provider"])
        try:
            tokens: OAuthTokens = await connector.refresh_access_token(refresh_token)
        except ConnectorAuthError as e:
            await update_connection(
                connection_id, status=STATUS_NEEDS_REAUTH, last_error=str(e)
            )
            raise

        await update_connection(
            connection_id,
            status=STATUS_CONNECTED,
            access_token=crypto_service.encrypt(tokens.access_token),
            refresh_token=crypto_service.encrypt(tokens.refresh_token or refresh_token),
            token_expires_at=tokens.expires_at,
            last_error=None,
        )
        return tokens.access_token
