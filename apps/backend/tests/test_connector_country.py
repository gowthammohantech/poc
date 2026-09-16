"""A mailbox connection carries the regime its attachments are processed under.

Before this, everything a connector pulled was filed as INDIA, so a mailbox
feeding the US pipeline produced documents the US documents list never showed.
The country now lives on the connection: chosen when it is connected, editable
afterwards, and read by every sync.
"""

import importlib
import tempfile
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """A database module pointed at a throwaway file."""
    tmp = Path(tempfile.mkdtemp(prefix="connector-country-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))

    from app.db import database
    importlib.reload(database)
    assert database.DB_PATH == str(tmp)
    yield database

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)


class TestConnectionCountry:
    """What the sync reads off a connection row."""

    def test_a_row_without_a_country_is_india(self):
        """Connections made before the column existed carry NULL."""
        from app.services import connector_service

        assert connector_service.connection_country({"country": None}) == "INDIA"
        assert connector_service.connection_country({}) == "INDIA"

    def test_case_is_normalised(self):
        from app.services import connector_service

        assert connector_service.connection_country({"country": "usa"}) == "USA"

    def test_an_unknown_country_falls_back_to_india(self):
        """Neither pipeline would run for a value outside the two regimes."""
        from app.services import connector_service

        assert connector_service.connection_country({"country": "CANADA"}) == "INDIA"


@pytest.mark.asyncio
async def test_fresh_database_has_the_connection_country(fresh_db):
    await fresh_db.init_db()
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("PRAGMA table_info(connector_connections)")
        columns = {row["name"] for row in await cursor.fetchall()}
    assert "country" in columns


@pytest.mark.asyncio
async def test_upgrade_backfills_existing_connections_to_india(fresh_db):
    """A mailbox connected before the column existed kept feeding India."""
    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        await db.execute(
            """CREATE TABLE connector_connections (
                   id TEXT PRIMARY KEY,
                   provider TEXT NOT NULL,
                   status TEXT NOT NULL DEFAULT 'PENDING'
               )"""
        )
        await db.execute(
            "INSERT INTO connector_connections (id, provider) VALUES ('old-1', 'GMAIL')"
        )
        await db.commit()

    await fresh_db.init_db()

    async with aiosqlite.connect(fresh_db.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT country FROM connector_connections WHERE id = 'old-1'"
        )
        row = await cursor.fetchone()
    assert row["country"] == "INDIA"


@pytest.mark.asyncio
async def test_connecting_stores_the_chosen_country(fresh_db):
    """The regime the user is working in is fixed onto the pending connection."""
    from app.services import connector_service

    await fresh_db.init_db()
    connection_id, _url = await connector_service.begin_oauth("FAKE", country="USA")
    connection = await connector_service.get_connection(connection_id)

    assert connector_service.connection_country(connection) == "USA"


@pytest.mark.asyncio
async def test_connecting_without_a_country_is_india(fresh_db):
    from app.services import connector_service

    await fresh_db.init_db()
    connection_id, _url = await connector_service.begin_oauth("FAKE")
    connection = await connector_service.get_connection(connection_id)

    assert connector_service.connection_country(connection) == "INDIA"


@pytest.mark.asyncio
async def test_the_country_is_normalised_on_update(fresh_db):
    """The filters form posts whatever the select holds; junk must not stick."""
    from app.services import connector_service

    await fresh_db.init_db()
    connection_id, _url = await connector_service.begin_oauth("FAKE")

    await connector_service.update_connection(connection_id, country="usa")
    assert connector_service.connection_country(
        await connector_service.get_connection(connection_id)
    ) == "USA"

    await connector_service.update_connection(connection_id, country="ATLANTIS")
    assert connector_service.connection_country(
        await connector_service.get_connection(connection_id)
    ) == "INDIA"
