"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { uploadBrs, processBrsDocument } from "@/lib/api";
import FileDropzone from "@/components/FileDropzone";

export default function BrsPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    try {
      setStatus("uploading");
      setMessage("Uploading and converting BRS document...");
      const uploadResult = await uploadBrs(file);
      const id = uploadResult.document_id;
      setStatus("processing");
      setMessage(`Converted (${uploadResult.page_count} page(s)). Running vision extraction...`);
      await processBrsDocument(id);
      setMessage("Extraction complete! Redirecting to review...");
      router.push(`/brs-review/${id}`);
    } catch (err: unknown) {
      setStatus("error");
      const msg = err instanceof Error ? err.message : "An error occurred";
      setMessage(`Error: ${msg}`);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-gray-900">Bank Reconciliation Statement Agent</h1>
          <p className="mt-2 text-gray-600">
            Upload a BRS document (PDF or image). The agent will extract all balances and
            reconciling items and validate the math automatically.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
          <FileDropzone
            accept=".pdf,.jpg,.jpeg,.png,.webp,.tiff,.tif,.bmp,.heic,.heif"
            file={file}
            onFileSelected={setFile}
            label="Drag & drop your BRS document here, or click to browse"
            hint="PDF, JPG, PNG, WEBP, TIFF, BMP, HEIC, HEIF"
          />

          {message && (
            <div
              className={`rounded-lg p-3 text-sm ${
                status === "error"
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : "bg-emerald-50 text-emerald-700 border border-emerald-200"
              }`}
            >
              {(status === "processing" || status === "uploading") ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  {message}
                </span>
              ) : message}
            </div>
          )}

          <button
            type="submit"
            disabled={!file || status === "uploading" || status === "processing"}
            className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-300 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
          >
            {status === "uploading" || status === "processing" ? "Processing..." : "Upload & Extract BRS"}
          </button>
        </form>

        {/* How It Works */}
        <div className="mt-10">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">How It Works</h2>
          <div className="relative">
            <div className="flex flex-col sm:flex-row gap-0 sm:gap-0">
              {[
                { step: 1, title: "Upload & Convert", desc: "Document converted to page images" },
                { step: 2, title: "Vision Extraction", desc: "Vision LLM reads the full document" },
                { step: 3, title: "Balance Extraction", desc: "Book balance, bank balance & reconciling items identified" },
                { step: 4, title: "Math Validation", desc: "Adjusted balances verified to reconcile" },
                { step: 5, title: "Review & Export", desc: "Reviewer inspects and exports results" },
              ].map((item, idx, arr) => (
                <div key={item.step} className="flex sm:flex-col items-start sm:items-center sm:flex-1 relative">
                  <div className="flex sm:flex-col items-center sm:w-full">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-emerald-600 text-white text-sm font-bold flex items-center justify-center z-10">
                      {item.step}
                    </div>
                    {idx < arr.length - 1 && (
                      <>
                        <div className="sm:hidden w-px h-4 bg-emerald-200 ml-3.5 my-0.5" />
                        <div className="hidden sm:block h-px flex-1 bg-emerald-200 mt-[-16px] mx-1 w-full" />
                      </>
                    )}
                  </div>
                  <div className="ml-3 sm:ml-0 sm:mt-8 sm:text-center pb-4 sm:pb-0">
                    <p className="text-sm font-medium text-gray-800">{item.title}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Agents Involved */}
        <div className="mt-8">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Agents Involved</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              {
                icon: "👁️",
                name: "BRS Vision Agent",
                desc: "Uses direct vision LLM to read the full document without OCR preprocessing",
              },
              {
                icon: "🤖",
                name: "Extraction Agent",
                desc: "Pulls out all balance figures and reconciling line items with amounts",
              },
              {
                icon: "🔢",
                name: "Validation Agent",
                desc: "Runs arithmetic checks and flags any reconciliation discrepancies",
              },
            ].map((agent) => (
              <div key={agent.name} className="bg-white border border-gray-200 rounded-xl p-4 flex gap-3 shadow-sm">
                <span className="text-xl">{agent.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-800">{agent.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{agent.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 text-center">
          <Link href="/brs-documents" className="text-sm text-emerald-600 hover:underline">
            View all processed BRS documents →
          </Link>
        </div>
      </div>
    </main>
  );
}
