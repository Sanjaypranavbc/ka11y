# ka11y — Production Optimization, Persistence & Telemetry Plan

**Date:** 2026-06-02
**Author:** engineering (planning)
**Scope:** `ka11y-python` (FastAPI auditors), `ka11y-node` (axe-core engine), shared crawl/queue/storage layer.

---

## 0. Decisions locked (from kickoff Q&A)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Deployment target / DB engine | **Single box, SQLite (WAL)**, in-process asyncio workers. Crash-safety comes from the DB, not a broker. |
| 2 | Asset storage | **DB metadata + files on a mounted volume.** One row per asset (path, sha256, type, run_id, page_url, bytes); bytes stay on disk. |
| 3 | Crawl strategy | **Unify on a single crawl pass.** One browser loads each page once; axe-core runs against that same page. Kills the double Playwright+Puppeteer load. |
| 4 | Queue / execution | **DB-backed durable queue + ProcessPoolExecutor** for CPU-bound auditors. No external broker. |

Design constraints implied by these choices:
- **Keep SQLite swappable.** Use a thin DAL (data-access layer) with parameterized SQL or SQLAlchemy Core so a future Postgres move is mechanical, not a rewrite.
- **Single writer discipline.** SQLite WAL allows many readers + one writer. All writes go through one serialized writer (an `asyncio.Queue` drained by a single task, or a short-lived `to_thread` with a global write lock). Never write SQLite from multiple processes concurrently.
- **The DB must never fail an audit.** Every persistence call is wrapped; a DB error logs and degrades, exactly like the existing timing loggers (`run_timing.py`, `stage_timing.py`).

---

## 1. As-is architecture & measured bottlenecks

### 1.1 Request lifecycle (today)
1. `POST /api/v1/combined/` (`routes.py:201`) → builds `_jobs[job_id]` **in-memory dict**, fires `asyncio.create_task(_run_job(...))`, returns 202.
2. `runner._run_job` (`runner.py:165`) acquires `_job_semaphore` (`KA11Y_MAX_CONCURRENT_JOBS=4`), then `_run_job_body`:
   - Resolves language, makes `output_dir` on disk.
   - **Fires axe (Node) and Python stages concurrently** via `asyncio.gather`.
   - Node and Python **each crawl the whole site independently**, synchronized by `snapshot_urls_event` / `snapshot_urls_container` so Node audits Python's discovered URL set.
   - Merges findings (`_merge_findings`), builds report, writes `combined_report.json`, updates `_jobs[job_id]["result"]`.
3. `store._evict_old_jobs` (`store.py:161`) deletes the in-memory job **and** its on-disk `*_combined` dir after `_JOB_TTL_SECONDS=3600`.

### 1.2 Concurrency map (today)
| Layer | Limit | Where |
|-------|-------|-------|
| Concurrent audit jobs | `KA11Y_MAX_CONCURRENT_JOBS=4` | `runner.py:62` |
| Heavy stages (image + rendered-layout) | `KA11Y_HEAVY_STAGE_CONCURRENCY=2` | `stages.py:212` |
| Chromium processes (Python pool) | `KA11Y_MAX_BROWSERS=2` | `browser_pool.py:60` |
| Parallel pages per crawl (Python) | `_UNIVERSAL_PARALLEL_PAGES` | `universal_page.py:43` |
| Node puppeteer concurrency | `PUPPETEER_MAX_CONCURRENT=3` | `accessibility.service.js:82` |
| Node BFS within a request | **serial** (1 page at a time) | `crawl.js:116` `while(queue)` |
| CPU auditor offload | `asyncio.to_thread` (GIL-bound for pure-Python) | `stages.py` (20+ call sites) |

