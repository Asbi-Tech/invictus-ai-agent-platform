# Invictus Deals Onboarding

**Invictus Deals Onboarding Platform** — automatically ingests, classifies, and analyses investment documents from Google Drive, surfaces the latest version of each document type per deal, and extracts structured deal fields using an external RAG pipeline.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Why This Is Production-Grade](#why-this-is-production-grade)
- [API Endpoints](#api-endpoints)
- [Document Types](#document-types)
- [Deal Fields](#deal-fields)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the Worker](#running-the-worker)
- [Database Migrations](#database-migrations)
- [Deployment (Railway)](#deployment-railway)

---

## Overview

Invictus Deals Onboarding connects to a user's Google Drive, runs a nightly worker that scans for new investment documents, and processes them through a multi-stage AI pipeline:

1. **Ingestion** — detects new files by Drive file ID (never reprocesses), downloads in parallel
2. **Classification** — batches up to 30 docs per `gpt-4o-mini` call to classify type, extract deal name, date, and summary
3. **Deal resolution** — fuzzy-matches document folder paths to deal records using `rapidfuzz`
4. **Version management** — automatically marks older versions of the same document type per deal as superseded
5. **Vectorization** — sends the latest document per type to an external ingestion API (Invitus AI Insights) for RAG indexing
6. **AI analysis** — calls the Analytical endpoint to determine `investment_type`, `deal_status`, and `deal_reason`
7. **Field extraction** — calls the ExtractFields endpoint to populate 13–16 structured deal fields (tailored per investment type: Fund, Direct, or Co-Investment)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Google Drive                            │
│              (user's investment document folder)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Drive API v3
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Nightly Worker                             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Drive Ingest│  │ Batch LLM    │  │   Deal Resolver      │  │
│  │  (parallel   │→ │ Classifier   │→ │   (fuzzy match +     │  │
│  │   download)  │  │ gpt-4o-mini  │  │    folder heuristic) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                ↓                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   PostgreSQL                            │    │
│  │  users · documents · deals · deal_fields                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                            ↓                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Vectorizer Pipeline (per deal)              │   │
│  │  Stage 1: Create ingestion job                           │   │
│  │  Stage 2: Upload docs to SAS URLs (parallel)             │   │
│  │  Stage 3: Confirm upload                                 │   │
│  │  Stage 4: Poll until COMPLETED (25 min cap, backoff)     │   │
│  │  Stage 5: Persist vectorizer_doc_id                      │   │
│  │  Stage 6: Analytical → investment_type + deal_outcome    │   │
│  │  Stage 7: ExtractFields → 13–16 structured deal fields   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                             │
│         Rate-limited REST API · JWT auth · CORS                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   React + Vite Frontend                         │
│       Deal grid · Document slots · Structured field display     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
invictus-deals-onboarding/
├── frontend/                    # React + Vite + Tailwind dashboard
│   ├── src/
│   │   ├── components/          # DocumentCard, Hero, Navbar, etc.
│   │   ├── pages/               # Index, DealDetail, NotFound
│   │   └── lib/api.ts           # Typed API client
│   └── package.json
└── server/
    ├── app/
    │   ├── config.py            # Pydantic settings with startup validation
    │   ├── database.py          # SQLAlchemy engine (pool_recycle, TCP keepalives)
    │   ├── main.py              # FastAPI app, CORS, rate limiting, body size guard
    │   ├── models/
    │   │   ├── user.py          # User (OAuth tokens encrypted at rest)
    │   │   ├── document.py      # Document (versioning, vectorizer_doc_id)
    │   │   ├── deal.py          # Deal (investment_type, deal_status, deal_reason)
    │   │   └── deal_field.py    # DealField (structured extracted fields)
    │   ├── routes/
    │   │   ├── auth_routes.py   # Google OAuth 2.0 flow + JWT issuance
    │   │   ├── document_routes.py # Deal list, deal detail, document slots
    │   │   ├── drive_routes.py  # Drive folder configuration
    │   │   └── sync_routes.py   # Sync status and document counts
    │   ├── schemas/             # Pydantic request/response models
    │   ├── services/            # document_service, drive_service, google_auth_service
    │   └── utils/
    │       ├── auth.py          # JWT bearer dependency
    │       └── encryption.py    # Fernet encryption for OAuth tokens
    ├── worker/
    │   ├── worker.py            # Orchestrator: batched ingest → LLM → vectorize
    │   ├── drive_ingestion.py   # File discovery, download, checksum
    │   ├── parser.py            # Text extraction (pdfminer / python-pptx / python-docx)
    │   ├── batch_analyzer.py    # Batch LLM classifier (30 docs/call, 10 parallel chunks)
    │   ├── deal_resolver.py     # Fuzzy folder-path → deal name matching
    │   ├── summarizer.py        # Per-doc summary generation
    │   ├── vectorizer.py        # 7-stage Invitus AI Insights pipeline
    │   ├── field_definitions.py # Fund / Direct / Co-Investment field definitions
    │   └── field_extractor.py   # ExtractFields API integration
    ├── alembic/                 # 10 incremental migrations
    ├── setup_db.sh              # DB bootstrap (local + Railway URL support)
    └── requirements.txt
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Auth | Google OAuth 2.0 + JWT (`python-jose`) |
| Token security | Fernet symmetric encryption (`cryptography`) |
| Document parsing | pdfminer.six, python-pptx, python-docx |
| Classification | OpenAI `gpt-4o-mini` (batch, 30 docs/call) |
| Vectorization | Invitus AI Insights (Azure Functions RAG pipeline) |
| Fuzzy matching | rapidfuzz |
| Rate limiting | slowapi |
| Frontend | React 18 + Vite + Tailwind CSS + shadcn/ui |
| Package manager | Bun |
| Deployment | Railway (backend + DB) |

---

## Document Processing Pipeline

```
Google Drive folder
        │
        ▼
  Detect new files by Drive file ID
  (already-seen files are never reprocessed)
        │
        ▼
  Download files in parallel (20 threads)
  Extract text: PDF → pdfminer · PPTX → python-pptx · DOCX → python-docx
        │
        ▼
  Batch LLM classification (gpt-4o-mini, 30 docs/call, up to 10 parallel chunks)
  → doc_type, deal_name, doc_date, summary, is_client flag
        │
        ▼
  Fuzzy deal resolution (rapidfuzz folder-path matching)
  → link document to existing deal or create new deal record
        │
        ▼
  Persist to PostgreSQL
  Mark older versions of same (deal, doc_type) as superseded
        │
        ▼
  Step 4.5: retire meeting-minutes-only deals from pipeline
        │
        ▼
  Vectorizer pipeline — deals processed sequentially, each runs 7 stages:
  1. POST /v1/api/ingestions          → job_id + SAS upload URLs
  2. PUT  <SAS_URL>                   → upload file bytes (4 threads/deal, 3 retries)
  3. POST /v1/api/jobs/{id}/confirm-upload
  4. GET  /v1/api/jobs/{id}           → poll with exponential backoff (5s→60s, 25 min cap)
  5. Persist vectorizer_doc_id on COMPLETED docs only
  6. POST /api/Analytical             → investment_type + deal_outcome (ACCEPTED/REJECTED)
  7. POST /api/ExtractFields          → 13–16 structured fields by investment type
        │
        ▼
  Deal fields stored in deal_fields table
  Surfaced in frontend DealDetail view
```

---

## Why This Is Production-Grade

### Reliability

- **Idempotent ingestion** — files are keyed by Drive file ID with a SHA-256 checksum. The worker can be rerun at any time without creating duplicates.
- **Automatic retry on failure** — docs that fail vectorization (no `vectorizer_doc_id` set) are automatically included in the next worker run. The worker never marks a doc as `vectorized` unless the external pipeline confirmed it.
- **HTTP retries with backoff** — all outbound HTTP calls (SAS uploads, ingestion API, Analytical, ExtractFields) retry up to 3 times with 5 s / 15 s / 30 s backoff before failing.
- **Vectorizer polling resilience** — Stage 4 uses exponential backoff (5 s → 60 s cap, ×1.5 multiplier) for up to 25 minutes and tolerates transient GET errors without aborting the job.
- **DB connection hardening** — `pool_recycle=300`, TCP keepalives (`keepalives_idle=30`), and a `SELECT 1` ping before every persist step with `engine.dispose()` on failure — prevents Railway's SSL proxy from silently dropping idle connections mid-run.
- **Single-instance lock** — `fcntl.LOCK_EX` prevents two worker processes from running simultaneously and corrupting state.

### Security

- **OAuth tokens encrypted at rest** — Google refresh tokens are encrypted with Fernet before being stored in PostgreSQL. The `ENCRYPTION_KEY` is validated at startup.
- **JWT authentication** — all API endpoints are protected by short-lived JWTs. The `SECRET_KEY` is validated to be ≥ 32 characters at startup via Pydantic.
- **Rate limiting** — `slowapi` enforces 200 req/min globally and 60 req/min on document endpoints, protecting against abuse.
- **Request body size cap** — `_BodySizeLimitMiddleware` rejects payloads over 10 MB with HTTP 413, preventing memory exhaustion attacks.
- **No secrets in code** — all credentials are loaded from `.env` via `pydantic-settings`. The config class validates `ENCRYPTION_KEY` is a valid Fernet key at import time.

### Scalability

- **Memory-bounded batching** — `INGEST_BATCH_SIZE=500` (configurable via `.env`) caps peak RAM regardless of Drive folder size. A 10,000-file folder runs in 20 iterations, not one monolithic load.
- **Parallel downloads** — 20 concurrent Drive API threads per batch, saturating typical network bandwidth.
- **Parallel LLM classification** — 30 docs/call × up to 10 concurrent API calls = 300 docs classified simultaneously. 10,000 files complete in ~344 total API calls.
- **Per-deal isolation** — each deal runs its vectorizer pipeline in its own DB session (thread-safe, no shared SQLAlchemy state). 2 deals run concurrently — tuned to avoid throttling dev-tier Azure Functions.
- **Per-user isolation** — up to 5 users processed in parallel, each in their own DB session.

### Data Integrity

- **Incremental migrations** — 10 Alembic migrations in strict sequence (`0001`→`0010`). Schema changes are version-controlled and reproducible.
- **Unique constraints** — `(file_id)` on documents prevents duplicate ingestion; `(deal_id, field_name)` on deal_fields ensures one value per field per deal.
- **Version management** — older documents of the same `(user_id, doc_type, deal_id)` are automatically marked `superseded` when a newer version is ingested, so queries always return the latest.
- **Meeting-minutes guard** — deals whose only documents are meeting minutes are retired from the pipeline (not surfaced as deals), preventing false positives from governance documents.
- **Investment-type-specific fields** — Fund (13 fields), Direct (15 fields), and Co-Investment (16 fields) each have their own field definition set. Fields are always deleted and replaced atomically in a single transaction, preventing stale data.

### Observability

- **Timestamped log files** — every worker run writes to `worker/logs/worker_YYYY-MM-DD_HH-MM-SS.log` and stdout simultaneously.
- **Structured log messages** — every stage logs deal ID, document name, external doc IDs, status, and failure reasons. Failed field extractions log the specific field name and error.
- **Pipeline progress counters** — the worker logs total files, batch progress, docs already vectorized, dealless docs skipped, and deals retired at each step.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/auth/login` | — | Redirect to Google OAuth consent screen |
| `GET` | `/auth/callback` | — | OAuth callback, issues JWT |
| `GET` | `/auth/me` | JWT | Current user profile |
| `POST` | `/drive/folder` | JWT | Configure root Drive folder path |
| `GET` | `/sync/status` | JWT | Sync state, document counts, last run time |
| `GET` | `/documents/deals` | JWT | All deals with latest doc slots and deal fields |
| `GET` | `/documents/deals/{id}` | JWT | Single deal with all docs and structured fields |
| `GET` | `/documents/latest` | JWT | Latest document per type (legacy flat list) |
| `GET` | `/health` | — | Liveness probe |

All authenticated endpoints require `Authorization: Bearer <token>`.

---

## Document Types

| Type | Description |
|------|-------------|
| `pitch_deck` | Investor presentation or company overview |
| `investment_memo` | Due diligence report, deal memo, term sheet analysis |
| `prescreening_report` | Initial assessment or first-look screening |
| `meeting_minutes` | Formal IC/Investment Committee session minutes only |
| `other` | Call notes, board updates, LP letters, operational docs |

> **Note:** `meeting_minutes` requires strong IC signals (motion, quorum, resolution, vote). Call notes and catch-up notes are classified as `other`.

---

## Deal Fields

Structured fields extracted from vectorized documents via the ExtractFields API. Field sets vary by investment type:

| Investment Type | Field Count | Sample Fields |
|----------------|-------------|---------------|
| Fund | 13 | `fundName`, `assetManager`, `fundSize`, `vintageYear`, `targetReturn` |
| Direct | 15 | `companyName`, `sector`, `stage`, `roundSize`, `preMoneyValuation`, `leadInvestor` |
| Co-Investment | 16 | All Direct fields + `leadSponsor`, `coInvestmentSize` |

Fields are grouped into sections (`Opportunity overview`, `Key terms`) and displayed in the DealDetail view with formatted values.

---

## Backend Setup

### Prerequisites

- **Python 3.11** — recommended via [conda](https://docs.conda.io/en/latest/miniconda.html) or [pyenv](https://github.com/pyenv/pyenv)
- **PostgreSQL 14+** — install via your OS package manager:
  ```bash
  # macOS (Homebrew)
  brew install postgresql@16
  brew services start postgresql@16

  # Ubuntu / Debian
  sudo apt install postgresql postgresql-contrib
  sudo systemctl start postgresql

  # Windows — download from https://www.postgresql.org/download/windows/
  ```
- **Google Cloud OAuth credentials** (see step 3 below)
- **OpenAI API key** — from [platform.openai.com](https://platform.openai.com/api-keys)

### 1. Clone and create environment

```bash
git clone https://github.com/sinanshamsudheen/invictus-deals-onboarding.git
cd invictus-deals-onboarding
```

Using conda (recommended):

```bash
conda create -n lokam python=3.11
conda activate lokam
```

Or using venv:

```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
cd server
pip install -r requirements.txt
```

### 3. Set up Google OAuth credentials

1. Go to [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or select an existing one)
3. Click **Create Credentials → OAuth client ID**
4. Set application type to **Web application**
5. Add authorized redirect URI: `http://localhost:8000/auth/callback`
6. Copy the **Client ID** and **Client Secret**
7. Enable the **Google Drive API**: go to [APIs & Services → Library](https://console.cloud.google.com/apis/library), search for "Google Drive API", and click **Enable**
8. Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) → **Test users** → add your Google email address (required while the app is in "Testing" mode)

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `server/.env` and fill in all required values:

```env
# ── PostgreSQL ─────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://postgres:password@localhost:5432/invictus_deals_onboarding

# ── Google OAuth ───────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# ── OpenAI ─────────────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-...

# ── Security ───────────────────────────────────────────────────────────────
# JWT secret — must be at least 32 characters
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<64-char-hex-string>

# Fernet key for encrypting OAuth tokens at rest
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<fernet-base64-key>

# ── Frontend ───────────────────────────────────────────────────────────────
FRONTEND_URL=http://localhost:8080

# ── Invitus AI Insights (optional) ────────────────────────────────────────
# Leave unset to disable the vectorization + analytical pipeline entirely.
# VECTORIZER_INGEST_URL=https://...
# VECTORIZER_ANALYTICAL_URL=https://...
# VECTORIZER_FUNCTION_KEY=...
# VECTORIZER_TENANT_ID=...
```

> **Tip:** Run the two `python -c "..."` commands above to generate `SECRET_KEY` and `ENCRYPTION_KEY` values. Do not reuse the same key for both.

### 5. Set up the database

**Option A — Interactive script (recommended for first-time setup):**

```bash
cd server
chmod +x setup_db.sh
./setup_db.sh
# Choose option 3: "Setup database AND run migrations"
```

**Option B — One-liner:**

```bash
cd server
./setup_db.sh --setup-db && ./setup_db.sh --migrate
```

**Option C — Fully manual:**

```bash
# Create the PostgreSQL database
createdb invictus_deals_onboarding

# Install required extensions
psql -d invictus_deals_onboarding -c 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'

# Run all Alembic migrations
cd server
alembic upgrade head
```

> **Note:** The `setup_db.sh` script reads `DATABASE_URL` from `server/.env`. If you use a different DB name/user/password, update your `.env` first. Default credentials: user=`lokamdb`, password=`sanji`, database=`golden`.

### 6. Start the API server

```bash
# From server/ directory
uvicorn app.main:app --reload --port 8000
```

Or using the start script:

```bash
python start_server.py --reload
```

Verify the server is running:
- Health check: http://localhost:8000/health
- API docs (Swagger): http://localhost:8000/docs
- OAuth login: http://localhost:8000/auth/login

---

## Frontend Setup

### Prerequisites

- **Node.js 18+** and npm, **or** [Bun](https://bun.sh/) (recommended)

### 1. Install dependencies

```bash
cd frontend
bun install        # or: npm install
```

### 2. Configure environment

```bash
cp .env.example .env
```

The default `.env` should work for local development:

```env
VITE_API_URL=http://localhost:8000
```

### 3. Start the development server

```bash
bun dev            # or: npm run dev
```

The frontend runs at **http://localhost:8080** and automatically proxies API requests (`/auth`, `/drive`, `/documents/deals`, `/sync`, `/health`) to the backend at `http://localhost:8000` via Vite's proxy config.

### 4. Build for production

```bash
bun run build      # or: npm run build
```

Output is written to `frontend/dist/`.

### Connecting frontend to backend

When both are running locally:

1. Open **http://localhost:8080** in your browser
2. Click **Sign in with Google** — this redirects to the backend OAuth flow
3. After authentication, the frontend receives a JWT and uses it for all subsequent API calls
4. Configure your Google Drive folder(s) in the settings panel

> **Important:** The backend's `FRONTEND_URL` env var must match the frontend's origin (`http://localhost:8080`) for the OAuth redirect to work correctly after login.

---

## Running the Worker

```bash
# from server/
conda activate lokam
python worker/worker.py

# Vectorizer-only mode: skip Drive sync + LLM classification, run the full
# vectorization pipeline (Stages 1–7) for all deals with incomplete state:
#   Case A — docs not yet vectorized          → full Stage 1–7
#   Case B — vectorized but no investment_type → Stage 6 + Stage 7
#   Case C — investment_type set, no fields    → Stage 7 only
python worker/worker.py --vectorize-only
```

**Schedule nightly at 2 AM via cron:**

```cron
0 2 * * * conda run -n lokam python /path/to/server/worker/worker.py >> /var/log/invictus_deals_onboarding_worker.log 2>&1
```

Each run writes a timestamped log to `server/worker/logs/`.

---

## Database Migrations

| Migration | Description |
|-----------|-------------|
| `0001` | Initial schema: users, documents |
| `0002` | Add version management + deal_id to documents |
| `0003` | Add deals table |
| `0004` | Performance indexes for `get_latest_documents_per_type` |
| `0005` | Add vectorizer fields to documents and deals |
| `0006` | Add company_name to deals |
| `0007` | Add deal_fields table with indexes |
| `0008` | Per-user file_id uniqueness constraint |
| `0009` | Add custom_prompt column to users |
| `0010` | Add folder_ids JSONB for multi-folder support |

```bash
alembic upgrade head      # apply all migrations
alembic current           # check current revision
alembic downgrade -1      # roll back one step
```

---

## Deployment (Railway)

The backend is deployed to Railway with the following environment variables set in the Railway dashboard (same keys as `.env`). The `DATABASE_URL` is provided automatically by Railway's PostgreSQL plugin.

**Run migrations on Railway:**

```bash
DATABASE_URL=<railway_url> ./setup_db.sh
```

**Worker scheduling:** trigger `python worker/worker.py` via Railway's cron job feature or an external scheduler pointed at the deployed service.

> Google OAuth test users must be added at [Google Cloud Console → APIs & Services → OAuth consent screen → Test users](https://console.cloud.google.com/apis/credentials/consent) until the app passes Google's verification review.
