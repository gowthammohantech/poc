# Runner Guide — Invoice OCR Platform

Step-by-step instructions to get the whole application running locally from a fresh clone.

The platform is three services that must all be running:

| Service | Tech | Port | Directory | Talks to |
|---|---|---|---|---|
| **Web** (UI) | Next.js 16 + React 19 | 3000 | `apps/web` | Backend (via `/api/backend` proxy) |
| **Backend** (API + OCR) | FastAPI + Python 3.12 | 8000 | `apps/backend` | Mastra, Tesseract, PaddleOCR, MongoDB |
| **Mastra** (AI agents) | Mastra + `@ai-sdk/openai` | 4111 | `mastra-service` | OpenAI API |

Request flow: Browser → Web (3000) → Backend (8000) → Mastra (4111) → OpenAI.

---

## 0. Prerequisites

Install these once on your machine.

### Required

| Tool | Version | Why |
|---|---|---|
| **Node.js** | 20+ (24 works) | Web + Mastra |
| **npm** | 10+ | Comes with Node |
| **Python** | **3.12 exactly** | Backend. PaddlePaddle does not publish wheels for 3.13/3.14 — newer Pythons will fail at `pip install`. |
| **Tesseract OCR** | 5.x | Local OCR engine (first in the fallback chain) |
| **Poppler** | any recent | `pdf2image` uses `pdftoppm` to render PDF pages |
| **OpenAI API key** | — | Used by Mastra agents (`gpt-4o`, `gpt-4o-mini`) for extraction, validation, and vision fallback |

### macOS (Homebrew)

```bash
brew install node python@3.12 tesseract poppler
```

Check what you got:

```bash
node --version          # v20+ or v24+
python3.12 --version    # Python 3.12.x
tesseract --version     # tesseract 5.x
pdftoppm -v             # pdftoppm version ...
```

> **Apple Silicon vs Intel:** the backend defaults to Homebrew's Apple Silicon paths
> (`/opt/homebrew/bin/tesseract`, `/opt/homebrew/share/tessdata`). On an Intel Mac, Homebrew
> installs to `/usr/local/...` — you'll set `TESSERACT_CMD` / `TESSDATA_PREFIX` in step 3 to match.
> Run `brew --prefix` to find out which one you have.

### Windows

1. Install Node.js 20+ from https://nodejs.org
2. Install Python 3.12 from https://www.python.org/downloads/ (tick "Add to PATH"). Verify with `py -0p`.
3. Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki (default path `C:\Program Files\Tesseract-OCR`)
4. Install Poppler from https://github.com/oschwartz10612/poppler-windows/releases — unzip somewhere like `C:\poppler` and note the `Library\bin` folder.

You will point the backend at these paths via env vars in step 3.

### Ubuntu / Debian

```bash
sudo apt-get update && sudo apt-get install -y \
  tesseract-ocr tesseract-ocr-eng poppler-utils libgl1 libglib2.0-0 libheif-dev
# Python 3.12 (if not the default): sudo apt-get install python3.12 python3.12-venv
```

---

## 1. Install Node dependencies (Web + Mastra)

The repo root is an npm workspace that covers `apps/web` and `mastra-service`. One command installs both:

```bash
cd /path/to/poc
npm install
```

This also installs `concurrently`, which the root `npm run dev` uses to start everything at once.

---

## 2. Set up the Python backend

Create a virtual environment **with Python 3.12** inside `apps/backend` and install requirements.
The dev script (`scripts/dev-backend.mjs`) looks for `.venv` in exactly this location.

### macOS / Linux

```bash
cd apps/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cd ../..
```

### Windows (PowerShell)

```powershell
cd apps\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
cd ..\..
```

> This install is large (PaddlePaddle, PaddleOCR, OpenCV, pandas, ~1–2 GB). Expect it to take several minutes.
> `pillow_heif` (for `.heic` uploads) is already in `requirements.txt`.

Sanity check that the app imports cleanly:

```bash
cd apps/backend && .venv/bin/python -c "import app.main; print('backend OK')" && cd ../..
# Windows: cd apps\backend; .\.venv\Scripts\python -c "import app.main; print('backend OK')"; cd ..\..
```

