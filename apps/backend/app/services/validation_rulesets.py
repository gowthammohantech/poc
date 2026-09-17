"""Which deterministic rules apply to a document, and which of them are fatal.

Two different rule-name lists were previously hardcoded in two places, and they
did not agree:

  * processing_service partitioned the error/warning *message* lists using a
    narrow set of three rules;
  * validation_service.determine_validation_status decided the document *status*
    using a wider set that also covered the GST rules.

Both behaviours are deliberate-looking and both are preserved here verbatim, as
`critical_for_messages` and `critical_for_status`. Collapsing them into one set
would change which documents come back INVALID, so they stay distinct.

Adding a regime means adding a RuleSet, not editing the orchestrator.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from app.schemas.validation_schema import RuleCheck
from app.services import us_validation_service, validation_service

COUNTRY_INDIA = "INDIA"
COUNTRY_USA = "USA"

DOC_TYPE_SO = "SO"
DOC_TYPE_SA = "SA"
DOC_TYPE_INV = "INV"
DOC_TYPE_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuleSet:
    """The deterministic rules for one document regime."""

    name: str
    run: Callable[[Dict[str, Any]], List[RuleCheck]]
    # Failures of these rules are reported as errors rather than warnings.
    critical_for_messages: FrozenSet[str]
    # Failures of these rules make the document INVALID.
    critical_for_status: FrozenSet[str]

    def partition_messages(self, rule_checks: List[RuleCheck]) -> tuple[List[str], List[str]]:
        """Split failed checks into (warnings, errors) message lists."""
        failed = [c for c in rule_checks if not c.passed]
        warnings = [c.message for c in failed if c.rule not in self.critical_for_messages]
        errors = [c.message for c in failed if c.rule in self.critical_for_messages]
        return warnings, errors

    def determine_status(self, rule_checks: List[RuleCheck], llm_checks: List[dict]) -> str:
        errors = [c for c in rule_checks if not c.passed and c.rule in self.critical_for_status]
        warnings = [c for c in rule_checks if not c.passed and c not in errors]
        llm_flags = [c for c in llm_checks if c.get("result") == "FAIL"]

        if errors:
            return "INVALID"
        if warnings or llm_flags:
            return "NEEDS_REVIEW"
        return "VALID"


INDIA_INVOICE_RULESET = RuleSet(
    name="india_invoice",
    run=validation_service.run_all_rules,
    critical_for_messages=frozenset({
        "invoice_number_present", "invoice_date_valid", "total_math_check",
    }),
    critical_for_status=frozenset({
        "invoice_number_present", "invoice_date_valid", "total_math_check",
        "vendor_gstin_format", "customer_gstin_format", "cgst_igst_mutually_exclusive",
    }),
)

US_SA_RULESET = RuleSet(
    name="us_shipping_authorization",
    run=us_validation_service.run_sa_rules,
    # A release with no parts or a misaligned schedule cannot be acted on, so
    # those are errors. Everything else — a missing supplier code, a quantity
    # that is not a multiple of the standard pack — is worth a human's eye
    # without blocking the document.
    critical_for_messages=frozenset({
        "sa_parts_present", "sa_schedule_columns_present", "sa_schedule_width_match",
    }),
    critical_for_status=frozenset({
        "sa_parts_present", "sa_schedule_columns_present", "sa_schedule_width_match",
    }),
)

US_SO_RULESET = RuleSet(
    name="us_purchase_order",
    run=us_validation_service.run_so_rules,
    critical_for_messages=frozenset({
        "so_order_number_present", "so_order_date_valid", "so_line_items_present",
        "so_totals_math_check",
    }),
    critical_for_status=frozenset({
        "so_order_number_present", "so_order_date_valid", "so_line_items_present",
        "so_totals_math_check",
    }),
)

US_INV_RULESET = RuleSet(
    name="us_invoice",
    run=us_validation_service.run_inv_rules,
    # The fields an invoice cannot be paid or matched without, and totals that
    # have to reconcile because the total is what gets paid. A line that does
    # not multiply out, a subtotal that disagrees with its lines, or a due date
    # before the invoice date all send the document to a human instead: each
    # is often a vendor's own rounding or a single misread, not a bad invoice.
    critical_for_messages=frozenset({
        "inv_invoice_number_present", "inv_invoice_date_valid", "inv_line_items_present",
        "inv_total_present", "inv_totals_math_check",
    }),
    critical_for_status=frozenset({
        "inv_invoice_number_present", "inv_invoice_date_valid", "inv_line_items_present",
        "inv_total_present", "inv_totals_math_check",
    }),
)


# A document the classifier could not place still gets read as a purchase
# order, because that degrades to a mostly-empty form rather than a misaligned
# matrix. Nothing is fatal, though: we do not know what the document is, so
# calling it INVALID would be asserting more than we know. Every failure lands
# as a warning, which puts the document in NEEDS_REVIEW where a human can set
# the type and re-process.
US_UNKNOWN_RULESET = RuleSet(
    name="us_unclassified",
    run=us_validation_service.run_so_rules,
    critical_for_messages=frozenset(),
    critical_for_status=frozenset(),
)


def get_ruleset(country: Optional[str], doc_type: Optional[str] = None) -> RuleSet:
    """Pick the rules for a document. Anything unrecognised falls back to India."""
    if (country or COUNTRY_INDIA).upper() != COUNTRY_USA:
        return INDIA_INVOICE_RULESET
    normalized = (doc_type or DOC_TYPE_UNKNOWN).upper()
    if normalized == DOC_TYPE_SA:
        return US_SA_RULESET
    if normalized == DOC_TYPE_SO:
        return US_SO_RULESET
    if normalized == DOC_TYPE_INV:
        return US_INV_RULESET
    return US_UNKNOWN_RULESET