### 1.3 The five real bottlenecks
- **B1 — Double crawl.** Each page is fetched and rendered twice (Playwright snapshot + Puppeteer axe). ~2× page-load time and ~2× browser RAM. This is the dominant cost at depth>0.
- **B2 — Node BFS is serial.** `crawl.js` visits one URL at a time even though the service allows 3 concurrent. On a 50-page crawl axe is effectively single-threaded.
- **B3 — No persistence.** `_jobs` + report JSON + assets all evaporate on TTL or restart. A crash mid-run loses everything; no history; no audit trail.
- **B4 — GIL-bound CPU work.** OCR, cosine-similarity, contrast analysis run in threads. NumPy/OpenCV release the GIL, but pure-Python paths (text similarity, parsing) don't — so "parallel" stages serialize on CPU.
- **B5 — Fragmented telemetry.** 4 file formats (`run_timings.log`, `crawler_timings.log`, `logs/timings/*.jsonl`, step-logger JSONL). Not queryable, not joinable, swept with the job dir.

---

## 2. Target architecture (to-be)

```
                      ┌───────────────────────────────────────────────┐
   POST /combined ──► │  API (FastAPI, stateless re: job state)        │
                      │   • validates + SSRF guard                     │
                      │   • INSERT run(status=queued) into SQLite      │
                      │   • returns 202 + run_id                       │
                      └───────────────┬───────────────────────────────┘
                                      │  (no in-proc handoff required)
                      ┌───────────────▼───────────────────────────────┐
                      │  Dispatcher (single asyncio task)              │
                      │   • polls runs WHERE status=queued (FIFO)      │
                      │   • admits up to MAX_CONCURRENT_JOBS           │
                      │   • on boot: requeue status=running (crash     │
                      │     recovery)                                  │
                      └───────────────┬───────────────────────────────┘
                                      │
                      ┌───────────────▼───────────────────────────────┐
                      │  Job worker (per run)                          │
                      │   1. SINGLE crawl pass (Playwright)            │
                      │      → per-page: DOM snapshot + axe-core run   │
                      │        (axe.min.js injected into same page)    │
                      │   2. CPU auditors → ProcessPoolExecutor        │
                      │   3. merge → report                            │
                      │   4. persist: run, findings, report, assets,   │
                      │      stage_timings  (all SQLite, one writer)   │
                      └───────────────┬───────────────────────────────┘
                                      │
            ┌─────────────────────────┼──────────────────────────────┐
            ▼                         ▼                              ▼
   SQLite (WAL) ka11y.db      Asset volume /data/assets       SSE bus (in-mem)
   runs / findings /          <sha256>.png / .har             live progress only
   reports / assets /         (pointed to by assets table)
   stage_timings / events
```

Key shifts vs. today:
- **Job state lives in SQLite**, not `_jobs`. `_jobs` becomes a *cache* of hot rows + the SSE subscriber bus only.
- **One crawl pass.** Node's Puppeteer crawl is removed; axe-core is injected into the Playwright page. (Node service is retained as a *pure axe-rule + mapping library* called over HTTP per-page with already-rendered HTML, OR embedded — see §7 for the two variants.)
- **CPU auditors run in a process pool**, sized to cores, shared across jobs.
- **All telemetry is rows**, queryable and joinable to runs.

---

## 3. Workstream A — SQLite persistence layer

### 3.1 New module: `ka11y/store/db.py`
Single owner of the connection + schema + write serialization.

```python
# pseudo-API
class Database:
    def __init__(self, path=os.getenv("KA11Y_DB_PATH", "/data/ka11y.db")): ...
    async def init(self):        # PRAGMA journal_mode=WAL; synchronous=NORMAL;
                                 # busy_timeout=5000; foreign_keys=ON; run migrations
    async def write(self, sql, params): ...   # serialized via single writer task
    async def read(self, sql, params): ...    # to_thread, many concurrent OK
    async def tx(self, fn): ...               # batched multi-statement write
```
- WAL + `synchronous=NORMAL` is the right durability/throughput tradeoff for a single box.
- A **single async writer task** drains an `asyncio.Queue[(sql, params, future)]`; all writers `await db.write(...)`. This removes "database is locked" entirely.
- Schema versioning via a `schema_migrations` table + ordered `.sql` files in `ka11y/store/migrations/`.

### 3.2 Schema (v1)

