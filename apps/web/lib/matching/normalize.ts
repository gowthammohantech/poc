/**
 * Layer 1 — normalization utilities shared by every other matching layer.
 * Nothing here compares two records directly; it only produces canonical values.
 */

export const MIN_SUBSTRING_LEN = 4;

/** Levenshtein edit distance — the base for every fuzzy-similarity score in this engine. */
export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const curr = [i];
    for (let j = 1; j <= b.length; j++) {
      curr[j] = a[i - 1] === b[j - 1] ? prev[j - 1] : 1 + Math.min(prev[j - 1], prev[j], curr[j - 1]);
    }
    prev = curr;
  }
  return prev[b.length];
}

/** 0-1 similarity ratio derived from Levenshtein distance. */
export function similarity(a: string, b: string): number {
  if (!a || !b) return 0;
  const maxLen = Math.max(a.length, b.length);
  if (maxLen === 0) return 1;
  return 1 - levenshtein(a, b) / maxLen;
}

/** Trim + lowercase — the baseline text normalization used before any comparison. */
export function normalizeText(s: string | null | undefined): string {
  return (s ?? "").trim().toLowerCase();
}

/** Strip everything but letters/digits — collapses punctuation/spacing noise ("INV-091" vs "INV091"). */
export function alnumOnly(s: string | null | undefined): string {
  return (s ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function digitsOnly(s: string | null | undefined): string {
  return (s ?? "").replace(/[^0-9]/g, "");
}

export function tokenize(s: string | null | undefined): string[] {
  return (s ?? "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((t) => t.length >= MIN_SUBSTRING_LEN);
}

/**
 * Reference/voucher normalization: uppercase, strip whitespace/punctuation, strip leading
 * zeros when the remainder is purely numeric (so "0101" and "101" compare equal, but an
 * alnum code like "RV0101" keeps its zeros since stripping them could collide two different
 * vouchers).
 */
export function normalizeReference(raw: string | null | undefined): string {
  const stripped = alnumOnly(raw).toUpperCase();
  if (/^\d+$/.test(stripped)) {
    return stripped.replace(/^0+(?=\d)/, "");
  }
  return stripped;
}

const NAME_NOISE_WORDS = new Set(["LTD", "LIMITED", "PVT", "PRIVATE", "INC", "LLC", "CO", "COMPANY", "AC", "ACCOUNT"]);

/** Account-name normalization: uppercase, strip common corporate/account suffixes, collapse whitespace. */
export function normalizeName(raw: string | null | undefined): string {
  const cleaned = (raw ?? "")
    .toUpperCase()
    .replace(/[^A-Z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .filter((w) => !NAME_NOISE_WORDS.has(w));
  return cleaned.join(" ");
}

/**
 * Amount normalization: strip currency symbols/commas and convert to integer cents (rounded),
 * once at ingestion — every downstream comparison works on these integers, never raw floats.
 */
export function toCents(raw: string | number | null | undefined): number | null {
  if (raw == null || raw === "") return null;
  let n: number;
  if (typeof raw === "number") {
    n = raw;
  } else {
    const cleaned = raw.trim().replace(/[₹$,]/g, "").replace(/INR/gi, "").trim();
    n = Number(cleaned);
  }
  if (!Number.isFinite(n)) return null;
  return Math.round(n * 100);
}

export function centsToAmount(cents: number | null): number | null {
  return cents == null ? null : cents / 100;
}

/**
 * Date normalization → canonical ISO "YYYY-MM-DD". Format list kept in sync with
 * apps/backend/app/services/excel_parse_service.py:_DATE_FORMATS — update both together.
 * 2-digit years are assumed 2000+.
 */
const MONTHS: Record<string, string> = {
  jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
  jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
};

export function normalizeDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = raw.trim();
  if (!s) return null;

  // YYYY-MM-DD (already canonical)
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;

  // DD-MM-YYYY or DD/MM/YYYY
  m = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
  if (m) return isoOrNull(m[3], m[2], m[1]);

  // DD/MM/YY
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2})$/);
  if (m) return isoOrNull(String(2000 + Number(m[3])), m[2], m[1]);

  // DD-Mon-YY or DD-Mon-YYYY
  m = s.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2,4})$/);
  if (m) {
    const mon = MONTHS[m[2].toLowerCase()];
    if (!mon) return null;
    const year = m[3].length === 2 ? String(2000 + Number(m[3])) : m[3];
    return isoOrNull(year, mon, m[1]);
  }

  // Fallback: let Date parse it (handles things like ISO with time components)
  const d = new Date(s);
  if (!Number.isNaN(d.getTime())) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }
  return null;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function isoOrNull(year: string, month: string, day: string): string | null {
  const y = Number(year), mo = Number(month), d = Number(day);
  if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return `${y}-${pad2(mo)}-${pad2(d)}`;
}

/** Whole-day difference between two canonical ISO dates, or null if either is unparseable. */
export function daysBetween(a: string | null, b: string | null): number | null {
  if (!a || !b) return null;
  const da = new Date(a);
  const db = new Date(b);
  if (Number.isNaN(da.getTime()) || Number.isNaN(db.getTime())) return null;
  return Math.abs((da.getTime() - db.getTime()) / (1000 * 60 * 60 * 24));
}

export function addDaysIso(iso: string, days: number): string {
  const d = new Date(iso);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}
