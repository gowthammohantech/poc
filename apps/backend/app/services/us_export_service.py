"""Export builders for the two US document types.

The India builders hardcode thirteen GST columns at fixed indices, which a
shipping authorization's variable-width week grid cannot use, so these are
separate builders rather than a country flag threaded through those. The route
layer, the final_outputs table and the download endpoints are all shared.
"""

import csv
import io
from typing import Any, Dict, List, Optional

DOC_TYPE_SA = "SA"


def _document(final_output: Dict[str, Any]) -> Dict[str, Any]:
    return (final_output.get("corrected_json", {}) or {}).get("invoice", {}) or {}


def _blank(value: Any) -> Any:
    """Excel and CSV both read None as the string 'None' unless we intervene."""
    return "" if value is None else value


def _party_rows(label: str, party: Optional[dict]) -> List[List[Any]]:
    party = party or {}
    rows = [[f"{label} Name", _blank(party.get("name"))]]
    if party.get("code") is not None:
        rows.append([f"{label} Code", _blank(party.get("code"))])
    rows.append([f"{label} Address", _blank(party.get("address"))])
    rows.append([f"{label} Contact", _blank(party.get("contact"))])
    if party.get("phone") is not None:
        rows.append([f"{label} Phone", _blank(party.get("phone"))])
    return rows


def _schedule_headers(columns: List[dict]) -> List[str]:
    """One column per weekly bucket, labelled '<week> <delivery date>'."""
    headers = []
    for column in columns:
        column = column or {}
        week = column.get("week_label") or ""
        # The printed date is what a reader checks against the page; the ISO
        # one is derived, so it is the fallback.
        when = column.get("raw_delivery_date") or column.get("delivery_date") or ""
        headers.append(" ".join(part for part in (week, when) if part))
    return headers


def _row_total(quantities: List[Any]) -> float:
    return sum(q for q in quantities if isinstance(q, (int, float)) and not isinstance(q, bool))


