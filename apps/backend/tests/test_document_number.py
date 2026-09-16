"""The documents list shows the number each document is known by.

India invoices carry an invoice number, US purchase orders an order number and
US shipping authorizations a release number; the list reads whichever the
payload has, preferring what a reviewer submitted over what extraction read.
"""

import importlib
import json
import tempfile
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
async def service(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="document-number-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))

    from app.db import database
    importlib.reload(database)
    from app.services import document_service
    importlib.reload(document_service)
    await database.init_db()
    yield database, document_service

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)
    importlib.reload(document_service)


async def _seed(database, doc_id, extracted=None, corrected=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "INSERT INTO documents (id, filename, status) VALUES (?, ?, 'VALID')",
            (doc_id, f"{doc_id}.pdf"),
        )
        if extracted is not None:
            await db.execute(
                "INSERT INTO extraction_results (id, document_id, invoice_json) VALUES (?, ?, ?)",
                (f"e-{doc_id}", doc_id, json.dumps({"invoice": extracted})),
            )
        if corrected is not None:
            await db.execute(
                "INSERT INTO final_outputs (id, document_id, corrected_json) VALUES (?, ?, ?)",
                (f"f-{doc_id}", doc_id, json.dumps({"invoice": corrected})),
            )
        await db.commit()


async def _numbers(document_service):
    return {d["id"]: d["document_number"] for d in await document_service.get_all_documents()}


async def test_each_document_family_shows_its_own_number(service):
    database, document_service = service
    await _seed(database, "india", extracted={"invoice_number": "INV-001"})
    await _seed(database, "so", extracted={"document_type": "SO", "order_number": "PO-42"})
    await _seed(database, "sa", extracted={"document_type": "SA", "release_number": "R-7"})

    assert await _numbers(document_service) == {"india": "INV-001", "so": "PO-42", "sa": "R-7"}


async def test_a_reviewed_number_wins_over_the_extracted_one(service):
    database, document_service = service
    await _seed(database, "doc", extracted={"invoice_number": "1NV-00l"},
                corrected={"invoice_number": "INV-001"})

    assert (await _numbers(document_service))["doc"] == "INV-001"


async def test_no_extraction_or_a_blank_number_is_null(service):
    database, document_service = service
    await _seed(database, "unprocessed")
    await _seed(database, "blank", extracted={"invoice_number": "  "})

    assert await _numbers(document_service) == {"unprocessed": None, "blank": None}
