import re
from typing import List, Dict, Any
from app.schemas.validation_schema import RuleCheck

GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MATH_TOLERANCE = 0.05  # 5 paise tolerance


def run_all_rules(invoice_json: Dict[str, Any]) -> List[RuleCheck]:
    invoice = invoice_json.get("invoice", {})
    checks = []

    checks.extend(_validate_invoice_number(invoice))
    checks.extend(_validate_invoice_date(invoice))
    checks.extend(_validate_gstin(invoice))
    checks.extend(_validate_line_items(invoice))
    checks.extend(_validate_totals(invoice))
    checks.extend(_validate_tax_consistency(invoice))
    checks.extend(_validate_bank_details(invoice))

    return checks


def _validate_invoice_number(invoice: dict) -> List[RuleCheck]:
    inv_num = invoice.get("invoice_number")
    if inv_num:
        return [RuleCheck(rule="invoice_number_present", passed=True,
                          message="Invoice number is present", field="invoice_number")]
    return [RuleCheck(rule="invoice_number_present", passed=False,
                      message="Invoice number is missing", field="invoice_number")]


def _validate_invoice_date(invoice: dict) -> List[RuleCheck]:
    inv_date = invoice.get("invoice_date")
    if not inv_date:
        return [RuleCheck(rule="invoice_date_valid", passed=False,
                          message="Invoice date is missing", field="invoice_date")]
    if DATE_PATTERN.match(str(inv_date)):
        return [RuleCheck(rule="invoice_date_valid", passed=True,
                          message="Invoice date format is valid", field="invoice_date")]
    return [RuleCheck(rule="invoice_date_valid", passed=False,
                      message=f"Invoice date '{inv_date}' is not in YYYY-MM-DD format",
                      field="invoice_date")]


def _validate_gstin(invoice: dict) -> List[RuleCheck]:
    checks = []
    vendor_gstin = invoice.get("vendor", {}).get("gstin")
    if vendor_gstin:
        valid = bool(GSTIN_PATTERN.match(str(vendor_gstin).strip().upper()))
        checks.append(RuleCheck(
            rule="vendor_gstin_format", passed=valid,
            message=f"Vendor GSTIN '{vendor_gstin}' is {'valid' if valid else 'invalid'}",
            field="vendor.gstin"
        ))
    customer_gstin = invoice.get("customer", {}).get("gstin")
    if customer_gstin:
        valid = bool(GSTIN_PATTERN.match(str(customer_gstin).strip().upper()))
        checks.append(RuleCheck(
            rule="customer_gstin_format", passed=valid,
            message=f"Customer GSTIN '{customer_gstin}' is {'valid' if valid else 'invalid'}",
            field="customer.gstin"
        ))
    return checks


def _validate_line_items(invoice: dict) -> List[RuleCheck]:
    items = invoice.get("line_items", [])
    if not items:
        return [RuleCheck(rule="line_items_present", passed=False,
                          message="No line items found", field="line_items")]

    checks = [RuleCheck(rule="line_items_present", passed=True,
                        message=f"{len(items)} line item(s) found", field="line_items")]

    for i, item in enumerate(items):
        qty = item.get("quantity")
        unit_price = item.get("unit_price")
        total = item.get("total")
        taxable = item.get("taxable_value")

        if qty is not None and unit_price is not None and taxable is not None:
            expected_taxable = qty * unit_price
            diff = abs(expected_taxable - taxable)
            if diff > MATH_TOLERANCE * max(abs(taxable), 1):
                checks.append(RuleCheck(
                    rule=f"line_item_{i+1}_taxable_value",
                    passed=False,
                    message=f"Line {i+1}: qty×unit_price={expected_taxable:.2f} ≠ taxable_value={taxable:.2f}",
                    field=f"line_items[{i}].taxable_value"
                ))
    return checks


def _validate_totals(invoice: dict) -> List[RuleCheck]:
    tax_summary = invoice.get("tax_summary", {})
    subtotal = tax_summary.get("subtotal")
    total_tax = tax_summary.get("total_tax")
    grand_total = tax_summary.get("grand_total")
    round_off = tax_summary.get("round_off") or 0.0

    checks = []
    if subtotal is not None and total_tax is not None and grand_total is not None:
        expected = subtotal + total_tax + round_off
        diff = abs(expected - grand_total)
        passed = diff <= MATH_TOLERANCE
        checks.append(RuleCheck(
            rule="total_math_check",
            passed=passed,
            message=f"subtotal({subtotal}) + tax({total_tax}) + round_off({round_off}) = {expected:.2f}, grand_total = {grand_total:.2f}, diff = {diff:.4f}",
            field="tax_summary"
        ))
    return checks


def _validate_tax_consistency(invoice: dict) -> List[RuleCheck]:
    tax_summary = invoice.get("tax_summary", {})
    cgst = tax_summary.get("cgst_total") or 0.0
    sgst = tax_summary.get("sgst_total") or 0.0
    igst = tax_summary.get("igst_total") or 0.0
    total_tax = tax_summary.get("total_tax")
    checks = []

    if total_tax is not None:
        calculated = cgst + sgst + igst
        diff = abs(calculated - total_tax)
        passed = diff <= MATH_TOLERANCE
        checks.append(RuleCheck(
            rule="tax_components_sum",
            passed=passed,
            message=f"CGST({cgst}) + SGST({sgst}) + IGST({igst}) = {calculated:.2f}, total_tax = {total_tax:.2f}",
            field="tax_summary.total_tax"
        ))

    if cgst > 0 and igst > 0:
        checks.append(RuleCheck(
            rule="cgst_igst_mutually_exclusive",
            passed=False,
            message="Both CGST and IGST are non-zero — only one should apply per invoice",
            field="tax_summary"
        ))

    return checks


def _validate_bank_details(invoice: dict) -> List[RuleCheck]:
    bank = invoice.get("bank_details", {})
    ifsc = bank.get("ifsc")
    if ifsc:
        valid = bool(IFSC_PATTERN.match(str(ifsc).strip().upper()))
        return [RuleCheck(
            rule="ifsc_format",
            passed=valid,
            message=f"IFSC '{ifsc}' is {'valid' if valid else 'invalid'}",
            field="bank_details.ifsc"
        )]
    return []


def determine_validation_status(rule_checks: List[RuleCheck], llm_checks: List[dict]) -> str:
    errors = [c for c in rule_checks if not c.passed and c.rule in (
        "invoice_number_present", "invoice_date_valid", "total_math_check",
        "vendor_gstin_format", "customer_gstin_format", "cgst_igst_mutually_exclusive"
    )]
    warnings = [c for c in rule_checks if not c.passed and c not in errors]

    llm_flags = [c for c in llm_checks if c.get("result") == "FAIL"]

    if errors:
        return "INVALID"
    if warnings or llm_flags:
        return "NEEDS_REVIEW"
    return "VALID"
