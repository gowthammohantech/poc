from fastapi import APIRouter, HTTPException

from app.services import brs_document_service as docs
from app.services import brs_mastra_client
from app.services.brs_validation_service import run_all_brs_rules, determine_brs_validation_status
from app.ocr_engines.tesseract_engine import run_tesseract

router = APIRouter()


@router.get("")
async def list_brs_documents():
    return await docs.get_all_documents()


@router.get("/{document_id}")
async def get_brs_document(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")
    return doc


@router.get("/{document_id}/pages")
async def get_brs_pages(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")
    return await docs.get_pages(document_id)


@router.post("/{document_id}/process")
async def process_brs_document(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    pages = await docs.get_pages(document_id)
    if not pages:
        raise HTTPException(status_code=400, detail="No pages found. Upload the document first.")

    preprocessed_paths = [p["preprocessed_path"] or p["original_path"] for p in pages]

    # Step 1: Tesseract OCR to extract raw text as a reference signal
    await docs.update_document_status(document_id, "EXTRACTING")
    try:
        ocr_result = run_tesseract(preprocessed_paths)
        ocr_text = ocr_result.get("text", "")
        ocr_confidence = ocr_result.get("confidence", 0.0)
        await docs.log_step(
            document_id, "OCR", "SUCCESS",
            f"Tesseract confidence: {ocr_confidence:.1f}%, words: {ocr_result.get('word_count', 0)}",
            details={"engine": "TESSERACT", "confidence": ocr_confidence},
        )
    except Exception as e:
        ocr_text = ""
        ocr_confidence = 0.0
        await docs.log_step(document_id, "OCR", "WARNING", f"Tesseract failed, continuing vision-only: {e}")

    # Step 2: Hybrid extraction — pass OCR text + images to vision agent
    await docs.log_step(document_id, "EXTRACTION", "STARTED", "Calling BRS direct vision agent")

    brs_json = await brs_mastra_client.call_brs_direct_vision_agent({
        "document_id": document_id,
        "page_image_paths": preprocessed_paths,
        "ocr_text": ocr_text,
    })

    if not brs_json:
        brs_json = {}

    # Stamp document_id and metadata
    brs_json["document_id"] = document_id
    brs_json.setdefault("metadata", {})
    brs_json["metadata"]["processing_mode"] = "HYBRID_OCR_VISION"
    brs_json["metadata"]["ocr_confidence"] = ocr_confidence
    brs_json["metadata"]["pages"] = len(pages)

    confidence_json = brs_json.get("confidence", {})
    await docs.save_extraction_result(document_id, brs_json, confidence_json)
    await docs.update_document_status(document_id, "EXTRACTED", processing_mode="HYBRID_OCR_VISION")
    await docs.log_step(document_id, "EXTRACTION", "SUCCESS", "BRS vision extraction complete")

    # Step 2: Rule-based validation
    await docs.update_document_status(document_id, "VALIDATING")
    rule_checks = run_all_brs_rules(brs_json)
    rule_checks_dicts = [c.to_dict() for c in rule_checks]

    # Step 3: LLM validation
    llm_val = await brs_mastra_client.call_brs_validation_agent({
        "document_id": document_id,
        "brs_json": brs_json,
    })
    llm_checks = llm_val.get("llm_checks", [])
    llm_warnings = llm_val.get("warnings", [])

    critical_rules = {"bank_balance_math", "book_balance_math", "balances_reconcile"}
    warnings = [
        c.message for c in rule_checks if not c.passed and c.rule not in critical_rules
    ] + llm_warnings
    errors = [c.message for c in rule_checks if not c.passed and c.rule in critical_rules]

    val_status = determine_brs_validation_status(rule_checks, llm_checks)

    await docs.save_validation_result(document_id, val_status, rule_checks_dicts, llm_checks, warnings, errors)
    await docs.update_document_status(document_id, val_status)
    await docs.log_step(document_id, "VALIDATION", "SUCCESS", f"BRS validation status: {val_status}")

    return {
        "document_id": document_id,
        "status": val_status,
        "processing_mode": "HYBRID_OCR_VISION",
        "message": "BRS extraction and validation complete. Review the extracted data.",
    }
