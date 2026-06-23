import { z } from "zod";

export const VendorSchema = z.object({
  name: z.string().nullable().optional(),
  gstin: z.string().nullable().optional(),
  pan: z.string().nullable().optional(),
  address: z.string().nullable().optional(),
  phone: z.string().nullable().optional(),
  email: z.string().nullable().optional(),
});

export const CustomerSchema = z.object({
  name: z.string().nullable().optional(),
  gstin: z.string().nullable().optional(),
  address: z.string().nullable().optional(),
});

export const LineItemSchema = z.object({
  description: z.string().nullable().optional(),
  hsn_sac: z.string().nullable().optional(),
  quantity: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
  unit_price: z.number().nullable().optional(),
  taxable_value: z.number().nullable().optional(),
  cgst_rate: z.number().nullable().optional(),
  cgst_amount: z.number().nullable().optional(),
  sgst_rate: z.number().nullable().optional(),
  sgst_amount: z.number().nullable().optional(),
  igst_rate: z.number().nullable().optional(),
  igst_amount: z.number().nullable().optional(),
  total: z.number().nullable().optional(),
});

export const TaxSummarySchema = z.object({
  subtotal: z.number().nullable().optional(),
  cgst_total: z.number().nullable().optional(),
  sgst_total: z.number().nullable().optional(),
  igst_total: z.number().nullable().optional(),
  total_tax: z.number().nullable().optional(),
  round_off: z.number().nullable().optional(),
  grand_total: z.number().nullable().optional(),
});

export const BankDetailsSchema = z.object({
  account_name: z.string().nullable().optional(),
  account_number: z.string().nullable().optional(),
  bank_name: z.string().nullable().optional(),
  ifsc: z.string().nullable().optional(),
  branch: z.string().nullable().optional(),
});

export const InvoiceDataSchema = z.object({
  invoice_number: z.string().nullable().optional(),
  invoice_date: z.string().nullable().optional(),
  due_date: z.string().nullable().optional(),
  currency: z.string().nullable().optional(),
  vendor: VendorSchema.optional().default({}),
  customer: CustomerSchema.optional().default({}),
  purchase_order_number: z.string().nullable().optional(),
  line_items: z.array(LineItemSchema).optional().default([]),
  tax_summary: TaxSummarySchema.optional().default({}),
  bank_details: BankDetailsSchema.optional().default({}),
});

export const ConfidenceSchema = z.object({
  overall: z.number().default(0),
  invoice_number: z.number().default(0),
  invoice_date: z.number().default(0),
  gstin: z.number().default(0),
  line_items: z.number().default(0),
  totals: z.number().default(0),
});

export const RuleCheckSchema = z.object({
  rule: z.string(),
  passed: z.boolean(),
  message: z.string(),
  field: z.string().nullable().optional(),
});

export const LLMCheckSchema = z.object({
  check: z.string(),
  result: z.enum(["PASS", "FAIL", "UNCERTAIN"]),
  confidence: z.number(),
  message: z.string(),
  field: z.string().nullable().optional(),
});

export const ValidationSchema = z.object({
  status: z.enum(["VALID", "NEEDS_REVIEW", "INVALID", "PENDING"]),
  rule_checks: z.array(RuleCheckSchema).default([]),
  llm_checks: z.array(LLMCheckSchema).default([]),
  warnings: z.array(z.string()).default([]),
  errors: z.array(z.string()).default([]),
});

export const MetadataSchema = z.object({
  ocr_engine: z.string().nullable().optional(),
  complexity_score: z.number().nullable().optional(),
  processing_mode: z.string().nullable().optional(),
  pages: z.number().default(0),
});

export const InvoiceOutputSchema = z.object({
  document_id: z.string(),
  invoice: InvoiceDataSchema.default({}),
  confidence: ConfidenceSchema.default({ overall: 0, invoice_number: 0, invoice_date: 0, gstin: 0, line_items: 0, totals: 0 }),
  validation: ValidationSchema.default({ status: "PENDING", rule_checks: [], llm_checks: [], warnings: [], errors: [] }),
  metadata: MetadataSchema.default({ pages: 0 }),
});

export type InvoiceOutput = z.infer<typeof InvoiceOutputSchema>;
export type InvoiceData = z.infer<typeof InvoiceDataSchema>;
export type LineItem = z.infer<typeof LineItemSchema>;
