/**
 * Public entry point for the matching engine — a thin orchestrator over the layered modules in
 * ./lib/matching/*. Kept at this import path (`@/lib/matchingEngine`) so existing callers don't
 * need to change their import.
 *
 * Pipeline: voucherScoring (Waves A/B, pairwise) → combinationSearch (Waves C/D, split/combined
 * deposits) → per-ledger-row VoucherMatch assembly (+ optional 3-way COA validation) →
 * invoiceAggregation (Layer 4 rollup) → stats.
 */
import type { BrsTransaction } from "@/types/brs";
import type {
  CoaRow,
  InvoiceSummary,
  LedgerRow,
  MatchingOptions,
  MatchingResult,
  MatchingStats,
  ReconciliationMode,
  VoucherMatch,
  VoucherStatus,
} from "@/types/matching";
import { normalizeDate } from "./matching/normalize";
import { DEFAULT_OPTIONS, anchorAmount, anchorDate, directionForTxn, hasSettlement, runTwoWaveAssignment, type PairScore } from "./matching/voucherScoring";
import { runCombinationSearch, type CombinedMatch } from "./matching/combinationSearch";
import { aggregateInvoices } from "./matching/invoiceAggregation";
import { accountNameSimilarity, bestAccountMatch, isBankOrCashType, narrationAccountScore } from "./matching/coaValidation";

/**
 * Every field is independently optional — Invoice No/Date/Amount and Ledger Date/Voucher/Amount
 * are each mapped through whenever present, regardless of whether their sibling fields are also
 * filled in. A field only produces an error if it was actually provided but is malformed (a
 * garbled date/amount); a blank field is never an error on its own.
 */
export function validateLedgerRow(row: Partial<LedgerRow>): string[] {
  const errors: string[] = [];
  if (row.transaction_type !== "Sales Receipt" && row.transaction_type !== "Purchase Payment") {
    errors.push('Transaction Type must be "Sales Receipt" or "Purchase Payment"');
  }

  if (row.invoice_date && !normalizeDate(row.invoice_date)) {
    errors.push("Invoice Date is not a valid date");
  }
  if (row.invoice_amount != null && (Number.isNaN(row.invoice_amount) || row.invoice_amount < 0)) {
    errors.push("Invoice Amount must be a non-negative number");
  }
  if (row.ledger_date && !normalizeDate(row.ledger_date)) {
    errors.push("Ledger Date must be a valid date");
  }
  if (row.ledger_amount != null && (Number.isNaN(row.ledger_amount) || row.ledger_amount <= 0)) {
    errors.push("Ledger Amount must be a positive number");
  }

  return errors;
}

export function validateCoaRow(row: Partial<CoaRow>): string[] {
  const errors: string[] = [];
  if (!row.account_code || !row.account_code.trim()) errors.push("Account Code is required");
  if (!row.account_name || !row.account_name.trim()) errors.push("Account Name is required");
  if (!row.account_type || !row.account_type.trim()) errors.push("Account Type is required");
  return errors;
}

// Reference/voucher matching is intentionally not scored (see voucherScoring.ts) — it proved
// unreliable across real invoices/ledgers, so "Matched By" no longer reports on it at all.
function reasonsForPair(pair: PairScore, options: MatchingOptions): string[] {
  const reasons: string[] = [];
  reasons.push(pair.amountScore > 0 ? "Amount matched exactly" : "Amount did not match");
  if (pair.dateScore >= options.weights.date - 0.01) reasons.push("Date matched exactly");
  else if (pair.dateScore > 0) reasons.push("Date within tolerance (partial credit)");
  else reasons.push("Date outside tolerance window");
  if (!pair.directionConsistent) reasons.push("Transaction type/direction mismatch");
  return reasons;
}

function statusForPair(pair: PairScore, options: MatchingOptions): VoucherStatus {
  if (!pair.directionConsistent) return "Partially Matched";
  return pair.score >= options.matchedScoreThreshold ? "Matched" : "Partially Matched";
}

