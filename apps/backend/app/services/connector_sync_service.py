"""Runs a mailbox sync: fetch attachments, ingest them, drive the OCR pipeline.

A sync takes minutes, so it cannot happen inside the request that starts it.
The run is tracked in connector_sync_runs and reported by polling; the work
itself happens in an asyncio task on this process.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pymongo.errors import DuplicateKeyError

from app.db.mongo import get_database, with_id
from app.services import connector_service, ingest_service
from app.services.connectors import ConnectorError, MailAttachmentRef, get_connector
from app.services.processing_service import run_processing_pipeline

logger = logging.getLogger(__name__)

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"

ITEM_INGESTED = "INGESTED"
ITEM_SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"
ITEM_SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
ITEM_SKIPPED_INLINE = "SKIPPED_INLINE"
ITEM_FAILED = "FAILED"

# Which run counter each skip reason lands in. Kept apart so the UI can say
# *why* something was passed over: "wrong sort of file" and "an image too small
# to be a document" are different answers, and reporting both as one number is
# what let the inline heuristic drop invoices unnoticed.
_SKIP_COUNTERS = {
    ITEM_SKIPPED_UNSUPPORTED: "skipped_unsupported",
    ITEM_SKIPPED_INLINE: "skipped_inline",
}

# asyncio discards tasks nothing holds a reference to, which would abandon a
# sync partway through for no visible reason.
_TASKS: dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.utcnow().isoformat()


def _max_bytes() -> int:
    return int(os.getenv("CONNECTOR_MAX_ATTACHMENT_MB", "15")) * 1024 * 1024


def _min_bytes() -> int:
    return int(os.getenv("CONNECTOR_MIN_ATTACHMENT_KB", "20")) * 1024


# -- run records -----------------------------------------------------------


async def get_run(run_id: str) -> Optional[dict]:
    return with_id(await get_database().connector_sync_runs.find_one({"_id": run_id}))


async def list_runs(connection_id: str, limit: int = 20) -> list[dict]:
    cursor = get_database().connector_sync_runs.find(
        {"connection_id": connection_id}
    ).sort("started_at", -1).limit(limit)
    return [with_id(doc) async for doc in cursor]


async def list_run_items(run_id: str) -> list[dict]:
    cursor = get_database().connector_sync_items.find(
        {"run_id": run_id}
    ).sort("created_at", 1)
    return [with_id(doc) async for doc in cursor]


# Every stage a document passes through before validation settles it. Wider
# than _ABANDONED_DOCUMENT_STATUSES below, which is only about restart recovery:
# a connector document resting at COMPLEXITY_ANALYZED is still on its way to
# becoming an invoice, because its sync calls the pipeline itself.
_IN_FLIGHT_DOCUMENT_STATUSES = (
    "UPLOADED", "SAVING", "SAVED", "CONVERTING", "PREPROCESSING", "PREPROCESSED",
    "ANALYZING_COMPLEXITY", "COMPLEXITY_ANALYZED", "ROUTING", "ROUTED",
    "OCR_RUNNING", "EXTRACTING", "EXTRACTED", "VALIDATING",
)

# Run counters worth summing across a connection's whole history.
_TOTAL_COLUMNS = (
    "messages_scanned", "messages_with_attachments", "attachments_found",
    "documents_created", "documents_processed", "documents_failed",
    "skipped_duplicates", "skipped_unsupported", "skipped_inline",
)

_READY_DOCUMENT_STATUSES = ("VALID", "COMPLETED")

# Counters a run carries from the moment it is created, so a stats read never
# has to distinguish "no runs yet" from "a run that has not counted anything".
_RUN_DEFAULTS: dict = {
    "messages_scanned": 0,
    "messages_with_attachments": 0,
    "attachments_found": 0,
    "documents_created": 0,
    "documents_processed": 0,
    "documents_failed": 0,
    "skipped_duplicates": 0,
    "skipped_unsupported": 0,
    "skipped_inline": 0,
    "current_activity": None,
    "error_message": None,
    "finished_at": None,
}


async def get_connection_stats(connection_id: str) -> dict:
    """What a connection has pulled in so far, without having to start a sync.

    Two sources, deliberately: the run counters are a record of what each sync
    saw in the mailbox, while the invoice counts come from the documents
    collection, because a document keeps moving through the pipeline (and can be
    reviewed, or fail) long after the run that ingested it has finished.
    """
    db = get_database()

    run_cursor = await db.connector_sync_runs.aggregate([
        {"$match": {"connection_id": connection_id}},
        {"$group": {
            "_id": None,
            "runs": {"$sum": 1},
            **{col: {"$sum": {"$ifNull": [f"${col}", 0]}} for col in _TOTAL_COLUMNS},
        }},
    ])
    run_totals = await run_cursor.to_list(1)

    # Aggregating over no runs yields no group at all; the UI wants zeroes.
    grouped = run_totals[0] if run_totals else {}
    runs = grouped.get("runs", 0)
    totals = {col: grouped.get(col, 0) for col in _TOTAL_COLUMNS}

    last_run = with_id(await db.connector_sync_runs.find_one(
        {"connection_id": connection_id},
        sort=[("started_at", -1)],
    ))

    def count_if(condition: dict) -> dict:
        return {"$sum": {"$cond": [condition, 1, 0]}}

    invoice_cursor = await db.documents.aggregate([
        {"$match": {"source_connector_id": connection_id}},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "in_progress": count_if({"$in": ["$status", list(_IN_FLIGHT_DOCUMENT_STATUSES)]}),
            "ready": count_if({"$in": ["$status", list(_READY_DOCUMENT_STATUSES)]}),
            "needs_review": count_if({"$eq": ["$status", "NEEDS_REVIEW"]}),
            # Extracted, but validation found problems in it.
            "invalid": count_if({"$eq": ["$status", "INVALID"]}),
            # Never got as far as an extraction.
            "failed": count_if({"$eq": ["$status", "FAILED"]}),
        }},
    ])
    invoice_totals = await invoice_cursor.to_list(1)

    counted = invoice_totals[0] if invoice_totals else {}
    invoices = {
        key: counted.get(key, 0) or 0
        for key in ("total", "in_progress", "ready", "needs_review", "invalid", "failed")
    }

    return {
        "connection_id": connection_id,
        "runs": runs,
        "last_run": last_run,
        "totals": totals,
        "invoices": invoices,
    }


async def has_running_sync(connection_id: str) -> bool:
    found = await get_database().connector_sync_runs.find_one(
        {"connection_id": connection_id, "status": STATUS_RUNNING}, {"_id": 1}
    )
    return found is not None


async def _update_run(run_id: str, **fields):
    if not fields:
        return
    bad = [key for key in fields if key.startswith("$") or "." in key]
    if bad:
        raise ValueError(f"Invalid field name(s) for update: {', '.join(bad)}")
    await get_database().connector_sync_runs.update_one(
        {"_id": run_id}, {"$set": fields}
    )


async def _record_item(run_id: str, connection_id: str, ref: MailAttachmentRef,
                       status: str, document_id: str | None = None,
                       error_message: str | None = None):
    await get_database().connector_sync_items.insert_one({
        "_id": str(uuid.uuid4()),
        "run_id": run_id,
        "connection_id": connection_id,
        "external_message_id": ref.message_id,
        "external_attachment_id": ref.attachment_id,
        "part_index": ref.part_index,
        "filename": ref.filename,
        "mime_type": ref.mime_type,
        "size_bytes": ref.size_bytes,
        "from_address": ref.from_address,
        "subject": ref.subject,
        "received_at": ref.received_at,
        "document_id": document_id,
        "status": status,
        "error_message": error_message,
        "created_at": _now(),
    })


# Stages a document can only be sitting in because its run was interrupted.
# COMPLEXITY_ANALYZED is excluded: that is a legitimate rest between upload and
# a separate /process call.
_ABANDONED_DOCUMENT_STATUSES = (
    "SAVING", "CONVERTING", "PREPROCESSING", "ANALYZING_COMPLEXITY",
    "ROUTING", "ROUTED", "OCR_RUNNING", "EXTRACTING", "EXTRACTED", "VALIDATING",
)


async def reap_stale_runs():
    """Close out work abandoned by a restart.

    Sync tasks live in this process, so on startup nothing is genuinely in
    flight. Both the run and the document it was mid-way through have to be
    settled: a document left at OCR_RUNNING is not FAILED, so the duplicate
    check would treat it as already ingested and skip that attachment on every
    future sync. Marking it FAILED lets the next sync retry it in place.
    """
    db = get_database()
    await db.connector_sync_runs.update_many(
        {"status": STATUS_RUNNING},
        {"$set": {
            "status": STATUS_FAILED,
            "error_message": "Interrupted by a server restart",
            "finished_at": _now(),
        }},
    )
    await db.documents.update_many(
        {"source": "CONNECTOR", "status": {"$in": list(_ABANDONED_DOCUMENT_STATUSES)}},
        {"$set": {"status": "FAILED", "updated_at": _now()}},
    )


# -- starting a sync -------------------------------------------------------


async def start_sync(connection_id: str, trigger: str = "MANUAL") -> dict:
    connection = await connector_service.get_connection(connection_id)
    if not connection:
        raise ConnectorError("Connection not found")
    if connection["status"] == connector_service.STATUS_NEEDS_REAUTH:
        raise ConnectorError("This account needs to be authorised again before syncing.")
    if connection["status"] != connector_service.STATUS_CONNECTED:
        raise ConnectorError("This account is not connected.")
    if await has_running_sync(connection_id):
        raise SyncAlreadyRunning("A sync is already running for this account.")

    run_id = str(uuid.uuid4())
    await get_database().connector_sync_runs.insert_one({
        **_RUN_DEFAULTS,
        "_id": run_id,
        "connection_id": connection_id,
        "status": STATUS_RUNNING,
        "trigger": trigger,
        "current_activity": "Connecting…",
        "started_at": _now(),
    })

    task = asyncio.create_task(run_sync(run_id, connection_id))
    _TASKS[run_id] = task
    task.add_done_callback(lambda _t: _TASKS.pop(run_id, None))

    return await get_run(run_id)


class SyncAlreadyRunning(ConnectorError):
    """A sync is already in flight for this connection."""


# -- the sync itself -------------------------------------------------------


def _skip_reason(ref: MailAttachmentRef) -> Optional[str]:
    """Why this attachment cannot be an invoice, or None to go and fetch it.

    Order matters. What the file *is* comes first, because the inline rule
    below is a heuristic and must not get to veto a document the sender clearly
    attached on purpose: an inline flag only disqualifies the small images the
    rule exists for, never a PDF.
    """
    if Path(ref.filename).suffix.lower() not in ingest_service.ALLOWED_SUFFIXES:
        return ITEM_SKIPPED_UNSUPPORTED
    if ref.size_bytes and ref.size_bytes > _max_bytes():
        return ITEM_SKIPPED_UNSUPPORTED
    if ref.size_bytes and ref.size_bytes < _min_bytes():
        # Below this it is a logo or a signature image, not an invoice.
        return ITEM_SKIPPED_INLINE
    if ref.is_inline and ref.mime_type.lower().startswith("image/"):
        return ITEM_SKIPPED_INLINE
    return None


async def run_sync(run_id: str, connection_id: str):
    counters = {
        "documents_created": 0,
        "documents_processed": 0,
        "documents_failed": 0,
        "skipped_duplicates": 0,
        "skipped_unsupported": 0,
        "skipped_inline": 0,
    }
    try:
        connection = await connector_service.get_connection(connection_id)
        connector = get_connector(connection["provider"])
        access_token = await connector_service.get_valid_access_token(connection_id)

        await _update_run(run_id, current_activity="Searching the mailbox…")
        refs, scanned = await connector.list_attachments(
            access_token,
            query=connection.get("filter_query") or None,
            label_id=connection.get("filter_label") or None,
            max_messages=connection.get("max_messages_per_sync") or 1,
        )
        await _update_run(
            run_id,
            messages_scanned=scanned,
            # Several attachments can share one message, so this is not len(refs).
            messages_with_attachments=len({ref.message_id for ref in refs}),
            attachments_found=len(refs),
            current_activity=f"Found {len(refs)} attachment(s)",
        )

        # One at a time: the pipeline is CPU- and LLM-bound, so running these
        # concurrently would buy rate limits rather than speed.
        for ref in refs:
            skip = _skip_reason(ref)
            if skip:
                await _record_item(run_id, connection_id, ref, skip)
                counters[_SKIP_COUNTERS[skip]] += 1
                await _update_run(run_id, **counters)
                continue

            existing = await connector_service.is_already_ingested(connection_id, ref.source_ref)
            if existing and existing["status"] != "FAILED":
                await _record_item(run_id, connection_id, ref, ITEM_SKIPPED_DUPLICATE,
                                   document_id=existing["id"])
                counters["skipped_duplicates"] += 1
                await _update_run(run_id, **counters)
                continue

            await _update_run(
                run_id, current_activity=f"Processing {ref.filename}…", **counters
            )
            try:
                if existing:
                    # A previous attempt failed at the OCR stage; retry the
                    # pipeline on that document rather than ingesting a second copy.
                    document_id = existing["id"]
                else:
                    content = await connector.fetch_attachment(access_token, ref)
                    result = await ingest_service.ingest_bytes(
                        filename=ref.filename,
                        content=content,
                        mime_type=ref.mime_type,
                        source=ingest_service.SOURCE_CONNECTOR,
                        # The regime chosen for this mailbox: its attachments
                        # run the India invoice pipeline or the US one.
                        country=connector_service.connection_country(connection),
                        source_connector_id=connection_id,
                        source_ref=ref.source_ref,
                        source_metadata={
                            "provider": connection["provider"],
                            "from": ref.from_address,
                            "subject": ref.subject,
                            "received_at": ref.received_at,
                            "thread_id": ref.thread_id,
                            "attachment_id": ref.attachment_id,
                        },
                    )
                    document_id = result.document_id
                    counters["documents_created"] += 1

                await run_processing_pipeline(document_id)
                counters["documents_processed"] += 1
                await _record_item(run_id, connection_id, ref, ITEM_INGESTED, document_id=document_id)
            except DuplicateKeyError:
                # ux_documents_source_ref refused a second copy of this
                # attachment, so something ingested it between the check above
                # and here. Same outcome as the check finding it.
                logger.info("Attachment %s was already ingested concurrently", ref.filename)
                await _record_item(run_id, connection_id, ref, ITEM_SKIPPED_DUPLICATE)
                counters["skipped_duplicates"] += 1
            except Exception as e:
                logger.exception("Connector sync failed on %s", ref.filename)
                counters["documents_failed"] += 1
                await _record_item(run_id, connection_id, ref, ITEM_FAILED, error_message=str(e))
            await _update_run(run_id, **counters)

        if counters["documents_failed"] and not counters["documents_processed"]:
            status = STATUS_FAILED
        elif counters["documents_failed"]:
            status = STATUS_PARTIAL
        else:
            status = STATUS_COMPLETED

        await _update_run(
            run_id, status=status, finished_at=_now(),
            current_activity=None, **counters,
        )
        await connector_service.update_connection(connection_id, last_sync_at=_now())

    except Exception as e:
        logger.exception("Connector sync %s failed", run_id)
        await _update_run(
            run_id, status=STATUS_FAILED, error_message=str(e),
            finished_at=_now(), current_activity=None, **counters,
        )
        await connector_service.update_connection(connection_id, last_error=str(e))
