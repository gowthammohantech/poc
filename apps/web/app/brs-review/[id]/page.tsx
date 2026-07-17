"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useForm, useFieldArray } from "react-hook-form";
import { ImageIcon } from "lucide-react";
import { getBrsReview, submitBrsReview, getBrsExportUrl } from "@/lib/api";
import PagePreview from "@/components/PagePreview";
import Modal from "@/components/Modal";
import CollapsibleSection from "@/components/CollapsibleSection";
import type {
  BrsReviewData,
  BrsData,
  BrsItemType,
  BrsEffect,
  BrsReconciliationItem,
  BrsTransaction,
} from "@/types/brs";

const BRS_ITEM_TYPES: BrsItemType[] = [
  "DEPOSIT_IN_TRANSIT",
  "OUTSTANDING_CHECK",
  "BANK_CHARGE",
  "BANK_INTEREST",
  "BOOK_ERROR",
  "BANK_ERROR",
  "NSF_CHECK",
  "DIRECT_DEPOSIT",
  "OTHER_ADDITION",
  "OTHER_DEDUCTION",
];

export default function BrsReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [review, setReview] = useState<BrsReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitMsg, setSubmitMsg] = useState("");
  const [previewOpen, setPreviewOpen] = useState(false);

  const { register, control, handleSubmit, reset } = useForm<BrsData>();
  const { fields: bankFields, append: appendBank, remove: removeBank } = useFieldArray({
    control,
    name: "bank_side_items",
  });
  const { fields: bookFields, append: appendBook, remove: removeBook } = useFieldArray({
    control,
    name: "book_side_items",
  });

  useEffect(() => {
    if (!id) return;
    getBrsReview(id as string)
      .then((data: BrsReviewData) => {
        setReview(data);
        reset(data.brs);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id, reset]);

  const onSubmit = async (formData: BrsData) => {
    setSubmitting(true);
    setSubmitMsg("");
    try {
      await submitBrsReview(id as string, formData);
      setSubmitMsg("BRS review submitted successfully!");
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
          <svg className="animate-spin h-8 w-8 mx-auto text-emerald-600" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="mt-3 text-gray-600">Loading BRS review data...</p>
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-600">Failed to load BRS review data.</p>
      </div>
    );
  }

  const val = review.validation;
  const conf = review.confidence;
  const overallConfidence = Math.round((conf?.overall ?? 0) * 100);
  const bankStatement = review.bank_statement;

  const statusColor =
    val.status === "VALID" ? "bg-green-100 text-green-800 border-green-200" :
    val.status === "INVALID" ? "bg-red-100 text-red-800 border-red-200" :
    "bg-yellow-100 text-yellow-800 border-yellow-200";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">BRS Review</h1>
          <p className="text-sm text-gray-500 font-mono">{id}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded-full border text-sm font-medium ${statusColor}`}>
            {val.status}
          </span>
          <span className="px-3 py-1 rounded-full border border-emerald-200 bg-emerald-50 text-sm font-medium text-emerald-800">
            Overall confidence: {overallConfidence}%
          </span>
          <a
            href={`/brs-matching?documentId=${id}`}
            className="text-sm bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1.5 rounded-lg transition-colors"
          >
            Reconcile with Accounts
          </a>
          <button
            type="button"
            onClick={() => setPreviewOpen(true)}
            title="View document pages"
            className="p-2 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
          >
            <ImageIcon className="w-4 h-4" />
          </button>
          <details className="relative">
            <summary className="list-none cursor-pointer text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors">
              Export
            </summary>
            <div className="absolute right-0 top-full z-10 mt-1 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
              <a href={getBrsExportUrl(id as string, "json")} target="_blank" className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100">JSON</a>
              <a href={getBrsExportUrl(id as string, "csv")} className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100">CSV</a>
              <a href={getBrsExportUrl(id as string, "excel")} className="block px-3 py-2 text-sm text-gray-700 hover:bg-gray-100">Excel</a>
            </div>
          </details>
        </div>
      </div>

      <Modal open={previewOpen} onClose={() => setPreviewOpen(false)} title="Document Pages">
        <PagePreview pageUrls={review.page_urls} ocrReference={null} />
      </Modal>

      {/* Validation alerts */}
      {(val.errors.length > 0 || val.warnings.length > 0) && (
        <div className="px-6 py-3 space-y-2">
          {val.errors.map((e, i) => (
            <div key={i} className="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-700">
              {e}
            </div>
          ))}
          {val.warnings.map((w, i) => (
            <div key={i} className="bg-yellow-50 border border-yellow-200 rounded-lg px-4 py-2 text-sm text-yellow-700">
              {w}
            </div>
          ))}
        </div>
      )}

      <div className="max-w-6xl mx-auto p-6">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">

          {/* Document header info */}
          <section className="bg-white rounded-lg border p-4 space-y-3">
            <h2 className={sectionTitle}>Document Info</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field label="Company Name">
                <input {...register("document_info.company_name")} className={inputCls} />
              </Field>
              <Field label="Bank Name">
                <input {...register("document_info.bank_name")} className={inputCls} />
              </Field>
              <Field label="Account Number">
                <input {...register("document_info.account_number")} className={inputCls} />
              </Field>
              <Field label="Currency">
                <input {...register("document_info.currency")} className={inputCls} placeholder="INR" />
              </Field>
              <Field label="Period Start">
                <input {...register("document_info.statement_period_start")} className={inputCls} placeholder="YYYY-MM-DD" />
              </Field>
              <Field label="Period End">
                <input {...register("document_info.statement_period_end")} className={inputCls} placeholder="YYYY-MM-DD" />
              </Field>
              <Field label="Prepared By">
                <input {...register("document_info.prepared_by")} className={inputCls} />
              </Field>
              <Field label="Prepared Date">
                <input {...register("document_info.prepared_date")} className={inputCls} placeholder="YYYY-MM-DD" />
              </Field>
            </div>

            {bankStatement && (
              <div className="flex flex-wrap gap-2 pt-2 border-t">
                <StatChip label="Opening Balance" value={fmtAmount(bankStatement.opening_balance)} />
                <StatChip label="Closing Balance" value={fmtAmount(bankStatement.closing_balance)} />
                <StatChip label="Debit Count" value={bankStatement.statement_totals?.total_debit_count ?? "—"} />
                <StatChip label="Credit Count" value={bankStatement.statement_totals?.total_credit_count ?? "—"} />
                <StatChip label="Total Debits" value={fmtAmount(bankStatement.statement_totals?.total_debit_amount)} />
                <StatChip label="Total Credits" value={fmtAmount(bankStatement.statement_totals?.total_credit_amount)} />
              </div>
            )}
          </section>

          {/* Transactions (from bank statement extraction) — expanded by default */}
          <CollapsibleSection title="Transactions" defaultOpen>
            <TransactionsTable transactions={bankStatement?.transactions ?? []} />
          </CollapsibleSection>

          {/* Balances */}
          <CollapsibleSection title="Balances">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Opening Balance (Bank)">
                <input {...register("balances.opening_balance_bank", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
              <Field label="Opening Balance (Book)">
                <input {...register("balances.opening_balance_book", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
              <Field label="Closing Balance (Bank)">
                <input {...register("balances.closing_balance_bank", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
              <Field label="Closing Balance (Book)">
                <input {...register("balances.closing_balance_book", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
              <Field label="Reconciled Balance">
                <input {...register("balances.reconciled_balance", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
            </div>
          </CollapsibleSection>

          {/* Reconciling Items (bank vs book) */}
          {review.brs && (
            <CollapsibleSection title="Reconciling Items">
              <ReconcilingItemsView
                bankItems={review.brs.bank_side_items ?? []}
                bookItems={review.brs.book_side_items ?? []}
                adjustedBank={review.brs.adjusted_bank_balance}
                adjustedBook={review.brs.adjusted_book_balance}
              />
            </CollapsibleSection>
          )}

          {/* Bank Side Items */}
          <CollapsibleSection
            title="Bank Side Items"
            action={
              <button
                type="button"
                onClick={() => appendBank({ item_type: null, description: null, reference_number: null, date: null, amount: 0, effect: "ADD_TO_BANK", affects_side: "BANK" })}
                className="text-xs bg-emerald-50 text-emerald-700 hover:bg-emerald-100 px-2 py-1 rounded"
              >
                + Add Row
              </button>
            }
          >
            <ItemTable
              fields={bankFields}
              register={register}
              remove={removeBank}
              prefix="bank_side_items"
              effectOptions={["ADD_TO_BANK", "DEDUCT_FROM_BANK"]}
            />
          </CollapsibleSection>

          {/* Book Side Items */}
          <CollapsibleSection
            title="Book Side Items"
            action={
              <button
                type="button"
                onClick={() => appendBook({ item_type: null, description: null, reference_number: null, date: null, amount: 0, effect: "ADD_TO_BOOK", affects_side: "BOOK" })}
                className="text-xs bg-emerald-50 text-emerald-700 hover:bg-emerald-100 px-2 py-1 rounded"
              >
                + Add Row
              </button>
            }
          >
            <ItemTable
              fields={bookFields}
              register={register}
              remove={removeBook}
              prefix="book_side_items"
              effectOptions={["ADD_TO_BOOK", "DEDUCT_FROM_BOOK"]}
            />
          </CollapsibleSection>

          {/* Adjusted Balances */}
          <CollapsibleSection title="Adjusted Balances">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Adjusted Bank Balance">
                <input {...register("adjusted_bank_balance", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
              <Field label="Adjusted Book Balance">
                <input {...register("adjusted_book_balance", { valueAsNumber: true })} className={inputCls} type="number" step="any" />
              </Field>
            </div>
          </CollapsibleSection>

          {/* Validation Checks */}
          {val.rule_checks.length > 0 && (
            <CollapsibleSection title="Validation Checks">
              <div className="space-y-1">
                {val.rule_checks.map((rc, i) => (
                  <div key={i} className={`flex items-start gap-2 text-xs ${rc.passed ? "text-green-700" : "text-red-700"}`}>
                    <span className="mt-0.5">{rc.passed ? "✓" : "✗"}</span>
                    <span>{rc.message}</span>
                  </div>
                ))}
              </div>
            </CollapsibleSection>
          )}

          {submitMsg && (
            <div className={`rounded-lg p-3 text-sm border ${
              submitMsg.includes("Failed") ? "bg-red-50 text-red-700 border-red-200" : "bg-green-50 text-green-700 border-green-200"
            }`}>
              {submitMsg}
            </div>
          )}

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-300 text-white font-medium py-2.5 px-4 rounded-lg transition-colors"
            >
              {submitting ? "Saving..." : "Submit Corrected BRS"}
            </button>
            <a
              href="/agents/brs"
              className="px-4 py-2.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors text-sm font-medium"
            >
              Process Another
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}

const inputCls = "w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500";
const tdInputCls = "w-full border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-400 min-w-[60px]";
const sectionTitle = "font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2";

function fmtAmount(n: number | null | undefined) {
  return n == null ? "—" : n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded px-2.5 py-1 text-xs">
      <span className="text-gray-500">{label}:</span>
      <span className="font-semibold text-gray-900">{value}</span>
    </div>
  );
}

function Field({
  label,
  children,
  isError,
  colSpan,
}: {
  label: string;
  children: React.ReactNode;
  isError?: boolean;
  colSpan?: boolean;
}) {
  return (
    <div className={colSpan ? "col-span-2" : ""}>
      <label className={`block text-xs font-medium mb-1 ${isError ? "text-red-600" : "text-gray-600"}`}>
        {label}
      </label>
      {children}
      {isError && <p className="text-xs text-red-500 mt-0.5">Validation error</p>}
    </div>
  );
}

const TXN_PAGE_SIZE_OPTIONS = [25, 50, 100];

function TransactionsTable({ transactions }: { transactions: BrsTransaction[] }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const totalPages = Math.max(1, Math.ceil(transactions.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);

  const pageRows = useMemo(() => {
    const start = currentPage * pageSize;
    return transactions.slice(start, start + pageSize);
  }, [transactions, currentPage, pageSize]);

  const fmt = (n: number | null | undefined) =>
    n == null ? "—" : n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  if (transactions.length === 0) {
    return <p className="text-xs text-gray-400 py-2">No transactions extracted.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b">
              <th className="text-left py-1.5 pr-3">Date</th>
              <th className="text-left py-1.5 pr-3">Narration</th>
              <th className="text-left py-1.5 pr-3">Reference No</th>
              <th className="text-right py-1.5 pr-3">Debit</th>
              <th className="text-right py-1.5 pr-3">Credit</th>
              <th className="text-right py-1.5">Balance</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((txn, i) => (
              <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                <td className="py-1.5 pr-3 whitespace-nowrap text-gray-600">{txn.transaction_date ?? "—"}</td>
                <td className="py-1.5 pr-3 text-gray-800 max-w-[320px] truncate" title={txn.narration ?? ""}>
                  {txn.narration ?? "—"}
                </td>
                <td className="py-1.5 pr-3 font-mono text-gray-500 whitespace-nowrap">{txn.reference_number ?? "—"}</td>
                <td className="py-1.5 pr-3 text-right text-red-700">{txn.debit != null ? fmt(txn.debit) : "—"}</td>
                <td className="py-1.5 pr-3 text-right text-green-700">{txn.credit != null ? fmt(txn.credit) : "—"}</td>
                <td className="py-1.5 text-right font-medium text-gray-900">{fmt(txn.balance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-gray-600 pt-2">
        <div className="flex items-center gap-2">
          <span>
            Showing {currentPage * pageSize + 1}-{Math.min((currentPage + 1) * pageSize, transactions.length)} of {transactions.length}
          </span>
          <select
            value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(0); }}
            className="border border-gray-300 rounded px-1.5 py-1 text-xs"
          >
            {TXN_PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>{size} / page</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
            className="px-2.5 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
          >
            Prev
          </button>
          <span>Page {currentPage + 1} of {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={currentPage >= totalPages - 1}
            className="px-2.5 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function ReconcilingItemsView({
  bankItems,
  bookItems,
  adjustedBank,
  adjustedBook,
}: {
  bankItems: BrsReconciliationItem[];
  bookItems: BrsReconciliationItem[];
  adjustedBank: number | null;
  adjustedBook: number | null;
}) {
  const allItems = [
    ...bankItems.map((it) => ({ ...it, side: "BANK" as const })),
    ...bookItems.map((it) => ({ ...it, side: "BOOK" as const })),
  ];

  if (allItems.length === 0) {
    return <p className="text-xs text-gray-400 py-2">No reconciling items extracted.</p>;
  }

  const effectLabel = (effect: string) => {
    if (effect === "ADD_TO_BANK" || effect === "ADD_TO_BOOK") return { label: "+", cls: "text-green-700 font-semibold" };
    return { label: "−", cls: "text-red-600 font-semibold" };
  };

  const sideChip = (side: "BANK" | "BOOK") =>
    side === "BANK"
      ? "bg-blue-50 text-blue-700 border border-blue-200"
      : "bg-violet-50 text-violet-700 border border-violet-200";

  const fmt = (n: number | null | undefined) =>
    n == null ? "—" : n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1.5 pr-3">Side</th>
            <th className="text-left py-1.5 pr-3">Type</th>
            <th className="text-left py-1.5 pr-3">Description</th>
            <th className="text-left py-1.5 pr-3">Ref #</th>
            <th className="text-left py-1.5 pr-3">Date</th>
            <th className="text-right py-1.5 pr-2">Effect</th>
            <th className="text-right py-1.5">Amount</th>
          </tr>
        </thead>
        <tbody>
          {allItems.map((item, i) => {
            const { label, cls } = effectLabel(item.effect);
            return (
              <tr key={i} className="border-b last:border-0 hover:bg-gray-50">
                <td className="py-1.5 pr-3">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${sideChip(item.side)}`}>
                    {item.side}
                  </span>
                </td>
                <td className="py-1.5 pr-3 text-gray-600 whitespace-nowrap">
                  {item.item_type?.replace(/_/g, " ") ?? "—"}
                </td>
                <td className="py-1.5 pr-3 text-gray-800 max-w-[160px] truncate" title={item.description ?? ""}>
                  {item.description ?? "—"}
                </td>
                <td className="py-1.5 pr-3 font-mono text-gray-500">{item.reference_number ?? "—"}</td>
                <td className="py-1.5 pr-3 text-gray-500">{item.date ?? "—"}</td>
                <td className={`py-1.5 pr-2 text-right ${cls}`}>{label}</td>
                <td className="py-1.5 text-right font-medium text-gray-900">
                  {fmt(item.amount)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Adjusted balance summary strip */}
      <div className="mt-3 pt-3 border-t grid grid-cols-2 gap-3 text-xs">
        <div className="flex items-center justify-between bg-blue-50 rounded px-3 py-2">
          <span className="text-blue-700 font-medium">Adjusted Bank Balance</span>
          <span className="font-semibold text-blue-900">{fmt(adjustedBank)}</span>
        </div>
        <div className="flex items-center justify-between bg-violet-50 rounded px-3 py-2">
          <span className="text-violet-700 font-medium">Adjusted Book Balance</span>
          <span className="font-semibold text-violet-900">{fmt(adjustedBook)}</span>
        </div>
      </div>
    </div>
  );
}

