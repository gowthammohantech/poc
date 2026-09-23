"""The OCR → extraction → validation pipeline, callable without going via HTTP.

Lifted out of the /process route so connector syncs can drive it in-process
rather than making the server call itself over the network.
"""

import json

from starlette.concurrency import run_in_threadpool

from app.services import document_service as docs
from app.services import file_storage_service as storage
from app.services import mastra_client
from app.services import us_mastra_client
from app.services.ocr_service import run_ocr_with_fallback
from app.services.validation_rulesets import COUNTRY_USA, get_ruleset
from app.services.validation_service import run_all_rules, determine_validation_status


class ProcessingError(Exception):
    """Raised when a document cannot be processed. `not_found` maps to a 404."""

    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.message = message
        self.not_found = not_found


async def run_processing_pipeline(document_id: str) -> dict:
    doc = await docs.get_document(document_id)
    if not doc:
        raise ProcessingError("Document not found", not_found=True)

    pages = await docs.get_pages(document_id)
    if not pages:
        raise ProcessingError("No pages found. Upload the document first.")

    # Mongo points at files this container may never have seen -- a redeploy
    # starts with an empty cache -- so each one is faulted in from Blob first.
    preprocessed_paths = await storage.ensure_local_many(
        [p["preprocessed_path"] or p["original_path"] for p in pages]
    )
    complexity_reasons = json.loads(doc["complexity_reasons"] or "[]") if doc.get("complexity_reasons") else []

    if (doc.get("country") or "INDIA").upper() == COUNTRY_USA:
        return await _run_us_pipeline(document_id, doc, pages)

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
        # Step 2a: Local OCR. Tesseract and PaddleOCR are blocking and
        # CPU-bound, so they run off the event loop.
        await docs.update_document_status(document_id, "OCR_RUNNING")
        ocr_result, final_engine = await run_in_threadpool(
            run_ocr_with_fallback, selected_engine, preprocessed_paths
        )

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

    ruleset = get_ruleset(doc.get("country"), doc.get("doc_type"))

    async def validate_extraction(candidate: dict):
        rule_checks = ruleset.run(candidate)
        rule_checks_dicts = [c.dict() for c in rule_checks]
        llm_val = await mastra_client.call_validation_agent({
            "document_id": document_id,
            "invoice_json": candidate,
        })
        llm_checks = llm_val.get("llm_checks", [])
        llm_warnings = llm_val.get("warnings", [])
        warnings, errors = ruleset.partition_messages(rule_checks)
        return (
            rule_checks_dicts,
            llm_checks,
            warnings + llm_warnings,
            errors,
            ruleset.determine_status(rule_checks, llm_checks),
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


async def _run_us_pipeline(document_id: str, doc: dict, pages: list) -> dict:
    """OCR → classify → extract → validate, for a US purchase order, release or invoice.

    Kept as its own function rather than a set of conditionals threaded through
    the India body above: the two regimes share the persistence calls and
    nothing else, and a regression in the India path is the expensive kind.

    Three deliberate differences from the India pipeline:

      * The router agent is skipped and vision is always used. All US
        documents are dense tables whose meaning lives in the column a number
        sits in, and Tesseract runs --psm 6, which reads a grid as one
        paragraph and throws that away. A misread digit on an order line is
        also unrecoverable arithmetic rather than a typo.
      * The page images sent to the agent are the originals, not the
        preprocessed ones. Preprocessing binarises for Tesseract's benefit,
        which on a wide table can thin out the hairline rules that carry the
        column alignment.
      * There is no vision-retry-on-INVALID leg. That exists to escalate a
        local-OCR result to vision; this path already started there.
    """
    # Mongo points at files this container may never have seen -- a redeploy
    # starts with an empty cache -- so each one is faulted in from Blob first.
    original_paths = await storage.ensure_local_many(
        [p["original_path"] for p in pages if p.get("original_path")]
    )
    ocr_paths = await storage.ensure_local_many(
        [p["preprocessed_path"] or p["original_path"] for p in pages]
    )
    vision_paths = original_paths or ocr_paths

    final_engine = "OPENAI_VISION_LLM"
    processing_mode = "DIRECT_LLM_WITH_OCR_REFERENCE"

    await docs.update_document_status(document_id, "ROUTING")
    await docs.update_document_status(document_id, "ROUTED", ocr_engine=final_engine)
    await docs.log_step(
        document_id, "ROUTING", "SUCCESS",
        f"Engine: {final_engine}, Reason: US documents are wide tables where "
        f"column position carries the meaning; routed to vision regardless of score",
    )

    # Tesseract runs for two reasons that both survive its poor grasp of the
    # layout: it gives the review screen its word boxes, and its text is a
    # useful second opinion on a digit the model is unsure of.
    ocr_text = ""
    await docs.update_document_status(document_id, "OCR_RUNNING")
    try:
        ocr_result, ocr_engine = await run_in_threadpool(
            run_ocr_with_fallback, "TESSERACT", ocr_paths
        )
        ocr_text = ocr_result.get("text", "") or ""
        await docs.save_ocr_result(
            document_id, ocr_engine, ocr_text,
            ocr_result.get("confidence", 0), ocr_result.get("word_count", 0),
            ocr_result.get("metadata", {}),
        )
        await docs.log_step(document_id, "OCR", "SUCCESS",
                            f"Reference text from {ocr_engine}: {len(ocr_text)} chars")
    except Exception as e:
        await docs.log_step(document_id, "OCR", "WARNING",
                            f"Reference OCR failed, continuing with images only: {e}")

    # Classify, unless a reviewer already told us what this is and re-processed.
    doc_type = doc.get("doc_type")
    if not doc_type:
        await docs.update_document_status(document_id, "CLASSIFYING")
        classification = await us_mastra_client.call_us_doc_classifier({
            "document_id": document_id,
            "page_image_paths": vision_paths,
            "ocr_text": ocr_text,
        })
        doc_type = classification.get("document_type", us_mastra_client.DOC_TYPE_UNKNOWN)
        await docs.update_document_status(document_id, "CLASSIFIED", doc_type=doc_type)
        await docs.log_step(
            document_id, "US_CLASSIFY", "SUCCESS",
            f"Type: {doc_type} (confidence {classification.get('confidence', 0)}). "
            f"{classification.get('reason', '')}",
        )

    await docs.update_document_status(document_id, "EXTRACTING")
    extraction_payload = {
        "document_id": document_id,
        "page_image_paths": vision_paths,
        "ocr_text": ocr_text,
        "expected_fields": doc.get("expected_fields", ""),
    }
    # An unclassified document is read as a purchase order: that degrades to a
    # mostly-empty form a reviewer can correct, rather than a matrix whose
    # columns are silently misaligned.
    if doc_type == us_mastra_client.DOC_TYPE_SA:
        raw = await us_mastra_client.call_us_sa_vision_agent(extraction_payload)
    elif doc_type == us_mastra_client.DOC_TYPE_INV:
        raw = await us_mastra_client.call_us_inv_vision_agent(extraction_payload)
    else:
        raw = await us_mastra_client.call_us_so_vision_agent(extraction_payload)

    document_json = us_mastra_client.normalize_us_payload(raw, doc_type, document_id)
    document_json.setdefault("metadata", {})
    document_json["metadata"].update({
        "ocr_engine": final_engine,
        "processing_mode": processing_mode,
        "complexity_score": doc.get("complexity_score"),
        "pages": len(pages),
        "country": COUNTRY_USA,
        "document_type": doc_type,
    })
    confidence_json = document_json.get("confidence", {})

    await docs.save_extraction_result(document_id, document_json, confidence_json)
    await docs.update_document_status(document_id, "EXTRACTED",
                                      ocr_engine=final_engine, processing_mode=processing_mode)
    await docs.log_step(document_id, "EXTRACTION", "SUCCESS",
                        f"Extracted as {doc_type} via {final_engine}")

    await docs.update_document_status(document_id, "VALIDATING")
    ruleset = get_ruleset(COUNTRY_USA, doc_type)
    rule_checks = ruleset.run(document_json)
    llm_val = await us_mastra_client.call_us_validation_agent({
        "document_id": document_id,
        "document_type": doc_type,
        "document_json": document_json,
    })
    llm_checks = llm_val.get("llm_checks", [])
    warnings, errors = ruleset.partition_messages(rule_checks)
    warnings = warnings + llm_val.get("warnings", [])
    val_status = ruleset.determine_status(rule_checks, llm_checks)

    rule_checks_dicts = [c.dict() for c in rule_checks]
    await docs.save_validation_result(document_id, val_status, rule_checks_dicts,
                                      llm_checks, warnings, errors)
    document_json["validation"] = {
        "status": val_status,
        "rule_checks": rule_checks_dicts,
        "llm_checks": llm_checks,
        "warnings": warnings,
        "errors": errors,
    }
    await docs.save_extraction_result(document_id, document_json, confidence_json)
    await docs.update_document_status(document_id, val_status)
    await docs.log_step(document_id, "VALIDATION", "SUCCESS", f"Status: {val_status}")

    return {
        "document_id": document_id,
        "status": val_status,
        "doc_type": doc_type,
        "ocr_engine": final_engine,
        "processing_mode": processing_mode,
        "message": f"US {doc_type} processing complete. Status: {val_status}",
    }
