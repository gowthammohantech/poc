import re
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any, Dict, List, Optional, Tuple


PROCESSING_MODE = "TESSERACT_TABLE"
LOW_ROW_CONFIDENCE = 55.0
BALANCE_TOLERANCE = 0.05


@dataclass
class OcrWord:
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float
    page_index: int

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass
class OcrRow:
    words: List[OcrWord]
    page_index: int

    @property
    def text(self) -> str:
        return " ".join(word.text for word in sorted(self.words, key=lambda w: w.x)).strip()

    @property
    def avg_confidence(self) -> float:
        confidences = [word.confidence for word in self.words if word.confidence > 0]
        return sum(confidences) / len(confidences) if confidences else 0.0

    @property
    def center_y(self) -> float:
        return sum(word.center_y for word in self.words) / len(self.words)


@dataclass
class ColumnLayout:
    anchors: Dict[str, float]

    def bucket_words(self, row: OcrRow) -> Dict[str, List[OcrWord]]:
        columns = sorted(self.anchors.items(), key=lambda item: item[1])
        buckets = {name: [] for name, _ in columns}
        if not columns:
            return buckets

        boundaries = [
            (columns[i][1] + columns[i + 1][1]) / 2
            for i in range(len(columns) - 1)
        ]

        for word in row.words:
            col_index = 0
            while col_index < len(boundaries) and word.center_x > boundaries[col_index]:
                col_index += 1
            buckets[columns[col_index][0]].append(word)

        return buckets


def extract_brs_from_tesseract_result(
    ocr_result: Dict[str, Any],
    document_id: str,
    page_count: int,
) -> Dict[str, Any]:
    warnings: List[str] = []
    text = ocr_result.get("text", "") or ""
    metadata = ocr_result.get("metadata", {}) or {}
    pages = metadata.get("page_references", []) or []

    transactions = _extract_transactions(pages, warnings)
    doc_info = _extract_document_info(text)
    balances = _extract_balances(text)
    confidence = _build_confidence(ocr_result.get("confidence", 0.0), balances, transactions)

    if not transactions:
        warnings.append("No transaction rows were extracted from the Tesseract word boxes.")

    return {
        "document_id": document_id,
        "brs": {
            "document_info": doc_info,
            "balances": balances,
            "bank_side_items": [],
            "book_side_items": [],
            "bank_transactions": transactions,
            "adjusted_bank_balance": None,
            "adjusted_book_balance": None,
        },
        "confidence": confidence,
        "metadata": {
            "processing_mode": PROCESSING_MODE,
            "ocr_confidence": ocr_result.get("confidence", 0.0),
            "pages": page_count,
            "transaction_count": len(transactions),
            "extraction_warnings": warnings,
        },
    }


def _extract_transactions(pages: List[dict], warnings: List[str]) -> List[Dict[str, Any]]:
    transactions: List[Dict[str, Any]] = []
    active_layout: Optional[ColumnLayout] = None

    for page_index, page in enumerate(pages):
        rows = _rows_from_page(page, page_index)
        page_layout = _find_layout(rows)
        if page_layout:
            active_layout = page_layout

        for row in rows:
            detected_layout = _detect_column_layout(row)
            if detected_layout:
                active_layout = detected_layout
                continue
            if not active_layout:
                continue

            parsed = _parse_transaction_row(row, active_layout, warnings)
            if parsed == "CONTINUATION":
                continuation = _continuation_text(row, active_layout)
                if continuation and transactions:
                    current = transactions[-1]
                    current["description"] = _join_description(current.get("description"), continuation)
                continue
            if not isinstance(parsed, dict):
                continue

            parsed["_row_confidence"] = row.avg_confidence
            if row.avg_confidence < LOW_ROW_CONFIDENCE:
                warnings.append(
                    f"Low OCR confidence for transaction row on page {row.page_index + 1}: "
                    f"{row.avg_confidence:.1f}% ({row.text})"
                )
            transactions.append(parsed)

    _infer_single_amount_sides(transactions, warnings)
    return [_public_transaction(txn) for txn in transactions]


