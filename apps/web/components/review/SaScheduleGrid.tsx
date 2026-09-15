"use client";

import { useFieldArray } from "react-hook-form";

import ConfidenceBadge from "@/components/ConfidenceBadge";
import { tdInputCls } from "@/components/review/ReviewPrimitives";
import { alignQuantities, partTotal, scheduleColumnLabel } from "@/lib/us/schedule";
import type { UsSaData } from "@/types/usDocument";

interface Props {
  doc: UsSaData;
  /* eslint-disable @typescript-eslint/no-explicit-any */
  control: any;
  register: any;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  confidence: Record<string, number>;
}

/**
 * The parts x week grid at the heart of a shipping authorization.
 *
 * The quantity array is positional against the schedule header, so the header
 * is edited once at the top rather than per row: correcting a week's date
 * fixes that column for every part at once, which is how the document itself
 * is laid out.
 *
 * The four identity columns are sticky so they stay readable while 35-odd week
 * columns scroll past. Each cell registers as a plain indexed path rather than
 * a nested field array -- react-hook-form is uncontrolled, so several hundred
 * inputs cost nothing per keystroke, whereas a field array per row would
 * re-render the row.
 */
export default function SaScheduleGrid({ doc, control, register, confidence }: Props) {
  const { fields: columnFields } = useFieldArray({ control, name: "schedule_columns" as never });
  const { fields: partFields } = useFieldArray({ control, name: "parts" as never });

  const columns = doc?.schedule_columns ?? [];
  const parts = doc?.parts ?? [];
  const width = columnFields.length;

  if (width === 0 || partFields.length === 0) {
    return (
      <section className="bg-white rounded-lg border p-4 space-y-2">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Delivery Schedule</h2>
        <p className="text-sm text-gray-500">
          No weekly schedule was extracted from this release. Check the page preview and, if the
          grid is visible there, re-process the document.
        </p>
      </section>
    );
  }

  const repaired = parts.filter((p) => p?.quantities_repaired);

  return (
    <section className="bg-white rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Delivery Schedule</h2>
        <ConfidenceBadge value={confidence.quantities ?? confidence.overall ?? 0} />
        <span className="text-xs text-gray-400">
          {partFields.length} part{partFields.length === 1 ? "" : "s"} × {width} week
          {width === 1 ? "" : "s"}
        </span>
      </div>

      {repaired.length > 0 && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
          {repaired.length} row{repaired.length === 1 ? " was" : "s were"} adjusted to fit the
          schedule header, so the quantities after the gap may sit under the wrong week. Check
          these against the page preview before submitting.
        </p>
      )}

      <div className="overflow-x-auto border border-gray-200 rounded">
        <table className="text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50">
              <th className="sticky left-0 z-20 bg-gray-50 border-b border-r px-2 py-1 text-left font-medium text-gray-600 min-w-[90px]">
                PO
              </th>
              <th className="sticky left-[90px] z-20 bg-gray-50 border-b border-r px-2 py-1 text-left font-medium text-gray-600 min-w-[110px]">
                Part Number
              </th>
              <th className="border-b border-r px-2 py-1 text-left font-medium text-gray-600 min-w-[160px]">
                Description
              </th>
              <th className="border-b border-r px-2 py-1 text-left font-medium text-gray-600 min-w-[70px]">
                Std Pack
              </th>
              {columnFields.map((field, c) => {
                const { week, date } = scheduleColumnLabel(columns[c]);
                return (
                  <th
                    key={field.id}
                    className="border-b border-r px-1 py-1 text-center font-medium text-gray-600 min-w-[72px]"
                  >
                    <input
                      className="w-full bg-transparent text-center font-semibold text-gray-700 focus:outline-none focus:bg-white focus:ring-1 focus:ring-blue-400 rounded"
                      defaultValue={week}
                      {...register(`schedule_columns.${c}.week_label` as const)}
                    />
                    <input
                      className="w-full bg-transparent text-center text-[10px] text-gray-500 focus:outline-none focus:bg-white focus:ring-1 focus:ring-blue-400 rounded"
                      defaultValue={date}
                      {...register(`schedule_columns.${c}.raw_delivery_date` as const)}
                    />
                  </th>
                );
              })}
              <th className="border-b px-2 py-1 text-right font-medium text-gray-600 min-w-[80px]">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {partFields.map((field, p) => {
              const part = parts[p];
              const quantities = alignQuantities(part?.quantities, width);
              return (
                <tr key={field.id} className="even:bg-gray-50/50">
                  <td className="sticky left-0 z-10 bg-inherit border-b border-r px-1 py-1">
                    <input className={tdInputCls} {...register(`parts.${p}.po_number` as const)} />
                  </td>
                  <td className="sticky left-[90px] z-10 bg-inherit border-b border-r px-1 py-1">
                    <input className={tdInputCls} {...register(`parts.${p}.part_number` as const)} />
                  </td>
                  <td className="border-b border-r px-1 py-1">
                    <input className={tdInputCls} {...register(`parts.${p}.description` as const)} />
                  </td>
                  <td className="border-b border-r px-1 py-1">
                    <input
                      type="number"
                      step="any"
                      className={tdInputCls}
                      {...register(`parts.${p}.std_pack` as const, { valueAsNumber: true })}
                    />
                  </td>
                  {quantities.map((_, c) => (
                    <td key={c} className="border-b border-r px-0.5 py-1">
                      <input
                        type="number"
                        step="any"
                        className={`${tdInputCls} text-right min-w-[64px]`}
                        {...register(`parts.${p}.quantities.${c}` as const, {
                          valueAsNumber: true,
                        })}
                      />
                    </td>
                  ))}
                  <td className="border-b px-2 py-1 text-right font-medium text-gray-700 tabular-nums">
                    {partTotal({ quantities }).toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-400">
        Scroll sideways for later weeks. Totals are computed from the extracted figures and
        refresh when the document is re-loaded.
      </p>
    </section>
  );
}
