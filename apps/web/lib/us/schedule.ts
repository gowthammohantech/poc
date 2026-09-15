/**
 * Helpers for a shipping authorization's weekly grid.
 *
 * The quantity array is positional against the schedule header, so the review
 * grid needs a row of exactly the header's width to render. Kept in lib/ both
 * because it is pure and because vitest only collects tests from here.
 */

import type { UsSaPart, UsScheduleColumn } from "@/types/usDocument";

/**
 * A row of exactly `columnCount` cells. The backend already pads ragged rows
 * and flags them, but a hand-edited or partially extracted document can still
 * reach the grid short, and a grid that drops cells is worse than one that
 * shows blanks.
 */
export function alignQuantities(
  quantities: (number | null)[] | null | undefined,
  columnCount: number,
): (number | null)[] {
  const row = Array.isArray(quantities) ? quantities : [];
  if (row.length === columnCount) return row;
  if (row.length > columnCount) return row.slice(0, columnCount);
  return [...row, ...Array<number | null>(columnCount - row.length).fill(null)];
}

/** The two-line header a bucket shows: its week label over its delivery date. */
export function scheduleColumnLabel(column: UsScheduleColumn | undefined): {
  week: string;
  date: string;
} {
  return {
    week: column?.week_label ?? "",
    // Prefer what the document printed; the ISO date is derived, so it is the
    // fallback rather than the thing a reviewer checks against the page.
    date: column?.raw_delivery_date ?? column?.delivery_date ?? "",
  };
}

/** Total pieces released for a part, ignoring cells that could not be read. */
export function partTotal(part: Pick<UsSaPart, "quantities">): number {
  return (part.quantities ?? []).reduce<number>(
    (sum, q) => sum + (typeof q === "number" && Number.isFinite(q) ? q : 0),
    0,
  );
}

/** Column headers for a flat export: one identity block, then one per bucket. */
export function flattenScheduleHeader(columns: UsScheduleColumn[]): string[] {
  return [
    "PO",
    "Part Number",
    "Description",
    "Std Pack",
    ...columns.map((c) => {
      const { week, date } = scheduleColumnLabel(c);
      return [week, date].filter(Boolean).join(" ");
    }),
    "Total",
  ];
}
