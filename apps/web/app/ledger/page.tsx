"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  getLedgerEntries,
  createLedgerEntry,
  updateLedgerEntry,
  deleteLedgerEntry,
} from "@/lib/api";
import type { LedgerEntry, LedgerEntryInput } from "@/types/ledger";

const emptyForm: LedgerEntryInput = {
  entry_date: "",
  ledger_name: "",
  description: "",
  reference_number: "",
  amount: 0,
  entry_type: "CREDIT",
  notes: "",
};

export default function LedgerPage() {
  const [entries, setEntries] = useState<LedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const { register, handleSubmit, reset } = useForm<LedgerEntryInput>({
    defaultValues: emptyForm,
  });

  function load() {
    setLoading(true);
    getLedgerEntries()
      .then(setEntries)
      .catch(() => setError("Failed to load ledger entries."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  function openAddForm() {
    setEditingId(null);
    reset(emptyForm);
    setShowForm(true);
  }

  function openEditForm(entry: LedgerEntry) {
    setEditingId(entry.id);
    reset({
      entry_date: entry.entry_date,
      ledger_name: entry.ledger_name ?? "",
      description: entry.description,
      reference_number: entry.reference_number ?? "",
      amount: entry.amount,
      entry_type: entry.entry_type,
      notes: entry.notes ?? "",
    });
    setShowForm(true);
  }

  async function onSubmit(data: LedgerEntryInput) {
    setError("");
    const payload = {
      ...data,
      amount: Number(data.amount),
      ledger_name: data.ledger_name || null,
      reference_number: data.reference_number || null,
      notes: data.notes || null,
    };
    try {
      if (editingId) {
        await updateLedgerEntry(editingId, payload);
      } else {
        await createLedgerEntry(payload);
      }
      setShowForm(false);
      setEditingId(null);
      load();
    } catch {
      setError("Failed to save ledger entry.");
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Delete this ledger entry?")) return;
    try {
      await deleteLedgerEntry(id);
      load();
    } catch {
      setError("Failed to delete ledger entry.");
    }
  }

  const fmt = (n: number) =>
    n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <main className="min-h-screen bg-gray-50 py-10 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Ledger</h1>
            <p className="text-sm text-gray-500 mt-1">
              Your book-side records. Every processed BRS document is automatically 2-way matched against this list.
            </p>
          </div>
          <button
            onClick={openAddForm}
            className="text-sm bg-emerald-600 text-white px-4 py-2 rounded-lg hover:bg-emerald-700 transition-colors"
          >
            + Add Entry
          </button>
        </div>

        {error && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {showForm && (
          <form
            onSubmit={handleSubmit(onSubmit)}
            className="mt-6 bg-white rounded-xl border p-4 space-y-3"
          >
            <h2 className="font-semibold text-gray-900 text-sm uppercase tracking-wide border-b pb-2">
              {editingId ? "Edit Entry" : "New Entry"}
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Date">
                <input
                  {...register("entry_date", { required: true })}
                  className={inputCls}
                  placeholder="YYYY-MM-DD"
                />
              </Field>
              <Field label="Type">
                <select {...register("entry_type", { required: true })} className={inputCls}>
                  <option value="CREDIT">CREDIT (money in)</option>
                  <option value="DEBIT">DEBIT (money out)</option>
                </select>
              </Field>
              <Field label="Ledger Name">
                <input {...register("ledger_name")} className={inputCls} placeholder="Customer, vendor, or account" />
              </Field>
              <Field label="Reference #">
                <input {...register("reference_number")} className={inputCls} />
              </Field>
              <Field label="Description" colSpan>
                <input {...register("description", { required: true })} className={inputCls} />
              </Field>
              <Field label="Amount">
                <input
                  {...register("amount", { required: true, valueAsNumber: true })}
                  className={inputCls}
                  type="number"
                  step="any"
                />
              </Field>
              <Field label="Notes">
                <input {...register("notes")} className={inputCls} />
              </Field>
            </div>
            <div className="flex gap-3 pt-2">
              <button
                type="submit"
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-2 px-4 rounded-lg transition-colors text-sm"
              >
                {editingId ? "Save Changes" : "Add Entry"}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors text-sm font-medium"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        <div className="mt-6">
          {loading ? (
            <p className="text-gray-500">Loading...</p>
          ) : entries.length === 0 ? (
            <div className="bg-white rounded-xl border p-12 text-center">
              <p className="text-gray-500">No ledger entries yet.</p>
              <button onClick={openAddForm} className="mt-4 text-emerald-600 hover:underline">
                Add your first entry →
              </button>
            </div>
          ) : (
            <div className="bg-white rounded-xl border overflow-hidden overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Date</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Ledger Name</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Description</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Ref #</th>
                    <th className="text-left py-3 px-4 font-medium text-gray-700">Type</th>
                    <th className="text-right py-3 px-4 font-medium text-gray-700">Amount</th>
                    <th className="py-3 px-4"></th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.id} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="py-3 px-4 text-gray-600">{entry.entry_date}</td>
                      <td className="py-3 px-4 text-gray-900 max-w-[180px] truncate" title={entry.ledger_name ?? ""}>
                        {entry.ledger_name || "—"}
                      </td>
                      <td className="py-3 px-4 text-gray-900 max-w-[240px] truncate" title={entry.description}>
                        {entry.description}
                      </td>
                      <td className="py-3 px-4 font-mono text-gray-500 text-xs">
                        {entry.reference_number || "—"}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-xs font-medium ${
                            entry.entry_type === "CREDIT"
                              ? "bg-green-50 text-green-700"
                              : "bg-red-50 text-red-700"
                          }`}
                        >
                          {entry.entry_type}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-medium text-gray-900">
                        {fmt(entry.amount)}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <button
                          onClick={() => openEditForm(entry)}
                          className="text-emerald-600 hover:underline text-xs mr-3"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => onDelete(entry.id)}
                          className="text-red-500 hover:underline text-xs"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

const inputCls = "w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500";

function Field({
  label,
  children,
  colSpan,
}: {
  label: string;
  children: React.ReactNode;
  colSpan?: boolean;
}) {
  return (
    <div className={colSpan ? "col-span-2" : ""}>
      <label className="block text-xs font-medium mb-1 text-gray-600">{label}</label>
      {children}
    </div>
  );
}
