"""Rules for the three US document types, checked against the real samples.

The golden payloads below are taken from the two sample documents, so a change
that breaks extraction of a document we have actually seen fails here.
"""

import pytest

from app.services.us_validation_service import run_inv_rules, run_sa_rules, run_so_rules


def _checks_by_rule(checks):
    return {c.rule: c for c in checks}


# --------------------------------------------------------------------------
# SA — built from SA_EXAMPLE_5.pdf (Hutchinson -> PIOLAX, supplier code 4283)
# --------------------------------------------------------------------------

def _sa_columns(count=4):
    weeks = ["W27", "W28", "W29", "W30", "W31"]
    ship = ["2026-06-22", "2026-06-29", "2026-07-06", "2026-07-13", "2026-07-20"]
    delivery = ["2026-06-29", "2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27"]
    return [
        {"week_label": weeks[i], "ship_date": ship[i], "delivery_date": delivery[i]}
        for i in range(count)
    ]


def _sa(**overrides):
    doc = {
        "document_type": "SA",
        "supplier": {"name": "PIOLAX", "code": "4283", "contact": None},
        "issuer": {"name": "HUTCHINSON AUTOPARTES MEXICO, S.A. DE C.V."},
        "schedule_columns": _sa_columns(4),
        "parts": [
            {"po_number": "P170135", "part_number": "1434080B", "description": "FASTENER",
             "std_pack": 1000, "quantities": [0, 0, 0, 50000]},
            {"po_number": "P006442", "part_number": "481126-22B", "description": "CLAMP",
             "std_pack": 400, "quantities": [0, 0, 0, 12000]},
        ],
        "terms_notes": [],
    }
    doc.update(overrides)
    return {"invoice": doc}


class TestShippingAuthorizationRules:
    def test_the_sample_release_passes_every_rule(self):
        checks = run_sa_rules(_sa())
        failed = [c.rule for c in checks if not c.passed]
        assert failed == []

    def test_a_short_quantity_row_fails_alignment(self):
        """A row of the wrong width shifts every quantity after the gap."""
        payload = _sa(parts=[
            {"po_number": "P170135", "part_number": "1434080B", "std_pack": 1000,
             "quantities": [0, 0, 50000]},  # three quantities, four buckets
        ])
        check = _checks_by_rule(run_sa_rules(payload))["sa_schedule_width_match"]
        assert not check.passed
        assert "row 1 has 3 of 4" in check.message

    def test_a_long_quantity_row_also_fails_alignment(self):
        payload = _sa(parts=[
            {"part_number": "X", "quantities": [0, 0, 0, 0, 0]},
        ])
        assert not _checks_by_rule(run_sa_rules(payload))["sa_schedule_width_match"].passed

    def test_no_parts_is_reported(self):
        checks = _checks_by_rule(run_sa_rules(_sa(parts=[])))
        assert not checks["sa_parts_present"].passed
        assert "sa_schedule_width_match" not in checks, "width is meaningless with no rows"

    def test_no_schedule_columns_is_reported(self):
        checks = _checks_by_rule(run_sa_rules(_sa(schedule_columns=[])))
        assert not checks["sa_schedule_columns_present"].passed

    def test_a_missing_part_number_is_flagged_per_row(self):
        payload = _sa(parts=[
            {"po_number": "P170135", "part_number": None, "quantities": [0, 0, 0, 0]},
        ])
        assert not _checks_by_rule(run_sa_rules(payload))["sa_part_1_part_number"].passed

    def test_negative_quantities_are_rejected(self):
        payload = _sa(parts=[
            {"part_number": "1434080B", "std_pack": 1000, "quantities": [0, -500, 0, 0]},
        ])
        check = _checks_by_rule(run_sa_rules(payload))["sa_quantities_non_negative"]
        assert not check.passed
        assert "1434080B week 2" in check.message

    def test_a_quantity_off_the_standard_pack_is_flagged(self):
        """50500 against a 1000-piece pack is the shape of a misread digit."""
        payload = _sa(parts=[
            {"part_number": "1434080B", "std_pack": 1000, "quantities": [0, 0, 0, 50500]},
        ])
        assert not _checks_by_rule(run_sa_rules(payload))["sa_std_pack_multiple"].passed

    def test_a_part_without_a_standard_pack_is_not_flagged(self):
        payload = _sa(parts=[
            {"part_number": "411205A", "std_pack": None, "quantities": [0, 0, 0, 7]},
        ])
        assert _checks_by_rule(run_sa_rules(payload))["sa_std_pack_multiple"].passed

    def test_out_of_order_delivery_dates_are_flagged(self):
        """A year inferred wrongly at the W52 -> w1 rollover shows up here."""
        columns = _sa_columns(4)
        columns[2]["delivery_date"] = "2025-07-13"
        assert not _checks_by_rule(run_sa_rules(_sa(schedule_columns=columns)))[
            "sa_delivery_dates_ordered"].passed

    def test_unparsed_delivery_dates_do_not_break_the_order_check(self):
        columns = _sa_columns(4)
        columns[1]["delivery_date"] = None
        assert _checks_by_rule(run_sa_rules(_sa(schedule_columns=columns)))[
            "sa_delivery_dates_ordered"].passed

    def test_an_unidentified_supplier_is_flagged(self):
        payload = _sa(supplier={"name": None, "code": None})
        assert not _checks_by_rule(run_sa_rules(payload))["sa_supplier_identified"].passed

    def test_a_supplier_code_alone_identifies_the_supplier(self):
        payload = _sa(supplier={"name": None, "code": "4283"})
        assert _checks_by_rule(run_sa_rules(payload))["sa_supplier_identified"].passed


