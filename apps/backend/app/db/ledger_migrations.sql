CREATE TABLE IF NOT EXISTS ledger_entries (
    id TEXT PRIMARY KEY,
    entry_date TEXT NOT NULL,
    ledger_name TEXT,
    description TEXT NOT NULL,
    reference_number TEXT,
    amount REAL NOT NULL,
    entry_type TEXT NOT NULL, -- DEBIT | CREDIT
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brs_match_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    match_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE INDEX IF NOT EXISTS idx_ledger_entries_date ON ledger_entries(entry_date);
CREATE INDEX IF NOT EXISTS idx_brs_match_results_doc ON brs_match_results(document_id);
