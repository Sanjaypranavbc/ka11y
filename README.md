# ka11y — AI-Powered WCAG Accessibility Auditing

**ka11y** is a next-generation accessibility auditing platform that transcends traditional DOM-based scanning. By combining industry-standard DOM analysis with advanced Computer Vision (CV) and Natural Language Processing (NLP), ka11y detects complex accessibility violations that automated tools typically miss—such as descriptive alt-text accuracy, animated content controls, and interactive target sizes.

---

## 🏗 Architecture Overview

The system operates on a hybrid, parallel execution model. A central **Python FastAPI** orchestrator manages high-level job lifecycle and SSE (Server-Sent Events) broadcasting, while specialized engines handle different audit domains.

### System Flow
```mermaid
graph TD
    Client[Browser / CI / SDK] -- "POST /api/v1/combined/" --> Orchestrator["FastAPI Orchestrator (Python)"]
    
    subgraph "Parallel Execution Engines"
        direction LR
        NodeEngine["Node.js Engine (axe-core)"]
        PythonEngine["Python AI Auditors"]
    end

    Orchestrator --> NodeEngine
    Orchestrator --> PythonEngine
    
    NodeEngine -- "DOM/ARIA Findings" --> Aggregator["Result Aggregator"]
    PythonEngine -- "CV/NLP/Rendered Findings" --> Aggregator
    
    Aggregator -- "Merged JSON Report" --> Storage["Artefact Storage (Local/Docker)"]
    Aggregator -- "job_complete SSE" --> Client
    
    subgraph "Python Audit Pipeline"
        direction TB
        Context["1. Context Extraction (Playwright)"]
        Semantic["2. Semantic Enrichment (NLP)"]
        Interaction["3. Interaction Simulation"]
        Policy["4. Policy Decision Engine"]
        Context --> Semantic --> Interaction --> Policy
    end
    
    PythonEngine -.-> Context
```

---

## 🚀 Key Features

- **Hybrid Auditing Engine:** Runs `axe-core` (Node.js) for DOM structure and ARIA semantics alongside **Python Auditors** for visual and behavioral checks.
- **AI-Powered Visual Analysis:** Uses OCR and Image Classification to verify if alt-text actually describes the image content (WCAG 1.1.1).
- **Behavioral Detection:** Identifies moving content like carousels and autoplay videos (WCAG 2.2.2).
- **Real-time Feedback:** Streams audit progress via **Server-Sent Events (SSE)**, allowing frontends to display live status cards for each stage.
- **Graceful Degradation:** If one engine fails or times out, the system returns partial results with warnings rather than a hard failure.

---

## 🛠 Tech Stack

