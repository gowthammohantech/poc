"""The India rules must come through the ruleset refactor unchanged.

Before validation_rulesets existed, two different rule-name lists were written
out by hand in two places and they did not agree: processing_service used three
names to split error messages from warnings, while determine_validation_status
used six to decide the document status. Both are preserved deliberately, so
these tests pin both -- a well-meaning "cleanup" that merges them would change
which invoices come back INVALID.
"""

import pytest

from app.schemas.validation_schema import RuleCheck
from app.services import validation_service
from app.services.validation_rulesets import (
    INDIA_INVOICE_RULESET,
    US_SA_RULESET,
    US_SO_RULESET,
    US_UNKNOWN_RULESET,
    get_ruleset,
)


def _failed(rule: str) -> RuleCheck:
    return RuleCheck(rule=rule, passed=False, message=f"{rule} failed", field=None)


def _passed(rule: str) -> RuleCheck:
    return RuleCheck(rule=rule, passed=True, message=f"{rule} ok", field=None)


class TestIndiaRuleSetIsUnchanged:
    def test_message_partition_uses_the_original_three_names(self):
        assert INDIA_INVOICE_RULESET.critical_for_messages == frozenset({
            "invoice_number_present", "invoice_date_valid", "total_math_check",
        })

    def test_status_uses_the_original_six_names(self):
        assert INDIA_INVOICE_RULESET.critical_for_status == frozenset({
            "invoice_number_present", "invoice_date_valid", "total_math_check",
            "vendor_gstin_format", "customer_gstin_format", "cgst_igst_mutually_exclusive",
        })

    def test_gstin_failure_is_a_warning_message_but_still_invalidates(self):
        """The two lists diverge here, exactly as they did before the refactor."""
        checks = [_failed("vendor_gstin_format")]
        warnings, errors = INDIA_INVOICE_RULESET.partition_messages(checks)

        assert warnings == ["vendor_gstin_format failed"]
        assert errors == []
        assert INDIA_INVOICE_RULESET.determine_status(checks, []) == "INVALID"

    def test_total_math_failure_is_an_error_message_and_invalidates(self):
        checks = [_failed("total_math_check")]
        warnings, errors = INDIA_INVOICE_RULESET.partition_messages(checks)

        assert warnings == []
        assert errors == ["total_math_check failed"]
        assert INDIA_INVOICE_RULESET.determine_status(checks, []) == "INVALID"

    def test_passing_checks_are_never_reported(self):
        warnings, errors = INDIA_INVOICE_RULESET.partition_messages(
            [_passed("invoice_number_present"), _passed("ifsc_format")]
        )
        assert (warnings, errors) == ([], [])


class TestStatusLadder:
    def test_all_clear_is_valid(self):
        assert INDIA_INVOICE_RULESET.determine_status([_passed("ifsc_format")], []) == "VALID"

    def test_a_non_critical_failure_needs_review(self):
        assert INDIA_INVOICE_RULESET.determine_status([_failed("ifsc_format")], []) == "NEEDS_REVIEW"

    def test_an_llm_fail_alone_needs_review(self):
        llm = [{"check": "totals_plausibility", "result": "FAIL"}]
        assert INDIA_INVOICE_RULESET.determine_status([], llm) == "NEEDS_REVIEW"

    def test_an_llm_uncertain_does_not_downgrade(self):
        llm = [{"check": "totals_plausibility", "result": "UNCERTAIN"}]
        assert INDIA_INVOICE_RULESET.determine_status([], llm) == "VALID"


class TestDetermineValidationStatusWrapper:
    """The public function keeps its signature and its India default."""

    def test_defaults_to_the_india_ruleset(self):
        assert validation_service.determine_validation_status(
            [_failed("vendor_gstin_format")], []
        ) == "INVALID"

    def test_accepts_an_explicit_ruleset(self):
        assert validation_service.determine_validation_status(
            [_failed("vendor_gstin_format")], [], US_SO_RULESET
        ) == "NEEDS_REVIEW", "a GST rule name means nothing to a US purchase order"


class TestRuleSetSelection:
    @pytest.mark.parametrize("country,doc_type,expected", [
        ("INDIA", None, INDIA_INVOICE_RULESET),
        ("india", "SA", INDIA_INVOICE_RULESET),
        (None, None, INDIA_INVOICE_RULESET),
        ("MARS", "SA", INDIA_INVOICE_RULESET),
        ("USA", "SA", US_SA_RULESET),
        ("usa", "sa", US_SA_RULESET),
        ("USA", "SO", US_SO_RULESET),
        ("USA", "UNKNOWN", US_UNKNOWN_RULESET),
        ("USA", None, US_UNKNOWN_RULESET),
    ])
    def test_picks_the_right_ruleset(self, country, doc_type, expected):
        assert get_ruleset(country, doc_type) is expected

    def test_unclassified_us_documents_are_never_invalid(self):
        """We do not know what the document is, so we do not assert it is wrong."""
        checks = [_failed("so_order_number_present"), _failed("so_line_items_present")]
        assert US_UNKNOWN_RULESET.determine_status(checks, []) == "NEEDS_REVIEW"

        warnings, errors = US_UNKNOWN_RULESET.partition_messages(checks)
        assert errors == []
        assert len(warnings) == 2
