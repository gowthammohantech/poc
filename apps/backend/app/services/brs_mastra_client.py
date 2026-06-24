import os
import json
import re
import base64
from datetime import date
from pathlib import Path
from typing import Dict, Any, List
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
