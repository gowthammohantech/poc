from pydantic import BaseModel
from typing import Optional, Literal


class LedgerEntryCreate(BaseModel):
    entry_date: str
    ledger_name: Optional[str] = None
    description: str
    reference_number: Optional[str] = None
    amount: float
    entry_type: Literal["DEBIT", "CREDIT"]
    notes: Optional[str] = None


class LedgerEntryUpdate(BaseModel):
    entry_date: str
    ledger_name: Optional[str] = None
    description: str
    reference_number: Optional[str] = None
    amount: float
    entry_type: Literal["DEBIT", "CREDIT"]
    notes: Optional[str] = None
