import unittest
from importlib.util import find_spec
from unittest.mock import AsyncMock, Mock, patch

if find_spec("fastapi"):
    from app.api import brs_document_routes
else:
    brs_document_routes = None


def _sample_brs_json():
    return {
        "document_id": "doc-1",
        "brs": {
            "document_info": {
                "company_name": "Acme",
                "bank_name": "Example Bank",
                "account_number": "123456",
                "statement_period_start": "2025-01-01",
                "statement_period_end": "2025-01-31",
                "currency": "INR",
                "prepared_by": None,
                "prepared_date": None,
            },
            "balances": {
                "opening_balance_bank": None,
                "opening_balance_book": None,
                "closing_balance_bank": None,
                "closing_balance_book": None,
                "reconciled_balance": None,
            },
            "bank_side_items": [],
            "book_side_items": [],
            "bank_transactions": [
                {
                    "date": "2025-01-02",
                    "description": "UPI Payment",
                    "reference_number": "UTR123",
                    "debit": 100.0,
                    "credit": None,
                    "balance": 900.0,
                }
            ],
            "adjusted_bank_balance": None,
            "adjusted_book_balance": None,
        },
        "confidence": {"overall": 0.9},
        "metadata": {
            "processing_mode": "TESSERACT_TABLE",
            "ocr_confidence": 90.0,
            "pages": 1,
            "transaction_count": 1,
            "extraction_warnings": [],
        },
    }


class BrsDocumentRoutesTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipIf(brs_document_routes is None, "FastAPI is not installed in this Python environment")
    async def test_process_uses_tesseract_table_path_without_vision_agent(self):
        brs_json = _sample_brs_json()
        ocr_result = {"text": "", "confidence": 90.0, "word_count": 5, "metadata": {"page_references": []}}

        with (
            patch.object(brs_document_routes.docs, "get_document", AsyncMock(return_value={"id": "doc-1"})),
            patch.object(
                brs_document_routes.docs,
                "get_pages",
                AsyncMock(return_value=[{"preprocessed_path": "page.png", "original_path": "page.png"}]),
            ),
            patch.object(brs_document_routes.docs, "update_document_status", AsyncMock()),
            patch.object(brs_document_routes.docs, "log_step", AsyncMock()),
            patch.object(brs_document_routes.docs, "save_extraction_result", AsyncMock()),
            patch.object(brs_document_routes.docs, "save_validation_result", AsyncMock()),
            patch.object(brs_document_routes.docs, "get_extraction_result", AsyncMock(return_value={"brs_json": brs_json})),
            patch.object(brs_document_routes.docs, "save_match_result", AsyncMock()),
            patch.object(brs_document_routes.ledger_service, "get_all_entries", AsyncMock(return_value=[])),
            patch.object(brs_document_routes, "run_tesseract", Mock(return_value=ocr_result)) as run_tesseract,
            patch.object(
                brs_document_routes,
                "extract_brs_from_tesseract_result",
                Mock(return_value=brs_json),
            ) as extract_table,
        ):
            result = await brs_document_routes.process_brs_document("doc-1", processing_mode="TESSERACT_TABLE")

        run_tesseract.assert_called_once_with(["page.png"])
        extract_table.assert_called_once_with(ocr_result, "doc-1", 1)
        self.assertEqual(result["processing_mode"], "TESSERACT_TABLE")

    @unittest.skipIf(brs_document_routes is None, "FastAPI is not installed in this Python environment")
    async def test_process_uses_hybrid_ocr_vision_agent(self):
        brs_json = _sample_brs_json()
        brs_json["metadata"]["processing_mode"] = "HYBRID_OCR_VISION"
        ocr_result = {"text": "some ocr text", "confidence": 90.0, "word_count": 5, "metadata": {"page_references": []}}

        with (
            patch.object(brs_document_routes.docs, "get_document", AsyncMock(return_value={"id": "doc-1"})),
            patch.object(
                brs_document_routes.docs,
                "get_pages",
                AsyncMock(return_value=[{"preprocessed_path": "page.png", "original_path": "page.png"}]),
            ),
            patch.object(brs_document_routes.docs, "update_document_status", AsyncMock()),
            patch.object(brs_document_routes.docs, "log_step", AsyncMock()),
            patch.object(brs_document_routes.docs, "save_extraction_result", AsyncMock()),
            patch.object(brs_document_routes.docs, "save_validation_result", AsyncMock()),
            patch.object(brs_document_routes.docs, "get_extraction_result", AsyncMock(return_value={"brs_json": brs_json})),
            patch.object(brs_document_routes.docs, "save_match_result", AsyncMock()),
            patch.object(brs_document_routes.ledger_service, "get_all_entries", AsyncMock(return_value=[])),
            patch.object(brs_document_routes, "run_tesseract", Mock(return_value=ocr_result)) as run_tesseract,
            patch.object(
                brs_document_routes,
                "call_brs_direct_vision_agent",
                AsyncMock(return_value=brs_json),
            ) as run_vision,
        ):
            result = await brs_document_routes.process_brs_document("doc-1", processing_mode="HYBRID_OCR_VISION")

        run_tesseract.assert_called_once_with(["page.png"])
        run_vision.assert_called_once_with({
            "page_image_paths": ["page.png"],
            "document_id": "doc-1",
            "ocr_text": "some ocr text",
        })
        self.assertEqual(result["processing_mode"], "HYBRID_OCR_VISION")


if __name__ == "__main__":
    unittest.main()
