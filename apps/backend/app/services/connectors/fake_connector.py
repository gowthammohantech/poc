"""A mailbox that isn't one, for exercising the connector path without Google.

Synthesises messages from the sample invoices in the repo's invoices/ folder,
including a duplicate and an unsupported file so the skip paths get walked too.
Always listed alongside the real providers; it reports itself as unconfigured
when the sample folder is missing.
"""

import os
from pathlib import Path

from app.services.connectors.base import ConnectorError, MailAttachmentRef, OAuthTokens

_SAMPLE_DIR = Path(os.getenv("CONNECTOR_FAKE_DIR", "")) if os.getenv("CONNECTOR_FAKE_DIR") else \
    Path(__file__).resolve().parents[5] / "invoices"

_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".txt": "text/plain",
}

_SENDERS = [
    ("billing@acme-supplies.example", "Invoice for October"),
    ("accounts@northwind-traders.example", "Your invoice is attached"),
    ("no-reply@globex-logistics.example", "Statement + invoice"),
]

_FOLDERS = [
    {"id": "INBOX", "name": "Inbox"},
    {"id": "Label_Invoices", "name": "Invoices"},
]


class FakeConnector:
    provider = "FAKE"
    label = "Sample Mailbox"
    default_scopes: list[str] = []

    def is_configured(self) -> bool:
        return _SAMPLE_DIR.is_dir()

    def build_authorization_url(self, *, state: str, redirect_uri: str) -> str:
        # No consent screen to visit — the callback completes immediately.
        return f"{redirect_uri}?code=fake-code&state={state}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens:
        return OAuthTokens(
            access_token="fake-access-token",
            refresh_token="fake-refresh-token",
            expires_at="2999-01-01T00:00:00",
            scopes=[],
            account_email="sample.mailbox@example.com",
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        return await self.exchange_code(code="fake-code", redirect_uri="")

    async def get_account_email(self, access_token: str) -> str:
        return "sample.mailbox@example.com"

    async def list_folders(self, access_token: str) -> list[dict]:
        return list(_FOLDERS)

    async def list_attachments(
        self, access_token: str, *, query: str | None, label_id: str | None, max_messages: int,
    ) -> tuple[list[MailAttachmentRef], int]:
        if not _SAMPLE_DIR.is_dir():
            raise ConnectorError(f"Sample folder not found: {_SAMPLE_DIR}")

        files = sorted(p for p in _SAMPLE_DIR.iterdir() if p.is_file())[: max(1, max_messages)]
        refs: list[MailAttachmentRef] = []

        for i, path in enumerate(files):
            sender, subject = _SENDERS[i % len(_SENDERS)]
            refs.append(_ref(f"fake-msg-{i:03d}", 0, path, sender, f"{subject} ({path.stem})", i))

        if refs:
            # A resend of the first invoice — should be skipped as a duplicate
            # on the second sync, and ingested exactly once on the first.
            first = files[0]
            sender, subject = _SENDERS[0]
            refs.append(_ref("fake-msg-000", 0, first, sender, subject, 0))

            # An unsupported attachment, so the skip path gets exercised.
            refs.append(MailAttachmentRef(
                message_id="fake-msg-notes",
                attachment_id=None,
                part_index=0,
                filename="delivery-notes.txt",
                mime_type="text/plain",
                size_bytes=2048,
                from_address=_SENDERS[1][0],
                subject="Delivery notes (no invoice)",
                received_at="2026-01-15T09:00:00",
            ))

        return refs, len({r.message_id for r in refs})

    async def fetch_attachment(self, access_token: str, ref: MailAttachmentRef) -> bytes:
        path = _SAMPLE_DIR / ref.filename
        if not path.is_file():
            raise ConnectorError(f"Sample attachment missing: {ref.filename}")
        return path.read_bytes()


def _ref(message_id: str, part_index: int, path: Path, sender: str, subject: str, day: int) -> MailAttachmentRef:
    return MailAttachmentRef(
        message_id=message_id,
        attachment_id=None,
        part_index=part_index,
        filename=path.name,
        mime_type=_MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream"),
        size_bytes=path.stat().st_size,
        from_address=sender,
        subject=subject,
        received_at=f"2026-01-{(day % 28) + 1:02d}T09:00:00",
    )
