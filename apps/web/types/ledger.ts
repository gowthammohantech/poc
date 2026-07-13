import type { BrsBankTransaction } from "./brs";

export type LedgerEntryType = "DEBIT" | "CREDIT";

export interface LedgerEntry {
  id: string;
  entry_date: string;
  ledger_name: string | null;
  description: string;
  reference_number: string | null;
  amount: number;
  entry_type: LedgerEntryType;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LedgerEntryInput {
  entry_date: string;
  ledger_name: string | null;
  description: string;
  reference_number: string | null;
  amount: number;
  entry_type: LedgerEntryType;
  notes: string | null;
}

export interface MatchedPair {
  bank_transaction: BrsBankTransaction;
  ledger_entry: LedgerEntry;
  match_type: "EXACT" | "FUZZY";
  confidence: number;
  date_diff_days: number | null;
  amount_diff: number;
}

export interface MatchSummary {
  total_bank: number;
  total_ledger: number;
  matched: number;
  unmatched_bank: number;
  unmatched_ledger: number;
  match_rate: number;
}

export interface MatchReport {
  summary: MatchSummary;
  matched: MatchedPair[];
  unmatched_bank: BrsBankTransaction[];
  unmatched_ledger: LedgerEntry[];
}
