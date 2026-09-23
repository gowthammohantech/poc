"""Deleting documents from the list removes everything they produced.

A deleted document leaves nothing behind: no record, no files on disk, and no
trace that would stop a mailbox sync from ingesting its attachment again.
"""

import pytest

from app.services import connector_service, document_service, file_storage_service

# The stage results live on the document now, so deleting it takes them with
# it. These are the keys that must be gone because the parent is.
EMBEDDED_STAGES = ("pages", "ocr", "extraction", "validation", "final_output")


@pytest.fixture
def storage(tmp_path, monkeypatch):
    """Point the storage layer at a throwaway directory."""
    base = tmp_path / "uploads"
    base.mkdir()
    monkeypatch.setattr(file_storage_service, "STORAGE_BASE", base)
    return base


@pytest.fixture
def seed(mongo_db, make_document, storage):
    async def _seed(doc_id, connector_id=None):
        await make_document(
            doc_id,
            source="CONNECTOR" if connector_id else "MANUAL",
            source_connector_id=connector_id,
            source_ref=f"ref-{doc_id}" if connector_id else None,
        )
        await document_service.add_page(doc_id, 1, "p")
        await document_service.save_ocr_result(doc_id, "x", "text", 0.5, 1, {})
        await document_service.save_extraction_result(doc_id, {}, {})
        await document_service.save_validation_result(doc_id, "VALID", [], [], [], [])
        await document_service.save_final_output(doc_id, {})
        await document_service.log_step(doc_id, "s", "ok")

        (storage / doc_id / "original").mkdir(parents=True)
        (storage / doc_id / "original" / "file.pdf").write_bytes(b"%PDF")
        return doc_id

    return _seed


async def test_deleting_a_document_removes_its_record_and_files(mongo_db, seed, storage):
    await seed("gone")
    await seed("kept")

    assert await document_service.delete_document("gone") == 1

    assert await mongo_db.documents.find_one({"_id": "gone"}) is None
    assert await mongo_db.processing_logs.count_documents({"document_id": "gone"}) == 0

    kept = await mongo_db.documents.find_one({"_id": "kept"})
    for stage in EMBEDDED_STAGES:
        assert stage in kept, stage
    assert await mongo_db.processing_logs.count_documents({"document_id": "kept"}) == 1

    assert not (storage / "gone").exists()
    assert (storage / "kept").exists()


async def test_bulk_delete_counts_only_documents_that_existed(mongo_db, seed):
    for doc_id in ("a", "b", "c"):
        await seed(doc_id)

    assert await document_service.delete_documents(["a", "b", "missing"]) == 2
    assert [d["id"] for d in await document_service.get_all_documents()] == ["c"]
    assert await document_service.delete_documents([]) == 0
    assert await document_service.delete_document("missing") == 0


async def test_a_deleted_mailbox_document_can_be_ingested_again(mongo_db, seed):
    await mongo_db.connector_sync_items.insert_one({
        "_id": "item", "run_id": "run", "connection_id": "conn",
        "external_message_id": "msg", "part_index": 0,
        "document_id": "mail", "status": "INGESTED",
    })
    await seed("mail", connector_id="conn")
    assert await connector_service.is_already_ingested("conn", "ref-mail")

    await document_service.delete_document("mail")

    assert await connector_service.is_already_ingested("conn", "ref-mail") is None
    item = await mongo_db.connector_sync_items.find_one({"_id": "item"})
    assert item["document_id"] is None
