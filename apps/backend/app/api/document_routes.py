import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException

from app.services import document_service as docs
from app.services import mastra_client
from app.services.ocr_service import run_ocr_with_fallback
from app.services.validation_service import run_all_rules, determine_validation_status

router = APIRouter()


# Intermediate states the pipeline passes through; a row parked in one of these
# is either still processing or was abandoned mid-run, so it is not listed.
IN_PROGRESS_STATUSES = {"VALIDATING", "COMPLEXITY_ANALYZED"}


@router.get("")
async def list_documents():
    """List processed documents, newest run per filename only."""
    rows = await docs.get_all_documents()  # already ordered created_at DESC
    seen_filenames = set()
    result = []
    for row in rows:
        if row.get("status") in IN_PROGRESS_STATUSES:
            continue
        filename = row.get("filename")
        if filename in seen_filenames:
            continue
        seen_filenames.add(filename)
        result.append(row)
    return result


@router.get("/{document_id}")
async def get_document(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/pages")
async def get_pages(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    pages = await docs.get_pages(document_id)
    return pages


@router.post("/{document_id}/process")
async def process_document(document_id: str):
    doc = await docs.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await docs.get_pages(document_id)
    if not pages:
        raise HTTPException(status_code=400, detail="No pages found. Upload the document first.")

    preprocessed_paths = [p["preprocessed_path"] or p["original_path"] for p in pages]
    complexity_reasons = json.loads(doc["complexity_reasons"] or "[]") if doc.get("complexity_reasons") else []

    # Step 1: OCR Routing via Mastra
    await docs.update_document_status(document_id, "ROUTING")
    router_payload = {
        "complexity_score": doc.get("complexity_score", 50),
        "complexity_level": doc.get("complexity_level", "MEDIUM"),
        "reasons": complexity_reasons,
        "page_count": doc.get("page_count", len(pages)),
        "must_use_llm": bool(doc.get("must_use_llm", 0)),
        "expected_fields": doc.get("expected_fields", ""),
    }
    route_result = await mastra_client.call_ocr_router(router_payload)
    selected_engine = route_result.get("engine", "TESSERACT")
    route_reason = route_result.get("reason", "")

    await docs.update_document_status(document_id, "ROUTED", ocr_engine=selected_engine)
    await docs.log_step(document_id, "ROUTING", "SUCCESS",
                        f"Engine: {selected_engine}, Reason: {route_reason}")

    invoice_json = {}
    confidence_json = {}
    final_engine = selected_engine
    processing_mode = "OCR_THEN_LLM"

    if selected_engine in ("TESSERACT", "PADDLEOCR"):
        # Step 2a: Local OCR
        await docs.update_document_status(document_id, "OCR_RUNNING")
        ocr_result, final_engine = run_ocr_with_fallback(selected_engine, preprocessed_paths)

        if ocr_result.get("low_confidence") or not ocr_result.get("text", "").strip():
            # All local OCR failed — escalate to LLM
            # Preserve its spatial references for the review screen even when
            # vision extraction becomes the authoritative result.
            await docs.save_ocr_result(
                document_id, final_engine,
                ocr_result.get("text", ""), ocr_result.get("confidence", 0.0),
                ocr_result.get("word_count", 0), ocr_result.get("metadata", {})
            )
            await docs.log_step(document_id, "OCR", "WARNING",
                                 "Local OCR low confidence, escalating to OpenAI Vision")
            final_engine = "OPENAI_VISION_LLM"
            processing_mode = "DIRECT_LLM"
        else:
            # Save OCR result
            await docs.save_ocr_result(
                document_id, final_engine,
                ocr_result["text"], ocr_result["confidence"],
                ocr_result["word_count"], ocr_result["metadata"]
            )
            await docs.log_step(document_id, "OCR", "SUCCESS",
                                 f"Engine: {final_engine}, Confidence: {ocr_result['confidence']:.1f}")

            # Step 2b: Extraction via Mastra
            await docs.update_document_status(document_id, "EXTRACTING")
            extraction_payload = {
                "document_id": document_id,
                "ocr_text": ocr_result["text"],
                "expected_fields": doc.get("expected_fields", ""),
            }
            # Moderate and complex documents benefit from the page image as a
            # second source of truth for tables, handwritten marks, and layouts.
            if (doc.get("complexity_score") or 0) > 40:
                extraction_payload["page_image_paths"] = preprocessed_paths
                processing_mode = "OCR_THEN_LLM_WITH_VISION"
            invoice_json = await mastra_client.call_extraction_agent(extraction_payload)
            await docs.log_step(document_id, "EXTRACTION", "SUCCESS",
                                 f"Extracted via {final_engine} → LLM"
                                 f"{' with page images' if extraction_payload.get('page_image_paths') else ''}")

    if final_engine == "OPENAI_VISION_LLM" or processing_mode == "DIRECT_LLM":
        # Step 2c: Direct Vision extraction
        await docs.update_document_status(document_id, "EXTRACTING")
        processing_mode = "DIRECT_LLM"
        vision_payload = {
            "document_id": document_id,
            "page_image_paths": preprocessed_paths,
            "expected_fields": doc.get("expected_fields", ""),
        }
        invoice_json = await mastra_client.call_direct_vision_agent(vision_payload)
        await docs.log_step(document_id, "DIRECT_VISION_EXTRACTION", "SUCCESS",
                             "Extracted via OpenAI Vision")

    # Ensure document_id is set
    if not invoice_json:
        invoice_json = {}
    invoice_json["document_id"] = document_id
    invoice_json.setdefault("metadata", {})
    invoice_json["metadata"]["ocr_engine"] = final_engine
    invoice_json["metadata"]["processing_mode"] = processing_mode
    invoice_json["metadata"]["complexity_score"] = doc.get("complexity_score")
    invoice_json["metadata"]["pages"] = len(pages)

    # Save extraction result
    confidence_json = invoice_json.get("confidence", {})
    await docs.save_extraction_result(document_id, invoice_json, confidence_json)
    await docs.update_document_status(document_id, "EXTRACTED",
                                       ocr_engine=final_engine, processing_mode=processing_mode)

    async def validate_extraction(candidate: dict):
        rule_checks = run_all_rules(candidate)
        rule_checks_dicts = [c.dict() for c in rule_checks]
        llm_val = await mastra_client.call_validation_agent({
            "document_id": document_id,
            "invoice_json": candidate,
        })
        llm_checks = llm_val.get("llm_checks", [])
        llm_warnings = llm_val.get("warnings", [])
        warnings = [c.message for c in rule_checks if not c.passed and c.rule not in (
            "invoice_number_present", "invoice_date_valid", "total_math_check"
        )] + llm_warnings
        errors = [c.message for c in rule_checks if not c.passed and c.rule in (
            "invoice_number_present", "invoice_date_valid", "total_math_check"
        )]
        return (
            rule_checks_dicts,
            llm_checks,
            warnings,
            errors,
            determine_validation_status(rule_checks, llm_checks),
        )

    # Step 3: validate the local-OCR extraction first.
    await docs.update_document_status(document_id, "VALIDATING")
    rule_checks_dicts, llm_checks, warnings, errors, val_status = await validate_extraction(invoice_json)

    # A deterministic INVALID result means required invoice data is missing or
    # inconsistent. Give the vision model one image-based recovery attempt.
    # Do not retry an extraction that already came from direct vision.
    if val_status == "INVALID" and final_engine != "OPENAI_VISION_LLM":
        await docs.log_step(
            document_id, "VISION_RETRY", "WARNING",
            "Initial OCR extraction was invalid; retrying with OpenAI Vision page images",
        )
        await docs.update_document_status(document_id, "EXTRACTING")
        retried_invoice = await mastra_client.call_direct_vision_agent({
            "document_id": document_id,
            "page_image_paths": preprocessed_paths,
            "expected_fields": doc.get("expected_fields", ""),
        })
        if retried_invoice:
            invoice_json = retried_invoice
            final_engine = "OPENAI_VISION_LLM"
            processing_mode = "DIRECT_LLM_RETRY_AFTER_INVALID"
            invoice_json["document_id"] = document_id
            invoice_json.setdefault("metadata", {})
            invoice_json["metadata"].update({
                "ocr_engine": final_engine,
                "processing_mode": processing_mode,
                "complexity_score": doc.get("complexity_score"),
                "pages": len(pages),
            })
            confidence_json = invoice_json.get("confidence", {})
            await docs.save_extraction_result(document_id, invoice_json, confidence_json)
            await docs.update_document_status(
                document_id, "EXTRACTED", ocr_engine=final_engine, processing_mode=processing_mode
            )
            await docs.update_document_status(document_id, "VALIDATING")
            rule_checks_dicts, llm_checks, warnings, errors, val_status = await validate_extraction(invoice_json)
            await docs.log_step(document_id, "VISION_RETRY", "SUCCESS", f"Retry status: {val_status}")
        else:
            await docs.log_step(document_id, "VISION_RETRY", "FAILED", "OpenAI Vision returned no extraction")

    await docs.save_validation_result(
        document_id, val_status, rule_checks_dicts, llm_checks, warnings, errors
    )

    # Update invoice validation block
    invoice_json["validation"] = {
        "status": val_status,
        "rule_checks": rule_checks_dicts,
        "llm_checks": llm_checks,
        "warnings": warnings,
        "errors": errors,
    }
    await docs.save_extraction_result(document_id, invoice_json, confidence_json)
    await docs.update_document_status(document_id, val_status)
    await docs.log_step(document_id, "VALIDATION", "SUCCESS", f"Status: {val_status}")

    return {
        "document_id": document_id,
        "status": val_status,
        "ocr_engine": final_engine,
        "processing_mode": processing_mode,
        "message": "Processing complete. Review the invoice data.",
    }
