"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useCountry } from "./useCountry";
import { Upload, FileText, LogOut, ChevronLeft, PanelLeftClose, Bot, ArrowLeftRight, Plug } from "lucide-react";

const INVOICE_NAV_ITEMS = [
  { href: "/agents/invoice-ocr", label: "Process Invoice", icon: Upload },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/connectors", label: "Connectors", icon: Plug },
];

const US_NAV_ITEMS = [
  { href: "/agents/invoice-ocr", label: "Process Document", icon: Upload },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/connectors", label: "Connectors", icon: Plug },
];

const BRS_NAV_ITEMS = [
  { href: "/agents/brs", label: "Process BRS", icon: Upload },
  { href: "/brs-documents", label: "BRS Documents", icon: FileText },
  { href: "/brs-matching", label: "Reconcile Accounts", icon: ArrowLeftRight },
];

const AGENT_NAVIGATION = {
  invoice: {
    title: "Invoice OCR Agent",
    iconContainerClass: "bg-violet-100",
    iconClass: "text-violet-600",
    activeClass: "bg-violet-50 text-violet-700 border border-violet-200",
    activeIconClass: "text-violet-600",
    items: INVOICE_NAV_ITEMS,
  },
  // The same routes as the invoice agent -- the country selector decides what
  // they render -- with wording that matches the documents being processed.
  invoiceUs: {
    title: "US Order & Release Agent",
    iconContainerClass: "bg-violet-100",
    iconClass: "text-violet-600",
    activeClass: "bg-violet-50 text-violet-700 border border-violet-200",
    activeIconClass: "text-violet-600",
    items: US_NAV_ITEMS,
  },
  brs: {
    title: "BRS Agent",
    iconContainerClass: "bg-emerald-100",
    iconClass: "text-emerald-600",
    activeClass: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    activeIconClass: "text-emerald-600",
    items: BRS_NAV_ITEMS,
  },
};

function cn(...classes: (string | false | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

interface Props {
  onCollapse?: () => void;
}

export default function Sidebar({ onCollapse }: Props) {
  const pathname = usePathname();
  const router = useRouter();
  const { country } = useCountry();
  const isBrs =
    pathname.startsWith("/agents/brs") ||
    pathname.startsWith("/brs-documents") ||
    pathname.startsWith("/brs-review") ||
    pathname.startsWith("/brs-matching");
  // A US review screen keeps the US nav even if the selector was flipped back,
  // so the sidebar matches the document on screen.
  const isUs = pathname.startsWith("/us-review") || country === "USA";
  const activeAgent = isBrs
    ? AGENT_NAVIGATION.brs
    : isUs
      ? AGENT_NAVIGATION.invoiceUs
      : AGENT_NAVIGATION.invoice;

  async function handleSignOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <aside className="flex flex-col w-60 min-h-screen bg-white border-r border-slate-200">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-slate-200 flex items-start justify-between gap-2">
        <div>
          <Image
            src="/elixir-logo.png"
            alt="Elixir Global"
            width={140}
            height={46}
            style={{ height: "auto" }}
            priority
          />
          <p className="text-[10px] text-violet-600 font-semibold tracking-widest uppercase mt-2">
            Agent Sandbox
          </p>
        </div>
        <button
          onClick={onCollapse}
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors flex-shrink-0"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4">
        {/* Back to agent hub */}
        <Link
          href="/"
          className="flex items-center gap-2 px-3 py-2 mb-3 rounded-lg text-xs text-slate-400 hover:text-slate-700 hover:bg-slate-50 transition-colors group"
        >
          <ChevronLeft className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform" />
          All Agents
        </Link>

        <div className="flex items-center gap-2 px-3 mb-2">
          <div className={cn("w-5 h-5 rounded-md flex items-center justify-center flex-shrink-0", activeAgent.iconContainerClass)}>
            <Bot className={cn("w-3 h-3", activeAgent.iconClass)} />
          </div>
          <span className="text-[11px] font-bold uppercase tracking-widest text-slate-500 truncate">
            {activeAgent.title}
          </span>
        </div>
        <div className="ml-3 pl-3 border-l border-slate-100 space-y-0.5">
          {activeAgent.items.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                  active
                    ? activeAgent.activeClass
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                )}
              >
                <Icon className={cn("w-4 h-4", active ? activeAgent.activeIconClass : "text-slate-400")} />
                {label}
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-3 py-4 border-t border-slate-200">
        <button
          onClick={handleSignOut}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
