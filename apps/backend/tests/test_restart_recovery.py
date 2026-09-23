"""Restart recovery for connector syncs.

Sync tasks live in the server process, so a restart abandons whatever was in
flight. Both halves have to be settled on startup — the run record and the
document it was part-way through — or the attachment becomes unreachable: the
duplicate check sees a non-FAILED document and skips it on every future sync.
"""

import pytest

from app.services import connector_service, connector_sync_service


@pytest.fixture
def add_document(make_document):
    async def _add(status, source="CONNECTOR", source_ref=None):
        return await make_document(
            status=status,
            source=source,
            source_connector_id="conn-1",
            source_ref=source_ref,
        )

    return _add


@pytest.mark.parametrize(
    "status", ["ROUTING", "ROUTED", "OCR_RUNNING", "EXTRACTING", "EXTRACTED", "VALIDATING"]
)
async def test_documents_abandoned_mid_pipeline_are_failed(
    mongo_db, add_document, document_status, status
):
    doc_id = await add_document(status)

    await connector_sync_service.reap_stale_runs()

    assert await document_status(doc_id) == "FAILED"


async def test_finished_documents_are_left_alone(mongo_db, add_document, document_status):
    ids = {s: await add_document(s) for s in
           ("VALID", "INVALID", "NEEDS_REVIEW", "COMPLETED", "FAILED")}

    await connector_sync_service.reap_stale_runs()

    for expected, doc_id in ids.items():
        assert await document_status(doc_id) == expected


async def test_document_awaiting_processing_is_left_alone(mongo_db, add_document, document_status):
    """COMPLEXITY_ANALYZED is a rest between upload and a separate /process."""
    doc_id = await add_document("COMPLEXITY_ANALYZED")

    await connector_sync_service.reap_stale_runs()

    assert await document_status(doc_id) == "COMPLEXITY_ANALYZED"


async def test_manual_uploads_are_not_touched(mongo_db, add_document, document_status):
    """Only connector work is ours to settle."""
    doc_id = await add_document("OCR_RUNNING", source="MANUAL")

    await connector_sync_service.reap_stale_runs()

    assert await document_status(doc_id) == "OCR_RUNNING"


async def test_running_sync_runs_are_failed(mongo_db, make_run):
    run_id = await make_run(status="RUNNING")

    await connector_sync_service.reap_stale_runs()

    run = await connector_sync_service.get_run(run_id)
    assert run["status"] == "FAILED"
    assert "restart" in run["error_message"]
    assert run["finished_at"]


async def test_settled_runs_are_left_alone(mongo_db, make_run):
    run_id = await make_run(status="COMPLETED", finished_at="2026-01-01T01:00:00")

    await connector_sync_service.reap_stale_runs()

    run = await connector_sync_service.get_run(run_id)
    assert run["status"] == "COMPLETED"
    assert run["error_message"] is None


async def test_reaped_document_becomes_retryable(mongo_db, add_document):
    """The point of the whole exercise: the next sync can pick it up again.

    is_already_ingested is what the sync loop consults; a FAILED document is
    retried in place rather than skipped as a duplicate.
    """
    doc_id = await add_document("OCR_RUNNING", source_ref="msg-1:0:invoice.pdf")

    before = await connector_service.is_already_ingested("conn-1", "msg-1:0:invoice.pdf")
    assert before["status"] == "OCR_RUNNING"  # would be skipped as a duplicate

    await connector_sync_service.reap_stale_runs()

    after = await connector_service.is_already_ingested("conn-1", "msg-1:0:invoice.pdf")
    assert after["id"] == doc_id
    assert after["status"] == "FAILED"  # the sync loop retries this one
