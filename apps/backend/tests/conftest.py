"""Shared fixtures for the database tests.

Every test that touches storage gets its own throwaway Mongo database, created
on entry and dropped on exit, so tests are order-independent.

These run against a real MongoDB rather than mongomock: the suite asserts on
partial unique index enforcement and aggregation semantics that mongomock does
not reproduce faithfully, so passing against a fake would prove nothing about
the deployed behaviour. Point MONGO_TEST_URI at a server — or set MONGODB_URI —
and they run; with no server reachable they skip rather than fail.

Configuration is read per call inside app.db.mongo, so monkeypatch.setenv is
enough to redirect the whole process. The SQLite layer this replaced needed an
importlib.reload of the database module, duplicated in eight test files.
"""

import itertools
import os
import uuid
from datetime import datetime

import pytest
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.db import mongo

TEST_URI = os.getenv("MONGO_TEST_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017"

_SEQUENCE = itertools.count()

# Probed once and remembered. Asking per test would otherwise spend the full
# server-selection timeout on each one before skipping.
_server_reachable: bool | None = None


async def _reachable() -> bool:
    global _server_reachable
    if _server_reachable is None:
        client = AsyncMongoClient(TEST_URI, serverSelectionTimeoutMS=1500)
        try:
            await client.admin.command("ping")
            _server_reachable = True
        except PyMongoError:
            _server_reachable = False
        finally:
            await client.close()
    return _server_reachable


@pytest.fixture(autouse=True)
def no_real_blob_storage(monkeypatch):
    """Keep every test on local disk.

    file_storage_service falls back to local-only when this is unset, which is
    the behaviour the suite asserts. Without this an .env picked up from the
    environment would silently point the tests at the live storage account.
    """
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)


@pytest.fixture
async def mongo_db(monkeypatch):
    """An empty database with every index and validator applied."""
    monkeypatch.setenv("MONGODB_URI", TEST_URI)
    monkeypatch.setenv("MONGO_DB_NAME", f"invoice_ocr_test_{uuid.uuid4().hex[:12]}")

    if not await _reachable():
        pytest.skip(
            f"No MongoDB reachable at {TEST_URI}. "
            "Set MONGO_TEST_URI to run the database tests."
        )

    # A client built for an earlier test is bound to that test's event loop.
    await mongo.close_client()

    await mongo.ensure_indexes()
    database = mongo.get_database()
    try:
        yield database
    finally:
        await mongo.get_client().drop_database(database.name)
        await mongo.close_client()


def _timestamp() -> str:
    """Distinct, increasing timestamps so sort order is deterministic."""
    return f"2026-01-01T00:00:{next(_SEQUENCE):06d}"


@pytest.fixture
def make_document(mongo_db):
    """Insert a document carrying the same full field set create_document writes.

    Taking the defaults from the service keeps these fixtures honest: a field
    added there shows up here without anyone having to remember.
    """
    from app.services.document_service import _DOCUMENT_DEFAULTS

    async def _make(doc_id: str | None = None, **overrides) -> str:
        doc_id = doc_id or str(uuid.uuid4())
        now = _timestamp()
        record = {
            **_DOCUMENT_DEFAULTS,
            "_id": doc_id,
            "filename": f"{doc_id}.pdf",
            "status": "VALID",
            "created_at": now,
            "updated_at": now,
            "pages": [],
        }
        record.update(overrides)
        await mongo_db.documents.insert_one(record)
        return doc_id

    return _make


@pytest.fixture
def make_run(mongo_db):
    """Insert a connector_sync_runs record with its counters defaulted to zero."""
    from app.services.connector_sync_service import _RUN_DEFAULTS

    async def _make(connection_id: str = "conn-1", **overrides) -> str:
        run_id = overrides.pop("run_id", None) or str(uuid.uuid4())
        record = {
            **_RUN_DEFAULTS,
            "_id": run_id,
            "connection_id": connection_id,
            "status": "COMPLETED",
            "trigger": "MANUAL",
            "started_at": "2026-01-01T00:00:00",
        }
        record.update(overrides)
        await mongo_db.connector_sync_runs.insert_one(record)
        return run_id

    return _make


@pytest.fixture
def document_status(mongo_db):
    """Read one document's status back out of the store."""

    async def _status(doc_id: str) -> str | None:
        found = await mongo_db.documents.find_one({"_id": doc_id}, {"status": 1})
        return found["status"] if found else None

    return _status