function baseVoucherMatch(row: LedgerRow): VoucherMatch {
  return {
    ledgerRowId: row.id,
    invoiceNo: row.invoice_no,
    ledgerVoucher: row.ledger_voucher,
    // Falls back to the invoice's own amount/date when no separate settlement leg was recorded,
    // so an invoice-only row that matches a bank transaction on its invoice date/amount still
    // reports the amount it was actually matched on (and counts correctly in invoiceAggregation).
    ledgerAmount: anchorAmount(row),
    ledgerDate: anchorDate(row),
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
  };
}

/**
 * 3-way only: when a ledger row has no usable amount/date anchor at all — neither a settlement
 * leg nor invoice date/amount — there's nothing numeric left to score against. Fall back to
 * matching purely on Account Name against the bank narration. This is weaker evidence than an
 * amount+date match (a shared name says nothing about which of several transactions for that
 * party this is), so it's always capped at "Partially Matched" regardless of similarity score.
 */
function accountNameOnlyMatch(
  row: LedgerRow,
  bankTxns: BrsTransaction[],
  usedBankTxns: ReadonlySet<number>,
  options: MatchingOptions
): { bankTxnIndex: number; score: number } | null {
  if (!row.account_name) return null;
  let best: { bankTxnIndex: number; score: number } | null = null;
  for (let bi = 0; bi < bankTxns.length; bi++) {
    if (usedBankTxns.has(bi)) continue;
    if (directionForTxn(bankTxns[bi]) !== row.transaction_type) continue;
    const score = narrationAccountScore(bankTxns[bi].narration, row.account_name);
    if (score < options.fuzzyAccountThreshold) continue;
    if (!best || score > best.score) best = { bankTxnIndex: bi, score };
  }
  return best;
}

/**
 * 3-way only: second, independent confirmation for the account-name-only fallback above. A
 * narration match alone (accountNameOnlyMatch) just says the name appears somewhere in the bank
 * statement text — it says nothing about whether it's a real ledger account. If the same name
 * also resolves against the uploaded Chart of Accounts, that's confirmation from both of the
 * two sources this row actually has data from (COA + Statement; Invoice/Ledger are both blank),
 * so "Matched By" can call it out plainly as "Account Matched" instead of only the raw
 * narration-similarity detail.
 */
function accountNameConfirmedByCoa(row: LedgerRow, narration: string | null, coaRows: CoaRow[], options: MatchingOptions): boolean {
  return Boolean(bestAccountMatch(row.account_name, narration, coaRows, options.accountNameMatchThreshold, options.fuzzyAccountThreshold));
}

/**
 * 3-way only, last resort: bank transactions that no ledger row claims at all — nothing in the
 * uploaded Invoice/Ledger data references this party, so there's no LedgerRow for the two
 * fallbacks above to even attach to. Still check the narration directly against the Chart of
 * Accounts (excluding Bank/Cash rows, which name *this* statement's own account, not a
 * counterparty); a hit means the transaction belongs to a known party even with zero Invoice or
 * Ledger entries for it. Produces synthetic, ledger-less VoucherMatch rows so these show up in
 * Bank Results instead of a bare "no settlement found" — they're excluded from invoice
 * aggregation since they don't correspond to any real invoice.
 */
function findLedgerlessCoaMatches(
  bankTxns: BrsTransaction[],
  coaRows: CoaRow[],
  usedBankTxns: Set<number>,
  options: MatchingOptions
): VoucherMatch[] {
  const partyPool = coaRows.filter((c) => !isBankOrCashType(c.account_type));
  const matches: VoucherMatch[] = [];
  for (let bi = 0; bi < bankTxns.length; bi++) {
    if (usedBankTxns.has(bi)) continue;
    const match = bestAccountMatch(undefined, bankTxns[bi].narration, partyPool, options.accountNameMatchThreshold, options.fuzzyAccountThreshold);
    if (!match) continue;
    usedBankTxns.add(bi);
    matches.push({
      ledgerRowId: `coa-only:${bi}`,
      invoiceNo: "",
      ledgerVoucher: null,
      ledgerAmount: null,
      ledgerDate: null,
      matchedBankTxnIndexes: [bi],
      score: Math.round(match.score * 100),
      status: "Partially Matched",
      failedCriteria: ["amount_date_unavailable", "no_ledger_row"],
      resolvedLedgerAccount: match.row,
      ledgerAccountMatchType: match.type,
      resolvedBankCashAccount: null,
      bankCashMatchType: null,
      coaValidated: null,
      reasons: [
        "Account Matched, Missing Invoice & Ledger",
        `Account "${match.row.account_name}"${match.row.account_code ? ` (${match.row.account_code})` : ""} found in Chart of Accounts and matched to this bank statement narration — no Invoice or Ledger entry exists for it`,
      ],
    });
  }
  return matches;
}

