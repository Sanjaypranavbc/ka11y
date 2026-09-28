# ka11y-python — Code Quality, Maintainability & Debugging Review

Date: 2026-09-27 · Branch: `refactor_code` (HEAD `1b19bf6`) · Scope: `ka11y-python/` only
Status: **analysis only — no code changed.** Every claim below was verified by reading the
code or running a command; nothing is inferred from file names.

Baseline measured before any change:

| Metric | Value |
|---|---|
| Python source | 34,548 lines in `ka11y/` (146 modules) + `enrich_audit.py` (775) |
| Tests | 634 collected · **612 passed, 22 failed** (all 22 are environment coupling, see §10) · 150 s |
| Ruff (default rules) | 49 findings · 27 auto-fixable (25 unused imports, 18 late imports, 2 unused vars, 1 shadowed import) |
| Type-hinted `def`s | 719 with a return annotation, 91 without |
| `print()` in library code | 71 (alttext 28, text_detector 16, engine 15, extract_color 11, logger 1) |
| Loggers | 52 via `setup_logger`, **9 via stdlib `logging.getLogger`** (those messages are dropped, see §8) |
| `except Exception: pass/return None` | 38 sites |
| Distinct `KA11Y_*` env vars read | 85, across 25 files |

---

## 1. Architecture (as it actually runs)

```
HTTP (uvicorn --proxy-headers)
 └─ ka11y/main.py            FastAPI app + 5 middlewares + lifespan (tracing, SQLite, PG, eviction,
 │                           dispatcher, retention)                       ← composition root
 └─ api/router.py            /api/v1  aggregates 9 routers
     ├─ auth/router.py          OIDC + password sign-in, sealed cookies         (public)
     ├─ api/v1/combined/        THE ENGINE — submit / poll / SSE / review / export
     ├─ api/v1/audits.py        ownership-aware history + artifact links        (PG)
     ├─ api/v1/admin.py         admin console read models                        (PG + SQLite)
     ├─ api/v1/assets.py        content-addressed asset serving  (+ /admin/metrics, mis-homed)
     ├─ api/v1/rules/           WCAG catalogue + per-rule job launchers (partly BROKEN, §5)
     ├─ api/v1/rule_evaluator   /test/rule single-rule tester
     └─ api/v1/{crawl,pipeline} DEPRECATED legacy 3-step endpoints (UI does not call them)
```

The combined-audit request path (one job):

```
POST /combined/combined-audit
  routes._admit_run        SSRF check → _jobs[job] (hot cache) → PG audit_jobs row → dispatcher.enqueue
  dispatcher.enqueue       SQLite runs row status=queued → notify()
  dispatcher._drain        picks queued rows FIFO, cap KA11Y_MAX_CONCURRENT_JOBS → runner._run_job_body
  runner._run_job_body_inner
     detect_page_language → output dir → step logger → emit_job_plan
     ┌ asyncio.gather ──────────────────────────────────────────────────────────────┐
     │ stages._run_python_stages                    runner._fetch_node_findings      │
     │   _heavy(_load_universal_snapshot)  ← ONE       POST node:/analyse-url-flat   │
     │     UniversalPageLoader.load (browser pool)                                   │
     │     SnapshotNormalizer                                                        │
     │   gather( _stage_image_audit,  _stage_media_audit_universal )                  │
     │     adapter → OCR groups (EasyOCR|Paddle) → converters                          │
     └───────────────────────────────────────────────────────────────────────────────┘
     site_analysis (≥2 pages) → pdf_audit → level filter → _merge_findings (python wins)
     _build_report → register_report_assets → Gemini enrich (enrich_audit.py, thread)
     write combined_report.json → _jobs update (lock) → SQLite save_report/findings/pages/mark_completed
     → PG mark_completed → storage.upload_job_artifacts (S3|local) → optional e-mail → timing logs
     → SSE job_complete → _close_subscribers
GET /combined/{id}        hot cache (lock snapshot) → _finalize_job_view (image URL rewrite, manual-review
                          overlay, technique re-tag + strip)  |  fallback: SQLite runs + run_reports
```

Layering, verified from imports (`grep -rhoE "^from ka11y\." …`):

```
L0  config/  i18n/  preprocessor/                        (no internal deps)
L1  utils/  store/  storage/  db/  observability/  auth/
L2  crawler/                                              (uses accessibility/pipeline extractors)
L3  text_detector/  accessibility/rules/  accessibility/pipeline/  [classifier/ — nobody imports it]
L4  api/v1/combined/  api/v1/*.py
L5  api/router.py  main.py
```

