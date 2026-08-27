import uuid
import json
from datetime import datetime
from typing import Optional
import aiosqlite

from app.db.database import get_db
from app.schemas.document_schema import DocumentCreate


async def create_document(data: DocumentCreate) -> str:
    doc_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO documents
               (id, filename, original_path, mime_type, status, expected_fields, must_use_llm,
                source, source_connector_id, source_ref, source_metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'UPLOADED', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, data.filename, data.original_path, data.mime_type,
             data.expected_fields, int(data.must_use_llm),
             data.source, data.source_connector_id, data.source_ref, data.source_metadata,
             now, now),
        )
        await db.commit()
    return doc_id


async def update_document_status(document_id: str, status: str, **fields):
    now = datetime.utcnow().isoformat()
    set_parts = ["status = ?", "updated_at = ?"]
    values = [status, now]
    for key, val in fields.items():
        set_parts.append(f"{key} = ?")
        if isinstance(val, (dict, list)):
            values.append(json.dumps(val))
        else:
            values.append(val)
    values.append(document_id)
    async with get_db() as db:
        await db.execute(
            f"UPDATE documents SET {', '.join(set_parts)} WHERE id = ?", values
        )
        await db.commit()


async def get_document(document_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM documents WHERE id = ?", (document_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_all_documents() -> list:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM documents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def add_page(document_id: str, page_number: int, original_path: str,
                   preprocessed_path: str = None, width: int = None, height: int = None) -> str:
    page_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO document_pages
               (id, document_id, page_number, original_path, preprocessed_path, width, height, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (page_id, document_id, page_number, original_path, preprocessed_path, width, height, now),
        )
        await db.commit()
    return page_id


async def get_pages(document_id: str) -> list:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM document_pages WHERE document_id = ? ORDER BY page_number",
            (document_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def log_step(document_id: str, step: str, status: str, message: str = "", details: dict = None):
    log_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO processing_logs (id, document_id, step, status, message, details, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (log_id, document_id, step, status, message, json.dumps(details) if details else None, now),
        )
        await db.commit()


async def save_ocr_result(document_id: str, engine: str, raw_text: str,
                           confidence: float, word_count: int, metadata: dict) -> str:
    result_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO ocr_results (id, document_id, engine, raw_text, confidence, word_count, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result_id, document_id, engine, raw_text, confidence, word_count, json.dumps(metadata), now),
        )
        await db.commit()
    return result_id


async def get_ocr_result(document_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM ocr_results WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
            (document_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result["metadata_json"]) if result["metadata_json"] else {}
        return result


async def save_extraction_result(document_id: str, invoice_json: dict,
                                  confidence_json: dict, raw_llm_response: str = None) -> str:
    result_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO extraction_results (id, document_id, invoice_json, confidence_json, raw_llm_response, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (result_id, document_id, json.dumps(invoice_json), json.dumps(confidence_json), raw_llm_response, now),
        )
        await db.commit()
    return result_id


async def get_extraction_result(document_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM extraction_results WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
            (document_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        r["invoice_json"] = json.loads(r["invoice_json"]) if r["invoice_json"] else {}
        r["confidence_json"] = json.loads(r["confidence_json"]) if r["confidence_json"] else {}
        return r


async def save_validation_result(document_id: str, status: str, rule_checks: list,
                                   llm_checks: list, warnings: list, errors: list) -> str:
    result_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO validation_results
               (id, document_id, status, rule_checks_json, llm_checks_json, warnings_json, errors_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result_id, document_id, status,
             json.dumps(rule_checks), json.dumps(llm_checks),
             json.dumps(warnings), json.dumps(errors), now),
        )
        await db.commit()
    return result_id


async def get_validation_result(document_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM validation_results WHERE document_id = ? ORDER BY created_at DESC LIMIT 1",
            (document_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        for key in ("rule_checks_json", "llm_checks_json", "warnings_json", "errors_json"):
            r[key] = json.loads(r[key]) if r[key] else []
        return r


async def save_final_output(document_id: str, corrected_json: dict) -> str:
    output_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    async with get_db() as db:
        await db.execute(
            "DELETE FROM final_outputs WHERE document_id = ?", (document_id,)
        )
        await db.execute(
            "INSERT INTO final_outputs (id, document_id, corrected_json, submitted_at) VALUES (?, ?, ?, ?)",
            (output_id, document_id, json.dumps(corrected_json), now),
        )
        await db.commit()
    return output_id


async def get_final_output(document_id: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM final_outputs WHERE document_id = ? ORDER BY submitted_at DESC LIMIT 1",
            (document_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        r = dict(row)
        r["corrected_json"] = json.loads(r["corrected_json"]) if r["corrected_json"] else {}
        return r
