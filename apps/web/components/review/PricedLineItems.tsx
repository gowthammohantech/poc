"use client";

import { useFieldArray } from "react-hook-form";

import ConfidenceBadge from "@/components/ConfidenceBadge";
import { tdInputCls } from "@/components/review/ReviewPrimitives";
import type { UsInvData, UsSoData } from "@/types/usDocument";

interface Column {
  key: string;
  label: string;
  numeric?: boolean;
  minWidth?: string;
}

interface Layout {
  columns: Column[];
  /** The two fields whose product the amount column must equal. */
  priceKey: string;
  amountKey: string;
  emptyText: string;
}

/**
 * A purchase order and an invoice price their lines the same way but name the
 * fields differently, and each carries one column the other does not: an
 * order's due date, an invoice's ordered-versus-shipped quantity.
 */
const LAYOUTS: Record<"SO" | "INV", Layout> = {
  SO: {
    columns: [
      { key: "part_number", label: "Part Number", minWidth: "min-w-[140px]" },
      { key: "description", label: "Description", minWidth: "min-w-[200px]" },
      { key: "quantity", label: "Qty", numeric: true },
      { key: "uom", label: "UOM", minWidth: "min-w-[50px]" },
      { key: "due_date", label: "Due Date", minWidth: "min-w-[95px]" },
      { key: "unit_cost", label: "Unit Cost", numeric: true },
      { key: "extended_cost", label: "Ext'd Cost", numeric: true },
    ],
    priceKey: "unit_cost",
    amountKey: "extended_cost",
    emptyText: "No line items were extracted from this order.",
  },
  INV: {
    columns: [
      { key: "part_number", label: "Part Number", minWidth: "min-w-[140px]" },
      { key: "description", label: "Description", minWidth: "min-w-[200px]" },
      { key: "quantity_ordered", label: "Qty Ord", numeric: true },
      { key: "quantity", label: "Qty Inv", numeric: true },
      { key: "uom", label: "UOM", minWidth: "min-w-[50px]" },
      { key: "unit_price", label: "Unit Price", numeric: true },
      { key: "amount", label: "Amount", numeric: true },
    ],
    priceKey: "unit_price",
    amountKey: "amount",
    emptyText: "No line items were extracted from this invoice.",
  },
};

interface Props {
  doc: UsSoData | UsInvData;
  variant: "SO" | "INV";
  /* eslint-disable @typescript-eslint/no-explicit-any */
  control: any;
  register: any;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  confidence: Record<string, number>;
}

/** A priced line table: quantity x unit price = line amount, per line. */
export default function PricedLineItems({ doc, variant, control, register, confidence }: Props) {
  const { fields, append, remove } = useFieldArray({ control, name: "line_items" as never });
  const layout = LAYOUTS[variant];
  const lines = (doc?.line_items ?? []) as unknown as Record<string, unknown>[];

  const emptyLine = Object.fromEntries(
    ["line_number", ...layout.columns.map((c) => c.key)].map((key) => [key, null]),
  );

  return (
    <section className="bg-white rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Line Items</h2>
        <ConfidenceBadge value={confidence.line_items ?? confidence.overall ?? 0} />
        <button
          type="button"
          onClick={() => append(emptyLine as never)}
          className="ml-auto text-xs text-blue-600 hover:underline"
        >
          + Add Row
        </button>
      </div>

      {fields.length === 0 ? (
        <p className="text-sm text-gray-500">{layout.emptyText}</p>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50">
                {["#", ...layout.columns.map((c) => c.label), ""].map((header) => (
                  <th
                    key={header}
                    className="border-b px-2 py-1 text-left font-medium text-gray-600 whitespace-nowrap"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields.map((field, i) => {
                const line = lines[i];
                const quantity = line?.quantity;
                const price = line?.[layout.priceKey];
                const amount = line?.[layout.amountKey];
                // Flagging the arithmetic here mirrors the deterministic rule
                // the backend runs, so a reviewer sees which row to look at
                // without reading the validation list.
                const expected =
                  typeof quantity === "number" && typeof price === "number" ? quantity * price : null;
                const mismatched =
                  expected !== null &&
                  typeof amount === "number" &&
                  Math.abs(expected - amount) > Math.max(0.05, expected * 0.001);

                return (
                  <tr key={field.id} className={mismatched ? "bg-red-50" : "even:bg-gray-50/50"}>
                    <td className="border-b px-2 py-1 text-gray-500">{i + 1}</td>
                    {layout.columns.map((column) => (
                      <td key={column.key} className={`border-b px-1 py-1 ${column.minWidth ?? ""}`}>
                        {column.numeric ? (
                          // Unit prices run to four decimal places; step="any" keeps them.
                          <input
                            type="number"
                            step="any"
                            className={`${tdInputCls} text-right`}
                            {...register(`line_items.${i}.${column.key}`, { valueAsNumber: true })}
                          />
                        ) : (
                          <input className={tdInputCls} {...register(`line_items.${i}.${column.key}`)} />
                        )}
                        {column.key === layout.amountKey && mismatched && (
                          <p className="text-[10px] text-red-600 mt-0.5 whitespace-nowrap">
                            expected {expected?.toFixed(2)}
                          </p>
                        )}
                      </td>
                    ))}
                    <td className="border-b px-1 py-1">
                      <button
                        type="button"
                        onClick={() => remove(i)}
                        className="text-gray-400 hover:text-red-600"
                        aria-label={`Remove line ${i + 1}`}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
