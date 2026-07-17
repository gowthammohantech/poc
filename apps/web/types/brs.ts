export type BrsItemType =
  | "DEPOSIT_IN_TRANSIT"
  | "OUTSTANDING_CHECK"
  | "BANK_CHARGE"
  | "BANK_INTEREST"
  | "BOOK_ERROR"
  | "BANK_ERROR"
  | "NSF_CHECK"
  | "DIRECT_DEPOSIT"
  | "OTHER_ADDITION"
  | "OTHER_DEDUCTION";

export type BrsEffect =
  | "ADD_TO_BANK"
  | "DEDUCT_FROM_BANK"
  | "ADD_TO_BOOK"
  | "DEDUCT_FROM_BOOK";

export type BrsAffectsSide = "BANK" | "BOOK" | "BOTH";

export interface BrsDocumentInfo {
  company_name: string | null;
  bank_name: string | null;
  account_number: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  currency: string | null;
  prepared_by: string | null;
  prepared_date: string | null;
}

export interface BrsBalances {
  opening_balance_bank: number | null;
  opening_balance_book: number | null;
  closing_balance_bank: number | null;
  closing_balance_book: number | null;
  reconciled_balance: number | null;
}

export interface BrsReconciliationItem {
  item_type: BrsItemType | null;
  description: string | null;
  reference_number: string | null;
  date: string | null;
  amount: number;
  effect: BrsEffect;
  affects_side: BrsAffectsSide;
}

export interface BrsData {
  document_info: BrsDocumentInfo;
  balances: BrsBalances;
  bank_side_items: BrsReconciliationItem[];
  book_side_items: BrsReconciliationItem[];
  adjusted_bank_balance: number | null;
  adjusted_book_balance: number | null;
}

export interface BrsConfidence {
  overall: number;
  opening_balance_bank: number;
  opening_balance_book: number;
  closing_balance_bank: number;
  closing_balance_book: number;
  bank_side_items: number;
  book_side_items: number;
  reconciled_balance: number;
}

export interface BrsRuleCheck {
  rule: string;
  passed: boolean;
  message: string;
  field: string | null;
}

export interface BrsLLMCheck {
  check: string;
  result: "PASS" | "FAIL" | "UNCERTAIN";
  confidence: number;
  message: string;
  field: string | null;
}

export interface BrsValidation {
  status: "VALID" | "NEEDS_REVIEW" | "INVALID" | "PENDING";
  rule_checks: BrsRuleCheck[];
  llm_checks: BrsLLMCheck[];
  warnings: string[];
  errors: string[];
}

export interface BrsMetadata {
  processing_mode: string | null;
  pages: number;
}

export interface BrsOutput {
  document_id: string;
  brs: BrsData;
  confidence: BrsConfidence;
  validation: BrsValidation;
  metadata: BrsMetadata;
}

export interface BrsStatementDocumentInfo {
  company_name: string | null;
  bank_name: string | null;
  account_number: string | null;
  statement_period_start: string | null;
  statement_period_end: string | null;
  currency: string | null;
}

export interface BrsStatementTotals {
  total_debit_count: number | null;
  total_credit_count: number | null;
  total_debit_amount: number | null;
  total_credit_amount: number | null;
}

export interface BrsTransaction {
  transaction_date: string | null;
  narration: string | null;
  reference_number: string | null;
  debit: number | null;
  credit: number | null;
  balance: number | null;
}

export interface BrsBankStatement {
  document_info: BrsStatementDocumentInfo;
  opening_balance: number | null;
  closing_balance: number | null;
  statement_totals: BrsStatementTotals;
  transactions: BrsTransaction[];
}

export interface BrsReviewData {
  document_id: string;
  status: string;
  page_urls: string[];
  brs: BrsData;
  bank_statement: BrsBankStatement | null;
  coa: unknown[];
  ledger: unknown[];
  confidence: BrsConfidence;
  validation: BrsValidation;
}

export interface BrsUploadResponse {
  document_id: string;
  filename: string;
  status: string;
  page_count: number;
  message: string;
}

export interface BrsDocument {
  id: string;
  filename: string;
  status: string;
  page_count: number;
  processing_mode: string | null;
  created_at: string;
}