def _rows_from_page(page: dict, page_index: int) -> List[OcrRow]:
    words = [
        OcrWord(
            text=str(box.get("text", "")).strip(),
            x=float(box.get("x", 0)),
            y=float(box.get("y", 0)),
            width=float(box.get("width", 0)),
            height=float(box.get("height", 0)),
            confidence=float(box.get("confidence", 0)),
            page_index=page_index,
        )
        for box in page.get("boxes", [])
        if str(box.get("text", "")).strip()
    ]
    if not words:
        return []

    heights = [word.height for word in words if word.height > 0]
    row_tolerance = max(8.0, (median(heights) if heights else 12.0) * 0.75)
    rows: List[List[OcrWord]] = []

    for word in sorted(words, key=lambda w: (w.center_y, w.x)):
        if not rows:
            rows.append([word])
            continue

        current_center = sum(item.center_y for item in rows[-1]) / len(rows[-1])
        if abs(word.center_y - current_center) <= row_tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])

    return [
        OcrRow(words=sorted(row_words, key=lambda w: w.x), page_index=page_index)
        for row_words in rows
    ]


def _find_layout(rows: List[OcrRow]) -> Optional[ColumnLayout]:
    for row in rows[:20]:
        layout = _detect_column_layout(row)
        if layout:
            return layout
    return None


def _detect_column_layout(row: OcrRow) -> Optional[ColumnLayout]:
    anchors: Dict[str, float] = {}
    tokens = [_clean_token(word.text) for word in row.words]

    for index, word in enumerate(row.words):
        token = tokens[index]
        previous = tokens[index - 1] if index > 0 else ""

        if token == "date":
            _set_anchor(anchors, "date", word.center_x, prefer="left")
        elif token in {"description", "particulars", "narration", "details", "remarks"}:
            _set_anchor(anchors, "description", word.center_x)
        elif token == "transaction" and "description" not in anchors:
            _set_anchor(anchors, "description", word.center_x)
        elif token in {"ref", "reference", "cheque", "check", "chq", "utr", "instrument"}:
            _set_anchor(anchors, "reference", word.center_x)
        elif token == "no" and previous in {"ref", "reference", "cheque", "check", "chq", "instrument"}:
            _set_anchor(anchors, "reference", word.center_x)
        elif token in {"debit", "withdrawal", "withdrawals", "paid", "dr"}:
            _set_anchor(anchors, "debit", word.center_x)
        elif token in {"credit", "deposit", "deposits", "received", "receipt", "cr"}:
            _set_anchor(anchors, "credit", word.center_x)
        elif token in {"amount", "amt"} and "debit" not in anchors and "credit" not in anchors:
            _set_anchor(anchors, "amount", word.center_x)
        elif token in {"balance", "bal"}:
            _set_anchor(anchors, "balance", word.center_x, prefer="right")

    has_date = "date" in anchors
    has_text = "description" in anchors or "reference" in anchors
    has_money = any(key in anchors for key in ("debit", "credit", "amount", "balance"))
    if has_date and has_text and has_money:
        return ColumnLayout(anchors=anchors)
    return None


def _set_anchor(anchors: Dict[str, float], name: str, value: float, prefer: str = "average"):
    if name not in anchors:
        anchors[name] = value
    elif prefer == "left":
        anchors[name] = min(anchors[name], value)
    elif prefer == "right":
        anchors[name] = max(anchors[name], value)
    else:
        anchors[name] = (anchors[name] + value) / 2


def _parse_transaction_row(
    row: OcrRow,
    layout: ColumnLayout,
    warnings: List[str],
) -> Optional[Dict[str, Any] | str]:
    row_text = row.text
    if _is_total_or_balance_row(row_text):
        return None

    buckets = layout.bucket_words(row)
    date_text = _bucket_text(buckets, "date")
    normalized_date = _parse_date_from_text(date_text) or _parse_date_from_text(row_text)

    if not normalized_date:
        if row_text and not _looks_like_non_transaction_text(row_text):
            return "CONTINUATION"
        return None

    debit = _amount_value(_parse_amount(_bucket_text(buckets, "debit")))
    credit = _amount_value(_parse_amount(_bucket_text(buckets, "credit")))
    balance = _amount_value(_parse_amount(_bucket_text(buckets, "balance")))
    amount_info = _parse_amount(_bucket_text(buckets, "amount"))

    if debit is None and credit is None and amount_info:
        value, marker = amount_info
        debit, credit = _side_from_marker(value, marker)

    description = _bucket_text(buckets, "description")
    reference = _bucket_text(buckets, "reference") or _extract_reference(row_text)

    if not description:
        description = _fallback_description(row, buckets)

    if debit is None and credit is None and amount_info:
        warnings.append(
            f"Could not determine debit/credit side for amount {amount_info[0]:.2f} "
            f"on page {row.page_index + 1}: {row.text}"
        )

    return {
        "date": normalized_date,
        "description": description or None,
        "reference_number": reference or None,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "_single_amount": amount_info[0] if amount_info else None,
        "_single_amount_marker": amount_info[1] if amount_info else None,
        "_page_index": row.page_index,
        "_raw_text": row.text,
    }


