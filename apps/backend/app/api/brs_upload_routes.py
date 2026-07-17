from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException

from app.schemas.brs_schema import BrsDocumentCreate, BrsUploadResponse
from app.services import file_storage_service as storage
from app.services import brs_document_service as docs
from app.services.convert_service import convert_to_pages
from app.services.preprocess_service import preprocess_pages

router = APIRouter()

ALLOWED_MIME = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/tiff", "image/bmp", "image/heic", "image/heif",
    "image/heic-sequence", "image/heif-sequence",
}


@router.post("/upload", response_model=BrsUploadResponse)
async def upload_brs(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".heic", ".heif"}:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    doc_data = BrsDocumentCreate(
        filename=file.filename or "upload",
        original_path="",
        mime_type=content_type,
    )
    document_id = await docs.create_document(doc_data)
    await docs.log_step(document_id, "UPLOAD", "SUCCESS", "BRS file received")

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

    for i, (orig, prep) in enumerate(zip(page_paths, preprocessed_paths), start=1):
        await docs.add_page(document_id, i, orig, prep)

    await docs.update_document_status(document_id, "PREPROCESSED", page_count=len(page_paths))
    await docs.log_step(document_id, "PREPROCESS", "SUCCESS", f"{len(page_paths)} page(s) preprocessed")

    return BrsUploadResponse(
        document_id=document_id,
        filename=file.filename or "upload",
        status="PREPROCESSED",
        page_count=len(page_paths),
        message="Upload and preprocessing complete. Call /process to start BRS extraction.",
    )
