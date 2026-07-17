import { describe, it, expect } from "vitest";
import { buildBankTxnIndex, dateWindowCandidates, exactAmountCandidates, candidatesFor } from "../candidateIndex";
import type { BrsTransaction } from "@/types/brs";

function txn(date: string, amount: number, credit: boolean): BrsTransaction {
  return {
    transaction_date: date,
    narration: "",
    reference_number: null,
    debit: credit ? null : amount,
    credit: credit ? amount : null,
    balance: null,
  };
}

describe("buildBankTxnIndex / dateWindowCandidates", () => {
  const bankTxns = [
    txn("2024-04-09", 25000, true),   // 0
    txn("2024-04-10", 18500, false),  // 1
    txn("2024-04-20", 12000, true),   // 2
  ];
  const index = buildBankTxnIndex(bankTxns);
  const all = new Set([0, 1, 2]);

  it("finds bank txns within the date window, merging boundary days", () => {
    const candidates = dateWindowCandidates(index, "2024-04-09", 1, all);
    expect(candidates.sort()).toEqual([0, 1]);
  });

  it("excludes txns outside the window", () => {
    const candidates = dateWindowCandidates(index, "2024-04-09", 1, all);
    expect(candidates).not.toContain(2);
  });

  it("respects the available set (consumed txns excluded)", () => {
    const candidates = dateWindowCandidates(index, "2024-04-09", 1, new Set([1]));
    expect(candidates).toEqual([1]);
  });

  it("returns [] for an unparseable anchor date", () => {
    expect(dateWindowCandidates(index, null, 5, all)).toEqual([]);
  });
});

describe("exactAmountCandidates", () => {
  const bankTxns = [txn("2024-04-09", 25000, true), txn("2024-04-10", 25000, false)];
  const index = buildBankTxnIndex(bankTxns);

  it("finds all txns with the exact cents amount", () => {
    const candidates = exactAmountCandidates(index, 2500000, new Set([0, 1]));
    expect(candidates.sort()).toEqual([0, 1]);
  });
});

describe("candidatesFor", () => {
  const bankTxns = [
    txn("2024-04-09", 25000, true), // 0 - exact amount match
    txn("2024-04-09", 30000, true), // 1 - same day, different amount
  ];
  const index = buildBankTxnIndex(bankTxns);

  it("prefers exact-amount candidates within the window when available", () => {
    const candidates = candidatesFor(index, "2024-04-09", 2500000, 3, new Set([0, 1]));
    expect(candidates).toEqual([0]);
  });

  it("falls back to the full date-window pool when no exact-amount candidate exists", () => {
    const candidates = candidatesFor(index, "2024-04-09", 999900, 3, new Set([0, 1]));
    expect(candidates.sort()).toEqual([0, 1]);
  });
});
