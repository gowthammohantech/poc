"""Bank reconciliation documents, shaped the same way as invoice documents.

Pages and the stage results are embedded on the document; processing logs keep
their own collection. The `*_json` key names the SQLite columns had are
preserved on the embedded sub-documents because the BRS routes and export
service read through them.
"""

import uuid
import json
from datetime import datetime
from typing import Optional

from app.db.mongo import get_database, with_id
from app.schemas.brs_schema import BrsDocumentCreate

_DOCUMENT_DEFAULTS: dict = {
    "original_path": None,
    "mime_type": None,
    "status": "UPLOADED",
    "page_count": 0,
    "processing_mode": None,
}

_STAGES = ("pages", "extraction", "validation", "final_output")
_WITHOUT_STAGES = {stage: 0 for stage in _STAGES}


async def create_document(data: BrsDocumentCreate) -> str:
    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    await get_database().brs_documents.insert_one({
        **_DOCUMENT_DEFAULTS,
        "_id": doc_id,
        "filename": data.filename,
        "original_path": data.original_path,
        "mime_type": data.mime_type,
        "created_at": now,
        "updated_at": now,
        "pages": [],
    })
    return doc_id


def _sanitize(fields: dict) -> dict:
    bad = [key for key in fields if key.startswith("$") or "." in key]
    if bad:
        raise ValueError(f"Invalid field name(s) for update: {', '.join(bad)}")
    return fields


async def update_document_status(document_id: str, status: str, **fields):
    updates = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    for key, val in _sanitize(fields).items():
        updates[key] = json.dumps(val) if isinstance(val, (dict, list)) else val
    await get_database().brs_documents.update_one({"_id": document_id}, {"$set": updates})


async def get_document(document_id: str) -> Optional[dict]:
    doc = await get_database().brs_documents.find_one({"_id": document_id}, _WITHOUT_STAGES)
    return with_id(doc)


async def get_all_documents() -> list:
    cursor = get_database().brs_documents.find({}, _WITHOUT_STAGES).sort("created_at", -1)
    return [with_id(doc) async for doc in cursor]


async def add_page(document_id: str, page_number: int, original_path: str,
                   preprocessed_path: str = None, width: int = None, height: int = None) -> str:
    page_id = str(uuid.uuid4())
    await get_database().brs_documents.update_one(
        {"_id": document_id},
        {"$push": {"pages": {
            "id": page_id,
            "document_id": document_id,
            "page_number": page_number,
            "original_path": original_path,
            "preprocessed_path": preprocessed_path,
            "width": width,
            "height": height,
            "created_at": datetime.utcnow().isoformat(),
        }}},
    )
    return page_id


async def get_pages(document_id: str) -> list:
    doc = await get_database().brs_documents.find_one({"_id": document_id}, {"pages": 1})
    pages = (doc or {}).get("pages") or []
    return sorted(pages, key=lambda p: p.get("page_number") or 0)


async def log_step(document_id: str, step: str, status: str, message: str = "", details: dict = None):
    await get_database().brs_processing_logs.insert_one({
        "_id": str(uuid.uuid4()),
        "document_id": document_id,
        "step": step,
        "status": status,
        "message": message,
        "details": details,
        "created_at": datetime.utcnow().isoformat(),
    })


async def save_extraction_result(document_id: str, brs_json: dict,
                                 confidence_json: dict, raw_llm_response: str = None) -> str:
    result_id = str(uuid.uuid4())
    await get_database().brs_documents.update_one(
        {"_id": document_id},
        {"$set": {"extraction": {
            "id": result_id,
            "document_id": document_id,
            "brs_json": brs_json or {},
            "confidence_json": confidence_json or {},
            "raw_llm_response": raw_llm_response,
            "created_at": datetime.utcnow().isoformat(),
        }}},
    )
    return result_id


async def get_extraction_result(document_id: str) -> Optional[dict]:
    doc = await get_database().brs_documents.find_one({"_id": document_id}, {"extraction": 1})
    return (doc or {}).get("extraction") or None


async def save_validation_result(document_id: str, status: str, rule_checks: list,
                                 llm_checks: list, warnings: list, errors: list) -> str:
    result_id = str(uuid.uuid4())
    await get_database().brs_documents.update_one(
        {"_id": document_id},
        {"$set": {"validation": {
            "id": result_id,
            "document_id": document_id,
            "status": status,
            "rule_checks_json": rule_checks,
            "llm_checks_json": llm_checks,
            "warnings_json": warnings,
            "errors_json": errors,
            "created_at": datetime.utcnow().isoformat(),
        }}},
    )
    return result_id


async def get_validation_result(document_id: str) -> Optional[dict]:
    doc = await get_database().brs_documents.find_one({"_id": document_id}, {"validation": 1})
    return (doc or {}).get("validation") or None


async def save_final_output(document_id: str, corrected_json: dict) -> str:
    output_id = str(uuid.uuid4())
    await get_database().brs_documents.update_one(
        {"_id": document_id},
        {"$set": {"final_output": {
            "id": output_id,
            "document_id": document_id,
            "corrected_json": corrected_json,
            "submitted_at": datetime.utcnow().isoformat(),
        }}},
    )
    return output_id


async def get_final_output(document_id: str) -> Optional[dict]:
    doc = await get_database().brs_documents.find_one({"_id": document_id}, {"final_output": 1})
    return (doc or {}).get("final_output") or None


async def _merge_into_extraction_json(document_id: str, patch: dict) -> None:
    """Merge keys into the same brs_json blob that already holds bank_statement, coa, ledger, etc. — no separate collection."""
    db = get_database()
    existing = await db.brs_documents.find_one({"_id": document_id}, {"extraction": 1})
    extraction = (existing or {}).get("extraction")

    if extraction:
        brs_json = dict(extraction.get("brs_json") or {})
        brs_json.update(patch)
        await db.brs_documents.update_one(
            {"_id": document_id}, {"$set": {"extraction.brs_json": brs_json}}
        )
    else:
        await db.brs_documents.update_one(
            {"_id": document_id},
            {"$set": {"extraction": {
                "id": str(uuid.uuid4()),
                "document_id": document_id,
                "brs_json": patch,
                "confidence_json": {},
                "raw_llm_response": None,
                "created_at": datetime.utcnow().isoformat(),
            }}},
        )


async def save_coa_data(document_id: str, rows: list) -> None:
    await _merge_into_extraction_json(document_id, {"coa": rows})


async def save_ledger_data(document_id: str, rows: list) -> None:
    await _merge_into_extraction_json(document_id, {"ledger": rows})


async def get_coa_data(document_id: str) -> list:
    result = await get_extraction_result(document_id)
    return result["brs_json"].get("coa", []) if result else []


async def get_ledger_data(document_id: str) -> list:
    result = await get_extraction_result(document_id)
    return result["brs_json"].get("ledger", []) if result else []
