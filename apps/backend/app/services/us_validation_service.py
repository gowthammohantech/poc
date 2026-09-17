"""Deterministic rules for the three US document types.

The India rules check a GST tax invoice: GSTINs, CGST/SGST/IGST consistency, a
grand total that adds up. No US document carries GST -- not even the US
invoice -- so none of that applies and this is a separate rule set rather than
a country flag threaded through validation_service.

  * SA — a shipping authorization: a parts x week-bucket demand schedule. There
    are no prices, so the arithmetic that matters is structural: every part's
    quantity row has to line up with the schedule header.
  * SO — a purchase order: per-line quantity x unit cost = extended cost. The
    sample carries no totals row at all, so the totals check only fires when a
    grand total is actually present.
  * INV — a supplier invoice: per-line quantity x unit price = amount, and a
    totals block that has to reconcile, because the total is the figure that
    gets paid. Sales tax is a single optional line; many invoices carry none.

As with the India rules, the LLM reads and these rules decide.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from app.schemas.validation_schema import RuleCheck
from app.services.validation_service import DATE_PATTERN, MATH_TOLERANCE

# Unit costs are printed to four decimal places ($6.2985), but some vendors
# round them on the page. An absolute 0.05 is unforgiving on a five-figure
# line, so allow 0.1% of the line as a floor.
_RELATIVE_TOLERANCE = 0.001


def _line_tolerance(expected: float) -> float:
    return max(MATH_TOLERANCE, abs(expected) * _RELATIVE_TOLERANCE)


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_iso_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# SA — shipping authorization
# --------------------------------------------------------------------------

def run_sa_rules(payload: Dict[str, Any]) -> List[RuleCheck]:
    doc = payload.get("invoice", {}) or {}
    checks: List[RuleCheck] = []

    checks.extend(_validate_sa_supplier(doc))
    checks.extend(_validate_sa_schedule_columns(doc))
    checks.extend(_validate_sa_parts(doc))

    return checks


def _validate_sa_supplier(doc: dict) -> List[RuleCheck]:
    supplier = doc.get("supplier") or {}
    identified = bool(supplier.get("name") or supplier.get("code"))
    return [RuleCheck(
        rule="sa_supplier_identified",
        passed=identified,
        message=(
            f"Supplier identified as {supplier.get('name') or supplier.get('code')}"
            if identified else
            "Neither a supplier name nor a supplier code was found"
        ),
        field="supplier.name",
    )]


def _validate_sa_schedule_columns(doc: dict) -> List[RuleCheck]:
    columns = doc.get("schedule_columns") or []
    checks = [RuleCheck(
        rule="sa_schedule_columns_present",
        passed=len(columns) > 0,
        message=(
            f"{len(columns)} weekly bucket(s) found"
            if columns else "No weekly schedule columns were extracted"
        ),
        field="schedule_columns",
    )]

    if not columns:
        return checks

    # Buckets run left to right in calendar order. An out-of-order date means
    # columns were transposed or a year was inferred wrongly at the W52 -> w1
    # rollover, which would silently misdate every quantity in the row.
    delivery_dates = [_parse_iso_date((c or {}).get("delivery_date")) for c in columns]
    known = [d for d in delivery_dates if d is not None]
    ordered = all(earlier < later for earlier, later in zip(known, known[1:]))
    checks.append(RuleCheck(
        rule="sa_delivery_dates_ordered",
        passed=ordered,
        message=(
            "Delivery dates increase left to right" if ordered else
            "Delivery dates are not in ascending order across the schedule"
        ),
        field="schedule_columns",
    ))
    return checks


def _validate_sa_parts(doc: dict) -> List[RuleCheck]:
    parts = doc.get("parts") or []
    column_count = len(doc.get("schedule_columns") or [])

    checks = [RuleCheck(
        rule="sa_parts_present",
        passed=len(parts) > 0,
        message=f"{len(parts)} part row(s) found" if parts else "No part rows were extracted",
        field="parts",
    )]

    if not parts:
        return checks

    # The quantities array is positional: index i is the quantity for
    # schedule_columns[i]. A row of the wrong width means every quantity after
    # the gap is attributed to the wrong week, so this is fatal, not cosmetic.
    #
    # us_mastra_client pads or trims a ragged row so the review grid can render
    # it, and leaves a quantities_repaired note behind when it does. That note
    # counts as a mismatch here: repairing the shape must not hide the fact
    # that the model lost track of the columns.
    mismatched = []
    for i, part in enumerate(parts):
        repaired = part.get("quantities_repaired")
        if repaired:
            mismatched.append(f"row {i + 1} was {repaired}")
        elif len(part.get("quantities") or []) != column_count:
            mismatched.append(
                f"row {i + 1} has {len(part.get('quantities') or [])} of {column_count}")

    checks.append(RuleCheck(
        rule="sa_schedule_width_match",
        passed=not mismatched,
        message=(
            f"All {len(parts)} part row(s) span {column_count} bucket(s)"
            if not mismatched else
            "Part row(s) do not line up with the schedule header: " + ", ".join(mismatched)
        ),
        field="parts",
    ))

    negative = []
    for i, part in enumerate(parts):
        label = part.get("part_number") or f"row {i + 1}"
        checks.append(RuleCheck(
            rule=f"sa_part_{i + 1}_part_number",
            passed=bool(part.get("part_number")),
            message=(
                f"Part number {part.get('part_number')}"
                if part.get("part_number") else f"Row {i + 1} has no part number"
            ),
            field=f"parts.{i}.part_number",
        ))
        for j, raw in enumerate(part.get("quantities") or []):
            quantity = _as_number(raw)
            if quantity is not None and quantity < 0:
                negative.append(f"{label} week {j + 1}")

    checks.append(RuleCheck(
        rule="sa_quantities_non_negative",
        passed=not negative,
        message=(
            "All scheduled quantities are zero or positive" if not negative else
            "Negative quantities found at: " + ", ".join(negative)
        ),
        field="parts",
    ))

    # A release that asks for a part in anything other than whole standard
    # packs is usually a misread digit, but it is legitimate often enough that
    # it stays a warning.
    off_pack = []
    for i, part in enumerate(parts):
        std_pack = _as_number(part.get("std_pack"))
        if not std_pack:
            continue
        for j, raw in enumerate(part.get("quantities") or []):
            quantity = _as_number(raw)
            if quantity and quantity % std_pack != 0:
                off_pack.append(f"{part.get('part_number') or f'row {i + 1}'} week {j + 1}")

    checks.append(RuleCheck(
        rule="sa_std_pack_multiple",
        passed=not off_pack,
        message=(
            "Scheduled quantities are whole standard packs" if not off_pack else
            "Quantities are not a multiple of the standard pack at: " + ", ".join(off_pack)
        ),
        field="parts",
    ))
    return checks


# --------------------------------------------------------------------------
# SO — purchase order
# --------------------------------------------------------------------------

def run_so_rules(payload: Dict[str, Any]) -> List[RuleCheck]:
    doc = payload.get("invoice", {}) or {}
    checks: List[RuleCheck] = []

    checks.extend(_validate_so_header(doc))
    checks.extend(_validate_so_line_items(doc))
    checks.extend(_validate_so_totals(doc))

    return checks


def _validate_so_header(doc: dict) -> List[RuleCheck]:
    order_number = doc.get("order_number")
    order_date = doc.get("order_date")
    ship_to = doc.get("ship_to") or {}

    checks = [RuleCheck(
        rule="so_order_number_present",
        passed=bool(order_number),
        message=(
            f"PO number {order_number}" if order_number else "No PO number was found"
        ),
        field="order_number",
    )]

    parsed = _parse_iso_date(order_date)
    if order_date is None:
        checks.append(RuleCheck(
            rule="so_order_date_valid",
            passed=False,
            message="No order date was found",
            field="order_date",
        ))
    else:
        checks.append(RuleCheck(
            rule="so_order_date_valid",
            passed=parsed is not None,
            message=(
                f"Order date {order_date}" if parsed else
                f"Order date '{order_date}' is not a valid YYYY-MM-DD date"
            ),
            field="order_date",
        ))

    has_ship_to = bool(ship_to.get("name") or ship_to.get("address"))
    checks.append(RuleCheck(
        rule="so_ship_to_present",
        passed=has_ship_to,
        message="Ship-to address present" if has_ship_to else "No ship-to address was found",
        field="ship_to.address",
    ))
    return checks


def _validate_so_line_items(doc: dict) -> List[RuleCheck]:
    items = doc.get("line_items") or []
    checks = [RuleCheck(
        rule="so_line_items_present",
        passed=len(items) > 0,
        message=f"{len(items)} line item(s) found" if items else "No line items were extracted",
        field="line_items",
    )]

    for i, item in enumerate(items):
        quantity = _as_number(item.get("quantity"))
        checks.append(RuleCheck(
            rule=f"so_line_{i + 1}_quantity",
            passed=quantity is not None and quantity > 0,
            message=(
                f"Line {i + 1} quantity {quantity}" if quantity and quantity > 0 else
                f"Line {i + 1} has no positive quantity"
            ),
            field=f"line_items.{i}.quantity",
        ))

        unit_cost = _as_number(item.get("unit_cost"))
        extended = _as_number(item.get("extended_cost"))
        if quantity is None or unit_cost is None or extended is None:
            continue
        expected = quantity * unit_cost
        within = abs(expected - extended) <= _line_tolerance(expected)
        checks.append(RuleCheck(
            rule=f"so_line_{i + 1}_extended_cost",
            passed=within,
            message=(
                f"Line {i + 1}: {quantity} x {unit_cost} = {extended}" if within else
                f"Line {i + 1}: {quantity} x {unit_cost} = {round(expected, 2)}, "
                f"but the extended cost reads {extended}"
            ),
            field=f"line_items.{i}.extended_cost",
        ))
    return checks


def _validate_so_totals(doc: dict) -> List[RuleCheck]:
    totals = doc.get("totals") or {}
    grand_total = _as_number(totals.get("grand_total"))
    # The sample purchase order prints no totals block at all. Reporting a
    # failure for a total the document never carried would be noise, so the
    # check only runs when there is a figure to check.
    if grand_total is None:
        return []

    items = doc.get("line_items") or []
    line_sum = sum(
        _as_number(item.get("extended_cost")) or 0.0
        for item in items
    )
    subtotal = _as_number(totals.get("subtotal"))
    if subtotal is None:
        subtotal = line_sum

    expected = (
        subtotal
        + (_as_number(totals.get("sales_tax")) or 0.0)
        + (_as_number(totals.get("freight")) or 0.0)
        - (_as_number(totals.get("discount")) or 0.0)
    )
    within = abs(expected - grand_total) <= _line_tolerance(expected)
    return [RuleCheck(
        rule="so_totals_math_check",
        passed=within,
        message=(
            f"Totals add up to {grand_total}" if within else
            f"Subtotal plus tax and freight less discount is {round(expected, 2)}, "
            f"but the grand total reads {grand_total}"
        ),
        field="totals.grand_total",
    )]


# --------------------------------------------------------------------------
# INV — invoice
# --------------------------------------------------------------------------

def run_inv_rules(payload: Dict[str, Any]) -> List[RuleCheck]:
    doc = payload.get("invoice", {}) or {}
    checks: List[RuleCheck] = []

    checks.extend(_validate_inv_header(doc))
    checks.extend(_validate_inv_line_items(doc))
    checks.extend(_validate_inv_totals(doc))

    return checks


def _date_check(field: str, label: str, value: Any, required: bool) -> Optional[RuleCheck]:
    rule = f"inv_{field}_valid"
    if value is None:
        if not required:
            return None
        return RuleCheck(rule=rule, passed=False, message=f"No {label.lower()} was found", field=field)
    parsed = _parse_iso_date(value)
    return RuleCheck(
        rule=rule,
        passed=parsed is not None,
        message=(
            f"{label} {value}" if parsed else
            f"{label} '{value}' is not a valid YYYY-MM-DD date"
        ),
        field=field,
    )


def _validate_inv_header(doc: dict) -> List[RuleCheck]:
    invoice_number = doc.get("invoice_number")
    checks = [RuleCheck(
        rule="inv_invoice_number_present",
        passed=bool(invoice_number),
        message=(
            f"Invoice number {invoice_number}" if invoice_number else "No invoice number was found"
        ),
        field="invoice_number",
    )]

    # The model's commonest identifier mistake: putting the PO it bills
    # against in the invoice number. Paying against a PO number as if it were
    # an invoice number is how duplicate payments slip through.
    if invoice_number:
        clashes = [
            label for key, label in (("po_number", "PO number"),
                                     ("order_number", "order number"),
                                     ("customer_number", "customer number"))
            if doc.get(key) and str(doc.get(key)).strip() == str(invoice_number).strip()
        ]
        checks.append(RuleCheck(
            rule="inv_invoice_number_distinct",
            passed=not clashes,
            message=(
                "Invoice number is distinct from the other references" if not clashes else
                f"Invoice number {invoice_number} is the same as the {', '.join(clashes)}"
            ),
            field="invoice_number",
        ))

    for check in (
        _date_check("invoice_date", "Invoice date", doc.get("invoice_date"), required=True),
        _date_check("due_date", "Due date", doc.get("due_date"), required=False),
    ):
        if check is not None:
            checks.append(check)

    invoice_date = _parse_iso_date(doc.get("invoice_date"))
    due_date = _parse_iso_date(doc.get("due_date"))
    if invoice_date and due_date:
        in_order = due_date >= invoice_date
        checks.append(RuleCheck(
            rule="inv_due_date_after_invoice_date",
            passed=in_order,
            message=(
                f"Due {due_date.isoformat()}, {(due_date - invoice_date).days} day(s) after the invoice date"
                if in_order else
                f"Due date {due_date.isoformat()} is before the invoice date "
                f"{invoice_date.isoformat()}; one was probably read day-first"
            ),
            field="due_date",
        ))

    vendor = doc.get("vendor") or {}
    identified = bool(vendor.get("name"))
    checks.append(RuleCheck(
        rule="inv_vendor_identified",
        passed=identified,
        message=(
            f"Invoiced by {vendor.get('name')}" if identified else
            "The vendor who issued the invoice was not identified"
        ),
        field="vendor.name",
    ))

    bill_to = doc.get("bill_to") or {}
    has_bill_to = bool(bill_to.get("name") or bill_to.get("address"))
    checks.append(RuleCheck(
        rule="inv_bill_to_present",
        passed=has_bill_to,
        message="Bill-to present" if has_bill_to else "No bill-to customer was found",
        field="bill_to.name",
    ))
    return checks


def _validate_inv_line_items(doc: dict) -> List[RuleCheck]:
    items = doc.get("line_items") or []
    checks = [RuleCheck(
        rule="inv_line_items_present",
        passed=len(items) > 0,
        message=f"{len(items)} line item(s) found" if items else "No line items were extracted",
        field="line_items",
    )]

    for i, item in enumerate(items):
        quantity = _as_number(item.get("quantity"))
        unit_price = _as_number(item.get("unit_price"))
        amount = _as_number(item.get("amount"))
        # A lump-sum service or freight line legitimately prints only an
        # amount, so the arithmetic runs only when all three are present.
        if quantity is None or unit_price is None or amount is None:
            continue
        expected = quantity * unit_price
        within = abs(expected - amount) <= _line_tolerance(expected)
        checks.append(RuleCheck(
            rule=f"inv_line_{i + 1}_amount",
            passed=within,
            message=(
                f"Line {i + 1}: {quantity} x {unit_price} = {amount}" if within else
                f"Line {i + 1}: {quantity} x {unit_price} = {round(expected, 2)}, "
                f"but the amount reads {amount}"
            ),
            field=f"line_items.{i}.amount",
        ))
    return checks


def _validate_inv_totals(doc: dict) -> List[RuleCheck]:
    totals = doc.get("totals") or {}
    items = doc.get("line_items") or []
    total = _as_number(totals.get("total"))
    balance_due = _as_number(totals.get("balance_due"))

    # Unlike a purchase order, an invoice exists to state what is owed, so a
    # missing figure is a failure rather than something to skip.
    checks = [RuleCheck(
        rule="inv_total_present",
        passed=total is not None or balance_due is not None,
        message=(
            f"Invoice total {total if total is not None else balance_due}"
            if total is not None or balance_due is not None else
            "No invoice total or balance due was found"
        ),
        field="totals.total",
    )]

    line_amounts = [_as_number(item.get("amount")) for item in items]
    subtotal = _as_number(totals.get("subtotal"))
    if subtotal is not None and line_amounts and all(a is not None for a in line_amounts):
        line_sum = sum(line_amounts)
        within = abs(line_sum - subtotal) <= _line_tolerance(subtotal)
        checks.append(RuleCheck(
            rule="inv_subtotal_matches_lines",
            passed=within,
            message=(
                f"Line amounts add up to the subtotal {subtotal}" if within else
                f"Line amounts add up to {round(line_sum, 2)}, but the subtotal reads {subtotal}"
            ),
            field="totals.subtotal",
        ))

    if total is not None:
        base = subtotal
        if base is None and line_amounts and all(a is not None for a in line_amounts):
            base = sum(line_amounts)
        if base is not None:
            expected = (
                base
                - abs(_as_number(totals.get("discount")) or 0.0)
                + (_as_number(totals.get("freight")) or 0.0)
                + (_as_number(totals.get("sales_tax")) or 0.0)
            )
            within = abs(expected - total) <= _line_tolerance(expected)
            checks.append(RuleCheck(
                rule="inv_totals_math_check",
                passed=within,
                message=(
                    f"Totals add up to {total}" if within else
                    f"Subtotal less discount plus freight and sales tax is "
                    f"{round(expected, 2)}, but the total reads {total}"
                ),
                field="totals.total",
            ))

    amount_paid = _as_number(totals.get("amount_paid"))
    if total is not None and balance_due is not None:
        expected = total - (amount_paid or 0.0)
        within = abs(expected - balance_due) <= _line_tolerance(expected)
        checks.append(RuleCheck(
            rule="inv_balance_due_check",
            passed=within,
            message=(
                f"Balance due {balance_due}" if within else
                f"Total less amount paid is {round(expected, 2)}, "
                f"but the balance due reads {balance_due}"
            ),
            field="totals.balance_due",
        ))

    negative = [
        key for key in ("subtotal", "freight", "sales_tax", "tax_rate")
        if (_as_number(totals.get(key)) or 0.0) < 0
    ]
    if negative:
        checks.append(RuleCheck(
            rule="inv_charges_non_negative",
            passed=False,
            message="Negative values found in: " + ", ".join(negative),
            field="totals",
        ))
    return checks
