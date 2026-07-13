from fastapi import APIRouter, HTTPException

from app.services import brs_document_service as docs
from app.services import ledger_service
from app.services.brs_validation_service import run_all_brs_rules, determine_brs_validation_status
from app.services.brs_matching_service import run_two_way_match
from app.services.brs_tesseract_table_service import (
    PROCESSING_MODE,
    extract_brs_from_tesseract_result,
)
from app.ocr_engines.tesseract_engine import run_tesseract
from app.services.brs_mastra_client import call_brs_direct_vision_agent

router = APIRouter()


async def _run_and_save_match(document_id: str) -> dict:
    extraction = await docs.get_extraction_result(document_id)
    brs_json = extraction.get("brs_json", {}) if extraction else {}
    brs_data = brs_json.get("brs", brs_json)
    bank_transactions = brs_data.get("bank_transactions", [])

    ledger_entries = await ledger_service.get_all_entries()

    match_report = run_two_way_match(bank_transactions, ledger_entries)
    await docs.save_match_result(document_id, match_report)
    return match_report


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
async def process_brs_document(document_id: str, processing_mode: str = "HYBRID_OCR_VISION"):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    pages = await docs.get_pages(document_id)
    if not pages:
        raise HTTPException(status_code=400, detail="No pages found. Upload the document first.")

    preprocessed_paths = [p["preprocessed_path"] or p["original_path"] for p in pages]

    # Step 1: Tesseract OCR with word coordinates for local table extraction.
    await docs.update_document_status(document_id, "EXTRACTING")
    try:
        ocr_result = run_tesseract(preprocessed_paths)
        ocr_confidence = ocr_result.get("confidence", 0.0)
        await docs.log_step(
            document_id, "OCR", "SUCCESS",
            f"Tesseract confidence: {ocr_confidence:.1f}%, words: {ocr_result.get('word_count', 0)}",
            details={"engine": "TESSERACT", "confidence": ocr_confidence},
        )
    except Exception as e:
        await docs.log_step(document_id, "OCR", "FAILED", f"Tesseract failed: {e}")
        raise HTTPException(status_code=500, detail=f"Tesseract OCR failed: {e}")

    # Step 2: Extraction (Hybrid OCR + Vision or Tesseract Table Only)
    if processing_mode == "HYBRID_OCR_VISION":
        await docs.log_step(document_id, "EXTRACTION", "STARTED", "Running Hybrid OCR + Vision extraction via Mastra Agent")
        try:
            brs_json = await call_brs_direct_vision_agent({
                "page_image_paths": preprocessed_paths,
                "document_id": document_id,
                "ocr_text": ocr_result.get("text", "")
            })
            if not brs_json or "brs" not in brs_json:
                raise ValueError("Mastra Direct Vision Agent returned invalid or empty response")
            
            # Ensure document_id is correct and metadata is set
            brs_json["document_id"] = document_id
            if "metadata" not in brs_json:
                brs_json["metadata"] = {}
            brs_json["metadata"].update({
                "processing_mode": "HYBRID_OCR_VISION",
                "ocr_confidence": ocr_result.get("confidence", 0.0),
                "pages": len(pages),
                "transaction_count": len(brs_json.get("brs", {}).get("bank_transactions", [])),
                "extraction_warnings": [],
            })
        except Exception as e:
            await docs.log_step(document_id, "EXTRACTION", "FAILED", f"Hybrid OCR + Vision extraction failed: {e}")
            raise HTTPException(status_code=500, detail=f"Hybrid OCR + Vision extraction failed: {e}")
    else:
        await docs.log_step(document_id, "EXTRACTION", "STARTED", "Parsing Tesseract table rows")
        brs_json = extract_brs_from_tesseract_result(ocr_result, document_id, len(pages))

    extraction_warnings = brs_json.get("metadata", {}).get("extraction_warnings", [])

    confidence_json = brs_json.get("confidence", {})
    await docs.save_extraction_result(document_id, brs_json, confidence_json)
    await docs.update_document_status(document_id, "EXTRACTED", processing_mode=processing_mode)
    await docs.log_step(
        document_id,
        "EXTRACTION",
        "SUCCESS",
        f"Extraction complete with {len(brs_json.get('brs', {}).get('bank_transactions', []))} transaction(s)",
        details={"processing_mode": processing_mode, "warnings": extraction_warnings},
    )

    # Step 3: Rule-based validation
    await docs.update_document_status(document_id, "VALIDATING")
    rule_checks = run_all_brs_rules(brs_json)
    rule_checks_dicts = [c.to_dict() for c in rule_checks]

    critical_rules = {"bank_balance_math", "book_balance_math", "balances_reconcile"}
    warnings = [
        c.message for c in rule_checks if not c.passed and c.rule not in critical_rules
    ] + extraction_warnings
    errors = [c.message for c in rule_checks if not c.passed and c.rule in critical_rules]
    llm_checks = []

    val_status = determine_brs_validation_status(rule_checks, llm_checks)

    await docs.save_validation_result(document_id, val_status, rule_checks_dicts, llm_checks, warnings, errors)
    await docs.update_document_status(document_id, val_status)
    await docs.log_step(document_id, "VALIDATION", "SUCCESS", f"BRS validation status: {val_status}")

    # Step 4: 2-way match extracted bank transactions against the dummy ledger.
    # Best-effort — an empty/misconfigured ledger should never fail the OCR pipeline.
    try:
        match_report = await _run_and_save_match(document_id)
        await docs.log_step(
            document_id, "MATCHING", "SUCCESS",
            f"2-way match: {match_report['summary']['matched']} matched, "
            f"{match_report['summary']['unmatched_bank']} unmatched bank, "
            f"{match_report['summary']['unmatched_ledger']} unmatched ledger",
        )
    except Exception as e:
        await docs.log_step(document_id, "MATCHING", "WARNING", f"2-way matching failed: {e}")

    return {
        "document_id": document_id,
        "status": val_status,
        "processing_mode": processing_mode,
        "message": "BRS extraction and validation complete. Review the extracted data.",
    }


@router.post("/{document_id}/match")
async def match_brs_document(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    extraction = await docs.get_extraction_result(document_id)
    if not extraction:
        raise HTTPException(status_code=400, detail="Document has not been processed yet.")

    match_report = await _run_and_save_match(document_id)
    return match_report


@router.get("/{document_id}/match")
async def get_brs_match(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="BRS document not found")

    result = await docs.get_match_result(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="No match results yet. Run matching first.")
    return result["match_json"]
