import os
import re
import aiofiles
from pathlib import Path
from fastapi import UploadFile

STORAGE_BASE = Path(os.getenv("STORAGE_BASE", "storage/uploads"))

_UNSAFE_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_MAX_FILENAME_LEN = 180


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


def safe_filename(name: str | None) -> str:
    """Reduce a caller-supplied name to a bare, writable filename.

    Email attachment names reach us straight from the sender, so this has to
    hold up against deliberate path traversal, not just awkward characters.
    """
    candidate = (name or "").replace("\\", "/").split("/")[-1].strip()
    candidate = _UNSAFE_CHARS.sub("_", candidate).strip(". ")
    if not candidate or candidate in {".", ".."}:
        return "upload"
    if len(candidate) > _MAX_FILENAME_LEN:
        stem, dot, suffix = candidate.rpartition(".")
        if dot and len(suffix) <= 10:
            candidate = stem[: _MAX_FILENAME_LEN - len(suffix) - 1] + "." + suffix
        else:
            candidate = candidate[:_MAX_FILENAME_LEN]
    return candidate


async def save_bytes(document_id: str, filename: str, content: bytes) -> str:
    original_dir = get_original_dir(document_id)
    dest = original_dir / safe_filename(filename)
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    return str(dest)


async def save_upload(document_id: str, file: UploadFile) -> str:
    return await save_bytes(document_id, file.filename or "upload", await file.read())


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
