export interface Vendor {
  name: string | null;
  gstin: string | null;
  pan: string | null;
  address: string | null;
  phone: string | null;
  email: string | null;
}

export interface Customer {
  name: string | null;
  gstin: string | null;
  address: string | null;
}

export interface LineItem {
  description: string | null;
  hsn_sac: string | null;
  quantity: number | null;
  unit: string | null;
  unit_price: number | null;
  taxable_value: number | null;
  cgst_rate: number | null;
  cgst_amount: number | null;
  sgst_rate: number | null;
  sgst_amount: number | null;
  igst_rate: number | null;
  igst_amount: number | null;
  total: number | null;
}

export interface TaxSummary {
  subtotal: number | null;
  cgst_total: number | null;
  sgst_total: number | null;
  igst_total: number | null;
  total_tax: number | null;
  round_off: number | null;
  grand_total: number | null;
}

export interface BankDetails {
  account_name: string | null;
  account_number: string | null;
  bank_name: string | null;
  ifsc: string | null;
  branch: string | null;
}

export interface InvoiceData {
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string | null;
  vendor: Vendor;
  customer: Customer;
  purchase_order_number: string | null;
  line_items: LineItem[];
  tax_summary: TaxSummary;
  bank_details: BankDetails;
}

export interface Confidence {
  overall: number;
  invoice_number: number;
  invoice_date: number;
  gstin: number;
  line_items: number;
  totals: number;
}

export interface RuleCheck {
  rule: string;
  passed: boolean;
  message: string;
  field: string | null;
}

export interface LLMCheck {
  check: string;
  result: "PASS" | "FAIL" | "UNCERTAIN";
  confidence: number;
  message: string;
  field: string | null;
}

export interface Validation {
  status: "VALID" | "NEEDS_REVIEW" | "INVALID" | "PENDING";
  rule_checks: RuleCheck[];
  llm_checks: LLMCheck[];
  warnings: string[];
  errors: string[];
}

export interface InvoiceMetadata {
  ocr_engine: string | null;
  complexity_score: number | null;
  processing_mode: string | null;
  pages: number;
}

export interface OcrBox {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
}

export interface OcrReferencePage {
  width: number;
  height: number;
  boxes: OcrBox[];
}

export interface OcrReference {
  engine: string;
  pages: OcrReferencePage[];
}

export interface InvoiceOutput {
  document_id: string;
  invoice: InvoiceData;
  confidence: Confidence;
  validation: Validation;
  metadata: InvoiceMetadata;
}

export interface ReviewData {
  document_id: string;
  status: string;
  filename?: string | null;
  complexity_score?: number | null;
  complexity_level?: string | null;
  ocr_engine?: string | null;
  processing_mode?: string | null;
  page_count?: number | null;
  page_urls: string[];
  invoice: InvoiceData;
  confidence: Confidence;
  ocr_reference: OcrReference | null;
  validation: Validation;
}

export interface UploadResponse {
  document_id: string;
  filename: string;
  status: string;
  page_count: number;
  complexity_score: number | null;
  complexity_level: string | null;
  message: string;
}

export interface Document {
  id: string;
  filename: string;
  status: string;
  complexity_score: number | null;
  complexity_level: string | null;
  ocr_engine: string | null;
  page_count: number;
  created_at: string;
}
