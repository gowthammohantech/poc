"""Deleting documents from the list removes everything they produced.

A deleted document leaves no rows, no files on disk, and no trace that would
stop a mailbox sync from ingesting its attachment again.
"""

import importlib
import tempfile
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
async def service(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="document-delete-test-"))
    monkeypatch.setenv("DB_PATH", str(tmp / "test.db"))

    from app.db import database
    importlib.reload(database)
    from app.services import connector_service, document_service
    importlib.reload(document_service)
    importlib.reload(connector_service)
    storage = tmp / "uploads"
    monkeypatch.setattr(document_service, "STORAGE_BASE", storage)
    await database.init_db()
    yield database, document_service, connector_service, storage

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)
    importlib.reload(document_service)
    importlib.reload(connector_service)


CHILD_TABLES = (
    "document_pages", "ocr_results", "extraction_results",
    "validation_results", "final_outputs", "processing_logs",
)


async def _seed(database, storage, doc_id, connector_id=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            """INSERT INTO documents (id, filename, status, source_connector_id, source_ref)
               VALUES (?, ?, 'VALID', ?, ?)""",
            (doc_id, f"{doc_id}.pdf", connector_id, f"ref-{doc_id}" if connector_id else None),
        )
        await db.execute(
            "INSERT INTO document_pages (id, document_id, page_number, original_path) VALUES (?, ?, 1, 'p')",
            (f"p-{doc_id}", doc_id),
        )
        await db.execute(
            "INSERT INTO ocr_results (id, document_id, engine) VALUES (?, ?, 'x')",
            (f"o-{doc_id}", doc_id),
        )
        await db.execute(
            "INSERT INTO extraction_results (id, document_id, invoice_json) VALUES (?, ?, '{}')",
            (f"e-{doc_id}", doc_id),
        )
        await db.execute(
            "INSERT INTO validation_results (id, document_id, status) VALUES (?, ?, 'VALID')",
            (f"v-{doc_id}", doc_id),
        )
        await db.execute(
            "INSERT INTO final_outputs (id, document_id, corrected_json) VALUES (?, ?, '{}')",
            (f"f-{doc_id}", doc_id),
        )
        await db.execute(
            "INSERT INTO processing_logs (id, document_id, step, status) VALUES (?, ?, 's', 'ok')",
            (f"l-{doc_id}", doc_id),
        )
        await db.commit()
    (storage / doc_id / "original").mkdir(parents=True)
    (storage / doc_id / "original" / "file.pdf").write_bytes(b"%PDF")


async def _count(database, table, column, doc_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        cursor = await db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (doc_id,))
        return (await cursor.fetchone())[0]


async def test_deleting_a_document_removes_its_rows_and_files(service):
    database, document_service, _, storage = service
    await _seed(database, storage, "gone")
    await _seed(database, storage, "kept")

    assert await document_service.delete_document("gone") == 1

    assert await _count(database, "documents", "id", "gone") == 0
    for table in CHILD_TABLES:
        assert await _count(database, table, "document_id", "gone") == 0, table
        assert await _count(database, table, "document_id", "kept") == 1, table
    assert not (storage / "gone").exists()
    assert (storage / "kept").exists()


async def test_bulk_delete_counts_only_documents_that_existed(service):
    database, document_service, _, storage = service
    for doc_id in ("a", "b", "c"):
        await _seed(database, storage, doc_id)

    assert await document_service.delete_documents(["a", "b", "missing"]) == 2
    assert [d["id"] for d in await document_service.get_all_documents()] == ["c"]
    assert await document_service.delete_documents([]) == 0
    assert await document_service.delete_document("missing") == 0


async def test_a_deleted_mailbox_document_can_be_ingested_again(service):
    database, document_service, connector_service, storage = service
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys=OFF")
        await db.execute(
            """INSERT INTO connector_sync_items
               (id, run_id, connection_id, external_message_id, part_index, document_id, status)
               VALUES ('item', 'run', 'conn', 'msg', 0, 'mail', 'INGESTED')"""
        )
        await db.commit()
    await _seed(database, storage, "mail", connector_id="conn")
    assert await connector_service.is_already_ingested("conn", "ref-mail")

    await document_service.delete_document("mail")

    assert await connector_service.is_already_ingested("conn", "ref-mail") is None
    async with aiosqlite.connect(database.DB_PATH) as db:
        cursor = await db.execute("SELECT document_id FROM connector_sync_items WHERE id = 'item'")
        assert (await cursor.fetchone())[0] is None