```sql
-- One row per audit job (replaces the _jobs dict as source of truth)
CREATE TABLE runs (
  run_id          TEXT PRIMARY KEY,           -- uuid4
  url             TEXT NOT NULL,
  status          TEXT NOT NULL,              -- queued|running|completed|failed|cancelled
  lang_requested  TEXT, lang_resolved TEXT,
  wcag_level      TEXT,
  params_json     TEXT NOT NULL,              -- the full CombinedRequest (toggles, depth, max_pages)
  max_depth       INTEGER, max_pages INTEGER,
  submitted_at    TEXT NOT NULL,
  run_started_at  TEXT, completed_at TEXT,
  queue_wait_ms   INTEGER, wall_ms INTEGER,
  error_id        TEXT, error_stage TEXT,
  summary_json    TEXT,                        -- {violations, needs_review, passes, score}
  attempt         INTEGER NOT NULL DEFAULT 0,  -- for crash-requeue
  worker_pid      INTEGER,
  output_dir      TEXT
);
CREATE INDEX idx_runs_status   ON runs(status);
CREATE INDEX idx_runs_url      ON runs(url);
CREATE INDEX idx_runs_submitted ON runs(submitted_at DESC);

-- Per-page crawl record (enables page-scoped reporting from DB)
CREATE TABLE run_pages (
  id         INTEGER PRIMARY KEY,
  run_id     TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  page_url   TEXT NOT NULL,                    -- RESOLVED url (post-redirect)
  depth      INTEGER,
  http_status INTEGER,
  crawl_ms   INTEGER,
  snapshot_ref TEXT                            -- asset id of stored DOM snapshot, optional
);
CREATE INDEX idx_run_pages_run ON run_pages(run_id);

-- The full report, compressed. One row per run (latest). zlib(JSON).
CREATE TABLE run_reports (
  run_id      TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
  report_zlib BLOB NOT NULL,
  bytes_raw   INTEGER, bytes_stored INTEGER,
  created_at  TEXT NOT NULL
);

-- Individual findings, denormalized for querying (top-N, by SC, by page).
CREATE TABLE findings (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  page_url    TEXT,
  wcag_sc     TEXT,                            -- "1.4.3"
  level       TEXT,                            -- A|AA|AAA
  status      TEXT,                            -- fail|needs_review|pass
  source      TEXT,                            -- axe|python
  reason_code TEXT,
  selector    TEXT,
  element_json TEXT,                           -- element blob (kept small)
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_findings_run    ON findings(run_id);
CREATE INDEX idx_findings_sc     ON findings(run_id, wcag_sc);
CREATE INDEX idx_findings_status ON findings(run_id, status);

-- Asset registry: bytes on disk, metadata here (Decision #2).
CREATE TABLE assets (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  page_url    TEXT,
  kind        TEXT NOT NULL,                   -- screenshot|ocr_crop|har|dom_snapshot|contrast_region
  rel_path    TEXT NOT NULL,                   -- relative to KA11Y_ASSET_DIR
  sha256      TEXT NOT NULL,                   -- dedupe + integrity
  mime        TEXT, width INTEGER, height INTEGER,
  bytes       INTEGER,
  created_at  TEXT NOT NULL,
  UNIQUE(run_id, rel_path)
);
CREATE INDEX idx_assets_run    ON assets(run_id);
CREATE INDEX idx_assets_sha    ON assets(sha256);

-- Telemetry: one row per fine-grained step (replaces the 4 log files).
CREATE TABLE stage_timings (
  id          INTEGER PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  page_url    TEXT, depth INTEGER,
  stage       TEXT NOT NULL,                   -- image_audit|pipeline|axe_core|...
  sub_stage   TEXT, rule TEXT,
  duration_ms REAL,
  item_count  INTEGER,
  status      TEXT,                            -- ok|error|timeout
  error       TEXT,
  extra_json  TEXT,
  ts          TEXT NOT NULL
);
CREATE INDEX idx_timings_run   ON stage_timings(run_id);
CREATE INDEX idx_timings_stage ON stage_timings(run_id, stage);

-- Job lifecycle / SSE event log (durable progress, survives restart).
CREATE TABLE run_events (
  id        INTEGER PRIMARY KEY,
  run_id    TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  event     TEXT NOT NULL,                     -- stage_start|stage_complete|warning|job_complete...
  data_json TEXT,
  ts        TEXT NOT NULL
);
CREATE INDEX idx_events_run ON run_events(run_id);
```

