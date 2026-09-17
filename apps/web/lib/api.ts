import axios from "axios";

import type { Country } from "@/lib/country";
import type { UsReviewData } from "@/types/usDocument";

// Keep browser requests on the frontend origin. The Next.js route handler proxies
// them to FastAPI using the server-only FASTAPI_URL environment variable.
const FASTAPI_URL = "/api/backend";

export const api = axios.create({
  baseURL: FASTAPI_URL,
  timeout: 600000,
});

export async function uploadInvoice(
  file: File,
  expectedFields?: string,
  mustUseLlm?: boolean,
  country?: Country
) {
  const form = new FormData();
  form.append("file", file);
  if (expectedFields) form.append("expected_fields", expectedFields);
  if (mustUseLlm) form.append("must_use_llm", "true");
  // Omitted rather than defaulted, so a caller that predates the country
  // dimension still posts exactly the form the backend used to receive.
  if (country) form.append("country", country);
  const { data } = await api.post("/api/documents/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function processDocument(documentId: string) {
  const { data } = await api.post(`/api/documents/${documentId}/process`);
  return data;
}

export async function getReview(documentId: string) {
  const { data } = await api.get(`/api/documents/${documentId}/review`);
  return data;
}

export async function submitReview(documentId: string, correctedInvoice: object) {
  const { data } = await api.post(`/api/documents/${documentId}/review/submit`, {
    corrected_invoice: correctedInvoice,
  });
  return data;
}

export async function getDocuments() {
  const { data } = await api.get("/api/documents");
  return data;
}

export async function getDocument(documentId: string) {
  const { data } = await api.get(`/api/documents/${documentId}`);
  return data;
}

export function getExportUrl(documentId: string, format: "json" | "csv" | "excel") {
  return `${FASTAPI_URL}/api/documents/${documentId}/export/${format}`;
}

export function getPageImageUrl(pageUrl: string) {
  if (pageUrl.startsWith("http")) return pageUrl;
  const normalizedPageUrl = pageUrl.replace(/\\/g, "/");
  const suffix = normalizedPageUrl.startsWith("/") ? normalizedPageUrl : `/${normalizedPageUrl}`;
  return `${FASTAPI_URL}${suffix}`;
}

// ---- USA Document API ----
// A US purchase order, shipping authorization or invoice travels the same endpoints as
// an invoice -- the payload keeps the "invoice" envelope key -- so these are
// typed views of the invoice functions rather than new routes.

export async function getUsReview(documentId: string): Promise<UsReviewData> {
  const { data } = await api.get(`/api/documents/${documentId}/review`);
  return data as UsReviewData;
}

export async function submitUsReview(documentId: string, correctedDocument: unknown) {
  const { data } = await api.post(`/api/documents/${documentId}/review/submit`, {
    corrected_invoice: correctedDocument,
  });
  return data;
}

// ---- BRS Agent API ----

export async function uploadBrs(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/api/brs/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function processBrsDocument(documentId: string) {
  const { data } = await api.post(`/api/brs/${documentId}/process`);
  return data;
}

export async function getBrsReview(documentId: string) {
  const { data } = await api.get(`/api/brs/${documentId}/review`);
  return data;
}

export async function submitBrsReview(documentId: string, correctedBrs: object) {
  const { data } = await api.post(`/api/brs/${documentId}/review/submit`, {
    corrected_brs: correctedBrs,
  });
  return data;
}

export async function getBrsDocuments() {
  const { data } = await api.get("/api/brs");
  return data;
}

export function getBrsExportUrl(documentId: string, format: "json" | "csv" | "excel") {
  return `${FASTAPI_URL}/api/brs/${documentId}/export/${format}`;
}

// ---- BRS Matching (reconciliation) ----

export async function parseCoaExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/api/brs/matching/parse-coa", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function parseLedgerExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post("/api/brs/matching/parse-ledger", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function saveCoaData(documentId: string, rows: unknown[]) {
  const { data } = await api.post(`/api/brs/matching/${documentId}/coa`, { rows });
  return data;
}

export async function saveLedgerData(documentId: string, rows: unknown[]) {
  const { data } = await api.post(`/api/brs/matching/${documentId}/ledger`, { rows });
  return data;
}

// ---- Connectors ----

export async function getConnectorProviders() {
  const { data } = await api.get("/api/connectors/providers");
  return data;
}

export async function getConnectors() {
  const { data } = await api.get("/api/connectors");
  return data;
}

export async function startConnectorOAuth(provider: string, country?: string) {
  const { data } = await api.post(`/api/connectors/${provider}/oauth/start`, { country });
  return data as { connection_id: string; authorization_url: string };
}

export async function getConnectorFolders(connectionId: string) {
  const { data } = await api.get(`/api/connectors/${connectionId}/folders`);
  return data;
}

export async function updateConnectorFilters(
  connectionId: string,
  filters: {
    country?: string | null;
    filter_label?: string | null;
    filter_label_name?: string | null;
    filter_query?: string | null;
    max_messages_per_sync?: number | null;
  }
) {
  const { data } = await api.post(`/api/connectors/${connectionId}/filters`, filters);
  return data;
}

export async function disconnectConnector(connectionId: string) {
  const { data } = await api.post(`/api/connectors/${connectionId}/disconnect`);
  return data;
}

export async function startConnectorSync(connectionId: string) {
  const { data } = await api.post(`/api/connectors/${connectionId}/sync`);
  return data as { run_id: string; status: string };
}

export async function getSyncRun(runId: string) {
  const { data } = await api.get(`/api/connectors/sync-runs/${runId}`);
  return data;
}

export async function getSyncRunItems(runId: string) {
  const { data } = await api.get(`/api/connectors/sync-runs/${runId}/items`);
  return data;
}

export async function getConnectorStats(connectionId: string) {
  const { data } = await api.get(`/api/connectors/${connectionId}/stats`);
  return data;
}

export async function getConnectorSyncRuns(connectionId: string) {
  const { data } = await api.get(`/api/connectors/${connectionId}/sync-runs`);
  return data;
}
