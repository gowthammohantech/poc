/**
 * Which document regime the app is working in.
 *
 * This is a module-level store rather than a React context because the value
 * has to cross boundaries a provider would not cover cheaply: the TopBar sets
 * it, the documents list and upload page read it, and the agent hub at "/"
 * bypasses AppLayout entirely. Keeping the store here also puts it somewhere
 * vitest can reach -- the config only collects lib/ **\/*.test.ts.
 */

export type Country = "INDIA" | "USA";

export const COUNTRIES: { key: Country; label: string; short: string }[] = [
  { key: "INDIA", label: "India", short: "IN" },
  { key: "USA", label: "United States", short: "US" },
];

export const DEFAULT_COUNTRY: Country = "INDIA";
export const COUNTRY_STORAGE_KEY = "selected_country";

export function isCountry(value: unknown): value is Country {
  return value === "INDIA" || value === "USA";
}

/** Anything unrecognised is INDIA, matching the backend's normalize_country. */
export function normalizeCountry(value: string | null | undefined): Country {
  const candidate = (value ?? "").trim().toUpperCase();
  return isCountry(candidate) ? candidate : DEFAULT_COUNTRY;
}

export function countryLabel(country: Country): string {
  return COUNTRIES.find((c) => c.key === country)?.label ?? country;
}

let current: Country = DEFAULT_COUNTRY;
const listeners = new Set<() => void>();

export function getCountry(): Country {
  return current;
}

/** The value React renders on the server, before storage has been read. */
export function getServerCountry(): Country {
  return DEFAULT_COUNTRY;
}

export function setCountry(next: Country): void {
  if (next === current) return;
  current = next;
  try {
    window.localStorage.setItem(COUNTRY_STORAGE_KEY, next);
  } catch {
    // Private browsing and blocked site data both throw here. The selection
    // still works for this session; it just will not survive a reload.
  }
  listeners.forEach((listener) => listener());
}

export function subscribeCountry(listener: () => void): () => void {
  listeners.add(listener);

  // Keep a second tab in step. Storage events only fire in *other* tabs, so
  // this never double-handles the write above.
  const onStorage = (event: StorageEvent) => {
    if (event.key !== COUNTRY_STORAGE_KEY) return;
    const next = normalizeCountry(event.newValue);
    if (next === current) return;
    current = next;
    listeners.forEach((l) => l());
  };

  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }

  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

/** Read the saved country once on the client. Safe to call during SSR. */
export function hydrateCountryFromStorage(): void {
  if (typeof window === "undefined") return;
  let saved: string | null = null;
  try {
    saved = window.localStorage.getItem(COUNTRY_STORAGE_KEY);
  } catch {
    return;
  }
  if (saved === null) return;
  const next = normalizeCountry(saved);
  if (next === current) return;
  current = next;
  listeners.forEach((listener) => listener());
}

/** Test-only: drop the in-memory selection so cases cannot leak into each other. */
export function resetCountryForTests(): void {
  current = DEFAULT_COUNTRY;
  listeners.clear();
}
