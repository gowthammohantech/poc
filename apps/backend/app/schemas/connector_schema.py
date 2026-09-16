from pydantic import BaseModel
from typing import Optional


class ProviderResponse(BaseModel):
    provider: str
    label: str
    configured: bool
    enabled: bool


class OAuthStartRequest(BaseModel):
    """Which regime the mailbox is being connected for; defaults to India."""

    country: Optional[str] = None


class OAuthStartResponse(BaseModel):
    connection_id: str
    authorization_url: str


class FilterUpdate(BaseModel):
    country: Optional[str] = None
    filter_label: Optional[str] = None
    filter_label_name: Optional[str] = None
    filter_query: Optional[str] = None
    max_messages_per_sync: Optional[int] = None


class SyncStartResponse(BaseModel):
    run_id: str
    status: str
