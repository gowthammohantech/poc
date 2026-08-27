"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getDocuments } from "@/lib/api";
import SourceBadge from "@/components/SourceBadge";
import type { Document, IngestionSource } from "@/types/invoice";

type SourceFilter = "ALL" | IngestionSource;

const FILTERS: { key: SourceFilter; label: string }[] = [
  { key: "ALL", label: "All" },
  { key: "MANUAL", label: "Manual" },
  { key: "API", label: "API" },
  { key: "CONNECTOR", label: "Connector" },
];

function isSourceFilter(value: string | null): value is SourceFilter {
  return FILTERS.some((f) => f.key === value);
}

function DocumentsPage() {
  const requested = useSearchParams().get("source");
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  // Seeded from the URL so "View N new invoices" from a connector sync lands
  // on the connector rows.
  const [filter, setFilter] = useState<SourceFilter>(
    isSourceFilter(requested) ? requested : "ALL"
  );

  useEffect(() => {
    getDocuments()
      .then(setDocs)
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(
    () => (filter === "ALL" ? docs : docs.filter((d) => (d.source ?? "MANUAL") === filter)),
    [docs, filter]
  );

  const statusColor = (s: string) => {
    if (s === "COMPLETED" || s === "VALID") return "text-green-700 bg-green-50";
    if (s === "INVALID" || s === "FAILED") return "text-red-700 bg-red-50";
    if (s === "NEEDS_REVIEW") return "text-yellow-700 bg-yellow-50";
    return "text-gray-600 bg-gray-50";
  };

  // The review screen's prev/next arrows rebuild the list themselves, so the
  // active filter travels with the link to keep them in step with what is shown.
  const reviewHref = (id: string) =>
    filter === "ALL" ? `/review/${id}` : `/review/${id}?source=${filter}`;

  return (
    <main className="min-h-screen bg-gray-50 py-10 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Processed Invoices</h1>
          <div className="flex items-center gap-2">
            <Link href="/connectors" className="text-sm border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-100 transition-colors">
              Connectors
            </Link>
            <Link href="/agents/invoice-ocr" className="text-sm bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors">
              + Upload New
            </Link>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-4">
          {FILTERS.map(({ key, label }) => {
            const count = key === "ALL" ? docs.length : docs.filter((d) => (d.source ?? "MANUAL") === key).length;
            return (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  filter === key
                    ? "bg-blue-600 text-white"
                    : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-100"
                }`}
              >
                {label} <span className="opacity-60">{count}</span>
              </button>
            );
          })}
        </div>

        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : visible.length === 0 ? (
          <div className="bg-white rounded-xl border p-12 text-center">
            {docs.length === 0 ? (
              <>
                <p className="text-gray-500">No invoices processed yet.</p>
                <Link href="/agents/invoice-ocr" className="mt-4 inline-block text-blue-600 hover:underline">Upload your first invoice →</Link>
              </>
            ) : (
              <p className="text-gray-500">No invoices from this source yet.</p>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Filename</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Source</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Status</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Complexity</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">OCR Engine</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Pages</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Created</th>
                  <th className="py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((doc) => (
                  <tr key={doc.id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium text-gray-900 max-w-[200px] truncate">
                      {doc.filename}
                    </td>
                    <td className="py-3 px-4">
                      <SourceBadge doc={doc} />
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColor(doc.status)}`}>
                        {doc.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-600">
                      {doc.complexity_level || "-"}
                      {doc.complexity_score !== null && (
                        <span className="text-gray-400 ml-1">({doc.complexity_score})</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-600 text-xs font-mono">
                      {doc.ocr_engine || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-600">{doc.page_count}</td>
                    <td className="py-3 px-4 text-gray-400 text-xs">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4">
                      <a
                        href={reviewHref(doc.id)}
                        className="text-blue-600 hover:underline text-xs"
                      >
                        Review →
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}

export default function DocumentsPageWrapper() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-gray-50 py-10 px-6" />}>
      <DocumentsPage />
    </Suspense>
  );
}
