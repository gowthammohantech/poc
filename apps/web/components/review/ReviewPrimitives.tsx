"use client";

/**
 * Pieces shared by the India invoice review screen and the US document one.
 *
 * Lifted verbatim out of app/review/[id]/page.tsx when the US screen was added,
 * so the two stay visually identical. The class strings are copied exactly,
 * quirks included -- adjusting one here shifts every review page in the app.
 */

import { ChevronLeft, ChevronRight } from "lucide-react";

export function NavArrow({
  side,
  disabled,
  onClick,
  label,
}: {
  side: "left" | "right";
  disabled: boolean;
  onClick: () => void;
  label: string;
}) {
  const Icon = side === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`fixed ${side === "left" ? "left-2" : "right-2"} top-1/2 -translate-y-1/2 z-30 h-10 w-10 flex items-center justify-center rounded-full border border-gray-300 bg-white/90 text-gray-600 shadow-sm backdrop-blur transition-colors hover:bg-white hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-white/90`}
    >
      <Icon className="w-5 h-5" />
    </button>
  );
}

export const inputCls = "w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500";
export const tdInputCls = "w-full border border-gray-200 rounded px-1.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400 min-w-[60px]";

export function Field({
  label,
  children,
  badge,
  isError,
  colSpan,
}: {
  label: string;
  children: React.ReactNode;
  badge?: React.ReactNode;
  isError?: boolean;
  colSpan?: boolean;
}) {
  return (
    <div className={colSpan ? "col-span-2" : ""}>
      <label className={`block text-xs font-medium mb-1 flex items-center gap-1 ${isError ? "text-red-600" : "text-gray-600"}`}>
        {label} {badge}
      </label>
      {children}
      {isError && <p className="text-xs text-red-500 mt-0.5">Validation error</p>}
    </div>
  );
}
