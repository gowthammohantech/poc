"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useForm, useFieldArray } from "react-hook-form";
import { getReview, submitReview, getExportUrl } from "@/lib/api";
import PagePreview from "@/components/PagePreview";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import type { ReviewData, InvoiceData } from "@/types/invoice";

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [review, setReview] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitMsg, setSubmitMsg] = useState("");

  const { register, control, handleSubmit, reset } = useForm<InvoiceData>();
  const { fields: lineItemFields, append, remove } = useFieldArray({
    control,
    name: "line_items",
  });

  useEffect(() => {
    if (!id) return;
    getReview(id as string)
      .then((data) => {
        setReview(data);
        reset(data.invoice);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id, reset]);

  const onSubmit = async (formData: InvoiceData) => {
    setSubmitting(true);
    setSubmitMsg("");
    try {
      await submitReview(id as string, formData);
      setSubmitMsg("Review submitted successfully! Invoice is now locked.");
    } catch {
      setSubmitMsg("Failed to submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <svg className="animate-spin h-8 w-8 mx-auto text-blue-600" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="mt-3 text-gray-600">Loading review data...</p>
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-600">Failed to load review data.</p>
      </div>
    );
  }

  const val = review.validation;
  const conf = review.confidence;
  const overallConfidence = Math.min(99, Math.max(95, Math.round((conf.overall ?? 0) * 100)));

  const statusColor =
    val.status === "VALID" ? "bg-green-100 text-green-800 border-green-200" :
    val.status === "INVALID" ? "bg-red-100 text-red-800 border-red-200" :
    "bg-yellow-100 text-yellow-800 border-yellow-200";

  const complexityLevel = review.complexity_level || null;
  const complexityColor =
    complexityLevel === "LOW" ? "bg-emerald-50 text-emerald-800 border-emerald-200" :
    complexityLevel === "HIGH" ? "bg-orange-50 text-orange-800 border-orange-200" :
    "bg-amber-50 text-amber-800 border-amber-200";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Invoice Review</h1>
          <p className="text-sm text-gray-500 font-mono">{id}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded-full border text-sm font-medium ${statusColor}`}>
            {val.status}
          </span>
          {complexityLevel && (
            <span
              className={`px-3 py-1 rounded-full border text-sm font-medium ${complexityColor}`}
              title="Document complexity used to route the OCR engine"
            >
              {complexityLevel}
              {review.complexity_score !== null && review.complexity_score !== undefined && (
                <span className="opacity-60 ml-1">({review.complexity_score})</span>
              )}
            </span>
          )}
          {review.ocr_engine && (
            <span
              className="px-3 py-1 rounded-full border border-gray-200 bg-gray-50 text-xs font-mono text-gray-700"
              title="OCR engine used for this document"
            >
              {review.ocr_engine}
            </span>
          )}
          {/* <span className="px-3 py-1 rounded-full border border-blue-200 bg-blue-50 text-sm font-medium text-blue-800">
            Overall confidence: {overallConfidence}%
          </span> */}
          <details className="relative">
            <summary className="list-none cursor-pointer text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors">
              Export 
            </summary>
            <div className="absolute right-0 top-full z-10 mt-1 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
              <a
                href={getExportUrl(id as string, "json")}
                target="_blank"
                className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                JSON
              </a>
              <a
                href={getExportUrl(id as string, "csv")}
                className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                CSV
              </a>
              <a
                href={getExportUrl(id as string, "excel")}
                className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
              >
                Excel
              </a>
            </div>
          </details>
          <button
            type="button"
            disabled
            title="Connect an Elixir Books account to enable publishing."
            className="text-sm bg-purple-600 text-white px-3 py-1.5 rounded-lg opacity-60 cursor-not-allowed"
          >
            Publish to Elixir Books
          </button>
        </div>
      </div>

      {/* Validation alerts */}
      {(val.errors.length > 0 || val.warnings.length > 0) && (
        <div className="px-6 py-3 space-y-2">
          {val.errors.map((e, i) => (
            <div key={i} className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-700">
              ✗ {e}
            </div>
          ))}
          {val.warnings.map((w, i) => (
            <div key={i} className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2 text-sm text-yellow-700">
              ⚠ {w}
            </div>
          ))}
        </div>
      )}

      {/* Two-panel layout */}
      <div className="grid grid-cols-2 gap-0 h-[calc(100vh-120px)]">
        {/* Left: Page Preview */}
        <div className="overflow-y-auto border-r bg-gray-100 p-4">
          <PagePreview pageUrls={review.page_urls} ocrReference={review.ocr_reference} />
        </div>

        {/* Right: Editable Form */}
        <div className="overflow-y-auto p-6">
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">

            {/* Invoice Header */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
                Invoice Header
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Invoice Number"
                  badge={<ConfidenceBadge value={conf.invoice_number} />}
                  isError={val.rule_checks.some(c => c.field === "invoice_number" && !c.passed)}
                >
                  <input {...register("invoice_number")} className={inputCls} placeholder="INV-001" />
                </Field>
                <Field
                  label="Invoice Date"
                  badge={<ConfidenceBadge value={conf.invoice_date} />}
                  isError={val.rule_checks.some(c => c.field === "invoice_date" && !c.passed)}
                >
                  <input {...register("invoice_date")} className={inputCls} placeholder="YYYY-MM-DD" />
                </Field>
                <Field label="Due Date">
                  <input {...register("due_date")} className={inputCls} placeholder="YYYY-MM-DD" />
                </Field>
                <Field label="Currency">
                  <input {...register("currency")} className={inputCls} placeholder="INR" />
                </Field>
                <Field label="PO Number">
                  <input {...register("purchase_order_number")} className={inputCls} />
                </Field>
              </div>
            </section>

            {/* Vendor */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
                Vendor
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Name">
                  <input {...register("vendor.name")} className={inputCls} />
                </Field>
                <Field
                  label="GSTIN"
                  badge={<ConfidenceBadge value={conf.gstin} />}
                  isError={val.rule_checks.some(c => c.field === "vendor.gstin" && !c.passed)}
                >
                  <input {...register("vendor.gstin")} className={inputCls} />
                </Field>
                <Field label="PAN">
                  <input {...register("vendor.pan")} className={inputCls} />
                </Field>
                <Field label="Phone">
                  <input {...register("vendor.phone")} className={inputCls} />
                </Field>
                <Field label="Email">
                  <input {...register("vendor.email")} className={inputCls} />
                </Field>
                <Field label="Address" colSpan>
                  <input {...register("vendor.address")} className={inputCls} />
                </Field>
              </div>
            </section>

            {/* Customer */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
                Customer
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Name">
                  <input {...register("customer.name")} className={inputCls} />
                </Field>
                <Field
                  label="GSTIN"
                  isError={val.rule_checks.some(c => c.field === "customer.gstin" && !c.passed)}
                >
                  <input {...register("customer.gstin")} className={inputCls} />
                </Field>
                <Field label="Address" colSpan>
                  <input {...register("customer.address")} className={inputCls} />
                </Field>
              </div>
            </section>

            {/* Line Items */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <div className="flex items-center justify-between border-b pb-2">
                <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide">
                  Line Items <ConfidenceBadge value={conf.line_items} />
                </h2>
                <button
                  type="button"
                  onClick={() => append({
                    description: null, hsn_sac: null, quantity: null, unit: null,
                    unit_price: null, taxable_value: null, cgst_rate: null,
                    cgst_amount: null, sgst_rate: null, sgst_amount: null,
                    igst_rate: null, igst_amount: null, total: null,
                  })}
                  className="text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 px-2 py-1 rounded"
                >
                  + Add Row
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b">
                      <th className="text-left py-1 pr-2">Description</th>
                      <th className="text-left py-1 pr-2">HSN</th>
                      <th className="text-right py-1 pr-2">Qty</th>
                      <th className="text-right py-1 pr-2">Unit Price</th>
                      <th className="text-right py-1 pr-2">Taxable</th>
                      <th className="text-right py-1 pr-2">CGST%</th>
                      <th className="text-right py-1 pr-2">CGST₹</th>
                      <th className="text-right py-1 pr-2">SGST%</th>
                      <th className="text-right py-1 pr-2">SGST₹</th>
                      <th className="text-right py-1 pr-2">IGST%</th>
                      <th className="text-right py-1 pr-2">IGST₹</th>
                      <th className="text-right py-1 pr-2">Total</th>
                      <th className="py-1"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {lineItemFields.map((field: { id: string }, i: number) => (
                      <tr key={field.id} className="border-b last:border-0">
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.description`)} className={tdInputCls} />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.hsn_sac`)} className={tdInputCls} />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.quantity`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.unit_price`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.taxable_value`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.cgst_rate`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.cgst_amount`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.sgst_rate`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.sgst_amount`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.igst_rate`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.igst_amount`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1 pr-2">
                          <input {...register(`line_items.${i}.total`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
                        </td>
                        <td className="py-1">
                          <button type="button" onClick={() => remove(i)} className="text-red-400 hover:text-red-600 text-xs px-1">✕</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {lineItemFields.length === 0 && (
                  <p className="text-center text-gray-400 text-xs py-4">No line items extracted.</p>
                )}
              </div>
            </section>

            {/* Tax Summary */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
                Tax Summary <ConfidenceBadge value={conf.totals} />
              </h2>
              <div className="grid grid-cols-2 gap-3">
                {(["subtotal", "cgst_total", "sgst_total", "igst_total", "total_tax", "round_off", "grand_total"] as const).map((f) => (
                  <Field
                    key={f}
                    label={f.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                    isError={f === "grand_total" && val.rule_checks.some(c => c.field === "tax_summary" && !c.passed)}
                  >
                    <input
                      {...register(`tax_summary.${f}`, { valueAsNumber: true })}
                      className={inputCls}
                      type="number"
                      step="any"
                    />
                  </Field>
                ))}
              </div>
            </section>

            {/* Bank Details */}
            <section className="bg-white rounded-lg border p-4 space-y-3">
              <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
                Bank Details
              </h2>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Account Name">
                  <input {...register("bank_details.account_name")} className={inputCls} />
                </Field>
                <Field label="Account Number">
                  <input {...register("bank_details.account_number")} className={inputCls} />
                </Field>
                <Field label="Bank Name">
                  <input {...register("bank_details.bank_name")} className={inputCls} />
                </Field>
                <Field
                  label="IFSC"
                  isError={val.rule_checks.some(c => c.field === "bank_details.ifsc" && !c.passed)}
                >
                  <input {...register("bank_details.ifsc")} className={inputCls} />
                </Field>
                <Field label="Branch">
                  <input {...register("bank_details.branch")} className={inputCls} />
                </Field>
              </div>
            </section>

            {/* Rule checks summary */}
            {val.rule_checks.length > 0 && (
              <section className="bg-white rounded-lg border p-4">
                <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2 mb-3">
                  Validation Checks
                </h2>
                <div className="space-y-1">
                  {val.rule_checks.map((rc, i) => (
                    <div key={i} className={`flex items-start gap-2 text-xs ${rc.passed ? "text-green-700" : "text-red-700"}`}>
                      <span className="mt-0.5">{rc.passed ? "✓" : "✗"}</span>
                      <span>{rc.message}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Submit */}
            {submitMsg && (
              <div className="rounded-lg p-3 text-sm bg-green-50 text-green-700 border border-green-200">
                {submitMsg}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="submit"
                disabled={submitting}
                className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
              >
                {submitting ? "Saving..." : "Submit Corrected Invoice"}
              </button>
              <a
                href="/agents/invoice-ocr"
                className="px-4 py-2.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors text-sm font-medium"
              >
                Process Another
              </a>
            </div>

          </form>
        </div>
      </div>
    </div>
  );
}

const inputCls = "w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500";
const tdInputCls = "w-full border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 min-w-[60px]";

function Field({
  label,
  children,
  badge,
  isError,
  colSpan,
}: {
  label: string;
  children: React.ReactNode;
  badge?: React.ReactNode;
  isError?: boolean;
  colSpan?: boolean;
}) {
  return (
    <div className={colSpan ? "col-span-2" : ""}>
      <label className={`block text-xs font-medium mb-1 flex items-center gap-1 ${isError ? "text-red-600" : "text-gray-600"}`}>
        {label} {badge}
      </label>
      {children}
      {isError && <p className="text-xs text-red-500 mt-0.5">Validation error</p>}
    </div>
  );
}
