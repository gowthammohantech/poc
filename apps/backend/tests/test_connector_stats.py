"""Counters behind the connectors page.

The page has to say what the last sync pulled in without starting one, so the
numbers come from two places that drift apart on purpose: the run records are a
snapshot of what each sync saw in the mailbox, while the invoice counts track
documents that keep moving through the pipeline afterwards.
"""

import uuid

import pytest

from app.services import connector_sync_service


@pytest.fixture
def add_document(make_document):
    async def _add(status, connection_id="conn-1"):
        return await make_document(
            status=status,
            source="CONNECTOR",
            source_connector_id=connection_id,
            source_ref=str(uuid.uuid4()),
        )

    return _add


async def test_a_connection_that_has_never_synced_reports_zeroes(mongo_db):
    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["runs"] == 0
    assert stats["last_run"] is None
    assert stats["totals"]["messages_scanned"] == 0
    assert stats["invoices"] == {
        "total": 0, "in_progress": 0, "ready": 0, "needs_review": 0, "invalid": 0, "failed": 0
    }


async def test_every_counter_is_present_even_with_no_runs(mongo_db):
    """The UI reads these by name; a missing key is a crash, not a zero."""
    totals = (await connector_sync_service.get_connection_stats("conn-1"))["totals"]

    assert set(totals) == set(connector_sync_service._TOTAL_COLUMNS)


async def test_totals_sum_across_every_run(mongo_db, make_run):
    await make_run(messages_scanned=25, messages_with_attachments=6,
                   attachments_found=8, documents_processed=5)
    await make_run(messages_scanned=10, messages_with_attachments=2,
                   attachments_found=3, documents_processed=3, documents_failed=1)

    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["runs"] == 2
    assert stats["totals"]["messages_scanned"] == 35
    assert stats["totals"]["messages_with_attachments"] == 8
    assert stats["totals"]["attachments_found"] == 11
    assert stats["totals"]["documents_processed"] == 8
    assert stats["totals"]["documents_failed"] == 1


async def test_skips_are_totalled_by_reason(mongo_db, make_run):
    """One number for every skip cannot say why anything was passed over, which
    is how a filter bug hid: dropped invoices read as unsupported files."""
    await make_run(skipped_unsupported=2, skipped_inline=3, skipped_duplicates=1)
    await make_run(skipped_unsupported=1, skipped_inline=4)

    totals = (await connector_sync_service.get_connection_stats("conn-1"))["totals"]

    assert totals["skipped_unsupported"] == 3
    assert totals["skipped_inline"] == 7
    assert totals["skipped_duplicates"] == 1


async def test_last_run_is_the_most_recently_started(mongo_db, make_run):
    await make_run(started_at="2026-01-01T00:00:00", messages_scanned=1)
    newest = await make_run(started_at="2026-03-01T00:00:00", messages_scanned=2)
    await make_run(started_at="2026-02-01T00:00:00", messages_scanned=3)

    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["last_run"]["id"] == newest


@pytest.mark.parametrize(
    "status", ["UPLOADED", "CONVERTING", "COMPLEXITY_ANALYZED", "OCR_RUNNING", "VALIDATING"]
)
async def test_documents_still_in_the_pipeline_count_as_in_progress(mongo_db, add_document, status):
    await add_document(status)

    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["invoices"]["in_progress"] == 1
    assert stats["invoices"]["total"] == 1


async def test_settled_documents_are_split_by_outcome(mongo_db, add_document):
    for status in ("VALID", "COMPLETED", "NEEDS_REVIEW", "INVALID", "FAILED"):
        await add_document(status)

    invoices = (await connector_sync_service.get_connection_stats("conn-1"))["invoices"]

    assert invoices["total"] == 5
    assert invoices["in_progress"] == 0
    assert invoices["ready"] == 2      # VALID, COMPLETED
    assert invoices["needs_review"] == 1
    assert invoices["invalid"] == 1    # extracted, but did not validate
    assert invoices["failed"] == 1     # never reached an extraction


async def test_another_connections_work_is_not_counted(mongo_db, make_run, add_document):
    await make_run(connection_id="conn-2", messages_scanned=99)
    await add_document("VALID", connection_id="conn-2")

    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["runs"] == 0
    assert stats["totals"]["messages_scanned"] == 0
    assert stats["invoices"]["total"] == 0


async def test_manual_uploads_are_not_counted(mongo_db, make_document):
    """They have no source_connector_id, so they belong to no connection."""
    await make_document(source="MANUAL")

    stats = await connector_sync_service.get_connection_stats("conn-1")

    assert stats["invoices"]["total"] == 0
