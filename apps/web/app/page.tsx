"use client";

import { useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { uploadInvoice, processDocument } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [expectedFields, setExpectedFields] = useState("");
  const [mustUseLlm, setMustUseLlm] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "processing" | "error">("idle");
  const [message, setMessage] = useState("");

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    try {
      setStatus("uploading");
      setMessage("Uploading and converting document...");
      const uploadResult = await uploadInvoice(file, expectedFields || undefined, mustUseLlm);
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
          <h1 className="text-3xl font-bold text-gray-900">Invoice OCR Platform</h1>
          <p className="mt-2 text-gray-600">
            Upload an invoice PDF or image to extract structured data automatically.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
              dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-blue-400"
            }`}
          >
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.tiff,.tif,.bmp,.heic,.heif"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            {file ? (
              <div>
                <p className="font-medium text-gray-800">{file.name}</p>
                <p className="text-sm text-gray-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            ) : (
              <div>
                <p className="text-gray-500">Drag & drop your invoice here, or click to browse</p>
                <p className="text-sm text-gray-400 mt-2">PDF, JPG, PNG, WEBP, TIFF, BMP, HEIC, HEIF</p>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Expected Fields (optional)
            </label>
            <textarea
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g., vendor name: Acme Corp, invoice number: INV-2024-001"
              value={expectedFields}
              onChange={(e) => setExpectedFields(e.target.value)}
            />
            <p className="text-xs text-gray-400 mt-1">
              Provide known field values to improve accuracy validation.
            </p>
          </div>

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
            {status === "uploading" || status === "processing" ? "Processing..." : "Upload & Process Invoice"}
          </button>
        </form>

        <div className="mt-6 text-center">
          <a href="/documents" className="text-sm text-blue-600 hover:underline">
            View all processed invoices →
          </a>
        </div>
      </div>
    </main>
  );
}