### 3.3 Retention
- Replace TTL eviction (`store.py:161`) with a **DB retention sweep**: delete `runs` older than `KA11Y_RUN_RETENTION_DAYS` (default 30); `ON DELETE CASCADE` clears children; a paired pass deletes orphaned asset files whose rows are gone. Optional `VACUUM` weekly.
- Hot in-memory cache (`_jobs`) keeps only running + recently-completed runs for fast polling; everything else reads from DB.

---

## 4. Workstream B — Asset store

### 4.1 New module: `ka11y/store/assets.py`
```python
def put_asset(run_id, kind, src_bytes_or_path, page_url=None, mime=None) -> AssetRef:
    # 1. compute sha256
    # 2. rel_path = f"{run_id}/{kind}/{sha256[:2]}/{sha256}.{ext}"
    # 3. write under KA11Y_ASSET_DIR (default /data/assets), atomically (tmp+rename)
    # 4. INSERT into assets (dedupe on (run_id, rel_path))
    # 5. return AssetRef(id, rel_path, url="/api/v1/assets/{id}")
```
- **Content-addressed** path (`sha256`) gives free dedupe — the same logo across 50 pages stores one file.
- Serving endpoint `GET /api/v1/assets/{id}` looks up the row, streams the file with the stored mime; replaces today's `?path=` query-string scheme (`routes.py:324`) which leaks filesystem paths and needs per-job SSRF-style path validation.
- Migrate existing producers: image crawler, OCR crops, rendered-layout screenshots, HAR capture, contrast regions → all call `put_asset` instead of writing into the TTL-swept `output_dir`.

---

## 5. Workstream C — Telemetry → DB

- Keep the **call sites** (`stage_timing.start/stop`, `crawler_timing.time_crawler`, `run_timing.log_run_timing`, step logger) but swap their **sinks** to `db.write` into `stage_timings` / `run_events` / `runs`. One adapter per existing logger keeps the rest of the code untouched.
- File logs become **optional** (`KA11Y_TELEMETRY_FILES=0` to disable) — useful for local debugging, off in prod.
- New analytics endpoints (read-only, served from DB):
  - `GET /api/v1/combined/{run_id}/timings` — rebuilt from `stage_timings` (replaces in-mem version).
  - `GET /api/v1/admin/metrics` — rollups: p50/p95 wall_ms by depth, slowest stages, OCR vs contrast split, failure rate by stage. These are the questions `stage_timing.py`'s docstring poses, now answerable in SQL.

---

## 6. Workstream D — Durable queue + process pool

### 6.1 Queue (no broker)
- `POST` does **not** `create_task`. It `INSERT`s a `runs` row with `status=queued` and returns.
- A single **Dispatcher** asyncio task (started in lifespan):
  1. On boot, `UPDATE runs SET status='queued', attempt=attempt+1 WHERE status='running'` → **crash recovery** (in-flight jobs resume).
  2. Loop: `SELECT ... WHERE status='queued' ORDER BY submitted_at LIMIT (slots_free)`; for each, mark `running`, launch `_run_job_body`.
  3. Respects `KA11Y_MAX_CONCURRENT_JOBS`. Backpressure is natural: queued rows just wait, visibly (`status=queued` is pollable).
- Add `attempt < KA11Y_MAX_ATTEMPTS` (default 2) so a crash-looping URL fails permanently instead of retrying forever.
- Optional `DELETE`/cancel: `POST /combined/{run_id}/cancel` sets `status=cancelled`; worker checks a cancel flag between stages.

