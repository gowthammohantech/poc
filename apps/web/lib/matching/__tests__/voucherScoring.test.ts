import { describe, it, expect } from "vitest";
import { scorePair, runTwoWaveAssignment, DEFAULT_OPTIONS } from "../voucherScoring";
import type { BrsTransaction } from "@/types/brs";
import type { LedgerRow } from "@/types/matching";

function txn(overrides: Partial<BrsTransaction> = {}): BrsTransaction {
  return {
    transaction_date: "2024-04-09",
    narration: "UPI:USHA NANDHINI-RV101",
    reference_number: "RV101",
    debit: null,
    credit: 25000,
    balance: null,
    ...overrides,
  };
}

function ledgerRow(overrides: Partial<LedgerRow> = {}): LedgerRow {
  return {
    id: "row-1",
    transaction_type: "Sales Receipt",
    invoice_no: "SI-1001",
    invoice_date: "2024-04-01",
    invoice_amount: 25000,
    ledger_date: "2024-04-09",
    ledger_voucher: "RV-101",
    ledger_amount: 25000,
    account_name: null,
    bank_cash_account: null,
    ...overrides,
  };
}

describe("scorePair — scenario 1: simple exact match", () => {
  it("scores the maximum for amount+date+direction all aligned", () => {
    const result = scorePair(txn(), ledgerRow());
    expect(result.amountScore).toBe(50);
    expect(result.dateScore).toBe(40);
    expect(result.directionConsistent).toBe(true);
    expect(result.score).toBe(100);
    expect(result.failedCriteria).toEqual([]);
  });
});

describe("scorePair — scenario 2: date outside tolerance", () => {
  it("drops date score to 0 and lowers the composite below the Matched threshold", () => {
    const result = scorePair(txn({ transaction_date: "2024-05-01" }), ledgerRow({ ledger_date: "2024-04-09" }));
    expect(result.dateScore).toBe(0);
    expect(result.failedCriteria).toContain("date_out_of_range");
    expect(result.score).toBeLessThan(DEFAULT_OPTIONS.matchedScoreThreshold);
  });
});

describe("reference/voucher content no longer affects scoring", () => {
  it("a garbled/unrelated reference or narration scores identically to an exact one", () => {
    const exactRef = scorePair(txn({ reference_number: "RV101", narration: "RV101" }), ledgerRow());
    const garbledRef = scorePair(txn({ reference_number: "XYZQWERTY999", narration: "some unrelated text" }), ledgerRow());
    expect(exactRef.score).toBe(garbledRef.score);
    expect(exactRef.amountScore).toBe(garbledRef.amountScore);
    expect(exactRef.dateScore).toBe(garbledRef.dateScore);
    expect(exactRef.failedCriteria).toEqual(garbledRef.failedCriteria);
  });
});

describe("runTwoWaveAssignment — scenario 4: fully unmatched bank txn", () => {
  it("leaves a bank txn with no plausible ledger row unassigned", () => {
    const bankTxns = [txn({ credit: 99999999, transaction_date: "1999-01-01" })];
    const ledgerRows = [ledgerRow()];
    const result = runTwoWaveAssignment(bankTxns, ledgerRows);
    expect(result.usedBankTxns.size).toBe(0);
    expect(result.assignments.size).toBe(0);
  });
});

describe("runTwoWaveAssignment — scenario 8: two ledger rows competing for one bank txn", () => {
  it("with reference no longer a differentiator, a tied score is broken deterministically by original ledger row index", () => {
    const bankTxns = [txn()]; // single bank txn, amount 25000
    // Both rows now score identically on amount+date+direction (reference isn't scored) — this
    // is exactly the tie-break scenario the deterministic sort exists for.
    const first = ledgerRow({ id: "first" });
    const second = ledgerRow({ id: "second" });
    const result = runTwoWaveAssignment(bankTxns, [first, second]);
    expect(result.assignments.size).toBe(1);
    expect(result.assignments.has(0)).toBe(true); // "first" (lower original index) wins the tie
    expect(result.assignments.has(1)).toBe(false); // "second" loses, no other candidate available
  });
});

describe("runTwoWaveAssignment — direction mismatch handled via Wave B", () => {
  it("only assigns a direction-inconsistent pair in Wave B, flagged accordingly", () => {
    const bankTxns = [txn({ credit: null, debit: 25000 })]; // a debit
    const ledgerRows = [ledgerRow({ transaction_type: "Sales Receipt" })]; // expects a credit
    const result = runTwoWaveAssignment(bankTxns, ledgerRows);
    const assigned = result.assignments.get(0);
    expect(assigned?.directionConsistent).toBe(false);
  });
});
