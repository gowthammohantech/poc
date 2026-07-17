/**
 * Layer 3 — scored matching. Computes a 0-100 composite score per (ledger row, bank txn)
 * candidate pair and runs a deterministic two-wave greedy assignment.
 *
 * Two waves, not one flat pass, deliberately: if every candidate pair (direction-consistent or
 * not) were sorted into a single list by score, a strongly-scored but direction-WRONG pair
 * (e.g. amount+date both line up, 50+40+0=90) could consume a contested bank
 * transaction before a weaker-but-correct pair elsewhere in the dataset ever gets a chance at
 * it — the mismatched pair still ends up capped to "Partially Matched", but it may have starved
 * a legitimately correct match of its bank transaction in the process. Wave A only considers
 * direction-consistent pairs (mirrors accounting reality: Sales Receipt ↔ bank credit, Purchase
 * Payment ↔ bank debit); only once that's fully resolved does Wave B look at the leftovers.
 */
import type { BrsTransaction } from "@/types/brs";
import type { LedgerRow, MatchingOptions } from "@/types/matching";
import { toCents, daysBetween, normalizeDate } from "./normalize";
import { buildBankTxnIndex, candidatesFor, type BankTxnIndex } from "./candidateIndex";

// Reference/voucher matching was dropped as a scoring criterion — it proved unreliable across
// real invoices/ledgers (bank narrations rarely carry a clean, comparable reference), so it was
// removed rather than left as noisy signal. Amount takes the weight it used to hold; Date keeps
// its share; Direction is unchanged.
export const DEFAULT_OPTIONS: MatchingOptions = {
  dateToleranceDays: 5,
  minMatchScore: 60,
  matchedScoreThreshold: 85,
  weights: { amount: 50, date: 40, direction: 10 },
  maxCombinationSize: 3,
  maxCombinationPoolSize: 15,
  accountNameMatchThreshold: 0.75,
  fuzzyAccountThreshold: 0.6,
};

export function directionForTxn(txn: BrsTransaction): LedgerRow["transaction_type"] | null {
  if (txn.credit != null && txn.credit > 0) return "Sales Receipt";
  if (txn.debit != null && txn.debit > 0) return "Purchase Payment";
  return null;
}

export function bankAmountCents(txn: BrsTransaction): number | null {
  if (txn.credit != null && txn.credit > 0) return toCents(txn.credit);
  if (txn.debit != null && txn.debit > 0) return toCents(txn.debit);
  return null;
}

/**
 * The date/amount to match a ledger row against a bank transaction: the settlement leg's own
 * values if recorded, else the invoice's own date/amount. An invoice-only row (no separate
 * Ledger Date/Voucher/Amount entered yet) is matched directly against its own expected date and
 * amount — a bank transaction whose date and amount exactly match the invoice is itself strong
 * evidence that this invoice was paid, even before a formal settlement voucher is recorded.
 */
export function anchorDate(row: LedgerRow): string | null {
  return normalizeDate(row.ledger_date ?? row.invoice_date);
}

export function anchorAmount(row: LedgerRow): number | null {
  return row.ledger_amount ?? row.invoice_amount;
}

export interface PairScore {
  ledgerRowIndex: number;
  bankTxnIndex: number;
  amountScore: number;
  dateScore: number;
  directionConsistent: boolean;
  score: number;
  failedCriteria: string[];
}

/** Full points at 0 days, linear decay to 0 at the tolerance window edge. */
function dateProximityScore(ledgerDate: string | null, bankDate: string | null, toleranceDays: number, weight: number): number {
  const diff = daysBetween(ledgerDate, bankDate);
  if (diff == null) return 0;
  if (diff >= toleranceDays) return 0;
  return weight * (1 - diff / toleranceDays);
}

export function scorePair(
  txn: BrsTransaction,
  ledgerRow: LedgerRow,
  options: MatchingOptions = DEFAULT_OPTIONS
): PairScore {
  const { weights, dateToleranceDays } = options;

  const ledgerCents = toCents(anchorAmount(ledgerRow));
  const amountScore = ledgerCents != null && ledgerCents === bankAmountCents(txn) ? weights.amount : 0;

  const dateScore = dateProximityScore(anchorDate(ledgerRow), normalizeDate(txn.transaction_date), dateToleranceDays, weights.date);

  const directionConsistent = directionForTxn(txn) === ledgerRow.transaction_type;
  const directionScore = directionConsistent ? weights.direction : 0;

  const failedCriteria: string[] = [];
  if (amountScore === 0) failedCriteria.push("amount_mismatch");
  if (dateScore === 0) failedCriteria.push("date_out_of_range");
  if (!directionConsistent) failedCriteria.push("direction_mismatch");

  return {
    ledgerRowIndex: -1,
    bankTxnIndex: -1,
    amountScore,
    dateScore,
    directionConsistent,
    score: amountScore + dateScore + directionScore,
    failedCriteria,
  };
}

