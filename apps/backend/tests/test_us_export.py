"""US export builders, checked on payloads shaped like the real samples.

The one that matters most is the release matrix: it is the only export in the
app whose width varies per document, so a ragged row would silently misalign
every quantity a reader sees.
"""

import csv
import io

import pytest

from app.services.us_export_service import (
    build_inv_export_csv,
    build_inv_export_excel,
    build_sa_export_csv,
    build_sa_export_excel,
    build_so_export_csv,
    build_so_export_excel,
    build_us_export_csv,
    build_us_export_excel,
    build_us_export_json,
    export_basename,
)


def _final(document: dict) -> dict:
    return {"corrected_json": {"invoice": document, "metadata": {}}}


def _sa_document(parts=None, columns=None) -> dict:
    return {
        "document_type": "SA",
        "release_number": "REL-7781",
        "release_date": "2026-08-03",
        "received_by": "CHIGDON",
        "received_at": "2026-08-03T08:20",
        "issuer": {"name": "HUTCHINSON AUTOPARTES MEXICO, S.A. DE C.V.",
                   "address": "CELAYA, GTO. MEXICO 38110",
                   "phone": "+52 (461) 1920100", "contact": "Pamela Hoffman"},
        "supplier": {"name": "PIOLAX", "code": "4283", "address": None, "contact": None},
        "schedule_columns": columns if columns is not None else [
            {"week_label": "W27", "raw_delivery_date": "29-Jun", "delivery_date": "2026-06-29"},
            {"week_label": "W28", "raw_delivery_date": "6-Jul", "delivery_date": "2026-07-06"},
            {"week_label": "W29", "raw_delivery_date": "13-Jul", "delivery_date": "2026-07-13"},
        ],
        "parts": parts if parts is not None else [
            {"po_number": "P170135", "part_number": "1434080B", "description": "FASTENER",
             "std_pack": 1000, "quantities": [0, 50000, 0]},
            {"po_number": "P006442", "part_number": "481126-22B", "description": "CLAMP",
             "std_pack": 400, "quantities": [0, 12000, 0]},
        ],
        "terms_notes": ["ALL SUPPLIERS MUST SEND US THE SHIPMENT DOCUMENTS VIA E-MAIL"],
    }


def _so_document() -> dict:
    return {
        "document_type": "SO",
        "order_number": "33336",
        "order_date": "2026-08-11",
        "currency": "USD",
        "payment_terms": "NET 60",
        "freight_terms": None,
        "ship_via": "BEST WAY",
        "received_by": "CHIGDON",
        "received_at": "2026-08-12T08:35",
        "vendor": {"name": "PIOLAX", "code": "PIOLAX",
                   "address": "139 ETOWAH INDUSTRIAL COURT, CANTON, GA 30114",
                   "contact": "Tera Myers", "phone": None},
        "buyer": {"name": "M.Y. AUTO TECH MFG. OF AMERICA", "address": None, "contact": None},
        "bill_to": {"name": None, "address": "565 Beulah Church Rd, CARROLLTON, GA 30117",
                    "contact": "Andrea Williams", "phone": "770-853-7787"},
        "ship_to": {"name": None, "address": "565 BEULAH CHURCH RD, CARROLLTON, GA 30117",
                    "contact": None, "phone": "678-390-6300"},
        "line_items": [
            {"line_number": 1, "part_number": "17550THRAA030Y1",
             "description": "VALVE, COMBINATIONFILL VENT", "quantity": 1780, "uom": "EA",
             "due_date": "2026-12-07", "unit_cost": 6.2985, "extended_cost": 11211.33},
            {"line_number": 2, "part_number": "9159410A 3000",
             "description": "CLIP PROTECTOR MT", "quantity": 17500, "uom": "EA",
             "due_date": "2026-12-07", "unit_cost": 0.1621, "extended_cost": 2836.75},
        ],
        "totals": {"subtotal": None, "sales_tax": None, "freight": None,
                   "discount": None, "grand_total": None},
        "notes": [],
    }


