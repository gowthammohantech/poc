"""Rules for the two US document types, checked against the real samples.

The golden payloads below are taken from the two sample documents, so a change
that breaks extraction of a document we have actually seen fails here.
"""

import pytest

from app.services.us_validation_service import run_sa_rules, run_so_rules


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
        rules = " ".join(c.rule for c in run_so_rules(_so()) + run_sa_rules(_sa()))
        for india_only in ("gstin", "hsn", "cgst", "sgst", "igst", "ifsc", "pan"):
            assert india_only not in rules
