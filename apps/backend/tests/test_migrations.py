"""The migration runner must be safe to run on every boot.

init_db() re-executes the .sql files each time the app starts, so the column
additions have to be guarded and the backfill has to leave existing rows alone
on the second pass.
"""

import os
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """A database module pointed at a throwaway file."""
    import importlib

    tmp = Path(tempfile.mkdtemp(prefix="migrations-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))

    from app.db import database
    importlib.reload(database)
    assert database.DB_PATH == str(tmp)
    yield database

    # Leave the module pointing at whatever the environment says again.
    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)


async def _columns(db_path: str, table: str) -> set[str]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(f"PRAGMA table_info({table})")
        return {row["name"] for row in await cursor.fetchall()}


@pytest.mark.asyncio
async def test_creates_documents_source_columns(fresh_db):
    await fresh_db.init_db()
    columns = await _columns(fresh_db.DB_PATH, "documents")
    assert {"source", "source_connector_id", "source_ref", "source_metadata"} <= columns


@pytest.mark.asyncio
async def test_creates_connector_tables(fresh_db):
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'connector%'"
        )
        tables = {row["name"] for row in await cursor.fetchall()}
    assert tables == {"connector_connections", "connector_sync_runs", "connector_sync_items"}


@pytest.mark.asyncio
async def test_creates_sync_run_counter_columns(fresh_db):
    await fresh_db.init_db()
    columns = await _columns(fresh_db.DB_PATH, "connector_sync_runs")
    assert "messages_with_attachments" in columns


@pytest.mark.asyncio
async def test_adds_the_counter_column_to_a_database_created_before_it(fresh_db):
    """CREATE TABLE IF NOT EXISTS leaves an existing table alone, so the column
    only reaches a deployed database through the guarded ALTER."""
    sql = (Path(fresh_db.__file__).parent / "connector_migrations.sql").read_text()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        without_column = [
            line for line in sql.splitlines(keepends=True)
            if "messages_with_attachments" not in line
        ]
        await db.executescript("".join(without_column))
        await db.execute(
            "INSERT INTO connector_sync_runs (id, connection_id) VALUES ('run-1', 'conn-1')"
        )
        await db.commit()

    await fresh_db.init_db()

    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT messages_with_attachments FROM connector_sync_runs WHERE id = 'run-1'"
        )
        assert (await cursor.fetchone())["messages_with_attachments"] == 0


@pytest.mark.asyncio
async def test_is_idempotent(fresh_db):
    await fresh_db.init_db()
    await fresh_db.init_db()
    await fresh_db.init_db()
    columns = await _columns(fresh_db.DB_PATH, "documents")
    assert "source" in columns


@pytest.mark.asyncio
async def test_backfills_rows_written_before_the_column_existed(fresh_db):
    """Simulate a database created by the previous schema, then migrate it."""
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        await db.executescript(
            (Path(fresh_db.__file__).parent / "migrations.sql").read_text()
        )
        await db.execute(
            "INSERT INTO documents (id, filename, status) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), "legacy-invoice.pdf", "COMPLETED"),
        )
        await db.commit()

    await fresh_db.init_db()

    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT source, source_ref FROM documents")
        rows = [dict(r) for r in await cursor.fetchall()]

    assert rows == [{"source": "MANUAL", "source_ref": None}]


@pytest.mark.asyncio
async def test_source_ref_is_unique_per_connection(fresh_db):
    """The backstop that stops one attachment becoming two documents."""
    insert = """INSERT INTO documents (id, filename, status, source, source_connector_id, source_ref)
                VALUES (?, ?, 'VALID', 'CONNECTOR', 'conn-1', 'msg-1:0:invoice.pdf')"""
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        await db.execute(insert, (str(uuid.uuid4()), "invoice.pdf"))
        await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(insert, (str(uuid.uuid4()), "invoice.pdf"))


@pytest.mark.asyncio
async def test_null_source_refs_do_not_collide(fresh_db):
    """Manual uploads all have a NULL source_ref; the index must ignore them."""
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        for name in ("a.pdf", "b.pdf", "c.pdf"):
            await db.execute(
                "INSERT INTO documents (id, filename, status) VALUES (?, ?, 'VALID')",
                (str(uuid.uuid4()), name),
            )
        await db.commit()
        cursor = await db.execute("SELECT COUNT(*) FROM documents")
        assert (await cursor.fetchone())[0] == 3
