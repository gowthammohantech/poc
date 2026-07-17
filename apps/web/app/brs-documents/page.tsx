"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getBrsDocuments } from "@/lib/api";
import type { BrsDocument } from "@/types/brs";

export default function BrsDocumentsPage() {
  const [docs, setDocs] = useState<BrsDocument[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getBrsDocuments()
      .then(setDocs)
      .finally(() => setLoading(false));
  }, []);

  const statusColor = (s: string) => {
    if (s === "COMPLETED" || s === "VALID") return "text-green-700 bg-green-50";
    if (s === "INVALID" || s === "FAILED") return "text-red-700 bg-red-50";
    if (s === "NEEDS_REVIEW") return "text-yellow-700 bg-yellow-50";
    return "text-gray-600 bg-gray-50";
  };

  return (
    <main className="min-h-screen bg-gray-50 py-10 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Processed BRS Documents</h1>
          <Link
            href="/agents/brs"
            className="text-sm bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 transition-colors"
          >
            + Upload New BRS
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : docs.length === 0 ? (
          <div className="bg-white rounded-xl border p-12 text-center">
            <p className="text-gray-500">No BRS documents processed yet.</p>
            <Link href="/agents/brs" className="mt-4 inline-block text-emerald-600 hover:underline">
              Upload your first BRS document →
            </Link>
          </div>
        ) : (
          <div className="bg-white rounded-xl border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Filename</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Status</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Processing Mode</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Pages</th>
                  <th className="text-left py-3 px-4 font-medium text-gray-700">Created</th>
                  <th className="py-3 px-4"></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-b last:border-0 hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium text-gray-900 max-w-[200px] truncate">
                      {doc.filename}
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColor(doc.status)}`}>
                        {doc.status}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-600 text-xs font-mono">
                      {doc.processing_mode || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-600">{doc.page_count}</td>
                    <td className="py-3 px-4 text-gray-400 text-xs">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4">
                      <a href={`/brs-review/${doc.id}`} className="text-emerald-600 hover:underline text-xs">
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
