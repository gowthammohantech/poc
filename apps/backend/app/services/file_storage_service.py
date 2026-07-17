import os
import aiofiles
from pathlib import Path
from fastapi import UploadFile

STORAGE_BASE = Path(os.getenv("STORAGE_BASE", "storage/uploads"))


def get_original_dir(document_id: str) -> Path:
    p = STORAGE_BASE / document_id / "original"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_page_dir(document_id: str) -> Path:
    p = STORAGE_BASE / document_id / "pages"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_preprocessed_dir(document_id: str) -> Path:
    p = STORAGE_BASE / document_id / "preprocessed"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def save_upload(document_id: str, file: UploadFile) -> str:
    original_dir = get_original_dir(document_id)
    filename = file.filename or "upload"
    dest = original_dir / filename
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)
    return str(dest)


def path_to_public_url(path: str) -> str:
    normalized = path.replace("\\", "/")
    marker = "storage/uploads/"
    if marker in normalized:
        rel = normalized[normalized.index(marker):]
        return f"/{rel}"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def get_page_url(document_id: str, filename: str) -> str:
    return f"/storage/uploads/{document_id}/pages/{filename}"


def get_preprocessed_url(document_id: str, filename: str) -> str:
    return f"/storage/uploads/{document_id}/preprocessed/{filename}"
