import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  COUNTRY_STORAGE_KEY,
  DEFAULT_COUNTRY,
  getCountry,
  hydrateCountryFromStorage,
  isCountry,
  normalizeCountry,
  resetCountryForTests,
  setCountry,
  subscribeCountry,
} from "@/lib/country";

function fakeStorage(seed: Record<string, string> = {}) {
  const store: Record<string, string> = { ...seed };
  return {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    _store: store,
  };
}

function installWindow(storage: ReturnType<typeof fakeStorage>) {
  (globalThis as Record<string, unknown>).window = {
    localStorage: storage,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
}

beforeEach(() => resetCountryForTests());

afterEach(() => {
  delete (globalThis as Record<string, unknown>).window;
  resetCountryForTests();
});

describe("normalizeCountry", () => {
  it.each([
    ["USA", "USA"],
    ["usa", "USA"],
    ["  usa  ", "USA"],
    ["INDIA", "INDIA"],
    ["india", "INDIA"],
  ])("normalizes %s to %s", (input, expected) => {
    expect(normalizeCountry(input)).toBe(expected);
  });

  it.each([null, undefined, "", "   ", "MEXICO", "US", "IN", "{}"])(
    "falls back to India for %s",
    (input) => {
      expect(normalizeCountry(input as string | null | undefined)).toBe("INDIA");
    },
  );
});

describe("isCountry", () => {
  it("accepts only the two known values", () => {
    expect(isCountry("USA")).toBe(true);
    expect(isCountry("INDIA")).toBe(true);
    expect(isCountry("usa")).toBe(false);
    expect(isCountry(undefined)).toBe(false);
  });
});

describe("the store", () => {
  it("starts on the default", () => {
    expect(getCountry()).toBe(DEFAULT_COUNTRY);
  });

  it("notifies subscribers and persists the choice", () => {
    const storage = fakeStorage();
    installWindow(storage);
    const listener = vi.fn();
    subscribeCountry(listener);

    setCountry("USA");

    expect(getCountry()).toBe("USA");
    expect(listener).toHaveBeenCalledTimes(1);
    expect(storage._store[COUNTRY_STORAGE_KEY]).toBe("USA");
  });

  it("does not notify when the value is unchanged", () => {
    installWindow(fakeStorage());
    const listener = vi.fn();
    subscribeCountry(listener);

    setCountry(DEFAULT_COUNTRY);

    expect(listener).not.toHaveBeenCalled();
  });

  it("stops notifying after unsubscribe", () => {
    installWindow(fakeStorage());
    const listener = vi.fn();
    subscribeCountry(listener)();

    setCountry("USA");

    expect(listener).not.toHaveBeenCalled();
  });

  it("survives storage that throws, as private browsing does", () => {
    (globalThis as Record<string, unknown>).window = {
      localStorage: {
        getItem: () => { throw new Error("blocked"); },
        setItem: () => { throw new Error("blocked"); },
      },
      addEventListener: () => {},
      removeEventListener: () => {},
    };

    expect(() => setCountry("USA")).not.toThrow();
    expect(getCountry()).toBe("USA");
  });
});

describe("hydrateCountryFromStorage", () => {
  it("adopts a saved country and notifies", () => {
    installWindow(fakeStorage({ [COUNTRY_STORAGE_KEY]: "USA" }));
    const listener = vi.fn();
    subscribeCountry(listener);

    hydrateCountryFromStorage();

    expect(getCountry()).toBe("USA");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("ignores a corrupted saved value", () => {
    installWindow(fakeStorage({ [COUNTRY_STORAGE_KEY]: "ATLANTIS" }));

    hydrateCountryFromStorage();

    expect(getCountry()).toBe("INDIA");
  });

  it("is a no-op during server rendering", () => {
    expect(() => hydrateCountryFromStorage()).not.toThrow();
    expect(getCountry()).toBe("INDIA");
  });
});
