"""Shared ingestion path: bytes in, a document ready for OCR out.

Every ingestion channel funnels through here — the manual upload endpoint, a
script posting to the API, and the mailbox connectors — so a document lands in
exactly the same state regardless of how it arrived.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.schemas.document_schema import DocumentCreate
from app.services import file_storage_service as storage
from app.services import document_service as docs
from app.services.complexity_service import analyze_complexity
from app.services.convert_service import convert_to_pages
from app.services.preprocess_service import preprocess_pages

ALLOWED_MIME = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/tiff", "image/bmp", "image/heic", "image/heif",
    "image/heic-sequence", "image/heif-sequence",
}

ALLOWED_SUFFIXES = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif", ".bmp", ".heic", ".heif",
}

SOURCE_MANUAL = "MANUAL"
SOURCE_API = "API"
SOURCE_CONNECTOR = "CONNECTOR"
VALID_SOURCES = {SOURCE_MANUAL, SOURCE_API, SOURCE_CONNECTOR}


class IngestError(Exception):
    """A document could not be taken in. `stage` names the step that failed."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = message


@dataclass
class IngestResult:
    document_id: str
    filename: str
    status: str
    page_count: int
    complexity_score: Optional[float]
    complexity_level: Optional[str]


def validate_ingest_type(filename: str, content_type: Optional[str]) -> str:
    """Accept a file by declared MIME type, falling back to its extension."""
    content_type = content_type or ""
    if content_type in ALLOWED_MIME:
        return content_type
    suffix = Path(filename or "").suffix.lower()
    if suffix in ALLOWED_SUFFIXES:
        return content_type
    raise IngestError("VALIDATE", f"Unsupported file type: {content_type or suffix or 'unknown'}")


def normalize_source(source: Optional[str]) -> str:
    candidate = (source or SOURCE_MANUAL).strip().upper()
    return candidate if candidate in VALID_SOURCES else SOURCE_MANUAL


async def ingest_bytes(
    *,
    filename: str,
    content: bytes,
    mime_type: Optional[str] = None,
    expected_fields: Optional[str] = None,
    must_use_llm: bool = False,
    source: str = SOURCE_MANUAL,
    source_connector_id: Optional[str] = None,
    source_ref: Optional[str] = None,
    source_metadata: Optional[dict] = None,
) -> IngestResult:
    """Save, split into pages, preprocess and score a document.

    Leaves it at COMPLEXITY_ANALYZED, ready for the OCR pipeline.
    """
    filename = filename or "upload"
    mime_type = validate_ingest_type(filename, mime_type)

    doc_data = DocumentCreate(
        filename=filename,
        original_path="",
        mime_type=mime_type,
        expected_fields=expected_fields,
        must_use_llm=must_use_llm,
        source=normalize_source(source),
        source_connector_id=source_connector_id,
        source_ref=source_ref,
        source_metadata=json.dumps(source_metadata) if source_metadata else None,
    )
    document_id = await docs.create_document(doc_data)
    await docs.log_step(document_id, "UPLOAD", "SUCCESS", "File received")

    # Save original file
    await docs.update_document_status(document_id, "SAVING")
    original_path = await storage.save_bytes(document_id, filename, content)
    await docs.update_document_status(document_id, "SAVED", original_path=original_path)
    await docs.log_step(document_id, "SAVE_FILE", "SUCCESS", f"Saved to {original_path}")

    # Convert to pages. Rendering and OpenCV work is CPU-bound, so it runs off
    # the event loop — a connector sync would otherwise stall every other
    # request, including the poll that reports its own progress.
    await docs.update_document_status(document_id, "CONVERTING")
    try:
        page_dir = storage.get_page_dir(document_id)
        page_paths = await run_in_threadpool(convert_to_pages, original_path, page_dir)
        await docs.log_step(document_id, "CONVERT", "SUCCESS", f"{len(page_paths)} page(s) created")
    except Exception as e:
        await docs.update_document_status(document_id, "FAILED")
        await docs.log_step(document_id, "CONVERT", "FAILED", str(e))
        raise IngestError("CONVERT", str(e))

    # Preprocess pages
    await docs.update_document_status(document_id, "PREPROCESSING")
    try:
        preprocessed_dir = storage.get_preprocessed_dir(document_id)
        preprocessed_paths = await run_in_threadpool(preprocess_pages, page_paths, preprocessed_dir)
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
        complexity = await run_in_threadpool(analyze_complexity, preprocessed_paths)
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

    return IngestResult(
        document_id=document_id,
        filename=filename,
        status="COMPLEXITY_ANALYZED",
        page_count=len(page_paths),
        complexity_score=complexity["score"],
        complexity_level=complexity["level"],
    )


async def ingest_upload_file(
    file: UploadFile,
    *,
    expected_fields: Optional[str] = None,
    must_use_llm: bool = False,
    source: str = SOURCE_MANUAL,
) -> IngestResult:
    filename = file.filename or "upload"
    validate_ingest_type(filename, file.content_type)
    return await ingest_bytes(
        filename=filename,
        content=await file.read(),
        mime_type=file.content_type or "",
        expected_fields=expected_fields,
        must_use_llm=must_use_llm,
        source=source,
    )
