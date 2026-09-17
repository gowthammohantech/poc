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


_INV_RESPONSE = {
    "invoice": {
        "document_type": "INV",
        "invoice_number": "INV-204417",
        "invoice_date": "2026-09-02",
        "po_number": "33336",
        "vendor": {"name": "PIOLAX"},
        "bill_to": {"name": "M.Y. AUTO TECH MFG. OF AMERICA"},
        "line_items": [
            {"line_number": 1, "part_number": "9159410A 3000", "quantity": 17500,
             "unit_price": 0.1621, "amount": 2836.75},
        ],
        "totals": {"subtotal": 2836.75, "freight": 150.0, "sales_tax": None,
                   "total": 2986.75, "balance_due": 2986.75},
        "notes": [],
    },
    "confidence": {"overall": 0.93},
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

    async def test_an_invoice_goes_to_the_invoice_extractor_and_rules(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        from app.services import document_service as docs
        await _seed(database)

        async def _wrong_extractor(payload):
            raise AssertionError("a US invoice must not be read as an order or a release")

        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "INV", "confidence": 0.96}))
        mp.setattr(us_client, "call_us_so_vision_agent", _wrong_extractor)
        mp.setattr(us_client, "call_us_sa_vision_agent", _wrong_extractor)
        mp.setattr(us_client, "call_us_inv_vision_agent",
                   lambda payload: _async(dict(_INV_RESPONSE)))

        result = await processing_service.run_processing_pipeline("doc-1")

        assert result["doc_type"] == "INV"
        assert result["status"] == "VALID"
        assert (await _document(database))["doc_type"] == "INV"

        extraction = await docs.get_extraction_result("doc-1")
        assert extraction["invoice_json"]["invoice"]["invoice_number"] == "INV-204417"
        rules = {c["rule"] for c in extraction["invoice_json"]["validation"]["rule_checks"]}
        assert "inv_totals_math_check" in rules
        assert not any(r.startswith("so_") for r in rules)

    async def test_an_invoice_that_does_not_add_up_is_invalid(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        broken = {"invoice": dict(_INV_RESPONSE["invoice"],
                                  totals={"subtotal": 2836.75, "total": 9999.0})}
        mp.setattr(us_client, "call_us_doc_classifier",
                   lambda payload: _async({"document_type": "INV", "confidence": 0.96}))
        mp.setattr(us_client, "call_us_inv_vision_agent", lambda payload: _async(broken))

        result = await processing_service.run_processing_pipeline("doc-1")
        assert result["status"] == "INVALID"

    async def test_an_india_document_still_takes_the_india_path(self, pipeline):
        """The India router is stubbed to raise, so reaching it fails loudly."""
        processing_service, database, us_client, mp = pipeline
        await _seed(database, country="INDIA")

        with pytest.raises(AssertionError, match="India router"):
            await processing_service.run_processing_pipeline("doc-1")


async def _async(value):
    return value


class TestInvoiceMentionRule:
    """Business rule: "invoice" anywhere in the document makes it an invoice."""

    @pytest.mark.parametrize("text", [
        "INVOICE",
        "This invoice consolidates 3 shipments.",
        "Packing Slip No.  Order Date  Invoice Date",
        "PURCHASE ORDER 33336 ... Send all invoices to ap@piolax.example",
        "SHIPPING AUTHORIZATION W27 W28 STD PACK ... invoiced monthly",
    ])
    def test_any_mention_is_an_invoice(self, text):
        from app.services.us_mastra_client import fallback_document_type, mentions_invoice
        assert mentions_invoice(text)
        assert fallback_document_type(text)["document_type"] == "INV"

    def test_no_mention_leaves_the_decision_to_the_layout(self):
        from app.services.us_mastra_client import fallback_document_type, mentions_invoice
        text = "PURCHASE ORDER  Bill To  Ship Via BEST WAY  UNIT COST  EXT'D COST"
        assert not mentions_invoice(text)
        assert fallback_document_type(text)["document_type"] == "SO"

    async def test_the_classifier_agent_is_not_asked_when_the_text_says_invoice(self, monkeypatch):
        from app.services import us_mastra_client

        async def _never(*args, **kwargs):
            raise AssertionError("the agent must not overrule an invoice mention")

        monkeypatch.setattr(us_mastra_client, "_call_agent", _never)
        result = await us_mastra_client.call_us_doc_classifier({
            "document_id": "d", "page_image_paths": [],
            "ocr_text": "PURCHASE ORDER 4500139581\nInvoice Number 74983441",
        })
        assert result["document_type"] == "INV"

    async def test_the_agent_still_decides_when_the_text_does_not(self, monkeypatch):
        from app.services import us_mastra_client

        async def _agent(agent, content, timeout=None):
            return {"document_type": "SO", "confidence": 0.9, "reason": "order form"}

        monkeypatch.setattr(us_mastra_client, "_call_agent", _agent)
        result = await us_mastra_client.call_us_doc_classifier({
            "document_id": "d", "page_image_paths": [], "ocr_text": "PURCHASE ORDER 33336",
        })
        assert result["document_type"] == "SO"

    async def test_the_pipeline_reads_a_mentioned_invoice_with_the_invoice_extractor(self, pipeline):
        processing_service, database, us_client, mp = pipeline
        await _seed(database)

        def _ocr(engine, paths):
            text = "PURCHASE ORDER No. 4500139581  This invoice consolidates 3 shipments."
            return {"text": text, "confidence": 90.0, "word_count": 8, "metadata": {}}, "TESSERACT"

        async def _never(*args, **kwargs):
            raise AssertionError("classification is decided by the invoice mention")

        mp.setattr(processing_service, "run_ocr_with_fallback", _ocr)
        mp.setattr(us_client, "_call_agent", _never)
        mp.setattr(us_client, "call_us_inv_vision_agent",
                   lambda payload: _async(dict(_INV_RESPONSE)))

        result = await processing_service.run_processing_pipeline("doc-1")
        assert result["doc_type"] == "INV"


class TestKeywordFallback:
    """Used only when the classifier agent is down; an invoice must not read as an order."""

    def test_invoice_wording_outweighs_the_order_words_an_invoice_also_carries(self):
        from app.services.us_mastra_client import fallback_document_type
        text = """INVOICE  Invoice Number: INV-204417  Invoice Date: 09/02/2026
                  Bill To: M.Y. AUTO TECH  Ship Via: UPS  Customer PO: 33336
                  QTY  UNIT PRICE  EXTENDED  Remit To: PO BOX 930412  Balance Due $2,986.75"""
        assert fallback_document_type(text)["document_type"] == "INV"

    def test_an_invoice_whose_ocr_lost_most_of_its_labels(self):
        """Tesseract on the MSC sample: the header table and remit-to stub came out garbled.

        "Purchase Order No." is the PO the invoice bills against, and must not
        count as order wording.
        """
        from app.services.us_mastra_client import fallback_document_type
        text = """Ashland VA 23005-4870 74983441 4500139581
                  Invoice Number Purchase Order No.
                  Sub-Total: 865.69  Sales Tax: 0.00  Total: $872.69
                  This invoice consolidates 3 shipments.
                  Quantity Ordered | Quantity Shipped | Unit of Measure | Discounted Unit Price
                  Extended Price  Ship Via UPS GROUND
                  Customer Number Invoice Number"""
        assert fallback_document_type(text)["document_type"] == "INV"

    def test_a_purchase_order_that_quotes_its_own_number_is_still_an_order(self):
        from app.services.us_mastra_client import fallback_document_type
        text = """PURCHASE ORDER  Purchase Order No. 33336  Bill To  Ship Via BEST WAY
                  UNIT COST  EXT'D COST"""
        assert fallback_document_type(text)["document_type"] == "SO"

    def test_a_purchase_order_is_still_an_order(self):
        from app.services.us_mastra_client import fallback_document_type
        text = """PURCHASE ORDER  Vendor Code PIOLAX  Bill To  Ship Via BEST WAY
                  PART NUMBER  QUANTITY  UOM  UNIT COST  EXT'D COST  Freight Terms"""
        assert fallback_document_type(text)["document_type"] == "SO"

    def test_a_release_is_still_a_release(self):
        from app.services.us_mastra_client import fallback_document_type
        text = "SHIPPING AUTHORIZATION SUPPLIER CODE 4283 STD PACK Ship date Delivery date W27 W28"
        assert fallback_document_type(text)["document_type"] == "SA"
