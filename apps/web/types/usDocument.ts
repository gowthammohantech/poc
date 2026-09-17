/**
 * The three US document families.
 *
 * None is a GST tax invoice, so these do not extend the India invoice types:
 * an SA is a parts x week demand schedule with no money on it at all, an SO is
 * a purchase order whose totals block is frequently absent, and an INV is a
 * supplier invoice with a single sales tax line, a remit-to and a balance due.
 */

import type { OcrReference, Validation } from "./invoice";

export type UsDocType = "SO" | "SA" | "INV" | "UNKNOWN";

export interface UsParty {
  name: string | null;
  code?: string | null;
  address: string | null;
  phone?: string | null;
  email?: string | null;
  contact: string | null;
  /** INV vendor only: the EIN printed on the invoice. */
  tax_id?: string | null;
}

/**
 * One weekly bucket of a release. The two dates come from stacked header rows
 * a week apart; raw_* hold them exactly as printed, since the source carries
 * no year and the reviewer checks against the page.
 */
export interface UsScheduleColumn {
  week_label: string | null;
  ship_date: string | null;
  delivery_date: string | null;
  raw_ship_date: string | null;
  raw_delivery_date: string | null;
}

/**
 * `quantities` is positional: index i is the quantity for schedule_columns[i].
 * `quantities_repaired` is set by the backend when a ragged row had to be
 * padded or trimmed to fit the header, and the document fails validation when
 * it is present.
 */
export interface UsSaPart {
  po_number: string | null;
  part_number: string | null;
  description: string | null;
  std_pack: number | null;
  quantities: (number | null)[];
  total_quantity: number | null;
  quantities_repaired?: string | null;
}

export interface UsSaData {
  document_type: "SA";
  release_number: string | null;
  release_date: string | null;
  received_by: string | null;
  received_at: string | null;
  issuer: UsParty;
  supplier: UsParty;
  schedule_columns: UsScheduleColumn[];
  parts: UsSaPart[];
  terms_notes: string[];
}

export interface UsSoLineItem {
  line_number: number | null;
  part_number: string | null;
  description: string | null;
  quantity: number | null;
  uom: string | null;
  due_date: string | null;
  unit_cost: number | null;
  extended_cost: number | null;
}

export interface UsSoTotals {
  subtotal: number | null;
  sales_tax: number | null;
  freight: number | null;
  discount: number | null;
  grand_total: number | null;
}

export interface UsSoData {
  document_type: "SO";
  order_number: string | null;
  order_date: string | null;
  order_datetime_raw: string | null;
  received_by: string | null;
  received_at: string | null;
  buyer: UsParty;
  vendor: UsParty;
  bill_to: UsParty;
  ship_to: UsParty;
  currency: string | null;
  payment_terms: string | null;
  freight_terms: string | null;
  ship_via: string | null;
  line_items: UsSoLineItem[];
  totals: UsSoTotals;
  notes: string[];
}

export interface UsInvLineItem {
  line_number: number | null;
  part_number: string | null;
  description: string | null;
  /** Printed only when the invoice shows ordered and shipped separately. */
  quantity_ordered: number | null;
  /** The quantity billed. */
  quantity: number | null;
  uom: string | null;
  unit_price: number | null;
  amount: number | null;
}

export interface UsInvTotals {
  subtotal: number | null;
  discount: number | null;
  freight: number | null;
  /** A percentage as printed: 7.25 means 7.25%. */
  tax_rate: number | null;
  sales_tax: number | null;
  total: number | null;
  amount_paid: number | null;
  balance_due: number | null;
}

export interface UsInvData {
  document_type: "INV";
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  /** The customer's purchase order this invoice bills against. */
  po_number: string | null;
  /** The vendor's own sales order or job number. */
  order_number: string | null;
  customer_number: string | null;
  bol_number: string | null;
  ship_date: string | null;
  ship_via: string | null;
  freight_terms: string | null;
  payment_terms: string | null;
  currency: string | null;
  received_by: string | null;
  received_at: string | null;
  vendor: UsParty;
  remit_to: Pick<UsParty, "name" | "address">;
  bill_to: UsParty;
  ship_to: UsParty;
  line_items: UsInvLineItem[];
  totals: UsInvTotals;
  notes: string[];
}

export type UsDocumentData = UsSaData | UsSoData | UsInvData;

export function isSaData(doc: UsDocumentData | null | undefined): doc is UsSaData {
  return doc?.document_type === "SA";
}

export interface UsReviewData {
  document_id: string;
  status: string;
  filename?: string;
  country: string;
  doc_type: UsDocType | null;
  complexity_score?: number | null;
  complexity_level?: string | null;
  ocr_engine?: string | null;
  processing_mode?: string | null;
  page_count?: number;
  page_urls: string[];
  invoice: UsDocumentData;
  confidence: Record<string, number>;
  ocr_reference: OcrReference | null;
  validation: Validation;
}