### Backend (Orchestration & AI)
- **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python 3.13+)
- **Automation:** [Playwright](https://playwright.dev/) (Browser orchestration & context extraction)
- **Computer Vision:** [EasyOCR](https://github.com/JaidedAI/EasyOCR), [OpenCV](https://opencv.org/)
- **NLP & ML:** [PyTorch](https://pytorch.org/), [Hugging Face Transformers](https://huggingface.co/docs/transformers/index), [SpaCy](https://spacy.io/), [Google Gemini AI](https://ai.google.dev/)
- **Audio/Speech:** [Faster-Whisper](https://github.com/SYSTRAN/faster-whisper)

### Backend (DOM Analysis)
- **Runtime:** Node.js
- **Engine:** [axe-core](https://github.com/dequelabs/axe-core)

### Frontend (SDK & Dashboard)
- **Library:** React (TypeScript)
- **Styling:** Tailwind CSS
- **Build Tool:** Vite
- **Package Manager:** Bun

### DevOps
- **Containerization:** Docker & Docker Compose
- **Configuration:** YAML-based universal config

---

## 📖 Solution Components

### 1. Unified Accessibility Pipeline
Instead of evaluating elements in isolation, `ka11y` uses a **Centralized Context Pipeline**. It extracts the full page state (DOM, CSS, ARIA, Bounding Boxes) once and feeds this "Rich Context" into multiple WCAG policies. This drastically reduces false positives in complex checks like **2.5.8 Target Size**.

### 2. Python AI Auditors
Specialized auditors handle criteria that require "human-like" understanding:
- **Alt-Text Auditor:** Compares the visible image content (via OCR/Classification) against the `alt` attribute.
- **Form Auditor:** Verifies visible labels and error identification (WCAG 3.3.1/3.3.2).
- **Motion Auditor:** Detects animated GIFs, CSS animations, and JS-driven layout shifts.

### 3. SSE Progress Bus
The system maintains an internal event bus. As each stage (axe-core, image-crawl, form-audit) starts or completes, an event is broadcast to all connected clients. This provides a responsive, "live" experience for long-running audits.

---

## 📂 Project Structure

- `ka11y-python/`: The core FastAPI application, AI auditors, and Playwright crawlers.
- `ka11y-node/`: Node.js microservice wrapping `axe-core` for standard DOM audits.
- `ka11y-frontend-sdk/`: A React-based UI components and hooks for integrating ka11y results.
- `ka11y-docs/`: Comprehensive technical documentation and WCAG mapping guides.
- `i18n/`: Multi-language support for audit findings (currently English, Japanese, German).

---

## 🔌 Combined Accessibility Endpoint

A combined endpoint is available to run Node and Python checks simultaneously on the same target URL:

### GET `/api/ka11y/combined?url=<target-url>`

**Response Format:**
```json
{
  "url": "https://example.com",
  "node_result": { ... },
  "python_result": { ... },
  "combined_summary": {
    "total_issues": 3,
    "critical": 1,
    "warnings": 2
  }
}
```

### Running Locally

1. **Start the Node service:**
   ```bash
   cd ka11y-node
   npm install
   npm run dev # Runs on port 3000 by default
   ```

2. **Start the Python service:**
   ```bash
   cd ka11y-python
   poetry install
   poetry run uvicorn ka11y.main:app --reload --port 8000
   ```

3. **Request Combined Results:**
   Send a `GET` request to `http://localhost:3000/api/ka11y/combined?url=https://example.com`.

### Queue + worker (Amazon SQS)

Audits no longer run inside the API process. `POST /api/v1/combined` writes the
job's `state.json` to object storage, publishes an `AuditJobMessage` (job id,
URL, request parameters — a few hundred bytes) to SQS and answers `202`. A
separate **worker** process consumes the queue and runs the audit:

```bash
cd ka11y-python
poetry run python -m ka11y.worker.worker     # needs SQS_QUEUE_URL (+ SQS_ENDPOINT_URL for LocalStack)
```

| Rule | Where |
|------|-------|
| A concurrency slot (`WORKER_MAX_CONCURRENCY`, default 2) is taken **before** a message is received, and at most *free slots* messages are pulled | `ka11y/worker/concurrency.py`, `Worker.run` |
| The message is deleted only **after** the final `state.json` is written (completed / failed / cancelled) | `Worker._settle_outcome` |
| A visibility heartbeat extends the message every `SQS_VISIBILITY_TIMEOUT/2` s while the audit runs | `Worker._heartbeat` |
| Already-terminal jobs (duplicate deliveries) are deleted and skipped; a cancel marker settles the job without running it | `Worker._handle` |
| `SIGTERM`/`SIGINT` stop polling and let in-flight audits finish (`WORKER_SHUTDOWN_TIMEOUT`) | `Worker.request_stop` |
| A runner crash leaves the message for redelivery; after `WORKER_MAX_ATTEMPTS` (3) the job is failed. The queue's dead-letter `RedrivePolicy` uses the same `maxReceiveCount=3` | `Worker._settle_crash`, `localstack/init-sqs.sh` |

Locally, `docker compose` starts a **LocalStack** service and
`localstack/init-sqs.sh` creates `ka11y-audit-jobs` (visibility 300 s, long
poll 20 s) plus `ka11y-audit-jobs-dlq`. In AWS create the same two queues and
set `SQS_QUEUE_URL` (leave `SQS_ENDPOINT_URL` empty); the code never creates
queues. The API and the worker share one object store — an S3 bucket
(`KA11Y_S3_BUCKET`) or, without one, the `./output/artifacts` bind mount —
which is where `state.json`, `reviews.json`, `reports/` and every asset live.
PostgreSQL is switched off for now (see `docker-compose.yml`), so sign-in
stays disabled (`KA11Y_AUTH_DISABLED=1`).

### Running with Docker

```bash
docker compose up --build      # first start: creates ./output/*, LocalStack queues, API + worker
docker compose down            # stop; history is kept
./run.sh                       # stop + rebuild + start (non-destructive)
./run.sh --wipe                # clean slate: deletes ./output/* after confirmation
```

**History persists across restarts.** Everything stateful is a bind mount under
`./output/` (git-ignored), so `docker compose down` / `up`, `down -v`,
`docker volume prune` and image rebuilds never lose data:

| Path | Container | Holds |
|------|-----------|-------|
| `output/pg` | postgres `/var/lib/postgresql/data` | users, sessions, audit history (admin console) |
| `output/assets`, `output/artifacts` | python `/data/assets`, `/data/artifacts` | screenshots/crops; stored JSON/CSV/PDF reports |
| `output/logs`, `output/crawled_images` | python `/app/logs`, `/app/crawled_images` | scratch output, safe to delete |

Only the ML model caches (`huggingface_cache`, `paddlex_models`, `easyocr_models`)
are named volumes; losing them just means a re-download. `output/pg` must be empty
on the very first start (PostgreSQL's initdb refuses a non-empty directory), so it
is created by Docker, never checked in. To wipe history by hand:

```bash
docker compose down
sudo rm -rf output/pg output/assets output/artifacts
```

Migrating from the old named volume (`ka11y_ka11y_pg`) to `output/pg`, one time:

```bash
docker compose down
docker run --rm -v ka11y_ka11y_pg:/from -v "$PWD/output/pg":/to alpine sh -c 'cp -a /from/. /to/'
docker compose up -d
docker volume rm ka11y_ka11y_pg   # once you have confirmed the history is back
```

