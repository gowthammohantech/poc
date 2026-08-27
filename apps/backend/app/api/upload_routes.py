from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.schemas.document_schema import UploadResponse
from app.services import ingest_service

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    expected_fields: str = Form(None),
    must_use_llm: bool = Form(False),
    source: str = Form(ingest_service.SOURCE_MANUAL),
):
    try:
        result = await ingest_service.ingest_upload_file(
            file,
            expected_fields=expected_fields,
            must_use_llm=must_use_llm,
            source=source,
        )
    except ingest_service.IngestError as e:
        if e.stage == "VALIDATE":
            raise HTTPException(status_code=400, detail=e.message)
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e.message}")

    return UploadResponse(
        document_id=result.document_id,
        filename=result.filename,
        status=result.status,
        page_count=result.page_count,
        complexity_score=result.complexity_score,
        complexity_level=result.complexity_level,
        message="Upload, conversion, preprocessing, and complexity analysis complete. Call /process to start OCR.",
    )
