# Prompt for Claude Code: 2-Way / 3-Way Reconciliation Matching Module

## Context

This is an existing accounting/finance automation app. It already has:
- An agent that extracts data from uploaded bank statements.
- A **"Process BRS"** page where the user uploads a bank statement, which the agent parses into structured transactions (date, description, debit/credit, amount, reference, etc.).

I now want to add a new module on top of this: **2-way and 3-way reconciliation matching**, with its own landing page. Before writing any code, inspect the existing codebase (framework, folder structure, component library, styling approach — Tailwind/CSS modules/styled-components, state management, API layer, file upload handling for the bank statement feature) and follow the same conventions exactly. Reuse existing components (buttons, cards, tables, modals, upload widgets, color tokens, spacing scale) instead of introducing new ones, so this page feels native to the app, not bolted on.

## Objective

Build a new landing page for **Bank Reconciliation Matching** that lets the user reconcile:

1. **Bank Statement** (already uploaded/extracted via the existing Process BRS flow)
2. **Chart of Accounts (COA)** — uploaded via Excel
3. **Receipt / Payment ledger data** (Sales Receipts + Purchase Payments) — uploaded via Excel/manual entry, or (in future) pulled from a connected database

The page should support both:
- **2-way matching**: Bank Statement ↔ Ledger (Receipt/Payment)
- **3-way matching**: Bank Statement ↔ COA ↔ Ledger (Receipt/Payment)

## Data Inputs

### 1. Chart of Accounts (COA) — Excel upload
Expected columns (confirm actual headers by inspecting a sample file if the user provides one, otherwise assume):
- Account Code
- Account Name
- Account Type (Asset/Liability/Income/Expense/Bank/Cash etc.)
- Parent Group (optional)

### 2. Purchase & Sales Ledger — Excel upload or manual table entry
Format (as provided by the user):

| Transaction Type | Invoice No | Ledger Date | Ledger Voucher | Ledger Amount |
|---|---|---|---|---|
| Sales Receipt | SI-1001 | 01-Jan-26 | RV-101 | 25,000 |
| Purchase Payment | PI-2005 | 03-Jan-26 | PV-205 | 18,500 |
| Sales Receipt | SI-1010 | 05-Jan-26 | RV-108 | 12,000 |
| Purchase Payment | PI-2012 | 10-Jan-26 | PV-220 | 20,000 |

- `Transaction Type` is an enum: `Sales Receipt` | `Purchase Payment` (leave room to extend to `Sales Invoice` / `Purchase Invoice` later).
- Support uploading this via Excel (parse into a table, validate column headers, show inline errors for bad rows).
- Also support **manual add/edit** of rows in a table UI (add row, edit cell, delete row) as an alternative to uploading a file.
- Add a **"Connect Database"** button next to the upload option. For now this should be a **non-functional placeholder** (disabled or shows a "Coming soon" tooltip/modal on click) — do not build real DB connectivity yet. Just leave a clear extension point (e.g., a stubbed handler `onConnectDatabase()`) so it can be wired up later to push Receipt / Payment / Sales Invoice / Purchase Invoice records from the user's own database/table.

### 3. Bank Statement
Already available from the existing Process BRS extraction — reuse that data/state; don't rebuild the upload flow. If the extracted data isn't easily accessible as shared state, add a lightweight way to pull the last processed statement's transactions into this new module.

## Matching Engine

Build a matching function (pure, testable, separate from UI) that takes the three datasets and produces a reconciliation result per bank transaction:

- **Match keys/heuristics** (in priority order):
  1. Voucher/reference number match (Bank ref ↔ Ledger Voucher, and Ledger Voucher ↔ COA reference if applicable for 3-way)
  2. Exact amount match
  3. Date match within a configurable tolerance window (e.g., ±3 days), since bank clearing dates often lag ledger dates
  4. Transaction type/direction consistency (credit in bank ↔ Sales Receipt; debit in bank ↔ Purchase Payment)
- **Match status per transaction**: `Matched` (all criteria hit), `Partially Matched` (amount matches but date/reference doesn't, or vice versa), `Unmatched`.
- Compute a simple confidence score (e.g., weighted sum of matched criteria) to sort/filter results.
- For **3-way matching**, additionally validate the ledger entry maps to a valid COA account (e.g., the ledger voucher's account code exists in COA and is of an appropriate type — Bank/Cash for receipts/payments).
- Design this matching logic as a swappable module so the "2-way" vs "3-way" toggle simply changes which datasets are required/used, without duplicating logic.

## UI/UX Requirements

Design a **BRS Matching Landing Page**, styled consistently with the existing Process BRS page (same header/nav pattern, card styles, colors, typography, spacing). Suggested structure:

### A. Page header
- Title: "Bank Reconciliation — Matching"
- A toggle/segmented control: **2-Way Matching** | **3-Way Matching** (switching this changes which upload sections are required)

### B. Setup / Upload section (step-based or accordion-style cards)
1. **Bank Statement** — show status card indicating it's already loaded from Process BRS (with a link/button to go re-process if needed), showing transaction count and date range.
2. **Chart of Accounts (COA)** — Excel upload widget (drag-and-drop + browse), show parsed preview table, validation errors if headers don't match. Only shown/required when 3-Way mode is selected.
3. **Receipt / Payment Ledger** — two options side-by-side:
   - "Upload Excel" (drag-and-drop, same style as COA upload)
   - "Connect Database" button (disabled/placeholder, tooltip "Coming soon")
   - Below both: an editable table showing whatever data is loaded (from upload or manual entry), with an "Add Row" button for manual entries.

### C. Run Matching
- A prominent "Run Matching" button (disabled until required inputs are present for the selected mode).
- Loading state while matching runs.

### D. Results Dashboard
- Summary cards at top: Total Bank Transactions, Matched, Partially Matched, Unmatched, Match %.
- A results table with filters (status, transaction type, date range) and search, showing bank transaction alongside its matched ledger entry (and COA account for 3-way), with a color-coded status badge (green/amber/red).
- Row-level detail view (drawer or modal) showing side-by-side comparison of the bank line vs. ledger line (vs. COA line for 3-way), highlighting which fields matched/mismatched.
- Manual override actions: "Confirm Match", "Reject Match", "Manually Match to..." (opens a picker of unmatched ledger entries).
- "Export Reconciliation Report" button (Excel/PDF, matching whatever export pattern the existing app uses elsewhere).

## Acceptance Criteria
- New page follows existing app's visual language exactly (verify by comparing against the Process BRS page components/styles before finalizing).
- COA and Ledger data can be uploaded via Excel with validation and preview.
- Ledger data can also be added/edited manually in-table.
- "Connect Database" is visibly present but clearly a placeholder for future work — no broken promises to the user (e.g., no fake success states).
- 2-way and 3-way matching both work end-to-end using the existing Process BRS bank statement data.
- Matching logic is isolated in its own module/function with clear inputs/outputs so it can be unit tested and later replaced with a smarter algorithm (e.g., fuzzy matching, ML-based) without touching the UI.
- Results view clearly communicates match status, confidence, and lets the user manually correct mismatches.

## Out of Scope (for this pass)
- Actual live database connectivity (just the UI placeholder/button).
- Sales Invoice / Purchase Invoice matching (structure the data model so these can be added later, but don't build full support now).