---

## 3. Create the environment files

None of these files are committed (`.gitignore`d). Create all three.

### 3a. `mastra-service/.env` — **required**

The only place the OpenAI key is needed. `mastra dev` loads this file automatically.

```env
OPENAI_API_KEY=sk-...
```

### 3b. `apps/web/.env.local` — **required**

The web app has a login gate. Without `ACCESS_TOKEN` you cannot get past `/login`.

```env
# Any string you choose — this is what you type on the login screen.
ACCESS_TOKEN=dev-token

# Where the Next.js server-side proxy forwards /api/backend/* requests.
FASTAPI_URL=http://localhost:8000
```

### 3c. `apps/backend/.env` — optional overrides

The backend works with no `.env` on an Apple Silicon Mac with Homebrew. Create this file only if you need to change a default. `app/main.py` loads it via `python-dotenv`.

```env
# --- OCR tool locations ---
# macOS Apple Silicon (defaults, no change needed):
#   TESSERACT_CMD=/opt/homebrew/bin/tesseract
#   TESSDATA_PREFIX=/opt/homebrew/share/tessdata
# macOS Intel:
#   TESSERACT_CMD=/usr/local/bin/tesseract
#   TESSDATA_PREFIX=/usr/local/share/tessdata
# Ubuntu:
#   TESSERACT_CMD=/usr/bin/tesseract
#   TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata
# Windows:
#   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
#   TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata
#   POPPLER_PATH=C:\poppler\Library\bin

# --- Services ---
# MASTRA_SERVICE_URL=http://localhost:4111
# FRONTEND_URL=http://localhost:3000      # extra CORS origin (localhost:3000 is already allowed)

# --- Storage ---
# MONGODB_URI=mongodb://localhost:27017   # connection string
# MONGO_DB_NAME=invoice_ocr               # database name
# STORAGE_BASE=storage/uploads            # uploaded files, relative to apps/backend
# PDF_RENDER_DPI=300
```

---

## 4. Run the application

### Option A — everything in one terminal (recommended)

From the repo root:

```bash
npm run dev
```

This runs `concurrently` with three processes:

- `npm run dev:backend` → `scripts/dev-backend.mjs` → `uvicorn app.main:app --reload --port 8000` using `apps/backend/.venv`
- `npm run dev:mastra` → `mastra dev` on port 4111
- `npm run dev:web` → `next dev` on port 3000

Press `Ctrl+C` once to stop all three.

> **Branch note:** on `main`, `dev:backend` runs `scripts/dev-backend.mjs`, which works on every OS.
> On `brsreconcile`, `dev:backend` is `cd apps\backend && .venv\Scripts\activate && ...` — **Windows only**.
> On macOS/Linux with that branch, `npm run dev` will start Web + Mastra but the backend exits immediately
> (`cd: appsbackend: No such file or directory`). Start the backend yourself with Option B, Terminal 1.

### Option B — three separate terminals

Useful when you want to read one service's logs in isolation.

**Terminal 1 — Backend (port 8000)**

```bash
cd apps/backend
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
# Windows: .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

or from the repo root: `npm run dev:backend`

**Terminal 2 — Mastra (port 4111)**

```bash
cd mastra-service
npm run dev
```

**Terminal 3 — Web (port 3000)**

```bash
cd apps/web
npm run dev
```

Start order doesn't strictly matter (they connect lazily), but Backend → Mastra → Web avoids errors on the first upload.

---

## 5. Verify everything is up

Run these in a fourth terminal (or a browser):

```bash
# Backend
curl http://localhost:8000/api/health
# → {"status":"ok","service":"invoice-ocr-backend"}

# Backend interactive API docs
open http://localhost:8000/docs

# Mastra Studio (agents + workflows playground)
open http://localhost:4111

