/**
 * Integration tests for the full runMatching() pipeline, covering the 10 scenarios from the
 * matching-engine spec end-to-end (not just the individual layers, which have their own tests).
 */
import { describe, it, expect } from "vitest";
import { runMatching, validateLedgerRow } from "../../matchingEngine";
import type { BrsTransaction } from "@/types/brs";
import type { CoaRow, LedgerRow } from "@/types/matching";

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

let idCounter = 0;
function ledgerRow(overrides: Partial<LedgerRow> = {}): LedgerRow {
  idCounter += 1;
  return {
    id: `row-${idCounter}`,
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

describe("scenario 1: simple exact 1:1 match", () => {
  it("Matched voucher, Fully Settled invoice", () => {
    const result = runMatching([txn()], [ledgerRow()], [], "2-way");
    expect(result.voucherMatches[0].status).toBe("Matched");
    expect(result.invoiceSummary[0].status).toBe("Fully Settled");
    expect(result.unmatchedBankTxnIndexes).toEqual([]);
  });
});

describe("scenario 2: amount matches, date outside tolerance -> Partially Matched", () => {
  it("downgrades status when date sits right at the edge of the tolerance window (still discoverable as a candidate, but scores 0 for date)", () => {
    // Default tolerance is 5 days — a candidate at exactly the boundary is still in the
    // candidate pool (the window is inclusive) but the linear decay bottoms out to 0 there.
    const result = runMatching(
      [txn({ transaction_date: "2024-04-14" })],
      [ledgerRow({ ledger_date: "2024-04-09" })],
      [],
      "2-way"
    );
    expect(result.voucherMatches[0].status).toBe("Partially Matched");
    expect(result.voucherMatches[0].failedCriteria).toContain("date_out_of_range");
  });

  it("a bank txn far outside any plausible window never becomes a candidate at all (Unmatched, not Partial)", () => {
    const result = runMatching(
      [txn({ transaction_date: "2024-06-01" })],
      [ledgerRow({ ledger_date: "2024-04-09" })],
      [],
      "2-way"
    );
    expect(result.voucherMatches[0].status).toBe("Unmatched");
  });
});

describe("scenario 3: reference/narration is garbled or unrelated", () => {
  it("no longer affects status — amount/date/direction alone still produce a full Matched result", () => {
    const result = runMatching(
      [txn({ reference_number: "QQQZZZ111", narration: "unrelated text entirely" })],
      [ledgerRow()],
      [],
      "2-way"
    );
    expect(result.voucherMatches[0].status).toBe("Matched");
    expect(result.voucherMatches[0].reasons.some((r) => r.toLowerCase().includes("reference"))).toBe(false);
  });
});

describe("scenario 4: fully unmatched bank transaction", () => {
  it("reports a bank txn with no plausible candidate as unmatched", () => {
    const result = runMatching(
      [txn({ credit: 999999, transaction_date: "1999-01-01" })],
      [ledgerRow()],
      [],
      "2-way"
    );
    expect(result.unmatchedBankTxnIndexes).toEqual([0]);
  });
});

describe("scenario 5: invoice with no settlement recorded -> Not Settled", () => {
  it("a ledger row with a blank settlement leg produces Not Settled", () => {
    const result = runMatching(
      [],
      [ledgerRow({ ledger_date: null, ledger_voucher: null, ledger_amount: null })],
      [],
      "2-way"
    );
    expect(result.voucherMatches[0].status).toBe("Unmatched");
    expect(result.invoiceSummary[0].status).toBe("Not Settled");
    expect(result.invoiceSummary[0].outstanding).toBe(25000);
  });
});

describe("scenario 5b: invoice-only row (no settlement leg recorded) matches directly on its own invoice date/amount", () => {
  it("matches a bank transaction using invoice_date/invoice_amount when ledger_date/voucher/amount are all null, and counts toward settlement", () => {
    const result = runMatching(
      [
        txn({
          transaction_date: "2024-03-28",
          narration: "IMPS-4088251533919-USHA NANDHINI S-KBBK-XXXXX6739-KBBKTRANSFER 00004088251533919",
          reference_number: "4088251533919",
          credit: null,
          debit: 48500,
        }),
      ],
      [
        ledgerRow({
          transaction_type: "Purchase Payment",
          invoice_no: "PI-2012",
          invoice_date: "2024-03-28",
          invoice_amount: 48500,
          ledger_date: null,
          ledger_voucher: null,
          ledger_amount: null,
          account_name: "USHA NANDHINI",
          bank_cash_account: "HDFC BANK",
        }),
      ],
      [],
      "2-way"
    );
    expect(result.voucherMatches[0].status).toBe("Matched");
    expect(result.voucherMatches[0].ledgerAmount).toBe(48500);
    expect(result.invoiceSummary[0].status).toBe("Fully Settled");
    expect(result.invoiceSummary[0].outstanding).toBe(0);
  });
});

describe("scenario 6: invoice settled via two partial ledger rows, both matched -> Fully Settled", () => {
  it("sums both settlements to exactly the invoice amount", () => {
    const bankTxns = [
      txn({ credit: 15000, reference_number: "RV-201", narration: "RV-201" }),
      txn({ credit: 10000, reference_number: "RV-202", narration: "RV-202", transaction_date: "2024-04-10" }),
    ];
    const ledgerRows = [
      ledgerRow({ invoice_no: "SI-2001", invoice_amount: 25000, ledger_amount: 15000, ledger_voucher: "RV-201" }),
      ledgerRow({ invoice_no: "SI-2001", invoice_amount: 25000, ledger_amount: 10000, ledger_voucher: "RV-202", ledger_date: "2024-04-10" }),
    ];
    const result = runMatching(bankTxns, ledgerRows, [], "2-way");
    expect(result.voucherMatches.every((v) => v.status === "Matched")).toBe(true);
    const invoice = result.invoiceSummary.find((s) => s.invoiceNo === "SI-2001")!;
    expect(invoice.status).toBe("Fully Settled");
    expect(invoice.totalSettled).toBe(25000);
    expect(invoice.outstanding).toBe(0);
  });
});

describe("scenario 7: invoice settled via two partial ledger rows, only one matched -> Partially Settled", () => {
  it("only counts the confirmed settlement toward totalSettled", () => {
    const bankTxns = [txn({ credit: 15000, reference_number: "RV-301", narration: "RV-301" })];
    const ledgerRows = [
      ledgerRow({ invoice_no: "SI-3001", invoice_amount: 25000, ledger_amount: 15000, ledger_voucher: "RV-301" }),
      ledgerRow({ invoice_no: "SI-3001", invoice_amount: 25000, ledger_amount: 10000, ledger_voucher: "RV-302", ledger_date: "2030-01-01" }),
    ];
    const result = runMatching(bankTxns, ledgerRows, [], "2-way");
    const invoice = result.invoiceSummary.find((s) => s.invoiceNo === "SI-3001")!;
    expect(invoice.status).toBe("Partially Settled");
    expect(invoice.totalSettled).toBe(15000);
    expect(invoice.outstanding).toBe(10000);
  });
});

describe("scenario 8: two ledger rows competing for one bank transaction", () => {
  it("a tied score (amount/date/direction identical) is broken deterministically; the loser is left unmatched", () => {
    const bankTxns = [txn()];
    const first = ledgerRow({ id: "first" });
    const second = ledgerRow({ id: "second" });
    const result = runMatching(bankTxns, [first, second], [], "2-way");
    const firstResult = result.voucherMatches.find((v) => v.ledgerRowId === "first")!;
    const secondResult = result.voucherMatches.find((v) => v.ledgerRowId === "second")!;
    expect(firstResult.matchedBankTxnIndexes).toEqual([0]);
    expect(secondResult.matchedBankTxnIndexes).toEqual([]);
  });
});

describe("scenario 9: split deposit — one bank credit equals sum of two ledger vouchers", () => {
  it("marks both ledger rows Matched (combined) against the single bank txn", () => {
    const bankTxns = [txn({ credit: 25000, reference_number: null, narration: "aggregated settlement" })];
    const ledgerRows = [
      ledgerRow({ id: "a", ledger_amount: 15000, ledger_voucher: "RV-401" }),
      ledgerRow({ id: "b", ledger_amount: 10000, ledger_voucher: "RV-402" }),
    ];
    const result = runMatching(bankTxns, ledgerRows, [], "2-way");
    const a = result.voucherMatches.find((v) => v.ledgerRowId === "a")!;
    const b = result.voucherMatches.find((v) => v.ledgerRowId === "b")!;
    expect(a.status).toBe("Matched (combined)");
    expect(b.status).toBe("Matched (combined)");
    expect(a.matchedBankTxnIndexes).toEqual([0]);
    expect(b.matchedBankTxnIndexes).toEqual([0]);
  });
});

describe("scenario 10: 3-way, missing COA Bank/Cash account -> downgraded with reason", () => {
  it("downgrades an otherwise-Matched voucher when the Bank/Cash account doesn't resolve", () => {
    const coaRows: CoaRow[] = [
      { account_code: "2001", account_name: "USHA NANDHINI", account_type: "Sundry Debtors" },
      // no Bank/Cash typed COA row at all
    ];
    const row = ledgerRow({ account_name: "USHA NANDHINI", bank_cash_account: "ICICI Bank Current A/c" });
    const result = runMatching([txn()], [row], coaRows, "3-way");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Partially Matched");
    expect(vm.coaValidated).toBe(false);
    expect(vm.reasons.some((r) => r.includes("Bank/Cash Account"))).toBe(true);
  });

  it("stays Matched when both the ledger account and Bank/Cash account resolve", () => {
    const coaRows: CoaRow[] = [
      { account_code: "2001", account_name: "USHA NANDHINI", account_type: "Sundry Debtors" },
      { account_code: "1001", account_name: "ICICI Bank Current A/c", account_type: "Bank" },
    ];
    const row = ledgerRow({ account_name: "USHA NANDHINI", bank_cash_account: "ICICI Bank Current A/c" });
    const result = runMatching([txn()], [row], coaRows, "3-way");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Matched");
    expect(vm.coaValidated).toBe(true);
  });
});

describe("validateLedgerRow: every field is independently optional", () => {
  const base: Partial<LedgerRow> = { transaction_type: "Sales Receipt" };

  it("accepts a row with only the full Ledger set (no invoice details)", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_no: "",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: "2024-04-09",
      ledger_voucher: "RV-101",
      ledger_amount: 25000,
    });
    expect(errors).toEqual([]);
  });

  it("accepts a row with only the full Invoice set (not yet settled)", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_no: "SI-1001",
      invoice_date: "2024-04-01",
      invoice_amount: 25000,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
    });
    expect(errors).toEqual([]);
  });

  it("accepts a row where both sets are fully present", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_no: "SI-1001",
      invoice_date: "2024-04-01",
      invoice_amount: 25000,
      ledger_date: "2024-04-09",
      ledger_voucher: "RV-101",
      ledger_amount: 25000,
    });
    expect(errors).toEqual([]);
  });

  it("accepts a partially-filled row (e.g. Ledger Amount known, but no Date/Voucher yet) with no error", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_no: "PI-2012",
      invoice_date: "2024-01-10",
      invoice_amount: 20000,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: 20000,
    });
    expect(errors).toEqual([]);
  });

  it("accepts a fully empty row (no field-level errors — an empty row just carries no data)", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_no: "",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
    });
    expect(errors).toEqual([]);
  });

  it("still flags a field that was provided but is malformed", () => {
    const errors = validateLedgerRow({
      ...base,
      invoice_amount: -5, // negative — invalid
    });
    expect(errors.some((e) => e.includes("Invoice Amount"))).toBe(true);
  });
});

