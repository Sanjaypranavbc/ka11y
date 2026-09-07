# 5. Full Execution Flow (Code-Level)

Traced for the **primary path**: `POST /api/v1/combined/combined-audit`
(the "run everything" convenience endpoint) through to a completed,
persisted report. Side paths (`/python-audit`, per-rule endpoints, the
narrower `/crawl`/`/pipeline` endpoints, the rule tester) are called out
at the point where they diverge. Every step references the section 4
module documentation that explains the code in depth.

## Step 0 — process startup (once, not per request)

1. `uvicorn ka11y.main:app` imports `ka11y/main.py`
   (`01-OVERVIEW-AND-ENTRYPOINT.md`). In order: `load_dotenv()` →
   `setup_logger()` (creates `logs/`, `03-MODULES-config-utils.md` §
   `config/logger.py`) → `load_config()` (§ `utils/config_loader.py`) →
   builds the `FastAPI` app with `lifespan=lifespan` → attaches
   `_RateLimitMiddleware`, `_SecurityHeadersMiddleware`, `CORSMiddleware` →
   `app.include_router(router)` (§ `07-MODULES-api.md` (A) `api/router.py`,
   which itself mounts `crawl`, `pipeline`, `combined`, `assets`, `rules`,
   `rule_evaluator`).
2. Uvicorn starts serving; on first request, or immediately if uvicorn eagerly
   enters the lifespan, `main.py`'s `lifespan()` context manager runs:
   `store.init_db()` (opens SQLite, runs migrations, starts the writer
   thread — `08-MODULES-store.md` § `db.py`), then
   `asyncio.create_task(_evict_old_jobs())` (in-memory TTL sweep, §
   `combined/store.py`), then `asyncio.create_task(dispatcher.run_dispatcher())`
   and `asyncio.create_task(retention.run_retention_loop())` (§
   `combined/dispatcher.py`, § `store/retention.py`). All three background
   loops now run for the life of the process.

## Step 1 — client submits an audit

`POST /api/v1/combined/combined-audit?url=https://example.com&max_depth=1&wcag_level=AAA`
(query-param convenience route; the JSON-body `/python-audit` route is
identical from here on, just built from a full `CombinedRequest` payload
instead of individual query params).

1. FastAPI validates and constructs `CombinedRequest` (§ `07-MODULES-api.md`
   (B) `combined/models.py`) — every constraint (`max_depth` 0-5,
   `max_pages` capped to 20 by `_cap_max_pages`, `wcag_level` pattern,
   `lang` pattern) is enforced here, before any handler code runs.
2. `routes.submit_combined_audit` (§ (D) `combined/routes.py`) forces every
   `run_*` flag `True` and calls `_admit_run(payload)`.
3. `_admit_run`: generates `job_id = uuid4()`; **calls `assert_public_url(url)`**
   — the SSRF entry-point gate (§ (D), resolves DNS, rejects private/
   loopback/reserved addresses) — raising `HTTPException(400)` immediately
   if the URL is disallowed, **before anything is queued or persisted**;
   seeds a `_jobs[job_id]` hot-cache entry (`status: "queued"`); calls
   `dispatcher.enqueue(job_id, payload)`.
4. `dispatcher.enqueue` (§ (D) `combined/dispatcher.py`): `repo.create_run(...)`
   — **first durable write**, `INSERT OR REPLACE` into SQLite `runs` with
   `status='queued'` and the full serialized `CombinedRequest` as
   `params_json`; `repo.insert_event(job_id, "queued", ...)`; then
   `notify()` — sets the dispatcher's wakeup `asyncio.Event` (or, if the
   dispatcher failed to start, falls straight back to
   `asyncio.create_task(runner._run_job(...))` — the legacy in-process
   path).
5. The route handler returns immediately (**HTTP 202**) with the job dict
   (`status: "queued"`). The client now polls `GET /api/v1/combined/{job_id}`
   or connects to `GET /api/v1/combined/{job_id}/stream` (SSE).