**Inverted dependency (L3 → L4):** `accessibility/rules/documents/pdf_audit.py`,
`accessibility/rules/media/video_analysis.py` and `media/animated_images.py` import
`_make_finding` from `api/v1/combined/findings.py`. The finding factory is domain logic that
lives in the API package; the rule layer now depends on the HTTP layer (lazy imports hide the
cycle, they don't remove it).

## 2. Module responsibilities (and where they blur)

| Module | Stated purpose | Actual state |
|---|---|---|
| `main.py` (402) | app wiring | also hosts 4 middleware classes (rate limit, body cap, security headers, https redirect) — a `middleware.py` would be clearer; hard-coded CORS origins incl. an EC2 hostname; duplicate `CORSMiddleware` import |
| `combined/routes.py` (979) | thin HTTP handlers | also: SSRF classifier (duplicates `crawler/_ssrf_guard.py`), a dead `build_ssrf_route_handler`, image-path containment logic, view shaping. Not thin. |
| `combined/runner.py` (972) | orchestrate one job | `_run_job_body_inner` is ~550 lines doing 12 distinct things (§13) |
| `combined/stages.py` (974) | per-stage coroutines | `_stage_image_audit` ~350 lines: adapter, OCR budgeting, language grouping, category mapping, OCR, saving, 2 converter loops, animated-image scan, metrics |
| `combined/findings.py` (1382) | finding factory + converters | fine in purpose; large because 9 converters each rebuild `element` kwargs |
| `combined/store.py` | hot cache + SSE bus + eviction | OK; lock discipline documented but not followed by its callers (§6) |
| `combined/dispatcher.py` | durable queue | OK; contains a dead try/except (§5-B10) |
| `store/` (SQLite) | run queue, reports, findings, assets, timings, reviews | OK, clear |
| `db/` (PostgreSQL) | users, sessions, ownership, history, report pointers, crashes | OK, clear; **second persistence layer for the same job** |
| `storage/` (S3/local) | artifact bytes | OK, clear |
| `crawler/universal_page.py` (1639) | one browser pass | ~500 lines are inline JS strings; `crawler/js/universal_extract.js` exists but **nothing loads it** |
| `crawler/image_extractor.py` (1862) | image DOM extraction + asset capture | ~900 lines are the `EXTRACT_JS` string |
| `crawler/optimized/engine.py` (966) | standalone CLI crawler | CLI/legacy only; tests still import it |
| `crawler/optimized/optimized_crawler.py` | "drop-in AsyncImageCrawler" | now only adapts raw docs to `ImageData`; its `crawl_page` no longer crawls in the live path |
| `text_detector/text_detector.py` (902) | OCR driver | 77-line commented-out old `detect_text_in_image`; 16 `print()`; loads config + logs at import |
| `accessibility/rules/non_text/alttext.py` (1726) | 1.1.1/1.4.5/1.4.11/4.1.2 checks | `generate_audit_report` is 540 lines; 28 `print()` in `_print_summary` |
| `accessibility/pipeline/` | decision-policy engine | reachable only through two extractors used by the crawler; engine/router/policies are dormant (`KA11Y_UNIVERSAL_PIPELINE_CONTEXTS=0`) |
| `classifier/classifier.py` (737) | CLIP image classifier | **zero importers anywhere** (ka11y, tests, scripts) |
| `api/v1/{crawl,pipeline}.py` + `dependencies.py` + `models/{crawl,pipeline}.py` | legacy endpoints | deprecated, near-duplicates of each other, UI never calls them |
| `utils/` | 17 helpers | mixed bag: config, timing ×3, report writers ×3, mail ×2, url, soup, lang, not_implemented |

## 3. Data flow — the important shapes

* **Request:** `CombinedRequest` (pydantic, validated). Good.
* **Job record:** `_jobs[job_id]` is an untyped `dict` with ~20 ad-hoc keys
  (`status, stages, warnings, warning_details, result, output_dir, step_log_path, step_summary_path,
  html_snapshots, universal_crawler_duration_s, universal_warning_path, plan, run_started_at, error_id,
  error_stage, artifacts, _created_at …`). Written from 6 modules. No schema; `JobStatusResponse`
  covers only a subset.
* **Finding:** a `dict` produced by `_make_finding` (~25 keys). Every downstream step
  (`_merge_findings`, `_build_report`, `apply_reviews`, `annotate_findings`, `save_findings`,
  exports) re-derives structure from key names.
* **Report:** `dict` from `_build_report`; mutated in place afterwards by enrichment, image-URL
  rewriting, review overlay, technique re-tagging. The hot-cache report object is shared with
  every GET handler (`dict(snapshot)` is a shallow copy — `job["result"]` is the same object).

## 4. External systems

| System | Where | Timeout | Retry | Failure mode |
|---|---|---|---|---|
| Chromium (Playwright) | `crawler/browser_pool.py` | per-stage `wait_for` | relaunch on disconnect | stage degrades (warning) |
| Node axe-core | `runner._fetch_node_findings` | base+per-page, floor 300 s | none | Python-only report + warning |
| EasyOCR / PaddleOCR | `text_detector/` | none (thread pool of 4) | none | per-image try/except |
| Gemini (google-genai) | `enrich_audit.py` | 60 s http | yes (retries counted) | static reason/fix fallback |
| Deepgram | `rules/media/quality_engine.py` | — | — | not reviewed in depth |
| SMTP (Gmail) | `utils/gmail_sender.py` | default socket | none | logged, job stays completed |
| PostgreSQL | `db/engine.py` (async SQLAlchemy, pool 5+5, pre-ping) | driver default | none | every write best-effort |
| SQLite | `store/db.py` (single writer thread, WAL) | busy 5 s | none | hot-path writes swallowed |
| S3 / local disk | `storage/backends.py` | boto default | boto default | best-effort |
| Arize / Phoenix OTel | `observability/` | — | — | no-op spans |
| Filesystem | `output/<domain>_<ts>_<id>_combined/` | — | — | TTL rmtree after 1 h |

## 5. Bugs and reliability defects (verified)

Severity: CRITICAL / HIGH / MEDIUM / LOW. "B-n" ids are referenced later.

**B1 [HIGH] Per-rule job endpoints run nothing and fail every time.**
`api/v1/rules/run_router.py:20-40` `RULE_FLAGS` names 13 flags (`run_form_audit`,
`run_label_in_name_audit`, `run_target_size_audit`, …) that no longer exist on `CombinedRequest`
(`combined/models.py` has only `run_ocr`, `run_image_audit`, `run_media_audit`, `run_captions_audit`).
Pydantic v2 ignores unknown kwargs, so `POST /rules/3.3.1/run` (and 12 others) creates a job with
every stage off → `runner.py:549` raises `RuntimeError("All audit sources failed")` → job `failed`.
The same module also bypasses the durable queue and PG ownership (`asyncio.create_task(_run_job…)`),
uses status `"pending"` that no reader expects, and defaults `max_pages=50` which the model silently
caps to 20. *Suggested:* delete the 13 dead entries, route the 6 live ones through
`routes._admit_run` with `success_criteria_id`, or remove the router if the UI never needs it (it
doesn't call it today).

**B2 [HIGH] A job can be stuck `running` forever.**
`runner.py:430-475`: status is set to `running` and `detect_page_language`, `load_config`,
`mkdir`, `ExecutionStepLogger(...)` all execute *before* the `try:` at line 476. Any exception
there escapes `_run_job_body_inner`; `dispatcher._run_tracked` only logs "crashed". SQLite row and
hot entry stay `running`, SSE clients hang, and on restart the row is re-queued and re-run. Today
`detect_page_language` swallows its own errors, so the live trigger is disk/permission errors on
`output_dir.mkdir` or the step-log directory. *Suggested:* move everything after the status flip
into the `try`, and have `_run_tracked` mark the run failed as a last resort.

**B3 [HIGH] Cross-tenant read of any audit by id; global history listing.**
`_assert_can_view` is enforced only on `/{job_id}/export` and `/{job_id}/findings/{id}/review`
(`routes.py:558,690`). `GET /combined/{job_id}`, `/timings`, `/stream`, `/reviews`, `/image`,
`POST /{job_id}/cancel` and `POST /{job_id}/rerun` accept any signed-in user. `GET /combined/history`
(`routes.py:464`) lists **every** run in the SQLite store with URLs, for every user. In a deployment
shared between Blue Caffeine and Kao this is an authorization gap. UUIDs are unguessable, but
`/combined/history` hands them out. *Suggested:* apply `_assert_can_view` to every `{job_id}` route;
either scope `/combined/history` through `audit_repo` or remove it (the UI uses `/audits/history`).

**B4 [MEDIUM] `/api/v1/admin/metrics` is not admin-only.**
It is declared in `api/v1/assets.py:53` and mounted with `require_user`, not on the admin router
(`require_admin`). Exposes failure URLs and throughput to any user. *Suggested:* move it into
`admin.py` (or delete: `admin.py` already has richer stats).

**B5 [MEDIUM] Enqueue failure leaves a job `queued` forever with no error.**
`repo.create_run` swallows its own exception (`store/repo.py:94`), so the `try/except` in
`dispatcher.enqueue` (line 110-124) can only trigger on `insert_event`. A failed INSERT means the
dispatcher never sees the row; the hot entry says `queued` indefinitely. *Suggested:* let
`create_run` raise for this one caller (it is the only write whose failure must not be silent), and
have `_admit_run` mark the hot entry failed / return 503.

**B6 [MEDIUM] Cancellation is half-implemented.**
`runner.py:438-443`: if the job is already cancelled, the hot status is set but nothing is written
to SQLite (`update_run` already happened in the route — fine) and no SSE terminal event is sent, so
`/stream` clients wait on keepalives. Nothing inside `_run_python_stages` checks `is_cancelled`
"between stages" as the route docstring promises. Cancelled jobs are also never evicted from memory
(`store._evict_old_jobs` only evicts `completed|failed`). Cancel in the `_jobs` hot cache is written
without the per-job lock.

**B7 [MEDIUM] Shared job id and unbounded cache in the rule tester.**
`api/v1/rule_evaluator.py:42` uses one `JOB_ID = "rule_evaluator"` for every concurrent request, so
`_jobs["rule_evaluator"]["stages"]` interleaves across users, and `_stage_complete`'s "stage not
found in running state" warnings fire. `_SNAPSHOT_CACHE` grows per distinct URL with no bound, and
cached snapshots reference `html_snapshot` paths inside a `TemporaryDirectory` that has already been
deleted. It also returns raw exception text to the client (`detail=f"...{exc}"`, line 209) while
every other route scrubs internals behind an `error_id`.

**B8 [MEDIUM] Import-time `load_dotenv()` couples the test suite to the developer's `.env`.**
`main.py:21` runs `load_dotenv()` at import. The first test module that imports `ka11y.main` injects
`DATABASE_URL=…@postgres:5432` and the https redirect URI into `os.environ`; `test_auth.py`'s
`skipif(not DATABASE_URL)` then no longer skips, PG resolution fails ("failed to resolve host"), auth
returns 503, and 22 tests fail (`308 == 302` is `KA11Y_FORCE_HTTPS` defaulting on from the https
redirect URI). This is the whole 22-failure baseline. Production is unaffected (compose passes env
explicitly). *Suggested:* move `load_dotenv()` to the uvicorn entry (`if __name__ == "__main__"` /
a `run.py`) or guard it with `PYTEST_CURRENT_TEST`, and make conftest clear `DATABASE_URL`.

**B9 [LOW] Two independent concurrency caps on one resource.**
`runner._get_job_semaphore` (per-loop `Semaphore(KA11Y_MAX_CONCURRENT_JOBS)`) is used by the legacy
`_run_job` path; `dispatcher._inflight` enforces the same number for the queue path. With both
paths live (fallback + `run_router`), the effective cap is up to 2×. `runner.py:332` also reads the
private `sem._value`.

**B10 [LOW] Miscellaneous.**
`runner._stamp_job_outcome` checks status `"timeout"` which is never assigned (timeouts become
`failed`). `stage_events._stage_complete` clears throttle keys for phases `crawl|ocr|transcribe` but
the image stage emits `alt_audit`, so `_progress_last_emit` leaks one key per job.
`runner.py:971-972` two `await asyncio.sleep(0)` with no comment. `combined/__init__.py` re-exports
eight `_private` names as the package API. `submit_python_audit`'s docstring advertises form and
label-in-name audits that were removed.

## 6. Maintainability issues

1. **Three sources of truth for one job** (`_jobs` dict, SQLite `runs`, PG `audit_jobs`), written in
   sequence by the runner with best-effort semantics. Any reader has to know which store answers
   which question (hot status → dict; queue → SQLite; ownership → PG). This is the single largest
   cognitive-load item and it is *documented* nowhere except scattered comments.
2. **Untyped job and finding dicts** (§3). A `JobStatus` enum and a `JobRecord` dataclass/TypedDict
   would make 6 modules' writes checkable.
3. **Status strings** `queued|pending|running|completed|failed|cancelled|timeout` are literals in
   14 files; `admin.py` even carries an alias table (`_STATUS_ALIAS`) to normalise them.
4. **Configuration in three places:** `os.getenv` at import in 25 files (85 vars),
   `ka11y/config/config.yml` **and** `<repo>/config/universal.yml` (the loader prefers the latter
   when present — so local dev and Docker read *different files*; today the drift is harmless
   because the two extra keys have equal defaults, but the 770-line `checks:` section of
   `universal.yml` is read by nobody: `get_check_config_value` has zero callers), plus
   `auth/config.py` and `storage/config.py` which are the good pattern.
5. **Lock discipline is aspirational.** `store._get_job_lock` exists and `routes`/`runner` use it,
   but `stage_events`, `stages`, `dispatcher`, `run_router` and `rule_evaluator` mutate `_jobs[...]`
   without it. Either the lock matters everywhere or it should go.
6. **The finding factory lives in the API layer** (§1 inversion).
7. **Legacy paths kept alive:** `crawl.py`/`pipeline.py`/`dependencies.py` (deprecated, UI-unused),
   `_run_job` legacy launcher, `OptimizedImageCrawler` "crawler" that no longer crawls,
   `optimized/engine.py` CLI, `media_crawler.py` (only a model left), `classifier/` (unused),
   `crawler/js/universal_extract.js` (unused), `accessibility/pipeline` engine (dormant).

## 7. Debugging issues

* A failed job gives the operator an `error_id`; the traceback is in `logs/KAC_<date>.log`
  **only if** the module logs through `setup_logger`. The 9 stdlib loggers (`browser_pool`,
  `rule_evaluator`, and 7 others) have no handler → INFO dropped, WARNING+ to stderr only.
* `job_id` is embedded in message text in ~40 different formats (`[combined] job %s:`,
  `job {job_id}`, `run %s`, `(job=%s kind=%s)`); nothing can filter a log by job.
* Timing exists in four parallel systems: `utils/run_timing.py`, `utils/stage_timing.py`,
  `utils/crawler_timing.py`, `ExecutionStepLogger` step logs — plus OTel spans. They mostly agree
  but each has its own file/table.
* Errors inside `except: pass` at `runner.py:442,458` (cancel check, crawler_timing) and 36 others
  hide the root cause when something finally goes wrong.

## 8. Logging gaps

* No structured fields anywhere (`extra=` count: 0). The `KaLogger.process` adapter already
  merges `extra`; adding `job_id` there is a two-line change.
* Mixed f-string (76) and `%` (90) formatting; f-strings defeat lazy formatting and level filtering.
* Sensitive-data check: no secrets logged (SMTP password, session secret, API keys are never
  formatted into messages). `.env` is not tracked by git. `.env.example` does embed real staff
  e-mail addresses in `KA11Y_ALLOWED_EMAILS` (PII in a template).
* `setup_logger` picks the file name from the *start-up* date; a long-running process writes to
  yesterday's file (RotatingFileHandler, not Timed). Minor.
* Import-time side effects: `main.py`, `text_detector.py`, `utils/config_loader.py` all execute
  `load_config()`/log lines when imported.

## 9. Error-handling gaps

Boundary review:

| Boundary | State | Gap |
|---|---|---|
| HTTP → job | 4xx validated by pydantic; SSRF check | authz missing on most job routes (B3) |
| Job orchestration | fail path writes 3 stores + crash upload | pre-`try` window (B2); enqueue (B5); cancel (B6) |
| Browser | pool recovers from disconnect; per-stage timeouts | stage failure returns `[]` silently to the merge; only a warning string tells the user coverage dropped |
| Node | timeout scaled; failure → warning | none |
| OCR | per-image try/except inside thread pool | no per-image timeout; a hung reader hangs the stage until `_STAGE_TIMEOUT_SECONDS` (1200 s) |
| Gemini | best-effort, thread | fine |
| SQLite | writes swallowed by design | `create_run` should not be (B5) |
| PG | writes swallowed by design | `get_owner`/`list_reports` *do* raise → a PG outage turns `/export` into a 500 while the rest degrades |
| S3 | best-effort | fine |
| SMTP | logged | fine |

## 10. Testing gaps

* 634 tests, good coverage of converters, contrast, alt-text rules, crawler helpers, storage, store.
* **No test** for: `dispatcher._drain`/`enqueue` fallback, `_evict_old_jobs`, `cancel`, `rerun`
  (one exists but fails on env), authorization on job routes, `run_router` (would have caught B1),
  `rule_evaluator` concurrency, `_run_job_body_inner` failure path writing all three stores.
* The 22 baseline failures are all B8 (dotenv leakage); the suite is green only on a machine
  without a `.env` or with PostgreSQL reachable at host `postgres`. Memory notes confirm the 5
  `test_api_smoke` failures pre-date this branch.
* `pyproject.toml` `addopts` always writes an HTML report; there is no ruff/mypy configuration.

## 11. Dead-code candidates

| Candidate | Evidence | Class |
|---|---|---|
| `ka11y/classifier/` (737 lines) | zero importers in `ka11y/`, `tests/`, `scripts/` | **LIKELY DEAD** (confirm with git log intent) |
| `crawler/js/universal_extract.js` | zero references | **SAFE TO REMOVE** |
| `text_detector.py:194-290` commented-out `detect_text_in_image` | 77 commented lines | **SAFE TO REMOVE** |
| `config/logger.py` `log_info/log_warning/…` wrappers | zero callers | **SAFE TO REMOVE** |
| `routes.build_ssrf_route_handler`, `_BLOCKED_NETWORKS`, `_ip_is_blocked`, `_is_non_public_ip` | only self-referenced; live guard is `crawler/_ssrf_guard.install_ssrf_guard` via `context_factory` | **SAFE TO REMOVE** (fold `assert_public_url` onto `_ssrf_guard._host_is_blocked`) |
| `run_router.RULE_FLAGS` 13 dead entries; `models/pipeline.py` 5 dead flags | fields do not exist | **SAFE TO REMOVE** |
| `api/v1/crawl.py`, `pipeline.py`, `dependencies.py`, `models/crawl.py`, `models/pipeline.py` | `deprecated=True`, UI has no caller | **LIKELY DEAD** — needs your confirmation no external client uses them |
| `runner._run_job` + `_get_job_semaphore` | only the enqueue fallback and `run_router` | **UNCERTAIN** — tied to B1/B9 decision |
| `universal.yml` `checks:` section (~770 lines) | `get_check_config_value` has no callers | **LIKELY DEAD** config |
| `accessibility/pipeline/{decisions,router,runners,pipeline_stage}` | dormant behind `KA11Y_UNIVERSAL_PIPELINE_CONTEXTS`; has tests | **UNCERTAIN** — product decision |
| `crawler/optimized/engine.py` CLI | tests import it; docs say CLI only | **ACTIVE (CLI)** |
| `PythonStagesResult` import in `runner.py`, `repo.time`, `assets.repo`, 7 `engine.py` imports, 5 policy imports | ruff F401 | **SAFE TO REMOVE** |

## 12. Duplication

* SSRF classification: `routes.py:55-107` vs `crawler/_ssrf_guard.py:70-186` (same CIDR list,
  same semantics).
* Image-URL rewriting: `runner.py:663-685` and `routes._inject_image_urls` are the same loop.
* Severity/status alias tables: `db/audit_repo._SEVERITY_ALIAS`, `admin._SEVERITY_ALIAS`,
  `admin._STATUS_ALIAS`.
* Contrast report builder: `api/v1/pipeline.extract_contrast_report` vs
  `findings._build_contrast_report`.
* `crawl.py` vs `pipeline.py` (≈180 lines each, same three steps).
* `_now()` ISO helpers in 6 modules; `_parse_iso`/`_parse_ts` in 3.
* Per-loop lazy singleton pattern hand-rolled 5 times (`_LazyAsyncLock`, `_get_job_lock`,
  `_get_job_semaphore`, `_get_wakeup`, `browser_pool.get_pool`, `db.engine` loop id).

## 13. Overly large functions

| Function | Lines | Distinct responsibilities |
|---|---|---|
| `runner._run_job_body_inner` | ~550 | mark running · cancel check · language · output dir · plan · gather engines · site analysis · PDF audit · level filter · merge · build report · assets · URL rewrite · enrichment · write file · slim passes · 3× persist · upload · e-mail · timing · SSE · failure path (writes 4 places) |
| `alttext.AltTextAccessibilityAuditor.generate_audit_report` | 540 | per-image loop with 6 SC checks inline + CSV/JSON writing + summary print |
| `stages._stage_image_audit` | ~350 | see §2 |
| `text_detector.OCRPreprocessing.detect_text_in_image` | 243 | OCR call · bbox filtering · colour extraction · contrast · classification |
| `universal_page.UniversalPageLoader.load` | 230 | BFS · budgets · image capture wiring · snapshot assembly |
| `universal_page._crawl_one_url_inner` | 175 | navigate · cookies · lazy-load · extract · frames · images · html snapshot |
| `findings._build_contrast_report` | 152 | |
| `image_extractor.capture_assets` | 252 | |

## 14. Overly large modules

`image_extractor.py` 1862 (≈900 JS), `alttext.py` 1726, `universal_page.py` 1639 (≈500 JS),
`findings.py` 1382, `quality_engine.py` 1099, `media_auditor.py` 1027, `routes.py` 979,
`stages.py` 974, `runner.py` 972, `engine.py` 966, `text_detector.py` 902, `admin.py` 868.
Moving the JS strings into the existing `crawler/js/` directory alone removes ~1400 lines of
Python-file noise.

## 15. Circular-dependency risks

* `accessibility/rules/* → api/v1/combined/findings` (lazy, inside functions). Real inversion.
* `combined/routes → api/v1/audits._assert_can_view` and `audits → combined` is avoided only by
  lazy import inside handlers.
* `stages.py` puts `PythonStagesResult` before its imports (E402 ×12) — a symptom of an earlier
  cycle fix; `runner` imports it from `stages` but does not use it.
* `utils/lang_detector → crawler/_ssrf_guard` (utils reaching up).

## 16. Configuration problems

* Two YAML files with a silent precedence rule (§6.4); Docker never sees `universal.yml`.
* 85 `KA11Y_*` env vars read at import time as module constants → unchangeable at runtime and
  order-dependent under pytest; `KA11Y_MAX_BROWSER_CONTEXTS` has three accepted aliases.
* `.env` loaded at import (B8).
* CORS origins hard-coded in `main.py`.
* `KA11Y_ALLOWED_EMAILS` default in `.env.example` contains real addresses.
* Retention/TTL constants: 1 h hot TTL, 30 d SQLite retention, `passes[:100]` slimming,
  `_STAGE_TIMEOUT_SECONDS=1200`, `_CRAWL_TIMEOUT_SECONDS=300` — named, but spread across 4 files.

## 17. Security concerns

Good baseline (verified): SSRF guard installed on every browser context + submit-time DNS check;
parameterized SQL everywhere; scrypt passwords; AES-GCM sealed cookies with hashed session tokens;
HSTS/CSP/frame-ancestors; body cap; per-IP rate limiter; error scrubbing with `error_id`; path
containment on image serving; `.env` untracked.

Gaps: **B3** (IDOR + global history), **B4** (metrics under user auth), **B7** (exception text to
client), `repo.update_run(**fields)` interpolates column names from kwargs (all call sites pass
literals today — worth a whitelist assertion), `submit_combined_audit` still accepts the `url`
query parameter unvalidated until `CombinedRequest` runs (fine, but the pydantic error is a 500-shaped
`ValidationError` rather than 422 because it is raised inside the handler).

## 18. Performance concerns (observed, not measured)

* Every `GET /combined/{id}` on a finished job runs a SQLite `get_reviews` query, re-partitions all
  findings (`apply_reviews`), re-annotates techniques, and deep-copies via `strip_failure_techniques`.
  Reports have thousands of findings for depth-2 crawls; the UI polls this endpoint. Candidate for
  caching keyed on `(job_id, reviews_updated_at)`.
* Concurrent GETs mutate the shared hot report object (`apply_reviews` is idempotent, so this is
  a hazard rather than a bug).
* `_merge_findings` and `save_report` go through `run_cpu`, which pickles the entire findings list
  when `KA11Y_CPU_WORKERS` is set. For a thread fallback it is free; for the process pool the
  pickling may cost more than the work.
* OCR has no per-image timeout (§9). Resource math: 4 jobs × (1 browser slot of 2) × 4 OCR
  threads on one box — documented in comments but worth a single table in the README.
* `list_runs` uses `url LIKE '%x%'` (unindexable) — fine at current volumes.
* `assert_public_url` does a blocking `getaddrinfo` in a thread per submit — fine.

## 19. Recommended refactoring order

Each step is independently mergeable and leaves tests green. **Steps 0–1 are small; from step 2 on
each changes structure and needs your go-ahead.**

**Step 0 — safe hygiene (one commit, no behaviour change)**
ruff `--fix` (27), delete duplicate `CORSMiddleware` import, remove the 77 commented lines in
`text_detector.py`, remove the unused `log_*` wrappers and `universal_extract.js`, switch the 9
stdlib loggers to `setup_logger`, convert the 71 library `print()`s to `logger.debug/info`
(keeping `engine.py`'s CLI output), move `PythonStagesResult` below the imports in `stages.py`.

**Step 1 — bugs (one commit each, with a regression test)**
B2 (stuck-running window), B5 (enqueue failure), B1 (dead rule flags — I recommend deleting the
13 entries and routing the rest through `_admit_run`), B3 (authz on every `{job_id}` route;
`/combined/history` scoped or removed), B4 (`/admin/metrics` → admin router), B7 (per-request job
id, bounded LRU cache, scrubbed error), B8 (`load_dotenv` out of import path; conftest resets
`DATABASE_URL`) — this last one turns the baseline green and lets the auth tests skip honestly.

**Step 2 — remove confirmed dead code**
`classifier/`, legacy `crawl.py`/`pipeline.py`/`dependencies.py`/`models/*`, dead `RULE_FLAGS`,
`routes.py` SSRF duplicate (fold onto `_ssrf_guard`), `universal.yml` `checks:` section (or the
whole second config file — decision needed), `_run_job` legacy launcher once B1 lands.

**Step 3 — make state explicit**
`JobStatus` enum + `JobRecord` dataclass in `combined/store.py`; replace the 14 files' string
literals; one `settings.py` per package following the `auth/config.py` pattern for the 85 env
reads (read once at startup, injected, testable).

**Step 4 — fix the layer inversion**
Move `_make_finding`, `_source_filename`, `_lang_ctx` to `ka11y/accessibility/findings.py`;
`api/v1/combined/findings.py` keeps the converters and imports the factory. Rules stop importing
from `api`.

**Step 5 — split the two orchestration functions**
`_run_job_body_inner` → `_prepare_job`, `_run_engines`, `_post_process_findings`,
`_persist_completed`, `_deliver`, `_fail_job`. `_stage_image_audit` → `_adapt_images`,
`_run_ocr`, `_run_alt_audit`, `_convert_findings`. Names, not classes; same call order; existing
tests unchanged.

**Step 6 — observability**
`job_id` as a structured field on the adapter (`extra={"job_id": …}`) and one log line per
lifecycle boundary (submitted, started, crawl done, ocr done, merged, persisted, completed/failed).
Collapse the four timing systems onto `stage_timing` + spans, or document why each exists.

**Step 7 — readability**
JS strings to `crawler/js/*.js`; `alttext.generate_audit_report` per-SC check extraction (it already
has `_check_1_1_1_*` helpers — the loop body just needs to call them); `text_detector` OCR call vs
colour analysis split.

Deferred / not recommended now: replacing SQLite with PostgreSQL for the run store (behaviour
change, needs a migration plan), introducing repository classes (functions are fine), any
async→sync rewrite.

---

## 20. Progress log (same day, branch `refactor_code`)

Approved decisions: remove the deprecated `/crawl`, `/pipeline` and `/rules/*/run` routes; keep
`accessibility/pipeline` as a library; delete `config/universal.yml`.

| Commit | Step | What |
|---|---|---|
| `576a7f8` | 0 | ruff fixes, commented-out OCR block, unused wrappers/JS, 7 stdlib loggers → `setup_logger`, prints → logger |
| `98f4b1d` | 1 | **B8** `.env` no longer read by tests (`KA11Y_LOAD_DOTENV`); tracing-off spans are non-recording; 2 stale tests fixed → suite went from 22 failures to 0 |
| `27a68ad` | 1 | **B2** pre-try crash window closed, dispatcher marks escaped crashes failed; **B5** `create_run` raises, submit answers 503 |
| `e498a6c` | 1 | **B3** `_assert_can_view` on every `{job_id}` route, `/combined/history` admin-only; **B4** `/admin/metrics` under `require_admin`; `dotenv_enabled()` switch shared by main/tracing/enrich |
| `90e6983` | 1 | **B6** cancel check moved before `mark_running` (it could never fire), post-engine checkpoint, `job_cancelled` SSE, cancelled jobs evicted |
| `acdcfe8` | 1 | **B7** rule tester: per-request job id, 8-entry LRU cache, scrubbed errors; **B10** throttle-key leak, dead `timeout` status, comments/docstrings |
| `a6fdbdf` | 2 | **B1/B9** legacy `crawl.py`/`pipeline.py`/`dependencies.py`/`models/*`, `rules/run_router.py` + models removed; docs pages + nav updated |
| `8eb2b3d` | 2 | `config/universal.yml` removed, single `DEFAULT_CONFIG_PATH`, 6 dead settings helpers removed |
| `d3fc837` | 2 | **New finding, fixed:** the Python and Node Docker copies of `i18n/` were 3 months behind the shared one (5 reason templates + 2 severities missing in production); typo fixed at source, copies synced, drift test added |
| `b0edfc4` | 2 | `classifier/` removed; routes' duplicate SSRF classifier folded onto `crawler/_ssrf_guard` |

After: **635 passed, 25 skipped (need `DATABASE_URL`), 0 failed, 28 s** (was 612/22 in 150 s).
Ruff: 5 remaining, all deliberate late imports (E402) behind availability guards.

Not done (needs go-ahead, Steps 3–7): `JobStatus` enum + typed job record, per-package settings
for the 85 env reads, moving `_make_finding` out of the API layer, splitting
`_run_job_body_inner` / `_stage_image_audit`, structured `job_id` logging, JS strings to files.
Also still open: `i18n/` has three copies by design (Docker build contexts) — the drift test
now catches divergence, but a compose volume mount or a build-time copy would remove the
duplication; the `accessibility/pipeline` package remains dormant; `E702` semicolons in
`enrich_audit.py`; `CODEBASE_WALKTHROUGH/` still describes the removed classifier and routes.
