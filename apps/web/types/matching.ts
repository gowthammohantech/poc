import type { BrsTransaction } from "./brs";

export type ReconciliationMode = "2-way" | "3-way";

export interface CoaRow {
  account_code: string;
  account_name: string;
  account_type: string;
  parent_group?: string | null;
}

export type LedgerTransactionType = "Sales Receipt" | "Purchase Payment";

export interface LedgerRow {
  id: string;
  transaction_type: LedgerTransactionType;
  invoice_no: string;
  /** The invoice's own date — separate from the settlement leg below. */
  invoice_date: string | null;
  /** The invoice's own expected amount. Nullable (not defaulted to 0) — an invoice whose amount
   * hasn't been entered yet is "unknown", not "worth nothing"; see InvoiceStatus "Needs Review". */
  invoice_amount: number | null;
  /** One settlement leg (a single receipt/payment against the invoice). All three of
   * ledger_date/ledger_voucher/ledger_amount are either filled together (a real settlement) or
   * all blank together (an invoice recorded but not yet settled) — partial combinations are a
   * validation error, not a valid state. */
  ledger_date: string | null;
  ledger_voucher: string | null;
  ledger_amount: number | null;
  /** The ledger/party account (e.g. a customer or vendor name) — matched against any COA account type. */
  account_name?: string | null;
  /** Which Bank/Cash GL account the money actually hit — an extra, optional 3-way validation layer, matched only against Bank/Cash typed COA rows. */
  bank_cash_account?: string | null;
}

export type VoucherStatus = "Matched" | "Matched (combined)" | "Partially Matched" | "Unmatched";

export type InvoiceStatus = "Fully Settled" | "Partially Settled" | "Not Settled" | "Overpaid/Mismatch" | "Needs Review";

export interface VoucherMatch {
  ledgerRowId: string;
  invoiceNo: string;
  ledgerVoucher: string | null;
  ledgerAmount: number | null;
  ledgerDate: string | null;
  /** Indexes into the original bank transactions array — 0 items for Unmatched, 1 normally, 2-3 for a combined match. */
  matchedBankTxnIndexes: number[];
  score: number;
  status: VoucherStatus;
  failedCriteria: string[];
  /** 3-way only: the ledger row's own account (customer/vendor/etc.) resolved in the COA.
   * "narration" means no COA row resolved at all — the bank narration itself directly named
   * this party instead. */
  resolvedLedgerAccount: CoaRow | null;
  ledgerAccountMatchType: "name" | "fuzzy" | "narration" | null;
  /** 3-way only: the specific Bank/Cash GL account the settlement resolved to. "statement" means
   * it matched the uploaded bank statement's own bank name rather than an explicit COA row. */
  resolvedBankCashAccount: CoaRow | null;
  bankCashMatchType: "name" | "fuzzy" | "statement" | null;
  /** true only if every applicable 3-way check passed; null in 2-way mode. */
  coaValidated: boolean | null;
  reasons: string[];
}

export interface InvoiceSummary {
  invoiceNo: string;
  invoiceDate: string | null;
  invoiceAmount: number | null;
  totalSettled: number;
  outstanding: number | null;
  /** > 0 only when status is Overpaid/Mismatch. */
  mismatchAmount: number;
  status: InvoiceStatus;
  /** ledgerRowIds belonging to this invoice, linking back to voucherMatches. */
  voucherRefs: string[];
}

export interface MatchingStats {
  totalInvoices: number;
  fullySettled: number;
  partiallySettled: number;
  notSettled: number;
  mismatched: number;
  needsReview: number;
  totalBankTxns: number;
  matchedBankTxns: number;
}

export interface MatchingResult {
  mode: ReconciliationMode;
  voucherMatches: VoucherMatch[];
  invoiceSummary: InvoiceSummary[];
  unmatchedBankTxnIndexes: number[];
  stats: MatchingStats;
}

export interface MatchingWeights {
  amount: number;
  date: number;
  direction: number;
}

export interface MatchingOptions {
  dateToleranceDays: number;
  minMatchScore: number;
  matchedScoreThreshold: number;
  weights: MatchingWeights;
  maxCombinationSize: number;
  maxCombinationPoolSize: number;
  accountNameMatchThreshold: number;
  fuzzyAccountThreshold: number;
}

export interface ParseResponse<T> {
  rows: T[];
  errors: string[];
}

// Re-exported so consumers of the engine don't need a separate import from types/brs.
export type { BrsTransaction };
