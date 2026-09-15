"""Mastra calls for the two US document types.

Both documents are read by vision. The JSON-parsing helpers are imported from
mastra_client rather than copied -- brs_mastra_client already duplicates them
once, and a third copy is where they start to drift.

Two pieces of work happen here rather than in the prompt, because both are
deterministic and a language model asked to do them will guess:

  * derive_schedule_dates turns a shipping authorization's year-less bucket
    dates ("22-Jun") into ISO dates;
  * normalize_us_payload guarantees the envelope shape the rest of the
    pipeline reads, and lines every quantity row up with the schedule header.
"""

import base64
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.services.mastra_client import _extract_json_from_text, _parse_agent_text

logger = logging.getLogger(__name__)

MASTRA_URL = os.getenv("MASTRA_SERVICE_URL", "http://localhost:4111")
TIMEOUT = 180.0

# Both sample documents are a single page, but a release can run longer. The
# cap keeps a request inside the model's token budget; the caller logs when it
# bites so a dropped page is visible rather than silent.
MAX_VISION_PAGES = 5

DOC_TYPE_SA = "SA"
DOC_TYPE_SO = "SO"
DOC_TYPE_UNKNOWN = "UNKNOWN"
VALID_DOC_TYPES = {DOC_TYPE_SA, DOC_TYPE_SO, DOC_TYPE_UNKNOWN}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_SA_KEYWORDS = (
    "SHIPPING AUTHORIZATION", "DELIVERY RELEASE", "PLANNING RELEASE",
    "MATERIAL RELEASE", "STD PACK", "SUPPLIER CODE", "DELIVERY DATE", "SHIP DATE",
)
_SO_KEYWORDS = (
    "PURCHASE ORDER", "SALES ORDER", "UNIT COST", "UNIT PRICE", "EXT'D COST",
    "EXTENDED", "BILL TO", "SHIP VIA", "FREIGHT TERMS",
)


def _encode_images(image_paths: List[str], document_id: str) -> List[dict]:
    """Base64 the page images the agent will read, capped at MAX_VISION_PAGES."""
    if len(image_paths) > MAX_VISION_PAGES:
        logger.warning(
            "Document %s has %d pages; only the first %d are sent for extraction",
            document_id, len(image_paths), MAX_VISION_PAGES,
        )
    parts = []
    for path in image_paths[:MAX_VISION_PAGES]:
        try:
            b64 = base64.b64encode(Path(path).read_bytes()).decode()
            parts.append({"type": "image", "image": f"data:image/png;base64,{b64}"})
        except Exception:
            logger.warning("Could not read page image %s for document %s", path, document_id)
    return parts


async def _call_agent(agent: str, content: Any, timeout: float = TIMEOUT) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{MASTRA_URL}/api/agents/{agent}/generate",
            json={"messages": [{"role": "user", "content": content}]},
        )
        r.raise_for_status()
        return _extract_json_from_text(_parse_agent_text(r.json()))


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def fallback_document_type(ocr_text: str) -> Dict[str, Any]:
    """A keyword guess, used only when the classifier agent is unreachable.

    Tesseract flattens the SA's wide grid into a run-on line, so this cannot be
    trusted the way the vision classifier can -- hence the low confidence. When
    the text points both ways or neither, say UNKNOWN rather than guessing.
    """
    upper = (ocr_text or "").upper()
    sa_hits = sum(k in upper for k in _SA_KEYWORDS)
    if re.search(r"\bW\d{1,2}\b", upper):
        sa_hits += 1
    so_hits = sum(k in upper for k in _SO_KEYWORDS)

    if sa_hits > so_hits:
        return {"document_type": DOC_TYPE_SA, "confidence": 0.4,
                "reason": "keyword fallback: release-style wording in the OCR text"}
    if so_hits > sa_hits:
        return {"document_type": DOC_TYPE_SO, "confidence": 0.4,
                "reason": "keyword fallback: order-style wording in the OCR text"}
    return {"document_type": DOC_TYPE_UNKNOWN, "confidence": 0.0,
            "reason": "classifier unavailable and the OCR text is inconclusive"}


