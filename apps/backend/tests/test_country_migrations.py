"""The country dimension must reach databases that predate it.

documents.country decides which extraction regime a document runs under, so an
existing row that was ingested before the column existed has to end up as
INDIA rather than NULL — otherwise the pipeline would not know how to route it.
"""

import tempfile
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """A database module pointed at a throwaway file."""
    import importlib

    tmp = Path(tempfile.mkdtemp(prefix="country-migrations-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))

    from app.db import database
    importlib.reload(database)
    assert database.DB_PATH == str(tmp)
    yield database

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)


async def _columns(db_path: str, table: str) -> set[str]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_fresh_database_has_country_columns(fresh_db):
    await fresh_db.init_db()
    columns = await _columns(fresh_db.DB_PATH, "documents")
    assert {"country", "doc_type"} <= columns


@pytest.mark.asyncio
async def test_country_defaults_to_india(fresh_db):
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "INSERT INTO documents (id, filename) VALUES ('doc-1', 'invoice.pdf')"
        )
        await db.commit()
        cursor = await db.execute("SELECT country, doc_type FROM documents WHERE id = 'doc-1'")
        row = await cursor.fetchone()
    assert row["country"] == "INDIA"
    assert row["doc_type"] is None


@pytest.mark.asyncio
async def test_upgrade_backfills_existing_rows_to_india(fresh_db):
    """A database built before the column existed keeps its rows, as INDIA."""
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        await db.execute(
            """CREATE TABLE documents (
                   id TEXT PRIMARY KEY,
                   filename TEXT NOT NULL,
                   status TEXT DEFAULT 'UPLOADED'
               )"""
        )
        await db.execute("INSERT INTO documents (id, filename) VALUES ('old-1', 'legacy.pdf')")
        await db.commit()

    await fresh_db.init_db()

    columns = await _columns(fresh_db.DB_PATH, "documents")
    assert {"country", "doc_type"} <= columns
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT country FROM documents WHERE id = 'old-1'")
        row = await cursor.fetchone()
    assert row["country"] == "INDIA"


@pytest.mark.asyncio
async def test_init_db_is_idempotent_with_country_columns(fresh_db):
    """The .sql files re-run on every boot; a second pass must not raise."""
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        await db.execute(
            "INSERT INTO documents (id, filename, country) VALUES ('doc-us', 'po.pdf', 'USA')"
        )
        await db.commit()

    await fresh_db.init_db()

    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT country FROM documents WHERE id = 'doc-us'")
        row = await cursor.fetchone()
    assert row["country"] == "USA", "the backfill must not overwrite a set country"