describe("3-way: Bank/Cash Account falls back to the uploaded statement's bank name", () => {
  it("resolves via the statement's bank name when no matching COA row exists", () => {
    const coaRows: CoaRow[] = [
      { account_code: "2001", account_name: "USHA NANDHINI", account_type: "Sundry Debtors" },
      // no Bank/Cash typed COA row at all
    ];
    const row = ledgerRow({ account_name: "USHA NANDHINI", bank_cash_account: "ICICI Bank" });
    const result = runMatching([txn()], [row], coaRows, "3-way", "ICICI Bank");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Matched");
    expect(vm.coaValidated).toBe(true);
    expect(vm.bankCashMatchType).toBe("statement");
    expect(vm.resolvedBankCashAccount?.account_name).toBe("ICICI Bank");
  });

  it("still downgrades when the value matches neither the COA nor the statement's bank", () => {
    const coaRows: CoaRow[] = [{ account_code: "2001", account_name: "USHA NANDHINI", account_type: "Sundry Debtors" }];
    const row = ledgerRow({ account_name: "USHA NANDHINI", bank_cash_account: "Totally Different Bank" });
    const result = runMatching([txn()], [row], coaRows, "3-way", "ICICI Bank");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Partially Matched");
    expect(vm.coaValidated).toBe(false);
  });
});

