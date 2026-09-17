"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { uploadInvoice, processDocument } from "@/lib/api";
import FileDropzone from "@/components/FileDropzone";
import { useCountry } from "@/components/useCountry";
import type { Country } from "@/lib/country";

interface RegimeCopy {
  heading: string;
  blurb: string;
  dropLabel: string;
  expectedFieldsPlaceholder: string;
  submitLabel: string;
  footerLink: string;
  steps: { step: number; title: string; desc: string }[];
  agents: { icon: string; name: string; desc: string }[];
}

const COPY: Record<Country, RegimeCopy> = {
  INDIA: {
    heading: "Invoice OCR Agent",
    blurb: "Upload an invoice PDF or image to extract structured data automatically.",
    dropLabel: "Drag & drop your invoice here, or click to browse",
    expectedFieldsPlaceholder: "e.g., vendor name: Acme Corp, invoice number: INV-2024-001",
    submitLabel: "Upload & Process Invoice",
    footerLink: "View all processed invoices →",
    steps: [
      { step: 1, title: "Upload & Convert", desc: "PDF or image converted to page images" },
      { step: 2, title: "Complexity Analysis", desc: "Document scored to select OCR engine" },
      { step: 3, title: "OCR Extraction", desc: "Tesseract (simple) or Vision LLM (complex)" },
      { step: 4, title: "Field Extraction", desc: "Agent parses vendor, dates, line items, totals" },
      { step: 5, title: "Validation", desc: "Fields cross-checked against expected values" },
      { step: 6, title: "Human Review", desc: "Reviewer confirms and exports results | publish to elixir books" },
    ],
    agents: [
      { icon: "🔀", name: "OCR Engine Selector",
        desc: "Routes documents to Tesseract or Vision LLM based on complexity score" },
      { icon: "🤖", name: "Extraction Agent",
        desc: "LLM-powered agent that structures raw OCR text into typed invoice fields" },
      { icon: "✅", name: "Validation Agent",
        desc: "Compares extracted data against expected fields and computes confidence scores" },
    ],
  },
  USA: {
    heading: "US Order, Release & Invoice Agent",
    blurb:
      "Upload a US purchase order, shipping authorization or invoice. The agent works out which it is and extracts it accordingly.",
    dropLabel: "Drag & drop your purchase order, release or invoice here, or click to browse",
    expectedFieldsPlaceholder: "e.g., PO number: 33336, vendor: PIOLAX, supplier code: 4283",
    submitLabel: "Upload & Process Document",
    footerLink: "View all processed documents →",
    steps: [
      { step: 1, title: "Upload & Convert", desc: "PDF or image converted to page images" },
      { step: 2, title: "Reference OCR", desc: "Tesseract text kept as a second opinion on digits" },
      { step: 3, title: "Type Detection", desc: "Classified as a purchase order (SO), a release (SA) or an invoice (INV)" },
      { step: 4, title: "Extraction", desc: "Order or invoice lines, or the parts × week delivery schedule" },
      { step: 5, title: "Validation", desc: "Line and invoice-total arithmetic, and schedule alignment, checked in code" },
      { step: 6, title: "Human Review", desc: "Reviewer confirms and exports results" },
    ],
    agents: [
      { icon: "🧭", name: "Document Classifier",
        desc: "Tells a purchase order, a weekly delivery release and an invoice apart by their layout" },
      { icon: "🤖", name: "Extraction Agent",
        desc: "Reads order or invoice lines, or the parts × week quantity grid, straight from the page images" },
      { icon: "✅", name: "Validation Agent",
        desc: "Checks quantity × price, that an invoice's totals reconcile, and that every quantity row lines up with the schedule" },
    ],
  },
};

export default function InvoiceOcrPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [expectedFields, setExpectedFields] = useState("");
  const [mustUseLlm, setMustUseLlm] = useState(false);
  const { country } = useCountry();
  const copy = COPY[country];
  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    try {
      setStatus("uploading");
      setMessage("Uploading and converting document...");
      const uploadResult = await uploadInvoice(file, expectedFields || undefined, mustUseLlm, country);
      const id = uploadResult.document_id;
      setStatus("processing");
      setMessage(
        `Converted (${uploadResult.page_count} page(s), complexity: ${uploadResult.complexity_level}). Running OCR and extraction...`
      );
      await processDocument(id);
      setMessage("Processing complete! Redirecting to review...");
      router.push(`/review/${id}`);
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
          <h1 className="text-3xl font-bold text-gray-900">{copy.heading}</h1>
          <p className="mt-2 text-gray-600">{copy.blurb}</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
          <FileDropzone
            accept=".pdf,.jpg,.jpeg,.png,.webp,.tiff,.tif,.bmp,.heic,.heif"
            file={file}
            onFileSelected={setFile}
            label={copy.dropLabel}
            hint="PDF, JPG, PNG, WEBP, TIFF, BMP, HEIC, HEIF"
            activeColor="blue"
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Expected Fields (optional)
            </label>
            <textarea
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder={copy.expectedFieldsPlaceholder}
              value={expectedFields}
              onChange={(e) => setExpectedFields(e.target.value)}
            />
            <p className="text-xs text-gray-400 mt-1">
              Provide known field values to improve accuracy validation.
            </p>
          </div>

          {country === "USA" ? (
            // The US path always reads the page images directly, so there is no
            // engine choice to force. Say what it does instead of offering a
            // toggle that would do nothing.
            <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg p-3">
              US documents are read directly from the page images, and whether this is a
              purchase order, a shipping authorization or an invoice is detected automatically.
            </p>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="mustUseLlm"
                checked={mustUseLlm}
                onChange={(e) => setMustUseLlm(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600"
              />
              <label htmlFor="mustUseLlm" className="text-sm text-gray-700">
                Force Advance OCR Engine (for handwritten or complex invoices)
              </label>
            </div>
          )}

          {message && (
            <div
              className={`rounded-lg p-3 text-sm ${
                status === "error"
                  ? "bg-red-50 text-red-700 border border-red-200"
                  : "bg-blue-50 text-blue-700 border border-blue-200"
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
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
          >
            {status === "uploading" || status === "processing" ? "Processing..." : copy.submitLabel}
          </button>
        </form>

        {/* How It Works */}
        <div className="mt-10">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">How It Works</h2>
          <div className="relative">
            <div className="flex flex-col sm:flex-row gap-0 sm:gap-0">
              {copy.steps.map((item, idx, arr) => (
                <div key={item.step} className="flex sm:flex-col items-start sm:items-center sm:flex-1 relative">
                  <div className="flex sm:flex-col items-center sm:w-full">
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center z-10">
                      {item.step}
                    </div>
                    {idx < arr.length - 1 && (
                      <>
                        <div className="sm:hidden w-px h-4 bg-blue-200 ml-3.5 my-0.5" />
                        <div className="hidden sm:block h-px flex-1 bg-blue-200 mt-[-16px] mx-1 w-full" />
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
            {copy.agents.map((agent) => (
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
          <Link href="/documents" className="text-sm text-blue-600 hover:underline">
            {copy.footerLink}
          </Link>
        </div>
      </div>
    </main>
  );
}