## Step 2 — the dispatcher picks up the job

Running continuously in the background (§ (D) `combined/dispatcher.py`
`run_dispatcher`):

1. Woken by the `notify()` call (or its 2-second poll timeout regardless).
2. `_drain()`: computes free capacity
   (`_MAX_CONCURRENT_JOBS - len(_inflight)`, default 4); `repo.next_queued(free)`
   — fetches queued rows FIFO by `submitted_at`; for our new row,
   `_ensure_hot_entry` is a no-op (the hot entry already exists from step
   1.3); **claims the row synchronously** — `repo.update_run(run_id,
   status="running")` — before spawning anything, so a second dispatcher
   tick can't double-pick it; spawns `asyncio.create_task(_run_tracked(run_id,
   payload, None))`, tracked in `_inflight`.

## Step 3 — `runner._run_job` → `_run_job_body`

(§ (D) `combined/runner.py`.) This is the actual audit, in order:

1. Marks the job `running` in both the hot cache and (via `repo.mark_running`)
   the durable store; checks `repo.is_cancelled(job_id)` (returns early —
   no crawl, no browser — if a client already cancelled it).
2. **Language resolution**: if `payload.lang == "auto"` (the default for
   the query-param route), calls `detect_page_language(url)` (§
   `03-MODULES-config-utils.md` `utils/lang_detector.py`) — its own
   SSRF-guarded HEAD-ish fetch of the target page's first 16KB, reading
   `<html lang="">`; sets `_lang_ctx` (the `contextvars.ContextVar`
   `findings.py` reads for every localized string — inherited automatically
   by every `asyncio.create_task` spawned from here on).
3. Computes the per-job output directory:
   `{output_root}/{domain}_{MMDD_HHMM}_{job_id[:8]}_combined` (created —
   see `12-OUTPUT-FILES.md` for the full tree); creates an
   `ExecutionStepLogger` for structured step logging.
4. `emit_job_plan(job_id, ["image_audit", "media_audit"])` (both stages are
   active since every flag is `True` on this route) — broadcasts the SSE
   `job_plan` event so a connected client's progress bar has its weights.
5. **Launches two tasks concurrently**:
   - `python_task = create_task(_run_python_stages(...))`
   - `node_task = create_task(_fetch_node_findings(...))`
   both awaited together via `asyncio.wait_for(asyncio.gather(python_task,
   node_task, return_exceptions=True), timeout=1800)` (`_JOB_TIMEOUT_SECONDS`).

### Step 3a — Python stages (`_run_python_stages`, § `07-MODULES-api.md` (D) `combined/stages.py`)

1. `needs_crawl = run_media_audit or run_captions_audit or max_depth > 0` —
   `True` here (media audit is active). Calls `_load_universal_snapshot`:
   builds a `CrawlPolicy`, calls `UniversalPageLoader.load(...)` (§
   `04-MODULES-crawler.md` `crawler/universal_page.py`) — this is where the
   **actual Playwright browser work for the multi-page BFS** happens:
   leases a pooled `BrowserContext` (§ `browser_pool.py`), navigates every
   page (`navigate_with_resilience` → DNS preflight + retry, §
   `crawler/navigation.py`; the browser context itself carries the
   `_ssrf_guard.py` route handler installed by `context_factory.new_crawler_context`,
   so **every request the browser makes, including redirects, is
   independently re-validated against private IP ranges** — the crawl-time
   SSRF defense, distinct from step 1.3's one-time entry check), rejects
   cookie banners, runs the big in-page `_COMBINED_EXTRACT_JS` per frame,
   and — critically — calls `ElementContextExtractor.extract_contexts` +
   `SemanticRelationshipEngine.enrich_semantics` per page (§
   `05-MODULES-pipeline.md`'s extractors — this data is captured but, per
   that file's correction note, never actually consumed by a policy engine
   in this run). Saves `universal_snapshot_raw.json`, normalizes via
   `SnapshotNormalizer` (typed `MediaElementData` list), saves
   `universal_snapshot_normalized.json`.
2. Derives `discovered_urls` (deduped page list) and `crawled_pages`
   (success + failure records) from the snapshot.
3. Wraps the snapshot in a pre-resolved `asyncio.Future` (`snapshot_task`).
4. Launches **`_stage_image_audit`** (wrapped in `_heavy(...)` — the
   global 2-slot browser-heavy semaphore) and **`_stage_media_audit_universal`**
   (wrapped in a plain timeout, no semaphore) concurrently via
   `asyncio.gather(..., return_exceptions=True)`.

   - **`_stage_image_audit`** (§ `stages.py`): constructs an
     `OptimizedImageCrawler` (§ `04-MODULES-crawler.md`
     `optimized_crawler.py`), calls `crawl_page(discovered_urls=...)` —
     which drives `optimized.engine.Crawler.run()` (§ `04-MODULES-crawler.md`,
     the ~2,750-line BFS engine: one Chromium process managed by
     `BrowserManager`, a `ContextPool` of recycled contexts, per-page
     `EXTRACT_JS` DOM walk classifying every image element in-browser,
     `_capture_assets` screenshotting/downloading each one) into a private
     `_raw/` scratch directory, then `optimized.adapter.build_image_data`
     copies the captured pixel files into the shared crawl output
     directory and builds `List[ImageData]`. Selects an OCR budget
     (`select_ocr_candidate_paths`, § `03-MODULES-config-utils.md`
     `crawler_settings.py`), groups images by page language
     (`_ocr_lang_for_page`), and runs `OCRPreprocessing.scan_directory`
     per language group (§ `09-MODULES-text-classifier-i18n.md`
     `text_detector.py` — the persistent OCR thread pool, EasyOCR or
     PaddleOCR per `_select_ocr_reader_class`, each detection scored via
     `contrast_analyser.analyze_text_region` and
     `extract_color.extract_colors_from_mask`). Builds the contrast report
     (`findings._build_contrast_report`) and runs
     `OCR_RESULT_CONVERTERS` (1.4.3/1.4.6 findings). Runs
     `AltTextAccessibilityAuditor.generate_audit_report` (§
     `06-MODULES-rules.md` `alttext.py` — the ~500-line per-image WCAG
     1.1.1/4.1.2/1.4.5 decision tree) and `IMAGE_AUDIT_RECORD_CONVERTERS`.
     Returns `(findings, contrast_report, image_audit_report)`.
   - **`_stage_media_audit_universal`**: awaits the already-resolved
     `snapshot_task`, runs `MediaAuditor.generate_audit_report` (§
     `06-MODULES-rules.md` `media_auditor.py` — the 5-gate 1.2.1 decision
     tree, plus 1.2.2/1.2.3/1.4.2, including the Deepgram-API-backed
     `quality_engine.evaluate_transcript_quality`/`evaluate_captions_quality`
     calls for Gate 5/Gate 6), converts via `_media_to_findings`.
5. Returns a `PythonStagesResult` (`findings`, `contrast_report`,
   `image_audit_report`, `crawled_pages`).

### Step 3b — Node/axe-core (`_fetch_node_findings`, concurrent with 3a)

POSTs `{NODE_BASE_URL}/api/v1/analyse-url-flat` (the Node service, out of
scope for this deep-dive, per the agreed scope) with a scaled timeout
(`_node_http_timeout`, base + per-page); on any failure, returns empty
findings + a warning rather than raising — the whole job degrades to
Python-only results, never fails because of Node.

### Step 3c — merge and build the report (back in `_run_job_body`)

1. Both tasks resolve (or time out — `_JOB_TIMEOUT_SECONDS`, cancelling
   both). If Python's findings end up empty for any reason, **raises**
   (Python is the required source of truth).
2. Filters both finding lists by `_allowed_levels(wcag_level)`.
3. `all_findings = await run_cpu(_merge_findings, node_findings,
   python_findings)` (§ `08-MODULES-store.md` `cpu_pool.py` — offloaded to
   a process pool if `$KA11Y_CPU_WORKERS` is configured, else a thread) —
   deduplicates by `(wcag_sc, status, element_identity)`, Python winning
   collisions.
4. Applies `effective_filter` (only non-`None` for the per-rule endpoints,
   § (F) — not this route).
5. Sorts `fail` → `needs_review` → `pass`.
6. `report = _build_report(url, all_findings, ...)` (§ `07-MODULES-api.md`
   (D) `combined/report.py`) — stamps `finding_id`s, buckets by status,
   builds every summary/by_page/by_wcag_sc structure, computes the score.
7. **`register_report_assets(job_id, report)`** (§ `08-MODULES-store.md`
   `store/assets.py`) — every on-disk image the report references is
   content-addressed (SHA-256, deduplicated) into `KA11Y_ASSET_DIR` and the
   report's `image_url`/`element.image_src` fields are rewritten to
   `/api/v1/assets/{id}`.
8. **Writes `<output_dir>/combined_report.json`** — the first durable
   artifact on disk (see `12-OUTPUT-FILES.md`).
9. Truncates the in-memory `passes` array to 100 if larger.
10. Marks the job `completed` in the hot cache and durable store
    (`repo.save_report`, `repo.save_findings`, `repo.save_pages`,
    `repo.mark_completed`); `repo.insert_event(job_id, "job_complete", ...)`.
11. If `payload.email` is set: renders a PDF (`utils/report_pdf.py`, §
    `03-MODULES-config-utils.md` — leases a pooled Chromium page and calls
    `page.pdf()`) and sends the report email
    (`utils/report_mail.py`/`gmail_sender.py`) via a background thread —
    only after the run is fully persisted.
12. Logs run timing (`utils/run_timing.log_run_timing`) and the
    stage-timing summary; broadcasts the final `job_complete` SSE event.
13. **On any exception** anywhere in steps 3-12: captures the traceback,
    generates an opaque `error_id`, marks the job `failed` with only the
    generic message + `error_id`/`error_stage` exposed to the client,
    still logs timing, broadcasts `job_failed`.

## Step 4 — client retrieves the result

`GET /api/v1/combined/{job_id}` (§ (D) `combined/routes.py`
`get_combined_audit`): hot-cache lookup (falls back to
`_job_from_db`/SQLite if evicted or the process restarted); snapshotted
under the per-job lock; `_finalize_job_view` rewrites any still-bare image
paths and overlays stored manual-review decisions
(`report.apply_reviews`) before returning. The client can instead have
been streaming `GET /api/v1/combined/{job_id}/stream` the whole time and
simply receives the terminal `job_complete` SSE event with no extra poll
needed.

## Divergent paths (same underlying machinery)

- **`POST /python-audit`**: identical to the above except the caller
  supplies the full `CombinedRequest` JSON body directly (can disable
  individual `run_*` flags) — same `_admit_run` → dispatcher → `_run_job_body`
  path.
- **Per-rule endpoints** (`POST /api/v1/rules/{rule_id}/run`, § (F)
  `rules/run_router.py`): builds a `CombinedRequest` with every flag `False`
  except the one(s) `RULE_FLAGS[rule_id]` names — **for 13 of the 19
  registered `rule_id`s, that flag doesn't exist on `CombinedRequest` and
  is silently dropped**, so the job runs with *every* flag `False` and
  produces zero findings regardless of the requested rule (documented at
  length in `07-MODULES-api.md` (F)). Also **bypasses the durable
  dispatcher** — calls `runner._run_job` directly via `asyncio.create_task`,
  so these jobs are not crash-recoverable and don't appear in the `runs`
  table's normal flow the way dispatcher-submitted jobs do (though
  `_run_job_body` itself does still call `repo.mark_running`/`mark_completed`,
  so the row does get created and updated — just never queued/dispatched
  through `dispatcher.py`).
- **`POST /api/v1/test/rule`** (§ (E) `rule_evaluator.py`): for
  `wcag_1_1_1`/`wcag_1_4_3`/`wcag_1_4_5`/`wcag_1_4_6`/`wcag_1_4_11`/
  `wcag_4_1_2`/`wcag_1_2_1`/`wcag_1_2_2`, calls `_stage_image_audit`/
  `_stage_media_audit_universal` **directly** (bypassing
  `_run_python_stages`, `runner.py`, the dispatcher, and Node entirely),
  under a single shared, fixed `job_id="rule_evaluator"`; for
  `wcag_3_2_3`/`wcag_3_2_4`/`wcag_3_1_3`/`wcag_2_4_10`, proxies straight to
  the Node service; for anything else, `400`.
- **`POST /api/v1/crawl/`** and **`POST /api/v1/pipeline/`** (§ (E)):
  synchronous (no job/polling model at all) — crawl → OCR → alt-text audit,
  return the full result in the HTTP response body directly. No SSRF guard
  call visible in either handler beyond whatever `get_output_dir`'s
  hostname-regex validation provides incidentally (§ (C)
  `dependencies.py`) — neither calls `assert_public_url` explicitly.

## Background loops (run continuously, independent of any single request)

- `dispatcher.run_dispatcher()` — drains `queued` rows every ≤2s.
- `store.retention.run_retention_loop()` — deletes runs older than
  `$KA11Y_RUN_RETENTION_DAYS` (default 30) every hour, pruning asset files.
- `combined.store._evict_old_jobs()` — removes completed/failed jobs from
  the **in-memory** hot cache (and their on-disk `_combined` directory)
  after `_JOB_TTL_SECONDS` (1 hour), every 5 minutes.

## CLI args / config propagation summary

There is no CLI for the service itself (§ `01-OVERVIEW-AND-ENTRYPOINT.md`).
Every tunable enters through one of: an HTTP request field validated by a
Pydantic model (`CombinedRequest` etc.), an environment variable read
directly by the relevant module (`$KA11Y_MAX_CONCURRENT_JOBS`,
`$KA11Y_DB_PATH`, `$KA11Y_ASSET_DIR`, `$KA11Y_OCR_WORKERS`,
`$DEEPGRAM_API_KEY`, dozens more — each documented at its point of use in
section 4), or `config/config.yml`/`config/universal.yml` loaded once via
`utils.config_loader.load_config()` and read through
`utils.crawler_settings.py`'s typed accessors.

## Important side effects, consolidated

- **File I/O**: see `12-OUTPUT-FILES.md` for the complete inventory.
- **Network**: outbound Playwright navigation (SSRF-guarded at both the
  entry point and per-request during the crawl); the Node service HTTP
  call; the Deepgram transcription API call; SMTP for report email;
  downloaded media files for transcript quality checks.
- **Subprocess**: none from Python directly for the audit path — Chromium
  is driven via Playwright's protocol, not `subprocess`; the optional
  `ProcessPoolExecutor` (`cpu_pool.py`) spawns worker *processes* (via
  `multiprocessing`/`concurrent.futures`, not raw `subprocess`) only if
  `$KA11Y_CPU_WORKERS` is set.
- **Global/module state mutated**: `_jobs` (in-memory hot cache), the
  SQLite database, `_SNAPSHOT_CACHE` (rule-evaluator only), several
  thread-local OCR reader caches, the shared browser pool's warm Chromium
  instance.
- **Logging**: every stage emits through the shared `KaLogger` (console +
  rotating file) and, separately, structured JSONL step logs
  (`ExecutionStepLogger`) and stage-timing rows (SQLite `stage_timings` +
  optional `logs/timings/<run_id>.jsonl`).
