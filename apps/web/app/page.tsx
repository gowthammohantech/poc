"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bot, FileSearch, ArrowRight, LogOut, Landmark } from "lucide-react";

interface Agent {
  id: string;
  name: string;
  description: string;
  href: string;
  icon: React.ElementType;
  color: string;
  badgeColor: string;
}

const AGENTS: Agent[] = [
  {
    id: "invoice-ocr",
    name: "Invoice OCR Agent",
    description:
      "Extracts structured data from invoice PDFs and images. Runs OCR, parses fields, validates math, and stores results in a local database.",
    href: "/agents/invoice-ocr",
    icon: FileSearch,
    color: "from-violet-500 to-indigo-600",
    badgeColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  {
    id: "bank-reconciliation",
    name: "Bank Reconciliation Agent",
    description:
      "Processes bank statements end-to-end: extracts transactions via OCR, parses them with an LLM, and runs 5 balance reconciliation checks.",
    href: "/agents/brs",
    icon: Landmark,
    color: "from-emerald-500 to-teal-600",
    badgeColor: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
];

const COMING_SOON = [
  { name: "Contract Review Agent", desc: "Extract clauses, obligations and risk flags from legal contracts." },
  { name: "Purchase Order Agent", desc: "Match POs to invoices and flag discrepancies automatically." },
];

export default function AgentHubPage() {
  const router = useRouter();

  async function handleSignOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between px-8 py-5 bg-white border-b border-slate-200">
        <div className="flex items-center gap-4">
          <Image
            src="/elixir-logo.png"
            alt="Elixir Global"
            width={130}
            height={42}
            style={{ height: "auto" }}
            priority
          />
          <span className="hidden sm:block text-[10px] font-bold uppercase tracking-widest text-violet-600 bg-violet-50 border border-violet-200 px-2 py-1 rounded-md">
            Agent Sandbox
          </span>
        </div>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </header>

      {/* Hero */}
      <div className="px-8 pt-12 pb-8 max-w-5xl mx-auto w-full">
        <div className="flex items-center gap-2 mb-3">
          <Bot className="w-5 h-5 text-violet-500" />
          <span className="text-xs font-semibold uppercase tracking-widest text-violet-500">Agents</span>
        </div>
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Agent Hub</h1>
        <p className="text-slate-500 text-sm max-w-lg">
          Select an agent to launch its workspace. Each agent runs an automated multi-step
          pipeline powered by Elixir Global.
        </p>
      </div>

      {/* Active agents */}
      <div className="px-8 pb-6 max-w-5xl mx-auto w-full">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Active</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {AGENTS.map((agent) => {
            const Icon = agent.icon;
            return (
              <Link
                key={agent.id}
                href={agent.href}
                className="group bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-violet-300 transition-all duration-200 flex flex-col gap-4"
              >
                <div className="flex items-start justify-between">
                  <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${agent.color} flex items-center justify-center shadow-sm`}>
                    <Icon className="w-5 h-5 text-white" />
                  </div>
                  <span className={`text-[10px] font-semibold border rounded-full px-2 py-0.5 ${agent.badgeColor}`}>
                    Active
                  </span>
                </div>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-900 mb-1 group-hover:text-violet-700 transition-colors">
                    {agent.name}
                  </p>
                  <p className="text-xs text-slate-500 leading-relaxed">{agent.description}</p>
                </div>
                <div className="flex items-center gap-1 text-xs font-semibold text-violet-600 group-hover:gap-2 transition-all">
                  Launch
                  <ArrowRight className="w-3.5 h-3.5" />
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Coming soon */}
      <div className="px-8 pb-12 max-w-5xl mx-auto w-full">
        <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Coming Soon</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {COMING_SOON.map((agent) => (
            <div
              key={agent.name}
              className="bg-white border border-dashed border-slate-200 rounded-2xl p-5 flex flex-col gap-3 opacity-60"
            >
              <div className="w-11 h-11 rounded-xl bg-slate-100 flex items-center justify-center">
                <Bot className="w-5 h-5 text-slate-300" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-500 mb-1">{agent.name}</p>
                <p className="text-xs text-slate-400 leading-relaxed">{agent.desc}</p>
              </div>
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Coming soon
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
