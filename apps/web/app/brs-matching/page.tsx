"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  getBrsReview,
  getBrsDocuments,
  parseCoaExcel,
  parseLedgerExcel,
  saveCoaData,
  saveLedgerData,
} from "@/lib/api";
import FileDropzone from "@/components/FileDropzone";
import CollapsibleSection from "@/components/CollapsibleSection";
import {
  runMatching,
  validateCoaRow,
  validateLedgerRow,
} from "@/lib/matchingEngine";
import type { BrsTransaction } from "@/types/brs";
import type { BrsDocument, BrsReviewData } from "@/types/brs";
import type {
  CoaRow,
  InvoiceStatus,
  LedgerRow,
  LedgerTransactionType,
  MatchingResult,
  ReconciliationMode,
  VoucherMatch,
  VoucherStatus,
} from "@/types/matching";

let rowIdCounter = 0;
function nextRowId() {
  rowIdCounter += 1;
  return `row-${Date.now()}-${rowIdCounter}`;
}

const PAGE_SIZE_OPTIONS = [10, 25, 50];

// "Matched By" reasons that flag a gap in the data rather than confirming a clean match — call
// these out visually so a reviewer's eye goes straight to them instead of the routine reasons.
const HIGHLIGHTED_MATCH_REASONS = new Set([
  "Invoice details missing",
  "Receipt / Payment Ledger is missing",
  "Account Matched, Missing Invoice & Ledger",
]);

function usePagination<T>(rows: T[], initialPageSize = 10) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(initialPageSize);

  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, totalPages - 1);

  const pageRows = useMemo(
    () => rows.slice(currentPage * pageSize, currentPage * pageSize + pageSize),
    [rows, currentPage, pageSize],
  );

  return {
    pageRows,
    currentPage,
    totalPages,
    pageSize,
    setPage,
    setPageSize: (size: number) => {
      setPageSize(size);
      setPage(0);
    },
  };
}

function PaginationBar({
  currentPage,
  totalPages,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  currentPage: number;
  totalPages: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  if (total === 0) return null;
  return (
    <div className="flex items-center justify-between text-xs text-gray-600 pt-2 border-t">
      <div className="flex items-center gap-2">
        <span>
          Showing {currentPage * pageSize + 1}-
          {Math.min((currentPage + 1) * pageSize, total)} of {total}
        </span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="border border-gray-300 rounded px-1.5 py-1 text-xs"
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size} / page
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(0, currentPage - 1))}
          disabled={currentPage === 0}
          className="px-2.5 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
        >
          Prev
        </button>
        <span>
          Page {currentPage + 1} of {totalPages}
        </span>
        <button
          type="button"
          onClick={() =>
            onPageChange(Math.min(totalPages - 1, currentPage + 1))
          }
          disabled={currentPage >= totalPages - 1}
          className="px-2.5 py-1 rounded border border-gray-300 disabled:opacity-40 hover:bg-gray-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}

function blankLedgerRow(): LedgerRow {
  return {
    id: nextRowId(),
    transaction_type: "Sales Receipt",
    invoice_no: "",
    invoice_date: null,
    invoice_amount: null,
    ledger_date: null,
    ledger_voucher: null,
    ledger_amount: null,
    account_name: null,
    bank_cash_account: null,
  };
}

export default function BrsMatchingPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center text-gray-500">
          Loading...
        </div>
      }
    >
      <BrsMatchingContent />
    </Suspense>
  );
}

