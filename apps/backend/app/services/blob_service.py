"""Azure Blob Storage: the durable home for originals, page renders and preprocessed images.

Local disk under STORAGE_BASE stays in the picture, but as a working directory
rather than the record. It has to: poppler shells out to render a PDF, OpenCV
and Tesseract want a real file, and none of them take a byte stream. So every
file written locally is mirrored here, and anything missing from local disk --
the normal state after a redeploy onto a fresh container -- is pulled back on
demand.

A blob's key is its path relative to STORAGE_BASE: `<doc_id>/pages/page_001.png`.
That is deliberate. The paths already recorded in Mongo stay valid exactly as
they are, so moving to Blob needs no migration and no schema change; the same
relative string names both the cache entry and the blob.

With AZURE_STORAGE_CONNECTION_STRING unset every function here turns into a
no-op and the app behaves as it did before, local disk only. That is what the
test suite and an offline dev machine run against, so the Azure path is never
a prerequisite for working on anything else.
"""

import logging
import mimetypes
import os
from pathlib import Path
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONTAINER = "invoice-documents"
# Batch delete caps out at 256 blobs per request.
_DELETE_BATCH = 256

_client = None
_client_conn_str: Optional[str] = None
_container_ready = False


def connection_string() -> str:
    return os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()


def container_name() -> str:
    return os.getenv("AZURE_BLOB_CONTAINER", DEFAULT_CONTAINER).strip() or DEFAULT_CONTAINER


def is_enabled() -> bool:
    """False means every call here is a no-op and local disk is the only store."""
    return bool(connection_string())


def _service_client():
    """The process-wide async client, rebuilt if the configured account changed.

    Mirrors the lazy-global pattern in app.db.mongo for the same reason: config
    is read per call, so a test can redirect the process with setenv alone.
    """
    global _client, _client_conn_str, _container_ready
    from azure.storage.blob.aio import BlobServiceClient

    conn = connection_string()
    if _client is None or _client_conn_str != conn:
        _client = BlobServiceClient.from_connection_string(conn)
        _client_conn_str = conn
        _container_ready = False
    return _client


async def ensure_container() -> None:
    """Create the container if it is not there yet. Safe to call on every boot."""
    global _container_ready
    if not is_enabled() or _container_ready:
        return

    from azure.core.exceptions import ResourceExistsError

    try:
        await _service_client().create_container(container_name())
        logger.info("Created blob container %s", container_name())
    except ResourceExistsError:
        pass
    except Exception as e:
        # A key without container-create rights is fine as long as the container
        # already exists, so this must not stop the app from booting.
        logger.warning("Could not ensure blob container %s: %s", container_name(), e)
    _container_ready = True


async def close_client() -> None:
    global _client, _client_conn_str, _container_ready
    if _client is not None:
        await _client.close()
        _client = None
        _client_conn_str = None
        _container_ready = False


def _blob_client(key: str):
    return _service_client().get_blob_client(container=container_name(), blob=key)


def content_type_for(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


async def upload_bytes(key: str, data: bytes, *, content_type: Optional[str] = None) -> bool:
    """Overwrite the blob at `key`. Returns False when Blob is not configured."""
    if not is_enabled():
        return False

    from azure.storage.blob import ContentSettings

    await ensure_container()
    await _blob_client(key).upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type or content_type_for(key)),
    )
    return True


async def upload_file(key: str, source: Path | str) -> bool:
    path = Path(source)
    if not path.is_file():
        logger.warning("Nothing to upload, %s is not a file", path)
        return False
    return await upload_bytes(key, path.read_bytes(), content_type=content_type_for(path.name))


async def download_to(key: str, dest: Path | str) -> bool:
    """Pull a blob into the local cache. False if Blob is off or the key is gone."""
    if not is_enabled():
        return False

    from azure.core.exceptions import ResourceNotFoundError

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = await _blob_client(key).download_blob()
        # Written under a temporary name so a failed or concurrent download can
        # never leave a half-written image for OpenCV to choke on.
        tmp = dest.with_suffix(dest.suffix + ".partial")
        tmp.write_bytes(await stream.readall())
        tmp.replace(dest)
        return True
    except ResourceNotFoundError:
        return False
    except Exception as e:
        logger.warning("Could not download blob %s: %s", key, e)
        return False


async def exists(key: str) -> bool:
    if not is_enabled():
        return False
    try:
        return await _blob_client(key).exists()
    except Exception as e:
        logger.warning("Could not stat blob %s: %s", key, e)
        return False


async def open_stream(key: str) -> Optional[tuple[AsyncIterator[bytes], str, int]]:
    """Chunks, content type and length for serving a blob without buffering it.

    None when the blob is absent, which the caller turns into a 404.
    """
    if not is_enabled():
        return None

    from azure.core.exceptions import ResourceNotFoundError

    try:
        downloader = await _blob_client(key).download_blob()
    except ResourceNotFoundError:
        return None
    except Exception as e:
        logger.warning("Could not open blob %s: %s", key, e)
        return None

    props = downloader.properties
    declared = (props.content_settings.content_type if props.content_settings else None)

    async def _chunks() -> AsyncIterator[bytes]:
        async for chunk in downloader.chunks():
            yield chunk

    return _chunks(), declared or content_type_for(key), props.size


async def delete_prefix(prefix: str) -> int:
    """Delete every blob under `prefix`. Returns how many were removed."""
    if not is_enabled():
        return 0

    container = _service_client().get_container_client(container_name())
    try:
        names = [b.name async for b in container.list_blobs(name_starts_with=prefix)]
    except Exception as e:
        logger.warning("Could not list blobs under %s: %s", prefix, e)
        return 0

    deleted = 0
    for start in range(0, len(names), _DELETE_BATCH):
        batch = names[start:start + _DELETE_BATCH]
        try:
            # Partial failures come back as results rather than raising, so a
            # single missing blob does not abandon the rest of the batch.
            async for result in await container.delete_blobs(*batch):
                if getattr(result, "status_code", 202) in (202, 404):
                    deleted += 1
        except Exception as e:
            logger.warning("Could not delete %d blob(s) under %s: %s", len(batch), prefix, e)
    return deleted
