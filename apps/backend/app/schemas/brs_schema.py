from pydantic import BaseModel
from typing import Optional


class BrsDocumentCreate(BaseModel):
    filename: str
    original_path: str
    mime_type: Optional[str] = None


class BrsUploadResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    page_count: int
    message: str
