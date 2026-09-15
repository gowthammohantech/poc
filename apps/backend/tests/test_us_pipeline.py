"""The US branch, driven end to end with the Mastra calls stubbed out.

This is where the wiring is checked: that a USA document skips the router,
persists its classified type, lands the payload under the envelope key the
review route reads, and comes back with a status from the US rules rather than
the India ones.
"""

import importlib
import tempfile
from pathlib import Path

import aiosqlite
import pytest


@pytest.fixture
async def pipeline(monkeypatch):
    """The pipeline module against a throwaway database, Mastra stubbed."""
    tmp = Path(tempfile.mkdtemp(prefix="us-pipeline-test-")) / "test.db"
    monkeypatch.setenv("DB_PATH", str(tmp))

    from app.db import database
    importlib.reload(database)

    from app.services import document_service, processing_service, us_mastra_client
    importlib.reload(document_service)
    importlib.reload(processing_service)
    await database.init_db()

    # Local OCR is a reference signal here, not a dependency.
    def _no_ocr(engine, paths):
        return {"text": "", "confidence": 0.0, "word_count": 0, "metadata": {}}, "TESSERACT"

    monkeypatch.setattr(processing_service, "run_ocr_with_fallback", _no_ocr)

    async def _unexpected(*args, **kwargs):
        raise AssertionError("the India router must never run for a USA document")

    monkeypatch.setattr(processing_service.mastra_client, "call_ocr_router", _unexpected)

    async def _validation(payload):
        return {"llm_checks": [], "warnings": [], "confidence_adjustments": {}}

    monkeypatch.setattr(us_mastra_client, "call_us_validation_agent", _validation)

    yield processing_service, database, us_mastra_client, monkeypatch

    monkeypatch.delenv("DB_PATH", raising=False)
    importlib.reload(database)
    importlib.reload(document_service)
    importlib.reload(processing_service)


async def _seed(database, country="USA", doc_type=None):
    async with aiosqlite.connect(database.DB_PATH) as db:
        await db.execute(
            "INSERT INTO documents (id, filename, status, country, doc_type, page_count) "
            "VALUES ('doc-1', 'sample.pdf', 'COMPLEXITY_ANALYZED', ?, ?, 1)",
            (country, doc_type),
        )
        await db.execute(
            "INSERT INTO document_pages (id, document_id, page_number, original_path, "
            "preprocessed_path) VALUES ('p1', 'doc-1', 1, '/tmp/orig.png', '/tmp/prep.png')"
        )
        await db.commit()


async def _document(database, document_id="doc-1"):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        return await cursor.fetchone()


_SA_RESPONSE = {
    "invoice": {
        "document_type": "SA",
        "release_date": "2026-08-03",
        "supplier": {"name": "PIOLAX", "code": "4283"},
        "issuer": {"name": "HUTCHINSON AUTOPARTES MEXICO, S.A. DE C.V."},
        "schedule_columns": [
            {"week_label": "W27", "raw_ship_date": "22-Jun", "raw_delivery_date": "29-Jun"},
            {"week_label": "W28", "raw_ship_date": "29-Jun", "raw_delivery_date": "6-Jul"},
        ],
        "parts": [
            {"po_number": "P170135", "part_number": "1434080B", "description": "FASTENER",
             "std_pack": 1000, "quantities": [0, 50000]},
        ],
        "terms_notes": [],
    },
    "confidence": {"overall": 0.91},
}


