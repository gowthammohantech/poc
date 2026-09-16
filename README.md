# Invoice OCR Platform

End-to-end document processing platform: PDF/image → OCR → structured JSON → human review → export.

Two document regimes, chosen with the **country selector in the top right**:

- **India** — GST tax invoices (the original flow).
- **USA** — purchase orders (**SO**) and shipping authorizations (**SA**).

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
| `/api/documents/upload` | POST | Upload a document (`country` = `INDIA`\|`USA`) |
| `/api/documents` | GET | List all documents |
| `/api/documents/{id}` | GET | Get document status |
| `/api/documents/{id}/pages` | GET | Get page list |
| `/api/documents/{id}/process` | POST | Run OCR + extraction + validation |
| `/api/documents/{id}/review` | GET | Get review data |
| `/api/documents/{id}/review/submit` | POST | Submit corrected data |
| `/api/documents/{id}/export/json` | GET | Export JSON |
| `/api/documents/{id}/export/csv` | GET | Export CSV |
| `/api/documents/{id}/export/excel` | GET | Export Excel |
| `/api/connectors/providers` | GET | List mail providers |
| `/api/connectors` | GET | List connected accounts |
| `/api/connectors/{provider}/oauth/start` | POST | Begin the OAuth handshake |
| `/api/connectors/{provider}/oauth/callback` | GET | Provider redirect target |
| `/api/connectors/{id}/folders` | GET | Labels/folders to filter on |
| `/api/connectors/{id}/filters` | POST | Save the fetch filters |
| `/api/connectors/{id}/sync` | POST | Start a sync (returns immediately) |
| `/api/connectors/sync-runs/{run_id}` | GET | Sync progress |
| `/api/connectors/{id}/disconnect` | POST | Remove the account |

## Connectors (email ingestion)

Invoices can arrive by upload or be pulled from a mailbox. Every document records
where it came from — `MANUAL`, `API` or `CONNECTOR` — shown as a **Source** column
on `/documents`.

Attachments pulled from a mailbox go through exactly the same OCR and extraction
pipeline as manual uploads. A sync runs in the background and is reported by
polling, since processing a mailbox takes minutes.

Each connection carries a country — set from the country selector when it is
connected, and changeable afterwards under **Process as** on the connector card.
Everything that mailbox pulls is extracted under that regime and appears in
`/documents` with that country selected, so a mailbox of purchase orders is
connected as United States rather than India.

### Try it without a Google account

A **Sample Mailbox** provider is always listed at `/connectors` next to Gmail,
backed by the PDFs in `invoices/`. Connect it and press **Sync now** — this
exercises the whole path, including the duplicate and unsupported-attachment
skip rules.

### Enabling Gmail

One-time setup in [Google Cloud Console](https://console.cloud.google.com):

1. Create or select a project.
2. **APIs & Services → Library** → enable the **Gmail API**.
3. **OAuth consent screen** → External → fill in app name and contact email.
4. **Scopes** → add `https://www.googleapis.com/auth/gmail.readonly`
   (Google flags this as a restricted scope; that is expected).
5. **Test users** → add your own Gmail address. Required while in Testing mode.
6. **Credentials → Create credentials → OAuth client ID → Web application**, with
   the authorized redirect URI
   `http://localhost:8000/api/connectors/gmail/oauth/callback`. This must match
   exactly — a mismatch is the usual cause of `redirect_uri_mismatch`.
7. Copy the client ID and secret into `apps/backend/.env`.

Deployed, the redirect URI is the **backend's** public URL, not the frontend's —
`https://<backend-host>/api/connectors/gmail/oauth/callback` — and it has to be
added to the same Google client alongside the localhost one. Set
`GOOGLE_OAUTH_REDIRECT_URI`, `BACKEND_PUBLIC_URL` and `FRONTEND_URL` on the
backend service to match; `FRONTEND_URL` is where the callback sends the browser
back to, so a stale one lands the user on localhost after consent.

While the consent screen stays in **Testing**, Google expires refresh tokens after
seven days, so the connection will ask to be re-authorised about weekly. That is
Google's behaviour, not a fault in the app.

Connector settings live in `apps/backend/.env` — see `apps/backend/.env.example`.
`CONNECTOR_TOKEN_SECRET` (base64 of 32 random bytes) encrypts stored OAuth tokens;
without it they are held in plaintext and the server logs a warning on startup.

> There is no user model in this app, so a connected mailbox is shared by everyone
> who can sign in to the sandbox.

## US documents (SO and SA)

Select **United States** in the top-right selector and the upload page, the
documents list and the review screen all switch regime. The document's own
country is stored on the row, so a link always opens the right review screen
whatever the selector says.

Two document types, detected automatically:

| Type | Document | Shape |
|------|----------|-------|
| **SO** | Purchase order | Order header, three address blocks, priced line items (`quantity × unit cost = extended cost`) |
| **SA** | Shipping authorization | A parts × week demand schedule: `PO / Part Number / Description / Std Pack` against ~35 weekly buckets, each with a ship date and a delivery date |

The US path differs from the India one in three deliberate ways:

- **Vision always.** Both documents are dense tables where the meaning of a
  number is the column it sits in, and Tesseract reads a grid as one paragraph.
  Tesseract still runs, for the review screen's word boxes and as a second
  opinion on a digit.
- **Original page images**, not the preprocessed ones — binarising for
  Tesseract can thin out the hairline rules that carry the column alignment.
- **Year inference in code, not the model.** A release prints `22-Jun` with no
  year; the year is walked forward from the release date and rolls over at the
  December-to-January boundary.

A document the classifier cannot place is marked `UNKNOWN`, read as a purchase
order, and left in `NEEDS_REVIEW` — nothing about it is treated as fatal.

## OCR Routing Logic

Applies to the India flow. The US flow skips the router (see above).

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

The US flow inserts `CLASSIFYING → CLASSIFIED` between `OCR_RUNNING` and
`EXTRACTING`.

## Tests

```bash
cd apps/backend && pytest        # migrations, validation rules, pipeline, exports
cd apps/web && npm test          # vitest, lib/ only
cd apps/web && npx tsc --noEmit
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
      connectors/    Mail connectors (Gmail, sample mailbox)
  web/               Next.js frontend
    app/             Pages (upload, review, documents, connectors)
    components/      PagePreview, ConfidenceBadge, SourceBadge
    lib/             API client
    types/           TypeScript interfaces
mastra-service/      Mastra AI agents + workflows
  src/mastra/
    agents/          India invoice, BRS, and US (classifier, SO, SA, validator)
    prompts/         System prompts
    schemas/         Zod invoice schema
    workflows/       invoiceProcessingWorkflow
```



cd apps/backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000


cd mastra-service && npm run dev


cd apps/web && npm run dev