def _inv_document() -> dict:
    return {
        "document_type": "INV",
        "invoice_number": "INV-204417",
        "invoice_date": "2026-09-02",
        "due_date": "2026-11-01",
        "po_number": "33336",
        "order_number": "SO-88120",
        "customer_number": "000417",
        "bol_number": None,
        "payment_terms": "NET 60",
        "currency": "USD",
        "vendor": {"name": "PIOLAX", "address": "139 ETOWAH INDUSTRIAL COURT, CANTON, GA 30114",
                   "tax_id": "58-1234567", "email": "ar@piolax.example"},
        "remit_to": {"name": "PIOLAX", "address": "PO BOX 930412, ATLANTA, GA 31193"},
        "bill_to": {"name": "M.Y. AUTO TECH MFG. OF AMERICA", "address": None},
        "ship_to": {"name": None, "address": "565 BEULAH CHURCH RD, CARROLLTON, GA 30117"},
        "line_items": [
            {"line_number": 1, "part_number": "9159410A 3000", "description": "CLIP PROTECTOR MT",
             "quantity_ordered": 20000, "quantity": 17500, "uom": "EA",
             "unit_price": 0.1621, "amount": 2836.75},
        ],
        "totals": {"subtotal": 2836.75, "discount": None, "freight": 150.0, "tax_rate": None,
                   "sales_tax": None, "total": 2986.75, "amount_paid": None,
                   "balance_due": 2986.75},
        "notes": ["ACH: routing 061000104"],
    }


def _schedule_rows(csv_text: str) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(csv_text)))
    start = next(i for i, row in enumerate(rows) if row and row[0] == "Delivery Schedule")
    block = []
    for row in rows[start + 1:]:
        if not row or not any(cell.strip() for cell in row):
            break
        block.append(row)
    return block


class TestShippingAuthorizationCsv:
    def test_every_schedule_row_is_the_width_of_the_header(self):
        """A ragged matrix puts quantities under the wrong week."""
        rows = _schedule_rows(build_sa_export_csv(_final(_sa_document())))
        header = rows[0]
        assert len(header) == 4 + 3 + 1, "four identity columns, three weeks, a total"
        for row in rows[1:]:
            assert len(row) == len(header)

    def test_a_short_quantity_row_is_padded_to_the_header(self):
        document = _sa_document(parts=[
            {"po_number": "P1", "part_number": "X", "std_pack": 100, "quantities": [5000]},
        ])
        rows = _schedule_rows(build_sa_export_csv(_final(document)))
        assert len(rows[1]) == len(rows[0])

    def test_a_long_quantity_row_is_trimmed_to_the_header(self):
        document = _sa_document(parts=[
            {"po_number": "P1", "part_number": "X", "std_pack": 100,
             "quantities": [1, 2, 3, 4, 5, 6]},
        ])
        rows = _schedule_rows(build_sa_export_csv(_final(document)))
        assert len(rows[1]) == len(rows[0])

    def test_bucket_columns_are_labelled_by_week_and_printed_date(self):
        rows = _schedule_rows(build_sa_export_csv(_final(_sa_document())))
        assert rows[0][4:7] == ["W27 29-Jun", "W28 6-Jul", "W29 13-Jul"]

    def test_each_row_carries_its_released_total(self):
        rows = _schedule_rows(build_sa_export_csv(_final(_sa_document())))
        assert rows[1][-1] == "50000"
        assert rows[2][-1] == "12000"

    def test_the_supplier_code_survives_the_export(self):
        text = build_sa_export_csv(_final(_sa_document()))
        assert "Supplier Code,4283" in text

    def test_nulls_export_as_blanks_not_the_word_none(self):
        document = _sa_document(parts=[
            {"po_number": None, "part_number": "X", "description": None,
             "std_pack": None, "quantities": [0, None, 0]},
        ])
        assert "None" not in build_sa_export_csv(_final(document))

    def test_a_release_with_no_schedule_still_exports(self):
        text = build_sa_export_csv(_final(_sa_document(parts=[], columns=[])))
        assert "Shipping Authorization" in text


