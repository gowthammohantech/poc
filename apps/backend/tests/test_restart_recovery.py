"""Restart recovery for connector syncs.

Sync tasks live in the server process, so a restart abandons whatever was in
flight. Both halves have to be settled on startup — the run record and the
document it was part-way through — or the attachment becomes unreachable: the
duplicate check sees a non-FAILED document and skips it on every future sync.
"""

import importlib
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
async def db_module(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="restart-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))
    from app.db import database
    importlib.reload(database)
    await database.init_db()
    yield database
    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)


async def _insert_document(db_module, status: str, source: str = "CONNECTOR", source_ref: str | None = None):
    doc_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_module.DB_PATH) as db:
        await db.execute(
            """INSERT INTO documents (id, filename, status, source, source_connector_id, source_ref)
               VALUES (?, 'invoice.pdf', ?, ?, 'conn-1', ?)""",
            (doc_id, status, source, source_ref),
        )
        await db.commit()
    return doc_id


async def _status(db_module, doc_id: str) -> str:
    async with aiosqlite.connect(db_module.DB_PATH) as db:
        cursor = await db.execute("SELECT status FROM documents WHERE id = ?", (doc_id,))
        return (await cursor.fetchone())[0]


async def _reap(db_module):
    """Reload the sync service so it binds to the test database."""
    from app.services import connector_sync_service
    importlib.reload(connector_sync_service)
    await connector_sync_service.reap_stale_runs()
    return connector_sync_service


@pytest.mark.parametrize(
    "status", ["ROUTING", "ROUTED", "OCR_RUNNING", "EXTRACTING", "EXTRACTED", "VALIDATING"]
)
async def test_documents_abandoned_mid_pipeline_are_failed(db_module, status):
    doc_id = await _insert_document(db_module, status)
    await _reap(db_module)
    assert await _status(db_module, doc_id) == "FAILED"


async def test_finished_documents_are_left_alone(db_module):
    ids = {s: await _insert_document(db_module, s) for s in
           ("VALID", "INVALID", "NEEDS_REVIEW", "COMPLETED", "FAILED")}
    await _reap(db_module)
    for expected, doc_id in ids.items():
        assert await _status(db_module, doc_id) == expected


async def test_document_awaiting_processing_is_left_alone(db_module):
    """COMPLEXITY_ANALYZED is a rest between upload and a separate /process."""
    doc_id = await _insert_document(db_module, "COMPLEXITY_ANALYZED")
    await _reap(db_module)
    assert await _status(db_module, doc_id) == "COMPLEXITY_ANALYZED"


async def test_manual_uploads_are_not_touched(db_module):
    """Only connector work is ours to settle."""
    doc_id = await _insert_document(db_module, "OCR_RUNNING", source="MANUAL")
    await _reap(db_module)
    assert await _status(db_module, doc_id) == "OCR_RUNNING"


async def test_running_sync_runs_are_failed(db_module):
    run_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_module.DB_PATH) as db:
        await db.execute(
            "INSERT INTO connector_sync_runs (id, connection_id, status) VALUES (?, 'conn-1', 'RUNNING')",
            (run_id,),
        )
        await db.commit()

    await _reap(db_module)

    async with aiosqlite.connect(db_module.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM connector_sync_runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
    assert row["status"] == "FAILED"
    assert "restart" in row["error_message"]
    assert row["finished_at"]


async def test_reaped_document_becomes_retryable(db_module):
    """The point of the whole exercise: the next sync can pick it up again.

    is_already_ingested is what the sync loop consults; a FAILED document is
    retried in place rather than skipped as a duplicate.
    """
    from app.services import connector_service
    importlib.reload(connector_service)

    doc_id = await _insert_document(db_module, "OCR_RUNNING", source_ref="msg-1:0:invoice.pdf")

    before = await connector_service.is_already_ingested("conn-1", "msg-1:0:invoice.pdf")
    assert before["status"] == "OCR_RUNNING"  # would be skipped as a duplicate

    await _reap(db_module)

    after = await connector_service.is_already_ingested("conn-1", "msg-1:0:invoice.pdf")
    assert after["id"] == doc_id
    assert after["status"] == "FAILED"  # the sync loop retries this one
