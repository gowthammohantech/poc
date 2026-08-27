"""Tests for the Gmail parsing helpers.

These two functions are where the bugs live — nested multipart payloads and
Gmail's unpadded base64url — and both are pure, so they can be exercised
without a Google account or a network.
"""

import base64

from app.services.connectors.gmail_connector import (
    _decode_attachment_data,
    _refs_from_message,
    _walk_parts,
)


def _part(filename="", mime="text/plain", attachment_id=None, size=0, headers=None, parts=None):
    part = {"filename": filename, "mimeType": mime, "body": {"size": size}}
    if attachment_id:
        part["body"]["attachmentId"] = attachment_id
    if headers:
        part["headers"] = headers
    if parts:
        part["parts"] = parts
    return part


class TestDecodeAttachmentData:
    def test_decodes_unpadded_base64url(self):
        raw = b"%PDF-1.7 invoice bytes"
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        assert _decode_attachment_data(encoded) == raw

    def test_decodes_padded_base64url(self):
        raw = b"four"
        assert _decode_attachment_data(base64.urlsafe_b64encode(raw).decode()) == raw

    def test_handles_url_safe_alphabet(self):
        # Bytes that encode to '-' and '_' rather than '+' and '/'.
        raw = bytes([0xFB, 0xEF, 0xFE])
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        assert "-" in encoded or "_" in encoded
        assert _decode_attachment_data(encoded) == raw

    def test_empty_data_is_empty_bytes(self):
        assert _decode_attachment_data("") == b""

    def test_every_remainder_length_round_trips(self):
        for length in range(1, 13):
            raw = bytes(range(length))
            encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            assert _decode_attachment_data(encoded) == raw


class TestWalkParts:
    def test_finds_attachment_nested_in_multipart(self):
        payload = _part(mime="multipart/mixed", parts=[
            _part(mime="multipart/alternative", parts=[
                _part(mime="text/plain"),
                _part(mime="text/html"),
            ]),
            _part(filename="invoice.pdf", mime="application/pdf",
                  attachment_id="att-1", size=48000),
        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])

        assert len(found) == 1
        assert found[0]["filename"] == "invoice.pdf"
        assert found[0]["attachment_id"] == "att-1"
        assert found[0]["size_bytes"] == 48000
        assert found[0]["is_inline"] is False

    def test_ignores_body_parts_without_a_filename(self):
        payload = _part(mime="multipart/mixed", parts=[
            _part(mime="text/plain", attachment_id="att-body"),
            _part(filename="invoice.pdf", attachment_id="att-1"),
        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert [f["filename"] for f in found] == ["invoice.pdf"]

    def test_gmail_composer_attachment_is_not_inline(self):
        """Gmail stamps a Content-ID on every file attached from its composer.

        Regression: taking that as proof of inlining skipped real invoices —
        the disposition says `attachment` and has the final word.
        """
        payload = _part(filename="5105844084.pdf", mime="application/pdf",
                        attachment_id="att-1", size=72206, headers=[
                            {"name": "Content-Type", "value": 'application/pdf; name="5105844084.pdf"'},
                            {"name": "Content-Disposition", "value": 'attachment; filename="5105844084.pdf"'},
                            {"name": "Content-ID", "value": "<f_mtbaf7js0>"},
                            {"name": "X-Attachment-Id", "value": "f_mtbaf7js0"},
                        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert found[0]["is_inline"] is False

    def test_disposition_beats_content_id_in_either_order(self):
        for headers in (
            [{"name": "Content-ID", "value": "<f_x>"},
             {"name": "Content-Disposition", "value": "attachment; filename=a.pdf"}],
            [{"name": "Content-Disposition", "value": "attachment; filename=a.pdf"},
             {"name": "Content-ID", "value": "<f_x>"}],
        ):
            found: list[dict] = []
            _walk_parts(_part(filename="a.pdf", attachment_id="att-1", headers=headers), found, [0])
            assert found[0]["is_inline"] is False

    def test_flags_inline_images_by_content_id(self):
        payload = _part(mime="multipart/related", parts=[
            _part(filename="logo.png", mime="image/png", attachment_id="att-logo",
                  headers=[{"name": "Content-ID", "value": "<logo@acme>"}]),
            _part(filename="invoice.pdf", attachment_id="att-1"),
        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        by_name = {f["filename"]: f for f in found}
        assert by_name["logo.png"]["is_inline"] is True
        assert by_name["invoice.pdf"]["is_inline"] is False

    def test_flags_inline_by_content_disposition(self):
        payload = _part(filename="sig.png", mime="image/png", attachment_id="att-sig",
                        headers=[{"name": "Content-Disposition", "value": "inline; filename=sig.png"}])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert found[0]["is_inline"] is True

    def test_attached_disposition_is_not_inline(self):
        payload = _part(filename="invoice.pdf", attachment_id="att-1",
                        headers=[{"name": "Content-Disposition", "value": "attachment; filename=invoice.pdf"}])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert found[0]["is_inline"] is False

    def test_part_index_increments_across_the_whole_message(self):
        payload = _part(mime="multipart/mixed", parts=[
            _part(filename="a.pdf", attachment_id="att-a"),
            _part(mime="multipart/related", parts=[
                _part(filename="b.pdf", attachment_id="att-b"),
            ]),
            _part(filename="c.pdf", attachment_id="att-c"),
        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert [(f["filename"], f["part_index"]) for f in found] == [
            ("a.pdf", 0), ("b.pdf", 1), ("c.pdf", 2)
        ]

    def test_message_with_no_attachments_yields_nothing(self):
        payload = _part(mime="multipart/alternative", parts=[
            _part(mime="text/plain"), _part(mime="text/html"),
        ])
        found: list[dict] = []
        _walk_parts(payload, found, [0])
        assert found == []


class TestRefsFromMessage:
    def _message(self):
        return {
            "id": "msg-123",
            "threadId": "thread-9",
            "payload": {
                "headers": [
                    {"name": "From", "value": "billing@acme.example"},
                    {"name": "Subject", "value": "October invoice"},
                    {"name": "Date", "value": "Tue, 14 Oct 2025 09:31:00 +0000"},
                ],
                "mimeType": "multipart/mixed",
                "parts": [
                    _part(mime="text/plain"),
                    _part(filename="invoice.pdf", mime="application/pdf",
                          attachment_id="att-1", size=51200),
                ],
            },
        }

    def test_carries_message_headers_onto_each_attachment(self):
        refs = _refs_from_message(self._message())
        assert len(refs) == 1
        ref = refs[0]
        assert ref.message_id == "msg-123"
        assert ref.thread_id == "thread-9"
        assert ref.from_address == "billing@acme.example"
        assert ref.subject == "October invoice"
        assert ref.received_at.startswith("2025-10-14T09:31:00")

    def test_source_ref_is_stable_and_composed(self):
        ref = _refs_from_message(self._message())[0]
        assert ref.source_ref == "msg-123:0:invoice.pdf"

    def test_unparseable_date_does_not_raise(self):
        message = self._message()
        message["payload"]["headers"] = [{"name": "Date", "value": "not a date"}]
        assert _refs_from_message(message)[0].received_at == ""

    def test_missing_headers_do_not_raise(self):
        message = self._message()
        del message["payload"]["headers"]
        ref = _refs_from_message(message)[0]
        assert ref.from_address == ""
        assert ref.subject == ""
