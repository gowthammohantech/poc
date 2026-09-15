"use client";

import { useSyncExternalStore } from "react";

import {
  getCountry,
  getServerCountry,
  setCountry,
  subscribeCountry,
  type Country,
} from "@/lib/country";

/** The selected document regime, kept in step across every mounted component. */
export function useCountry(): { country: Country; setCountry: (next: Country) => void } {
  const country = useSyncExternalStore(subscribeCountry, getCountry, getServerCountry);
  return { country, setCountry };
}
