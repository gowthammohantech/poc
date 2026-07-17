import { describe, it, expect } from "vitest";
import {
  toCents,
  normalizeDate,
  normalizeReference,
  normalizeName,
  daysBetween,
  addDaysIso,
  similarity,
} from "../normalize";

describe("toCents", () => {
  it("converts a plain number to integer cents", () => {
    expect(toCents(25000)).toBe(2500000);
  });
  it("strips currency symbols and commas from strings", () => {
    expect(toCents("₹25,000.50")).toBe(2500050);
    expect(toCents("INR 1,200")).toBe(120000);
  });
  it("returns null for blank/invalid input", () => {
    expect(toCents(null)).toBeNull();
    expect(toCents("")).toBeNull();
    expect(toCents("not a number")).toBeNull();
  });
  it("avoids float rounding drift", () => {
    expect((toCents(19.1) ?? 0) - (toCents(19.1) ?? 0)).toBe(0);
    expect((toCents(0.1) ?? 0) + (toCents(0.2) ?? 0)).toBe(30);
  });
});

describe("normalizeDate", () => {
  it("handles already-ISO dates", () => {
    expect(normalizeDate("2026-01-01")).toBe("2026-01-01");
  });
  it("handles DD-Mon-YY", () => {
    expect(normalizeDate("01-Jan-26")).toBe("2026-01-01");
  });
  it("handles DD-MM-YYYY and DD/MM/YYYY", () => {
    expect(normalizeDate("15-04-2024")).toBe("2024-04-15");
    expect(normalizeDate("15/04/2024")).toBe("2024-04-15");
  });
  it("handles DD/MM/YY with 2-digit year assumed 2000+", () => {
    expect(normalizeDate("15/04/24")).toBe("2024-04-15");
  });
  it("returns null for unparseable input", () => {
    expect(normalizeDate("not a date")).toBeNull();
    expect(normalizeDate("")).toBeNull();
    expect(normalizeDate(null)).toBeNull();
  });
});

describe("normalizeReference", () => {
  it("normalizes case/spacing/symbols to the same value", () => {
    expect(normalizeReference("RV-101")).toBe(normalizeReference("rv101"));
    expect(normalizeReference("RV-101")).toBe(normalizeReference("RV 101"));
  });
  it("strips leading zeros only for purely-numeric references", () => {
    expect(normalizeReference("0101")).toBe("101");
    expect(normalizeReference("RV-0101")).toBe("RV0101");
  });
});

describe("normalizeName", () => {
  it("strips common suffixes and normalizes case/whitespace", () => {
    expect(normalizeName("Usha Nandhini")).toBe(normalizeName("USHA   NANDHINI"));
    expect(normalizeName("ABC Traders Pvt Ltd")).toBe(normalizeName("abc traders"));
  });
});

describe("daysBetween / addDaysIso", () => {
  it("computes whole-day differences", () => {
    expect(daysBetween("2024-04-09", "2024-04-12")).toBe(3);
  });
  it("addDaysIso round-trips with daysBetween", () => {
    const shifted = addDaysIso("2024-04-09", 5);
    expect(daysBetween("2024-04-09", shifted)).toBe(5);
  });
});

describe("similarity", () => {
  it("is 1 for identical strings and 0 for empty input", () => {
    expect(similarity("abc", "abc")).toBe(1);
    expect(similarity("", "abc")).toBe(0);
  });
});