def build_us_export_json(final_output: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
    """The corrected payload, stamped with what regime produced it.

    The India builder ignores its `document` argument. Here it is used, so the
    exported file says what it is without the reader having to infer it from
    the field names.
    """
    corrected = dict(final_output.get("corrected_json", {}) or {})
    corrected["country"] = document.get("country") or "USA"
    corrected["document_type"] = resolve_doc_type(final_output, document)
    return corrected


# --------------------------------------------------------------------------
# SA — shipping authorization
# --------------------------------------------------------------------------

def build_sa_export_csv(final_output: Dict[str, Any]) -> str:
    doc = _document(final_output)
    columns = doc.get("schedule_columns") or []
    parts = doc.get("parts") or []

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Shipping Authorization"])
    writer.writerow(["Release Number", _blank(doc.get("release_number"))])
    writer.writerow(["Release Date", _blank(doc.get("release_date"))])
    writer.writerow(["Received By", _blank(doc.get("received_by"))])
    writer.writerow(["Received At", _blank(doc.get("received_at"))])
    writer.writerow([])

    for row in _party_rows("Issuer", doc.get("issuer")):
        writer.writerow(row)
    writer.writerow([])
    for row in _party_rows("Supplier", doc.get("supplier")):
        writer.writerow(row)
    writer.writerow([])

    writer.writerow(["Delivery Schedule"])
    writer.writerow(
        ["PO", "Part Number", "Description", "Std Pack"]
        + _schedule_headers(columns)
        + ["Total"]
    )
    for part in parts:
        quantities = part.get("quantities") or []
        # Pad so every row is the width of the header even when extraction
        # came back short; a ragged CSV is unreadable in a spreadsheet.
        padded = list(quantities[:len(columns)]) + [None] * max(0, len(columns) - len(quantities))
        writer.writerow(
            [
                _blank(part.get("po_number")),
                _blank(part.get("part_number")),
                _blank(part.get("description")),
                _blank(part.get("std_pack")),
            ]
            + [_blank(q) for q in padded]
            + [_row_total(quantities)]
        )

    notes = doc.get("terms_notes") or []
    if notes:
        writer.writerow([])
        writer.writerow(["Terms & Notes"])
        for note in notes:
            writer.writerow([_blank(note)])

    return output.getvalue()


def build_sa_export_excel(final_output: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    doc = _document(final_output)
    columns = doc.get("schedule_columns") or []
    parts = doc.get("parts") or []

    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="D9E1F2")

    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Release Info"
    info = (
        [
            ("Release Number", doc.get("release_number")),
            ("Release Date", doc.get("release_date")),
            ("Received By", doc.get("received_by")),
            ("Received At", doc.get("received_at")),
            ("", ""),
        ]
        + [(label, value) for label, value in (tuple(r) for r in _party_rows("Issuer", doc.get("issuer")))]
        + [("", "")]
        + [(label, value) for label, value in (tuple(r) for r in _party_rows("Supplier", doc.get("supplier")))]
    )
    for row_idx, (label, value) in enumerate(info, start=1):
        ws1.cell(row=row_idx, column=1, value=label).font = bold
        ws1.cell(row=row_idx, column=2, value=_blank(value))
    ws1.column_dimensions["A"].width = 22
    ws1.column_dimensions["B"].width = 50

    ws2 = wb.create_sheet("Delivery Schedule")
    fixed = ["PO", "Part Number", "Description", "Std Pack"]
    headers = fixed + _schedule_headers(columns) + ["Total"]
    for col_idx, name in enumerate(headers, start=1):
        cell = ws2.cell(row=1, column=col_idx, value=name)
        cell.font = bold
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for row_idx, part in enumerate(parts, start=2):
        quantities = part.get("quantities") or []
        ws2.cell(row=row_idx, column=1, value=_blank(part.get("po_number")))
        ws2.cell(row=row_idx, column=2, value=_blank(part.get("part_number")))
        ws2.cell(row=row_idx, column=3, value=_blank(part.get("description")))
        ws2.cell(row=row_idx, column=4, value=_blank(part.get("std_pack")))
        for offset in range(len(columns)):
            value = quantities[offset] if offset < len(quantities) else None
            ws2.cell(row=row_idx, column=len(fixed) + 1 + offset, value=_blank(value))
        ws2.cell(row=row_idx, column=len(headers), value=_row_total(quantities))

    # Without this, scrolling to week 30 loses which part each row is.
    ws2.freeze_panes = "E2"
    for letter, width in (("A", 14), ("B", 18), ("C", 40), ("D", 10)):
        ws2.column_dimensions[letter].width = width

    notes = doc.get("terms_notes") or []
    ws3 = wb.create_sheet("Terms")
    ws3.cell(row=1, column=1, value="Terms & Notes").font = bold
    for row_idx, note in enumerate(notes, start=2):
        cell = ws3.cell(row=row_idx, column=1, value=_blank(note))
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws3.column_dimensions["A"].width = 120

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# SO — purchase order
# --------------------------------------------------------------------------

_SO_LINE_COLUMNS = [
    ("line_number", "Line #"),
    ("part_number", "Part Number"),
    ("description", "Description"),
    ("quantity", "Quantity"),
    ("uom", "UOM"),
    ("due_date", "Due Date"),
    ("unit_cost", "Unit Cost"),
    ("extended_cost", "Ext'd Cost"),
]

_SO_TOTAL_ROWS = [
    ("subtotal", "Subtotal"),
    ("sales_tax", "Sales Tax"),
    ("freight", "Freight"),
    ("discount", "Discount"),
    ("grand_total", "Grand Total"),
]


def build_so_export_csv(final_output: Dict[str, Any]) -> str:
    doc = _document(final_output)
    totals = doc.get("totals") or {}

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Purchase Order"])
    writer.writerow(["PO Number", _blank(doc.get("order_number"))])
    writer.writerow(["Order Date", _blank(doc.get("order_date"))])
    writer.writerow(["Currency", _blank(doc.get("currency"))])
    writer.writerow(["Payment Terms", _blank(doc.get("payment_terms"))])
    writer.writerow(["Freight Terms", _blank(doc.get("freight_terms"))])
    writer.writerow(["Ship Via", _blank(doc.get("ship_via"))])
    writer.writerow(["Received By", _blank(doc.get("received_by"))])
    writer.writerow(["Received At", _blank(doc.get("received_at"))])
    writer.writerow([])

    for label, key in (("Vendor", "vendor"), ("Buyer", "buyer"),
                       ("Bill To", "bill_to"), ("Ship To", "ship_to")):
        for row in _party_rows(label, doc.get(key)):
            writer.writerow(row)
        writer.writerow([])

    writer.writerow(["Line Items"])
    writer.writerow([label for _, label in _SO_LINE_COLUMNS])
    for item in doc.get("line_items") or []:
        writer.writerow([_blank(item.get(key)) for key, _ in _SO_LINE_COLUMNS])

    writer.writerow([])
    writer.writerow(["Totals"])
    for key, label in _SO_TOTAL_ROWS:
        writer.writerow([label, _blank(totals.get(key))])

    notes = doc.get("notes") or []
    if notes:
        writer.writerow([])
        writer.writerow(["Notes"])
        for note in notes:
            writer.writerow([_blank(note)])

    return output.getvalue()


def build_so_export_excel(final_output: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    doc = _document(final_output)
    totals = doc.get("totals") or {}
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="D9E1F2")

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Order Header"

    info: List[tuple] = [
        ("PO Number", doc.get("order_number")),
        ("Order Date", doc.get("order_date")),
        ("Currency", doc.get("currency")),
        ("Payment Terms", doc.get("payment_terms")),
        ("Freight Terms", doc.get("freight_terms")),
        ("Ship Via", doc.get("ship_via")),
        ("Received By", doc.get("received_by")),
        ("Received At", doc.get("received_at")),
        ("", ""),
    ]
    for label, key in (("Vendor", "vendor"), ("Buyer", "buyer"),
                       ("Bill To", "bill_to"), ("Ship To", "ship_to")):
        info.extend(tuple(row) for row in _party_rows(label, doc.get(key)))
        info.append(("", ""))
    info.extend((label, totals.get(key)) for key, label in _SO_TOTAL_ROWS)

    for row_idx, (label, value) in enumerate(info, start=1):
        ws1.cell(row=row_idx, column=1, value=label).font = bold
        ws1.cell(row=row_idx, column=2, value=_blank(value))
    ws1.column_dimensions["A"].width = 22
    ws1.column_dimensions["B"].width = 50

    ws2 = wb.create_sheet("Line Items")
    for col_idx, (_, label) in enumerate(_SO_LINE_COLUMNS, start=1):
        cell = ws2.cell(row=1, column=col_idx, value=label)
        cell.font = bold
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")

    for row_idx, item in enumerate(doc.get("line_items") or [], start=2):
        for col_idx, (key, _) in enumerate(_SO_LINE_COLUMNS, start=1):
            ws2.cell(row=row_idx, column=col_idx, value=_blank(item.get(key)))

    for letter, width in (("A", 8), ("B", 20), ("C", 42), ("D", 12),
                          ("E", 8), ("F", 14), ("G", 14), ("H", 16)):
        ws2.column_dimensions[letter].width = width
    ws2.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------

def resolve_doc_type(final_output: Dict[str, Any], document: Dict[str, Any]) -> Optional[str]:
    """Which builder to use, preferring what the reviewed payload says it is.

    The documents row carries the classifier's answer, which can be UNKNOWN or
    simply wrong. The corrected payload has been through a human, so its own
    document_type wins when it has one.
    """
    payload_type = _document(final_output).get("document_type")
    if isinstance(payload_type, str) and payload_type.strip().upper() in {DOC_TYPE_SA, "SO"}:
        return payload_type.strip().upper()
    return document.get("doc_type")


def build_us_export_csv(final_output: Dict[str, Any], doc_type: Optional[str]) -> str:
    if (doc_type or "").upper() == DOC_TYPE_SA:
        return build_sa_export_csv(final_output)
    return build_so_export_csv(final_output)


def build_us_export_excel(final_output: Dict[str, Any], doc_type: Optional[str]) -> bytes:
    if (doc_type or "").upper() == DOC_TYPE_SA:
        return build_sa_export_excel(final_output)
    return build_so_export_excel(final_output)


def export_basename(doc_type: Optional[str]) -> str:
    return "release" if (doc_type or "").upper() == DOC_TYPE_SA else "order"