export interface AssignmentResult {
  index: BankTxnIndex;
  assignments: Map<number, PairScore>; // ledgerRowIndex -> chosen pair
  usedBankTxns: Set<number>;
  settlementLedgerIndexes: number[]; // indexes of ledger rows with a usable matching anchor (settlement leg or invoice date/amount)
}

/** True if a ledger row has enough data to be matched against a bank transaction at all — either
 * a complete settlement leg, or (falling back) a usable invoice date + amount. */
export function hasSettlement(row: LedgerRow): boolean {
  return Boolean(anchorDate(row) && anchorAmount(row) != null);
}

function buildTriples(
  ledgerRows: LedgerRow[],
  ledgerIndexes: number[],
  bankTxns: BrsTransaction[],
  index: BankTxnIndex,
  availableBank: ReadonlySet<number>,
  options: MatchingOptions,
  requireDirectionConsistent: boolean
): PairScore[] {
  const triples: PairScore[] = [];
  for (const li of ledgerIndexes) {
    const row = ledgerRows[li];
    const ledgerCents = toCents(anchorAmount(row));
    const rowAnchorDate = anchorDate(row);
    const candidates = candidatesFor(index, rowAnchorDate, ledgerCents, options.dateToleranceDays, availableBank);
    for (const bi of candidates) {
      const txn = bankTxns[bi];
      const consistent = directionForTxn(txn) === row.transaction_type;
      if (consistent !== requireDirectionConsistent) continue;
      const pair = scorePair(txn, row, options);
      triples.push({ ...pair, ledgerRowIndex: li, bankTxnIndex: bi });
    }
  }
  return triples;
}

function sortTriples(triples: PairScore[]): PairScore[] {
  return [...triples].sort(
    (a, b) => b.score - a.score || a.ledgerRowIndex - b.ledgerRowIndex || a.bankTxnIndex - b.bankTxnIndex
  );
}

/**
 * Runs Wave A (direction-consistent only) then Wave B (leftovers, direction-inconsistent) and
 * returns the chosen assignment per ledger row plus which bank txns remain unused. Callers are
 * responsible for capping Wave-B-assigned status at "Partially Matched" (this function reports
 * `directionConsistent: false` on those pairs so status derivation downstream can apply the cap).
 */
export function runTwoWaveAssignment(
  bankTxns: BrsTransaction[],
  ledgerRows: LedgerRow[],
  options: MatchingOptions = DEFAULT_OPTIONS
): AssignmentResult {
  const index = buildBankTxnIndex(bankTxns);
  const settlementLedgerIndexes = ledgerRows.reduce<number[]>((acc, row, i) => {
    if (hasSettlement(row)) acc.push(i);
    return acc;
  }, []);

  const usedBank = new Set<number>();
  const usedLedger = new Set<number>();
  const assignments = new Map<number, PairScore>();

  // Wave A — direction-consistent candidates only.
  const waveA = sortTriples(
    buildTriples(ledgerRows, settlementLedgerIndexes, bankTxns, index, new Set(bankTxns.map((_, i) => i)), options, true)
  );
  for (const triple of waveA) {
    if (usedLedger.has(triple.ledgerRowIndex) || usedBank.has(triple.bankTxnIndex)) continue;
    if (triple.score < options.minMatchScore) continue;
    usedLedger.add(triple.ledgerRowIndex);
    usedBank.add(triple.bankTxnIndex);
    assignments.set(triple.ledgerRowIndex, triple);
  }

  // Wave B — leftovers, direction-inconsistent by construction (consistent pairs were already
  // fully explored in Wave A regardless of outcome).
  const remainingLedger = settlementLedgerIndexes.filter((i) => !usedLedger.has(i));
  const remainingBank = new Set(bankTxns.map((_, i) => i).filter((i) => !usedBank.has(i)));
  const waveB = sortTriples(buildTriples(ledgerRows, remainingLedger, bankTxns, index, remainingBank, options, false));
  for (const triple of waveB) {
    if (usedLedger.has(triple.ledgerRowIndex) || usedBank.has(triple.bankTxnIndex)) continue;
    if (triple.score < options.minMatchScore) continue;
    usedLedger.add(triple.ledgerRowIndex);
    usedBank.add(triple.bankTxnIndex);
    assignments.set(triple.ledgerRowIndex, triple);
  }

  return { index, assignments, usedBankTxns: usedBank, settlementLedgerIndexes };
}
