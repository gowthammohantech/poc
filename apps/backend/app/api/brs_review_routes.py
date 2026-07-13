from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from app.services import brs_document_service as docs

router = APIRouter()


@router.get("/{document_id}/review")
async def get_brs_review(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    pages = await docs.get_pages(document_id)
    extraction = await docs.get_extraction_result(document_id)
    validation = await docs.get_validation_result(document_id)

    page_urls = []
    for p in pages:
        path = (p.get("preprocessed_path") or p.get("original_path") or "").replace("\\", "/")
        if "storage/uploads" in path:
            rel = path[path.index("storage/uploads"):]
            page_urls.append(f"/{rel}")
        else:
            page_urls.append(path)

    brs_json = extraction.get("brs_json", {}) if extraction else {}
    brs_data = brs_json.get("brs", brs_json)

    return {
        "document_id": document_id,
        "status": doc.get("status"),
        "page_urls": page_urls,
        "brs": brs_data,
        "confidence": extraction.get("confidence_json", {}) if extraction else {},
        "validation": {
            "status": validation.get("status") if validation else "PENDING",
            "rule_checks": validation.get("rule_checks_json", []) if validation else [],
            "llm_checks": validation.get("llm_checks_json", []) if validation else [],
            "warnings": validation.get("warnings_json", []) if validation else [],
            "errors": validation.get("errors_json", []) if validation else [],
        },
    }


class BrsReviewSubmitRequest(BaseModel):
    corrected_brs: Dict[str, Any]


@router.post("/{document_id}/review/submit")
async def submit_brs_review(document_id: str, body: BrsReviewSubmitRequest):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    extraction = await docs.get_extraction_result(document_id)
    validation = await docs.get_validation_result(document_id)

    full_output = {
        "document_id": document_id,
        "brs": body.corrected_brs,
        "confidence": extraction.get("confidence_json", {}) if extraction else {},
        "validation": {
            "status": validation.get("status") if validation else "PENDING",
            "rule_checks": validation.get("rule_checks_json", []) if validation else [],
            "llm_checks": validation.get("llm_checks_json", []) if validation else [],
            "warnings": validation.get("warnings_json", []) if validation else [],
            "errors": validation.get("errors_json", []) if validation else [],
        },
        "metadata": extraction.get("brs_json", {}).get("metadata", {}) if extraction else {},
    }

    await docs.save_final_output(document_id, full_output)
    await docs.update_document_status(document_id, "COMPLETED")
    await docs.log_step(document_id, "REVIEW_SUBMIT", "SUCCESS", "User submitted corrected BRS output")

    return {"document_id": document_id, "status": "COMPLETED", "message": "BRS review submitted and saved."}
