"use client";

import { useFieldArray } from "react-hook-form";

import ConfidenceBadge from "@/components/ConfidenceBadge";
import { tdInputCls } from "@/components/review/ReviewPrimitives";
import type { UsSoData } from "@/types/usDocument";

interface Props {
  doc: UsSoData;
  /* eslint-disable @typescript-eslint/no-explicit-any */
  control: any;
  register: any;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  confidence: Record<string, number>;
}

const EMPTY_LINE = {
  line_number: null,
  part_number: null,
  description: null,
  quantity: null,
  uom: null,
  due_date: null,
  unit_cost: null,
  extended_cost: null,
};

/** The priced order table: quantity x unit cost = extended cost, per line. */
export default function SoLineItems({ doc, control, register, confidence }: Props) {
  const { fields, append, remove } = useFieldArray({ control, name: "line_items" as never });
  const lines = doc?.line_items ?? [];

  return (
    <section className="bg-white rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Line Items</h2>
        <ConfidenceBadge value={confidence.line_items ?? confidence.overall ?? 0} />
        <button
          type="button"
          onClick={() => append(EMPTY_LINE as never)}
          className="ml-auto text-xs text-blue-600 hover:underline"
        >
          + Add Row
        </button>
      </div>

      {fields.length === 0 ? (
        <p className="text-sm text-gray-500">No line items were extracted from this order.</p>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-gray-50">
                {["#", "Part Number", "Description", "Qty", "UOM", "Due Date", "Unit Cost", "Ext'd Cost", ""].map(
                  (header) => (
                    <th
                      key={header}
                      className="border-b px-2 py-1 text-left font-medium text-gray-600 whitespace-nowrap"
                    >
                      {header}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {fields.map((field, i) => {
                const line = lines[i];
                // Flagging the arithmetic here mirrors the deterministic rule
                // the backend runs, so a reviewer sees which row to look at
                // without reading the validation list.
                const expected =
                  typeof line?.quantity === "number" && typeof line?.unit_cost === "number"
                    ? line.quantity * line.unit_cost
                    : null;
                const mismatched =
                  expected !== null &&
                  typeof line?.extended_cost === "number" &&
                  Math.abs(expected - line.extended_cost) > Math.max(0.05, expected * 0.001);

                return (
                  <tr key={field.id} className={mismatched ? "bg-red-50" : "even:bg-gray-50/50"}>
                    <td className="border-b px-2 py-1 text-gray-500">{i + 1}</td>
                    <td className="border-b px-1 py-1 min-w-[140px]">
                      <input className={tdInputCls} {...register(`line_items.${i}.part_number` as const)} />
                    </td>
                    <td className="border-b px-1 py-1 min-w-[200px]">
                      <input className={tdInputCls} {...register(`line_items.${i}.description` as const)} />
                    </td>
                    <td className="border-b px-1 py-1">
                      <input
                        type="number"
                        step="any"
                        className={`${tdInputCls} text-right`}
                        {...register(`line_items.${i}.quantity` as const, { valueAsNumber: true })}
                      />
                    </td>
                    <td className="border-b px-1 py-1">
                      <input className={`${tdInputCls} min-w-[50px]`} {...register(`line_items.${i}.uom` as const)} />
                    </td>
                    <td className="border-b px-1 py-1">
                      <input className={`${tdInputCls} min-w-[95px]`} {...register(`line_items.${i}.due_date` as const)} />
                    </td>
                    <td className="border-b px-1 py-1">
                      {/* Unit costs run to four decimal places; step="any" keeps them. */}
                      <input
                        type="number"
                        step="any"
                        className={`${tdInputCls} text-right`}
                        {...register(`line_items.${i}.unit_cost` as const, { valueAsNumber: true })}
                      />
                    </td>
                    <td className="border-b px-1 py-1">
                      <input
                        type="number"
                        step="any"
                        className={`${tdInputCls} text-right`}
                        {...register(`line_items.${i}.extended_cost` as const, { valueAsNumber: true })}
                      />
                      {mismatched && (
                        <p className="text-[10px] text-red-600 mt-0.5 whitespace-nowrap">
                          expected {expected?.toFixed(2)}
                        </p>
                      )}
                    </td>
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
