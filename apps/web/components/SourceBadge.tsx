import { Mail, Plug, Terminal, Upload } from "lucide-react";
import type { Document, IngestionSource, SourceMetadata } from "@/types/invoice";

const PROVIDER_LABELS: Record<string, string> = {
  GMAIL: "Gmail",
  OUTLOOK: "Outlook",
  FAKE: "Sample Mailbox",
};

const STYLES: Record<IngestionSource, string> = {
  MANUAL: "bg-slate-100 text-slate-700",
  API: "bg-blue-50 text-blue-700",
  CONNECTOR: "bg-violet-50 text-violet-700",
};

const ICONS: Record<IngestionSource, typeof Mail> = {
  MANUAL: Upload,
  API: Terminal,
  CONNECTOR: Mail,
};

function parseMetadata(raw: string | null | undefined): SourceMetadata {
  if (!raw) return {};
  try {
    return JSON.parse(raw) as SourceMetadata;
  } catch {
    return {};
  }
}

/**
 * Where a document came from. Connector documents read as their provider
 * ("Gmail") rather than the generic source, since that is what the user
 * recognises; sender and subject go in the tooltip.
 */
export default function SourceBadge({ doc }: { doc: Document }) {
  const source: IngestionSource = doc.source ?? "MANUAL";
  const meta = parseMetadata(doc.source_metadata);

  let label: string = source === "MANUAL" ? "Manual" : source === "API" ? "API" : "Connector";
  let Icon = ICONS[source] ?? Upload;

  if (source === "CONNECTOR") {
    const provider = meta.provider?.toUpperCase();
    if (provider) {
      label = PROVIDER_LABELS[provider] ?? provider;
      if (provider === "OUTLOOK" || provider === "GMAIL") Icon = Mail;
      else Icon = Plug;
    }
  }

  const tooltip = [meta.from, meta.subject].filter(Boolean).join(" — ") || undefined;

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${STYLES[source] ?? STYLES.MANUAL}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}
