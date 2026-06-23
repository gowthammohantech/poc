import aiosqlite
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

DB_PATH = os.getenv("DB_PATH", "invoice_ocr.db")
_MIGRATIONS_FILE = Path(__file__).parent / "migrations.sql"


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    sql = _MIGRATIONS_FILE.read_text()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(sql)
        await db.commit()
