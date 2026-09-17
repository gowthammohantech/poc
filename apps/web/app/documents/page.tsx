"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Trash2 } from "lucide-react";
import { deleteDocument, deleteDocuments, getDocuments } from "@/lib/api";
import Modal from "@/components/Modal";
import { useCountry } from "@/components/useCountry";
import { normalizeCountry } from "@/lib/country";
import SourceBadge from "@/components/SourceBadge";
import { SkeletonTable } from "@/components/Skeleton";
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
  const router = useRouter();
  const { country } = useCountry();
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  // Seeded from the URL so "View N new invoices" from a connector sync lands
  // on the connector rows.
  const [filter, setFilter] = useState<SourceFilter>(
    isSourceFilter(requested) ? requested : "ALL"
  );

  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    getDocuments()
      .then((data) => {
        setDocs(data);
        setLoadError(null);
      })
      // A running connector sync loads the backend enough that a request can
      // drop. Say so rather than sitting on an empty table forever.
      .catch(() => setLoadError("Could not load invoices. Retry in a moment."))
      .finally(() => setLoading(false));
  }, []);

  // Both the table and the chip counts derive from this one list. Counting
  // over `docs` instead would show totals larger than the rows on screen.
  const inCountry = useMemo(
    () => docs.filter((d) => normalizeCountry(d.country) === country),
    [docs, country]
  );

  const visible = useMemo(
    () =>
      filter === "ALL"
        ? inCountry
        : inCountry.filter((d) => (d.source ?? "MANUAL") === filter),
    [inCountry, filter]
  );

  const isUsa = country === "USA";
  const noun = isUsa ? "documents" : "invoices";

  // Selection only ever covers rows on screen: switching the filter or region
  // drops the rest, so a delete can never reach a row the user cannot see.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => {
    setSelected((prev) => {
      const onScreen = new Set(visible.map((d) => d.id));
      const kept = [...prev].filter((id) => onScreen.has(id));
      return kept.length === prev.size ? prev : new Set(kept);
    });
  }, [visible]);

  const allSelected = visible.length > 0 && visible.every((d) => selected.has(d.id));
  const someSelected = selected.size > 0 && !allSelected;
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected;
  }, [someSelected]);

  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(visible.map((d) => d.id)));

  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Ids waiting on the confirmation dialog; null while it is closed.
  const [pendingDelete, setPendingDelete] = useState<string[] | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const askDelete = (ids: string[]) => {
    setDeleteError(null);
    setPendingDelete(ids);
  };

  const closeDelete = () => {
    if (!deleting) setPendingDelete(null);
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      if (pendingDelete.length === 1) await deleteDocument(pendingDelete[0]);
      else await deleteDocuments(pendingDelete);
      const removed = new Set(pendingDelete);
      setDocs((prev) => prev.filter((d) => !removed.has(d.id)));
      setSelected((prev) => new Set([...prev].filter((id) => !removed.has(id))));
      setPendingDelete(null);
    } catch {
      setDeleteError("Could not delete. Nothing was removed from the list; try again.");
    } finally {
      setDeleting(false);
    }
  };

  const pendingLabel =
    pendingDelete?.length === 1
      ? `"${docs.find((d) => d.id === pendingDelete[0])?.filename ?? "this document"}"`
      : `${pendingDelete?.length ?? 0} ${noun}`;

  const statusColor = (s: string) => {
    if (s === "COMPLETED" || s === "VALID") return "text-green-700 bg-green-50";
    if (s === "INVALID" || s === "FAILED") return "text-red-700 bg-red-50";
    if (s === "NEEDS_REVIEW") return "text-yellow-700 bg-yellow-50";
    return "text-gray-600 bg-gray-50";
  };

  // The review screen's prev/next arrows rebuild the list themselves, so the
  // active filter travels with the link to keep them in step with what is shown.
  // The href follows the row's own country, never the selector, so a row can
  // never open on the wrong review screen. Both filters travel with the link
  // because the review screen rebuilds the sibling list from them.
  const reviewHref = (doc: Document) => {
    const base = normalizeCountry(doc.country) === "USA" ? "us-review" : "review";
    const params = new URLSearchParams({ country: normalizeCountry(doc.country) });
    if (filter !== "ALL") params.set("source", filter);
    return `/${base}/${doc.id}?${params.toString()}`;
  };

  // The whole row opens the review screen. Cmd/Ctrl-click keeps the usual
  // "open in new tab" behaviour a plain link would have had.
  const openReview = (doc: Document, e: React.MouseEvent | React.KeyboardEvent) => {
    const href = reviewHref(doc);
    if (e.metaKey || e.ctrlKey) window.open(href, "_blank");
    else router.push(href);
  };

  return (
    <main className="min-h-screen bg-gray-50 py-10 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">
            {isUsa ? "Processed US Documents" : "Processed Invoices"}
          </h1>
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
            const count =
              key === "ALL"
                ? inCountry.length
                : inCountry.filter((d) => (d.source ?? "MANUAL") === key).length;
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
          {selected.size > 0 && (
            <button
              onClick={() => askDelete([...selected])}
              className="ml-auto inline-flex items-center gap-1.5 text-xs font-medium text-white bg-red-600 hover:bg-red-700 px-3 py-1.5 rounded-lg transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Delete selected ({selected.size})
            </button>
          )}
        </div>

        {loading ? (
          <SkeletonTable columns={isUsa ? 11 : 10} rows={6} />
        ) : loadError ? (
          <div className="bg-white rounded-xl border p-12 text-center">
            <p className="text-red-600 text-sm">{loadError}</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-3 text-sm text-blue-600 hover:underline"
            >
              Retry
            </button>
          </div>
        ) : visible.length === 0 ? (
          <div className="bg-white rounded-xl border p-12 text-center">
            {inCountry.length === 0 ? (
              <>
                <p className="text-gray-500">
                  No {isUsa ? "US documents" : "invoices"} processed yet.
                  {docs.length > 0 && " Switch the region at the top right to see the others."}
                </p>
                <Link href="/agents/invoice-ocr" className="mt-4 inline-block text-blue-600 hover:underline">
                  Upload your first {isUsa ? "document" : "invoice"} →
                </Link>
              </>
            ) : (
              <p className="text-gray-500">No {noun} from this source yet.</p>
            )}
          </div>
        ) : (
          <div className="bg-white rounded-xl border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="w-10 py-3 pl-4 pr-0">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      aria-label={`Select all ${noun}`}
                      className="h-4 w-4 rounded border-gray-300 accent-blue-600 cursor-pointer align-middle"
                    />
                  </th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Filename</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">
                    {isUsa ? "Document No" : "Invoice No"}
                  </th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Source</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Status</th>
                  {isUsa && (
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Type</th>
                  )}
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Complexity</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">OCR Engine</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Pages</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Created</th>
                  <th className="w-12 py-3 px-4">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((doc) => (
                  <tr
                    key={doc.id}
                    role="link"
                    tabIndex={0}
                    onClick={(e) => openReview(doc, e)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") openReview(doc, e);
                    }}
                    className={`border-b last:border-0 hover:bg-blue-50/50 cursor-pointer focus:outline-none focus-visible:bg-blue-50 ${
                      selected.has(doc.id) ? "bg-blue-50/40" : ""
                    }`}
                  >
                    {/* The row itself opens the review, so clicks and keys on
                        the controls must not bubble up to it. */}
                    <td
                      className="w-10 py-3 pl-4 pr-0"
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(doc.id)}
                        onChange={() => toggleOne(doc.id)}
                        aria-label={`Select ${doc.filename}`}
                        className="h-4 w-4 rounded border-gray-300 accent-blue-600 cursor-pointer align-middle"
                      />
                    </td>
                    <td className="py-3 px-4 font-medium text-gray-900 max-w-[200px] truncate">
                      {doc.filename}
                    </td>
                    <td className="py-3 px-4 text-gray-900 font-mono text-xs whitespace-nowrap">
                      {doc.document_number || "-"}
                    </td>
                    <td className="py-3 px-4">
                      <SourceBadge doc={doc} />
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColor(doc.status)}`}>
                        {doc.status}
                      </span>
                    </td>
                    {isUsa && (
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${
                            doc.doc_type === "SA"
                              ? "text-violet-700 bg-violet-50"
                              : doc.doc_type === "SO"
                                ? "text-indigo-700 bg-indigo-50"
                                : doc.doc_type === "INV"
                                  ? "text-emerald-700 bg-emerald-50"
                                  : "text-gray-600 bg-gray-50"
                          }`}
                        >
                          {doc.doc_type || "—"}
                        </span>
                      </td>
                    )}
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
                    <td className="py-3 px-4 text-gray-400 text-xs whitespace-nowrap">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td
                      className="py-3 px-4 text-right"
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <button
                        onClick={() => askDelete([doc.id])}
                        aria-label={`Delete ${doc.filename}`}
                        title="Delete"
                        className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={pendingDelete !== null}
        onClose={closeDelete}
        title={pendingDelete?.length === 1 ? "Delete document" : `Delete ${noun}`}
        size="md"
      >
        <p className="text-sm text-gray-700">
          Delete {pendingLabel}? This removes the extracted data and uploaded files and cannot be undone.
        </p>
        {deleteError && <p className="mt-3 text-sm text-red-600">{deleteError}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={closeDelete}
            disabled={deleting}
            className="text-sm border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={confirmDelete}
            disabled={deleting}
            className="text-sm bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 disabled:opacity-50"
          >
            {deleting ? "Deleting…" : "Delete"}
          </button>
        </div>
      </Modal>
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