# --------------------------------------------------------------------------
# SO — built from SO_EXAMPLE_1.pdf (M.Y. Auto Tech PO 33336 to PIOLAX)
# --------------------------------------------------------------------------

def _so(**overrides):
    doc = {
        "document_type": "SO",
        "order_number": "33336",
        "order_date": "2026-08-11",
        "ship_to": {"name": "M.Y. Auto Tech Mfg. of America",
                    "address": "565 BEULAH CHURCH RD, CARROLLTON, GA 30117"},
        "line_items": [
            {"line_number": 1, "part_number": "17550THRAA030Y1",
             "description": "VALVE, COMBINATIONFILL VENT", "quantity": 1780, "uom": "EA",
             "due_date": "2026-12-07", "unit_cost": 6.2985, "extended_cost": 11211.33},
            {"line_number": 2, "part_number": "70182STXA000H1",
             "description": "HOLDER, CONSOLE BRKT", "quantity": 10000, "uom": "EA",
             "due_date": "2026-12-07", "unit_cost": 0.0323, "extended_cost": 323.00},
            {"line_number": 3, "part_number": "9159410A 3000",
             "description": "CLIP PROTECTOR MT", "quantity": 17500, "uom": "EA",
             "due_date": "2026-12-07", "unit_cost": 0.1621, "extended_cost": 2836.75},
        ],
        "totals": {"subtotal": None, "sales_tax": None, "freight": None,
                   "discount": None, "grand_total": None},
    }
    doc.update(overrides)
    return {"invoice": doc}


class TestPurchaseOrderRules:
    def test_the_sample_order_passes_every_rule(self):
        failed = [c.rule for c in run_so_rules(_so()) if not c.passed]
        assert failed == []

    def test_line_arithmetic_is_checked_to_four_decimal_places(self):
        """1,780 x $6.2985 is $11,211.33 -- rounding unit cost to 2dp would not be."""
        checks = _checks_by_rule(run_so_rules(_so()))
        assert checks["so_line_1_extended_cost"].passed

    def test_a_wrong_extended_cost_is_caught(self):
        payload = _so(line_items=[
            {"quantity": 1780, "unit_cost": 6.2985, "extended_cost": 1121.33},
        ])
        check = _checks_by_rule(run_so_rules(payload))["so_line_1_extended_cost"]
        assert not check.passed
        assert "11211.33" in check.message

    def test_a_rounded_unit_cost_stays_within_tolerance(self):
        """Some vendors print the unit cost rounded; that is not an error."""
        payload = _so(line_items=[
            {"quantity": 10000, "unit_cost": 0.0323, "extended_cost": 323.15},
        ])
        assert _checks_by_rule(run_so_rules(payload))["so_line_1_extended_cost"].passed

    def test_no_totals_block_means_no_totals_check(self):
        """The sample purchase order prints no totals at all."""
        assert "so_totals_math_check" not in _checks_by_rule(run_so_rules(_so()))

    def test_a_grand_total_that_does_not_add_up_is_caught(self):
        payload = _so(totals={"subtotal": 14371.08, "sales_tax": 0, "freight": 0,
                              "discount": 0, "grand_total": 99999.00})
        assert not _checks_by_rule(run_so_rules(payload))["so_totals_math_check"].passed

    def test_a_grand_total_falls_back_to_the_line_sum(self):
        payload = _so(totals={"subtotal": None, "grand_total": 14371.08})
        assert _checks_by_rule(run_so_rules(payload))["so_totals_math_check"].passed

    @pytest.mark.parametrize("order_date", [None, "08/11/2026", "2026-13-45", "not a date"])
    def test_a_bad_order_date_is_rejected(self, order_date):
        assert not _checks_by_rule(run_so_rules(_so(order_date=order_date)))[
            "so_order_date_valid"].passed

    def test_a_missing_po_number_is_rejected(self):
        assert not _checks_by_rule(run_so_rules(_so(order_number=None)))[
            "so_order_number_present"].passed

    def test_no_line_items_is_rejected(self):
        assert not _checks_by_rule(run_so_rules(_so(line_items=[])))["so_line_items_present"].passed

    def test_a_zero_quantity_line_is_rejected(self):
        payload = _so(line_items=[{"quantity": 0, "unit_cost": 1.0, "extended_cost": 0.0}])
        assert not _checks_by_rule(run_so_rules(payload))["so_line_1_quantity"].passed

    def test_a_missing_ship_to_is_flagged(self):
        assert not _checks_by_rule(run_so_rules(_so(ship_to={})))["so_ship_to_present"].passed

    def test_no_gst_rule_ever_runs_on_a_us_document(self):
        rules = " ".join(
            c.rule for c in run_so_rules(_so()) + run_sa_rules(_sa()) + run_inv_rules(_inv()))
        for india_only in ("gstin", "hsn", "cgst", "sgst", "igst", "ifsc", "pan"):
            assert india_only not in rules


