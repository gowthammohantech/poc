import unittest

from app.services.brs_tesseract_table_service import extract_brs_from_tesseract_result


def _word(text, x, y, confidence=96):
    return {
        "text": text,
        "x": x,
        "y": y,
        "width": max(8, len(text) * 7),
        "height": 12,
        "confidence": confidence,
    }


def _page(rows):
    boxes = []
    for row_index, row in enumerate(rows):
        y = 20 + row_index * 24
        for text, x, *rest in row:
            confidence = rest[0] if rest else 96
            boxes.append(_word(text, x, y, confidence))
    return {"width": 760, "height": 1000, "boxes": boxes}


def _extract(rows, text="Account Number: 123456\nOpening Balance 1000.00\nClosing Balance 1400.00"):
    ocr_result = {
        "text": text,
        "confidence": 92.0,
        "metadata": {"page_references": [_page(rows)]},
    }
    return extract_brs_from_tesseract_result(ocr_result, "doc-1", 1)


class BrsTesseractTableServiceTests(unittest.TestCase):
    def test_extracts_separate_debit_credit_transaction_columns(self):
        result = _extract([
            [("Date", 10), ("Description", 110), ("Ref", 330), ("Debit", 440), ("Credit", 540), ("Balance", 650)],
            [("2025-01-02", 10), ("UPI", 110), ("Payment", 150), ("UTR123", 330), ("100.00", 440), ("900.00", 650)],
            [("2025-01-03", 10), ("Salary", 110), ("UTR124", 330), ("500.00", 540), ("1400.00", 650)],
        ])

        transactions = result["brs"]["bank_transactions"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0]["date"], "2025-01-02")
        self.assertEqual(transactions[0]["description"], "UPI Payment")
        self.assertEqual(transactions[0]["reference_number"], "UTR123")
        self.assertEqual(transactions[0]["debit"], 100.0)
        self.assertIsNone(transactions[0]["credit"])
        self.assertEqual(transactions[0]["balance"], 900.0)
        self.assertEqual(transactions[1]["credit"], 500.0)
        self.assertEqual(result["metadata"]["processing_mode"], "TESSERACT_TABLE")

    def test_merges_multiline_descriptions_and_skips_total_rows(self):
        result = _extract([
            [("Date", 10), ("Particulars", 110), ("Debit", 440), ("Credit", 540), ("Balance", 650)],
            [("2025-01-02", 10), ("ATM", 110), ("Withdrawal", 150), ("200.00", 440), ("800.00", 650)],
            [("City", 110), ("Center", 150)],
            [("Total", 110), ("200.00", 440)],
        ])

        transactions = result["brs"]["bank_transactions"]

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["description"], "ATM Withdrawal City Center")
        self.assertEqual(transactions[0]["debit"], 200.0)

    def test_extracts_single_signed_amount_column(self):
        result = _extract([
            [("Date", 10), ("Description", 110), ("Amount", 500), ("Balance", 650)],
            [("2025-01-02", 10), ("Card", 110), ("Purchase", 150), ("(100.00)", 500), ("900.00", 650)],
            [("2025-01-03", 10), ("Refund", 110), ("500.00", 500), ("CR", 565), ("1400.00", 650)],
        ])

        transactions = result["brs"]["bank_transactions"]

        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[0]["debit"], 100.0)
        self.assertIsNone(transactions[0]["credit"])
        self.assertEqual(transactions[1]["credit"], 500.0)

    def test_records_low_confidence_row_warnings(self):
        result = _extract([
            [("Date", 10), ("Description", 110), ("Debit", 440), ("Credit", 540), ("Balance", 650)],
            [("2025-01-02", 10, 40), ("UPI", 110, 40), ("Payment", 150, 40), ("100.00", 440, 40), ("900.00", 650, 40)],
        ])

        warnings = result["metadata"]["extraction_warnings"]

        self.assertTrue(any("Low OCR confidence" in warning for warning in warnings))

    def test_reuses_layout_across_pages(self):
        first_page = _page([
            [("Date", 10), ("Description", 110), ("Debit", 440), ("Credit", 540), ("Balance", 650)],
            [("2025-01-02", 10), ("Rent", 110), ("300.00", 440), ("700.00", 650)],
        ])
        second_page = _page([
            [("2025-01-03", 10), ("Deposit", 110), ("200.00", 540), ("900.00", 650)],
        ])
        ocr_result = {
            "text": "",
            "confidence": 92.0,
            "metadata": {"page_references": [first_page, second_page]},
        }

        result = extract_brs_from_tesseract_result(ocr_result, "doc-1", 2)

        transactions = result["brs"]["bank_transactions"]
        self.assertEqual(len(transactions), 2)
        self.assertEqual(transactions[1]["description"], "Deposit")
        self.assertEqual(transactions[1]["credit"], 200.0)


if __name__ == "__main__":
    unittest.main()