describe("3-way: Ledger Account falls back to the bank narration when no COA row exists", () => {
  it("real scenario — partial cheque payment against an invoice, vendor named only in the narration", () => {
    // No COA entry for "V.M.PHARMACEUTICALS" at all; the bank narration is the only place the
    // vendor name appears. Ledger Amount (7419) is a partial payment against a larger Invoice
    // Amount (15000) — the voucher-level match is against the settlement leg, not the invoice.
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "CHQ PAID-MICR CTS-CH-VM PHARMACEUTICALS",
      reference_number: null,
      debit: 7419,
      credit: null,
      balance: null,
    };
    const row = ledgerRow({
      transaction_type: "Purchase Payment",
      invoice_no: "SI-1010",
      invoice_date: "2024-04-01",
      invoice_amount: 15000,
      ledger_date: "2024-04-04",
      ledger_voucher: "RV-108",
      ledger_amount: 7419,
      account_name: "V.M.PHARMACEUTICALS",
      bank_cash_account: "HDFC BANK",
    });
    const coaRows: CoaRow[] = []; // no COA uploaded / no matching vendor entry at all

    const result = runMatching([bankTxn], [row], coaRows, "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];

    expect(vm.matchedBankTxnIndexes).toEqual([0]);
    expect(vm.ledgerAccountMatchType).toBe("narration");
    expect(vm.resolvedLedgerAccount?.account_name).toBe("V.M.PHARMACEUTICALS");
    expect(vm.bankCashMatchType).toBe("statement");
    expect(vm.coaValidated).toBe(true);
    expect(vm.status).toBe("Matched");

    const invoice = result.invoiceSummary.find((s) => s.invoiceNo === "SI-1010")!;
    expect(invoice.totalSettled).toBe(7419);
    expect(invoice.status).toBe("Partially Settled");
  });
});

