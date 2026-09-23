"""Documents and everything derived from them.

The six tables that used to hang off `documents` are embedded on the document
itself, because every reader here only ever wanted the most recent row per
stage. Processing logs stay in their own collection: they are an append-only
record with no upper bound.

The embedded sub-documents keep the `*_json` key names the SQLite columns had.
They hold real BSON now rather than serialised JSON, but the names are the
contract four route modules and three export services read through, so they
stay.
"""

import uuid
import json
import shutil
from datetime import datetime
from typing import Optional

from app.db.mongo import get_database, with_id
from app.schemas.document_schema import DocumentCreate
from app.services.file_storage_service import STORAGE_BASE

# Absent keys and SQL NULLs are not the same thing: `SELECT *` always returned
# every column, and readers index into these dicts directly. Writing the full
# shape on insert keeps every one of them working without a coalescing pass.
_DOCUMENT_DEFAULTS: dict = {
    "original_path": None,
    "mime_type": None,
    "status": "UPLOADED",
    "complexity_score": None,
    "complexity_level": None,
    "complexity_reasons": None,
    "ocr_engine": None,
    "processing_mode": None,
    "page_count": 0,
    "expected_fields": None,
    "must_use_llm": 0,
    "country": "INDIA",
    "doc_type": None,
    "source": "MANUAL",
    "source_connector_id": None,
    "source_ref": None,
    "source_metadata": None,
    "document_number": None,
}

# The embedded stage results, excluded from document reads. Without this the
# list endpoint would ship every document's OCR text and raw LLM response.
_STAGES = ("pages", "ocr", "extraction", "validation", "final_output")
_WITHOUT_STAGES = {stage: 0 for stage in _STAGES}


async def create_document(data: DocumentCreate) -> str:
    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    document = {
        **_DOCUMENT_DEFAULTS,
        "_id": doc_id,
        "filename": data.filename,
        "original_path": data.original_path,
        "mime_type": data.mime_type,
        "expected_fields": data.expected_fields,
        "must_use_llm": int(data.must_use_llm),
        "source": data.source,
        "source_connector_id": data.source_connector_id,
        "source_ref": data.source_ref,
        "source_metadata": data.source_metadata,
        "country": data.country,
        "doc_type": data.doc_type,
        "created_at": now,
        "updated_at": now,
        "pages": [],
    }
    await get_database().documents.insert_one(document)
    return doc_id


def _sanitize(fields: dict) -> dict:
    """Reject field names Mongo would read as update operators or paths."""
    bad = [key for key in fields if key.startswith("$") or "." in key]
    if bad:
        raise ValueError(f"Invalid field name(s) for update: {', '.join(bad)}")
    return fields


async def update_document_status(document_id: str, status: str, **fields):
    now = datetime.utcnow().isoformat()
    updates = {"status": status, "updated_at": now}
    for key, val in _sanitize(fields).items():
        # complexity_reasons and friends are declared as strings on
        # DocumentResponse, so structured values stay serialised here.
        updates[key] = json.dumps(val) if isinstance(val, (dict, list)) else val
    await get_database().documents.update_one({"_id": document_id}, {"$set": updates})


async def get_document(document_id: str) -> Optional[dict]:
    doc = await get_database().documents.find_one({"_id": document_id}, _WITHOUT_STAGES)
    return with_id(doc)


# The number a reader knows a document by: an India invoice's invoice number,
# a US purchase order's order number, a US shipping authorization's release
# number. Only one of the three is ever present on a given payload.
_DOCUMENT_NUMBER_KEYS = ("invoice_number", "order_number", "release_number")


def _document_number(payload: Optional[dict]) -> Optional[str]:
    """Pull the document number out of an extraction or correction payload.

    Was a generated pile of json_extract/NULLIF/TRIM/CASE run inside the
    document list query; the rule was always this bit of Python.
    """
    invoice = (payload or {}).get("invoice")
    if not isinstance(invoice, dict):
        return None

    def value(key: str) -> Optional[str]:
        raw = invoice.get(key)
        if raw is None:
            return None
        return str(raw).strip() or None

    candidates = []
    # A purchase order can also print an invoice number, but it is still known
    # by its PO number, so that one goes first for SOs.
    if invoice.get("document_type") == "SO":
        candidates.append(value("order_number"))
    candidates.extend(value(key) for key in _DOCUMENT_NUMBER_KEYS)
    return next((c for c in candidates if c), None)


def _resolve_document_number(final_payload: Optional[dict],
                             extraction_payload: Optional[dict]) -> Optional[str]:
    """A reviewer's correction wins over what extraction read."""
    return _document_number(final_payload) or _document_number(extraction_payload)


async def get_all_documents() -> list:
    """Every document, newest first, with its `document_number`.

    The number is maintained on write by save_extraction_result and
    save_final_output, so this is a plain read.
    """
    cursor = get_database().documents.find({}, _WITHOUT_STAGES).sort("created_at", -1)
    return [with_id(doc) async for doc in cursor]


