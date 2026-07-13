import aiosqlite
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

DB_PATH = os.getenv("DB_PATH", "invoice_ocr.db")
_MIGRATIONS_FILE = Path(__file__).parent / "migrations.sql"
_BRS_MIGRATIONS_FILE = Path(__file__).parent / "brs_migrations.sql"
_LEDGER_MIGRATIONS_FILE = Path(__file__).parent / "ledger_migrations.sql"


def _infer_ledger_name(description: str | None) -> str | None:
    if not description:
        return None

    value = description.strip()
    lower = value.lower()

    prefixes = [
        "cheque to ",
        "check to ",
        "payment to ",
        "paid to ",
        "upi ",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            return value[len(prefix):].strip() or value

    suffixes = [
        " settlement received",
        " payment issued, cheque not yet presented",
        " recorded in books, not yet credited",
        " received",
    ]
    for suffix in suffixes:
        if lower.endswith(suffix):
            return value[: -len(suffix)].strip(" -,:") or value

    if lower.startswith("cash deposit - "):
        return value[len("cash deposit - "):].strip() or value

    return value


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    for migrations_file in [_MIGRATIONS_FILE, _BRS_MIGRATIONS_FILE, _LEDGER_MIGRATIONS_FILE]:
        sql = migrations_file.read_text()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.executescript(sql)
            await db.commit()

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(ledger_entries)")
        columns = {row[1] for row in await cursor.fetchall()}
        added_ledger_name_column = False
        if "ledger_name" not in columns:
            await db.execute("ALTER TABLE ledger_entries ADD COLUMN ledger_name TEXT")
            added_ledger_name_column = True

        if added_ledger_name_column:
            cursor = await db.execute("SELECT id, description FROM ledger_entries")
            rows = await cursor.fetchall()
            for row in rows:
                await db.execute(
                    "UPDATE ledger_entries SET ledger_name = ? WHERE id = ?",
                    (_infer_ledger_name(row[1]), row[0]),
                )
            await db.commit()