describe("3-way: Account Name matched from bank narration alone when no Invoice or Ledger details are given", () => {
  it("matches purely on Account Name vs narration, capped at Partially Matched, with a confidence score", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-4088251533919-USHA NANDHINI S-KBBK-XXXXX6739-KBBKTRANSFER 00004088251533919",
      reference_number: null,
      debit: 48500,
      credit: null,
      balance: null,
    };
    const row = ledgerRow({
      transaction_type: "Purchase Payment",
      invoice_no: "",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
      account_name: "USHA NANDHINI",
      bank_cash_account: "HDFC BANK",
    });

    const result = runMatching([bankTxn], [row], [], "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];

    expect(vm.matchedBankTxnIndexes).toEqual([0]);
    expect(vm.status).toBe("Partially Matched");
    expect(vm.score).toBeGreaterThan(0);
    expect(vm.failedCriteria).toContain("amount_date_unavailable");
    expect(vm.reasons.some((r) => r.includes("Account Name Matched") && r.includes("%"))).toBe(true);
  });

  it("labels it 'Account Matched, Missing Invoice & Ledger' when the account name also resolves in the COA", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-4088251533919-USHA NANDHINI S-KBBK-XXXXX6739-KBBKTRANSFER 00004088251533919",
      reference_number: null,
      debit: 48500,
      credit: null,
      balance: null,
    };
    const row = ledgerRow({
      transaction_type: "Purchase Payment",
      invoice_no: "",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
      account_name: "USHA NANDHINI",
      bank_cash_account: "HDFC BANK",
    });
    const coaRows: CoaRow[] = [{ account_code: "V-100", account_name: "USHA NANDHINI", account_type: "Sundry Creditor" }];

    const result = runMatching([bankTxn], [row], coaRows, "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];

    expect(vm.status).toBe("Partially Matched");
    expect(vm.reasons).toContain("Account Matched, Missing Invoice & Ledger");
  });

  it("never resolves in 2-way mode (the fallback is 3-way only)", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-USHA NANDHINI S-KBBK",
      reference_number: null,
      debit: 48500,
      credit: null,
      balance: null,
    };
    const row = ledgerRow({
      transaction_type: "Purchase Payment",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
      account_name: "USHA NANDHINI",
    });
    const result = runMatching([bankTxn], [row], [], "2-way");
    expect(result.voucherMatches[0].matchedBankTxnIndexes).toEqual([]);
    expect(result.voucherMatches[0].status).toBe("Unmatched");
  });
});

