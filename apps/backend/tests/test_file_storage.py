"""The contract between local paths and blob keys.

Files live in two places: Azure Blob holds the record, the tree under
STORAGE_BASE is a local working cache. These tests pin the part that made the
move cheap -- a blob's key is just its path relative to STORAGE_BASE, so every
path already written to Mongo identifies its blob without a migration.

Azure itself is not exercised here. conftest clears the connection string for
the whole suite, so this asserts the local-only fallback, which is also what an
offline dev machine gets.
"""

import pytest

from app.services import blob_service, file_storage_service as storage


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(storage, "STORAGE_BASE", root)
    return root


class TestBlobKey:
    """The key has to come out the same whatever shape the stored path took."""

    def test_is_the_path_relative_to_the_storage_base(self, base):
        path = base / "doc-1" / "pages" / "page_001.png"
        assert storage.blob_key(path) == "doc-1/pages/page_001.png"

    def test_a_path_from_another_storage_base_still_resolves(self, base):
        """Rows written before the move, or by a container with a different
        STORAGE_BASE, must not be orphaned."""
        legacy = "/app/data/storage/uploads/doc-1/original/invoice.pdf"
        assert storage.blob_key(legacy) == "doc-1/original/invoice.pdf"

    def test_windows_separators_normalise(self, base):
        legacy = r"C:\srv\storage\uploads\doc-1\pages\page_002.png"
        assert storage.blob_key(legacy) == "doc-1/pages/page_002.png"

    def test_round_trips_back_to_a_local_path(self, base):
        path = base / "doc-1" / "original" / "invoice.pdf"
        assert storage.local_path_for_key(storage.blob_key(path)) == path


class TestStorageBoundary:
    """The serving route builds a path straight from the request."""

    def test_accepts_a_path_inside_the_storage_root(self, base):
        assert storage.is_within_storage(base / "doc-1" / "pages" / "p.png")

    def test_rejects_a_traversal_out_of_the_storage_root(self, base):
        assert not storage.is_within_storage(
            storage.local_path_for_key("../../../../etc/passwd")
        )


class TestWithoutAzure:
    """Unconfigured means local disk only, not broken."""

    def test_blob_layer_reports_itself_disabled(self):
        assert blob_service.is_enabled() is False

    async def test_saving_still_writes_the_file(self, base):
        path = await storage.save_bytes("doc-1", "invoice.pdf", b"%PDF-1.4")
        assert (base / "doc-1" / "original" / "invoice.pdf").read_bytes() == b"%PDF-1.4"
        assert storage.blob_key(path) == "doc-1/original/invoice.pdf"

    async def test_a_sender_supplied_name_cannot_escape_the_document_folder(self, base):
        """Attachment names come straight from the sender."""
        path = await storage.save_bytes("doc-1", "../../../evil.pdf", b"x")
        assert storage.is_within_storage(__import__("pathlib").Path(path))
        assert not (base.parent / "evil.pdf").exists()

    async def test_ensure_local_returns_a_file_that_is_already_cached(self, base):
        path = await storage.save_bytes("doc-1", "invoice.pdf", b"%PDF-1.4")
        assert await storage.ensure_local(path) == path

    async def test_ensure_local_hands_back_a_missing_path_untouched(self, base):
        """With nowhere to fetch from, the caller's own read error should fire."""
        missing = str(base / "doc-1" / "pages" / "page_001.png")
        assert await storage.ensure_local(missing) == missing

    async def test_mirroring_is_a_no_op(self, base):
        assert await storage.mirror_paths(["anything"]) == 0

    async def test_delete_removes_the_local_folder(self, base):
        await storage.save_bytes("doc-1", "invoice.pdf", b"%PDF-1.4")
        await storage.delete_document_files("doc-1")
        assert not (base / "doc-1").exists()

    async def test_delete_cannot_be_walked_out_of_the_storage_root(self, base):
        sibling = base.parent / "keep-me"
        sibling.mkdir()
        await storage.delete_document_files("../keep-me")
        assert sibling.exists()


class TestPublicUrls:
    """The review UI builds image URLs from these, so the shape is a contract."""

    def test_a_stored_path_becomes_a_storage_url(self, base):
        path = base / "doc-1" / "pages" / "page_001.png"
        assert storage.path_to_public_url(str(path)) == (
            "/storage/uploads/doc-1/pages/page_001.png"
        )

    def test_the_url_suffix_matches_the_blob_key(self, base):
        """Both sides of the serving route have to agree on the key."""
        path = str(base / "doc-1" / "pages" / "page_001.png")
        url = storage.path_to_public_url(path)
        assert url == f"/storage/uploads/{storage.blob_key(path)}"
