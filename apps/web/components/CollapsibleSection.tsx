"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

interface CollapsibleSectionProps {
  title: string;
  defaultOpen?: boolean;
  action?: React.ReactNode;
  children: React.ReactNode;
}

export default function CollapsibleSection({
  title,
  defaultOpen = false,
  action,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="bg-white rounded-lg border overflow-hidden">
      <div className="bg-[#2d3588]  flex items-center justify-between px-4 py-3">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 font-semibold text-white text-sm uppercase tracking-wide flex-1 text-left"
        >
          <ChevronDown className={` w-4 h-4 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`} />
          {title}
        </button>
        {action}
      </div>
      {open && <div className="px-4 pb-4 pt-1 border-t space-y-3">{children}</div>}
    </section>
  );
}
