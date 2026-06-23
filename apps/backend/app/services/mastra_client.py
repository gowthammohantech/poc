import os
import json
import re
import base64
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

MASTRA_URL = os.getenv("MASTRA_SERVICE_URL", "http://localhost:4111")
TIMEOUT = 120.0


def _parse_agent_text(response_json: dict) -> str:
    """Extract text content from Mastra agent response."""
    # Mastra returns {text: "...", ...} or {messages: [{content: "..."}]}
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
    """Extract JSON from agent response text, handling markdown code blocks."""
    # Try direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def call_ocr_router(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        f"Route this invoice to the correct OCR engine.\n\n"
        f"complexity_score: {payload.get('complexity_score')}\n"
        f"complexity_level: {payload.get('complexity_level')}\n"
        f"reasons: {payload.get('reasons', [])}\n"
        f"page_count: {payload.get('page_count')}\n"
        f"must_use_llm: {payload.get('must_use_llm')}\n"
        f"expected_fields: {payload.get('expected_fields', [])}\n\n"
        f"Return JSON: {{\"engine\": \"TESSERACT|PADDLEOCR|OPENAI_VISION_LLM\", \"reason\": \"string\"}}"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/invoiceOcrRouterAgent/generate",
                json={"messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            result = _extract_json_from_text(text)
            if "engine" not in result:
                result = _fallback_route(payload)
            return result
    except Exception:
        return _fallback_route(payload)


def _fallback_route(payload: dict) -> dict:
    if payload.get("must_use_llm"):
        return {"engine": "OPENAI_VISION_LLM", "reason": "must_use_llm flag set"}
    score = payload.get("complexity_score", 50)
    if score <= 40:
        return {"engine": "TESSERACT", "reason": "low complexity"}
    elif score <= 75:
        return {"engine": "PADDLEOCR", "reason": "medium complexity"}
    else:
        return {"engine": "OPENAI_VISION_LLM", "reason": "high complexity"}


async def call_extraction_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        f"Extract structured invoice data from this OCR text.\n\n"
        f"Document ID: {payload.get('document_id')}\n"
        f"Expected fields: {payload.get('expected_fields', [])}\n\n"
        f"OCR Text:\n{payload.get('ocr_text', '')}\n\n"
        f"Return the complete invoice JSON following the schema exactly. "
        f"Use null for missing values. Never hallucinate values."
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/invoiceExtractionAgent/generate",
                json={"messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            return _extract_json_from_text(text)
    except Exception:
        return {}


async def call_direct_vision_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    image_paths: List[str] = payload.get("page_image_paths", [])
    document_id: str = payload.get("document_id", "")
    expected_fields = payload.get("expected_fields", [])

    # Build content with base64-encoded images
    content_parts = [
        {
            "type": "text",
            "text": (
                f"Extract structured invoice data from these invoice page images.\n"
                f"Document ID: {document_id}\n"
                f"Expected fields: {expected_fields}\n"
                f"Return the complete invoice JSON following the schema exactly. "
                f"Use null for missing values. Never hallucinate values. "
                f"Preserve exact invoice numbers, GSTINs, PAN, account numbers, and IFSC codes."
            )
        }
    ]

    for path in image_paths[:5]:  # Limit to 5 pages to stay within token limits
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
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/directVisionInvoiceAgent/generate",
                json={"messages": [{"role": "user", "content": content_parts}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            return _extract_json_from_text(text)
    except Exception:
        return {}


async def call_validation_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = (
        f"Validate this extracted invoice data for accuracy and completeness.\n\n"
        f"Document ID: {payload.get('document_id')}\n\n"
        f"Today's date: {date.today().isoformat()}\n\n"
        f"Invoice JSON:\n{json.dumps(payload.get('invoice_json', {}), indent=2)}\n\n"
        f"Return JSON: {{\"llm_checks\": [{{\"check\": str, \"result\": \"PASS|FAIL|UNCERTAIN\", "
        f"\"confidence\": 0-1, \"message\": str, \"field\": str|null}}], "
        f"\"warnings\": [str], \"confidence_adjustments\": {{field: delta}}}}"
    )
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(
                f"{MASTRA_URL}/api/agents/invoiceValidationAgent/generate",
                json={"messages": [{"role": "user", "content": prompt}]},
            )
            r.raise_for_status()
            text = _parse_agent_text(r.json())
            return _extract_json_from_text(text)
    except Exception:
        return {"llm_checks": [], "warnings": [], "confidence_adjustments": {}}
