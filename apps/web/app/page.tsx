"use client";

import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";

function SignOutButton() {
  const router = useRouter();

  const handleSignOut = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  };

  return (
    <button
      onClick={handleSignOut}
      className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 transition-colors"
    >
      <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
      </svg>
      Sign out
    </button>
  );
}

interface AgentCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  iconBg: string;
  href?: string;
  active?: boolean;
}

function AgentCard({ title, description, icon, iconBg, href, active = false }: AgentCardProps) {
  if (!active) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6 flex flex-col gap-3 opacity-50 select-none">
        <div className={`w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center`}>
          {icon}
        </div>
        <div>
          <h3 className="font-semibold text-gray-700">{title}</h3>
          <p className="text-sm text-gray-400 mt-1">{description}</p>
        </div>
        <span className="mt-auto text-xs font-semibold text-gray-400 uppercase tracking-widest">
          Coming Soon
        </span>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center`}>
          {icon}
        </div>
        <span className="text-xs font-semibold text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
          Active
        </span>
      </div>
      <div>
        <h3 className="font-semibold text-gray-900">{title}</h3>
        <p className="text-sm text-gray-500 mt-1">{description}</p>
      </div>
      {href && (
        <Link
          href={href}
          className="mt-auto inline-flex items-center gap-1 text-sm font-medium text-purple-600 hover:text-purple-700"
        >
          Launch →
        </Link>
      )}
    </div>
  );
}

export default function AgentHubPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <nav className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Image src="/elixir-logo.png" alt="Elixir" width={64} height={64} />
          {/* <span className="text-base font-bold text-gray-900">Elixir</span> */}
          <span className="text-xs font-semibold tracking-widest text-purple-600 bg-purple-100 px-2.5 py-0.5 rounded-full uppercase">
            Agent Sandbox
          </span>
        </div>
        <SignOutButton />
      </nav>

      {/* Main content */}
      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="mb-8">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
            Agents
          </p>
          <h1 className="text-3xl font-bold text-gray-900">Agent Hub</h1>
          <p className="text-gray-500 mt-2">
            Select an agent to launch its workspace. Each agent runs an automated multi-step pipeline powered by Elixir Global.
          </p>
        </div>

        {/* Active agents */}
        <section className="mb-10">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Active</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <AgentCard
              active
              title="Invoice OCR Agent"
              description="Extracts structured data from invoice PDFs and images. Runs OCR, parses fields, validates math, and stores results in a local database."
              href="/agents/invoice-ocr"
              iconBg="bg-purple-100"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              }
            />
            <AgentCard
              active
              title="Bank Reconciliation Agent"
              description="Processes bank statements end-to-end: extracts transactions via OCR, parses them with an LLM, and runs 5 balance reconciliation checks."
              href="#"
              iconBg="bg-green-100"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
                </svg>
              }
            />
          </div>
        </section>

        {/* Coming soon */}
        <section>
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-4">Coming Soon</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <AgentCard
              title="Contract Review Agent"
              description="Extract clauses, obligations and risk flags from legal contracts."
              iconBg="bg-gray-100"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              }
            />
            <AgentCard
              title="Purchase Order Agent"
              description="Match POs to invoices and flag discrepancies automatically."
              iconBg="bg-gray-100"
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                </svg>
              }
            />
          </div>
        </section>
      </main>
    </div>
  );
}