class TestPurchaseOrderCsv:
    def test_the_line_columns_are_the_us_ones(self):
        text = build_so_export_csv(_final(_so_document()))
        assert "Unit Cost" in text and "Ext'd Cost" in text

    def test_no_gst_column_leaks_in_from_the_india_builder(self):
        text = build_so_export_csv(_final(_so_document())).upper()
        for india_only in ("GSTIN", "CGST", "SGST", "IGST", "HSN", "IFSC"):
            assert india_only not in text

    def test_unit_costs_keep_their_four_decimal_places(self):
        assert "6.2985" in build_so_export_csv(_final(_so_document()))

    def test_a_part_number_with_a_space_stays_one_cell(self):
        rows = list(csv.reader(io.StringIO(build_so_export_csv(_final(_so_document())))))
        assert any("9159410A 3000" in row for row in rows)

    def test_absent_totals_export_as_blanks(self):
        text = build_so_export_csv(_final(_so_document()))
        assert "Grand Total," in text
        assert "None" not in text


class TestInvoiceCsv:
    def test_the_invoice_header_carries_every_reference(self):
        rows = list(csv.reader(io.StringIO(build_inv_export_csv(_final(_inv_document())))))
        header = {row[0]: row[1] for row in rows if len(row) == 2}
        assert header["Invoice Number"] == "INV-204417"
        assert header["PO Number"] == "33336"
        assert header["Due Date"] == "2026-11-01"
        # Leading zeros are the whole of some customer numbers.
        assert header["Customer Number"] == "000417"

    def test_the_remit_to_and_tax_id_survive(self):
        text = build_inv_export_csv(_final(_inv_document()))
        assert "Remit To Address,\"PO BOX 930412, ATLANTA, GA 31193\"" in text
        assert "Vendor Tax ID,58-1234567" in text

    def test_the_line_columns_are_the_invoice_ones(self):
        rows = list(csv.reader(io.StringIO(build_inv_export_csv(_final(_inv_document())))))
        start = next(i for i, row in enumerate(rows) if row and row[0] == "Line Items")
        assert rows[start + 1] == ["Line #", "Part Number", "Description", "Qty Ordered",
                                   "Qty Invoiced", "UOM", "Unit Price", "Amount"]
        assert rows[start + 2][4] == "17500"
        assert rows[start + 2][6] == "0.1621"

    def test_what_is_owed_is_exported(self):
        text = build_inv_export_csv(_final(_inv_document()))
        assert "Total,2986.75" in text
        assert "Balance Due,2986.75" in text

    def test_no_gst_column_leaks_in_and_nulls_are_blank(self):
        text = build_inv_export_csv(_final(_inv_document()))
        for india_only in ("GSTIN", "CGST", "SGST", "IGST", "HSN", "IFSC"):
            assert india_only not in text.upper()
        assert "None" not in text


