"use client";

import { Check, ChevronDown, Globe } from "lucide-react";

import { COUNTRIES, type Country } from "@/lib/country";
import { useCountry } from "./useCountry";

/**
 * The India / USA switch. Uses the app's existing dropdown idiom -- a native
 * <details> with an absolutely positioned panel, as on the review screen's
 * Export menu -- so it needs no outside-click handling.
 */
export default function CountrySelector({ className = "" }: { className?: string }) {
  const { country, setCountry } = useCountry();
  const active = COUNTRIES.find((c) => c.key === country);

  function choose(event: React.MouseEvent<HTMLButtonElement>, next: Country) {
    setCountry(next);
    // Unlike the Export menu, choosing here does not navigate, so the panel
    // would otherwise stay open over the page.
    event.currentTarget.closest("details")?.removeAttribute("open");
  }

  return (
    <details className={`relative ${className}`}>
      <summary
        className="list-none cursor-pointer flex items-center gap-2 text-sm text-slate-700 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-lg transition-colors"
        aria-label={`Document region: ${active?.label ?? country}`}
      >
        <Globe className="w-4 h-4 text-slate-500" />
        <span className="font-medium">{active?.label ?? country}</span>
        <ChevronDown className="w-4 h-4 text-slate-400" />
      </summary>

      <div className="absolute right-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
        {COUNTRIES.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={(e) => choose(e, option.key)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 transition-colors"
          >
            <span>
              {option.label}
              <span className="ml-2 text-xs text-slate-400">
                {option.key === "INDIA" ? "GST invoices" : "Orders & releases"}
              </span>
            </span>
            {option.key === country && <Check className="w-4 h-4 text-violet-600 shrink-0" />}
          </button>
        ))}
      </div>
    </details>
  );
}
