"""Registry of available mail connectors.

Adding a provider is one new module and one entry here; nothing in the sync
orchestration, the API layer or the UI needs to know it exists.
"""

from app.services.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    MailAttachmentRef,
    MailConnector,
    OAuthTokens,
)
from app.services.connectors.fake_connector import FakeConnector
from app.services.connectors.gmail_connector import GmailConnector

__all__ = [
    "ConnectorAuthError",
    "ConnectorError",
    "ConnectorRateLimitError",
    "MailAttachmentRef",
    "MailConnector",
    "OAuthTokens",
    "available_providers",
    "get_connector",
]

_gmail = GmailConnector()
_fake = FakeConnector()

# The sample mailbox is always offered next to Gmail, so the connector path can
# be walked end to end without Google credentials.
_REGISTRY: dict[str, MailConnector] = {
    _gmail.provider: _gmail,
    _fake.provider: _fake,
}

# Listed so the UI can show it as coming soon before the adapter exists.
_PLANNED = [{"provider": "OUTLOOK", "label": "Outlook", "configured": False, "enabled": False}]


def get_connector(provider: str) -> MailConnector:
    connector = _REGISTRY.get((provider or "").upper())
    if connector is None:
        raise ConnectorError(f"Unknown connector provider: {provider}")
    return connector


def available_providers() -> list[dict]:
    """Every provider the UI should render, whether or not it is usable yet."""
    return [
        {
            "provider": connector.provider,
            "label": connector.label,
            "configured": connector.is_configured(),
            "enabled": True,
        }
        for connector in _REGISTRY.values()
    ] + _PLANNED
