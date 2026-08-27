"""Connector connections: storage, OAuth handshake state, and token lifecycle."""

import asyncio
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.db.database import get_db
from app.services import crypto_service
from app.services.connectors import ConnectorAuthError, ConnectorError, get_connector
from app.services.connectors.base import OAuthTokens

STATE_TTL_MINUTES = 10
REFRESH_MARGIN_SECONDS = 120

STATUS_PENDING = "PENDING"
STATUS_CONNECTED = "CONNECTED"
STATUS_NEEDS_REAUTH = "NEEDS_REAUTH"
STATUS_ERROR = "ERROR"
STATUS_DISCONNECTED = "DISCONNECTED"

# Serialise refreshes per connection so two callers don't race to spend the
# same authorisation code and invalidate each other's token.
_refresh_locks: dict[str, asyncio.Lock] = {}

# Fields that must never leave the backend.
_SECRET_FIELDS = {"access_token", "refresh_token", "oauth_state"}


def _now() -> str:
    return datetime.utcnow().isoformat()


def redirect_uri(provider: str) -> str:
    configured = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if configured and provider.upper() == "GMAIL":
        return configured
    base = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/connectors/{provider.lower()}/oauth/callback"


def public_view(row: dict) -> dict:
    """A connection as the frontend may see it — tokens stripped."""
    return {k: v for k, v in row.items() if k not in _SECRET_FIELDS}


# -- reads -----------------------------------------------------------------


async def get_connection(connection_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM connector_connections WHERE id = ?", (connection_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_connections() -> list[dict]:
    """Connections the user actually has.

    PENDING rows are mid-handshake — every abandoned "Connect" click leaves
    one — so they are not connections yet and are not listed.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM connector_connections
               WHERE status NOT IN (?, ?) ORDER BY created_at DESC""",
            (STATUS_DISCONNECTED, STATUS_PENDING),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def purge_stale_pending():
    """Drop handshakes that were never completed within the state window."""
    cutoff = (datetime.utcnow() - timedelta(minutes=STATE_TTL_MINUTES)).isoformat()
    async with get_db() as db:
        await db.execute(
            """DELETE FROM connector_connections
               WHERE status = ? AND (oauth_state_created_at IS NULL OR oauth_state_created_at < ?)""",
            (STATUS_PENDING, cutoff),
        )
        await db.commit()


async def is_already_ingested(connection_id: str, source_ref: str) -> Optional[dict]:
    """The document this attachment produced on an earlier sync, if any."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, status FROM documents
               WHERE source_connector_id = ? AND source_ref = ? LIMIT 1""",
            (connection_id, source_ref),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


# -- writes ----------------------------------------------------------------


async def update_connection(connection_id: str, **fields):
    if not fields:
        return
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    async with get_db() as db:
        await db.execute(
            f"UPDATE connector_connections SET {assignments} WHERE id = ?",
            [*fields.values(), connection_id],
        )
        await db.commit()


async def begin_oauth(provider: str) -> tuple[str, str]:
    """Create a pending connection and return (connection_id, authorization_url)."""
    provider = provider.upper()
    connector = get_connector(provider)
    if not connector.is_configured():
        raise ConnectorError(f"{connector.label} is not configured on this server.")

    await purge_stale_pending()

    connection_id = str(uuid.uuid4())
    state = secrets.token_urlsafe(32)
    now = _now()

    async with get_db() as db:
        await db.execute(
            """INSERT INTO connector_connections
               (id, provider, status, oauth_state, oauth_state_created_at,
                scopes, filter_query, max_messages_per_sync, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                connection_id, provider, STATUS_PENDING, state, now,
                " ".join(connector.default_scopes), "has:attachment",
                int(os.getenv("CONNECTOR_MAX_MESSAGES_PER_SYNC", "25")), now, now,
            ),
        )
        await db.commit()

    url = connector.build_authorization_url(state=state, redirect_uri=redirect_uri(provider))
    return connection_id, url


async def complete_oauth(provider: str, *, code: str, state: str) -> dict:
    """Exchange the authorisation code and mark the connection connected."""
    provider = provider.upper()
    connector = get_connector(provider)

    async with get_db() as db:
        cursor = await db.execute(
            """SELECT * FROM connector_connections
               WHERE provider = ? AND oauth_state = ? AND status = ?""",
            (provider, state, STATUS_PENDING),
        )
        row = await cursor.fetchone()

    if not row:
        raise ConnectorAuthError("This sign-in link is not valid. Start the connection again.")

    pending = dict(row)
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
