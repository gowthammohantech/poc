CREATE TABLE IF NOT EXISTS connector_connections (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,                     -- 'GMAIL' | 'OUTLOOK' | 'FAKE'
    account_email TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',     -- PENDING|CONNECTED|NEEDS_REAUTH|ERROR|DISCONNECTED
    access_token TEXT,                          -- ciphertext
    refresh_token TEXT,                         -- ciphertext
    token_expires_at DATETIME,
    scopes TEXT,
    oauth_state TEXT,
    oauth_state_created_at DATETIME,
    filter_label TEXT,                          -- provider label ID, e.g. 'Label_7'
    filter_label_name TEXT,                     -- display name, for the UI
    filter_query TEXT DEFAULT 'has:attachment',
    max_messages_per_sync INTEGER DEFAULT 25,
    last_sync_at DATETIME,
    last_error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS connector_sync_runs (
    id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'RUNNING',     -- RUNNING|COMPLETED|PARTIAL|FAILED
    trigger TEXT NOT NULL DEFAULT 'MANUAL',
    messages_scanned INTEGER DEFAULT 0,
    messages_with_attachments INTEGER DEFAULT 0,
    attachments_found INTEGER DEFAULT 0,
    documents_created INTEGER DEFAULT 0,
    documents_processed INTEGER DEFAULT 0,
    documents_failed INTEGER DEFAULT 0,
    skipped_duplicates INTEGER DEFAULT 0,
    skipped_unsupported INTEGER DEFAULT 0,
    current_activity TEXT,
    error_message TEXT,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    FOREIGN KEY (connection_id) REFERENCES connector_connections(id)
);

-- Deliberately not unique: a FAILED item must be retryable on the next sync.
-- Correctness is guaranteed by ux_documents_source_ref on documents.
CREATE TABLE IF NOT EXISTS connector_sync_items (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    external_message_id TEXT NOT NULL,
    external_attachment_id TEXT,
    part_index INTEGER,
    filename TEXT,
    mime_type TEXT,
    size_bytes INTEGER,
    from_address TEXT,
    subject TEXT,
    received_at DATETIME,
    document_id TEXT,
    status TEXT NOT NULL,  -- INGESTED|SKIPPED_DUPLICATE|SKIPPED_UNSUPPORTED|SKIPPED_INLINE|FAILED
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES connector_sync_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_connector_runs_conn ON connector_sync_runs(connection_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_connector_items_run ON connector_sync_items(run_id);
CREATE INDEX IF NOT EXISTS idx_connector_items_dedupe
    ON connector_sync_items(connection_id, external_message_id, part_index);
