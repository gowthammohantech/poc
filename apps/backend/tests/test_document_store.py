"""The guarantees the document store itself has to provide.

Replaces the tests for the old boot-time DDL runner. A schemaless store gives
nothing for free, so the three things the pipeline used to get from the schema —
a full field set on every record, one document per mailbox attachment, and a
country that is always one of the two regimes — are asserted here.
"""

import uuid

import pytest
from pymongo.errors import DuplicateKeyError, WriteError

from app.db import mongo
from app.schemas.document_schema import DocumentCreate
from app.services import document_service


class TestIndexes:
    """ensure_indexes runs on every boot, exactly as the .sql files used to."""

    async def test_is_idempotent(self, mongo_db):
        await mongo.ensure_indexes()
        await mongo.ensure_indexes()

        names = (await mongo_db.documents.index_information()).keys()
        assert "ux_documents_source_ref" in names

    async def test_the_attachment_guard_is_a_partial_unique_index(self, mongo_db):
        """The filter has to exclude nulls without excluding real values.

        `$exists: True` would match an explicit null and collapse every manual
        upload onto a single key, and partial filters do not accept `$ne`.
        """
        index = (await mongo_db.documents.index_information())["ux_documents_source_ref"]

        assert index["unique"] is True
        assert index["key"] == [("source_connector_id", 1), ("source_ref", 1)]
        assert index["partialFilterExpression"] == {"source_ref": {"$type": "string"}}


class TestOneDocumentPerAttachment:
    """The backstop that stops one attachment becoming two documents."""

    async def test_the_same_attachment_cannot_be_ingested_twice(self, mongo_db, make_document):
        await make_document(source="CONNECTOR", source_connector_id="conn-1",
                            source_ref="msg-1:0:invoice.pdf")

        with pytest.raises(DuplicateKeyError):
            await make_document(source="CONNECTOR", source_connector_id="conn-1",
                                source_ref="msg-1:0:invoice.pdf")

    async def test_the_same_reference_from_another_mailbox_is_allowed(self, mongo_db, make_document):
        await make_document(source="CONNECTOR", source_connector_id="conn-1", source_ref="msg-1:0")
        await make_document(source="CONNECTOR", source_connector_id="conn-2", source_ref="msg-1:0")

        assert await mongo_db.documents.count_documents({}) == 2

    async def test_manual_uploads_do_not_collide(self, mongo_db, make_document):
        """They all have no source_ref, so the index must ignore them."""
        for name in ("a", "b", "c"):
            await make_document(name)

        assert await mongo_db.documents.count_documents({}) == 3

    async def test_a_missing_source_ref_is_ignored_too(self, mongo_db):
        """Not just an explicit null: absent must not count as a value either."""
        for name in ("a", "b"):
            await mongo_db.documents.insert_one({
                "_id": name, "filename": f"{name}.pdf", "status": "VALID",
                "country": "INDIA", "source": "MANUAL",
            })

        assert await mongo_db.documents.count_documents({}) == 2


class TestDocumentShape:
    """`SELECT *` always returned every column; absent keys are not the same.

    Readers index into these dicts directly, so create_document writes the full
    shape rather than leaving each one to coalesce nulls.
    """

    async def test_a_new_document_carries_every_field(self, mongo_db):
        doc_id = await document_service.create_document(
            DocumentCreate(filename="invoice.pdf", original_path="/tmp/invoice.pdf")
        )
        document = await document_service.get_document(doc_id)

        assert document["country"] == "INDIA"
        assert document["doc_type"] is None
        assert document["source"] == "MANUAL"
        assert document["page_count"] == 0
        assert document["must_use_llm"] == 0
        assert document["document_number"] is None
        for field in ("complexity_score", "complexity_level", "complexity_reasons",
                      "ocr_engine", "processing_mode", "source_connector_id",
                      "source_ref", "source_metadata"):
            assert field in document, field

    async def test_the_chosen_country_is_kept(self, mongo_db):
        doc_id = await document_service.create_document(
            DocumentCreate(filename="po.pdf", original_path="/tmp/po.pdf", country="USA")
        )

        assert (await document_service.get_document(doc_id))["country"] == "USA"

    async def test_reads_do_not_carry_the_embedded_stage_results(self, mongo_db):
        """The list endpoint would otherwise ship every document's OCR text."""
        doc_id = await document_service.create_document(
            DocumentCreate(filename="invoice.pdf", original_path="/tmp/invoice.pdf")
        )
        await document_service.save_ocr_result(doc_id, "TESSERACT", "x" * 10_000, 0.9, 2, {})

        document = await document_service.get_document(doc_id)

        assert "ocr" not in document
        assert "pages" not in document
        # ...but it is still there to be asked for.
        assert (await document_service.get_ocr_result(doc_id))["raw_text"] == "x" * 10_000


class TestValidator:
    """What replaces the NOT NULL constraints the tables carried."""

    async def test_a_document_without_a_filename_is_refused(self, mongo_db):
        with pytest.raises(WriteError):
            await mongo_db.documents.insert_one({
                "_id": str(uuid.uuid4()), "status": "VALID",
                "country": "INDIA", "source": "MANUAL",
            })

    async def test_a_country_outside_the_two_regimes_is_refused(self, mongo_db):
        """Neither pipeline would run for a value outside them."""
        with pytest.raises(WriteError):
            await mongo_db.documents.insert_one({
                "_id": str(uuid.uuid4()), "filename": "x.pdf", "status": "VALID",
                "country": "CANADA", "source": "MANUAL",
            })