def _infer_single_amount_sides(transactions: List[Dict[str, Any]], warnings: List[str]):
    previous_balance: Optional[float] = None

    for index, txn in enumerate(transactions):
        amount = txn.get("_single_amount")
        if txn.get("debit") is None and txn.get("credit") is None and amount is not None:
            debit, credit = _side_from_marker(amount, txn.get("_single_amount_marker"))
            if debit is not None or credit is not None:
                txn["debit"] = debit
                txn["credit"] = credit
            elif previous_balance is not None and txn.get("balance") is not None:
                balance_delta = round(float(txn["balance"]) - previous_balance, 2)
                if abs(abs(balance_delta) - amount) <= BALANCE_TOLERANCE:
                    if balance_delta < 0:
                        txn["debit"] = amount
                    else:
                        txn["credit"] = amount
                else:
                    warnings.append(
                        f"Could not infer debit/credit side for row {index + 1}; "
                        f"amount {amount:.2f} does not match running balance delta {balance_delta:.2f}."
                    )

        if txn.get("balance") is not None:
            previous_balance = float(txn["balance"])


def _public_transaction(txn: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "date": txn.get("date"),
        "description": txn.get("description"),
        "reference_number": txn.get("reference_number"),
        "debit": txn.get("debit"),
        "credit": txn.get("credit"),
        "balance": txn.get("balance"),
    }


def _bucket_text(buckets: Dict[str, List[OcrWord]], name: str) -> str:
    return " ".join(word.text for word in sorted(buckets.get(name, []), key=lambda w: w.x)).strip()


def _continuation_text(row: OcrRow, layout: ColumnLayout) -> str:
    buckets = layout.bucket_words(row)
    text = _bucket_text(buckets, "description") or _fallback_description(row, buckets)
    return "" if _is_total_or_balance_row(text) else text


def _fallback_description(row: OcrRow, buckets: Dict[str, List[OcrWord]]) -> str:
    ignored = set()
    for bucket_name in ("date", "debit", "credit", "amount", "balance"):
        ignored.update(id(word) for word in buckets.get(bucket_name, []))
    words = [word.text for word in row.words if id(word) not in ignored]
    return " ".join(words).strip()


def _join_description(current: Optional[str], continuation: str) -> str:
    if not current:
        return continuation.strip()
    return f"{current.strip()} {continuation.strip()}".strip()


def _is_total_or_balance_row(text: str) -> bool:
    lower = text.lower()
    balance_terms = (
        "opening balance",
        "closing balance",
        "balance brought",
        "balance b/f",
        "balance bf",
        "balance carried",
        "balance c/f",
        "balance cf",
        "available balance",
        "reconciled balance",
        "grand total",
    )
    if any(term in lower for term in balance_terms):
        return True
    return bool(re.search(r"^\s*(total|net|subtotal)\b", lower))


def _looks_like_non_transaction_text(text: str) -> bool:
    lower = text.lower()
    return any(
        phrase in lower
        for phrase in (
            "statement",
            "account number",
            "customer",
            "page ",
            "date description",
            "date particulars",
        )
    )


def _clean_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_date_from_text(value: str) -> Optional[str]:
    if not value:
        return None

    month = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
    patterns = [
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b",
        rf"\b\d{{1,2}}[-\s]{month}[-\s]\d{{2,4}}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = _normalize_date(match.group(0))
        if parsed:
            return parsed
    return None


def _normalize_date(value: str) -> Optional[str]:
    cleaned = re.sub(r"\s+", " ", value.strip())
    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%y",
        "%d/%m/%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d %b %y",
        "%d %B %y",
        "%d-%b-%y",
        "%d-%B-%y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned.title(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> Optional[Tuple[float, Optional[str]]]:
    if not value or value.strip() in {"-", "--"}:
        return None

    lower = value.lower()
    marker = None
    if re.search(r"\b(dr|debit|withdrawal)\b", lower) or "(" in value or "-" in value:
        marker = "debit"
    elif re.search(r"\b(cr|credit|deposit)\b", lower):
        marker = "credit"

    matches = re.findall(
        r"[-(]?\s*(?:\d{1,3}(?:[,\s]\d{2,3})+|\d+)(?:\.\d{1,2})?\)?",
        value,
    )
    if not matches:
        return None

    raw = matches[-1]
    cleaned = (
        raw.replace(",", "")
        .replace(" ", "")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "")
    )
    try:
        return float(cleaned), marker
    except ValueError:
        return None


