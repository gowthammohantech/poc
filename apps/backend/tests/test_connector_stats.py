"""Counters behind the connectors page.

The page has to say what the last sync pulled in without starting one, so the
numbers come from two places that drift apart on purpose: the run records are a
snapshot of what each sync saw in the mailbox, while the invoice counts track
documents that keep moving through the pipeline afterwards.
"""

import importlib
import tempfile
import uuid
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
async def sync_service(monkeypatch):
    """The sync service bound to a throwaway database."""
    tmp = Path(tempfile.mkdtemp(prefix="stats-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))
    from app.db import database
    importlib.reload(database)
    await database.init_db()

    from app.services import connector_sync_service
    importlib.reload(connector_sync_service)
    yield connector_sync_service

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)


def _db_path() -> str:
    from app.db import database
    return database.DB_PATH


async def _insert_run(connection_id="conn-1", started_at="2026-01-01T00:00:00", **counters):
    run_id = str(uuid.uuid4())
    columns = ", ".join(counters)
    placeholders = ", ".join("?" for _ in counters)
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            f"""INSERT INTO connector_sync_runs
                (id, connection_id, status, started_at{',' if columns else ''} {columns})
                VALUES (?, ?, 'COMPLETED', ?{',' if columns else ''} {placeholders})""",
            (run_id, connection_id, started_at, *counters.values()),
        )
        await db.commit()
    return run_id


async def _insert_document(status, connection_id="conn-1"):
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """INSERT INTO documents (id, filename, status, source, source_connector_id, source_ref)
               VALUES (?, 'invoice.pdf', ?, 'CONNECTOR', ?, ?)""",
            (str(uuid.uuid4()), status, connection_id, str(uuid.uuid4())),
        )
        await db.commit()


async def test_a_connection_that_has_never_synced_reports_zeroes(sync_service):
    stats = await sync_service.get_connection_stats("conn-1")
    assert stats["runs"] == 0
    assert stats["last_run"] is None
    assert stats["totals"]["messages_scanned"] == 0
    assert stats["invoices"] == {
        "total": 0, "in_progress": 0, "ready": 0, "needs_review": 0, "invalid": 0, "failed": 0
    }


async def test_totals_sum_across_every_run(sync_service):
    await _insert_run(messages_scanned=25, messages_with_attachments=6,
                      attachments_found=8, documents_processed=5)
    await _insert_run(messages_scanned=10, messages_with_attachments=2,
                      attachments_found=3, documents_processed=3, documents_failed=1)

    stats = await sync_service.get_connection_stats("conn-1")

    assert stats["runs"] == 2
    assert stats["totals"]["messages_scanned"] == 35
    assert stats["totals"]["messages_with_attachments"] == 8
    assert stats["totals"]["attachments_found"] == 11
    assert stats["totals"]["documents_processed"] == 8
    assert stats["totals"]["documents_failed"] == 1


async def test_last_run_is_the_most_recently_started(sync_service):
    await _insert_run(started_at="2026-01-01T00:00:00", messages_scanned=1)
    newest = await _insert_run(started_at="2026-03-01T00:00:00", messages_scanned=2)
    await _insert_run(started_at="2026-02-01T00:00:00", messages_scanned=3)

    stats = await sync_service.get_connection_stats("conn-1")

    assert stats["last_run"]["id"] == newest


@pytest.mark.parametrize(
    "status", ["UPLOADED", "CONVERTING", "COMPLEXITY_ANALYZED", "OCR_RUNNING", "VALIDATING"]
)
async def test_documents_still_in_the_pipeline_count_as_in_progress(sync_service, status):
    await _insert_document(status)
    stats = await sync_service.get_connection_stats("conn-1")
    assert stats["invoices"]["in_progress"] == 1
    assert stats["invoices"]["total"] == 1


async def test_settled_documents_are_split_by_outcome(sync_service):
    for status in ("VALID", "COMPLETED", "NEEDS_REVIEW", "INVALID", "FAILED"):
        await _insert_document(status)

    invoices = (await sync_service.get_connection_stats("conn-1"))["invoices"]

    assert invoices["total"] == 5
    assert invoices["in_progress"] == 0
    assert invoices["ready"] == 2      # VALID, COMPLETED
    assert invoices["needs_review"] == 1
    assert invoices["invalid"] == 1    # extracted, but did not validate
    assert invoices["failed"] == 1     # never reached an extraction


async def test_another_connections_work_is_not_counted(sync_service):
    await _insert_run(connection_id="conn-2", messages_scanned=99)
    await _insert_document("VALID", connection_id="conn-2")

    stats = await sync_service.get_connection_stats("conn-1")

    assert stats["runs"] == 0
    assert stats["totals"]["messages_scanned"] == 0
    assert stats["invoices"]["total"] == 0


async def test_manual_uploads_are_not_counted(sync_service):
    """They have no source_connector_id, so they belong to no connection."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "INSERT INTO documents (id, filename, status, source) VALUES (?, 'x.pdf', 'VALID', 'MANUAL')",
            (str(uuid.uuid4()),),
        )
        await db.commit()

    assert (await sync_service.get_connection_stats("conn-1"))["invoices"]["total"] == 0
