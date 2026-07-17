/**
 * Layer 5 — 3-way COA validation. Relocated near-unchanged from the previous single-file
 * engine: this logic (name similarity tolerant of case/spacing/symbols, narration-based fuzzy
 * fallback, tolerant Bank/Cash type matching) was already solid and hand-verified against real
 * messy data earlier in this project — no algorithmic changes here, just a new home.
 */
import type { CoaRow } from "@/types/matching";
import { normalizeText, alnumOnly, similarity, MIN_SUBSTRING_LEN } from "./normalize";

export const DEFAULT_ACCOUNT_NAME_MATCH_THRESHOLD = 0.75;
export const DEFAULT_FUZZY_ACCOUNT_THRESHOLD = 0.6;

/**
 * How strongly two account names refer to the same account, 0-1 — tolerant of case, spacing,
 * and punctuation/symbol differences ("Bank A/c" vs "bank ac" vs "BANK-A.C" all read the same).
 */
export function accountNameSimilarity(a: string | null | undefined, b: string | null | undefined): number {
  const na = normalizeText(a);
  const nb = normalizeText(b);
  if (!na || !nb) return 0;
  if (na === nb) return 1;

  const aa = alnumOnly(a);
  const ab = alnumOnly(b);
  if (aa && ab) {
    if (aa === ab) return 1;
    if (aa.length >= MIN_SUBSTRING_LEN && ab.length >= MIN_SUBSTRING_LEN && (aa.includes(ab) || ab.includes(aa))) {
      return 0.95;
    }
    return similarity(aa, ab);
  }

  return similarity(na, nb);
}

/** True if a COA account_type reads as Bank or Cash, tolerant of labels like "Bank Account" or "Cash-in-Hand". */
export function isBankOrCashType(accountType: string | null | undefined): boolean {
  const t = normalizeText(accountType);
  return t.includes("bank") || t.includes("cash");
}

/** Word-level fuzzy score of a COA account name against free-form bank narration text (0-1). */
export function narrationAccountScore(narration: string | null | undefined, accountName: string): number {
  const n = normalizeText(narration);
  const acc = normalizeText(accountName);
  if (!n || !acc) return 0;
  if (n.includes(acc)) return 1;

  const nAlnum = alnumOnly(narration);
  const accAlnum = alnumOnly(accountName);
  if (accAlnum.length >= MIN_SUBSTRING_LEN && nAlnum.includes(accAlnum)) return 0.95;

  const narrationWords = n.split(/\s+/).filter((w) => w.length >= MIN_SUBSTRING_LEN);
  const accountWords = acc.split(/\s+/).filter((w) => w.length >= MIN_SUBSTRING_LEN);
  let best = 0;
  for (const aw of accountWords) {
    if (n.includes(aw)) {
      best = Math.max(best, 0.85);
      continue;
    }
    for (const nw of narrationWords) {
      best = Math.max(best, similarity(aw, nw));
    }
  }
  return best;
}

export interface AccountMatch {
  row: CoaRow;
  type: "name" | "fuzzy";
  score: number;
}

/**
 * Resolve a free-text account name (typed on the ledger row) against a pool of COA rows: first
 * try a near-exact name match, then fall back to fuzzy-matching the bank narration against each
 * candidate's account name. `pool` should already be restricted to whichever COA rows are
 * eligible (e.g. Bank/Cash only) — this function doesn't filter by type itself.
 */
export function bestAccountMatch(
  accountName: string | null | undefined,
  narration: string | null | undefined,
  pool: CoaRow[],
  nameThreshold = DEFAULT_ACCOUNT_NAME_MATCH_THRESHOLD,
  fuzzyThreshold = DEFAULT_FUZZY_ACCOUNT_THRESHOLD
): AccountMatch | null {
  if (accountName) {
    let best: { row: CoaRow; score: number } | null = null;
    for (const row of pool) {
      const score = accountNameSimilarity(accountName, row.account_name);
      if (score >= nameThreshold && (!best || score > best.score)) {
        best = { row, score };
      }
    }
    if (best) return { row: best.row, type: "name", score: best.score };
  }

  let bestFuzzy: { row: CoaRow; score: number } | null = null;
  for (const row of pool) {
    const score = narrationAccountScore(narration, row.account_name);
    if (score >= fuzzyThreshold && (!bestFuzzy || score > bestFuzzy.score)) {
      bestFuzzy = { row, score };
    }
  }
  if (bestFuzzy) return { row: bestFuzzy.row, type: "fuzzy", score: bestFuzzy.score };

  return null;
}
