"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";

const PAGE_TITLES: [string, string][] = [
  ["/agents/invoice-ocr", "Process Invoice"],
  ["/documents", "Documents"],
  ["/review", "Invoice Review"],
  ["/brs-matching", "Bank Reconciliation — Matching"],
];

interface Props {
  onToggle: () => void;
  sidebarOpen: boolean;
}

export default function TopBar({ onToggle, sidebarOpen }: Props) {
  const pathname = usePathname();
  const title =
    PAGE_TITLES.find(([k]) => pathname === k || pathname.startsWith(k + "/"))?.[1] ??
    "Elixir Sandbox";

  return (
    <header className="flex items-center gap-3 px-4 h-14 bg-white border-b border-slate-200 flex-shrink-0">
      <button
        onClick={onToggle}
        aria-label="Toggle sidebar"
        className="p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors"
      >
        {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>
      <span className="text-sm font-medium text-slate-700">{title}</span>
    </header>
  );
}