class TestUsPipeline:
    async def test_a_shipping_authorization_runs_end_to_end(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        async def _classify(payload):
            return {"document_type": "SA", "confidence": 0.95, "reason": "week grid"}

        async def _extract(payload):
            return dict(_SA_RESPONSE)

        mp.setattr(us_client, "call_us_doc_classifier", _classify)
        mp.setattr(us_client, "call_us_sa_vision_agent", _extract)

        result = await processing_service.run_processing_pipeline("doc-1")

        assert result["doc_type"] == "SA"
        assert result["status"] == "VALID"
        assert result["ocr_engine"] == "OPENAI_VISION_LLM", "US documents always use vision"

    async def test_the_classified_type_is_persisted_on_the_document(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        async def _classify(payload):
            return {"document_type": "SA", "confidence": 0.95, "reason": "week grid"}

        mp.setattr(us_client, "call_us_doc_classifier", _classify)
        mp.setattr(us_client, "call_us_sa_vision_agent",
                   lambda payload: _async(dict(_SA_RESPONSE)))

        await processing_service.run_processing_pipeline("doc-1")

        row = await _document(database)
        assert row["doc_type"] == "SA"
        assert row["country"] == "USA"
        assert row["status"] == "VALID"

    async def test_a_type_already_set_is_respected(self, pipeline):
        """A reviewer who corrects the type and re-processes is not overruled."""
        processing_service, database, us_client, mp = pipeline
        await _seed(database, doc_type="SA")

        async def _never(payload):
            raise AssertionError("classification must be skipped when the type is known")

        mp.setattr(us_client, "call_us_doc_classifier", _never)
        mp.setattr(us_client, "call_us_sa_vision_agent",
                   lambda payload: _async(dict(_SA_RESPONSE)))

        result = await processing_service.run_processing_pipeline("doc-1")
        assert result["doc_type"] == "SA"

    async def test_the_payload_lands_where_the_review_route_reads_it(self, pipeline):
        """review_routes reads invoice_json["invoice"]; a miss renders a blank form."""
        processing_service, database, us_client, mp = pipeline
        from app.services import document_service as docs
        await _seed(database)

        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "SA", "confidence": 1.0}))
        # An agent that answers with a different top-level key must still work.
        mp.setattr(us_client, "call_us_sa_vision_agent",
                   lambda payload: _async({"us_document": dict(_SA_RESPONSE["invoice"])}))

        await processing_service.run_processing_pipeline("doc-1")

        extraction = await docs.get_extraction_result("doc-1")
        document = extraction["invoice_json"]["invoice"]
        assert document["supplier"]["code"] == "4283"
        assert document["document_type"] == "SA"

    async def test_schedule_dates_are_derived_during_the_run(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        from app.services import document_service as docs
        await _seed(database)

        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "SA", "confidence": 1.0}))
        mp.setattr(us_client, "call_us_sa_vision_agent",
                   lambda payload: _async(dict(_SA_RESPONSE)))

        await processing_service.run_processing_pipeline("doc-1")

        extraction = await docs.get_extraction_result("doc-1")
        columns = extraction["invoice_json"]["invoice"]["schedule_columns"]
        assert columns[0]["ship_date"] == "2026-06-22"
        assert columns[0]["delivery_date"] == "2026-06-29"

    async def test_a_misaligned_release_is_invalid(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        broken = {"invoice": dict(_SA_RESPONSE["invoice"],
                                  parts=[{"part_number": "X", "quantities": [0]}])}
        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "SA", "confidence": 1.0}))
        mp.setattr(us_client, "call_us_sa_vision_agent", lambda payload: _async(broken))

        result = await processing_service.run_processing_pipeline("doc-1")
        assert result["status"] == "INVALID"

    async def test_an_unclassified_document_is_never_invalid(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "UNKNOWN", "confidence": 0.0}))
        mp.setattr(us_client, "call_us_so_vision_agent", lambda payload: _async({}))

        result = await processing_service.run_processing_pipeline("doc-1")

        assert result["doc_type"] == "UNKNOWN"
        assert result["status"] == "NEEDS_REVIEW", (
            "we do not know what the document is, so we do not assert it is wrong"
        )

    async def test_an_india_document_still_takes_the_india_path(self, pipeline):
        """The India router is stubbed to raise, so reaching it fails loudly."""
        processing_service, database, us_client, mp = pipeline
        await _seed(database, country="INDIA")

        with pytest.raises(AssertionError, match="India router"):
            await processing_service.run_processing_pipeline("doc-1")


async def _async(value):
    return value
