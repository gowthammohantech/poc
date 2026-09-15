/**
 * The two US document families.
 *
 * Neither is a tax invoice, so these do not extend the India invoice types:
 * an SA is a parts x week demand schedule with no money on it at all, and an
 * SO is a purchase order whose totals block is frequently absent.
 */

import type { OcrReference, Validation } from "./invoice";

export type UsDocType = "SO" | "SA" | "UNKNOWN";

export interface UsParty {
  name: string | null;
  code?: string | null;
  address: string | null;
  phone?: string | null;
  email?: string | null;
  contact: string | null;
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

export type UsDocumentData = UsSaData | UsSoData;

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