async def delete_documents(document_ids: list[str]) -> int:
    """Remove documents with everything derived from them, rows and files.

    Nothing is kept to mark a mailbox attachment as already seen, so the next
    connector sync is free to ingest it again.
    """
    ids = list(dict.fromkeys(document_ids))
    if not ids:
        return 0

    db = get_database()
    # Pages and the four stage results are embedded, so they go with the parent.
    result = await db.documents.delete_many({"_id": {"$in": ids}})
    await db.processing_logs.delete_many({"document_id": {"$in": ids}})
    # Sync history stays, but no longer points at a document that is gone.
    await db.connector_sync_items.update_many(
        {"document_id": {"$in": ids}}, {"$set": {"document_id": None}}
    )
    deleted = result.deleted_count

    # Files only after the rows are gone: a failed delete must not leave a
    # document whose pages have vanished.
    for doc_id in ids:
        folder = STORAGE_BASE / doc_id
        if folder.resolve().parent == STORAGE_BASE.resolve():
            shutil.rmtree(folder, ignore_errors=True)
    return deleted


async def delete_document(document_id: str) -> int:
    return await delete_documents([document_id])


async def add_page(document_id: str, page_number: int, original_path: str,
                   preprocessed_path: str = None, width: int = None, height: int = None) -> str:
    page_id = str(uuid.uuid4())
    page = {
        "id": page_id,
        "document_id": document_id,
        "page_number": page_number,
        "original_path": original_path,
        "preprocessed_path": preprocessed_path,
        "width": width,
        "height": height,
        "created_at": datetime.utcnow().isoformat(),
    }
    await get_database().documents.update_one(
        {"_id": document_id}, {"$push": {"pages": page}}
    )
    return page_id


async def get_pages(document_id: str) -> list:
    doc = await get_database().documents.find_one({"_id": document_id}, {"pages": 1})
    pages = (doc or {}).get("pages") or []
    return sorted(pages, key=lambda p: p.get("page_number") or 0)


async def log_step(document_id: str, step: str, status: str, message: str = "", details: dict = None):
    await get_database().processing_logs.insert_one({
        "_id": str(uuid.uuid4()),
        "document_id": document_id,
        "step": step,
        "status": status,
        "message": message,
        "details": details,
        "created_at": datetime.utcnow().isoformat(),
    })


async def save_ocr_result(document_id: str, engine: str, raw_text: str,
                          confidence: float, word_count: int, metadata: dict) -> str:
    result_id = str(uuid.uuid4())
    await get_database().documents.update_one(
        {"_id": document_id},
        {"$set": {"ocr": {
            "id": result_id,
            "document_id": document_id,
            "engine": engine,
            "raw_text": raw_text,
            "confidence": confidence,
            "word_count": word_count,
            "metadata": metadata,
            "created_at": datetime.utcnow().isoformat(),
        }}},
    )
    return result_id


async def get_ocr_result(document_id: str) -> Optional[dict]:
    doc = await get_database().documents.find_one({"_id": document_id}, {"ocr": 1})
    return (doc or {}).get("ocr") or None


async def save_extraction_result(document_id: str, invoice_json: dict,
                                 confidence_json: dict, raw_llm_response: str = None) -> str:
    result_id = str(uuid.uuid4())
    db = get_database()
    # A correction already on file outranks this extraction for the number.
    current = await db.documents.find_one({"_id": document_id}, {"final_output": 1})
    final_payload = ((current or {}).get("final_output") or {}).get("corrected_json")

    await db.documents.update_one(
        {"_id": document_id},
        {"$set": {
            "extraction": {
                "id": result_id,
                "document_id": document_id,
                "invoice_json": invoice_json,
                "confidence_json": confidence_json,
                "raw_llm_response": raw_llm_response,
                "created_at": datetime.utcnow().isoformat(),
            },
            "document_number": _resolve_document_number(final_payload, invoice_json),
        }},
    )
    return result_id


async def get_extraction_result(document_id: str) -> Optional[dict]:
    doc = await get_database().documents.find_one({"_id": document_id}, {"extraction": 1})
    return (doc or {}).get("extraction") or None


async def save_validation_result(document_id: str, status: str, rule_checks: list,
                                 llm_checks: list, warnings: list, errors: list) -> str:
    result_id = str(uuid.uuid4())
    await get_database().documents.update_one(
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
    doc = await get_database().documents.find_one({"_id": document_id}, {"validation": 1})
    return (doc or {}).get("validation") or None


async def save_final_output(document_id: str, corrected_json: dict) -> str:
    output_id = str(uuid.uuid4())
    db = get_database()
    # Fall back to extraction when a correction carries no number of its own.
    current = await db.documents.find_one({"_id": document_id}, {"extraction": 1})
    extraction_payload = ((current or {}).get("extraction") or {}).get("invoice_json")

    await db.documents.update_one(
        {"_id": document_id},
        {"$set": {
            "final_output": {
                "id": output_id,
                "document_id": document_id,
                "corrected_json": corrected_json,
                "submitted_at": datetime.utcnow().isoformat(),
            },
            "document_number": _resolve_document_number(corrected_json, extraction_payload),
        }},
    )
    return output_id


async def get_final_output(document_id: str) -> Optional[dict]:
    doc = await get_database().documents.find_one({"_id": document_id}, {"final_output": 1})
    return (doc or {}).get("final_output") or None
