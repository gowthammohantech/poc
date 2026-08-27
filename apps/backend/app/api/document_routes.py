from fastapi import APIRouter, HTTPException

from app.services import document_service as docs
from app.services.processing_service import ProcessingError, run_processing_pipeline

router = APIRouter()


# Intermediate states the pipeline passes through; a row parked in one of these
# is either still processing or was abandoned mid-run, so it is not listed.
IN_PROGRESS_STATUSES = {"VALIDATING", "COMPLEXITY_ANALYZED"}


@router.get("")
async def list_documents():
    """List processed documents, newest first."""
    rows = await docs.get_all_documents()  # already ordered created_at DESC
    return [row for row in rows if row.get("status") not in IN_PROGRESS_STATUSES]


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
