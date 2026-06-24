import { z } from "zod";

export const BrsItemTypeSchema = z.enum([
  "DEPOSIT_IN_TRANSIT",
  "OUTSTANDING_CHECK",
  "BANK_CHARGE",
  "BANK_INTEREST",
  "BOOK_ERROR",
  "BANK_ERROR",
  "NSF_CHECK",
  "DIRECT_DEPOSIT",
  "OTHER_ADDITION",
  "OTHER_DEDUCTION",
]);

export const BrsEffectSchema = z.enum([
  "ADD_TO_BANK",
  "DEDUCT_FROM_BANK",
  "ADD_TO_BOOK",
  "DEDUCT_FROM_BOOK",
]);

export const BrsAffectsSideSchema = z.enum(["BANK", "BOOK", "BOTH"]);

export const BrsDocumentInfoSchema = z.object({
  company_name: z.string().nullable(),
  bank_name: z.string().nullable(),
  account_number: z.string().nullable(),
  statement_period_start: z.string().nullable(),
  statement_period_end: z.string().nullable(),
  currency: z.string().nullable(),
  prepared_by: z.string().nullable(),
  prepared_date: z.string().nullable(),
});

export const BrsBalanceSchema = z.object({
  opening_balance_bank: z.number().nullable(),
  opening_balance_book: z.number().nullable(),
  closing_balance_bank: z.number().nullable(),
  closing_balance_book: z.number().nullable(),
  reconciled_balance: z.number().nullable(),
});

export const BrsReconciliationItemSchema = z.object({
  item_type: BrsItemTypeSchema.nullable(),
  description: z.string().nullable(),
  reference_number: z.string().nullable(),
  date: z.string().nullable(),
  amount: z.number(),
  effect: BrsEffectSchema,
  affects_side: BrsAffectsSideSchema,
});

export const BrsDataSchema = z.object({
  document_info: BrsDocumentInfoSchema,
  balances: BrsBalanceSchema,
  bank_side_items: z.array(BrsReconciliationItemSchema),
  book_side_items: z.array(BrsReconciliationItemSchema),
  adjusted_bank_balance: z.number().nullable(),
  adjusted_book_balance: z.number().nullable(),
});

export const BrsConfidenceSchema = z.object({
  overall: z.number(),
  opening_balance_bank: z.number(),
  opening_balance_book: z.number(),
  closing_balance_bank: z.number(),
  closing_balance_book: z.number(),
  bank_side_items: z.number(),
  book_side_items: z.number(),
  reconciled_balance: z.number(),
});

export const BrsRuleCheckSchema = z.object({
  rule: z.string(),
  passed: z.boolean(),
  message: z.string(),
  field: z.string().nullable(),
});

export const BrsLLMCheckSchema = z.object({
  check: z.string(),
  result: z.enum(["PASS", "FAIL", "UNCERTAIN"]),
  confidence: z.number(),
  message: z.string(),
  field: z.string().nullable(),
});

export const BrsValidationSchema = z.object({
  status: z.enum(["VALID", "NEEDS_REVIEW", "INVALID", "PENDING"]),
  rule_checks: z.array(BrsRuleCheckSchema),
  llm_checks: z.array(BrsLLMCheckSchema),
  warnings: z.array(z.string()),
  errors: z.array(z.string()),
});

export const BrsMetadataSchema = z.object({
  processing_mode: z.string().nullable(),
  pages: z.number(),
});

export const BrsOutputSchema = z.object({
  document_id: z.string(),
  brs: BrsDataSchema,
  confidence: BrsConfidenceSchema,
  validation: BrsValidationSchema,
  metadata: BrsMetadataSchema,
});