function BrsMatchingContent() {
  const searchParams = useSearchParams();
  const documentId = searchParams.get("documentId");

  const [bankReview, setBankReview] = useState<BrsReviewData | null>(null);
  const [bankLoading, setBankLoading] = useState(Boolean(documentId));
  const [allDocuments, setAllDocuments] = useState<BrsDocument[]>([]);
  const [pickerLoading, setPickerLoading] = useState(false);

  const [mode, setMode] = useState<ReconciliationMode>("3-way");

  const [coaRows, setCoaRows] = useState<CoaRow[]>([]);
  const [coaErrors, setCoaErrors] = useState<string[]>([]);
  const [coaFile, setCoaFile] = useState<File | null>(null);
  const [coaUploading, setCoaUploading] = useState(false);

  const [ledgerRows, setLedgerRows] = useState<LedgerRow[]>([]);
  const [ledgerErrors, setLedgerErrors] = useState<string[]>([]);
  const [ledgerFile, setLedgerFile] = useState<File | null>(null);
  const [ledgerUploading, setLedgerUploading] = useState(false);

  const [matchOutput, setMatchOutput] = useState<MatchingResult | null>(null);

  const hydratedRef = useRef(false);

  useEffect(() => {
    if (!documentId) return;
    setBankLoading(true);
    getBrsReview(documentId)
      .then((data: BrsReviewData) => {
        setBankReview(data);
        if (Array.isArray(data.coa) && data.coa.length > 0) setCoaRows(data.coa as CoaRow[]);
        if (Array.isArray(data.ledger) && data.ledger.length > 0) setLedgerRows(data.ledger as LedgerRow[]);
      })
      .catch(() => setBankReview(null))
      .finally(() => {
        setBankLoading(false);
        hydratedRef.current = true;
      });
  }, [documentId]);

  // Persist COA/Ledger to the backend (same store as the bank statement) whenever they change,
  // so a previously-uploaded/edited set redisplays automatically next time this document is opened.
  useEffect(() => {
    if (!documentId || !hydratedRef.current) return;
    const timeout = setTimeout(() => {
      saveCoaData(documentId, coaRows).catch(() => {});
    }, 800);
    return () => clearTimeout(timeout);
  }, [documentId, coaRows]);

  useEffect(() => {
    if (!documentId || !hydratedRef.current) return;
    const timeout = setTimeout(() => {
      saveLedgerData(documentId, ledgerRows).catch(() => {});
    }, 800);
    return () => clearTimeout(timeout);
  }, [documentId, ledgerRows]);

  useEffect(() => {
    if (documentId) return;
    setPickerLoading(true);
    getBrsDocuments()
      .then(setAllDocuments)
      .finally(() => setPickerLoading(false));
  }, [documentId]);

  const bankTransactions = bankReview?.bank_statement?.transactions ?? [];

  const dateRange = useMemo(() => {
    const dates = bankTransactions
      .map((t) => t.transaction_date)
      .filter(Boolean) as string[];
    if (dates.length === 0) return null;
    const sorted = [...dates].sort();
    return { start: sorted[0], end: sorted[sorted.length - 1] };
  }, [bankTransactions]);

  const ledgerRowErrors = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const row of ledgerRows) map.set(row.id, validateLedgerRow(row));
    return map;
  }, [ledgerRows]);

  const hasLedgerErrors = useMemo(
    () => Array.from(ledgerRowErrors.values()).some((errs) => errs.length > 0),
    [ledgerRowErrors],
  );

  const coaValidationErrors = useMemo(
    () => coaRows.flatMap((row) => validateCoaRow(row)),
    [coaRows],
  );

  const coaPagination = usePagination(coaRows);
  const ledgerPagination = usePagination(ledgerRows);

  const STATUS_ORDER: Record<VoucherStatus, number> = {
    Matched: 0,
    "Matched (combined)": 0,
    "Partially Matched": 1,
    Unmatched: 2,
  };

  // Bank Statement is the primary axis for the Results view: each bank transaction reconciled
  // against whichever Invoice/Ledger voucher(s) and COA account matched it. Derived from the
  // same voucherMatches the engine produces — a bank txn can be matched to 0 (unmatched), 1
  // (normal), or several vouchers at once (a "Matched (combined)" group sharing one deposit).
  // Sorted Matched -> Partially Matched -> Unmatched (stable within each group).
  const bankResults = useMemo(() => {
    if (!matchOutput) return [];
    const rows = bankTransactions.map((txn, i) => {
      const vouchers = matchOutput.voucherMatches.filter((v) => v.matchedBankTxnIndexes.includes(i));
      const status: VoucherStatus = vouchers[0]?.status ?? "Unmatched";
      return { index: i, txn, vouchers, status };
    });
    return rows.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
  }, [matchOutput, bankTransactions]);

  const bankStats = useMemo(() => {
    const total = bankResults.length;
    const matched = bankResults.filter((r) => r.status === "Matched" || r.status === "Matched (combined)").length;
    const partiallyMatched = bankResults.filter((r) => r.status === "Partially Matched").length;
    const unmatched = bankResults.filter((r) => r.status === "Unmatched").length;
    return {
      total,
      matched,
      partiallyMatched,
      unmatched,
      matchPercent: total > 0 ? Math.round((matched / total) * 1000) / 10 : 0,
    };
  }, [bankResults]);

  const [resultsFilter, setResultsFilter] = useState<"all" | "matched" | "partial" | "unmatched">("all");
  const filteredBankResults = useMemo(() => {
    if (resultsFilter === "all") return bankResults;
    if (resultsFilter === "matched") return bankResults.filter((r) => r.status === "Matched" || r.status === "Matched (combined)");
    if (resultsFilter === "partial") return bankResults.filter((r) => r.status === "Partially Matched");
    return bankResults.filter((r) => r.status === "Unmatched");
  }, [bankResults, resultsFilter]);

  const bankResultsPagination = usePagination(filteredBankResults, 25);
  const invoicePagination = usePagination(matchOutput?.invoiceSummary ?? [], 25);

  const canRunMatching =
    bankTransactions.length > 0 &&
    ledgerRows.length > 0 &&
    !hasLedgerErrors &&
    (mode === "2-way" ||
      (coaRows.length > 0 && coaValidationErrors.length === 0));

  async function handleCoaFile(file: File | null) {
    setCoaFile(file);
    if (!file) return;
    setCoaUploading(true);
    try {
      const result = await parseCoaExcel(file);
      setCoaRows((prev) => [...prev, ...(result.rows as CoaRow[])]);
      setCoaErrors(result.errors ?? []);
    } catch (err) {
      setCoaErrors([
        err instanceof Error ? err.message : "Failed to parse file",
      ]);
    } finally {
      setCoaUploading(false);
    }
  }

  async function handleLedgerFile(file: File | null) {
    setLedgerFile(file);
    if (!file) return;
    setLedgerUploading(true);
    try {
      const result = await parseLedgerExcel(file);
      const parsed = (result.rows as Omit<LedgerRow, "id">[]).map((r) => ({
        ...r,
        id: nextRowId(),
      }));
      setLedgerRows((prev) => [...prev, ...parsed]);
      setLedgerErrors(result.errors ?? []);
    } catch (err) {
      setLedgerErrors([
        err instanceof Error ? err.message : "Failed to parse file",
      ]);
    } finally {
      setLedgerUploading(false);
    }
  }

  function onConnectDatabase() {
    // Stubbed extension point — real DB connectivity is out of scope for this pass.
    // Intentionally a no-op so no fake success state is shown.
  }

  function updateLedgerRow(id: string, patch: Partial<LedgerRow>) {
    setLedgerRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    );
  }

  function removeLedgerRow(id: string) {
    setLedgerRows((prev) => prev.filter((r) => r.id !== id));
  }

  function handleRunMatching() {
    const statementBankName = bankReview?.bank_statement?.document_info?.bank_name ?? null;
    setMatchOutput(runMatching(bankTransactions, ledgerRows, coaRows, mode, statementBankName));
  }

  function handleExportCsv() {
    if (!matchOutput) return;
    const header = [
      "Date",
      "Narration",
      "Reference",
      "Amount",
      "Direction",
      "Matched Invoice(s)",
      "Status",
      "Score",
      "COA Validated",
      "Reasons",
    ];
    const rows = bankResults.map((r) => {
      const isCredit = r.txn.credit != null && r.txn.credit > 0;
      const amount = isCredit ? r.txn.credit : r.txn.debit;
      const matchedInvoices = r.vouchers
        .map((v) => `${v.invoiceNo}${v.ledgerVoucher ? ` (${v.ledgerVoucher})` : ""}`)
        .join(" + ");
      const primary = r.vouchers[0];
      return [
        r.txn.transaction_date ?? "",
        r.txn.narration ?? "",
        r.txn.reference_number ?? "",
        amount ?? "",
        isCredit ? "Credit" : "Debit",
        matchedInvoices,
        r.status,
        primary?.score ?? 0,
        mode === "3-way" ? (primary?.coaValidated == null ? "" : primary.coaValidated ? "Yes" : "No") : "",
        primary?.reasons.join(" | ") ?? "No settlement found for this bank transaction",
      ];
    });
    const csv = [header, ...rows]
      .map((row) =>
        row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(","),
      )
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `reconciliation-${documentId ?? "results"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!documentId) {
    return (
      <main className="min-h-screen bg-gray-50 py-10 px-6">
        <div className="max-w-3xl mx-auto">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">
            Bank Reconciliation — Matching
          </h1>
          <p className="text-gray-600 mb-6">
            Select a processed BRS document to reconcile against your accounts.
          </p>
          {pickerLoading ? (
            <p className="text-gray-500">Loading documents...</p>
          ) : allDocuments.length === 0 ? (
            <div className="bg-white rounded-xl border p-12 text-center">
              <p className="text-gray-500">No processed BRS documents yet.</p>
              <Link
                href="/agents/brs"
                className="mt-4 inline-block text-emerald-600 hover:underline"
              >
                Upload a BRS document →
              </Link>
            </div>
          ) : (
            <div className="bg-white rounded-xl border divide-y">
              {allDocuments.map((doc) => (
                <a
                  key={doc.id}
                  href={`/brs-matching?documentId=${doc.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-gray-50"
                >
                  <div>
                    <p className="font-medium text-gray-900">{doc.filename}</p>
                    <p className="text-xs text-gray-500">
                      {doc.status} · {doc.page_count} page(s)
                    </p>
                  </div>
                  <span className="text-emerald-600 text-sm">Select →</span>
                </a>
              ))}
            </div>
          )}
        </div>
      </main>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-6 py-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            Bank Reconciliation — Matching
          </h1>
          {/* <p className="text-sm text-gray-500 font-mono">{documentId}</p> */}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center rounded-lg border border-gray-300 overflow-hidden text-sm">
            <button
              type="button"
              onClick={() => setMode("3-way")}
              className={`px-4 py-1.5 ${mode === "3-way" ? "bg-[#2d3588] text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
            >
              3-Way Matching
            </button>
            <button
              type="button"
              onClick={() => setMode("2-way")}
              className={`px-4 py-1.5 ${mode === "2-way" ? "bg-[#2d3588] text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
            >
              2-Way Matching
            </button>
          </div>
          <button
            type="button"
            disabled={!canRunMatching}
            onClick={handleRunMatching}
            className="bg-[#2d3588] hover:bg-[#1a245a] disabled:bg-gray-300 text-white text-sm font-medium py-2 px-5 rounded-lg transition-colors whitespace-nowrap"
          >
            Run Matching
          </button>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6 space-y-6">
        {/* Results Dashboard — shown first, at the top */}
        {matchOutput && (
          <section className="bg-white rounded-lg border p-4 space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <h2 className={sectionTitle}>Results</h2>
              <div className="flex items-center gap-2">
                <div className="flex items-center rounded-lg border border-gray-300 overflow-hidden text-xs">
                  {(
                    [
                      ["all", "All"],
                      ["matched", "Matched"],
                      ["partial", "Partial"],
                      ["unmatched", "Unmatched"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setResultsFilter(value)}
                      className={`px-3 py-1.5 ${resultsFilter === value ? "bg-[#2d3588] text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={handleExportCsv}
                  className="text-xs bg-gray-100 text-gray-700 hover:bg-gray-200 px-3 py-1.5 rounded-lg"
                >
                  Export CSV
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <SummaryCard label="Total Bank Transactions" value={bankStats.total} />
              <SummaryCard label="Matched" value={bankStats.matched} color="text-green-700" />
              <SummaryCard label="Partially Matched" value={bankStats.partiallyMatched} color="text-yellow-700" />
              <SummaryCard label="Unmatched" value={bankStats.unmatched} color="text-red-700" />
              <SummaryCard label="Match %" value={`${bankStats.matchPercent}%`} />
            </div>

            <div className="overflow-x-auto overflow-y-auto max-h-[60vh] border rounded-lg">
              <table className="w-full text-xs">
                <thead className="sticky top-0 z-10 bg-white">
                  <tr className="text-gray-500 border-b">
                    <th className="text-left py-1.5 pr-3">Date</th>
                    <th className="text-left py-1.5 pr-3">Narration</th>
                    <th className="text-left py-1.5 pr-3">Reference</th>
                    <th className="text-right py-1.5 pr-3">Amount</th>
                    <th className="text-center py-1.5 pr-3">Direction</th>
                    <th className="text-left py-1.5 pr-3">Matched Invoice(s)</th>
                    {mode === "3-way" && <th className="text-left py-1.5 pr-3">COA Account</th>}
                    {mode === "3-way" && <th className="text-left py-1.5 pr-3">Bank/Cash Account</th>}
                    <th className="text-center py-1.5 pr-3">Status</th>
                    <th className="text-right py-1.5 pr-3">Score</th>
                    <th className="text-left py-1.5">Matched By</th>
                  </tr>
                </thead>
                <tbody>
                  {bankResultsPagination.pageRows.map((r) => {
                    const isCredit = r.txn.credit != null && r.txn.credit > 0;
                    const amount = isCredit ? r.txn.credit : r.txn.debit;
                    const primary: VoucherMatch | undefined = r.vouchers[0];
                    const reasons = primary?.reasons ?? ["No settlement found for this bank transaction"];
                    return (
                      <tr key={r.index} className="border-b last:border-0 hover:bg-gray-50" title={reasons.join("; ")}>
                        <td className="py-1.5 pr-3 whitespace-nowrap text-gray-600">{r.txn.transaction_date ?? "—"}</td>
                        <td className="py-1.5 pr-3 max-w-60 truncate text-gray-800" title={r.txn.narration ?? ""}>
                          {r.txn.narration ?? "—"}
                        </td>
                        <td className="py-1.5 pr-3 font-mono text-gray-500">{r.txn.reference_number ?? "—"}</td>
                        <td className={`py-1.5 pr-3 text-right font-medium ${isCredit ? "text-green-700" : "text-red-700"}`}>
                          {amount != null ? amount.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-center">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${isCredit ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                            {isCredit ? "Credit" : "Debit"}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3 text-gray-600">
                          {r.vouchers.length === 0 ? (
                            "—"
                          ) : (
                            <>
                              {r.vouchers[0].invoiceNo}
                              {r.vouchers[0].ledgerVoucher ? ` (${r.vouchers[0].ledgerVoucher})` : ""}
                              {r.vouchers.length > 1 && (
                                <span className="block text-[10px] text-amber-600">
                                  +{r.vouchers.length - 1} more invoice(s)
                                </span>
                              )}
                            </>
                          )}
                        </td>
                        {mode === "3-way" && (
                          <td className="py-1.5 pr-3 text-gray-600">
                            {primary?.resolvedLedgerAccount ? (
                              <>
                                {primary.resolvedLedgerAccount.account_name}
                                {primary.ledgerAccountMatchType === "fuzzy" && (
                                  <span className="ml-1 text-[10px] text-amber-600">(fuzzy)</span>
                                )}
                                {primary.ledgerAccountMatchType === "narration" && (
                                  <span className="ml-1 text-[10px] text-blue-600">(from narration)</span>
                                )}
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                        )}
                        {mode === "3-way" && (
                          <td className="py-1.5 pr-3 text-gray-600">
                            {primary?.resolvedBankCashAccount ? (
                              <>
                                {primary.resolvedBankCashAccount.account_name}
                                {primary.bankCashMatchType === "fuzzy" && (
                                  <span className="ml-1 text-[10px] text-amber-600">(fuzzy)</span>
                                )}
                                {primary.bankCashMatchType === "statement" && (
                                  <span className="ml-1 text-[10px] text-blue-600">(from statement)</span>
                                )}
                              </>
                            ) : (
                              "—"
                            )}
                          </td>
                        )}
                        <td className="py-1.5 pr-3 text-center">
                          <VoucherStatusBadge status={r.status} />
                        </td>
                        <td className="py-1.5 pr-3 text-right text-gray-700">{primary?.score ?? 0}%</td>
                        <td className="py-1.5 text-gray-500 max-w-60">
                          <ul className="space-y-0.5">
                            {reasons.map((reason, i) => (
                              <li
                                key={i}
                                className={`text-[10px] leading-tight ${
                                  HIGHLIGHTED_MATCH_REASONS.has(reason) ? "font-semibold text-red-600" : ""
                                }`}
                              >
                                {reason}
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <PaginationBar
              currentPage={bankResultsPagination.currentPage}
              totalPages={bankResultsPagination.totalPages}
              pageSize={bankResultsPagination.pageSize}
              total={filteredBankResults.length}
              onPageChange={bankResultsPagination.setPage}
              onPageSizeChange={bankResultsPagination.setPageSize}
            />
          </section>
        )}

        {/* Invoice Summary */}
        {matchOutput && (
          <CollapsibleSection title="Invoice Summary" defaultOpen={true}>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
              <SummaryCard label="Total Invoices" value={matchOutput.stats.totalInvoices} />
              <SummaryCard label="Fully Settled" value={matchOutput.stats.fullySettled} color="text-green-700" />
              <SummaryCard label="Partially Settled" value={matchOutput.stats.partiallySettled} color="text-yellow-700" />
              <SummaryCard label="Not Settled" value={matchOutput.stats.notSettled} color="text-red-700" />
              <SummaryCard label="Overpaid / Mismatch" value={matchOutput.stats.mismatched} color="text-orange-700" />
              <SummaryCard label="Needs Review" value={matchOutput.stats.needsReview} color="text-purple-700" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b">
                    <th className="text-left py-1.5 pr-3">Invoice No</th>
                    <th className="text-left py-1.5 pr-3">Invoice Date</th>
                    <th className="text-right py-1.5 pr-3">Invoice Amount</th>
                    <th className="text-right py-1.5 pr-3">Settled</th>
                    <th className="text-right py-1.5 pr-3">Outstanding</th>
                    <th className="text-center py-1.5">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {invoicePagination.pageRows.map((s) => (
                    <tr key={s.invoiceNo} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="py-1.5 pr-3 text-gray-800">{s.invoiceNo}</td>
                      <td className="py-1.5 pr-3 whitespace-nowrap text-gray-600">{s.invoiceDate ?? "—"}</td>
                      <td className="py-1.5 pr-3 text-right text-gray-800">
                        {s.invoiceAmount != null ? s.invoiceAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-right text-green-700">
                        {s.totalSettled.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td className="py-1.5 pr-3 text-right text-red-700">
                        {s.outstanding != null ? s.outstanding.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}
                      </td>
                      <td className="py-1.5 text-center">
                        <InvoiceStatusBadge status={s.status} />
                      </td>
                    </tr>
                  ))}
                  {invoicePagination.pageRows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="text-center text-gray-400 text-xs py-4">
                        No invoices to summarize yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <PaginationBar
              currentPage={invoicePagination.currentPage}
              totalPages={invoicePagination.totalPages}
              pageSize={invoicePagination.pageSize}
              total={matchOutput.invoiceSummary.length}
              onPageChange={invoicePagination.setPage}
              onPageSizeChange={invoicePagination.setPageSize}
            />
          </CollapsibleSection>
        )}

        {/* Bank Statement (Transactions) */}
        <CollapsibleSection title="Transactions" defaultOpen={false}>
          {bankLoading ? (
            <p className="text-sm text-gray-500">Loading bank statement...</p>
          ) : !bankReview ? (
            <p className="text-sm text-red-600">
              Could not load this document&apos;s bank statement.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <StatChip label="Transactions" value={bankTransactions.length} />
              {dateRange && (
                <StatChip
                  label="Period"
                  value={`${dateRange.start} → ${dateRange.end}`}
                />
              )}
              <Link
                href={`/brs-review/${documentId}`}
                className="text-emerald-600 hover:underline text-xs"
              >
                View / re-process →
              </Link>
            </div>
          )}
        </CollapsibleSection>

        {/* Chart of Accounts (3-way only) */}
        {mode === "3-way" && (
          <CollapsibleSection title="Chart of Accounts" defaultOpen={true}>
            <FileDropzone
              accept=".xlsx,.xlsm"
              file={coaFile}
              onFileSelected={handleCoaFile}
              label={
                coaUploading
                  ? "Uploading..."
                  : "Drag & drop your Chart of Accounts Excel file here, or click to browse"
              }
              hint="Columns: Account Code, Account Name, Account Type, Parent Group (optional)"
            />
            {coaErrors.length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700 space-y-1">
                {coaErrors.map((e, i) => (
                  <p key={i}>{e}</p>
                ))}
              </div>
            )}
            {coaRows.length > 0 && (
              <div className="space-y-2">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-500 border-b">
                        <th className="text-left py-1.5 pr-3">Account Code</th>
                        <th className="text-left py-1.5 pr-3">Account Name</th>
                        <th className="text-left py-1.5 pr-3">Account Type</th>
                        <th className="text-left py-1.5">Parent Group</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coaPagination.pageRows.map((row, i) => (
                        <tr
                          key={i}
                          className="border-b last:border-0 text-gray-700"
                        >
                          <td className="py-1.5 pr-3 font-mono">
                            {row.account_code}
                          </td>
                          <td className="py-1.5 pr-3">{row.account_name}</td>
                          <td className="py-1.5 pr-3">{row.account_type}</td>
                          <td className="py-1.5 text-gray-500">
                            {row.parent_group ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <PaginationBar
                  currentPage={coaPagination.currentPage}
                  totalPages={coaPagination.totalPages}
                  pageSize={coaPagination.pageSize}
                  total={coaRows.length}
                  onPageChange={coaPagination.setPage}
                  onPageSizeChange={coaPagination.setPageSize}
                />
              </div>
            )}
          </CollapsibleSection>
        )}

        {/* Ledger */}
        <CollapsibleSection title="Receipt / Payment Ledger" defaultOpen={true}>
          <div className="gap-3">
            <FileDropzone
              accept=".xlsx,.xlsm"
              file={ledgerFile}
              onFileSelected={handleLedgerFile}
              label={
                ledgerUploading ? "Uploading..." : "Upload Ledger Excel file"
              }
              hint="Transaction Type, Invoice No, Invoice Date, Invoice Amount, Ledger Date, Ledger Voucher, Ledger Amount, Account Name, Bank/Cash Account (Invoice Date/Amount and last 2 optional; Ledger Date/Voucher/Amount blank together = unsettled)"
            />
            {/* <div className="flex items-center justify-center border border-gray-200 rounded-lg p-6 bg-gray-50">
              <button
                type="button"
                disabled
                title="Coming soon"
                onClick={onConnectDatabase}
                className="px-4 py-2 rounded-lg bg-gray-200 text-gray-500 text-sm font-medium cursor-not-allowed"
              >
                Connect Database
              </button>
            </div> */}
          </div>
          {ledgerErrors.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700 space-y-1">
              {ledgerErrors.map((e, i) => (
                <p key={i}>{e}</p>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between pt-2 border-t">
            <span className="text-xs text-gray-500">
              {ledgerRows.length} row(s)
            </span>
            <button
              type="button"
              onClick={() => {
                setLedgerRows((prev) => [...prev, blankLedgerRow()]);
                ledgerPagination.setPage(
                  Math.floor(ledgerRows.length / ledgerPagination.pageSize),
                );
              }}
              className="text-xs bg-emerald-50 text-emerald-700 hover:bg-emerald-100 px-2 py-1 rounded"
            >
              + Add Row
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="text-left py-1 pr-2">Transaction Type</th>
                  <th className="text-left py-1 pr-2">Invoice No</th>
                  <th className="text-left py-1 pr-2">Invoice Date</th>
                  <th className="text-right py-1 pr-2">Invoice Amount</th>
                  <th className="text-left py-1 pr-2">Ledger Date</th>
                  <th className="text-left py-1 pr-2">Ledger Voucher</th>
                  <th className="text-right py-1 pr-2">Ledger Amount</th>
                  {mode === "3-way" && (
                    <th className="text-left py-1 pr-2">Account Name</th>
                  )}
                  {mode === "3-way" && (
                    <th className="text-left py-1 pr-2">Bank/Cash Account</th>
                  )}
                  <th className="py-1"></th>
                </tr>
              </thead>
              <tbody>
                {ledgerPagination.pageRows.map((row) => {
                  const errors = ledgerRowErrors.get(row.id) ?? [];
                  return (
                    <tr
                      key={row.id}
                      className="border-b last:border-0 align-top"
                    >
                      <td className="py-1 pr-2">
                        <select
                          value={row.transaction_type}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              transaction_type: e.target
                                .value as LedgerTransactionType,
                            })
                          }
                          className={tdInputCls}
                        >
                          <option value="Sales Receipt">Sales Receipt</option>
                          <option value="Purchase Payment">
                            Purchase Payment
                          </option>
                        </select>
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          value={row.invoice_no}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              invoice_no: e.target.value,
                            })
                          }
                          className={tdInputCls}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          value={row.invoice_date ?? ""}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              invoice_date: e.target.value || null,
                            })
                          }
                          placeholder="YYYY-MM-DD"
                          className={tdInputCls}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          type="number"
                          step="any"
                          value={row.invoice_amount ?? ""}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              invoice_amount: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                          className={`${tdInputCls} text-right`}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          value={row.ledger_date ?? ""}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              ledger_date: e.target.value || null,
                            })
                          }
                          placeholder="YYYY-MM-DD (blank = unsettled)"
                          className={tdInputCls}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          value={row.ledger_voucher ?? ""}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              ledger_voucher: e.target.value || null,
                            })
                          }
                          className={tdInputCls}
                        />
                      </td>
                      <td className="py-1 pr-2">
                        <input
                          type="number"
                          step="any"
                          value={row.ledger_amount ?? ""}
                          onChange={(e) =>
                            updateLedgerRow(row.id, {
                              ledger_amount: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                          className={`${tdInputCls} text-right`}
                        />
                      </td>
                      {mode === "3-way" && (
                        <td className="py-1 pr-2">
                          <input
                            value={row.account_name ?? ""}
                            onChange={(e) =>
                              updateLedgerRow(row.id, {
                                account_name: e.target.value,
                              })
                            }
                            placeholder="e.g. Usha Nandhini"
                            className={tdInputCls}
                          />
                        </td>
                      )}
                      {mode === "3-way" && (
                        <td className="py-1 pr-2">
                          <input
                            value={row.bank_cash_account ?? ""}
                            onChange={(e) =>
                              updateLedgerRow(row.id, {
                                bank_cash_account: e.target.value,
                              })
                            }
                            placeholder="e.g. ICICI Bank Current A/c"
                            className={tdInputCls}
                          />
                        </td>
                      )}
                      <td className="py-1">
                        <button
                          type="button"
                          onClick={() => removeLedgerRow(row.id)}
                          className="text-red-400 hover:text-red-600 px-1"
                        >
                          ✕
                        </button>
                        {errors.length > 0 && (
                          <div className="text-[10px] text-red-600 mt-0.5 max-w-[160px]">
                            {errors.join("; ")}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {ledgerRows.length === 0 && (
              <p className="text-center text-gray-400 text-xs py-4">
                No ledger entries yet.
              </p>
            )}
          </div>
          <PaginationBar
            currentPage={ledgerPagination.currentPage}
            totalPages={ledgerPagination.totalPages}
            pageSize={ledgerPagination.pageSize}
            total={ledgerRows.length}
            onPageChange={ledgerPagination.setPage}
            onPageSizeChange={ledgerPagination.setPageSize}
          />
        </CollapsibleSection>
      </div>
    </div>
  );
}

const sectionTitle =
  "font-semibold text-[#2d3588] text-sm uppercase tracking-wide border-b-[#2d3588] pb-2 mb-2 ";
const tdInputCls =
  "w-full border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-400 min-w-[90px]";

function StatChip({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded px-2.5 py-1 text-xs">
      <span className="text-gray-500">{label}:</span>
      <span className="font-semibold text-gray-900">{value}</span>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-center">
      <p className={`text-xl font-bold ${color ?? "text-gray-900"}`}>{value}</p>
      <p className="text-[11px] text-gray-500 mt-0.5">{label}</p>
    </div>
  );
}

function VoucherStatusBadge({ status }: { status: VoucherStatus }) {
  const cls =
    status === "Matched" || status === "Matched (combined)"
      ? "bg-green-100 text-green-800"
      : status === "Partially Matched"
        ? "bg-yellow-100 text-yellow-800"
        : "bg-red-100 text-red-800";
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  const cls =
    status === "Fully Settled"
      ? "bg-green-100 text-green-800"
      : status === "Partially Settled"
        ? "bg-yellow-100 text-yellow-800"
        : status === "Overpaid/Mismatch"
          ? "bg-orange-100 text-orange-800"
          : status === "Needs Review"
            ? "bg-purple-100 text-purple-800"
            : "bg-red-100 text-red-800";
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {status}
    </span>
  );
}

