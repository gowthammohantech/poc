import { describe, it, expect } from "vitest";
import { accountNameSimilarity, isBankOrCashType, bestAccountMatch } from "../coaValidation";
import type { CoaRow } from "@/types/matching";

describe("accountNameSimilarity", () => {
  it("treats case/spacing/symbol differences as equal", () => {
    expect(accountNameSimilarity("BANK", "Bank")).toBe(1);
    expect(accountNameSimilarity("BANK", "Bank A/c")).toBeGreaterThanOrEqual(0.95);
  });
});

describe("isBankOrCashType", () => {
  it("recognizes tolerant type labels", () => {
    expect(isBankOrCashType("Bank")).toBe(true);
    expect(isBankOrCashType("Bank Account")).toBe(true);
    expect(isBankOrCashType("Cash-in-Hand")).toBe(true);
    expect(isBankOrCashType("Sundry Debtors")).toBe(false);
  });
});

describe("bestAccountMatch", () => {
  const coaRows: CoaRow[] = [
    { account_code: "1001", account_name: "ICICI Bank Current A/c", account_type: "Bank" },
    { account_code: "2001", account_name: "USHA NANDHINI", account_type: "Sundry Debtors" },
  ];

  it("resolves a near-exact typed account name", () => {
    const match = bestAccountMatch("USHA NANDHINI", null, coaRows);
    expect(match?.row.account_code).toBe("2001");
    expect(match?.type).toBe("name");
  });

  it("falls back to narration fuzzy match when no name given", () => {
    const match = bestAccountMatch(null, "UPI:USHA NANDHINI S-...", coaRows);
    expect(match?.row.account_code).toBe("2001");
    expect(match?.type).toBe("fuzzy");
  });

  it("returns null when nothing resolves", () => {
    const match = bestAccountMatch("Totally Unrelated Co", "no clues here", coaRows);
    expect(match).toBeNull();
  });
});
