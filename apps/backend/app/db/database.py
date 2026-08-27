import aiosqlite
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

DB_PATH = os.getenv("DB_PATH", "invoice_ocr.db")
_MIGRATIONS_FILE = Path(__file__).parent / "migrations.sql"
_BRS_MIGRATIONS_FILE = Path(__file__).parent / "brs_migrations.sql"
_CONNECTOR_MIGRATIONS_FILE = Path(__file__).parent / "connector_migrations.sql"

_MIGRATION_FILES = [_MIGRATIONS_FILE, _BRS_MIGRATIONS_FILE, _CONNECTOR_MIGRATIONS_FILE]

# Columns added to tables that already exist in deployed databases. The .sql
# files are re-executed verbatim on every boot, so an ALTER TABLE there would
# raise "duplicate column" on the second run and abort the rest of the script.
# These are applied one at a time, guarded by PRAGMA table_info.
_COLUMN_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "documents": [
        ("source", "TEXT NOT NULL DEFAULT 'MANUAL'"),
        ("source_connector_id", "TEXT"),
        ("source_ref", "TEXT"),
        ("source_metadata", "TEXT"),
    ],
    "connector_sync_runs": [
        ("messages_with_attachments", "INTEGER DEFAULT 0"),
        ("skipped_inline", "INTEGER DEFAULT 0"),
    ],
}

# Run after the ALTERs: these reference columns that may not exist yet.
_POST_ALTER_STATEMENTS = [
    "UPDATE documents SET source = 'MANUAL' WHERE source IS NULL",
    """CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_source_ref
       ON documents(source_connector_id, source_ref)
       WHERE source_ref IS NOT NULL""",
    "CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source)",
]


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        # A connector sync writes steadily for minutes. WAL keeps readers from
        # blocking, but concurrent writers still need to wait rather than fail.
        await db.execute("PRAGMA busy_timeout=10000")
        yield db


async def _apply_column_additions(db: aiosqlite.Connection):
    for table, columns in _COLUMN_ADDITIONS.items():
        cursor = await db.execute(f"PRAGMA table_info({table})")
        existing = {row["name"] for row in await cursor.fetchall()}
        for name, ddl in columns:
            if name not in existing:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


async def init_db():
    for migrations_file in _MIGRATION_FILES:
        sql = migrations_file.read_text()
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.executescript(sql)
            await db.commit()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await _apply_column_additions(db)
        for statement in _POST_ALTER_STATEMENTS:
            await db.execute(statement)
        await db.commit()
