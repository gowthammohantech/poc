/**
 * Split/combined deposit matching — runs only over whatever Waves A/B (voucherScoring.ts)
 * left unmatched, only within the date window, only among direction-consistent candidates
 * (a hard filter here, not a scored criterion — a combination mixing a credit and a debit
 * leg doesn't make deposit/withdrawal sense and is never considered). Capped at combination
 * size 3 and a pool size of 15 per row (skip the search entirely for a row whose windowed
 * leftover pool exceeds that, rather than silently truncating it) to keep the search bounded.
 *
 * Two sequential sub-passes, C then D, each consuming what it finds before the next starts —
 * this is the determinism rule for this layer, mirroring the sort-then-greedy-consume pattern
 * used for the primary pairwise assignment.
 */
import type { BrsTransaction } from "@/types/brs";
import type { LedgerRow, MatchingOptions } from "@/types/matching";
import { toCents, daysBetween, normalizeDate } from "./normalize";
import { dateWindowCandidates, type BankTxnIndex } from "./candidateIndex";
import { directionForTxn, bankAmountCents, anchorAmount, anchorDate as ledgerAnchorDate, type AssignmentResult } from "./voucherScoring";

export interface CombinedMatch {
  ledgerRowIndexes: number[];
  bankTxnIndexes: number[];
  score: number;
}

function dateProximity(ledgerDate: string | null, bankDate: string | null, toleranceDays: number, weight: number): number {
  const diff = daysBetween(ledgerDate, bankDate);
  if (diff == null || diff >= toleranceDays) return 0;
  return weight * (1 - diff / toleranceDays);
}

/** First combination of size 2, then size 3 (only if no size-2 hit), whose cents sum matches exactly. Deterministic: pool is iterated in ascending order. */
function findCombination(pool: number[], amountOf: (i: number) => number | null, targetCents: number, maxSize: number): number[] | null {
  const sorted = [...pool].sort((a, b) => a - b);
  const n = sorted.length;

  for (let i = 0; i < n; i++) {
    const ai = amountOf(sorted[i]);
    if (ai == null) continue;
    for (let j = i + 1; j < n; j++) {
      const aj = amountOf(sorted[j]);
      if (aj == null) continue;
      if (ai + aj === targetCents) return [sorted[i], sorted[j]];
    }
  }

  if (maxSize < 3) return null;
  for (let i = 0; i < n; i++) {
    const ai = amountOf(sorted[i]);
    if (ai == null) continue;
    for (let j = i + 1; j < n; j++) {
      const aj = amountOf(sorted[j]);
      if (aj == null) continue;
      for (let k = j + 1; k < n; k++) {
        const ak = amountOf(sorted[k]);
        if (ak == null) continue;
        if (ai + aj + ak === targetCents) return [sorted[i], sorted[j], sorted[k]];
      }
    }
  }
  return null;
}

function combinedScore(legCount: number, avgDateProximity: number, options: MatchingOptions): number {
  const { weights } = options;
  const penalty = 5 * Math.max(0, legCount - 2);
  const raw = weights.amount + avgDateProximity + weights.direction - penalty;
  return Math.max(0, Math.min(100, raw));
}

export function runCombinationSearch(
  bankTxns: BrsTransaction[],
  ledgerRows: LedgerRow[],
  bankIndex: BankTxnIndex,
  primary: AssignmentResult,
  options: MatchingOptions
): CombinedMatch[] {
  const results: CombinedMatch[] = [];
  const leftoverBank = new Set(bankTxns.map((_, i) => i).filter((i) => !primary.usedBankTxns.has(i)));
  let leftoverLedger = primary.settlementLedgerIndexes.filter((i) => !primary.assignments.has(i));

  // Wave C — N leftover bank txns summing to one leftover ledger row's amount.
  const consumedLedger = new Set<number>();
  for (const li of leftoverLedger) {
    const row = ledgerRows[li];
    const targetCents = toCents(anchorAmount(row));
    const rowAnchorDate = ledgerAnchorDate(row);
    if (targetCents == null || !rowAnchorDate) continue;

    const pool = dateWindowCandidates(bankIndex, rowAnchorDate, options.dateToleranceDays, leftoverBank).filter(
      (bi) => directionForTxn(bankTxns[bi]) === row.transaction_type
    );
    if (pool.length === 0 || pool.length > options.maxCombinationPoolSize) continue;

    const combo = findCombination(pool, (bi) => bankAmountCents(bankTxns[bi]), targetCents, options.maxCombinationSize);
    if (!combo) continue;

    const avgDate = combo.reduce((sum, bi) => sum + dateProximity(rowAnchorDate, normalizeDate(bankTxns[bi].transaction_date), options.dateToleranceDays, options.weights.date), 0) / combo.length;

    results.push({
      ledgerRowIndexes: [li],
      bankTxnIndexes: combo,
      score: combinedScore(combo.length, avgDate, options),
    });
    combo.forEach((bi) => leftoverBank.delete(bi));
    consumedLedger.add(li);
  }
  leftoverLedger = leftoverLedger.filter((li) => !consumedLedger.has(li));

  // Wave D — N leftover ledger rows summing to one leftover bank txn's amount. Runs after C,
  // over C's updated leftovers, so neither pass can double-claim an item.
  const remainingBank = [...leftoverBank].sort((a, b) => a - b);
  for (const bi of remainingBank) {
    if (!leftoverBank.has(bi)) continue; // may have been consumed by an earlier Wave D iteration
    const txn = bankTxns[bi];
    const targetCents = bankAmountCents(txn);
    const anchorDate = normalizeDate(txn.transaction_date);
    const direction = directionForTxn(txn);
    if (targetCents == null || !anchorDate || !direction) continue;

    const pool = leftoverLedger.filter((li) => {
      const row = ledgerRows[li];
      if (row.transaction_type !== direction) return false;
      const diff = daysBetween(ledgerAnchorDate(row), anchorDate);
      return diff != null && diff <= options.dateToleranceDays;
    });
    if (pool.length === 0 || pool.length > options.maxCombinationPoolSize) continue;

    const combo = findCombination(pool, (li) => toCents(anchorAmount(ledgerRows[li])), targetCents, options.maxCombinationSize);
    if (!combo) continue;

    const avgDate = combo.reduce((sum, li) => sum + dateProximity(ledgerAnchorDate(ledgerRows[li]), anchorDate, options.dateToleranceDays, options.weights.date), 0) / combo.length;

    results.push({
      ledgerRowIndexes: combo,
      bankTxnIndexes: [bi],
      score: combinedScore(combo.length, avgDate, options),
    });
    combo.forEach((li) => {
      leftoverLedger = leftoverLedger.filter((x) => x !== li);
    });
    leftoverBank.delete(bi);
  }

  return results;
}
