"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isFullscreen = pathname === "/login" || pathname === "/";
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("sidebar_open");
    if (saved !== null) setSidebarOpen(saved === "true");
  }, []);

  function toggle() {
    setSidebarOpen((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_open", String(next));
      return next;
    });
  }

  if (isFullscreen) return <>{children}</>;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-10 lg:hidden"
          onClick={toggle}
        />
      )}

      {/* Sidebar */}
      <div
        className={`flex-shrink-0 transition-all duration-200 z-20 overflow-hidden ${
          sidebarOpen ? "w-60" : "w-0"
        }`}
      >
        <Sidebar onCollapse={toggle} />
      </div>

      {/* Floating expand tab, shown only when the sidebar is fully collapsed */}
      {!sidebarOpen && (
        <button
          onClick={toggle}
          title="Expand sidebar"
          aria-label="Expand sidebar"
          className="fixed left-0 top-1/2 -translate-y-1/2 z-20 w-5 h-12 rounded-r-lg bg-white border border-l-0 border-slate-200 text-slate-400 hover:text-slate-700 hover:bg-slate-50 flex items-center justify-center transition-colors"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      )}

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopBar onToggle={toggle} sidebarOpen={sidebarOpen} />
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