function applyCoaValidation(
  vm: VoucherMatch,
  row: LedgerRow,
  bankTxns: BrsTransaction[],
  coaRows: CoaRow[],
  options: MatchingOptions,
  statementBankName: string | null
): void {
  const narration = vm.matchedBankTxnIndexes.length > 0 ? bankTxns[vm.matchedBankTxnIndexes[0]].narration : null;
  const bankCashPool = coaRows.filter((c) => isBankOrCashType(c.account_type));

  const ledgerAccountMatch = bestAccountMatch(row.account_name, narration, coaRows, options.accountNameMatchThreshold, options.fuzzyAccountThreshold);
  let ledgerAccountOk = Boolean(ledgerAccountMatch);
  if (ledgerAccountMatch) {
    vm.resolvedLedgerAccount = ledgerAccountMatch.row;
    vm.ledgerAccountMatchType = ledgerAccountMatch.type;
    if (ledgerAccountMatch.type === "name") {
      vm.reasons.push(`Account Name Matched from COA: ${ledgerAccountMatch.row.account_name}${ledgerAccountMatch.row.account_code ? ` (${ledgerAccountMatch.row.account_code})` : ""}`);
    } else {
      vm.reasons.push(`Account Name Matched via narration fuzzy match against COA: ${ledgerAccountMatch.row.account_name} (${Math.round(ledgerAccountMatch.score * 100)}% similar)`);
    }
  } else if (row.account_name) {
    // No COA row resolves at all (e.g. no COA entry exists for this vendor/customer) — fall
    // back to checking whether the bank narration itself directly names this party. A narration
    // like "CHQ PAID-...-VM PHARMACEUTICALS" is itself strong, independent proof of who the
    // transaction is with, even with no formal ledger account set up for them yet.
    const narrationScore = narrationAccountScore(narration, row.account_name);
    if (narrationScore >= options.fuzzyAccountThreshold) {
      ledgerAccountOk = true;
      vm.resolvedLedgerAccount = { account_code: "", account_name: row.account_name, account_type: "" };
      vm.ledgerAccountMatchType = "narration";
      vm.reasons.push(`Account Name Matched: "${row.account_name}" found directly in bank narration (~${Math.round(narrationScore * 100)}% similar)`);
    } else if (!narration) {
      vm.reasons.push(`Account Name "${row.account_name}" not found in Chart of Accounts (no matched bank transaction to check narration against)`);
    } else {
      vm.reasons.push(`Account Name "${row.account_name}" not found in Chart of Accounts or bank narration`);
    }
  } else {
    vm.reasons.push("No account name provided for 3-way validation");
  }

  let bankCashOk = true; // optional layer — absence isn't a failure
  if (row.bank_cash_account) {
    const bankCashMatch = bestAccountMatch(row.bank_cash_account, narration, bankCashPool, options.accountNameMatchThreshold, options.fuzzyAccountThreshold);
    if (bankCashMatch) {
      bankCashOk = true;
      vm.resolvedBankCashAccount = bankCashMatch.row;
      vm.bankCashMatchType = bankCashMatch.type;
      if (bankCashMatch.type === "name") {
        vm.reasons.push(`Bank/Cash Account matched from COA: ${bankCashMatch.row.account_name}${bankCashMatch.row.account_code ? ` (${bankCashMatch.row.account_code})` : ""}`);
      } else {
        vm.reasons.push(`Bank/Cash Account inferred via narration fuzzy match against COA: ${bankCashMatch.row.account_name} (${Math.round(bankCashMatch.score * 100)}% similar)`);
      }
    } else {
      // Fall back to the bank statement's own bank — the fact that this reconciliation is
      // running against one specific uploaded statement already establishes which bank it is,
      // so a Bank/Cash Account that matches that name is treated as resolved even with no
      // matching COA row.
      const statementMatch =
        statementBankName && accountNameSimilarity(row.bank_cash_account, statementBankName) >= options.accountNameMatchThreshold;
      if (statementMatch && statementBankName) {
        bankCashOk = true;
        vm.resolvedBankCashAccount = { account_code: "", account_name: statementBankName, account_type: "Bank" };
        vm.bankCashMatchType = "statement";
        vm.reasons.push(`Bank/Cash Account matched to the uploaded statement's bank: ${statementBankName}`);
      } else {
        bankCashOk = false;
        vm.reasons.push(`Bank/Cash Account "${row.bank_cash_account}" not found in Chart of Accounts or the uploaded statement's bank`);
      }
    }
  }

  vm.coaValidated = ledgerAccountOk && bankCashOk;
  if (!vm.coaValidated && vm.status === "Matched") {
    vm.status = "Partially Matched";
  }
}

