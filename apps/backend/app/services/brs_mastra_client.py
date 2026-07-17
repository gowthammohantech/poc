import os
import json
import re
import base64
import asyncio
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

MASTRA_URL = os.getenv("MASTRA_SERVICE_URL", "http://localhost:4111")
TIMEOUT = 180.0


def _parse_agent_text(response_json: dict) -> str:
    if "text" in response_json:
        return response_json["text"]
    messages = response_json.get("messages", [])
    for msg in reversed(messages):
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            return content
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    return part.get("text", "")
    return ""


def _extract_json_from_text(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def call_brs_direct_vision_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    image_paths: List[str] = payload.get("page_image_paths", [])
    document_id: str = payload.get("document_id", "")
    ocr_text: str = payload.get("ocr_text", "")

    ocr_section = ""
    if ocr_text.strip():
        ocr_section = (
            f"\n\n--- TESSERACT OCR TEXT (secondary reference, may contain errors) ---\n"
            f"{ocr_text}\n"
            f"--- END OCR TEXT ---\n\n"
            f"Cross-reference the OCR text with the images. "
            f"The images are authoritative — use OCR text to confirm uncertain values such as amounts, dates, and account numbers.\n"
        )

    content_parts = [
        {
            "type": "text",
            "text": (
                f"Extract structured Bank Reconciliation Statement (BRS) data from these document page images.\n"
                f"Document ID: {document_id}"
                f"{ocr_section}"
                f"Return the complete BRS JSON following the schema exactly. "
                f"Use null for missing values. Never hallucinate values. "
                f"Preserve exact account numbers and reference numbers character-for-character."
            )
        }
    ]

    for path in image_paths[:5]:
        try:
            image_data = Path(path).read_bytes()
            b64 = base64.b64encode(image_data).decode()
            content_parts.append({
                "type": "image",
                "image": f"data:image/png;base64,{b64}"
            })
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/brsDirectVisionAgent/generate",
                json={"messages": [{"role": "user", "content": content_parts}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            return _extract_json_from_text(text)
    except Exception:
        return {}


BANK_STATEMENT_BATCH_SIZE = 5

_DATE_FORMATS = ["%d/%m/%y", "%d/%m/%Y", "%d-%m-%y", "%d-%m-%Y"]


def _normalize_transaction_date(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return raw
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _fix_date_if_out_of_range(date_str: Any, period_start: Optional[str], period_end: Optional[str]) -> Any:
    if not isinstance(date_str, str) or not period_start or not period_end:
        return date_str
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        start = datetime.strptime(period_start, "%Y-%m-%d")
        end = datetime.strptime(period_end, "%Y-%m-%d")
    except ValueError:
        return date_str
    if start <= d <= end:
        return date_str
    if d.day <= 12:
        try:
            swapped = d.replace(month=d.day, day=d.month)
        except ValueError:
            return date_str
        if start <= swapped <= end:
            return swapped.strftime("%Y-%m-%d")
    return date_str


async def _call_bank_statement_batch(
    document_id: str, image_paths: List[str], ocr_text: str,
    batch_num: int, total_batches: int, is_first: bool, is_last: bool,
) -> Dict[str, Any]:
    ocr_section = ""
    if is_first and ocr_text.strip():
        ocr_section = (
            f"\n\n--- TESSERACT OCR TEXT (secondary reference, may contain errors) ---\n"
            f"{ocr_text}\n--- END OCR TEXT ---\n"
        )

    content_parts: List[Dict[str, str]] = [{
        "type": "text",
        "text": (
            f"Extract bank statement data from this batch of page images.\n"
            f"Document ID: {document_id}\n"
            f"This is batch {batch_num} of {total_batches} (pages are in order, consecutive).\n"
            f"Extract document_info, opening_balance, and closing_balance whenever their explicit "
            f"labels appear in THESE pages — they may be on any page, including a summary box at "
            f"the start, the end, or a dedicated summary page. Do not assume based on batch position.\n"
            f"{ocr_section}"
            f"Return the complete bank statement JSON following the schema exactly. "
            f"Extract every transaction row visible in these images, in order. "
            f"Use null for missing values. Never hallucinate values."
        ),
    }]
    for path in image_paths:
        try:
            image_data = Path(path).read_bytes()
            b64 = base64.b64encode(image_data).decode()
            content_parts.append({"type": "image", "image": f"data:image/png;base64,{b64}"})
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            f"{MASTRA_URL}/api/agents/bankStatementDirectVisionAgent/generate",
            json={"messages": [{"role": "user", "content": content_parts}]},
        )
        r.raise_for_status()
        text = _parse_agent_text(r.json())
        return _extract_json_from_text(text)


async def call_bank_statement_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    image_paths: List[str] = payload.get("page_image_paths", [])
    document_id: str = payload.get("document_id", "")
    ocr_text: str = payload.get("ocr_text", "")

    batches = [
        image_paths[i:i + BANK_STATEMENT_BATCH_SIZE]
        for i in range(0, len(image_paths), BANK_STATEMENT_BATCH_SIZE)
    ] or [[]]
    total_batches = len(batches)

    document_info: Dict[str, Any] = {}
    statement_totals: Dict[str, Any] = {}
    best_opening = (None, -1.0)  # (value, confidence)
    best_closing = (None, -1.0)
    transactions: List[Dict[str, Any]] = []
    overall_confidences: List[float] = []
    transaction_confidences: List[float] = []
    failed_batches: List[int] = []

    for idx, batch_paths in enumerate(batches):
        is_first = idx == 0
        is_last = idx == total_batches - 1
        result = None
        for attempt in range(3):
            try:
                result = await _call_bank_statement_batch(
                    document_id, batch_paths, ocr_text, idx + 1, total_batches, is_first, is_last,
                )
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
        if result is None:
            failed_batches.append(idx + 1)
            continue

        bs = result.get("bank_statement", {})
        conf = result.get("confidence", {})

        if bs.get("document_info") and not document_info:
            document_info = bs["document_info"]
        for key, value in (bs.get("statement_totals") or {}).items():
            if value is not None and statement_totals.get(key) is None:
                statement_totals[key] = value

        if bs.get("opening_balance") is not None:
            opening_conf = conf.get("opening_balance", 0.0) or 0.0
            if opening_conf >= best_opening[1]:
                best_opening = (bs["opening_balance"], opening_conf)
        if bs.get("closing_balance") is not None:
            closing_conf = conf.get("closing_balance", 0.0) or 0.0
            if closing_conf >= best_closing[1]:
                best_closing = (bs["closing_balance"], closing_conf)

        for txn in bs.get("transactions") or []:
            txn["transaction_date"] = _normalize_transaction_date(txn.get("transaction_date"))
            transactions.append(txn)
        if conf.get("overall") is not None:
            overall_confidences.append(conf["overall"])
        if conf.get("transactions") is not None:
            transaction_confidences.append(conf["transactions"])

    period_start = document_info.get("statement_period_start")
    period_end = document_info.get("statement_period_end")
    for txn in transactions:
        txn["transaction_date"] = _fix_date_if_out_of_range(
            txn.get("transaction_date"), period_start, period_end
        )

    def _avg(values: List[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    return {
        "document_id": document_id,
        "bank_statement": {
            "document_info": document_info,
            "opening_balance": best_opening[0],
            "closing_balance": best_closing[0],
            "statement_totals": statement_totals,
            "transactions": transactions,
        },
        "confidence": {
            "overall": _avg(overall_confidences),
            "opening_balance": max(best_opening[1], 0.0),
            "closing_balance": max(best_closing[1], 0.0),
            "transactions": _avg(transaction_confidences),
        },
        "failed_batches": failed_batches,
        "total_batches": total_batches,
    }


async def call_brs_validation_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        f"Validate this extracted Bank Reconciliation Statement (BRS) data for accuracy and mathematical consistency.\n\n"
        f"Document ID: {payload.get('document_id')}\n\n"
        f"Today's date: {date.today().isoformat()}\n\n"
        f"BRS JSON:\n{json.dumps(payload.get('brs_json', {}), indent=2)}\n\n"
        f"Return JSON: {{\"llm_checks\": [{{\"check\": str, \"result\": \"PASS|FAIL|UNCERTAIN\", "
        f"\"confidence\": 0-1, \"message\": str, \"field\": str|null}}], "
        f"\"warnings\": [str], \"confidence_adjustments\": {{field: delta}}}}"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/brsValidationAgent/generate",
                json={"messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            return _extract_json_from_text(text)
    except Exception:
        return {"llm_checks": [], "warnings": [], "confidence_adjustments": {}}
