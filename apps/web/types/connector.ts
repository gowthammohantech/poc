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