# Web app
open http://localhost:3000
```

On first backend start the `invoice_ocr` database is created with its indexes, and `storage/uploads/` appears inside `apps/backend/`. The backend needs a reachable MongoDB; without one it fails on startup.

---

## 6. Use the app

1. Open http://localhost:3000 — you are redirected to `/login`.
2. Enter the `ACCESS_TOKEN` value from `apps/web/.env.local` (e.g. `dev-token`).
3. From the home page pick a workflow:
   - **Invoice OCR** → `/agents/invoice-ocr` — upload an invoice PDF / image / HEIC
   - **Bank Reconciliation (BRS)** → `/agents/brs` — upload a bank statement
   - **Ledger** → `/ledger`
4. Sample files to try are in the `invoices/` folder (PDFs and `.heic` photos).
5. Wait for processing (5–30 s; first PaddleOCR run also downloads its models, which can take a minute or two).
6. Review / correct extracted fields at `/review/<id>` (or `/brs-review/<id>`), then submit.
7. Export from `/documents` (or `/brs-documents`) as JSON, CSV, or Excel.

### How a document is routed

| Complexity score | Engine |
|---|---|
| ≤ 40 | Tesseract (local) |
| 41–75 | PaddleOCR (local) |
| > 75, or "must use LLM" ticked | OpenAI Vision via Mastra |

Low confidence at any local stage falls through to the next engine, ending at OpenAI Vision.

---

## 7. Run the backend tests

```bash
cd apps/backend
.venv/bin/python -m pytest tests -v
# Windows: .\.venv\Scripts\python -m pytest tests -v
```

Tests use `pytest` (installed with requirements) and don't need any service running.

---

## 8. Production build (optional)

**Mastra**

```bash
cd mastra-service
npm run build      # → .mastra/output/
npm run start      # node .mastra/output/index.mjs (port 4111)
```

**Web**

```bash
cd apps/web
npm run build
npm run start      # port 3000
```

**Backend** — run uvicorn without `--reload`:

```bash
cd apps/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Docker** — each service has its own `Dockerfile` (`apps/backend`, `apps/web`, `mastra-service`); `railway.json` files exist for Railway deploys. The backend image bundles Tesseract + Poppler, reads `MONGODB_URI` from the environment, and keeps uploads under `STORAGE_BASE=/app/data/...`, so mount a volume there.

---

## 9. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `cd: appsbackend: No such file or directory` from `npm run dev` | You're on a branch whose `dev:backend` script is Windows-only. Start the backend manually (step 4, Option B). |
| `Backend virtualenv Python is not runnable` from `npm run dev` | `apps/backend/.venv` is missing or built against a Python that was removed. Redo step 2. |
| `pip install` fails on `paddlepaddle` / `paddleocr` | You're on Python 3.13+/3.14. Recreate the venv with `python3.12` (step 2). |
| `TesseractNotFoundError` / `tesseract is not installed` | Tesseract isn't on the default path. Set `TESSERACT_CMD` and `TESSDATA_PREFIX` in `apps/backend/.env` (step 3c). |
| `pdf2image.exceptions.PDFInfoNotInstalledError` | Poppler missing. `brew install poppler` / `apt install poppler-utils`, or set `POPPLER_PATH` on Windows. |
| Stuck on `/login` / "Invalid access token" | `ACCESS_TOKEN` not set in `apps/web/.env.local`, or you typed something else. Restart `next dev` after editing `.env.local`. |
| Uploads return 502/`ECONNREFUSED` in the web console | Backend isn't running on 8000, or `FASTAPI_URL` points elsewhere. |
| Backend logs `Connection refused ... :4111` | Mastra isn't running. Start it (`npm run dev:mastra`). |
| Mastra logs `401` / `Incorrect API key` | Bad or missing `OPENAI_API_KEY` in `mastra-service/.env`. |
| `.heic` upload rejected | `pillow_heif` failed to import — `brew install libheif` (macOS) or `apt install libheif-dev`, then reinstall requirements. |
| Port already in use | `lsof -i :3000` / `:8000` / `:4111` and kill the old process. |
| Want a clean slate | Stop services, then drop the `invoice_ocr` database and delete `apps/backend/storage/`. Both are recreated on next start. |

---

## 10. Deploy

