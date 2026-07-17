from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.services.excel_parse_service import parse_coa_excel, parse_ledger_excel
from app.services import brs_document_service as docs

router = APIRouter()

ALLOWED_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}


class RowsPayload(BaseModel):
    rows: List[Dict[str, Any]]


def _validate_excel_upload(file: UploadFile) -> None:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")


@router.post("/matching/parse-coa")
async def parse_coa(file: UploadFile = File(...)):
    _validate_excel_upload(file)
    content = await file.read()
    try:
        return parse_coa_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/matching/parse-ledger")
async def parse_ledger(file: UploadFile = File(...)):
    _validate_excel_upload(file)
    content = await file.read()
    try:
        return parse_ledger_excel(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/matching/{document_id}/coa")
async def save_coa(document_id: str, body: RowsPayload):
    await docs.save_coa_data(document_id, body.rows)
    return {"saved": True, "count": len(body.rows)}


@router.post("/matching/{document_id}/ledger")
async def save_ledger(document_id: str, body: RowsPayload):
    await docs.save_ledger_data(document_id, body.rows)
    return {"saved": True, "count": len(body.rows)}
