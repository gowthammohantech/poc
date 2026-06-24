import axios from "axios";

// Keep browser requests on the frontend origin. The Next.js route handler proxies
// them to FastAPI using the server-only FASTAPI_URL environment variable.
const FASTAPI_URL = "/api/backend";

export const api = axios.create({
  baseURL: FASTAPI_URL,
  timeout: 300000,
});

export async function uploadInvoice(
  file: File,
  expectedFields?: string,
  mustUseLlm?: boolean
) {
  const form = new FormData();
  form.append("file", file);
  if (expectedFields) form.append("expected_fields", expectedFields);
  if (mustUseLlm) form.append("must_use_llm", "true");
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
  return `${FASTAPI_URL}${pageUrl}`;
}
