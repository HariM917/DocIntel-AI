# DOCINTEL AI
### Enterprise Document Intelligence & Secure Data Extraction Platform

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg?style=for-the-badge&logo=react)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6.svg?style=for-the-badge&logo=typescript)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3.4+-38B2AC.svg?style=for-the-badge&logo=tailwind-css)](https://tailwindcss.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.2+-EE4C2C.svg?style=for-the-badge&logo=pytorch)](https://pytorch.org/)
[![HuggingFace](https://img.shields.io/badge/RoBERTa-Token_Classification-FFD21E.svg?style=for-the-badge&logo=huggingface)](https://huggingface.co/)
[![FAISS](https://img.shields.io/badge/FAISS-Vector_RAG-0467DF.svg?style=for-the-badge)](https://github.com/facebookresearch/faiss)
[![MongoDB](https://img.shields.io/badge/MongoDB-Motor_Async-47A248.svg?style=for-the-badge&logo=mongodb)](https://www.mongodb.com/)

---

## 📌 Executive Summary

Modern enterprise organizations process thousands of complex documents daily — including **invoices, legal agreements, vendor contracts, government identity cards, and onboarding application forms**. 

Manual document processing introduces severe operational pain points:
- ⏳ **High Inefficiency:** ~6 minutes of manual data entry per document.
- ❌ **Human Error:** Typographical errors in bank accounts, invoice numbers, tax IDs, and billing amounts.
- 🔒 **Data Privacy Exposure:** Uncontrolled leakage of Personally Identifiable Information (PII) such as Indian **Aadhaar numbers, PAN cards, credit cards, bank accounts, and personal emails**.
- 🗄️ **Unsearchable Silos:** Scanned images and flattened PDFs remain inaccessible to semantic search and automated workflows.

**DOCINTEL AI** is a full-stack, enterprise-grade platform designed to automatically ingest, OCR, classify, redact, validate, extract, and index documents into a vector-grounded conversational AI assistant with zero hallucinations.

---

## 🚀 Key Platform Capabilities

| Capability | Engineering Implementation |
|---|---|
| 📄 **Multi-Format Ingestion** | High-resolution PDF parsing via **PyMuPDF (fitz)** with 300-DPI rasterization and image preprocessing (contrast, sharpness, adaptive thresholding) for **Tesseract OCR**. |
| 🏷️ **Multi-Signal Classification** | Weighted keyword density and contextual regex engine categorizing documents into `Invoice`, `Contract`, `Identity`, `Application`, `Form`, or `Other`. |
| 🧠 **RoBERTa Token NER** | Hugging Face Transformers token classification (`Jean-Baptiste/roberta-large-ner-english`) extracting `PERSON`, `ORGANIZATION`, `LOCATION`, and `DATE` with confidence scores. |
| 🛡️ **Algorithmic PII Validation** | Deterministic regex coupled with **Verhoeff algorithm** (Aadhaar 12-digit checksum), **Luhn MOD-10 algorithm** (credit cards), and Indian Income Tax Department status validation (PAN). |
| 🔒 **Dynamic Redaction Engine** | Enterprise security policies persisted in MongoDB that mask sensitive fields (e.g. `XXXX XXXX 9012`, `XXXXX1234F`, `r***@example.com`) across UI and text storage. |
| 📊 **Typed Schema Extraction** | Domain schema synthesis extracting invoices (subtotal, tax, currency, vendor, dates), contracts (parties, governing law), and identity credentials without hallucination. |
| ⚡ **Asynchronous Processing Pipeline** | Uploads return `202 Accepted` immediately; the AI pipeline runs in **Celery** workers over **Redis**, with atomic job claiming (no double-processing), bounded exponential-backoff retries, and idempotent re-processing. Production refuses to run the queue inline. |
| ⚡ **Conversational RAG Assistant** | SentenceTransformers (`all-MiniLM-L6-v2`) chunking and embedding documents into **FAISS** vector store for context-grounded conversational QA with source citations. Retrieval is **authorization-filtered at the vector level**, so a caller never sees another tenant's chunks. |
| 📈 **Live Telemetry Dashboard** | Real-time MongoDB metrics: Total Processed, **Avg. Extraction Confidence (%)**, Protected Entities, and Calculated Time Saved. Confidence is never fabricated — it is only reported where the pipeline actually measured it. |
| 🔄 **Resilient Local Dev Store** | In **non-production only**, a local JSON fallback (`data/local_db.json`) lets the stack run without a MongoDB daemon. **Production requires MongoDB**, the fallback is disabled, and the app refuses to start otherwise. |

---

## 🏗️ System Architecture & AI Pipeline

```mermaid
flowchart TD
    subgraph Client["Frontend (React 18 + Vite + Tailwind)"]
        UI1["Process Document Upload"]
        UI2["Dashboard Telemetry"]
        UI3["Document Archive & Filters"]
        UI4["Security Rule Engine"]
        UI5["FAISS RAG Assistant"]
    end

    subgraph Gateway["API Gateway (FastAPI)"]
        AUTH["JWT Authentication & Centralized Authorization"]
        EP1["POST /api/documents/process (202 Accepted)"]
        EP2["/api/dashboard/stats"]
        EP3["/api/security/rules"]
        EP4["/api/chat"]
    end

    subgraph Queue["Async Worker Tier (Phase 2)"]
        BROKER[("Redis broker + result backend")]
        WORKER["Celery worker — claim job atomically, run pipeline, retry on transient failure"]
    end

    subgraph Pipeline["Document Intelligence Pipeline (instrumented, fault-isolated)"]
        S1["1. Upload & Staging"]
        S2["2. PyMuPDF + Tesseract OCR (critical)"]
        S3["3. Text Normalization"]
        S4["4. Structure & Multi-Signal Classification"]
        S5["5. RoBERTa Named Entity Recognition"]
        S6["6. Deterministic PII Detection"]
        S7["7. Redaction Engine"]
        S8["8. Typed Schema Extraction"]
        S9["9. Validation (Verhoeff / Luhn / PAN)"]
        S10["10. Quality Assessment"]
        S11["11. Embedding"]
        S12["12. FAISS Indexing"]
    end

    subgraph Storage["Persistence Tier"]
        DB[("MongoDB 7.0 (required in prod)")]
        VEC[("FAISS Dense Vector Index — tenant-tagged chunks")]
    end

    UI1 --> EP1
    UI2 --> EP2
    UI3 --> EP1
    UI4 --> EP3
    UI5 --> EP4

    EP1 --> S1 --> BROKER --> WORKER
    WORKER --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8 --> S9 --> S10 --> S11 --> S12
    S8 --> DB
    S12 --> VEC
    EP4 <--> VEC
    EP4 --> DB
```

---

## 📂 Project Structure

```
DocIntel-AI/
├── .gitignore
├── docker-compose.yml               # Multi-container stack (Mongo + Redis + API + Celery worker + Frontend)
├── README.md                        # Master project documentation
│
├── backend/
│   ├── .env.example                 # Environment configuration template
│   ├── Dockerfile                   # Backend Docker container with Tesseract OCR
│   ├── README.md
│   ├── requirements.txt             # Python dependencies
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                # Pydantic v2 application settings
│   │   ├── database.py              # MongoDB async manager + local JSON fallback
│   │   ├── main.py                  # FastAPI entry point, lifespan, CORS, and exception handler
│   │   │
│   │   ├── api/                     # REST API Routers
│   │   │   ├── auth.py              # Register, login, JWT /me
│   │   │   ├── chat.py              # RAG conversational query answering
│   │   │   ├── dashboard.py         # Real-time metrics and recent document feeds
│   │   │   ├── documents.py         # File ingestion, archive list, details, delete, download
│   │   │   ├── search.py            # Global substring & entity search with snippet generation
│   │   │   └── security.py          # Dynamic PII masking rules engine
│   │   │
│   │   ├── models/                  # Domain Models
│   │   │   ├── document.py          # DocumentModel, EntityModel, PIIModel
│   │   │   ├── security.py          # SecurityRuleModel
│   │   │   └── user.py              # UserModel
│   │   │
│   │   ├── schemas/                 # Pydantic Schemas
│   │   │   ├── auth.py              # UserRegister, UserLogin, TokenResponse
│   │   │   ├── chat.py              # ChatRequest, ChatResponse, SourceReference
│   │   │   ├── dashboard.py         # DashboardStats, RecentDocumentItem
│   │   │   ├── document.py          # DocumentResponse, PipelineStep, Typed Schemas
│   │   │   └── security.py          # SecurityRule, SecurityRuleUpdate
│   │   │
│   │   ├── services/                # Business & AI Intelligence Services
│   │   │   ├── authorization_service.py   # Single source of truth for document/chunk access
│   │   │   ├── document_classifier.py     # Invoice/Contract/Identity multi-signal classifier
│   │   │   ├── document_service.py        # Ingestion, staging, storage, lifecycle orchestration
│   │   │   ├── embedding_service.py       # SentenceTransformers embeddings + deterministic SHA-256 fallback
│   │   │   ├── ner_service.py             # RoBERTa token classification (NER) + entity validation
│   │   │   ├── ocr_service.py             # PyMuPDF + Tesseract OCR engine
│   │   │   ├── pipeline_stages.py         # Stage-name constants & duration tracking
│   │   │   ├── pii_service.py             # Regex + context PII detection
│   │   │   ├── processing_service.py      # Job lifecycle, atomic claim, retry policy, pipeline driver
│   │   │   ├── quality_service.py         # Weighted quality assessment (OCR/coverage/entity density)
│   │   │   ├── queue_service.py           # local | celery dispatch selection
│   │   │   ├── rag_service.py             # FAISS index, authorized retrieval & grounded synthesis
│   │   │   ├── redaction_service.py       # Masking / deterministic placeholder policies
│   │   │   ├── storage_service.py         # StorageService abstraction (local filesystem)
│   │   │   ├── structure_service.py       # Heading/section structure detection
│   │   │   ├── structured_extraction.py   # Structured typed JSON schema generation
│   │   │   ├── text_normalization_service.py # Deterministic OCR text normalization
│   │   │   └── validation_service.py      # Verhoeff (Aadhaar), Luhn (Cards), PAN checksums
│   │   │
│   │   ├── worker/
│   │   │   └── celery_app.py        # Celery application (Redis broker/backend, acks_late)
│   │   ├── tasks/
│   │   │   └── document_tasks.py    # Celery task wrapping the processing job
│   │   │
│   │   └── utils/
│   │       └── security.py          # Password hashing, JWT, authorization dependency helpers
│   │
│   └── tests/                       # Automated Pytest Suite (143 Tests)
│       ├── conftest.py              # TestClient & database session setup
│       ├── test_auth.py             # User registration, login, token guards
│       ├── test_dashboard_search.py # Dashboard stats, search, security rules, chat
│       ├── test_documents.py        # Upload, processing pipeline, file validation
│       ├── test_ner.py              # RoBERTa label mapping & entity deduplication
│       ├── test_ocr.py              # Image preprocessing, PDF extraction, extensions
│       ├── test_pii_redaction.py    # Aadhaar, PAN, Luhn validation & masking
│       ├── test_structured_extraction.py # Category classification & schema extraction
│       ├── test_security_isolation.py  # Phase 1 — auth, ownership isolation, prod config guards
│       ├── test_phase2_async.py     # Phase 2 — async lifecycle, retries, storage, RAG metadata
│       ├── test_phase3_pipeline.py  # Phase 3 — staged pipeline, redaction, quality, validation
│       └── test_stabilization.py    # Production stabilization acceptance suite (32 tests)
│
├── frontend/
│   ├── .env.example
│   ├── Dockerfile                   # Multi-stage build with Nginx Alpine serving
│   ├── index.html                   # HTML5 shell
│   ├── nginx.conf                   # Reverse proxy & SPA routing configuration
│   ├── package.json
│   ├── tailwind.config.js           # Enterprise Navy & Brand color theme
│   ├── tsconfig.json                # TypeScript strict configuration
│   ├── vite.config.ts
│   │
│   └── src/
│       ├── App.tsx                  # React Router routes & auth provider shell
│       ├── index.css                # Tailwind directives & custom scrollbars
│       ├── main.tsx                 # React DOM mount point
│       ├── vite-env.d.ts            # Vite client environment types
│       │
│       ├── components/              # Reusable UI Components
│       │   ├── Navbar.tsx           # Global search with live dropdown, user profile
│       │   ├── PipelineVisualizer.tsx # Interactive 8-stage visual pipeline timeline
│       │   ├── Sidebar.tsx          # Navy enterprise navigation sidebar
│       │   ├── StatCard.tsx         # Dashboard metric card with trends
│       │   └── Toast.tsx            # Floating toast notification system
│       │
│       ├── hooks/
│       │   └── useAuth.tsx          # JWT auth context with localStorage persistence
│       │
│       ├── layouts/
│       │   └── DashboardLayout.tsx  # Authenticated shell layout
│       │
│       ├── pages/                   # Application Pages
│       │   ├── AIAssistant.tsx      # RAG assistant with grounded source citations
│       │   ├── Dashboard.tsx        # Real-time metrics & recent documents table
│       │   ├── DocumentArchive.tsx  # Filterable document database with pagination
│       │   ├── DocumentDetails.tsx  # Schema fields, entities, masked PII, OCR diff
│       │   ├── Login.tsx            # Login page with demo credentials auto-fill
│       │   ├── ProcessDocument.tsx  # Drag & drop upload, pipeline visualizer, tabbed results
│       │   ├── Register.tsx         # User registration
│       │   └── SecurityRules.tsx    # Toggleable PII redaction policy rules
│       │
│       ├── services/
│       │   └── api.ts               # Axios client with JWT interceptor & progress events
│       │
│       ├── types/
│       │   └── index.ts             # Complete TypeScript interface definitions
│       │
│       └── utils/
│           ├── formatters.ts        # Byte, date, confidence, and badge color formatters
│           └── index.ts
│
├── data/
│   ├── local_db.json                # Pre-seeded local persistent JSON store
│   ├── processed/                   # Processed documents staging
│   ├── sample_documents/            # Synthetic PDF and PNG invoices, contracts, IDs
│   └── vector_index/                # FAISS binary vector index + metadata chunks
│
├── docs/
│   ├── api.md                       # Full REST API documentation & JSON request/response
│   ├── architecture.md              # System architecture & Mermaid sequence diagram
│   └── demo.md                      # 5-minute hackathon evaluation guide
│
└── scripts/
    ├── create_sample_docs.py        # High-res sample invoice, contract, ID generator
    ├── seed_database.py             # Seeds admin user and default security rules
    └── test_pipeline.py             # End-to-end pipeline smoke test
```

---

## 🛠️ Local Development & Setup (Windows)

### Prerequisites
- **Python 3.11+** installed and added to `PATH`
- **Node.js 18+** & `npm`
- *(Optional)* **Tesseract OCR for Windows**: [UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki) (Defaults to `C:\Program Files\Tesseract-OCR\tesseract.exe`)
- *(Optional)* **Redis 7**: Required only when `PROCESSING_QUEUE=celery`. With the default `local` queue mode, jobs run in-process and no broker is needed.
- *(Optional, dev only)* **MongoDB 7.0**: In non-production, if MongoDB is not running and `ALLOW_LOCAL_FALLBACK=true`, the platform uses `data/local_db.json`. **Production always requires MongoDB** — the fallback is disabled and startup fails if it is not configured.

---

### 1. Backend Service (FastAPI)

```powershell
# Open terminal in project root:
cd backend

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Upgrade pip and install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Create environment configuration
copy .env.example .env

# Run FastAPI server
uvicorn app.main:app --reload --port 8000
```
- **API Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Interactive UI:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check Endpoint:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

### 2. Frontend Application (React + Vite + TypeScript)

```powershell
# Open a second PowerShell terminal:
cd frontend

# Install Node dependencies
npm install

# Create environment configuration
copy .env.example .env

# Start Vite development server
npm run dev
```
- **Web Application UI:** [http://localhost:5173](http://localhost:5173)

---

### 3. Database Seeding & Pipeline Smoke Test

```powershell
# In your backend virtual environment:
python scripts/create_sample_docs.py
python scripts/seed_database.py
python scripts/test_pipeline.py
```

**Default Admin Credentials:**
- **Email:** `admin@docintel.ai`
- **Password:** `Admin@12345`  
*(Or click "Fill Default Demo Admin" on the login page for 1-click access)*

---

## 🧪 Automated Testing & Verification

### Run Backend Pytest Suite
```powershell
cd backend
python -m pytest tests/ -v
```
**Result:** **143 tests pass** (`143 passed` on the current codebase). The suite covers:
- `test_auth.py`: Registration, duplicate prevention, login, JWT bearer validation, `/me` endpoint
- `test_ocr.py`: PIL image preprocessing, PDF page extraction, extension verification
- `test_ner.py`: RoBERTa token classification, label normalization (`PER` → `PERSON`), deduplication
- `test_pii_redaction.py`: Aadhaar Verhoeff checksum, PAN tax code validation, Luhn card check, masking
- `test_structured_extraction.py`: Invoice, Contract, Identity classification and typed schema generation
- `test_documents.py`: File ingestion, storage, retrieval, delete, and download
- `test_dashboard_search.py`: Real-time metric calculation, substring query search, rule updates, RAG chat
- `test_security_isolation.py`: Ownership/tenant isolation, production config guards, path-traversal defence
- `test_phase2_async.py`: Async job lifecycle, atomic claiming, retries, storage keys, RAG metadata
- `test_phase3_pipeline.py`: Staged pipeline behaviour, redaction modes, quality scoring, validation
- `test_stabilization.py`: Production-stabilization acceptance suite (authorization, RAG, embeddings, chunking, Celery, config, dashboard, AI confidence, storage)

### Run End-to-End Pipeline Smoke Test
```powershell
python scripts/test_pipeline.py
```
**Result:** Successfully validates file upload → OCR text extraction → text normalization → structure detection → classification → RoBERTa NER → deterministic PII detection → redaction → structured schema extraction → validation → quality assessment → embedding → MongoDB persistence → FAISS vector indexing & authorized RAG retrieval.

### Run Frontend Production Build
```powershell
cd frontend
npm run build
```
**Result:** Compiles with **zero TypeScript errors** (`npx tsc --noEmit` passes) and generates an optimized bundle in `frontend/dist/`.

---

## 🐳 Docker Multi-Container Stack

The Compose stack runs **five services**: MongoDB, Redis, the FastAPI backend, a Celery worker, and the Nginx-hosted React frontend.

A strong `JWT_SECRET_KEY` **must** be supplied (the stack refuses to start without it):

```powershell
$env:JWT_SECRET_KEY = "<a strong random value of at least 32 characters>"
docker compose up --build
```
- **Frontend Application:** [http://localhost:5173](http://localhost:5173)
- **Backend API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **MongoDB:** `localhost:27017` (bound to loopback only)
- **Redis:** internal network only (not published to the host)

`PROCESSING_QUEUE=celery` is set for the API and worker, so uploads are queued to Redis and processed out-of-band by the worker container.

---

## 🛡️ Security & Privacy Features

1. **Zero Secret Exposure:** No API keys, database credentials, or secret keys exist in client-side code or Git history.
2. **Centralized Authorization:** A single `authorization_service` is the source of truth for document access. A caller may read/modify a document only when it is theirs (`owner_id`) or belongs to their organization (`organization_id` — matched only when both sides are non-empty). Every document, search, dashboard, download and chat route enforces this.
3. **Tenant-Isolated Vector Retrieval:** FAISS chunks carry `owner_id` / `organization_id` metadata and are filtered **at retrieval time**. `top_k` counts only *authorized* results, so a caller can never receive another tenant's chunks. Chat additionally authorizes the target document against MongoDB before answering.
4. **PII Redaction Before Vectorization:** Only masked, sanitized text chunks are embedded and stored in the FAISS index to prevent sensitive PII leakage through embeddings.
5. **Prompt-Injection Defence:** Retrieved context is neutralized before it reaches the synthesis prompt, and the system instructions forbid following instructions embedded inside documents.
6. **Anti-Hallucination RAG Guardrails:** The conversational AI assistant answers questions strictly using retrieved document context, and only reports a confidence value derived from real retrieval scores (never fabricated). When information is not present in indexed documents, it answers:
   > *"I couldn't find that information in the available documents."*
7. **Algorithmic Checksums:** Validates 12-digit Indian Aadhaar numbers using the Verhoeff multiplication table and credit cards using the Luhn MOD-10 algorithm.
8. **Deterministic by Design:** The embedding fallback is a SHA-256-derived deterministic projection (never Python's salted `hash()`), so the same text always yields the same vector across processes and restarts.
9. **Fail-Closed Production Guards:** Production startup is refused unless a strong JWT secret, explicit CORS allow-list, Celery queue, real MongoDB/Redis endpoints, and the local storage backend are configured. Unimplemented S3 storage is explicitly refused rather than silently degraded.

---

## 📋 Hackathon Demo Walkthrough (5 Minutes)

1. **Login:** Navigate to [http://localhost:5173](http://localhost:5173) and click **"Fill Default Demo Admin"** (`admin@docintel.ai` / `Admin@12345`).
2. **Upload & Process:** Go to **"Process Document"**, drag & drop `data/sample_documents/sample_invoice.pdf`, and click **"Start Extraction & Redaction"**.
3. **Live Pipeline Visualizer:** Watch the interactive timeline progress across **Upload → OCR → Classification → RoBERTa NER → PII Detection → Redaction → Structured Extraction → FAISS Storage**.
4. **Inspect Tabs:** Review the synthesized **Structured Schema**, extracted **Entities**, detected **Masked PII**, and side-by-side **Raw vs. Redacted Text**.
5. **Dashboard Telemetry:** Return to **Dashboard** to see live updated metrics: Total Processed, Avg. Extraction Confidence, Protected Entities, and Calculated Time Saved.
6. **Ask AI Assistant:** Navigate to **"AI Assistant"** and ask:
   - *"What is the invoice amount?"*
   - *"Who is the vendor?"*
   - *"Which documents contain Aadhaar numbers?"*
   Observe grounded answers with clickable source citations and similarity scores.
7. **Security Rules:** Navigate to **"Security Rules"** and toggle compliance policies for Aadhaar, PAN, Emails, Phones, Bank Accounts, or Credit Cards with real-time persistence.

---

## Contributors

**HARI**

---
## 📄 License & GitHub Repository

- **Repository:** [https://github.com/HariM917/DocIntel-AI](https://github.com/HariM917/DocIntel-AI)
- **License:** Distributed under the MIT License.
