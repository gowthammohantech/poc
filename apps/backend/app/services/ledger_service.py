import uuid
from datetime import datetime
from typing import Optional

from app.db.database import get_db
from app.schemas.ledger_schema import LedgerEntryCreate, LedgerEntryUpdate


async def create_entry(data: LedgerEntryCreate) -> str:
    entry_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO ledger_entries
               (id, entry_date, ledger_name, description, reference_number, amount, entry_type, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entry_id, data.entry_date, data.ledger_name, data.description, data.reference_number,
             data.amount, data.entry_type, data.notes, now, now),
        )
        await db.commit()
    return entry_id


async def get_entry(entry_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM ledger_entries WHERE id = ?", (entry_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_entries() -> list:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM ledger_entries ORDER BY entry_date DESC, created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_entry(entry_id: str, data: LedgerEntryUpdate) -> bool:
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            """UPDATE ledger_entries
               SET entry_date = ?, ledger_name = ?, description = ?, reference_number = ?, amount = ?,
                   entry_type = ?, notes = ?, updated_at = ?
               WHERE id = ?""",
            (data.entry_date, data.ledger_name, data.description, data.reference_number, data.amount,
             data.entry_type, data.notes, now, entry_id),
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_entry(entry_id: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute("DELETE FROM ledger_entries WHERE id = ?", (entry_id,))
        await db.commit()
        return cursor.rowcount > 0
