/**
 * Layer 2 — candidate generation. Indexes bank transactions by normalized amount and by
 * day-bucket so per-ledger-row candidate lookups avoid a blind O(n×m) scan even with a few
 * thousand rows on each side.
 */
import type { BrsTransaction } from "@/types/brs";
import { normalizeDate, toCents, addDaysIso } from "./normalize";

export interface BankTxnIndex {
  amountCents: (number | null)[];
  dateIso: (string | null)[];
  byAmountCents: Map<number, number[]>;
  byDateBucket: Map<string, number[]>;
}

function bankAmountCents(txn: BrsTransaction): number | null {
  if (txn.credit != null && txn.credit > 0) return toCents(txn.credit);
  if (txn.debit != null && txn.debit > 0) return toCents(txn.debit);
  return null;
}

export function buildBankTxnIndex(bankTxns: BrsTransaction[]): BankTxnIndex {
  const amountCents: (number | null)[] = [];
  const dateIso: (string | null)[] = [];
  const byAmountCents = new Map<number, number[]>();
  const byDateBucket = new Map<string, number[]>();

  bankTxns.forEach((txn, i) => {
    const cents = bankAmountCents(txn);
    const iso = normalizeDate(txn.transaction_date);
    amountCents.push(cents);
    dateIso.push(iso);

    if (cents != null) {
      const arr = byAmountCents.get(cents);
      if (arr) arr.push(i);
      else byAmountCents.set(cents, [i]);
    }
    if (iso) {
      const arr = byDateBucket.get(iso);
      if (arr) arr.push(i);
      else byDateBucket.set(iso, [i]);
    }
  });

  return { amountCents, dateIso, byAmountCents, byDateBucket };
}

/**
 * All bank txn indexes within [anchorDate - toleranceDays, anchorDate + toleranceDays]
 * (inclusive of both boundary days — merges every bucket in the window, not just the exact
 * day), intersected with `available`. Returns [] if the anchor date itself is unparseable.
 */
export function dateWindowCandidates(
  index: BankTxnIndex,
  anchorDateIso: string | null,
  toleranceDays: number,
  available: ReadonlySet<number>
): number[] {
  if (!anchorDateIso) return [];
  const result: number[] = [];
  for (let offset = -toleranceDays; offset <= toleranceDays; offset++) {
    const bucketDate = offset === 0 ? anchorDateIso : addDaysIso(anchorDateIso, offset);
    const bucket = index.byDateBucket.get(bucketDate);
    if (!bucket) continue;
    for (const i of bucket) {
      if (available.has(i)) result.push(i);
    }
  }
  return result;
}

/** Bank txn indexes with exactly this cents amount, intersected with `available`. */
export function exactAmountCandidates(
  index: BankTxnIndex,
  cents: number | null,
  available: ReadonlySet<number>
): number[] {
  if (cents == null) return [];
  const bucket = index.byAmountCents.get(cents);
  if (!bucket) return [];
  return bucket.filter((i) => available.has(i));
}

/**
 * The candidate pool for one ledger row: same-amount matches within the date window first
 * (cheapest, highest-quality candidates); if none exist, fall back to the full date-window
 * pool so reference/date signals can still surface a Partially Matched explanation instead of
 * the row silently having zero candidates.
 */
export function candidatesFor(
  index: BankTxnIndex,
  anchorDateIso: string | null,
  amountCents: number | null,
  toleranceDays: number,
  available: ReadonlySet<number>
): number[] {
  const windowed = dateWindowCandidates(index, anchorDateIso, toleranceDays, available);
  if (amountCents == null) return windowed;
  const windowedSet = new Set(windowed);
  const exact = exactAmountCandidates(index, amountCents, available).filter((i) => windowedSet.has(i));
  return exact.length > 0 ? exact : windowed;
}
