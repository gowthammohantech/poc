import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Dict

from app.services import document_service as docs

router = APIRouter()


@router.get("/{document_id}/review")
async def get_review(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await docs.get_pages(document_id)
    extraction = await docs.get_extraction_result(document_id)
    validation = await docs.get_validation_result(document_id)
    ocr_result = await docs.get_ocr_result(document_id)

    page_urls = []
    for p in pages:
        path = p.get("preprocessed_path") or p.get("original_path") or ""
        # Convert local path to URL
        if "storage/uploads" in path:
            rel = path[path.index("storage/uploads"):]
            page_urls.append(f"/{rel}")
        else:
            page_urls.append(path)

    return {
        "document_id": document_id,
        "status": doc.get("status"),
        "page_urls": page_urls,
        # The extraction record is an envelope containing document metadata,
        # confidence, validation, and the actual form-ready invoice payload.
        "invoice": extraction.get("invoice_json", {}).get("invoice", {}) if extraction else {},
        "confidence": extraction.get("confidence_json", {}) if extraction else {},
        "ocr_reference": {
            "engine": ocr_result.get("engine"),
            "pages": ocr_result.get("metadata", {}).get("page_references", []),
        } if ocr_result else None,
        "validation": {
            "status": validation.get("status") if validation else "PENDING",
            "rule_checks": validation.get("rule_checks_json", []) if validation else [],
            "llm_checks": validation.get("llm_checks_json", []) if validation else [],
            "warnings": validation.get("warnings_json", []) if validation else [],
            "errors": validation.get("errors_json", []) if validation else [],
        },
    }


class ReviewSubmitRequest(BaseModel):
    corrected_invoice: Dict[str, Any]


@router.post("/{document_id}/review/submit")
async def submit_review(document_id: str, body: ReviewSubmitRequest):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    extraction = await docs.get_extraction_result(document_id)
    validation = await docs.get_validation_result(document_id)

    full_output = {
        "document_id": document_id,
        "invoice": body.corrected_invoice,
        "confidence": extraction.get("confidence_json", {}) if extraction else {},
        "validation": {
            "status": validation.get("status") if validation else "PENDING",
            "rule_checks": validation.get("rule_checks_json", []) if validation else [],
            "llm_checks": validation.get("llm_checks_json", []) if validation else [],
            "warnings": validation.get("warnings_json", []) if validation else [],
            "errors": validation.get("errors_json", []) if validation else [],
        },
        "metadata": extraction.get("invoice_json", {}).get("metadata", {}) if extraction else {},
    }

    await docs.save_final_output(document_id, full_output)
    await docs.update_document_status(document_id, "COMPLETED")
    await docs.log_step(document_id, "REVIEW_SUBMIT", "SUCCESS", "User submitted corrected output")

    return {"document_id": document_id, "status": "COMPLETED", "message": "Review submitted and saved."}
