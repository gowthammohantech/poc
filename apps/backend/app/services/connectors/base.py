"""The contract every mail connector implements.

Deliberately provider-neutral: Gmail terminology (labels, message ids) is
generalised so a Microsoft Graph implementation can slot in without the sync
orchestration or the UI knowing the difference.
"""

from dataclasses import dataclass, field
from typing import ClassVar, Protocol, runtime_checkable


@dataclass(frozen=True)
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: str                 # ISO8601 UTC
    scopes: list[str] = field(default_factory=list)
    account_email: str | None = None


@dataclass(frozen=True)
class MailAttachmentRef:
    """A candidate attachment, described without downloading its bytes."""

    message_id: str
    attachment_id: str | None       # provider handle, if the provider has one
    part_index: int                 # stable ordinal within the message
    filename: str
    mime_type: str
    size_bytes: int
    from_address: str = ""
    subject: str = ""
    received_at: str = ""
    is_inline: bool = False
    thread_id: str | None = None

    @property
    def source_ref(self) -> str:
        """Stable identity for this attachment, used to avoid re-ingesting it.

        Composed rather than taken from the provider handle: Gmail's
        attachmentId is not stable across fetches, and Graph has no equivalent.
        """
        return f"{self.message_id}:{self.part_index}:{self.filename}"


class ConnectorError(Exception):
    """A connector could not complete an operation."""


class ConnectorAuthError(ConnectorError):
    """Credentials are missing, expired, or revoked. Requires re-authorisation."""


class ConnectorRateLimitError(ConnectorError):
    """The provider asked us to back off."""


@runtime_checkable
class MailConnector(Protocol):
    provider: ClassVar[str]
    label: ClassVar[str]
    default_scopes: ClassVar[list[str]]

    def is_configured(self) -> bool:
        """True when the credentials this connector needs are present."""
        ...

    def build_authorization_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens: ...

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens: ...

    async def get_account_email(self, access_token: str) -> str: ...

    async def list_folders(self, access_token: str) -> list[dict]:
        """Selectable folders/labels as [{id, name}], for the filter dropdown."""
        ...

    async def list_attachments(
        self,
        access_token: str,
        *,
        query: str | None,
        label_id: str | None,
        max_messages: int,
    ) -> tuple[list[MailAttachmentRef], int]:
        """Return (candidate attachments, number of messages scanned)."""
        ...

    async def fetch_attachment(self, access_token: str, ref: MailAttachmentRef) -> bytes: ...
