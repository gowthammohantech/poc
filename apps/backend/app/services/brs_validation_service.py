from typing import List, Dict, Any
from dataclasses import dataclass

MATH_TOLERANCE = 0.05

BANK_SIDE_ITEM_TYPES = {"DEPOSIT_IN_TRANSIT", "OUTSTANDING_CHECK", "BANK_ERROR"}
BOOK_SIDE_ITEM_TYPES = {"BANK_CHARGE", "BANK_INTEREST", "NSF_CHECK", "DIRECT_DEPOSIT", "BOOK_ERROR"}

CRITICAL_RULES = {"bank_balance_math", "book_balance_math", "balances_reconcile"}


@dataclass
class BrsRuleCheck:
    rule: str
    passed: bool
    message: str
    field: str = None

    def to_dict(self) -> dict:
        return {"rule": self.rule, "passed": self.passed, "message": self.message, "field": self.field}


def run_all_brs_rules(brs_output: Dict[str, Any]) -> List[BrsRuleCheck]:
    brs = brs_output.get("brs", brs_output)
    doc_info = brs.get("document_info", {})
    balances = brs.get("balances", {})
    bank_items = brs.get("bank_side_items", [])
    book_items = brs.get("book_side_items", [])
    adj_bank = brs.get("adjusted_bank_balance")
    adj_book = brs.get("adjusted_book_balance")

    checks = []
    checks.extend(_check_completeness(doc_info))
    checks.extend(_check_bank_balance_math(balances, bank_items, adj_bank))
    checks.extend(_check_book_balance_math(balances, book_items, adj_book))
    checks.extend(_check_balances_reconcile(adj_bank, adj_book))
    checks.extend(_check_item_side_classification(bank_items, book_items))
    checks.extend(_check_amounts_non_negative(bank_items, book_items))
    return checks


def _check_completeness(doc_info: dict) -> List[BrsRuleCheck]:
    checks = []
    for field in ("company_name", "account_number", "statement_period_start", "statement_period_end"):
        if not doc_info.get(field):
            checks.append(BrsRuleCheck(
                rule=f"{field}_present", passed=False,
                message=f"{field.replace('_', ' ').title()} is missing",
                field=f"document_info.{field}"
            ))
        else:
            checks.append(BrsRuleCheck(
                rule=f"{field}_present", passed=True,
                message=f"{field.replace('_', ' ').title()} is present",
                field=f"document_info.{field}"
            ))
    return checks


def _check_bank_balance_math(balances: dict, bank_items: list, adj_bank) -> List[BrsRuleCheck]:
    opening = balances.get("opening_balance_bank")
    if opening is None or not bank_items:
        return []

    computed = opening
    for item in bank_items:
        amount = item.get("amount", 0) or 0
        effect = item.get("effect", "")
        if effect == "ADD_TO_BANK":
            computed += amount
        elif effect == "DEDUCT_FROM_BANK":
            computed -= amount

    if adj_bank is None:
        return [BrsRuleCheck(
            rule="bank_balance_math", passed=True,
            message=f"Computed adjusted bank balance: {computed:.2f} (not stated in document)",
            field="adjusted_bank_balance"
        )]

    diff = abs(computed - adj_bank)
    passed = diff <= MATH_TOLERANCE
    return [BrsRuleCheck(
        rule="bank_balance_math", passed=passed,
        message=(
            f"opening_bank({opening}) ± items = {computed:.2f}, "
            f"stated adjusted_bank = {adj_bank:.2f}, diff = {diff:.4f}"
        ),
        field="adjusted_bank_balance"
    )]


def _check_book_balance_math(balances: dict, book_items: list, adj_book) -> List[BrsRuleCheck]:
    opening = balances.get("opening_balance_book")
    if opening is None or not book_items:
        return []

    computed = opening
    for item in book_items:
        amount = item.get("amount", 0) or 0
        effect = item.get("effect", "")
        if effect == "ADD_TO_BOOK":
            computed += amount
        elif effect == "DEDUCT_FROM_BOOK":
            computed -= amount

    if adj_book is None:
        return [BrsRuleCheck(
            rule="book_balance_math", passed=True,
            message=f"Computed adjusted book balance: {computed:.2f} (not stated in document)",
            field="adjusted_book_balance"
        )]

    diff = abs(computed - adj_book)
    passed = diff <= MATH_TOLERANCE
    return [BrsRuleCheck(
        rule="book_balance_math", passed=passed,
        message=(
            f"opening_book({opening}) ± items = {computed:.2f}, "
            f"stated adjusted_book = {adj_book:.2f}, diff = {diff:.4f}"
        ),
        field="adjusted_book_balance"
    )]


def _check_balances_reconcile(adj_bank, adj_book) -> List[BrsRuleCheck]:
    if adj_bank is None or adj_book is None:
        return []
    diff = abs(adj_bank - adj_book)
    passed = diff <= MATH_TOLERANCE
    return [BrsRuleCheck(
        rule="balances_reconcile", passed=passed,
        message=(
            f"adjusted_bank({adj_bank:.2f}) vs adjusted_book({adj_book:.2f}), diff = {diff:.4f}"
        ),
        field="adjusted_bank_balance"
    )]


def _check_item_side_classification(bank_items: list, book_items: list) -> List[BrsRuleCheck]:
    checks = []
    for item in bank_items:
        itype = item.get("item_type", "")
        if itype in BOOK_SIDE_ITEM_TYPES:
            checks.append(BrsRuleCheck(
                rule="bank_items_side_check", passed=False,
                message=f"Item type '{itype}' belongs in book_side_items, not bank_side_items",
                field="bank_side_items"
            ))
    for item in book_items:
        itype = item.get("item_type", "")
        if itype in BANK_SIDE_ITEM_TYPES:
            checks.append(BrsRuleCheck(
                rule="book_items_side_check", passed=False,
                message=f"Item type '{itype}' belongs in bank_side_items, not book_side_items",
                field="book_side_items"
            ))
    return checks


def _check_amounts_non_negative(bank_items: list, book_items: list) -> List[BrsRuleCheck]:
    checks = []
    for items, side in [(bank_items, "bank"), (book_items, "book")]:
        for i, item in enumerate(items):
            amount = item.get("amount")
            if amount is not None and amount < 0:
                checks.append(BrsRuleCheck(
                    rule="amounts_non_negative", passed=False,
                    message=f"{side}_side_items[{i}] has negative amount {amount}",
                    field=f"{side}_side_items"
                ))
    return checks


def determine_brs_validation_status(rule_checks: List[BrsRuleCheck], llm_checks: List[dict]) -> str:
    critical_failures = [c for c in rule_checks if not c.passed and c.rule in CRITICAL_RULES]
    warnings = [c for c in rule_checks if not c.passed and c.rule not in CRITICAL_RULES]
    llm_flags = [c for c in llm_checks if c.get("result") == "FAIL"]

    if critical_failures:
        return "INVALID"
    if warnings or llm_flags:
        return "NEEDS_REVIEW"
    return "VALID"
