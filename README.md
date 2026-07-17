# Invoice OCR Platform

End-to-end invoice processing platform: PDF/image → OCR → structured JSON → human review → export.

## Stack

- **Frontend**: Next.js 15 + TypeScript + Tailwind (port 3000)
- **Backend**: FastAPI + Python 3.12 (port 8000)
- **AI Orchestration**: Mastra AI with `@mastra/core` (port 4111)
- **OCR**: Tesseract 5 → PaddleOCR → OpenAI Vision LLM (fallback chain)
- **Database**: SQLite (aiosqlite)
- **Storage**: Local filesystem (`storage/uploads/`)

## Setup

### 1. Set your OpenAI API key

Edit `.env` and `mastra-service/.env`:
```
OPENAI_API_KEY=sk-...
```

### 2. Start FastAPI (Terminal 1)

HEIC/HEIF uploads require the Pillow HEIF decoder (install once in the backend virtual environment):

```bash
cd apps/backend
.venv/bin/pip install pillow-heif
```

```bash
cd apps/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 3. Start Mastra service (Terminal 2)

```bash
cd mastra-service
npm run dev
# Mastra Studio: http://localhost:4111
```

### 4. Start Next.js (Terminal 3)

```bash
cd apps/web
npm run dev
# App: http://localhost:3000
```

## Usage

1. Open http://localhost:3000
2. Upload an invoice PDF or image
3. Wait for OCR + extraction to complete (~5-30 seconds depending on engine)
4. Review and correct extracted data on the review screen
5. Submit corrected invoice
6. Export as JSON, CSV, or Excel

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/documents/upload` | POST | Upload invoice |
| `/api/documents` | GET | List all documents |
| `/api/documents/{id}` | GET | Get document status |
| `/api/documents/{id}/pages` | GET | Get page list |
| `/api/documents/{id}/process` | POST | Run OCR + extraction + validation |
| `/api/documents/{id}/review` | GET | Get review data |
| `/api/documents/{id}/review/submit` | POST | Submit corrected data |
| `/api/documents/{id}/export/json` | GET | Export JSON |
| `/api/documents/{id}/export/csv` | GET | Export CSV |
| `/api/documents/{id}/export/excel` | GET | Export Excel |

## OCR Routing Logic

| Complexity Score | Engine |
|-----------------|--------|
| ≤ 40 (SIMPLE) | Tesseract |
| ≤ 75 (MEDIUM/HIGH) | PaddleOCR |
| > 75 (VERY_HIGH) | OpenAI Vision |
| `must_use_llm=true` | OpenAI Vision (always) |

Fallback chain: Tesseract → PaddleOCR → OpenAI Vision (triggered on low confidence).

## Document Status Flow

```
UPLOADED → SAVING → SAVED → CONVERTING → PREPROCESSING → 
COMPLEXITY_ANALYZED → ROUTING → ROUTED → OCR_RUNNING → 
EXTRACTING → EXTRACTED → VALIDATING → VALID|NEEDS_REVIEW|INVALID → COMPLETED
```

## Project Structure

```
apps/
  backend/           FastAPI + SQLite + OCR engines
    app/
      api/           HTTP route handlers
      services/      Business logic
      ocr_engines/   Tesseract + PaddleOCR
      db/            SQLite schema + connection
      schemas/       Pydantic models
  web/               Next.js frontend
    app/             Pages (upload, review, documents)
    components/      PagePreview, ConfidenceBadge
    lib/             API client
    types/           TypeScript interfaces
mastra-service/      Mastra AI agents + workflows
  src/mastra/
    agents/          4 agents (router, extractor, vision, validator)
    prompts/         System prompts
    schemas/         Zod invoice schema
    workflows/       invoiceProcessingWorkflow
```
