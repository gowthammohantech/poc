"""Which mailbox attachments a sync passes over before downloading them.

This filter runs on metadata alone — filename, MIME type, byte count — so it
is cheap, and correspondingly blunt. Its failure mode is not a crash but a
silent one: an invoice that never appears, counted as something the sync was
right to ignore. These cases pin the boundary.
"""

import pytest

from app.services.connectors import MailAttachmentRef
from app.services import connector_sync_service as sync


def _ref(filename="invoice.pdf", mime_type="application/pdf", size_bytes=72206,
         is_inline=False) -> MailAttachmentRef:
    return MailAttachmentRef(
        message_id="msg-1",
        attachment_id="att-1",
        part_index=0,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        is_inline=is_inline,
    )


class TestSkipReason:
    def test_an_ordinary_pdf_is_fetched(self):
        assert sync._skip_reason(_ref()) is None

    def test_inline_pdf_is_still_fetched(self):
        """Regression: a Gmail-composed invoice arrives flagged inline.

        The flag exists to drop logos. A PDF is never a logo, whatever the
        headers say, so the flag must not reach it.
        """
        assert sync._skip_reason(_ref(is_inline=True)) is None

    def test_inline_image_is_skipped(self):
        ref = _ref(filename="logo.png", mime_type="image/png", is_inline=True)
        assert sync._skip_reason(ref) == sync.ITEM_SKIPPED_INLINE

    def test_scanned_invoice_image_is_fetched_when_not_inline(self):
        ref = _ref(filename="scan.jpg", mime_type="image/jpeg")
        assert sync._skip_reason(ref) is None

    def test_tiny_attachment_is_skipped(self):
        assert sync._skip_reason(_ref(size_bytes=4096)) == sync.ITEM_SKIPPED_INLINE

    def test_oversized_attachment_is_unsupported(self):
        ref = _ref(size_bytes=sync._max_bytes() + 1)
        assert sync._skip_reason(ref) == sync.ITEM_SKIPPED_UNSUPPORTED

    def test_wrong_file_type_is_unsupported(self):
        ref = _ref(filename="invite.ics", mime_type="text/calendar", size_bytes=2047)
        assert sync._skip_reason(ref) == sync.ITEM_SKIPPED_UNSUPPORTED

    def test_file_type_is_judged_before_size(self):
        """A 2KB .ics is the wrong sort of file, not a small one."""
        ref = _ref(filename="invite.ics", mime_type="text/calendar", size_bytes=100)
        assert sync._skip_reason(ref) == sync.ITEM_SKIPPED_UNSUPPORTED

    def test_unknown_size_does_not_disqualify(self):
        """Providers do not always report a size; that is not grounds to skip."""
        assert sync._skip_reason(_ref(size_bytes=0)) is None

    @pytest.mark.parametrize("suffix", [".PDF", ".Jpg", ".HEIC"])
    def test_suffix_case_is_ignored(self, suffix):
        assert sync._skip_reason(_ref(filename=f"invoice{suffix}")) is None


class TestSkipCounters:
    def test_every_skip_reason_has_a_counter(self):
        """A reason with no counter would raise KeyError mid-sync."""
        reasons = {sync.ITEM_SKIPPED_UNSUPPORTED, sync.ITEM_SKIPPED_INLINE}
        assert reasons == set(sync._SKIP_COUNTERS)

    def test_counters_are_columns_the_run_record_totals(self):
        for column in sync._SKIP_COUNTERS.values():
            assert column in sync._TOTAL_COLUMNS
