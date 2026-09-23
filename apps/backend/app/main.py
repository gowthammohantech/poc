import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load apps/backend/.env before anything else is imported: the service modules
# read their configuration into module-level constants at import time, so a
# later call would leave every os.getenv default in place.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from app.db.mongo import close_client, ensure_indexes, ping
from app.services import blob_service
from app.services import file_storage_service as storage
from app.api.upload_routes import router as upload_router
from app.api.document_routes import router as document_router
from app.api.review_routes import router as review_router
from app.api.export_routes import router as export_router
from app.api.brs_upload_routes import router as brs_upload_router
from app.api.brs_document_routes import router as brs_document_router
from app.api.brs_review_routes import router as brs_review_router
from app.api.brs_export_routes import router as brs_export_router
from app.api.brs_matching_routes import router as brs_matching_router
from app.api.connector_routes import router as connector_router
from app.services.connector_sync_service import reap_stale_runs

# The local cache root. Nothing is mounted from it any more -- see
# serve_upload below -- but it is created at boot so the first upload of a
# fresh container is not the thing that discovers the path is unwritable.
STORAGE_DIR = Path(os.getenv("STORAGE_BASE", "storage/uploads")).parent
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Indexes and validators, not a schema: creating them is idempotent, so
    # this runs on every boot the way the old migration scripts did.
    await ensure_indexes()
    # Idempotent, and a no-op when Azure is not configured.
    await blob_service.ensure_container()
    # Sync runs live in this process, so anything still marked RUNNING was
    # abandoned by a restart. Close them out or the UI waits forever.
    await reap_stale_runs()
    try:
        yield
    finally:
        await close_client()
        await blob_service.close_client()


app = FastAPI(
    title="Invoice OCR Platform API",
    version="1.0.0",
    description="FastAPI backend for invoice OCR processing",
    lifespan=lifespan,
)

_cors_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if os.getenv("FRONTEND_URL"):
    _cors_origins.append(os.getenv("FRONTEND_URL"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/storage/uploads/{file_path:path}")
async def serve_upload(file_path: str):
    """Serve a page render or original, from the local cache or from Blob.

    This replaced a StaticFiles mount. The review UI builds these URLs from
    the paths in Mongo, so the shape has to stay `/storage/uploads/<key>` --
    but a container that has never processed the document has nothing on disk
    to mount, so a miss falls through to the blob of the same key.
    """
    local = storage.local_path_for_key(file_path)
    # file_path comes from the request, so confirm it did not climb out of
    # the storage root before touching it.
    if storage.is_within_storage(local) and local.is_file():
        return FileResponse(local, media_type=blob_service.content_type_for(local.name))

    streamed = await blob_service.open_stream(file_path)
    if streamed is None:
        raise HTTPException(status_code=404, detail="File not found")
    chunks, content_type, size = streamed
    return StreamingResponse(
        chunks,
        media_type=content_type,
        headers={"Content-Length": str(size), "Cache-Control": "private, max-age=3600"},
    )

app.include_router(upload_router, prefix="/api/documents", tags=["Upload"])
app.include_router(document_router, prefix="/api/documents", tags=["Documents"])
app.include_router(review_router, prefix="/api/documents", tags=["Review"])
app.include_router(export_router, prefix="/api/documents", tags=["Export"])

app.include_router(brs_upload_router, prefix="/api/brs", tags=["BRS Upload"])
app.include_router(brs_document_router, prefix="/api/brs", tags=["BRS Documents"])
app.include_router(brs_review_router, prefix="/api/brs", tags=["BRS Review"])
app.include_router(brs_export_router, prefix="/api/brs", tags=["BRS Export"])
app.include_router(brs_matching_router, prefix="/api/brs", tags=["BRS Matching"])

app.include_router(connector_router, prefix="/api/connectors", tags=["Connectors"])


@app.get("/api/health")
async def health():
    # Liveness stays independent of the database: a Mongo outage should be
    # visible here, not turn into a restart loop against the deploy policy.
    return {
        "status": "ok",
        "service": "invoice-ocr-backend",
        "database": "ok" if await ping() else "unreachable",
    }