The repo is set up for **Railway**: every service has a `Dockerfile`, and `apps/web/railway.json` +
`mastra-service/railway.json` carry dashboard-exported settings. Check the Railway dashboard first —
if the project already exists, deploying is just `git push` to the connected branch.

### Railway — from scratch

**1. Create the project.** Railway → New Project → Deploy from GitHub → `gowthammohantech/poc`.
Add the same repo **three times** as separate services and set each one's Root Directory.

| Service | Root Directory | Build | Start | Port |
|---|---|---|---|---|
| `backend` | `apps/backend` | Dockerfile (auto-detected) | from Dockerfile (`uvicorn ... --port 8000`) | 8000 |
| `mastra` | `mastra-service` | Dockerfile via `railway.json` | `npm run start` | 4111 |
| `web` | `apps/web` | Dockerfile via `railway.json` | `npm run start` | 3000 |

**2. Add a Volume to `backend`** mounted at **`/app/data`**. The database is remote now, but uploaded
originals and page renders still live on disk and the records only hold paths to them, so without a volume a
redeploy leaves documents pointing at files that are gone. The Dockerfile already sets
`STORAGE_BASE=/app/data/storage/uploads`. Keep `backend` at **1 replica** — a Railway volume cannot be shared
across instances, and the OAuth refresh lock is per-process.

Set **`MONGODB_URI`** (and optionally `MONGO_DB_NAME`) on the backend service, plus
**`CONNECTOR_TOKEN_SECRET`** — without it Gmail OAuth tokens are stored as plaintext, which now means
plaintext in a hosted database.

**3. Environment variables.** Use Railway's private network so backend and Mastra are never public.

`mastra`
```env
OPENAI_API_KEY=sk-...
PORT=4111
```

`backend`
```env
MASTRA_SERVICE_URL=http://${{mastra.RAILWAY_PRIVATE_DOMAIN}}:4111
```

`web`
```env
ACCESS_TOKEN=<strong secret — this is the login password>
FASTAPI_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000
NODE_ENV=production
```

**4. Networking.** Only `web` gets a public domain (Settings → Networking → Generate Domain).
Leave `backend` and `mastra` private: the browser never calls them directly — the Next.js
`/api/backend/*` route handler proxies server-side. The session cookie is `secure` in production,
so HTTPS is required (Railway provides it).

**5. Deploy order:** mastra → backend → web. Then verify:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://<web-domain>/login   # 200
# Log in with ACCESS_TOKEN, upload a file from invoices/
```

Later deploys: push to the branch. Each service's `watchPatterns` rebuilds only what changed.

### Before going live

- **Backend image is big.** PaddlePaddle + OpenCV push it past 2 GB; first build takes 10–15 min.
  PaddleOCR downloads its models on first request into `~/.paddlex` (not on the volume), so the
  first OCR after every redeploy is slow.
- **Mastra has no persistent storage** ("falling back to an in-memory store" warning). Fine here —
  agent calls are stateless — but Studio traces vanish on restart.
- **Stale `TESSDATA_PREFIX` in the backend Dockerfile** (`.../4.00/tessdata`) is harmless:
  `tesseract_engine.py` ignores a path that doesn't exist and Tesseract falls back to its default.
- **Auth is one shared token** in a cookie. Fine for a demo/sandbox, not multi-user.

### Alternatives

- **Vercel for the web only** — `apps/web/vercel.json` exists. Root Directory `apps/web`, same env
  vars, but `FASTAPI_URL` must be a **public** backend URL (Vercel can't reach Railway's private
  network). Backend and Mastra still need Railway or another Docker host.
- **Single VPS with Docker** — build the three Dockerfiles, run them on one Docker network with the
  same env vars, put Caddy/nginx in front of `web`.

---

## Quick reference

```bash
# One-time setup
npm install
cd apps/backend && python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt && cd ../..
echo "OPENAI_API_KEY=sk-..." > mastra-service/.env
printf "ACCESS_TOKEN=dev-token\nFASTAPI_URL=http://localhost:8000\n" > apps/web/.env.local

# Every time
npm run dev
# → http://localhost:3000  (login with ACCESS_TOKEN)
```