class TestRepairDoesNotHideMisalignment:
    """us_mastra_client pads a ragged row so the grid renders; the rule must still fail."""

    def test_a_padded_row_still_fails_the_width_check(self):
        payload = _sa(parts=[{
            "part_number": "1434080B",
            "quantities": [0, 0, 0, None],
            "quantities_repaired": "padded from 3 to 4",
        }])
        check = _checks_by_rule(run_sa_rules(payload))["sa_schedule_width_match"]
        assert not check.passed
        assert "padded from 3 to 4" in check.message

    def test_a_trimmed_row_still_fails_the_width_check(self):
        payload = _sa(parts=[{
            "part_number": "1434080B",
            "quantities": [0, 0, 0, 0],
            "quantities_repaired": "trimmed from 6 to 4",
        }])
        assert not _checks_by_rule(run_sa_rules(payload))["sa_schedule_width_match"].passed


# --------------------------------------------------------------------------
# INV — a supplier invoice billing the M.Y. Auto Tech purchase order
# --------------------------------------------------------------------------

def _inv(**overrides):
    doc = {
        "document_type": "INV",
        "invoice_number": "INV-204417",
        "invoice_date": "2026-09-02",
        "due_date": "2026-11-01",
        "po_number": "33336",
        "order_number": "SO-88120",
        "customer_number": "MYAUTO01",
        "payment_terms": "NET 60",
        "currency": "USD",
        "vendor": {"name": "PIOLAX", "address": "139 ETOWAH INDUSTRIAL COURT, CANTON, GA 30114",
                   "tax_id": "58-1234567"},
        "remit_to": {"name": "PIOLAX", "address": "PO BOX 930412, ATLANTA, GA 31193"},
        "bill_to": {"name": "M.Y. AUTO TECH MFG. OF AMERICA",
                    "address": "565 Beulah Church Rd, CARROLLTON, GA 30117"},
        "ship_to": {"address": "565 BEULAH CHURCH RD, CARROLLTON, GA 30117"},
        "line_items": [
            {"line_number": 1, "part_number": "17550THRAA030Y1", "quantity": 1780,
             "unit_price": 6.2985, "amount": 11211.33},
            {"line_number": 2, "part_number": "9159410A 3000", "quantity": 17500,
             "unit_price": 0.1621, "amount": 2836.75},
        ],
        "totals": {"subtotal": 14048.08, "discount": None, "freight": 150.00,
                   "tax_rate": None, "sales_tax": 0.0, "total": 14198.08,
                   "amount_paid": None, "balance_due": 14198.08},
        "notes": [],
    }
    doc.update(overrides)
    return {"invoice": doc}


def _inv_totals(**overrides):
    totals = dict(_inv()["invoice"]["totals"])
    totals.update(overrides)
    return totals


