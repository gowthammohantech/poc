"""Gmail, over the REST API with httpx.

Hand-rolled rather than using google-api-python-client: that library is
synchronous and would block the event loop, and it pins a protobuf version that
conflicts with the PaddleOCR stack already in requirements.txt. The surface we
need is seven endpoints.
"""

import base64
import os
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode

import httpx

from app.services.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    MailAttachmentRef,
    OAuthTokens,
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
TIMEOUT = 60.0

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"


class GmailConnector:
    provider = "GMAIL"
    label = "Gmail"
    default_scopes = [GMAIL_READONLY]

    # -- configuration -----------------------------------------------------

    @property
    def client_id(self) -> str:
        return os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")

    @property
    def client_secret(self) -> str:
        return os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # -- OAuth -------------------------------------------------------------

    def build_authorization_url(self, *, state: str, redirect_uri: str) -> str:
        if not self.is_configured():
            raise ConnectorError(
                "Gmail is not configured. Set GOOGLE_OAUTH_CLIENT_ID and "
                "GOOGLE_OAUTH_CLIENT_SECRET in apps/backend/.env."
            )
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.default_scopes),
            # Both are required for a refresh token to come back reliably;
            # without them the connection silently dies when the hour is up.
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens:
        payload = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        data = await self._token_request(payload)
        tokens = _tokens_from_response(data, existing_refresh=None)
        if not tokens.refresh_token:
            raise ConnectorAuthError(
                "Google did not return a refresh token. Remove this app's access at "
                "myaccount.google.com/permissions and connect again."
            )
        return tokens

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        payload = {
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        data = await self._token_request(payload)
        # A refresh response carries no refresh_token; the stored one stands.
        return _tokens_from_response(data, existing_refresh=refresh_token)

    async def _token_request(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(TOKEN_URL, data=payload)
        if response.status_code >= 400:
            detail = _error_detail(response)
            # invalid_grant means the user revoked access or, in Google's
            # Testing publishing mode, the refresh token aged out after 7 days.
            if "invalid_grant" in detail or response.status_code in (400, 401):
                raise ConnectorAuthError(f"Gmail authorisation failed: {detail}")
            raise ConnectorError(f"Gmail token request failed: {detail}")
        return response.json()

    # -- API ---------------------------------------------------------------

    async def get_account_email(self, access_token: str) -> str:
        data = await self._get(access_token, "/profile")
        return data.get("emailAddress", "")

    async def list_folders(self, access_token: str) -> list[dict]:
        data = await self._get(access_token, "/labels")
        labels = data.get("labels", [])
        return [
            {"id": label["id"], "name": label.get("name", label["id"])}
            for label in labels
            if label.get("type") == "user" or label.get("id") in {"INBOX", "STARRED", "IMPORTANT"}
        ]

    async def list_attachments(
        self, access_token: str, *, query: str | None, label_id: str | None, max_messages: int,
    ) -> tuple[list[MailAttachmentRef], int]:
        params: dict = {"maxResults": max(1, min(max_messages, 100))}
        if query:
            params["q"] = query
        if label_id:
            params["labelIds"] = label_id

        listing = await self._get(access_token, "/messages", params=params)
        messages = listing.get("messages", []) or []

        refs: list[MailAttachmentRef] = []
        for stub in messages:
            message_id = stub.get("id")
            if not message_id:
                continue
            detail = await self._get(
                access_token, f"/messages/{message_id}", params={"format": "full"}
            )
            refs.extend(_refs_from_message(detail))
        return refs, len(messages)

    async def fetch_attachment(self, access_token: str, ref: MailAttachmentRef) -> bytes:
        if not ref.attachment_id:
            raise ConnectorError(f"No attachment id for {ref.filename}")
        data = await self._get(
            access_token, f"/messages/{ref.message_id}/attachments/{ref.attachment_id}"
        )
        return _decode_attachment_data(data.get("data", ""))

    async def _get(self, access_token: str, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{API_BASE}{path}",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code in (401, 403):
            raise ConnectorAuthError(f"Gmail rejected the request: {_error_detail(response)}")
        if response.status_code == 429:
            raise ConnectorRateLimitError("Gmail rate limit reached; try again shortly.")
        if response.status_code >= 400:
            raise ConnectorError(
                f"Gmail request failed ({response.status_code}): {_error_detail(response)}"
            )
        return response.json()


# -- pure helpers (unit-tested without a network) --------------------------


def _decode_attachment_data(data: str) -> bytes:
    """Gmail returns base64url with the padding stripped."""
    if not data:
        return b""
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _walk_parts(payload: dict, out: list[dict], counter: list[int]) -> None:
    """Collect attachment-bearing parts from an arbitrarily nested payload."""
    if not isinstance(payload, dict):
        return
    body = payload.get("body") or {}
    filename = payload.get("filename") or ""
    if body.get("attachmentId") and filename:
        out.append({
            "part_index": counter[0],
            "filename": filename,
            "mime_type": payload.get("mimeType") or "application/octet-stream",
            "attachment_id": body["attachmentId"],
            "size_bytes": int(body.get("size") or 0),
            "is_inline": _is_inline(payload.get("headers") or []),
        })
        counter[0] += 1
    for part in payload.get("parts") or []:
        _walk_parts(part, out, counter)


def _is_inline(headers: list[dict]) -> bool:
    """Logos and signature images ride along on ordinary business email.

    They are attachments as far as the API is concerned, so without this every
    sync would ingest a pile of 4KB PNGs as if they were invoices.

    Content-Disposition decides it. A bare Content-ID does not: Gmail's own
    composer stamps one (`<f_...>`, alongside X-Attachment-Id) on every file a
    user attaches, so treating it as proof of inlining drops real invoices sent
    from Gmail. It is only a hint, and only when nothing says otherwise.
    """
    disposition = ""
    has_content_id = False
    for header in headers:
        name = (header.get("name") or "").lower()
        value = (header.get("value") or "").lower()
        if name == "content-disposition":
            disposition = value
        elif name == "content-id" and value:
            has_content_id = True

    if disposition.startswith("attachment"):
        return False
    if disposition.startswith("inline"):
        return True
    return has_content_id


def _header(headers: list[dict], name: str) -> str:
    target = name.lower()
    for header in headers:
        if (header.get("name") or "").lower() == target:
            return header.get("value") or ""
    return ""


def _refs_from_message(message: dict) -> list[MailAttachmentRef]:
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    parts: list[dict] = []
    _walk_parts(payload, parts, [0])

    received = _header(headers, "Date")
    try:
        received_iso = parsedate_to_datetime(received).isoformat() if received else ""
    except (TypeError, ValueError):
        received_iso = ""

    return [
        MailAttachmentRef(
            message_id=message.get("id", ""),
            attachment_id=part["attachment_id"],
            part_index=part["part_index"],
            filename=part["filename"],
            mime_type=part["mime_type"],
            size_bytes=part["size_bytes"],
            from_address=_header(headers, "From"),
            subject=_header(headers, "Subject"),
            received_at=received_iso,
            is_inline=part["is_inline"],
            thread_id=message.get("threadId"),
        )
        for part in parts
    ]


def _tokens_from_response(data: dict, existing_refresh: str | None) -> OAuthTokens:
    expires_in = int(data.get("expires_in") or 3600)
    return OAuthTokens(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token") or existing_refresh,
        expires_at=(datetime.utcnow() + timedelta(seconds=expires_in)).isoformat(),
        scopes=(data.get("scope") or "").split(),
    )


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return response.text[:300]
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return error.get("message") or str(error)
        description = body.get("error_description")
        if error or description:
            return f"{error or ''} {description or ''}".strip()
    return str(body)[:300]
