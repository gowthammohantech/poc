import { describe, it, expect } from "vitest";
import { aggregateInvoices } from "../invoiceAggregation";
import type { LedgerRow, VoucherMatch } from "@/types/matching";

function ledgerRow(overrides: Partial<LedgerRow> = {}): LedgerRow {
  return {
    id: "row",
    transaction_type: "Sales Receipt",
    invoice_no: "SI-0001",
    invoice_date: "2024-04-01",
    invoice_amount: 10000,
    ledger_date: null,
    ledger_voucher: null,
    ledger_amount: null,
    account_name: null,
    bank_cash_account: null,
    ...overrides,
  };
}

function voucher(overrides: Partial<VoucherMatch> = {}): VoucherMatch {
  return {
    ledgerRowId: "row",
    invoiceNo: "SI-0001",
    ledgerVoucher: null,
    ledgerAmount: null,
    ledgerDate: null,
    matchedBankTxnIndexes: [],
    score: 0,
    status: "Unmatched",
    failedCriteria: [],
    resolvedLedgerAccount: null,
    ledgerAccountMatchType: null,
    resolvedBankCashAccount: null,
    bankCashMatchType: null,
    coaValidated: null,
    reasons: [],
    ...overrides,
  };
}

describe("scenario 5: invoice with zero settlement -> Not Settled", () => {
  it("reports Not Settled with full outstanding when no voucher is matched", () => {
    const rows = [ledgerRow({ id: "a" })];
    const vouchers = [voucher({ ledgerRowId: "a", status: "Unmatched" })];
    const [summary] = aggregateInvoices(rows, vouchers);
    expect(summary.status).toBe("Not Settled");
    expect(summary.totalSettled).toBe(0);
    expect(summary.outstanding).toBe(10000);
  });
});

describe("scenario 6: two partial ledger rows, both matched -> Fully Settled", () => {
  it("sums settlements to exactly the invoice amount with 0 outstanding", () => {
    const rows = [
      ledgerRow({ id: "a", ledger_amount: 6000 }),
      ledgerRow({ id: "b", ledger_amount: 4000 }),
    ];
    const vouchers = [
      voucher({ ledgerRowId: "a", ledgerAmount: 6000, status: "Matched" }),
      voucher({ ledgerRowId: "b", ledgerAmount: 4000, status: "Matched" }),
    ];
    const [summary] = aggregateInvoices(rows, vouchers);
    expect(summary.status).toBe("Fully Settled");
    expect(summary.totalSettled).toBe(10000);
    expect(summary.outstanding).toBe(0);
  });
});

describe("scenario 7: two partial ledger rows, only one matched -> Partially Settled", () => {
  it("only counts the matched row toward totalSettled", () => {
    const rows = [
      ledgerRow({ id: "a", ledger_amount: 6000 }),
      ledgerRow({ id: "b", ledger_amount: 4000 }),
    ];
    const vouchers = [
      voucher({ ledgerRowId: "a", ledgerAmount: 6000, status: "Matched" }),
      voucher({ ledgerRowId: "b", ledgerAmount: 4000, status: "Unmatched" }),
    ];
    const [summary] = aggregateInvoices(rows, vouchers);
    expect(summary.status).toBe("Partially Settled");
    expect(summary.totalSettled).toBe(6000);
    expect(summary.outstanding).toBe(4000);
  });
});

describe("Overpaid/Mismatch and Needs Review", () => {
  it("flags settlement exceeding the invoice amount instead of flooring silently", () => {
    const rows = [ledgerRow({ id: "a", invoice_amount: 5000, ledger_amount: 7000 })];
    const vouchers = [voucher({ ledgerRowId: "a", ledgerAmount: 7000, status: "Matched" })];
    const [summary] = aggregateInvoices(rows, vouchers);
    expect(summary.status).toBe("Overpaid/Mismatch");
    expect(summary.mismatchAmount).toBe(2000);
  });

  it("puts invoices with an unknown amount into Needs Review, not Overpaid", () => {
    const rows = [ledgerRow({ id: "a", invoice_amount: null, ledger_amount: 7000 })];
    const vouchers = [voucher({ ledgerRowId: "a", ledgerAmount: 7000, status: "Matched" })];
    const [summary] = aggregateInvoices(rows, vouchers);
    expect(summary.status).toBe("Needs Review");
    expect(summary.outstanding).toBeNull();
  });
});
