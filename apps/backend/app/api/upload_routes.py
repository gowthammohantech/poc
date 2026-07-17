import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

from app.schemas.document_schema import DocumentCreate, UploadResponse
from app.services import file_storage_service as storage
from app.services import document_service as docs
from app.services.convert_service import convert_to_pages
from app.services.preprocess_service import preprocess_pages
from app.services.complexity_service import analyze_complexity

router = APIRouter()

ALLOWED_MIME = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/tiff", "image/bmp", "image/heic", "image/heif",
    "image/heic-sequence", "image/heif-sequence",
}


@router.post("/upload", response_model=UploadResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    expected_fields: str = Form(None),
    must_use_llm: bool = Form(False),
):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".heic", ".heif"}:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    doc_data = DocumentCreate(
        filename=file.filename or "upload",
        original_path="",
        mime_type=content_type,
        expected_fields=expected_fields,
        must_use_llm=must_use_llm,
    )
    document_id = await docs.create_document(doc_data)
    await docs.log_step(document_id, "UPLOAD", "SUCCESS", "File received")

    # Save original file
    await docs.update_document_status(document_id, "SAVING")
    original_path = await storage.save_upload(document_id, file)
    await docs.update_document_status(document_id, "SAVED", original_path=original_path)
    await docs.log_step(document_id, "SAVE_FILE", "SUCCESS", f"Saved to {original_path}")

    # Convert to pages
    await docs.update_document_status(document_id, "CONVERTING")
    try:
        page_dir = storage.get_page_dir(document_id)
        page_paths = convert_to_pages(original_path, page_dir)
        await docs.log_step(document_id, "CONVERT", "SUCCESS", f"{len(page_paths)} page(s) created")
    except Exception as e:
        await docs.update_document_status(document_id, "FAILED")
        await docs.log_step(document_id, "CONVERT", "FAILED", str(e))
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")

    # Preprocess pages
    await docs.update_document_status(document_id, "PREPROCESSING")
    try:
        preprocessed_dir = storage.get_preprocessed_dir(document_id)
        preprocessed_paths = preprocess_pages(page_paths, preprocessed_dir)
    except Exception as e:
        preprocessed_paths = page_paths
        await docs.log_step(document_id, "PREPROCESS", "WARNING", str(e))

    # Save page records
    for i, (orig, prep) in enumerate(zip(page_paths, preprocessed_paths), start=1):
        await docs.add_page(document_id, i, orig, prep)
    await docs.update_document_status(document_id, "PREPROCESSED", page_count=len(page_paths))
    await docs.log_step(document_id, "PREPROCESS", "SUCCESS", f"{len(page_paths)} page(s) preprocessed")

    # Complexity analysis
    await docs.update_document_status(document_id, "ANALYZING_COMPLEXITY")
    try:
        complexity = analyze_complexity(preprocessed_paths)
        await docs.update_document_status(
            document_id, "COMPLEXITY_ANALYZED",
            complexity_score=complexity["score"],
            complexity_level=complexity["level"],
            complexity_reasons=json.dumps(complexity["reasons"]),
        )
        await docs.log_step(document_id, "COMPLEXITY", "SUCCESS",
                            f"Score: {complexity['score']}, Level: {complexity['level']}")
    except Exception as e:
        complexity = {"score": 50, "level": "MEDIUM", "reasons": []}
        await docs.log_step(document_id, "COMPLEXITY", "WARNING", str(e))

    return UploadResponse(
        document_id=document_id,
        filename=file.filename or "upload",
        status="COMPLEXITY_ANALYZED",
        page_count=len(page_paths),
        complexity_score=complexity["score"],
        complexity_level=complexity["level"],
        message="Upload, conversion, preprocessing, and complexity analysis complete. Call /process to start OCR.",
    )