def _amount_value(info: Optional[Tuple[float, Optional[str]]]) -> Optional[float]:
    if not info:
        return None
    return info[0]


def _side_from_marker(amount: float, marker: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    if marker == "debit":
        return amount, None
    if marker == "credit":
        return None, amount
    return None, None


def _extract_reference(text: str) -> Optional[str]:
    match = re.search(
        r"\b(?:ref|reference|utr|chq|cheque|check|txn|transaction)\s*[:#.-]?\s*([A-Z0-9/-]{3,})",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _extract_document_info(text: str) -> Dict[str, Any]:
    account_number = _extract_labeled_text(
        text,
        [r"account\s*(?:number|no\.?)", r"a/c\s*(?:number|no\.?)", r"acct\s*(?:number|no\.?)"],
    )
    company_name = _extract_labeled_text(
        text,
        [r"company\s*name", r"account\s*name", r"customer\s*name"],
    )
    bank_name = _extract_labeled_text(text, [r"bank\s*name"]) or _extract_bank_name(text)
    period_start, period_end = _extract_statement_period(text)

    return {
        "company_name": company_name,
        "bank_name": bank_name,
        "account_number": account_number,
        "statement_period_start": period_start,
        "statement_period_end": period_end,
        "currency": _extract_currency(text),
        "prepared_by": None,
        "prepared_date": None,
    }


def _extract_balances(text: str) -> Dict[str, Any]:
    opening_bank = _extract_labeled_amount(
        text,
        ["opening balance", "balance brought forward", "balance b/f", "balance bf"],
    )
    closing_bank = _extract_labeled_amount(
        text,
        ["closing balance", "balance carried forward", "balance c/f", "balance cf"],
    )
    return {
        "opening_balance_bank": opening_bank,
        "opening_balance_book": None,
        "closing_balance_bank": closing_bank,
        "closing_balance_book": None,
        "reconciled_balance": None,
    }


def _extract_labeled_text(text: str, labels: List[str]) -> Optional[str]:
    for line in text.splitlines():
        for label in labels:
            match = re.search(rf"{label}\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                return value[:80] if value else None
    return None


def _extract_bank_name(text: str) -> Optional[str]:
    for line in text.splitlines()[:12]:
        value = line.strip()
        if 3 <= len(value) <= 80 and "bank" in value.lower():
            return value
    return None


def _extract_statement_period(text: str) -> Tuple[Optional[str], Optional[str]]:
    for line in text.splitlines():
        lower = line.lower()
        if "period" not in lower and "from" not in lower:
            continue
        dates = []
        for match in re.finditer(
            r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
            line,
        ):
            parsed = _normalize_date(match.group(0))
            if parsed:
                dates.append(parsed)
        if len(dates) >= 2:
            return dates[0], dates[1]
    return None, None


def _extract_currency(text: str) -> str:
    if re.search(r"\bUSD\b|\$", text, flags=re.IGNORECASE):
        return "USD"
    if re.search(r"\bINR\b|₹|\bRs\.?\b", text, flags=re.IGNORECASE):
        return "INR"
    return "INR"


def _extract_labeled_amount(text: str, labels: List[str]) -> Optional[float]:
    for line in text.splitlines():
        lower = line.lower()
        if not any(label in lower for label in labels):
            continue
        amount = _parse_amount(line)
        if amount:
            return amount[0]
    return None


def _build_confidence(
    ocr_confidence: float,
    balances: Dict[str, Any],
    transactions: List[Dict[str, Any]],
) -> Dict[str, float]:
    overall = round(max(0.0, min(float(ocr_confidence) / 100, 1.0)), 2)
    return {
        "overall": overall,
        "opening_balance_bank": overall if balances.get("opening_balance_bank") is not None else 0.0,
        "opening_balance_book": 0.0,
        "closing_balance_bank": overall if balances.get("closing_balance_bank") is not None else 0.0,
        "closing_balance_book": 0.0,
        "bank_side_items": 0.0,
        "book_side_items": 0.0,
        "reconciled_balance": 0.0,
        "bank_transactions": overall if transactions else 0.0,
    }