function ItemTable({
  fields,
  register,
  remove,
  prefix,
  effectOptions,
}: {
  fields: { id: string }[];
  register: ReturnType<typeof useForm<BrsData>>["register"];
  remove: (index: number) => void;
  prefix: "bank_side_items" | "book_side_items";
  effectOptions: BrsEffect[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 border-b">
            <th className="text-left py-1 pr-2">Type</th>
            <th className="text-left py-1 pr-2">Description</th>
            <th className="text-left py-1 pr-2">Ref #</th>
            <th className="text-left py-1 pr-2">Date</th>
            <th className="text-right py-1 pr-2">Amount</th>
            <th className="text-left py-1 pr-2">Effect</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field, i) => (
            <tr key={field.id} className="border-b last:border-0">
              <td className="py-1 pr-2">
                <select {...register(`${prefix}.${i}.item_type`)} className={tdInputCls}>
                  <option value="">—</option>
                  {BRS_ITEM_TYPES.map((t) => (
                    <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </td>
              <td className="py-1 pr-2">
                <input {...register(`${prefix}.${i}.description`)} className={tdInputCls} />
              </td>
              <td className="py-1 pr-2">
                <input {...register(`${prefix}.${i}.reference_number`)} className={tdInputCls} />
              </td>
              <td className="py-1 pr-2">
                <input {...register(`${prefix}.${i}.date`)} className={tdInputCls} placeholder="YYYY-MM-DD" />
              </td>
              <td className="py-1 pr-2">
                <input {...register(`${prefix}.${i}.amount`, { valueAsNumber: true })} className={`${tdInputCls} text-right`} type="number" step="any" />
              </td>
              <td className="py-1 pr-2">
                <select {...register(`${prefix}.${i}.effect`)} className={tdInputCls}>
                  {effectOptions.map((e) => (
                    <option key={e} value={e}>{e.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </td>
              <td className="py-1">
                <button type="button" onClick={() => remove(i)} className="text-red-400 hover:text-red-600 text-xs px-1">✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {fields.length === 0 && (
        <p className="text-center text-gray-400 text-xs py-4">No items extracted.</p>
      )}
    </div>
  );
}
