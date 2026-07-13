import unittest

from app.services.brs_validation_service import run_all_brs_rules


def _base_brs(transactions):
    return {
        "brs": {
            "document_info": {
                "company_name": "Acme",
                "account_number": "123456",
                "statement_period_start": "2025-01-01",
                "statement_period_end": "2025-01-31",
            },
            "balances": {},
            "bank_side_items": [],
            "book_side_items": [],
            "bank_transactions": transactions,
            "adjusted_bank_balance": None,
            "adjusted_book_balance": None,
        }
    }


class BrsValidationServiceTests(unittest.TestCase):
    def test_flags_transactions_with_both_debit_and_credit(self):
        checks = run_all_brs_rules(_base_brs([
            {
                "date": "2025-01-02",
                "description": "Ambiguous row",
                "reference_number": None,
                "debit": 100.0,
                "credit": 100.0,
                "balance": 900.0,
            }
        ]))

        self.assertTrue(any(
            check.rule == "bank_transaction_single_side_amount" and not check.passed
            for check in checks
        ))

    def test_flags_running_balance_mismatch(self):
        checks = run_all_brs_rules(_base_brs([
            {
                "date": "2025-01-02",
                "description": "Payment",
                "reference_number": None,
                "debit": 100.0,
                "credit": None,
                "balance": 900.0,
            },
            {
                "date": "2025-01-03",
                "description": "Deposit",
                "reference_number": None,
                "debit": None,
                "credit": 50.0,
                "balance": 980.0,
            },
        ]))

        self.assertTrue(any(
            check.rule == "bank_transaction_running_balance" and not check.passed
            for check in checks
        ))

    def test_valid_transaction_rows_pass_parseability_check(self):
        checks = run_all_brs_rules(_base_brs([
            {
                "date": "2025-01-02",
                "description": "Payment",
                "reference_number": None,
                "debit": 100.0,
                "credit": None,
                "balance": 900.0,
            },
            {
                "date": "2025-01-03",
                "description": "Deposit",
                "reference_number": None,
                "debit": None,
                "credit": 50.0,
                "balance": 950.0,
            },
        ]))

        self.assertTrue(any(
            check.rule == "bank_transaction_rows_parseable" and check.passed
            for check in checks
        ))


if __name__ == "__main__":
    unittest.main()
