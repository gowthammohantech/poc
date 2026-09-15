import { describe, expect, it } from "vitest";

import {
  alignQuantities,
  flattenScheduleHeader,
  partTotal,
  scheduleColumnLabel,
} from "@/lib/us/schedule";
import type { UsScheduleColumn } from "@/types/usDocument";

function column(overrides: Partial<UsScheduleColumn> = {}): UsScheduleColumn {
  return {
    week_label: "W27",
    ship_date: "2026-06-22",
    delivery_date: "2026-06-29",
    raw_ship_date: "22-Jun",
    raw_delivery_date: "29-Jun",
    ...overrides,
  };
}

describe("alignQuantities", () => {
  it("leaves a correctly sized row alone", () => {
    const row = [0, 50000, 0];
    expect(alignQuantities(row, 3)).toBe(row);
  });

  it("pads a short row with nulls rather than dropping the columns", () => {
    expect(alignQuantities([0, 50000], 4)).toEqual([0, 50000, null, null]);
  });

  it("trims a long row to the header width", () => {
    expect(alignQuantities([1, 2, 3, 4, 5], 3)).toEqual([1, 2, 3]);
  });

  it.each([[null], [undefined]])("treats %s as an empty row", (input) => {
    expect(alignQuantities(input as null | undefined, 2)).toEqual([null, null]);
  });

  it("returns nothing for a schedule with no columns", () => {
    expect(alignQuantities([1, 2], 0)).toEqual([]);
  });
});

describe("scheduleColumnLabel", () => {
  it("prefers the date as printed on the document", () => {
    expect(scheduleColumnLabel(column())).toEqual({ week: "W27", date: "29-Jun" });
  });

  it("falls back to the derived ISO date", () => {
    expect(scheduleColumnLabel(column({ raw_delivery_date: null }))).toEqual({
      week: "W27",
      date: "2026-06-29",
    });
  });

  it("survives a missing column", () => {
    expect(scheduleColumnLabel(undefined)).toEqual({ week: "", date: "" });
  });
});

describe("partTotal", () => {
  it("sums the released quantities", () => {
    expect(partTotal({ quantities: [0, 50000, 0, 50000] })).toBe(100000);
  });

  it("skips cells that could not be read", () => {
    expect(partTotal({ quantities: [1000, null, 2000] })).toBe(3000);
  });

  it("is zero for an empty row", () => {
    expect(partTotal({ quantities: [] })).toBe(0);
  });
});

describe("flattenScheduleHeader", () => {
  it("puts the identity columns first and a total last", () => {
    const header = flattenScheduleHeader([column(), column({ week_label: "W28" })]);
    expect(header).toEqual([
      "PO", "Part Number", "Description", "Std Pack",
      "W27 29-Jun", "W28 29-Jun", "Total",
    ]);
  });

  it("omits a missing date rather than leaving a dangling space", () => {
    const header = flattenScheduleHeader([
      column({ raw_delivery_date: null, delivery_date: null }),
    ]);
    expect(header[4]).toBe("W27");
  });
});
