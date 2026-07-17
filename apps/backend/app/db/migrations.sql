CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    original_path TEXT,
    mime_type TEXT,
    status TEXT DEFAULT 'UPLOADED',
    complexity_score REAL,
    complexity_level TEXT,
    complexity_reasons TEXT,
    ocr_engine TEXT,
    processing_mode TEXT,
    page_count INTEGER DEFAULT 0,
    expected_fields TEXT,
    must_use_llm INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_pages (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    original_path TEXT,
    preprocessed_path TEXT,
    width INTEGER,
    height INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS ocr_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    raw_text TEXT,
    confidence REAL,
    word_count INTEGER,
    metadata_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS extraction_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    invoice_json TEXT NOT NULL,
    confidence_json TEXT,
    raw_llm_response TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    status TEXT NOT NULL,
    rule_checks_json TEXT,
    llm_checks_json TEXT,
    warnings_json TEXT,
    errors_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS final_outputs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    corrected_json TEXT NOT NULL,
    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS processing_logs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_document_pages_doc ON document_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_doc ON ocr_results(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_results_doc ON extraction_results(document_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_doc ON validation_results(document_id);
CREATE INDEX IF NOT EXISTS idx_final_outputs_doc ON final_outputs(document_id);
CREATE INDEX IF NOT EXISTS idx_processing_logs_doc ON processing_logs(document_id);
