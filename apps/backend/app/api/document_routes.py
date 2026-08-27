from fastapi import APIRouter, HTTPException

from app.services import document_service as docs
from app.services.processing_service import ProcessingError, run_processing_pipeline

router = APIRouter()


# Where the pipeline comes to rest. Anything else is a stage it passes through:
# still running, or abandoned mid-run. Listing by the terminal set rather than
# naming the intermediate ones means a new pipeline stage cannot leak into the
# list by being forgotten here.
TERMINAL_STATUSES = {"VALID", "INVALID", "NEEDS_REVIEW", "COMPLETED", "FAILED"}


@router.get("")
async def list_documents():
    """List documents the pipeline has finished with, newest first."""
    rows = await docs.get_all_documents()  # already ordered created_at DESC
    return [row for row in rows if row.get("status") in TERMINAL_STATUSES]


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
    try:
        return await run_processing_pipeline(document_id)
    except ProcessingError as e:
        raise HTTPException(status_code=404 if e.not_found else 400, detail=e.message)