async def call_us_doc_classifier(payload: Dict[str, Any]) -> Dict[str, Any]:
    document_id = payload.get("document_id", "")
    ocr_text = payload.get("ocr_text", "") or ""

    content = [{
        "type": "text",
        "text": (
            "Classify this US supply-chain document as SO, SA or UNKNOWN.\n"
            f"Document ID: {document_id}\n"
            "Decide from the page layout first and the wording second.\n"
            + (f"\nOCR text (secondary reference only):\n{ocr_text[:4000]}\n" if ocr_text else "")
        ),
    }]
    # Two pages are plenty to tell a wide week grid from an order form.
    content.extend(_encode_images(payload.get("page_image_paths", [])[:2], document_id))

    try:
        result = await _call_agent("usDocClassifierAgent", content)
    except Exception as e:
        logger.warning("US classifier agent failed for %s: %s", document_id, e)
        return fallback_document_type(ocr_text)

    doc_type = str(result.get("document_type") or "").strip().upper()
    if doc_type not in VALID_DOC_TYPES:
        return fallback_document_type(ocr_text)
    return {
        "document_type": doc_type,
        "confidence": result.get("confidence", 0.0),
        "reason": result.get("reason", ""),
    }


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

async def _call_us_vision_agent(agent: str, label: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    document_id = payload.get("document_id", "")
    ocr_text = payload.get("ocr_text", "") or ""
    expected_fields = payload.get("expected_fields") or ""

    content = [{
        "type": "text",
        "text": (
            f"Extract structured data from these {label} page images.\n"
            f"Document ID: {document_id}\n"
            f"Expected fields: {expected_fields}\n"
            "Return the complete JSON following the schema exactly. Use null for "
            "missing values. Never hallucinate values. Preserve part numbers, PO "
            "numbers and supplier codes exactly as printed.\n"
            + (
                "\nOCR text from the same pages. This is a secondary reference: the "
                "images are the ground truth, and the OCR has lost the column layout.\n"
                f"{ocr_text[:12000]}\n" if ocr_text else ""
            )
        ),
    }]
    content.extend(_encode_images(payload.get("page_image_paths", []), document_id))

    try:
        return await _call_agent(agent, content)
    except Exception as e:
        logger.warning("%s failed for %s: %s", agent, document_id, e)
        return {}


async def call_us_sa_vision_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await _call_us_vision_agent(
        "usSaDirectVisionAgent", "shipping authorization", payload)


async def call_us_so_vision_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await _call_us_vision_agent(
        "usSoDirectVisionAgent", "purchase order", payload)


async def call_us_validation_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    import json

    prompt = (
        "Validate this extracted US supply-chain document for accuracy and completeness.\n\n"
        f"Document ID: {payload.get('document_id')}\n"
        f"Document type: {payload.get('document_type')}\n"
        f"Today's date: {date.today().isoformat()}\n\n"
        f"{json.dumps(payload.get('document_json', {}), indent=2)}\n\n"
        "Return the validation JSON."
    )
    try:
        return await _call_agent("usValidationAgent", prompt, timeout=120.0)
    except Exception as e:
        logger.warning("US validation agent failed for %s: %s",
                       payload.get("document_id"), e)
        return {"llm_checks": [], "warnings": [], "confidence_adjustments": {}}


# --------------------------------------------------------------------------
# Deterministic post-processing
# --------------------------------------------------------------------------

def _parse_day_month(raw: Any) -> Optional[tuple[int, int]]:
    """Read a bucket date like '22-Jun' or '6 Jul' into (day, month)."""
    if not isinstance(raw, str):
        return None
    match = re.match(r"^\s*(\d{1,2})[-/\s]*([A-Za-z]{3,})", raw.strip())
    if not match:
        return None
    month = _MONTHS.get(match.group(2)[:3].lower())
    if month is None:
        return None
    return int(match.group(1)), month


def _seed_year(*candidates: Any) -> Optional[int]:
    for value in candidates:
        if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
            return int(value[:4])
    return None


def _walk_forward(raws: List[Any], start_year: int) -> List[Optional[str]]:
    """Attach years to a run of year-less dates that moves forward in time.

    The buckets are consecutive weeks, so the year advances exactly when the
    month number stops increasing -- December to January. Doing this in Python
    rather than in the prompt is the point: it is arithmetic, and a model asked
    to supply a year will invent one.
    """
    out: List[Optional[str]] = []
    year = start_year
    previous: Optional[tuple[int, int]] = None

    for raw in raws:
        parsed = _parse_day_month(raw)
        if parsed is None:
            out.append(None)
            continue
        day, month = parsed
        if previous is not None and (month, day) < previous:
            year += 1
        previous = (month, day)
        try:
            out.append(date(year, month, day).isoformat())
        except ValueError:
            out.append(None)
    return out


def derive_schedule_dates(document: Dict[str, Any]) -> Dict[str, Any]:
    """Fill in ship_date and delivery_date from the year-less printed dates.

    The release prints '22-Jun' with no year. The year is seeded from the
    release date, falling back to the received stamp, then to today.
    """
    columns = document.get("schedule_columns") or []
    if not columns:
        return document

    seed = _seed_year(document.get("release_date"), document.get("received_at"))
    if seed is None:
        seed = date.today().year

    for field, raw_field in (("ship_date", "raw_ship_date"),
                             ("delivery_date", "raw_delivery_date")):
        raws = [(c or {}).get(raw_field) for c in columns]
        for column, derived in zip(columns, _walk_forward(raws, seed)):
            # Never overwrite a date the document itself spelled out in full.
            if column.get(field) is None:
                column[field] = derived

    return document


def _align_quantities(document: Dict[str, Any]) -> None:
    """Pad or trim each part's quantity row to the width of the schedule.

    This repairs the shape so the review grid renders, and does nothing to hide
    the problem: us_validation_service.sa_schedule_width_match still has to
    pass on the model's own output, and the padding is recorded so a reviewer
    sees which row was short.
    """
    width = len(document.get("schedule_columns") or [])
    if not width:
        return

    for part in document.get("parts") or []:
        quantities = part.get("quantities")
        if not isinstance(quantities, list):
            quantities = []
        if len(quantities) < width:
            part["quantities_repaired"] = f"padded from {len(quantities)} to {width}"
            quantities = quantities + [None] * (width - len(quantities))
        elif len(quantities) > width:
            part["quantities_repaired"] = f"trimmed from {len(quantities)} to {width}"
            quantities = quantities[:width]
        part["quantities"] = quantities


def normalize_us_payload(raw: Dict[str, Any], doc_type: str,
                         document_id: str = "") -> Dict[str, Any]:
    """Coerce an agent response into the envelope the pipeline reads.

    Everything downstream -- review_routes, the export builders, the validation
    rules -- reads the document out of invoice_json["invoice"]. A prompt that
    answered with a different top-level key would otherwise render a blank
    review form with no error at all, so the aliases are absorbed here.
    """
    payload = dict(raw or {})

    document = None
    for key in ("invoice", "document", "us_document", "sa", "so"):
        candidate = payload.pop(key, None)
        if isinstance(candidate, dict) and document is None:
            document = candidate
    if document is None:
        # The agent returned the document itself with no envelope at all.
        known = {"confidence", "metadata", "validation", "document_id"}
        document = {k: v for k, v in payload.items() if k not in known}
        payload = {k: v for k, v in payload.items() if k in known}

    document.setdefault("document_type", doc_type)
    if doc_type == DOC_TYPE_SA:
        document = derive_schedule_dates(document)
        _align_quantities(document)

    payload["invoice"] = document
    payload["document_id"] = document_id or payload.get("document_id", "")
    payload.setdefault("confidence", {})
    return payload