class TestExcel:
    def test_the_invoice_workbook(self):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(build_inv_export_excel(_final(_inv_document()))))

        assert wb.sheetnames == ["Invoice Header", "Line Items", "Notes"]
        assert wb["Line Items"].cell(row=1, column=8).value == "Amount"
        assert wb["Line Items"].cell(row=2, column=7).value == 0.1621
        labels = {row[0].value: row[1].value for row in wb["Invoice Header"].iter_rows()}
        assert labels["Invoice Number"] == "INV-204417"
        assert labels["Balance Due"] == 2986.75

    def test_the_release_workbook_freezes_the_identity_columns(self):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(build_sa_export_excel(_final(_sa_document()))))

        assert wb.sheetnames == ["Release Info", "Delivery Schedule", "Terms"]
        # Without this, scrolling to a later week loses which part a row is.
        assert wb["Delivery Schedule"].freeze_panes == "E2"

    def test_the_release_matrix_has_a_cell_per_bucket(self):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(build_sa_export_excel(_final(_sa_document()))))
        ws = wb["Delivery Schedule"]

        assert ws.max_column == 4 + 3 + 1
        assert ws.cell(row=1, column=5).value == "W27 29-Jun"
        assert ws.cell(row=2, column=6).value == 50000

    def test_the_order_workbook_has_a_line_items_sheet(self):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(build_so_export_excel(_final(_so_document()))))

        assert wb.sheetnames == ["Order Header", "Line Items"]
        assert wb["Line Items"].cell(row=2, column=7).value == 6.2985


class TestDispatch:
    @pytest.mark.parametrize("doc_type,expected", [
        ("SA", "release"), ("sa", "release"), ("SO", "order"), ("INV", "invoice"),
        ("inv", "invoice"), ("UNKNOWN", "order"), (None, "order"),
    ])
    def test_the_download_is_named_after_the_document(self, doc_type, expected):
        assert export_basename(doc_type) == expected

    def test_csv_dispatch_follows_the_document_type(self):
        assert "Delivery Schedule" in build_us_export_csv(_final(_sa_document()), "SA")
        assert "Purchase Order" in build_us_export_csv(_final(_so_document()), "SO")
        assert "Remit To Address" in build_us_export_csv(_final(_inv_document()), "INV")

    def test_excel_dispatch_follows_the_document_type(self):
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.load_workbook(
            io.BytesIO(build_us_export_excel(_final(_so_document()), "SO")))
        assert "Line Items" in wb.sheetnames

    def test_the_json_export_says_what_it_is(self):
        """The India builder ignores its document argument; this one uses it."""
        exported = build_us_export_json(
            _final(_sa_document()), {"country": "USA", "doc_type": "SA"})
        assert exported["country"] == "USA"
        assert exported["document_type"] == "SA"
        assert exported["invoice"]["supplier"]["code"] == "4283"


class TestDocTypeResolution:
    """The reviewed payload knows better than the classifier's stored guess."""

    def test_the_payload_type_wins_over_an_unknown_row(self):
        from app.services.us_export_service import resolve_doc_type
        assert resolve_doc_type(_final(_sa_document()), {"doc_type": "UNKNOWN"}) == "SA"

    def test_the_payload_type_wins_over_a_wrong_row(self):
        from app.services.us_export_service import resolve_doc_type
        assert resolve_doc_type(_final(_sa_document()), {"doc_type": "SO"}) == "SA"

    def test_the_row_is_used_when_the_payload_says_nothing(self):
        from app.services.us_export_service import resolve_doc_type
        document = _sa_document()
        document.pop("document_type")
        assert resolve_doc_type(_final(document), {"doc_type": "SA"}) == "SA"

    def test_a_reviewed_invoice_exports_as_an_invoice(self):
        from app.services.us_export_service import resolve_doc_type
        final = _final(_inv_document())
        assert resolve_doc_type(final, {"doc_type": "SO"}) == "INV"
        assert "Invoice Number" in build_us_export_csv(final, resolve_doc_type(final, {}))

    def test_a_junk_payload_type_falls_back_to_the_row(self):
        from app.services.us_export_service import resolve_doc_type
        document = dict(_sa_document(), document_type="INVOICE")
        assert resolve_doc_type(_final(document), {"doc_type": "SA"}) == "SA"

    def test_a_reviewed_release_exports_as_a_release(self):
        from app.services.us_export_service import build_us_export_csv, resolve_doc_type
        final, row = _final(_sa_document()), {"country": "USA", "doc_type": "UNKNOWN"}
        assert "Delivery Schedule" in build_us_export_csv(final, resolve_doc_type(final, row))
