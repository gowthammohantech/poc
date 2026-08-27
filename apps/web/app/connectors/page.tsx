"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Check, Loader2, Mail, Plug, RefreshCw } from "lucide-react";
import {
  disconnectConnector,
  getConnectorFolders,
  getConnectorProviders,
  getConnectors,
  getSyncRun,
  startConnectorOAuth,
  startConnectorSync,
  updateConnectorFilters,
} from "@/lib/api";
import type {
  ConnectorConnection,
  ConnectorProvider,
  ConnectorSyncRun,
  MailFolder,
} from "@/types/connector";

const POLL_INTERVAL_MS = 2000;
// A running sync loads the backend heavily; tolerate a few dropped polls.
const MAX_POLL_FAILURES = 5;

function providerIcon(provider: string) {
  return provider === "GMAIL" || provider === "OUTLOOK" || provider === "FAKE" ? Mail : Plug;
}

function statusPill(status: string) {
  if (status === "CONNECTED") return "bg-green-50 text-green-700";
  if (status === "NEEDS_REAUTH" || status === "ERROR") return "bg-red-50 text-red-700";
  return "bg-gray-100 text-gray-600";
}

function ConnectorsPage() {
  const router = useRouter();
  const params = useSearchParams();

  const [providers, setProviders] = useState<ConnectorProvider[]>([]);
  const [connections, setConnections] = useState<ConnectorConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const refresh = useCallback(async () => {
    const [p, c] = await Promise.all([getConnectorProviders(), getConnectors()]);
    setProviders(p);
    setConnections(c);
  }, []);

  useEffect(() => {
    refresh()
      .catch((err) => setNotice({ kind: "error", text: describe(err) }))
      .finally(() => setLoading(false));
  }, [refresh]);

  // The provider sends the user back here after consent; the backend has
  // already stored the tokens by the time we see these.
  useEffect(() => {
    const connected = params.get("connected");
    const error = params.get("error");
    if (!connected && !error) return;
    setNotice(
      error
        ? { kind: "error", text: error }
        : { kind: "ok", text: `${connected} connected.` }
    );
    router.replace("/connectors");
  }, [params, router]);

  const connectionsByProvider = new Map(connections.map((c) => [c.provider, c]));

  async function handleConnect(provider: string) {
    try {
      const { authorization_url } = await startConnectorOAuth(provider);
      window.location.href = authorization_url;
    } catch (err) {
      setNotice({ kind: "error", text: describe(err) });
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 py-10 px-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Connectors</h1>
          <p className="mt-1 text-sm text-gray-600">
            Pull invoices straight out of a mailbox. Attachments are processed by the same
            OCR and extraction pipeline as manual uploads, and appear in{" "}
            <Link href="/documents" className="text-blue-600 hover:underline">Documents</Link>.
          </p>
        </div>

        {notice && (
          <div
            className={`mb-4 rounded-lg p-3 text-sm border ${
              notice.kind === "error"
                ? "bg-red-50 text-red-700 border-red-200"
                : "bg-green-50 text-green-700 border-green-200"
            }`}
          >
            {notice.text}
          </div>
        )}

        {loading ? (
          <p className="text-gray-500">Loading...</p>
        ) : (
          <div className="space-y-4">
            {providers.map((provider) => (
              <ProviderCard
                key={provider.provider}
                provider={provider}
                connection={connectionsByProvider.get(provider.provider)}
                onConnect={() => handleConnect(provider.provider)}
                onChanged={refresh}
                onError={(text) => setNotice({ kind: "error", text })}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

function ProviderCard({
  provider,
  connection,
  onConnect,
  onChanged,
  onError,
}: {
  provider: ConnectorProvider;
  connection?: ConnectorConnection;
  onConnect: () => void;
  onChanged: () => Promise<void>;
  onError: (text: string) => void;
}) {
  const Icon = providerIcon(provider.provider);
  const connected = connection?.status === "CONNECTED" || connection?.status === "NEEDS_REAUTH";

  return (
    <div className={`bg-white rounded-xl border p-5 ${provider.enabled ? "" : "opacity-60"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-violet-50 flex items-center justify-center flex-shrink-0">
            <Icon className="w-4 h-4 text-violet-600" />
          </div>
          <div>
            <p className="font-medium text-gray-900">{provider.label}</p>
            {connected ? (
              <p className="text-sm text-gray-600">{connection?.account_email}</p>
            ) : provider.enabled ? (
              <p className="text-sm text-gray-500">
                {provider.configured
                  ? "Not connected"
                  : "Not configured on this server — add its credentials to apps/backend/.env"}
              </p>
            ) : (
              <p className="text-sm text-gray-500">Coming soon</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {connection && (
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusPill(connection.status)}`}>
              {connection.status}
            </span>
          )}
          {provider.enabled && !connected && (
            <button
              onClick={onConnect}
              disabled={!provider.configured}
              className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
            >
              Connect
            </button>
          )}
        </div>
      </div>

      {connection?.status === "NEEDS_REAUTH" && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            <p>{connection.last_error || "This account needs to be authorised again."}</p>
            <button onClick={onConnect} className="mt-1 underline">Reconnect</button>
          </div>
        </div>
      )}

      {connected && connection && (
        <ConnectedPanel connection={connection} onChanged={onChanged} onError={onError} />
      )}
    </div>
  );
}

function ConnectedPanel({
  connection,
  onChanged,
  onError,
}: {
  connection: ConnectorConnection;
  onChanged: () => Promise<void>;
  onError: (text: string) => void;
}) {
  const [folders, setFolders] = useState<MailFolder[]>([]);
  const [label, setLabel] = useState(connection.filter_label ?? "");
  const [query, setQuery] = useState(connection.filter_query ?? "has:attachment");
  const [maxMessages, setMaxMessages] = useState(connection.max_messages_per_sync ?? 25);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [run, setRun] = useState<ConnectorSyncRun | null>(null);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getConnectorFolders(connection.id).then(setFolders).catch(() => setFolders([]));
  }, [connection.id]);

  // Stop polling if the panel goes away mid-sync; the run itself carries on
  // server-side, which is what we want.
  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      await updateConnectorFilters(connection.id, {
        filter_label: label || null,
        filter_label_name: folders.find((f) => f.id === label)?.name ?? null,
        filter_query: query,
        max_messages_per_sync: Number(maxMessages) || 25,
      });
      setSaved(true);
      await onChanged();
    } catch (err) {
      onError(describe(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleSync() {
    setStarting(true);
    try {
      const { run_id } = await startConnectorSync(connection.id);
      let consecutiveFailures = 0;
      pollRef.current = setInterval(async () => {
        try {
          const latest: ConnectorSyncRun = await getSyncRun(run_id);
          consecutiveFailures = 0;
          setRun(latest);
          if (latest.status !== "RUNNING") {
            if (pollRef.current) clearInterval(pollRef.current);
            await onChanged().catch(() => undefined);
          }
        } catch {
          consecutiveFailures += 1;
          if (consecutiveFailures >= MAX_POLL_FAILURES && pollRef.current) {
            clearInterval(pollRef.current);
            onError("Lost contact with the server; the sync may still be running.");
          }
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      onError(describe(err));
    } finally {
      setStarting(false);
    }
  }

  async function handleDisconnect() {
    try {
      await disconnectConnector(connection.id);
      await onChanged();
    } catch (err) {
      onError(describe(err));
    }
  }

  const syncing = run?.status === "RUNNING" || starting;

  return (
    <div className="mt-5 border-t pt-4 space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Folder / label</label>
          <select
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
          >
            <option value="">All mail</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>{folder.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Search query</label>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="has:attachment"
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Max messages</label>
          <input
            type="number"
            min={1}
            max={100}
            value={maxMessages}
            onChange={(e) => setMaxMessages(Number(e.target.value))}
            className="w-full border border-gray-300 rounded-lg px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={handleSync}
          disabled={syncing}
          className="inline-flex items-center gap-2 text-sm bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
        >
          {syncing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          {syncing ? "Syncing…" : "Sync now"}
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="text-sm border border-gray-300 text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
        >
          {saving ? "Saving…" : "Save filters"}
        </button>
        {saved && (
          <span className="inline-flex items-center gap-1 text-xs text-green-700">
            <Check className="w-3 h-3" /> Saved
          </span>
        )}
        <button
          onClick={handleDisconnect}
          className="text-sm text-red-600 px-3 py-1.5 rounded-lg hover:bg-red-50 transition-colors ml-auto"
        >
          Disconnect
        </button>
      </div>

      <p className="text-xs text-gray-400">
        {connection.last_sync_at
          ? `Last synced ${new Date(connection.last_sync_at).toLocaleString()}`
          : "Never synced"}
      </p>

      {run && <SyncProgress run={run} />}
    </div>
  );
}

function SyncProgress({ run }: { run: ConnectorSyncRun }) {
  const done =
    run.documents_processed + run.documents_failed + run.skipped_duplicates + run.skipped_unsupported;
  const total = Math.max(run.attachments_found, done);
  const pct = total ? Math.round((done / total) * 100) : 0;

  const tone =
    run.status === "FAILED" ? "border-red-200 bg-red-50"
    : run.status === "PARTIAL" ? "border-amber-200 bg-amber-50"
    : run.status === "COMPLETED" ? "border-green-200 bg-green-50"
    : "border-blue-200 bg-blue-50";

  return (
    <div className={`rounded-lg border p-3 text-sm ${tone}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium text-gray-800">
          {run.status === "RUNNING" ? run.current_activity || "Working…" : `Sync ${run.status.toLowerCase()}`}
        </span>
        <span className="text-xs text-gray-500">{done}/{total || "?"}</span>
      </div>

      {run.status === "RUNNING" && (
        <div className="h-1.5 bg-white rounded-full overflow-hidden mb-2">
          <div className="h-full bg-blue-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
        <span>{run.messages_scanned} scanned</span>
        <span>{run.attachments_found} attachment(s)</span>
        <span>{run.documents_processed} processed</span>
        {run.skipped_duplicates > 0 && <span>{run.skipped_duplicates} already seen</span>}
        {run.skipped_unsupported > 0 && <span>{run.skipped_unsupported} skipped</span>}
        {run.documents_failed > 0 && <span className="text-red-600">{run.documents_failed} failed</span>}
      </div>

      {run.error_message && <p className="mt-2 text-xs text-red-700">{run.error_message}</p>}

      {run.status !== "RUNNING" && run.documents_processed > 0 && (
        <Link href="/documents?source=CONNECTOR" className="mt-2 inline-block text-xs text-blue-600 hover:underline">
          View {run.documents_processed} new invoice(s) →
        </Link>
      )}
    </div>
  );
}

function describe(err: unknown): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const detail = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
    if (detail) return detail;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}

export default function ConnectorsPageWrapper() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-gray-50 py-10 px-6" />}>
      <ConnectorsPage />
    </Suspense>
  );
}