describe("3-way: bank transaction with no ledger row at all still matches on COA + Statement alone", () => {
  it("labels it 'Account Matched, Missing Invoice & Ledger' when only a COA entry exists for the party (no ledger row)", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-409514284928-USHA NANDHINI S-KBBK-XXXXX6739-KBBKTRANSFER 0000409514284928",
      reference_number: null,
      debit: null,
      credit: 200,
      balance: null,
    };
    const coaRows: CoaRow[] = [{ account_code: "V-100", account_name: "USHA NANDHINI", account_type: "Sundry Creditor" }];

    const result = runMatching([bankTxn], [], coaRows, "3-way", "HDFC BANK");

    expect(result.voucherMatches).toHaveLength(1);
    const vm = result.voucherMatches[0];
    expect(vm.matchedBankTxnIndexes).toEqual([0]);
    expect(vm.status).toBe("Partially Matched");
    expect(vm.reasons).toContain("Account Matched, Missing Invoice & Ledger");
    expect(vm.resolvedLedgerAccount?.account_name).toBe("USHA NANDHINI");
    expect(result.unmatchedBankTxnIndexes).toEqual([]);
    // No real invoice exists for this synthetic match, so it shouldn't pollute Invoice Summary.
    expect(result.invoiceSummary).toHaveLength(0);
  });

  it("leaves the bank transaction Unmatched when no COA row's name appears in the narration either", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-XYZ TRADERS-KBBK",
      reference_number: null,
      debit: null,
      credit: 200,
      balance: null,
    };
    const coaRows: CoaRow[] = [{ account_code: "V-100", account_name: "USHA NANDHINI", account_type: "Sundry Creditor" }];

    const result = runMatching([bankTxn], [], coaRows, "3-way", "HDFC BANK");
    expect(result.voucherMatches).toHaveLength(0);
    expect(result.unmatchedBankTxnIndexes).toEqual([0]);
  });

  it("never resolves in 2-way mode", () => {
    const bankTxn: BrsTransaction = {
      transaction_date: "2024-04-04",
      narration: "IMPS-409514284928-USHA NANDHINI S-KBBK",
      reference_number: null,
      debit: null,
      credit: 200,
      balance: null,
    };
    const coaRows: CoaRow[] = [{ account_code: "V-100", account_name: "USHA NANDHINI", account_type: "Sundry Creditor" }];

    const result = runMatching([bankTxn], [], coaRows, "2-way", "HDFC BANK");
    expect(result.voucherMatches).toHaveLength(0);
    expect(result.unmatchedBankTxnIndexes).toEqual([0]);
  });
});

describe("3-way: 'Matched By' calls out a missing side (Ledger vs Invoice details)", () => {
  it("notes <>'Receipt / Payment Ledger is missing' when matched via invoice date/amount alone", () => {
    const row = ledgerRow({
      transaction_type: "Purchase Payment",
      invoice_no: "PI-2012",
      invoice_date: "2024-03-28",
      invoice_amount: 48500,
      ledger_date: null,
      ledger_voucher: null,
      ledger_amount: null,
      account_name: "USHA NANDHINI",
      bank_cash_account: "HDFC BANK",
    });
    const bankTxn = txn({ transaction_date: "2024-03-28", credit: null, debit: 48500 });
    const result = runMatching([bankTxn], [row], [], "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Matched");
    expect(vm.reasons).toContain("Receipt / Payment Ledger is missing");
  });

  it("notes 'Invoice details missing' when matched via a settlement leg alone (no invoice date/amount)", () => {
    const row = ledgerRow({
      invoice_no: "SI-1001",
      invoice_date: null,
      invoice_amount: null,
      ledger_date: "2024-04-09",
      ledger_voucher: "RV-101",
      ledger_amount: 25000,
      account_name: "USHA NANDHINI",
      bank_cash_account: "HDFC BANK",
    });
    const result = runMatching([txn()], [row], [], "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];
    expect(vm.status).toBe("Matched");
    expect(vm.reasons).toContain("Invoice details missing");
  });

  it("adds neither note when both Invoice and Ledger details are present", () => {
    const result = runMatching([txn()], [ledgerRow({ account_name: "USHA NANDHINI", bank_cash_account: "HDFC BANK" })], [], "3-way", "HDFC BANK");
    const vm = result.voucherMatches[0];
    expect(vm.reasons).not.toContain("Receipt / Payment Ledger is missing");
    expect(vm.reasons).not.toContain("Invoice details missing");
  });
});
