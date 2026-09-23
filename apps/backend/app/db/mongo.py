"""MongoDB client, index and validator management.

One pooled client for the process, opened lazily and closed on shutdown. This
replaces the previous SQLite layer, which opened a fresh connection for every
logical operation.

Configuration is read on each call rather than into module-level constants, so
tests can point the process at a throwaway database with monkeypatch.setenv
alone — the old layer needed importlib.reload to pick up a new DB_PATH.
"""

import logging
import os
from typing import Optional

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import CollectionInvalid, OperationFailure, PyMongoError

logger = logging.getLogger(__name__)

DEFAULT_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "invoice_ocr"

_client: Optional[AsyncMongoClient] = None
_client_uri: Optional[str] = None


def mongo_uri() -> str:
    return os.getenv("MONGODB_URI", DEFAULT_URI)


def mongo_db_name() -> str:
    return os.getenv("MONGO_DB_NAME", DEFAULT_DB_NAME)


def get_client() -> AsyncMongoClient:
    """The process-wide client. Rebuilt if the configured URI has changed."""
    global _client, _client_uri
    uri = mongo_uri()
    if _client is None or _client_uri != uri:
        _client = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "10000")),
            tz_aware=False,
        )
        _client_uri = uri
    return _client


def get_database() -> AsyncDatabase:
    """The application database. Name is resolved per call, see module docstring."""
    return get_client()[mongo_db_name()]


async def close_client() -> None:
    global _client, _client_uri
    if _client is not None:
        await _client.close()
        _client = None
        _client_uri = None


def with_id(document: Optional[dict]) -> Optional[dict]:
    """Rename Mongo's `_id` to the `id` every caller in this codebase expects."""
    if document is None:
        return None
    out = dict(document)
    if "_id" in out:
        out["id"] = out.pop("_id")
    return out


# -- indexes ---------------------------------------------------------------

# `source_ref` is only set on connector-ingested documents, and it is the sole
# guard against re-ingesting the same mailbox attachment. The filter has to be
# `$type: "string"` rather than `$exists: True`, which would also match an
# explicit null and collapse every manual upload onto one key; partial filters
# do not accept `$ne`.
_INDEXES: dict[str, list[dict]] = {
    "documents": [
        {"keys": [("status", ASCENDING)], "name": "idx_documents_status"},
        {"keys": [("created_at", DESCENDING)], "name": "idx_documents_created_at"},
        {"keys": [("source", ASCENDING)], "name": "idx_documents_source"},
        {"keys": [("country", ASCENDING)], "name": "idx_documents_country"},
        {"keys": [("source_connector_id", ASCENDING)], "name": "idx_documents_source_connector"},
        {
            "keys": [("source_connector_id", ASCENDING), ("source_ref", ASCENDING)],
            "name": "ux_documents_source_ref",
            "unique": True,
            "partialFilterExpression": {"source_ref": {"$type": "string"}},
        },
    ],
    "processing_logs": [
        {"keys": [("document_id", ASCENDING), ("created_at", ASCENDING)], "name": "idx_processing_logs_doc"},
    ],
    "brs_documents": [
        {"keys": [("status", ASCENDING)], "name": "idx_brs_documents_status"},
        {"keys": [("created_at", DESCENDING)], "name": "idx_brs_documents_created_at"},
    ],
    "brs_processing_logs": [
        {"keys": [("document_id", ASCENDING), ("created_at", ASCENDING)], "name": "idx_brs_processing_logs_doc"},
    ],
    "connector_connections": [
        {"keys": [("status", ASCENDING), ("created_at", DESCENDING)], "name": "idx_connector_connections_status"},
        {"keys": [("provider", ASCENDING), ("oauth_state", ASCENDING)], "name": "idx_connector_connections_state"},
    ],
    "connector_sync_runs": [
        {"keys": [("connection_id", ASCENDING), ("started_at", DESCENDING)], "name": "idx_connector_runs_conn"},
        {"keys": [("status", ASCENDING)], "name": "idx_connector_runs_status"},
    ],
    "connector_sync_items": [
        {"keys": [("run_id", ASCENDING), ("created_at", ASCENDING)], "name": "idx_connector_items_run"},
        {
            "keys": [
                ("connection_id", ASCENDING),
                ("external_message_id", ASCENDING),
                ("part_index", ASCENDING),
            ],
            "name": "idx_connector_items_dedupe",
        },
        {"keys": [("document_id", ASCENDING)], "name": "idx_connector_items_document"},
    ],
}


# A schemaless store turns what were NOT NULL violations into silent nulls, so
# the fields the pipeline cannot run without are asserted here instead.
# `moderate` leaves documents that already fail the schema updatable, which
# matters if a payload shape is tightened later; inserts are always validated.
_VALIDATORS: dict[str, dict] = {
    "documents": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["filename", "status", "country", "source"],
            "properties": {
                "filename": {"bsonType": "string"},
                "status": {"bsonType": "string"},
                "country": {"enum": ["INDIA", "USA"]},
                "source": {"bsonType": "string"},
                "source_ref": {"bsonType": ["string", "null"]},
                "source_connector_id": {"bsonType": ["string", "null"]},
            },
        }
    },
    "brs_documents": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["filename", "status"],
            "properties": {
                "filename": {"bsonType": "string"},
                "status": {"bsonType": "string"},
            },
        }
    },
    "connector_connections": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["provider", "status", "country"],
            "properties": {
                "provider": {"bsonType": "string"},
                "status": {"bsonType": "string"},
                "country": {"enum": ["INDIA", "USA"]},
            },
        }
    },
}


async def ensure_indexes() -> None:
    """Create every index and validator the app relies on.

    Safe to run on every boot: create_index is a no-op when an identical index
    already exists under the same name, and collMod overwrites the validator
    with the same definition.
    """
    db = get_database()

    for collection, specs in _INDEXES.items():
        for spec in specs:
            options = {k: v for k, v in spec.items() if k != "keys"}
            await db[collection].create_index(spec["keys"], **options)

    for collection, validator in _VALIDATORS.items():
        try:
            await db.create_collection(collection)
        except CollectionInvalid:
            pass  # already there, which is the normal case
        try:
            await db.command({
                "collMod": collection,
                "validator": validator,
                "validationLevel": "moderate",
                "validationAction": "error",
            })
        except OperationFailure as e:
            # A deployment that withholds collMod should not stop the app from
            # booting; the indexes above are the part that affects correctness.
            logger.warning("Could not apply validator to %s: %s", collection, e)


async def ping() -> bool:
    try:
        await get_client().admin.command("ping")
        return True
    except PyMongoError:
        return False
