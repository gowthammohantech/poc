CREATE TABLE IF NOT EXISTS brs_documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_path TEXT,
    mime_type TEXT,
    status TEXT DEFAULT 'UPLOADED',
    page_count INTEGER DEFAULT 0,
    processing_mode TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brs_document_pages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    original_path TEXT,
    preprocessed_path TEXT,
    width INTEGER,
    height INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE TABLE IF NOT EXISTS brs_extraction_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    brs_json TEXT NOT NULL,
    confidence_json TEXT,
    raw_llm_response TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE TABLE IF NOT EXISTS brs_validation_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,
    rule_checks_json TEXT,
    llm_checks_json TEXT,
    warnings_json TEXT,
    errors_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE TABLE IF NOT EXISTS brs_final_outputs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    corrected_json TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE TABLE IF NOT EXISTS brs_processing_logs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES brs_documents(id)
);

CREATE INDEX IF NOT EXISTS idx_brs_documents_status ON brs_documents(status);
CREATE INDEX IF NOT EXISTS idx_brs_pages_doc ON brs_document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_brs_extraction_doc ON brs_extraction_results(document_id);
CREATE INDEX IF NOT EXISTS idx_brs_validation_doc ON brs_validation_results(document_id);
CREATE INDEX IF NOT EXISTS idx_brs_final_outputs_doc ON brs_final_outputs(document_id);
CREATE INDEX IF NOT EXISTS idx_brs_processing_logs_doc ON brs_processing_logs(document_id);
