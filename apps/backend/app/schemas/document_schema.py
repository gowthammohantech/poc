from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DocumentCreate(BaseModel):
    filename: str
    original_path: str
    mime_type: Optional[str] = None
    expected_fields: Optional[str] = None
    must_use_llm: bool = False
    # How this document entered the system: MANUAL (uploaded by a person),
    # API (posted by a script), or CONNECTOR (pulled from a mailbox).
    source: str = "MANUAL"
    source_connector_id: Optional[str] = None
    source_ref: Optional[str] = None
    source_metadata: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_path: Optional[str]
    mime_type: Optional[str]
    status: str
    source: str = "MANUAL"
    source_connector_id: Optional[str] = None
    source_ref: Optional[str] = None
    source_metadata: Optional[str] = None
    complexity_score: Optional[float]
    complexity_level: Optional[str]
    complexity_reasons: Optional[str]
    ocr_engine: Optional[str]
    processing_mode: Optional[str]
    page_count: int
    expected_fields: Optional[str]
    must_use_llm: bool
    created_at: str
    updated_at: str


class PageResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    original_path: Optional[str]
    preprocessed_path: Optional[str]
    width: Optional[int]
    height: Optional[int]


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int
    complexity_score: Optional[float]
    complexity_level: Optional[str]
    message: str
