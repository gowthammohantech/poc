export interface ConnectorProvider {
  provider: string;
  label: string;
  /** Whether this server has the credentials the provider needs. */
  configured: boolean;
  /** False for providers listed as coming soon. */
  enabled: boolean;
}

export type ConnectionStatus =
  | "PENDING"
  | "CONNECTED"
  | "NEEDS_REAUTH"
  | "ERROR"
  | "DISCONNECTED";

export interface ConnectorConnection {
  id: string;
  provider: string;
  account_email: string | null;
  status: ConnectionStatus;
  token_expires_at: string | null;
  scopes: string | null;
  filter_label: string | null;
  filter_label_name: string | null;
  filter_query: string | null;
  max_messages_per_sync: number | null;
  last_sync_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export type SyncRunStatus = "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED";

export interface ConnectorSyncRun {
  id: string;
  connection_id: string;
  status: SyncRunStatus;
  trigger: string;
  messages_scanned: number;
  /** Messages that carried at least one attachment — not the attachment count. */
  messages_with_attachments: number;
  attachments_found: number;
  documents_created: number;
  documents_processed: number;
  documents_failed: number;
  skipped_duplicates: number;
  skipped_unsupported: number;
  current_activity: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

/** Lifetime run counters for a connection, summed across every sync. */
export interface ConnectorSyncTotals {
  messages_scanned: number;
  messages_with_attachments: number;
  attachments_found: number;
  documents_created: number;
  documents_processed: number;
  documents_failed: number;
  skipped_duplicates: number;
  skipped_unsupported: number;
}

/** Where the invoices this connection produced have got to. */
export interface ConnectorInvoiceCounts {
  total: number;
  /** Still somewhere in the OCR/extraction pipeline. */
  in_progress: number;
  ready: number;
  needs_review: number;
  /** Extracted, but validation found problems in it. */
  invalid: number;
  /** Never got as far as an extraction. */
  failed: number;
}

/**
 * What a connection has pulled in, available without starting a sync.
 *
 * `totals` is history — what the mailbox syncs saw. `invoices` is the present
 * state of the documents those syncs created, which keeps changing after a run
 * has finished.
 */
export interface ConnectorStats {
  connection_id: string;
  runs: number;
  last_run: ConnectorSyncRun | null;
  totals: ConnectorSyncTotals;
  invoices: ConnectorInvoiceCounts;
}

export type SyncItemStatus =
  | "INGESTED"
  | "SKIPPED_DUPLICATE"
  | "SKIPPED_UNSUPPORTED"
  | "SKIPPED_INLINE"
  | "FAILED";

export interface ConnectorSyncItem {
  id: string;
  run_id: string;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  from_address: string | null;
  subject: string | null;
  received_at: string | null;
  document_id: string | null;
  status: SyncItemStatus;
  error_message: string | null;
}

/** A selectable mailbox folder — a Gmail label, an Outlook folder. */
export interface MailFolder {
  id: string;
  name: string;
}