export function runMatching(
  bankTxns: BrsTransaction[],
  ledgerRows: LedgerRow[],
  coaRows: CoaRow[],
  mode: ReconciliationMode,
  statementBankName: string | null = null,
  optionsOverride?: Partial<MatchingOptions>
): MatchingResult {
  const options: MatchingOptions = {
    ...DEFAULT_OPTIONS,
    ...optionsOverride,
    weights: { ...DEFAULT_OPTIONS.weights, ...optionsOverride?.weights },
  };

  const primary = runTwoWaveAssignment(bankTxns, ledgerRows, options);
  const combined = runCombinationSearch(bankTxns, ledgerRows, primary.index, primary, options);

  const combinedByLedgerIndex = new Map<number, CombinedMatch>();
  for (const cm of combined) {
    for (const li of cm.ledgerRowIndexes) combinedByLedgerIndex.set(li, cm);
  }

  // Mutable — the account-name-only fallback below (3-way, no amount/date anchor at all) also
  // consumes bank txns as it finds them, so it has to share this set rather than compute its own.
  const usedBankTxns = new Set<number>(primary.usedBankTxns);
  for (const cm of combined) for (const bi of cm.bankTxnIndexes) usedBankTxns.add(bi);

  const voucherMatches: VoucherMatch[] = ledgerRows.map((row, i) => {
    const vm = baseVoucherMatch(row);

    const pair = primary.assignments.get(i);
    const combo = combinedByLedgerIndex.get(i);
    // Ledger Details = the settlement leg (ledger_date/voucher/amount); Invoice Details =
    // invoice_date/invoice_amount. Called out in "Matched By" whenever one side is entirely
    // missing but the row still matched off the other side's data.
    const ledgerBlank = row.ledger_date == null && row.ledger_voucher == null && row.ledger_amount == null;
    const invoiceBlank = row.invoice_date == null && row.invoice_amount == null;

    if (pair) {
      vm.matchedBankTxnIndexes = [pair.bankTxnIndex];
      vm.score = Math.round(pair.score);
      vm.status = statusForPair(pair, options);
      vm.failedCriteria = pair.failedCriteria;
      vm.reasons = reasonsForPair(pair, options);
      if (mode === "3-way" && ledgerBlank && !invoiceBlank) vm.reasons.push("Receipt / Payment Ledger is missing");
      if (mode === "3-way" && invoiceBlank && !ledgerBlank) vm.reasons.push("Invoice details missing");
    } else if (combo) {
      vm.matchedBankTxnIndexes = combo.bankTxnIndexes;
      vm.score = Math.round(combo.score);
      vm.status = "Matched (combined)";
      vm.reasons = [`Matched via a combined settlement across ${combo.bankTxnIndexes.length} bank transaction(s) / ${combo.ledgerRowIndexes.length} invoice voucher(s)`];
      if (mode === "3-way" && ledgerBlank && !invoiceBlank) vm.reasons.push("Receipt / Payment Ledger is missing");
      if (mode === "3-way" && invoiceBlank && !ledgerBlank) vm.reasons.push("Invoice details missing");
    } else if (mode === "3-way" && !hasSettlement(row) && row.account_name) {
      const nameMatch = accountNameOnlyMatch(row, bankTxns, usedBankTxns, options);
      if (nameMatch) {
        usedBankTxns.add(nameMatch.bankTxnIndex);
        vm.matchedBankTxnIndexes = [nameMatch.bankTxnIndex];
        vm.score = Math.round(nameMatch.score * 100);
        vm.status = "Partially Matched";
        vm.failedCriteria = ["amount_date_unavailable"];
        const matchedNarration = bankTxns[nameMatch.bankTxnIndex].narration;
        const confirmedByCoa = accountNameConfirmedByCoa(row, matchedNarration, coaRows, options);
        vm.reasons = confirmedByCoa
          ? [
              "Account Matched, Missing Invoice & Ledger",
              `Account Name "${row.account_name}" confirmed against both the Chart of Accounts and the bank statement narration (~${Math.round(nameMatch.score * 100)}% similar)`,
            ]
          : [
              `Account Name Matched: "${row.account_name}" found in bank narration (~${Math.round(nameMatch.score * 100)}% similar) — no Invoice or Ledger amount/date provided to verify further`,
            ];
      } else {
        vm.reasons = ["No Invoice or Ledger details provided, and Account Name did not match any bank transaction narration"];
      }
    } else if (!hasSettlement(row)) {
      vm.reasons = ["No settlement recorded for this invoice yet"];
    } else {
      vm.reasons = [
        `No bank transaction found for Amount ${anchorAmount(row)} around ${anchorDate(row)} within the ${options.dateToleranceDays}-day tolerance window`,
      ];
      vm.failedCriteria = ["no_candidate"];
    }

    if (mode === "3-way") {
      applyCoaValidation(vm, row, bankTxns, coaRows, options, statementBankName);
    }

    return vm;
  });

  const ledgerlessCoaMatches = mode === "3-way" ? findLedgerlessCoaMatches(bankTxns, coaRows, usedBankTxns, options) : [];
  const allVoucherMatches = [...voucherMatches, ...ledgerlessCoaMatches];

  const unmatchedBankTxnIndexes = bankTxns.map((_, i) => i).filter((i) => !usedBankTxns.has(i));

  // Ledger-less COA-only matches don't correspond to any real invoice, so they're kept out of
  // invoice aggregation — they only need to surface in the Bank Results / voucherMatches view.
  const invoiceSummary: InvoiceSummary[] = aggregateInvoices(ledgerRows, voucherMatches);

  const stats: MatchingStats = {
    totalInvoices: invoiceSummary.length,
    fullySettled: invoiceSummary.filter((s) => s.status === "Fully Settled").length,
    partiallySettled: invoiceSummary.filter((s) => s.status === "Partially Settled").length,
    notSettled: invoiceSummary.filter((s) => s.status === "Not Settled").length,
    mismatched: invoiceSummary.filter((s) => s.status === "Overpaid/Mismatch").length,
    needsReview: invoiceSummary.filter((s) => s.status === "Needs Review").length,
    totalBankTxns: bankTxns.length,
    matchedBankTxns: bankTxns.length - unmatchedBankTxnIndexes.length,
  };

  return { mode, voucherMatches: allVoucherMatches, invoiceSummary, unmatchedBankTxnIndexes, stats };
}

export { DEFAULT_OPTIONS };
export type { MatchingOptions, MatchingResult, VoucherMatch, InvoiceSummary, MatchingStats };
