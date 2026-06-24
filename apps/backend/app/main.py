import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.db.database import init_db
from app.api.upload_routes import router as upload_router
from app.api.document_routes import router as document_router
from app.api.review_routes import router as review_router
from app.api.export_routes import router as export_router

STORAGE_DIR = Path(os.getenv("STORAGE_BASE", "storage/uploads")).parent
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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

# Serve uploaded files from the same configurable location used by the upload
# service. In production STORAGE_BASE is /app/data/storage/uploads, so mounting
# the relative ./storage directory would otherwise return 404 for every page.
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

app.include_router(upload_router, prefix="/api/documents", tags=["Upload"])
app.include_router(document_router, prefix="/api/documents", tags=["Documents"])
app.include_router(review_router, prefix="/api/documents", tags=["Review"])
app.include_router(export_router, prefix="/api/documents", tags=["Export"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "invoice-ocr-backend"}
