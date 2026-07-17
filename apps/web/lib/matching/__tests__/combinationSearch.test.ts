import { describe, it, expect } from "vitest";
import { runTwoWaveAssignment, DEFAULT_OPTIONS } from "../voucherScoring";
import { runCombinationSearch } from "../combinationSearch";
import type { BrsTransaction } from "@/types/brs";
import type { LedgerRow } from "@/types/matching";

function txn(overrides: Partial<BrsTransaction> = {}): BrsTransaction {
  return {
    transaction_date: "2024-04-09",
    narration: "misc credit",
    reference_number: null,
    debit: null,
    credit: null,
    balance: null,
    ...overrides,
  };
}

function ledgerRow(overrides: Partial<LedgerRow> = {}): LedgerRow {
  return {
    id: "row",
    transaction_type: "Sales Receipt",
    invoice_no: "SI-0001",
    invoice_date: "2024-04-01",
    invoice_amount: 10000,
    ledger_date: "2024-04-09",
    ledger_voucher: "RV-0001",
    ledger_amount: 10000,
    account_name: null,
    bank_cash_account: null,
    ...overrides,
  };
}

describe("scenario 9: split deposit — one bank credit == sum of two ledger vouchers", () => {
  it("marks both ledger rows as Matched (combined) against the single bank txn", () => {
    const bankTxns = [txn({ credit: 30000 })]; // one deposit covering two invoices
    const ledgerRows = [
      ledgerRow({ id: "a", ledger_amount: 12000, ledger_voucher: "RV-0001" }),
      ledgerRow({ id: "b", ledger_amount: 18000, ledger_voucher: "RV-0002" }),
    ];
    const primary = runTwoWaveAssignment(bankTxns, ledgerRows);
    expect(primary.assignments.size).toBe(0); // neither matches the deposit alone

    const combined = runCombinationSearch(bankTxns, ledgerRows, primary.index, primary, DEFAULT_OPTIONS);
    expect(combined).toHaveLength(1);
    expect(combined[0].bankTxnIndexes).toEqual([0]);
    expect(combined[0].ledgerRowIndexes.sort()).toEqual([0, 1]);
    expect(combined[0].score).toBeGreaterThan(0);
  });
});

describe("one ledger row settled via two separate bank transactions", () => {
  it("marks the ledger row Matched (combined) with both bank txn indexes", () => {
    const bankTxns = [txn({ credit: 6000 }), txn({ credit: 4000, transaction_date: "2024-04-10" })];
    const ledgerRows = [ledgerRow({ ledger_amount: 10000 })];
    const primary = runTwoWaveAssignment(bankTxns, ledgerRows);
    expect(primary.assignments.size).toBe(0);

    const combined = runCombinationSearch(bankTxns, ledgerRows, primary.index, primary, DEFAULT_OPTIONS);
    expect(combined).toHaveLength(1);
    expect(combined[0].ledgerRowIndexes).toEqual([0]);
    expect(combined[0].bankTxnIndexes.sort()).toEqual([0, 1]);
  });
});

describe("no combination found leaves everything unmatched", () => {
  it("returns no combined matches when no subset sums correctly", () => {
    const bankTxns = [txn({ credit: 7777 }), txn({ credit: 8888 })];
    const ledgerRows = [ledgerRow({ ledger_amount: 10000 })];
    const primary = runTwoWaveAssignment(bankTxns, ledgerRows);
    const combined = runCombinationSearch(bankTxns, ledgerRows, primary.index, primary, DEFAULT_OPTIONS);
    expect(combined).toHaveLength(0);
  });
});