class TestInvoiceRules:
    def test_the_golden_invoice_passes_every_rule(self):
        failed = [c.message for c in run_inv_rules(_inv()) if not c.passed]
        assert failed == []

    def test_the_rules_it_runs(self):
        rules = set(_checks_by_rule(run_inv_rules(_inv())))
        assert {
            "inv_invoice_number_present", "inv_invoice_number_distinct", "inv_invoice_date_valid",
            "inv_due_date_valid", "inv_due_date_after_invoice_date", "inv_vendor_identified",
            "inv_bill_to_present", "inv_line_items_present", "inv_line_1_amount",
            "inv_total_present", "inv_subtotal_matches_lines", "inv_totals_math_check",
            "inv_balance_due_check",
        } <= rules

    def test_a_missing_invoice_number_is_rejected(self):
        assert not _checks_by_rule(run_inv_rules(_inv(invoice_number=None)))[
            "inv_invoice_number_present"].passed

    def test_the_po_number_read_as_the_invoice_number_is_flagged(self):
        check = _checks_by_rule(run_inv_rules(_inv(invoice_number="33336")))[
            "inv_invoice_number_distinct"]
        assert not check.passed
        assert "PO number" in check.message

    def test_a_missing_invoice_date_is_rejected(self):
        assert not _checks_by_rule(run_inv_rules(_inv(invoice_date=None)))[
            "inv_invoice_date_valid"].passed

    def test_a_day_first_date_is_rejected(self):
        assert not _checks_by_rule(run_inv_rules(_inv(invoice_date="02/09/2026")))[
            "inv_invoice_date_valid"].passed

    def test_a_missing_due_date_is_not_a_failure(self):
        """NET 60 with no printed due date is normal; the prompt must not invent one."""
        checks = _checks_by_rule(run_inv_rules(_inv(due_date=None)))
        assert "inv_due_date_valid" not in checks
        assert "inv_due_date_after_invoice_date" not in checks

    def test_a_due_date_before_the_invoice_date_is_flagged(self):
        assert not _checks_by_rule(run_inv_rules(_inv(due_date="2026-02-09")))[
            "inv_due_date_after_invoice_date"].passed

    def test_a_line_that_does_not_multiply_out_is_flagged(self):
        lines = [{"quantity": 1780, "unit_price": 6.2985, "amount": 1121.13}]
        assert not _checks_by_rule(run_inv_rules(_inv(line_items=lines)))[
            "inv_line_1_amount"].passed

    def test_a_lump_sum_line_skips_the_arithmetic(self):
        lines = [{"description": "TOOLING CHARGE", "quantity": None, "unit_price": None,
                  "amount": 500.0}]
        checks = _checks_by_rule(run_inv_rules(_inv(
            line_items=lines, totals=_inv_totals(subtotal=500.0, total=650.0, balance_due=650.0))))
        assert "inv_line_1_amount" not in checks
        assert checks["inv_totals_math_check"].passed

    def test_a_missing_total_is_rejected(self):
        """Unlike a purchase order, an invoice exists to say what is owed."""
        check = _checks_by_rule(run_inv_rules(_inv(
            totals=_inv_totals(total=None, balance_due=None))))["inv_total_present"]
        assert not check.passed

    def test_a_balance_due_alone_counts_as_a_total(self):
        assert _checks_by_rule(run_inv_rules(_inv(totals=_inv_totals(total=None))))[
            "inv_total_present"].passed

    def test_totals_that_do_not_reconcile_are_rejected(self):
        check = _checks_by_rule(run_inv_rules(_inv(totals=_inv_totals(total=15198.08))))[
            "inv_totals_math_check"]
        assert not check.passed
        assert "14198.08" in check.message

    def test_sales_tax_and_discount_are_part_of_the_total(self):
        totals = _inv_totals(discount=48.08, freight=None, tax_rate=7.0, sales_tax=980.0,
                             total=14980.0, balance_due=14980.0)
        assert _checks_by_rule(run_inv_rules(_inv(totals=totals)))["inv_totals_math_check"].passed

    def test_a_discount_printed_as_a_credit_is_still_subtracted(self):
        totals = _inv_totals(discount=-48.08, freight=None, total=14000.0, balance_due=14000.0)
        assert _checks_by_rule(run_inv_rules(_inv(totals=totals)))["inv_totals_math_check"].passed

    def test_a_subtotal_that_disagrees_with_its_lines_is_flagged(self):
        assert not _checks_by_rule(run_inv_rules(_inv(totals=_inv_totals(subtotal=14000.0))))[
            "inv_subtotal_matches_lines"].passed

    def test_a_partial_payment_must_leave_the_right_balance(self):
        checks = _checks_by_rule(run_inv_rules(_inv(
            totals=_inv_totals(amount_paid=5000.0, balance_due=9198.08))))
        assert checks["inv_balance_due_check"].passed

        checks = _checks_by_rule(run_inv_rules(_inv(
            totals=_inv_totals(amount_paid=5000.0, balance_due=14198.08))))
        assert not checks["inv_balance_due_check"].passed

    def test_no_sales_tax_is_not_a_failure(self):
        totals = _inv_totals(sales_tax=None, tax_rate=None)
        failed = [c.rule for c in run_inv_rules(_inv(totals=totals)) if not c.passed]
        assert failed == []
