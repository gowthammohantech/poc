"""Where uploaded files live, and how the rest of the app gets at them.

Two tiers. Azure Blob is the durable record; the directory tree under
STORAGE_BASE is a local working cache, because every library in the pipeline
(poppler, OpenCV, Tesseract, PaddleOCR) needs a real file on a real disk.

A blob's key is the file's path relative to STORAGE_BASE, so the paths already
stored in Mongo identify the blob too and nothing had to be migrated. Writes go
to disk first and are mirrored up; reads go through ensure_local, which pulls a
file back down when the cache does not have it.

With Azure unconfigured this degrades to exactly the previous behaviour: local
disk, nothing else. See app.services.blob_service.
"""

import logging
import os
import re
import shutil
from pathlib import Path

import aiofiles
from fastapi import UploadFile

from app.services import blob_service as blob

logger = logging.getLogger(__name__)

STORAGE_BASE = Path(os.getenv("STORAGE_BASE", "storage/uploads"))

_UNSAFE_CHARS = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_MAX_FILENAME_LEN = 180
# Paths recorded before Azure, or by a machine with a different STORAGE_BASE,
# are still rooted at this fragment. It is the fallback for deriving a key.
_LEGACY_MARKER = "storage/uploads/"


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


# -- local path <-> blob key ------------------------------------------------


def blob_key(path: str | Path) -> str:
    """The blob key for a stored file: its path relative to STORAGE_BASE."""
    normalized = str(path).replace("\\", "/")
    base = str(STORAGE_BASE).replace("\\", "/").rstrip("/")
    if base and normalized.startswith(base + "/"):
        return normalized[len(base) + 1:]
    if _LEGACY_MARKER in normalized:
        return normalized[normalized.index(_LEGACY_MARKER) + len(_LEGACY_MARKER):]
    return normalized.lstrip("/")


def local_path_for_key(key: str) -> Path:
    return STORAGE_BASE / key.lstrip("/")


def is_within_storage(path: Path) -> bool:
    """Guard for anything derived from a request path."""
    try:
        return path.resolve().is_relative_to(STORAGE_BASE.resolve())
    except (OSError, ValueError):
        return False


# -- writes -----------------------------------------------------------------


async def save_bytes(document_id: str, filename: str, content: bytes) -> str:
    """Write the original to the cache and mirror it to Blob.

    An upload failure is raised, not swallowed. The original is the one file
    nothing else can be derived from, so accepting a document we could not
    durably store would trade a visible error for silent loss on the next
    redeploy.
    """
    original_dir = get_original_dir(document_id)
    dest = original_dir / safe_filename(filename)
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
    await blob.upload_bytes(blob_key(dest), content, content_type=blob.content_type_for(dest.name))
    return str(dest)


async def save_upload(document_id: str, file: UploadFile) -> str:
    return await save_bytes(document_id, file.filename or "upload", await file.read())


async def mirror_paths(paths: list[str]) -> int:
    """Mirror files another service wrote straight to disk (page renders, preprocessed images).

    Best effort by design: these are all reproducible from the original, so a
    transient Blob failure is logged and the pipeline carries on rather than
    failing a document that is otherwise fine.
    """
    if not blob.is_enabled():
        return 0
    uploaded = 0
    for path in paths:
        try:
            if await blob.upload_file(blob_key(path), path):
                uploaded += 1
        except Exception as e:
            logger.warning("Could not mirror %s to blob storage: %s", path, e)
    return uploaded


# -- reads ------------------------------------------------------------------


async def ensure_local(path: str) -> str:
    """Return a path that exists on disk, fetching from Blob if the cache lacks it.

    This is the normal path after a redeploy: Mongo still points at files the
    new container has never seen.
    """
    if not path:
        return path
    if Path(path).is_file():
        return path

    key = blob_key(path)
    dest = local_path_for_key(key)
    if dest.is_file():
        return str(dest)
    if await blob.download_to(key, dest):
        return str(dest)
    # Left as-is so the caller's own "cannot read image" error still fires.
    return path


async def ensure_local_many(paths: list[str]) -> list[str]:
    return [await ensure_local(p) for p in paths]


# -- deletes ----------------------------------------------------------------


async def delete_document_files(document_id: str) -> None:
    """Remove a document's cache directory and every blob under its prefix."""
    folder = STORAGE_BASE / document_id
    # Keeps a crafted id from escaping the storage root into the filesystem.
    if folder.resolve().parent == STORAGE_BASE.resolve():
        shutil.rmtree(folder, ignore_errors=True)
    try:
        await blob.delete_prefix(f"{document_id}/")
    except Exception as e:
        logger.warning("Could not delete blobs for document %s: %s", document_id, e)


# -- public URLs ------------------------------------------------------------


def path_to_public_url(path: str) -> str:
    """The URL the review UI loads a stored file from.

    Derived from blob_key rather than by string-matching the path, so the
    suffix of the URL is always exactly the blob key. /storage/uploads/{key}
    is served by main.serve_upload, which looks the key up in the local cache
    and then in Blob -- the two would 404 against each other if this built the
    URL any other way.
    """
    if not path:
        return path
    return f"/storage/uploads/{blob_key(path)}"


def get_page_url(document_id: str, filename: str) -> str:
    return f"/storage/uploads/{document_id}/pages/{filename}"


def get_preprocessed_url(document_id: str, filename: str) -> str:
    return f"/storage/uploads/{document_id}/preprocessed/{filename}"
