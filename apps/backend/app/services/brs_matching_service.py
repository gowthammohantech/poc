from datetime import datetime, date
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple

AMOUNT_TOLERANCE = 0.01
FUZZY_DATE_WINDOW_DAYS = 3
FUZZY_DESCRIPTION_THRESHOLD = 0.6
FUZZY_LEDGER_NAME_THRESHOLD = 0.72

_DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"]


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _bank_txn_side_amount(txn: Dict[str, Any]) -> Optional[Tuple[str, float]]:
    debit = txn.get("debit")
    credit = txn.get("credit")
    if debit is not None and debit > 0:
        return "DEBIT", float(debit)
    if credit is not None and credit > 0:
        return "CREDIT", float(credit)
    return None


def _description_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(
        "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
    )


def _ledger_name_similarity(bank_description: Optional[str], ledger_name: Optional[str]) -> float:
    bank_text = _normalize_text(bank_description)
    ledger_text = _normalize_text(ledger_name)
    if not bank_text or not ledger_text:
        return 0.0
    if ledger_text in bank_text:
        return 1.0

    ledger_tokens = [token for token in ledger_text.split() if len(token) > 2]
    if ledger_tokens and all(token in bank_text for token in ledger_tokens):
        return 0.95

    return SequenceMatcher(None, bank_text, ledger_text).ratio()


def _normalize_ref(ref: Optional[str]) -> str:
    return (ref or "").strip().lower()


def run_two_way_match(bank_transactions: List[Dict[str, Any]], ledger_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    bank_candidates = []
    for i, txn in enumerate(bank_transactions):
        side_amount = _bank_txn_side_amount(txn)
        if side_amount is None:
            continue
        side, amount = side_amount
        bank_candidates.append({
            "index": i,
            "txn": txn,
            "side": side,
            "amount": amount,
            "txn_date": _parse_date(txn.get("date")),
        })

    ledger_candidates = []
    for i, entry in enumerate(ledger_entries):
        ledger_candidates.append({
            "index": i,
            "entry": entry,
            "side": entry.get("entry_type"),
            "amount": float(entry.get("amount") or 0),
            "entry_date": _parse_date(entry.get("entry_date")),
        })

    unmatched_bank_ids = {b["index"] for b in bank_candidates}
    unmatched_ledger_ids = {l["index"] for l in ledger_candidates}
    matched: List[Dict[str, Any]] = []

    # Pass 1: exact match (same date, same amount, same side)
    exact_pairs = []
    for b in bank_candidates:
        if b["index"] not in unmatched_bank_ids or b["txn_date"] is None:
            continue
        for l in ledger_candidates:
            if l["index"] not in unmatched_ledger_ids or l["entry_date"] is None:
                continue
            if b["side"] != l["side"]:
                continue
            if abs(b["amount"] - l["amount"]) > AMOUNT_TOLERANCE:
                continue
            if b["txn_date"] != l["entry_date"]:
                continue
            ref_match = _normalize_ref(b["txn"].get("reference_number")) and \
                _normalize_ref(b["txn"].get("reference_number")) == _normalize_ref(l["entry"].get("reference_number"))
            desc_sim = _description_similarity(b["txn"].get("description"), l["entry"].get("description"))
            name_sim = _ledger_name_similarity(b["txn"].get("description"), l["entry"].get("ledger_name"))
            tie_break_score = (1 if ref_match else 0) + max(desc_sim, name_sim)
            exact_pairs.append((b, l, 1.0, tie_break_score))

    exact_pairs.sort(key=lambda p: p[3], reverse=True)
    for b, l, score, _tie_break_score in exact_pairs:
        if b["index"] not in unmatched_bank_ids or l["index"] not in unmatched_ledger_ids:
            continue
        matched.append(_build_match(b, l, "EXACT", score))
        unmatched_bank_ids.discard(b["index"])
        unmatched_ledger_ids.discard(l["index"])

    # Pass 2: fuzzy match on what's left (amount exact, date within window, ref or description similarity)
    fuzzy_pairs = []
    for b in bank_candidates:
        if b["index"] not in unmatched_bank_ids:
            continue
        for l in ledger_candidates:
            if l["index"] not in unmatched_ledger_ids:
                continue
            if b["side"] != l["side"]:
                continue
            if abs(b["amount"] - l["amount"]) > AMOUNT_TOLERANCE:
                continue

            date_diff_days = None
            if b["txn_date"] is not None and l["entry_date"] is not None:
                date_diff_days = abs((b["txn_date"] - l["entry_date"]).days)
                if date_diff_days > FUZZY_DATE_WINDOW_DAYS:
                    continue

            ref_match = _normalize_ref(b["txn"].get("reference_number")) and \
                _normalize_ref(b["txn"].get("reference_number")) == _normalize_ref(l["entry"].get("reference_number"))
            desc_sim = _description_similarity(b["txn"].get("description"), l["entry"].get("description"))
            name_sim = _ledger_name_similarity(b["txn"].get("description"), l["entry"].get("ledger_name"))
            text_signal = max(desc_sim, name_sim)

            if not ref_match and text_signal < FUZZY_DESCRIPTION_THRESHOLD:
                continue

            score = 0.5
            score += 0.3 if ref_match else text_signal * 0.3
            if name_sim >= FUZZY_LEDGER_NAME_THRESHOLD:
                score += 0.05
            if date_diff_days is not None:
                score += max(0, (FUZZY_DATE_WINDOW_DAYS - date_diff_days) / FUZZY_DATE_WINDOW_DAYS) * 0.15
            score = min(score, 0.95)

            fuzzy_pairs.append((b, l, score, date_diff_days))

    fuzzy_pairs.sort(key=lambda p: p[2], reverse=True)
    for b, l, score, date_diff_days in fuzzy_pairs:
        if b["index"] not in unmatched_bank_ids or l["index"] not in unmatched_ledger_ids:
            continue
        matched.append(_build_match(b, l, "FUZZY", score, date_diff_days))
        unmatched_bank_ids.discard(b["index"])
        unmatched_ledger_ids.discard(l["index"])

    unmatched_bank = [b["txn"] for b in bank_candidates if b["index"] in unmatched_bank_ids]
    unmatched_ledger = [l["entry"] for l in ledger_candidates if l["index"] in unmatched_ledger_ids]

    total_bank = len(bank_candidates)
    total_ledger = len(ledger_candidates)
    matched_count = len(matched)
    denom = max(total_bank, total_ledger)
    match_rate = round((matched_count / denom) * 100, 1) if denom else 0.0

    return {
        "summary": {
            "total_bank": total_bank,
            "total_ledger": total_ledger,
            "matched": matched_count,
            "unmatched_bank": len(unmatched_bank),
            "unmatched_ledger": len(unmatched_ledger),
            "match_rate": match_rate,
        },
        "matched": matched,
        "unmatched_bank": unmatched_bank,
        "unmatched_ledger": unmatched_ledger,
    }


def _build_match(b: Dict[str, Any], l: Dict[str, Any], match_type: str, confidence: float,
                  date_diff_days: Optional[int] = None) -> Dict[str, Any]:
    if date_diff_days is None and b["txn_date"] is not None and l["entry_date"] is not None:
        date_diff_days = abs((b["txn_date"] - l["entry_date"]).days)
    return {
        "bank_transaction": b["txn"],
        "ledger_entry": l["entry"],
        "match_type": match_type,
        "confidence": round(confidence, 2),
        "date_diff_days": date_diff_days,
        "amount_diff": round(abs(b["amount"] - l["amount"]), 2),
    }
