from fastapi import APIRouter, HTTPException

from app.services import ledger_service
from app.schemas.ledger_schema import LedgerEntryCreate, LedgerEntryUpdate

router = APIRouter()


@router.post("")
async def create_ledger_entry(body: LedgerEntryCreate):
    entry_id = await ledger_service.create_entry(body)
    entry = await ledger_service.get_entry(entry_id)
    return entry


@router.get("")
async def list_ledger_entries():
    return await ledger_service.get_all_entries()


@router.get("/{entry_id}")
async def get_ledger_entry(entry_id: str):
    entry = await ledger_service.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    return entry


@router.put("/{entry_id}")
async def update_ledger_entry(entry_id: str, body: LedgerEntryUpdate):
    existing = await ledger_service.get_entry(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    await ledger_service.update_entry(entry_id, body)
    return await ledger_service.get_entry(entry_id)


@router.delete("/{entry_id}")
async def delete_ledger_entry(entry_id: str):
    existing = await ledger_service.get_entry(entry_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    await ledger_service.delete_entry(entry_id)
    return {"status": "deleted", "id": entry_id}