### 6.2 Process pool for CPU work
- Add `ka11y/store/cpu_pool.py`: a module-level `ProcessPoolExecutor(max_workers=KA11Y_CPU_WORKERS or cpu_count-1)`.
- Move **pure-Python CPU auditors** (cosine similarity, text parsing, contrast math that isn't already NumPy) from `asyncio.to_thread` → `loop.run_in_executor(cpu_pool, ...)`. Functions must be top-level + picklable; pass plain dicts, not Playwright handles.
- Keep **I/O + Playwright-bound** work on `to_thread`/async (can't pickle a browser).
- Net effect: B4 resolved — OCR/contrast/similarity genuinely parallelize across cores instead of serializing on the GIL.

---

## 7. Workstream E — Crawl unification (biggest perf win)

**Goal:** load each page once. Today `universal_page._crawl_one_url` already renders every page in Playwright and extracts a rich snapshot. axe-core is browser-agnostic JS — it runs in Chromium-via-Playwright exactly as it does in Puppeteer.

### 7.1 Approach (recommended): axe-core injected into the Playwright page
Inside `_crawl_one_url`, after the page is stable and the snapshot is extracted, **before closing the page**:
```python
await page.add_script_tag(path=AXE_MIN_JS)         # node_modules/axe-core/axe.min.js
axe_raw = await page.evaluate(AXE_RUN_JS, {opts})  # axe.run(document, {runOnly: levels})
```
Then map `axe_raw` → findings with the **existing** Node mapper logic ported to Python, OR `POST` the raw axe JSON to a slimmed Node endpoint that only does rule metadata + WCAG mapping (no browser). Either way **Puppeteer never launches** and `crawl.js` BFS is deleted.

- Removes B1 (double crawl) and B2 (serial Node BFS) at once.
- The `snapshot_urls_event` / `snapshot_urls_container` synchronization hack (`runner.py:302`, `stages.py:~1770`) is **deleted** — there's only one crawl, so there's nothing to synchronize.
- Node service shrinks to a stateless `/map-axe-results` + custom-checks library, or is folded into Python via a tiny axe runner. (Custom JS checks in `ka11y-node/src/custom-checks/*` that need a live DOM can also be injected as script tags into the same Playwright page — same pattern.)

### 7.2 Migration safety
- Gate behind `KA11Y_UNIFIED_CRAWL=1`. Run both paths in shadow on a fixture set; diff finding counts per SC (the `evidence-loop.js` / `scripts/test-audits.js` harnesses already exist for this).
- The memory notes a history of axe-coverage regressions at depth (runs `a7a5d98c`, D-1/D-3, R-3). Unification **removes the class of bug** (no more "Node raced past the snapshot") because axe runs in the same loop as the crawl. Keep the depth fixtures (`CRAWLER_FIXTURE_PLAN`) as the regression gate.

### 7.3 If unification must be staged
Fallback interim win (no engine change): parallelize `crawl.js` `boundedBfs` with a `p-limit(PUPPETEER_MAX_CONCURRENT)` worker pool instead of the serial `while`. Recovers B2 alone (~3× axe throughput at depth) while E.1 is built.

---

## 8. Workstream F — API additions (history & durability)

New/changed endpoints, all DB-backed:
- `GET /api/v1/combined/{run_id}` — unchanged contract; reads hot cache → DB fallback (survives restart/TTL). Resolves code-review.md §8 directly.
- `GET /api/v1/combined/history?limit=&offset=&url=&status=` — paginated run list from `runs`.
- `GET /api/v1/combined/{run_id}/timings` — from `stage_timings`.
- `GET /api/v1/assets/{id}` — content-addressed asset serving.
- `POST /api/v1/combined/{run_id}/cancel` — cooperative cancel.
- `GET /api/v1/admin/metrics` — ops rollups.
- SSE `stream` stays in-memory for live runs, but a reconnecting client can **replay** from `run_events` (catch-up before live tail).

---

## 9. Workstream G — Ops, config, observability

- **Env (new):** `KA11Y_DB_PATH`, `KA11Y_ASSET_DIR`, `KA11Y_RUN_RETENTION_DAYS`, `KA11Y_CPU_WORKERS`, `KA11Y_MAX_ATTEMPTS`, `KA11Y_UNIFIED_CRAWL`, `KA11Y_TELEMETRY_FILES`. All documented in `docker-compose.yml` + README.
- **Volumes (compose):** add `ka11y_db:/data` and `ka11y_assets:/data/assets`; both must be **named volumes / EBS**, not bind mounts, and backed up. WAL means back up `ka11y.db` + `-wal` + `-shm` together, or use `VACUUM INTO` for a consistent snapshot.
- **Health:** `/health` reports DB reachable + queue depth + pool saturation.
- **Single-writer + multiple uvicorn workers caveat:** with SQLite you should run **one** uvicorn worker process for writes (the dispatcher must be a singleton). Scale concurrency via the process pool + async, not multiple API processes. (This is the main thing that would push you to Decision-3 "Postgres-ready" later if you outgrow one box.)
- **Tuning defaults for a typical 8-core/16GB box:** `MAX_BROWSERS=3`, `MAX_CONCURRENT_JOBS=3`, `HEAVY_STAGE_CONCURRENCY=2`, `CPU_WORKERS=6`. Validate against `LAWSUIT_SITES_AUDIT_REPORT.md` sites.

---

## 10. Phased rollout

| Phase | Deliverable | Risk | Unblocks |
|-------|-------------|------|----------|
| **P0** | `ka11y/store/db.py` + schema + migrations + single-writer. Wire **writes only** (runs/reports/findings) alongside existing in-mem path (dual-write, read still in-mem). | Low | Everything |
| **P1** | Switch reads to DB; `_jobs` becomes cache. Add `/history`, DB-backed `{run_id}` + `/timings`. Retire TTL→retention sweep. Resolves §8. | Low | History/durability |
| **P2** | Asset store (`assets.py`) + `/assets/{id}`; migrate all asset producers; deprecate `?path=`. | Med | DB-as-source-of-truth for assets |
| **P3** | Telemetry sinks → DB; file logs optional; `/admin/metrics`. | Low | Queryable telemetry |
| **P4** | Durable queue + dispatcher + crash-requeue + cancel. | Med | Crash-safety |
| **P5** | Process pool for CPU auditors. | Med | True CPU parallelism (B4) |
| **P6** | Crawl unification behind `KA11Y_UNIFIED_CRAWL`; shadow-diff; flip default; delete Puppeteer BFS + snapshot-sync hack. | **High** | B1+B2 (the big win) |

P0–P3 are independent of P6 and bank durability/telemetry first. P6 is the high-reward, high-risk finale and is feature-flagged.

---

## 11. Risks & mitigations
- **SQLite write contention** → single serialized writer + WAL + `busy_timeout`; never multi-process writes.
- **DB on the request path failing an audit** → every persistence call wrapped, degrade-not-fail (same discipline as current timing loggers).
- **Process-pool pickling** → only top-level functions, plain-dict payloads; Playwright handles never cross the boundary.
- **Crawl-unification coverage regression** → feature flag + shadow diff on the existing fixture/evidence harnesses + keep depth regression fixtures green (history of D-1/D-3/R-3 regressions).
- **Asset disk growth** → content-addressed dedupe + retention sweep deletes orphaned files with their rows.
- **Backups** → `VACUUM INTO` snapshot or stop-the-world copy of `db + wal + shm`.

---

## 12. Open decisions still needed (please confirm before P6)
1. **Node service fate under unification:** (a) keep a slim stateless Node `/map-axe-results` microservice (least code churn, axe stays in JS), or (b) fully port axe invocation + mapping into Python and retire `ka11y-node`. Recommendation: **(a) first**, measure, then decide on (b).
2. **Custom JS checks** (`ka11y-node/src/custom-checks/*`, the 2.5.x audits): inject as script tags into the unified Playwright page, or keep calling Node per-page with rendered HTML? Recommendation: inject — keeps one page load.
3. **Retention window** default (`KA11Y_RUN_RETENTION_DAYS=30`?) and whether completed-run **assets** get a shorter TTL than the run metadata (metadata is cheap; screenshots aren't).
4. **Auth on history/admin endpoints** — `/history` and `/admin/metrics` expose every audited URL. Do they need an API key / auth gate before exposure?
