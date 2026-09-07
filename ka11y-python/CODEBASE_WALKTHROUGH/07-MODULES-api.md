# 4. Module-by-Module Breakdown — Group 5: API Layer (`api/`)

The FastAPI surface, plus the `combined/` subpackage — the de facto **core
engine** of the whole service (crawler + rule auditors + OCR + classifier +
store, orchestrated into one background job with SSE progress). This is the
largest group (25 files). Grouped here as: **(A)** router aggregation, **(B)**
request/response models, **(C)** shared dependencies, **(D)** the `combined/`
audit subsystem, **(E)** narrower standalone endpoints, **(F)** the
`rules/` metadata + per-rule-runner subpackage.

> **Important correction, confirmed by reading `stages.py` directly:** the
> `accessibility/pipeline/` decision-policy engine documented in
> `05-MODULES-pipeline.md` (`Policy111`, `Policy143`, `Policy145`, `Policy146`,
> `Policy1411`, `DecisionEngine`, etc.) is **not called anywhere in the live
> request path**. `stages.py` imports `pipeline_stage._run_pipeline_stage`
> and wraps it in a local function of the same name (`stages.py:86-126`), but
> that wrapper is **never invoked** — `_run_python_stages` (the actual
> orchestrator every request goes through) only calls `_stage_image_audit`
> and `_stage_media_audit_universal`, and its own docstring says so
> explicitly: *"The pipeline stage (`_run_pipeline_stage`) has been removed —
> it is out of scope for this run configuration"* (`stages.py:724-725`).
> Verified via `grep -rn "_run_pipeline_stage" ka11y/` — no other caller
> exists anywhere in the codebase. So today, WCAG 1.1.1 / 1.4.3 / 1.4.5 /
> 1.4.6 / 1.4.11 coverage in an actual audit comes entirely from
> `accessibility/rules/non_text/alttext.py` + `contrast_analyser.py`
> (`06-MODULES-rules.md`) — the `accessibility/pipeline/` engine is fully
> implemented but currently orphaned. See `13-EXTENSIBILITY.md` for what
> re-wiring it would take.

---

## (A) Router aggregation

### `ka11y/api/router.py` (44 lines) — already summarized in
`01-OVERVIEW-AND-ENTRYPOINT.md`; repeated here for completeness. Builds
`router = APIRouter(prefix="/api/v1")` and mounts, in order: `crawl.router`,
`pipeline.router`, `combined.router` (from the `combined/` package, itself
prefixed `/combined`), `assets.router`, `rules_router` (from `rules/`,
prefixed `/rules`), and `rule_evaluator.router` with an explicit
`prefix="/test"`. Also defines two inline health-check routes:
- `GET /health` (lines 16-19): static `{"status": "ok", "service":
  "ka11y-python"}`.
- `GET /system/health` (lines 22-43): additionally calls
  `GET {NODE_BASE_URL}/api/v1/health` with a 2s timeout via `httpx`, reporting
  `"ok"`, `"error: {status}"`, or `"unreachable: {exc}"` for the Node
  service's reachability — this is the one place Python checks Node is alive
  independent of an actual audit.

---

## (B) Request/response models

### `ka11y/api/v1/models/crawl.py` (20 lines)
`CrawlRequest` (`url`, `max_depth` 0-5, `run_ocr=True`, `run_audit=True`) and
`CrawlResponse` (`status`, `output_dir`, `url`, `max_depth`, `total_images`,
`ocr_dir`, `audit_report`, `audit_summary`) — the models for the narrower
`POST /api/v1/crawl/` endpoint.

### `ka11y/api/v1/models/pipeline.py` (49 lines)
`PipelineRequest` — `url`, `max_depth`, `run_ocr=True`, `run_image_audit=True`,
plus **four fields that reference removed auditors**:
`run_form_audit`, `run_label_in_name_audit`, `run_pause_stop_hide_audit`,
`run_target_size_audit`, `run_text_spacing_audit` — all declared, all
defaulting `True`, **none of them read anywhere** in
`api/v1/pipeline.py`'s route handler (verified — it only reads `payload.run_ocr`
and `payload.run_image_audit`). `PipelineResponse` similarly declares report
fields for `form_audit`, `label_in_name`, `pause_stop_hide`, `target_size`,
`text_spacing` that the handler never populates (they stay `None`/default).
This is dead schema surface left over from the same removal documented in
`api/v1/combined/constants.py`.

### `ka11y/api/v1/models/combined.py` (15 lines)
A **pure re-export**: `from ka11y.api.v1.combined.models import
CombinedRequest, JobStatusResponse`. Its own docstring explains why it
exists as a stub: it used to be a stale duplicate of the real models file
that had drifted out of sync (missing newer flags); now it just forwards to
the canonical source so old import paths don't break.

### `ka11y/api/v1/combined/models.py` (106 lines) — the real, actively-used models.
- `_SC_STAGE_PREREQUISITES` (lines 19-30): maps a `success_criteria_id`
  string to the `CombinedRequest` boolean flag(s) that must be `True` for
  that SC to produce results — **only for SCs whose flags still exist**
  (`1.1.1`→`run_image_audit`, `1.4.3`→`run_ocr`, `1.4.5`→`run_image_audit`,
  `1.4.6`→`run_ocr`, `1.4.11`→`run_image_audit`, `4.1.2`→`run_image_audit`,
  `1.2.1`→`run_media_audit`, `1.2.2`→`run_captions_audit`). Its own comment
  notes entries for removed flags were deliberately deleted so the validator
  below never does a `getattr()` against a nonexistent attribute.
- **Class `CombinedRequest(BaseModel)`** (lines 33-85) — the real audit
  request schema:
  - `url: HttpUrl`; `max_depth` (0-5, DoS-bounding comment); `internal_links`
    (kept as a safeguard even though the crawl always confines itself to the
    exact hostname regardless, per the field comment); `max_pages` (1-200 by
    the `Field` bound, but **re-clamped to ≤20** by the `_cap_max_pages`
    validator below — so a caller requesting 200 silently gets 20, no
    validation error); `wcag_level` (`^(A|AA|AAA)$`);
    `success_criteria_id` (`^\d+\.\d+\.\d+$`, optional).
  - **Active toggles**: `run_ocr`, `run_image_audit`, `run_media_audit`,
    `run_captions_audit` — all `True` by default. **These are the only
    `run_*` flags that actually exist on this model** — this is the
    authoritative confirmation (independent of `stages.py`) that
    label-in-name/target-size/text-spacing/pause-stop-hide/form/reflow/
    resize-text/orientation/hover-focus/focus-not-obscured/sensory flags do
    not exist here at all.
  - `lang` (default `"auto"`, pattern-validated); `email` (optional,
    pattern-validated rather than `pydantic.EmailStr` specifically so the
    project doesn't need the extra `email-validator` dependency, per the
    field comment).
  - `_cap_max_pages` (`@field_validator("max_pages")`, lines 64-67): `min(v,
    20)` — the actual page-count policy ceiling, silently applied.
  - `validate_success_criteria_dependencies` (`@model_validator(mode="after")`,
    lines 69-85): if `success_criteria_id` is set, checks every prerequisite
    flag in `_SC_STAGE_PREREQUISITES` is `True`; raises `ValueError` naming
    the missing flag(s) if not. **Important implication**: because this
    validator only knows about the 8 SCs in `_SC_STAGE_PREREQUISITES`, a
    `success_criteria_id` for anything else (e.g. `"2.5.3"`) passes
    validation silently and simply produces a report with **zero matching
    findings** later (see `runner.py`'s `effective_filter` logic below) —
    no error is ever raised for an unsupported SC ID submitted this way.
- **Class `JobStatusResponse(BaseModel)`** (lines 88-105): `job_id`,
  `status`, `url`, `submitted_at`, `lang`, `completed_at`, `report_path`,
  `result` (the full report dict once complete), `error` (a fixed generic
  string — internal detail is never returned to the client, per the field
  comment), `error_id` (opaque correlation ID for support/log lookup),
  `error_stage`, `current_stage`, `stages` (per-stage lifecycle records),
  `warnings`.

### `ka11y/api/v1/rules/models.py` (22 lines)
`RuleRunRequest` (`url`, `max_depth` 0-5, `internal_links=True`, `max_pages`
1-200 default 50, `lang="en"`) and `RuleUrlOnlyRequest` (`url`, `lang="en"`)
— the two request shapes for the dynamically-generated per-rule endpoints in
`rules/run_router.py`.

---

## (C) Shared dependencies

### `ka11y/api/v1/dependencies.py` (105 lines)
FastAPI DI providers used by the narrower `crawl.py`/`pipeline.py` routes
(the `combined/` subsystem builds its own equivalents inline instead of
using these).
- `get_config() -> dict` (`@lru_cache(maxsize=1)`, lines 37-40): loads and
  caches config once per process — note this differs from
  `utils.config_loader.load_config()`'s own `lru_cache`-by-path-string
  mechanism; this is a second, independent cache layer on top of it.
- `get_output_dir(url, config=Depends(get_config)) -> Path` (lines 46-76) —
  **security-relevant**: builds `<base_out>/<safe_domain>_<MMDD_HHMM>_<uid>/`.
  1. Extracts the hostname from `url`, strips a port if present.
  2. **Validates the hostname against a strict allowlist regex**
     (`^[A-Za-z0-9._-]+$`) — raises `ValueError` for anything else, so a
     hostname engineered with path-traversal characters (`../`, `/`, null
     bytes) can never reach the filesystem path construction below.
  3. Builds the directory name, appends an 8-hex-char UUID suffix
     specifically to prevent timestamp collisions between concurrent
     requests to the same domain within the same minute.
  4. **Canonical-path containment check** (lines 71-73): resolves the final
     path and asserts it still starts with the resolved `base_out` string —
     a second, defense-in-depth guard against the constructed path somehow
     escaping the output root.
  5. **Side effect**: `path.mkdir(parents=True, exist_ok=True)`.
- `get_image_crawler(url, max_depth, output_dir=Depends(get_output_dir)) ->
  AsyncImageCrawler` (lines 82-94): constructs an `OptimizedImageCrawler`
  (deferred import), then **overwrites** its self-computed `output_dir`
  attribute with the DI-provided one (so the crawler's own
  domain+timestamp directory logic, documented in `04-MODULES-crawler.md`'s
  `optimized_crawler.py` section, is bypassed in favor of this shared,
  security-checked path).
- `get_alt_text_auditor() -> AltTextAccessibilityAuditor` (lines 100-104):
  new stateless instance per request (deferred import).

---

## (D) The `combined/` audit subsystem — the real core engine

### `ka11y/api/v1/combined/__init__.py` (85 lines)
Package entry point / **living documentation**. Re-exports `router`,
`_evict_old_jobs`, `_build_report`, and every finding converter so
`main.py`/`api/router.py` and tests can import from the package root. Its
docstring is a genuinely useful **six-step "how to add a new Python rule"**
guide (crawler → auditor → finding converter in `findings.py` → register
metadata in `constants.py` → wire a stage in `stages.py` → expose a toggle
in `models.py`) — directly relevant to `13-EXTENSIBILITY.md`.

### `ka11y/api/v1/combined/constants.py` (47 lines)
Loads `_WCAG_NAMES`, `_WCAG_LEVEL`, `_SUGGESTED_FIX`, `_PYTHON_SEVERITY`
from the shared i18n YAML (`i18n/loader.py`, see
`09-MODULES-text-classifier-i18n.md`) at **import time**, preserving the
same variable names an older, hardcoded-dict version of this file used (so
callers didn't need to change). `STAGE_WEIGHTS` (lines 43-46): `{"image_audit":
62, "media_audit": 38}` — the progress-bar weight split for the two
currently-active stages, summing to 100. The comment explicitly documents
that weights for `axe_core`, `pipeline`, `form_audit`, `label_in_name`,
`pause_stop_hide`, `target_size`, `text_spacing`, `rendered_layout_audit`,
`sensory_audit` were **deleted** — the same removal this whole correction
note has been tracking — and the two remaining weights were scaled up
(from 40/18) to still sum to 100.

### `ka11y/api/v1/combined/auditor_field_map.py` (88 lines)
A **typo-proofing registry**: `AUDITOR_FIELD_MAP` (built via `_keys_for(sc)`,
lines 34-37, translating `"1.1.1"` → `("wcag_1_1_1_status",
"wcag_1_1_1_reason")`) lists every SC any converter in `findings.py`
consumes (`1.1.1, 1.2.1, 1.2.2, 1.2.3, 1.3.3, 1.4.2, 1.4.3, 1.4.5, 1.4.6,
1.4.11, 1.4.12, 2.2.2, 2.5.8, 3.3.1, 3.3.2, 4.1.2, 3.2.3, 3.2.4, 3.1.3,
2.4.10` — note several of these, e.g. `1.3.3`/`1.4.12`/`2.2.2`/`2.5.8`/
`3.3.1`/`3.3.2`/`3.2.3`/`3.2.4`/`3.1.3`/`2.4.10`, are registered here for
completeness/future use but have **no active Python converter** calling
`get_status`/`get_reason` for them today — only the ones actually used by
`findings.py`'s converters matter at runtime). `status_key(sc)`/`reason_key(sc)`
raise `KeyError` for an unregistered SC (fail loud); `get_status(record, sc,
default="")`/`get_reason(record, sc, default="")` are the safe accessors
converters actually call. The module docstring notes this is paired with
`tests/test_auditor_field_map.py`, which scans `findings.py` for any
`r.get("wcag_X_Y_Z_*")` literal and asserts the registry covers it — a
CI-enforced typo guard, since a mismatched key on either side previously
silently downgraded a whole SC to `needs_review` via `.get`'s default.

### `ka11y/api/v1/combined/store.py` (182 lines)
The **in-memory job store** and **SSE subscriber bus** — documented function
by function:
- `_jobs: Dict[str, Dict]` (line 27): every live/recent job, keyed by
  `job_id` — the hot cache the rest of the subsystem reads/writes directly
  (no ORM, just nested dict mutation).
- `_subscribers: Dict[str, List[asyncio.Queue]]` (line 30): per-job SSE
  client queues.
- `_LazyAsyncLock` (lines 32-62): a loop-aware wrapper around `asyncio.Lock`
  — recreates the underlying lock if the running event loop has changed
  (relevant for test suites that spin up a fresh loop per test, and for any
  future hot-reload path), so a module-level singleton lock never gets
  "used from the wrong loop" errors.
- `_get_job_lock(job_id) -> asyncio.Lock` (lines 82-101): a **per-job** lock
  registry, same loop-rebinding pattern. The comment explains why this
  matters: `_jobs[job_id].update({...})` and `stages.append(...)` are not
  atomic in CPython (each dict/list mutation is a separate bytecode op), so
  without a lock a concurrent poller could observe a half-applied update.
- `_broadcast(job_id, event_type, data)` (lines 116-127, async): pushes
  `{"event": ..., "data": ...}` to every subscriber queue for a job, under
  the subscribers lock (so a concurrent subscribe can't slip in between the
  snapshot and the push loop and miss the event).
- `_close_subscribers(job_id)` (lines 129-137): sends a `None` sentinel to
  every subscriber queue (their generators treat this as "stream over") and
  removes the job's subscriber list.
- `_safe_remove_job_dir(output_dir)` (lines 143-158): **side effect** —
  deletes a job's on-disk output directory, but only if it's an actual
  directory whose name ends in `_combined` (the runner's own naming
  convention) — a defensive check against ever deleting something that
  happens to share a variable name but isn't actually a job artifact
  directory.
- `_evict_old_jobs()` (lines 161-181, async infinite loop, called from
  `main.py`'s lifespan): every 5 minutes, finds jobs `completed`/`failed`
  and older than `_JOB_TTL_SECONDS` (3600 = 1 hour), removes them from
  `_jobs`/`_subscribers`/the job-lock registry, and prunes their on-disk
  directory via `asyncio.to_thread` (so a large `rmtree` can't stall the
  event loop / SSE broadcasts).

### `ka11y/api/v1/combined/stage_events.py` (304 lines)
Stage lifecycle helpers — every stage coroutine calls `_stage_start` on
entry and `_stage_complete`/`_stage_error_and_warn` on exit; these functions
are the single point where in-memory state, the JSONL step log, the SQLite
`stage_timings` mirror, and SSE broadcasts all get updated together.
- `_emit_stage_timing(...)` (lines 27-59): parses the stage's own
  `started_at`/`completed_at` ISO strings (already captured by the caller)
  and calls `stage_timing.record(...)` — "piggy-backing" on timestamps
  already being tracked rather than adding new instrumentation per stage.
- `_fire_broadcast(job_id, event_type, data)` (lines 68-84): schedules
  `_broadcast(...)` via `loop.create_task(...)` from **synchronous** code —
  the stage helpers themselves are sync (so call sites don't need `await`
  boilerplate), but need to push an async SSE event; if there's no running
  loop (e.g. called from a thread), logs a warning and drops the event
  rather than raising.
- `_plan_index(job_id, name) -> (index, total, weight)` (lines 87-104):
  looks up a stage's position in the job's stored `plan` (from
  `emit_job_plan`) for progress-bar rendering; falls back to `(None, None,
  None)` if no plan exists (e.g. unit tests).
- `emit_job_plan(job_id, active_stage_keys)` (lines 107-121): builds and
  stores the ordered stage plan (`{key, weight}` per stage, `weight_total`)
  and broadcasts a `job_plan` event — this is what lets the frontend draw an
  accurate weighted progress bar rather than a naive "stage N of M" count.
- `_stage_start` / `_stage_complete` / `_stage_error` (lines 124-270):
  append/update the stage's record in `_jobs[job_id]["stages"]`, write a
  matching JSONL step-log line (`append_step_log`), mirror timing into
  `stage_timing`, and broadcast the corresponding SSE event
  (`stage_start`/`stage_complete`/`stage_error`), each enriched with the
  plan `index`/`total`/`weight` if a plan exists. `_stage_complete` also
  clears the per-`(job,stage,phase)` progress-throttle cache entries for
  that stage (memory bound).
- `emit_stage_progress(job_id, name, current, total, *, phase=None)` (lines
  144-176): **throttled** sub-progress events — at most one per
  `(job_id, stage, phase)` every 0.2s (`_PROGRESS_MIN_INTERVAL_S`), except
  the terminal boundary (`current >= total`) always fires, so the UI's
  progress bar can't get stuck short of 100% due to throttling swallowing
  the last update.
- `_stage_error_and_warn(job_id, name, exc)` (lines 273-278): the common
  "non-fatal stage failure" path — logs, records the stage error, and
  appends a warning string to the job (used by every stage's `except`
  block).
- `_stage_warn(job_id, message)` (lines 281-288): appends a degradation
  warning without changing any stage's status — for partial-success
  conditions.
- `_record_crawler_time(job_id, stage_name, duration_s)` (lines 291-303):
  stamps `crawler_duration_s` onto the currently-`running` stage record of
  that name — surfaced in the timing breakdown UI and `run_timings.log`.

### `ka11y/api/v1/combined/dispatcher.py` (206 lines)
The **durable, crash-safe job dispatcher** (labeled "P4" in the docstring —
a phase/milestone marker used throughout this subsystem's comments). The
architectural shift this represents: the HTTP POST handler no longer runs a
job directly (`asyncio.create_task(_run_job(...))`); instead it persists a
`runs` row with `status='queued'` via SQLite (`store/repo.py`,
`08-MODULES-store.md`) and wakes this dispatcher, which is the **single
execution authority** enforcing the concurrency cap.
- `_get_wakeup() -> asyncio.Event` (lines 45-51): the same loop-rebinding
  lazy-singleton pattern seen throughout this subsystem.
- `notify()` (lines 58-63): sets the wakeup event (best-effort, swallows any
  exception) — called after `enqueue` persists a new row, so the dispatcher
  doesn't have to poll on a tight timer.
- `_payload_from_row(row) -> Optional[CombinedRequest]` (lines 70-76):
  deserializes the stored `params_json` back into a `CombinedRequest`;
  returns `None` (and logs a warning) if that fails — a corrupted/old-schema
  row is handled explicitly by the caller (marked `failed`), not crashed on.
- `_ensure_hot_entry(run_id, row, payload)` (lines 79-97): rebuilds a
  `_jobs[run_id]` hot-cache entry from the durable row if one doesn't
  already exist — this is exactly what makes crash recovery work: after a
  restart, `_jobs` is empty but the DB still has the `queued`/`running`
  rows, so the dispatcher reconstructs enough hot state for the stage-event
  helpers (which assume `_jobs[job_id]` exists) to keep working.
- `enqueue(run_id, payload, filter_rule=None)` (lines 100-136, async) — the
  public entry point called by `routes.py`'s `_admit_run`:
  1. **Side effect**: `repo.create_run(...)` — INSERTs the `runs` row with
     `status="queued"` and the full serialized params.
  2. `repo.insert_event(run_id, "queued", ...)`.
  3. **Fallback path**: if `not _dispatcher_running` (e.g. the store failed
     to initialize at startup — `main.py`'s lifespan degrades to
     memory-only in that case), directly `asyncio.create_task(_run_job(...))`
     — the legacy in-process path — so audits still run even without a
     working durable queue.
  4. Otherwise, just calls `notify()` and returns — the dispatcher's own
     loop picks it up.
- `_run_tracked(run_id, payload, filter_rule)` (lines 139-145, async): thin
  wrapper around `runner._run_job_body` that catches and logs any exception
  the job itself didn't already handle (a true "should never happen"
  safety net).
- `_drain()` (lines 148-172, async) — the core dispatch loop body:
  1. Computes `free = _MAX_CONCURRENT_JOBS - len(_inflight)`; returns
     immediately if no slots are free.
  2. `repo.next_queued(free)` — fetches up to `free` queued rows (FIFO,
     presumably ordered by submission time in the SQL — see
     `08-MODULES-store.md`).
  3. For each row: skips if the hot cache already shows it `running`
     (double-dispatch guard); rebuilds a `CombinedRequest`, marking the run
     `failed` immediately with `error_id="bad_params"` if deserialization
     failed; ensures a hot entry exists; **claims the row synchronously**
     (`repo.update_run(run_id, status="running")`) *before* spawning the
     task, specifically so the next `_drain()` tick (which could run before
     the spawned task's own first `await`) doesn't re-pick the same row;
     spawns `_run_tracked` as a tracked `asyncio.Task`, added to `_inflight`
     with a `done_callback` that discards it on completion.
- `run_dispatcher()` (lines 175-205, async, the task `main.py`'s lifespan
  starts): sets `_dispatcher_running = True`; runs `repo.requeue_running()`
  once at startup (crash recovery — any row left `status='running'` from a
  prior process that died mid-job gets reset to `queued`, logged if any were
  found); then loops forever: `_drain()`, then wait on the wakeup event with
  a 2-second timeout (so even without an explicit `notify()` call, the
  dispatcher polls at least every 2s) — always clears the event after
  waking (`finally`). Sets `_dispatcher_running = False` on the way out
  (cancellation or otherwise).

### `ka11y/api/v1/combined/findings.py` (1,375 lines)
The **finding factory** and every per-auditor **converter** that turns raw
auditor-record dicts (or OCR results) into the canonical finding shape the
rest of the system (reports, UI, CSV/PDF export) consumes.

- `_source_filename(src, fallback=None) -> Optional[str]` (lines 60-87):
  extracts the real, user-facing filename from an image's `src` URL (last
  path segment, URL-decoded), preserving an SVG sprite `#fragment` (e.g.
  `sprite.svg#icon-menu`) since that names the specific icon. Falls back to
  `fallback` (typically the crawler's internal hash-based name, see
  `adapter._unique_basename` in `04-MODULES-crawler.md`) for `data:` URIs or
  unusable paths — the module's own comment block (lines 50-58) explains why
  this distinction matters: the hash name is an internal OCR-correlation
  join key that must never be shown to a user as "the file name."
- `_make_finding(*, source, rule_id, wcag_sc, status, severity, ...) -> Dict`
  (lines 93-205) — **the single finding-shape factory** every converter
  calls:
  1. Canonicalizes `page_url` via `_canonicalize_url` at this "central
     choke point" (comment: `R-2`) so every stage's dedup keys and per-page
     UI grouping see identical URL strings regardless of which stage/engine
     produced the finding.
  2. `is_pass = status in ("pass", "inapplicable")`.
  3. Localizes the reason text: if `reason_code` is given, renders it
     through `i18n.loader.render_reason(wcag_sc, reason_code, lang=..., 
     fallback=reason, params=reason_params)` (YAML template lookup, with the
     raw `reason` string as a fallback if no template exists); otherwise
     uses the raw `reason` string directly.
  4. `severity_value = None if is_pass else severity` — passes never carry
     a severity (nothing to prioritize fixing).
  5. Builds an `element` dict (HTML truncated to 600 chars) — `None` if
     nothing meaningful was passed **and** `is_pass` is true (a clean pass
     with no element context is deliberately left elementless, though a
     fail/needs_review always gets a (possibly mostly-empty) element dict).
  6. Returns the full finding dict: `source`, `rule_id`, `wcag_sc`,
     `criterion_name` (looked up), `level`/`level_label`,
     `severity`/`severity_label`, `status`/`status_label`, `reason`,
     `detected_by: ["python"]`, `reason_code`, `suggested_fix` (`None` for
     passes), `help_url` (always `None` — never populated by any Python
     converter), `element`.
- `_is_incomplete_reason(reason) -> bool` (lines 208-210): reason text
  starting with `"INCOMPLETE"` (case-insensitive) — a string-based
  discriminator used by a few converters to distinguish "genuinely N/A" from
  "needs review, expressed as a None status with an INCOMPLETE-prefixed
  reason" (the same fragile convention flagged in `06-MODULES-rules.md`'s
  `alttext.py` write-up).
- **1.1.1 reason-code derivation** (lines 213-292): `_alt_is_generic`,
  `_alt_reason_params`, `_alt_text_reason_code`, `_incomplete_reason_code` —
  a documented fix (lines 214-220): every 1.1.1 failure used to be emitted
  with the single hardcoded code `fail_missing_alt` regardless of the real
  reason, so an `<img alt="YouTube">` that failed for being a *generic* icon
  alt was reported to the client as "no alt text at all." The code is now
  derived from the record's own fields (never by parsing the English reason
  string) — prefers `record["wcag_1_1_1_code"]` (stamped by the auditor
  itself when its branch knows the exact situation), falling back to
  `missing_alt`/`decorative_invalid`/`generic_alt`/`logo_review`/
  `icon_terse`/`alt_text_mismatch` derived from `classification`/`sub_type`/
  `has_ocr_text`.
- `_record_element_kwargs(record, page_url, *, html_key="html_snippet",
  element_id_keys=("element_id",), tag_key="tag") -> Dict` (lines 295-321):
  a generic adapter turning a raw auditor record into the `_make_finding`
  element-related kwargs — used by the media converter (below) which needs
  the same shape but from a differently-keyed record than the image
  converters.
- `_infer_classification(path) -> str` (lines 327-348): derives a display
  classification (`button`/`icon`/`functional_logo`/`logo`/`image`/`chart`/
  `informative`/`decorative`/`other`) purely from substring matches on the
  image's storage path (`/functional/buttons/`, `/informative/logos/`,
  etc.) — a path-based inverse of the classifier's own folder-naming scheme,
  used only by the contrast-report/OCR-converter code below (not by the
  crawler's own `ImageData.classification`, which is already known at
  capture time).
- `_build_contrast_report(ocr_results, page_by_filename=None) -> Dict`
  (lines 354-503): the structured contrast report shown in the UI's image
  visualiser — very similar in shape to `api/v1/pipeline.py`'s
  `extract_contrast_report` (a near-duplicate implementation for the
  narrower `/pipeline/` endpoint) but with two additions: (1) per-image
  `page_url` (via the `page_by_filename` map, so multi-page crawls can
  filter the visualiser per page) and `classification` (via
  `_infer_classification`); (2) prefers the `dominant_contrast` sub-object
  over the plain `compliance` one when computing the displayed ratio/AA/AAA
  flags, "so the displayed ratio is always in sync with the Pass/Fail
  verdict" (comment lines 408-410); (3) computes each image's
  `contrast_violations_count` **from the actual detections list** rather
  than trusting the OCR result's own precomputed count, since that count
  "can be stale or miscounted by the OCR pipeline" (comment lines 474-476).
- `_build_image_audit_report(records) -> Dict` (lines 506-587): the
  frontend-facing summary of the *entire* image-audit result set (unlike
  the contrast report, this includes every audited image, even ones with no
  OCR text/contrast data) — per-image summary rows plus a `by_classification`
  breakdown, using `get_status`/`get_reason` from `auditor_field_map.py` for
  every WCAG-status/reason pair (the typo-proofing this file exists to
  enforce).
- **Per-auditor converters** (lines 593-1307) — each takes raw auditor
  records (or OCR results) and a `page_url`, returns `List[Dict]` findings.
  All follow the same shape (documented once here rather than per-function,
  since the pattern repeats almost verbatim): filter to statuses that
  matter, build a synthetic `element_html` string representing the source
  element, resolve the real vs. internal filename via `_source_filename`,
  then branch on status (`INCOMPLETE`→`needs_review`, `FAILED`→`fail`,
  `PASSED`/other→`pass`) calling `_make_finding` once per record:
  - `_alt_text_to_findings` (1.1.1) — the richest one: derives the reason
    code via `_alt_text_reason_code`; also **reclassifies** a `PASSED`
    status containing `"manual review"` in its reason text as `INCOMPLETE`
    before branching (line 615-616) — a second string-sniffing
    reclassification layer on top of the auditor's own status.
  - `_name_role_value_to_findings` (4.1.2) — simpler, no reason-code
    derivation (uses `"fail"`/`"pass"` literal codes).
  - `_contrast_to_findings` / `_contrast_enhanced_to_findings` (1.4.3 /
    1.4.6) — operate directly on **OCR results**, not auditor records; skip
    logo/decorative/brand-logo images (via `_is_brand_logo`, imported from
    `alttext.py`) unless the OCR category is `button_text`; build a
    synthetic `<img-text fg=... bg=... ratio=...>` element HTML and a
    human `image_label` combining the filename and the detected text
    snippet; the two functions are near-identical except AA vs. AAA
    thresholds/fields (`dom_compliance.get("AA_passes")` vs.
    `get("AAA_passes")`).
  - `_images_of_text_to_findings` (1.4.5) — skips `N/A` records entirely
    (unlike 1.1.1/4.1.2, which handle `N/A` implicitly via the branch
    structure).
  - `_non_text_contrast_to_findings` (1.4.11) — the most involved status
    logic: computes `needs_review = status_raw == "INCOMPLETE" or
    (status_raw == "N/A" and _is_incomplete_reason(reason))` — because
    `_check_1_4_11` (documented in `06-MODULES-rules.md`) uses `None` for
    both "genuinely N/A" and "needs review," distinguished only by the
    reason text prefix, this converter has to re-derive which is which.
  - `_media_to_findings` (1.2.1, 1.2.2, 1.2.3, 1.4.2) (lines 1195-1307):
    structurally different from the image converters — one record can
    produce **up to four findings** (one per applicable criterion), each
    independently branched on its own status field; if `records` is empty,
    emits two synthetic `pass` findings ("No media elements found on
    page.") for 1.2.1 and 1.2.2 specifically (not 1.2.3/1.4.2) rather than
    producing zero findings for a page with no media at all.
  - `_contrast_capture_failed_to_findings(images_data, page_url)` (lines
    1310-1356): a **separate pass over `ImageData` (not OCR results or
    auditor records)** — for every image whose `capture_status != "ok"`,
    emits a `needs_review` finding for *both* 1.4.3 and 1.4.6 with
    `reason_code="capture_failed"`, explaining OCR never got a chance to run.
    Called after the OCR converters specifically so this finding appears
    alongside the normal contrast findings rather than being lost.
- **Converter registries** (lines 1358-1374): `IMAGE_AUDIT_RECORD_CONVERTERS`
  (a tuple of `(status_key, converter)` pairs — `wcag_1_1_1_status`→
  `_alt_text_to_findings`, `wcag_4_1_2_status`→`_name_role_value_to_findings`,
  `wcag_1_4_5_status`→`_images_of_text_to_findings`,
  `wcag_1_4_11_status`→`_non_text_contrast_to_findings`) and
  `OCR_RESULT_CONVERTERS` (`("1.4.3", _contrast_to_findings)`, `("1.4.6",
  _contrast_enhanced_to_findings)`) — `stages.py` iterates these tuples
  rather than calling each converter by name, so adding a new converter is a
  one-line registration (per the package docstring's "how to add a new
  rule" guide).

### `ka11y/api/v1/combined/report.py` (426 lines)
`_build_report` — merges all flat findings (Python + Node) into the final
combined report shape, plus the manual-review overlay logic.
- `_finding_signature(f) -> str` (lines 27-45): builds a stable
  element-identity string from `wcag_sc`, `rule_id`, and every available
  element-identity field (`page_url`, `frame_path`, `selector`/`target`,
  `element_ref_id`, `element_id`, `tag`, `image_src`, a whitespace-collapsed
  HTML prefix) — the basis for a `finding_id` that survives report
  regeneration so a client's manual-review decision can reattach to "the
  same" finding later.
- `_stamp_finding_ids(findings)` (lines 48-60): computes a 16-hex-char
  SHA-1 `finding_id` per finding from its signature, disambiguating true
  duplicates (same signature) with a `#N` suffix before hashing; also stamps
  `manual_review = (status == "needs_review")`.
- `apply_reviews(report, reviews) -> Dict` (lines 63-181) — overlays stored
  manual-review decisions and **recomputes the effective score**:
  1. Preserves the original automated counts under `summary["automated"]`
     the first time (idempotent — a second call reads the already-stored
     automated baseline rather than re-deriving it from already-repartitioned
     numbers, so reapplying reviews to the same hot report object never
     compounds).
  2. `_repartition(violations, needs_review, passes)` (nested closure, lines
     83-119): re-buckets the **union** of all three input lists purely from
     each finding's immutable `status` plus any `review_status` overlay —
     a `needs_review` finding with a recorded review moves into
     `violations`/`passes` accordingly (and gets `review_status`/
     `review_note`/`reviewed=True` stamped on it); one without a review, or
     whose review was since cleared (`status="needs_review"` re-open),
     loses those stamped fields and stays in `needs_review`. Purely
     derived, so repeated calls are stable.
  3. Recomputes `summary["violations"/"needs_review"/"passes"/"score"]` from
     the new partition, and `summary["reviews"] = {reviewed, pending,
     as_pass, as_violation}`.
  4. **Repeats the same repartition per-page** (`report["pages"]`) so the
     per-page summaries stay consistent with the flat lists, and syncs
     `pages_scanned` entries' violation/needs_review/pass counts from the
     freshly repartitioned page summaries.
- `_build_report(url, all_findings, lang="en", contrast_report=None,
  image_audit_report=None, crawled_pages=None) -> Dict` (lines 184-425):
  1. Stamps finding IDs (**before** bucketing, so every copy of a finding —
     flat lists and per-page arrays share the *same* dict object — carries
     the same ID; Python list membership by reference, not by copy).
  2. Buckets into `violations`/`needs_review`/`passes` by `status`.
  3. Builds `by_severity`, `by_level`, `by_wcag_sc`, `by_source` count maps.
  4. **Page-wise breakdown** (lines 231-337): groups findings by
     `_page_of(f)` — canonicalized + `CrawlPolicy`-normalized `element.page_url`,
     falling back to the canonicalized root URL for element-less (page-level)
     findings. Computes `pages_affected` per SC — the count of **distinct
     pages** with at least one violation for that SC, distinguishing "one
     problem repeated across 47 pages" from "47 problems on one page"
     (comment lines 261-264) — additive to the existing `by_wcag_sc` map so
     old consumers are unaffected.
  5. `_score(passes_n, violations_n)` (lines 302-306): `None` (not `100.0`)
     when there's no pass-or-fail data at all — the comment explains this
     was a real bug fix: a page with only `needs_review` findings (or none)
     previously reported a misleading perfect `100.0` score.
  6. Sorts pages worst-first (most violations, then most needs_review, then
     URL).
  7. **`pages_scanned`** (lines 348-390): distinct from `pages` — includes
     pages that produced **zero findings but were still crawled**, including
     ones that **failed to crawl entirely** (nav timeout, 404), sourced from
     the `crawled_pages` parameter (the union of Python's own
     `UniversalPageLoader` visit list and Node's `boundedBfs` visit list,
     assembled by `runner.py`), deduped against pages already represented in
     `pages`.
  8. Returns the full report dict: `url`, `generated_at`, `lang`, `labels`
     (localized severity/level/status label maps), `summary` (all the
     counts above plus `manual_review_required`, `score`, `page_count`),
     `violations`/`needs_review`/`passes` (flat), `pages`, `pages_scanned`,
     `contrast_report`, `image_audit_report`.

### `ka11y/api/v1/combined/stages.py` (835 lines)
Every per-stage coroutine and `_run_python_stages`, the Python-side
orchestrator. Documented function by function (the earlier correction note
above covers the headline architectural fact — `_run_pipeline_stage` is
dead code from this file's perspective).

- **Class `PythonStagesResult(BaseModel)`** (lines 28-47): the typed return
  value of `_run_python_stages`, replacing an older bare 3-tuple return —
  the docstring explains the tuple silently broke whenever a stage was
  added/reordered because the caller's positional unpack would grab the
  wrong field; named fields (`findings`, `contrast_report`,
  `image_audit_report`, `crawled_pages`) make the contract explicit.
  `model_config = ConfigDict(arbitrary_types_allowed=True)` so Pydantic
  doesn't deep-copy/revalidate the deeply-nested heterogeneous finding
  dicts on every assignment (a performance-motivated opt-out).
- `_run_pipeline_stage(url, job_id, run_image_audit, run_contrast_audit=True,
  lang="en", snapshot=None)` (lines 86-126) — the **orphaned wrapper**
  covered above: times and records stage lifecycle around a call to the
  real `accessibility.pipeline.pipeline_stage._run_pipeline_stage`
  (imported as `_real_run_pipeline_stage`), but is itself never called by
  anything.
- **Timeout/concurrency constants** (lines 129-160): `_STAGE_TIMEOUT_SECONDS
  = 1200` (20 min, whole image-audit stage including OCR);
  `_CRAWL_TIMEOUT_SECONDS = 300` (floor for the crawler pass alone — OCR
  still runs on whatever images were saved before this deadline, so a
  stuck target never blocks contrast analysis entirely);
  `_CRAWL_PER_PAGE_SECONDS = 20` and `_CRAWL_TIMEOUT_CEILING = 600` — the
  **effective crawl deadline scales with page count**
  (`max(_CRAWL_TIMEOUT_SECONDS, min(per_page * pages,
  _CRAWL_TIMEOUT_CEILING))`), fixing a documented bug where a page crawled
  late in a deep BFS got silently dropped/under-screenshotted versus the
  same page audited directly at depth 0; `_HEAVY_STAGE_CONCURRENCY = 2` —
  a **process-wide** (not per-job) semaphore bounding concurrent
  browser-heavy stages, since with `_MAX_CONCURRENT_JOBS=4` an unguarded
  depth>0 audit could spawn 8 simultaneous BFS crawls and OOM-kill the
  container.
- `_get_heavy_stage_sem()` (lines 163-170): the usual lazy per-loop
  semaphore singleton pattern.
- `_heavy(coro, *, timeout=_STAGE_TIMEOUT_SECONDS)` (lines 173-181, async):
  acquires the heavy-stage semaphore **before** arming the
  `asyncio.wait_for` deadline, specifically so a stage queued behind
  another heavy stage isn't penalized for time spent waiting its turn.
- `_warning_samples(warnings, *, sample_limit)` (lines 187-210): groups a
  flat warnings list by `code`, keeping up to `sample_limit` truncated
  samples per code (message capped at 320 chars) — used to summarize
  potentially-hundreds of per-page crawl warnings into a compact,
  UI-displayable structure.
- `_record_stage_metrics(...)` (lines 213-236): writes one
  `{stage}_summary` step-log entry with crawler/auditor/finding counts —
  purely observational.
- `_allowed_levels(wcag_level) -> set` (lines 242-248): `"A"` always
  included; `"AA"`/`"AAA"` cumulatively added — the report-level filter
  applied in `runner.py` after merging.
- `_ocr_lang_for_page(page_lang, run_lag) -> str` (lines 254-280) —
  documented at length in its own docstring: OCR backends only meaningfully
  distinguish Japanese from "everything else," so this only ever splits a
  run into a `ja` group and a non-`ja` group. Fixes a real cross-language
  bug: a non-Japanese child page under a Japanese-language run was
  previously OCR'd with the Japanese model (misreading Latin text); now a
  page's own detected language wins over the run's overall language when
  they conflict, falling back to the run language only when the page's
  language is unknown.
- `_stage_image_audit(...)` (lines 283-573, async) — the **larger of the
  two active stages**: crawl images → (optional) OCR → 1.1.1 alt-text +
  1.4.3/1.4.6 contrast.
  1. No-ops immediately if both `run_ocr` and `run_image_audit` are `False`.
  2. Constructs an `OptimizedImageCrawler`; `_crawl_and_save()` (nested
     closure) times the crawl via `time_crawler` and calls
     `image_crawler.crawl_page(discovered_urls=discovered_urls)` — note
     `discovered_urls`, if provided, comes from the **universal snapshot's**
     page list (shared with the media-audit stage), so the image crawler
     doesn't re-run its own BFS on a multi-page audit — it just crawls
     exactly those pages (see `optimized_crawler.py`'s handling of an
     explicit `discovered_urls` list, `04-MODULES-crawler.md`).
  3. Runs the crawl under the scaled timeout (above); on
     `asyncio.TimeoutError`, computes how many pages were actually covered
     vs. requested and appends a descriptive warning to the job — **does
     not fail the stage**, proceeds with whatever partial image set exists.
  4. **OCR budget selection** (lines 377-418): computes `max_ocr_images`
     (per-page × distinct-page-count, capped by the ceiling — see
     `crawler_settings.py`'s `select_ocr_candidate_paths` in
     `03-MODULES-config-utils.md`); logs and step-logs how many images were
     skipped due to budget.
  5. **Per-page OCR language grouping** (lines 419-429): builds
     `path_to_page` (screenshot path → page URL) and groups OCR paths by
     `_ocr_lang_for_page`, running a **separate `OCRPreprocessing` pass per
     language group** (so a mixed-language multi-page crawl gets each
     page's images OCR'd with the correct engine).
  6. Runs each group's OCR via `asyncio.to_thread(detector.scan_directory)`
     (offloading the CPU/GPU-bound OCR work off the event loop), emitting
     progress after each group.
  7. Builds the contrast report and runs `OCR_RESULT_CONVERTERS`, timing
     each via `stage_timing.time_stage`; adds
     `_contrast_capture_failed_to_findings`.
  8. If `run_image_audit`: runs `AltTextAccessibilityAuditor.generate_audit_report`
     via `asyncio.to_thread` (CPU-bound, offloaded), then
     `IMAGE_AUDIT_RECORD_CONVERTERS`.
  9. Records metrics, completes the stage, **returns a 3-tuple**
     `(findings, contrast_report, image_audit_report)` — note the function's
     own type annotation at line 295 says `Tuple[List[Dict],
     Optional[Dict[str, Any]]]` (a **2-tuple** type hint), which does not
     match the actual 3-value returns at lines 555/570/573 — a stale/
     incorrect type annotation, not a runtime bug (Python doesn't enforce
     annotations), but worth knowing if refactoring this signature.
  10. On `ImageCrawlerNavigationError` or any other exception: records a
      warning/error, returns `([], None, None)`.
- `_load_universal_snapshot(...)` (lines 576-652, async): builds a
  `CrawlPolicy`, runs `UniversalPageLoader.load(...)` under `time_crawler`,
  records the crawl duration onto the job (shared by the pipeline-stage
  wrapper above, for whenever/if it's ever wired back in), saves the raw
  snapshot to disk, normalizes it via `SnapshotNormalizer`, and if there
  were extraction warnings, writes `universal_snapshot_warnings.json` and
  summarizes them onto the job. **Raises** if `normalized.pages_crawled ==
  0` — this is the one condition that aborts the whole stage rather than
  degrading, since zero crawled pages means no media data exists at all.
- `_stage_media_audit_universal(...)` (lines 655-697, async): awaits the
  shared `snapshot_task` (a pre-resolved `asyncio.Future`, not a fresh
  crawl — see below), runs `MediaAuditor.generate_audit_report` via
  `asyncio.to_thread`, converts via `_media_to_findings`.
- `_run_python_stages(...)` (lines 702-834, async) — **the orchestrator**:
  1. `needs_crawl = any((run_media_audit, run_captions_audit)) or max_depth
     > 0` — the universal snapshot crawl only runs if media/captions is
     requested or the audit is genuinely multi-page; a single-page,
     image-only audit skips it entirely (the image-audit stage does its own
     lighter crawl in that case).
  2. If needed, calls `_load_universal_snapshot` **once**, then derives
     `discovered_urls` (deduped page URLs from `snapshot.page_summaries`)
     and `crawled_pages` (both successes, from `page_summaries`, and
     failures, inferred from any warning whose `page_url` never made it
     into `page_summaries` — i.e. a page that a warning names but that
     never successfully loaded).
  3. Wraps the (possibly `None`) snapshot in a pre-resolved
     `asyncio.Future` (`snapshot_task`) — this is the mechanism that lets
     `_stage_media_audit_universal` simply `await` it without knowing
     whether the crawl already happened or needs to happen; since it's
     pre-resolved, awaiting it is instant.
  4. Launches **both** stages concurrently: `_stage_image_audit` wrapped in
     `_heavy(...)` (the global browser-heavy semaphore) and
     `_stage_media_audit_universal` wrapped in a plain `_timed(...)` (no
     semaphore — it doesn't open its own browser, it consumes the
     already-built snapshot).
  5. `asyncio.gather(*stage_coros, return_exceptions=True)` — an exception
     in one stage doesn't cancel the other; each is logged and treated as
     zero findings for that stage.
  6. Returns the assembled `PythonStagesResult`.

### `ka11y/api/v1/combined/runner.py` (688 lines)
`_run_job` / `_run_job_body` — the actual background task the dispatcher
runs per job; launches Python stages and the Node/axe-core call in
parallel, merges, and persists the final report.
- **Timeout/concurrency constants** (lines 50-53, 152-171): `_JOB_TIMEOUT_SECONDS
  = 1800` (30 min overall job budget); `_MAX_CONCURRENT_JOBS = 4` (a
  **second**, job-level semaphore, distinct from `stages.py`'s
  `_HEAVY_STAGE_CONCURRENCY` — this one bounds whole jobs, not just the
  browser-heavy sub-stage within a job); `_NODE_TIMEOUT_SECONDS = 300` — a
  documented fix: this must stay **above** Node's own internal crawl budget
  (`ka11y-node`'s `flatCrawlBudgetMs`, default 255s), else Python gives up
  on Node before Node itself would have returned partial results, silently
  discarding every axe-core finding; `_NODE_HTTP_BASE_TIMEOUT = 60` /
  `_NODE_HTTP_PER_PAGE_TIMEOUT = 75` — another documented fix: a fixed
  300s ceiling doesn't scale for multi-page crawls (Node audits every
  requested page), so `_node_http_timeout(max_pages)` (lines 174-180)
  computes `base + per_page * pages`, floored at `_NODE_TIMEOUT_SECONDS`
  and capped at `_JOB_TIMEOUT_SECONDS`.
- `_get_job_semaphore()` (lines 56-63): the usual lazy per-loop singleton.
- `_merge_findings(node_findings, python_findings) -> List[Dict]` (lines
  66-145) — the **cross-engine deduplication** at the heart of the
  "combined" audit:
  1. `_sig(f) -> tuple`: builds a `(wcag_sc, status, element_identity)` key,
     where `element_identity` is the **first non-empty** of, in priority
     order: CSS selector (page+frame-scoped), normalized `target` list,
     `element_ref_id`, a non-URL-looking `element_id` + tag, `image_src`, or
     a SHA-1 hash of whitespace-collapsed HTML (namespaced by page/frame/tag
     to avoid merging unrelated repeated components by truncated markup
     coincidence). A finding with none of these (`ident == ""`) is **never
     deduplicated** — always kept as-is.
  2. Python findings are inserted first (`merged[key] = f`); Node findings
     only fill in keys not already claimed — **Python wins on collision**,
     since it "carries richer OCR-based contrast data for 1.4.3 and more
     precise image-level diagnostics" (docstring).
  3. Returns `list(merged.values()) + no_key` (both engines' un-keyable
     findings preserved, keyed ones deduplicated).
- `_fetch_node_findings(url, job_id, lang, payload) -> Dict` (lines
  183-248, async) — the Node/axe-core integration point:
  1. POSTs to `{NODE_BASE_URL}/api/v1/analyse-url-flat` with
     `url`/`lang`/`level`/`maxDepth`/`maxPages`/`internalLinks`/`jobId`
     (and `successCriteriaId` if a filter is set), timeout from
     `_node_http_timeout(max_pages)`.
  2. Normalizes Node's `pageUrl` camelCase alias into `page_url` inside
     `element` (or synthesizes `element` if Node returned a bare top-level
     `pageUrl`) — the one field-name reconciliation needed, since
     `axeResultMapper.js` on the Node side already emits snake_case for
     everything else.
  3. **Any exception** (network error, timeout, non-2xx, bad JSON) is
     caught, logged as a warning, and returns `{"findings": [], "scanned_pages":
     []}` — graceful degradation to Python-only results is the explicit
     design (module and function docstrings both state this).
- `_run_job(job_id, payload, filter_rule=None)` (lines 251-279, async) —
  the public entry point the dispatcher calls: acquires the job semaphore
  (marking the job `queued` in the hot cache if it had to actually wait, so
  a client polling status sees an accurate state), then calls
  `_run_job_body` inside the `async with sem` block.
- `_run_job_body(job_id, payload, filter_rule=None)` (lines 282-686, async)
  — the actual orchestration, in order:
  1. Marks the job `running` (hot cache + durable `repo.mark_running`),
     checks `repo.is_cancelled(job_id)` and returns early if a cancel
     request beat the dispatcher to it.
  2. Resolves `lang`: calls `detect_page_language(url)` if `payload.lang ==
     "auto"` (see `03-MODULES-config-utils.md`'s `lang_detector.py`),
     else uses the requested language directly; sets `_lang_ctx` (the
     `contextvars.ContextVar` `findings.py` reads for localization —
     inherited automatically by every child task spawned from here, per
     `asyncio.create_task`'s context-copy semantics) and
     `crawler_timing.set_run_id(job_id)`.
  3. Computes the per-job output directory:
     `{output_root}/{domain}_{MMDD_HHMM}_{job_id[:8]}_combined` (this
     `_combined` suffix is exactly what `store.py`'s `_safe_remove_job_dir`
     checks for before deleting a directory on TTL eviction).
  4. Creates an `ExecutionStepLogger` for this job (see
     `03-MODULES-config-utils.md`).
  5. `emit_job_plan(job_id, active_stages)` — `active_stages` is derived
     from which `run_*` flags are set (`image_audit` if `run_ocr` or
     `run_image_audit`; `media_audit` if `run_media_audit` or
     `run_captions_audit`).
  6. **Launches Python and Node concurrently**:
     `python_task = create_task(_run_python_stages(...))` and `node_task =
     create_task(_fetch_node_findings(...))`, then
     `asyncio.wait_for(asyncio.gather(python_task, node_task,
     return_exceptions=True), timeout=_JOB_TIMEOUT_SECONDS)` — on an overall
     timeout, **cancels both tasks** and raises `TimeoutError` (caught by
     the outer `except`, below, which marks the job `failed`).
  7. If the Python stages raised, logs it; if `python_findings` ends up
     empty regardless of why, **raises `RuntimeError`** — "All audit sources
     failed" — the one condition that fails the whole job (Python is
     treated as the primary, required source of truth; Node is optional).
  8. If the Node task raised or returned no findings, appends a warning
     (job continues with Python-only results either way).
  9. `crawled_pages = node_scanned_pages + python_result.crawled_pages` —
     the union of both engines' independently-discovered page lists.
  10. Filters both finding lists by `_allowed_levels(payload.wcag_level)`
      (a finding with no `level` at all passes through unfiltered).
  11. **Merges via `run_cpu(_merge_findings, ...)`** — offloaded to the
      shared CPU process pool (`store/cpu_pool.py`, `08-MODULES-store.md`)
      rather than run inline, since `_merge_findings` can be a nontrivial
      amount of CPU work over potentially thousands of findings on a large
      multi-page crawl.
  12. Applies `effective_filter = filter_rule or payload.success_criteria_id`
      — filters `all_findings` down to just that one `wcag_sc` if set. This
      is the mechanism that makes the per-rule endpoints
      (`rules/run_router.py`) and `rule_evaluator.py`'s single-rule testing
      work: the **same full combined pipeline runs**, and only the report
      is filtered afterward — so requesting one rule doesn't actually skip
      the crawl/OCR/other-stage work, it just narrows what's returned. (This
      also means the earlier-noted dead `run_label_in_name_audit`-style
      flags being silently dropped by `CombinedRequest` doesn't even matter
      for *filtering* — even if those flags worked, they'd only gate which
      *stage* runs, and `effective_filter` would still need a matching
      `wcag_sc` in the merged output to return anything for that SC; since
      no converter emits `wcag_sc="2.5.3"` etc. at all, the filtered result
      is empty regardless.)
  13. Sorts findings `fail` → `needs_review` → `pass`.
  14. Calls `_build_report(...)`, attaches `warnings`/`warning_details`.
  15. **Side effect**: `register_report_assets(job_id, report)` — moves
      every image referenced in the report into the content-addressed asset
      store (`store/assets.py`, `08-MODULES-store.md`) and rewrites
      `image_url`/`element.image_src` to point at `/api/v1/assets/{id}`;
      any leftover un-registered image paths get the legacy
      `/api/v1/combined/{job_id}/image?path=...` URL as a fallback (lines
      483-505).
  16. **Side effect**: writes `<output_dir>/combined_report.json`
      (`json.dump` with a custom `_json_serializer` for non-standard types —
      see `preprocessor/text_helper_models.py` in
      `09-MODULES-text-classifier-i18n.md`).
  17. **Truncates the in-memory `passes` array to 100** if larger (setting
      `summary["passes_truncated"] = True`) — the on-disk JSON and the
      durable store still get the full set (`repo.save_findings` runs on
      `report` before this truncation... actually **after** — let me note
      the actual order: truncation happens at line ~512-515, *before*
      `repo.save_report`/`save_findings` at line ~529-530, so **the durable
      DB copy is also truncated to 100 passes**; only the file at
      `report_path` (written earlier, line ~507-511) has the full set).
  18. Marks the job `completed` (hot cache + durable), saves findings/pages
      to SQLite, emits a `job_complete` event row.
  19. **Email delivery** (lines 548-558): if `payload.email` is set, renders
      the PDF (`build_report_pdf` — must run on this event loop since
      Playwright's async API is loop-bound) then sends the email via
      `asyncio.to_thread` (since `smtplib` blocks) — explicitly dispatched
      **only after** the run is fully persisted, so a mail failure can never
      turn a completed, stored audit into a reported failure.
  20. Logs run timing (`log_run_timing`), emits the stage-timing summary
      file, logs a final summary line, broadcasts `job_complete` over SSE.
  21. **On any exception** anywhere in the above (lines 602-683): captures
      the traceback and the exact `file:line in function()` origin;
      determines `current_stage` from whichever stage(s) were still
      `running` when the exception hit (falls back to the job's
      `current_stage` field, or `"post_processing"` if nothing was
      running); generates an opaque `error_id`; logs the full detail
      server-side; marks the job `failed` (hot cache + durable) with **only**
      the generic message `"Audit failed due to an internal error."` and the
      `error_id`/`error_stage` — never the exception type/message/traceback
      — exposed to the client; still logs run timing and the stage-timing
      summary for the failed run; broadcasts `job_failed`.
  22. `finally: await asyncio.sleep(0)` — yields control once at the very
      end (lets other pending callbacks/tasks get a turn before this
      coroutine's frame is torn down).

### `ka11y/api/v1/combined/routes.py` (774 lines)
The FastAPI route handlers — the HTTP surface of everything above.
- `FindingReviewRequest(BaseModel)` (lines 39-46): `status` (pattern
  `pass|violation|needs_review`), `note` (≤2000 chars), `reviewer`
  (≤200 chars) — the manual-review submission shape.
- **SSRF guard, third independent copy** (lines 48-210): `_BLOCKED_NETWORKS`
  (15 CIDR ranges — the same family of ranges as `crawler/_ssrf_guard.py`
  and `crawler/optimized/engine.py`'s copies, plus an explicit
  `::ffff:127.0.0.1/128` entry not present in the other two copies),
  `_ip_is_blocked`, `_is_non_public_ip` (adds `is_multicast`/`is_reserved`/
  `is_unspecified` checks on top of `_ip_is_blocked`),
  `build_ssrf_route_handler(page)` (a Playwright route-handler factory using
  a regex `_IP_HOST_RE` to detect literal-IP hostnames without a DNS lookup
  in the hot path — **note**: unlike `crawler/_ssrf_guard.py`, this handler
  only catches literal-IP redirect targets, not hostname-based ones needing
  resolution; whether it's actually installed anywhere or superseded by the
  crawler's own guard is not evident from this file alone), `_resolve_all_ips`
  (async `getaddrinfo` via `asyncio.to_thread`), and `assert_public_url(url)`
  (lines 157-210) — the function actually used as the entry-point guard for
  every submission route: rejects non-`http(s)` schemes, missing hostname,
  literal `"localhost"`, a literal blocked IP, a DNS-resolution failure, no
  resolved addresses, or **any** resolved address being blocked (samples up
  to 3 in the error message).
- `POST /python-audit` → `submit_python_audit(payload: CombinedRequest)`
  (lines 213-226): thin wrapper around `_admit_run(payload)` — despite its
  docstring still describing "form audit (3.3.x), and label-in-name audit
  (2.5.3)" as things it runs, per the correction note those stages don't
  exist; the docstring is stale relative to the current `CombinedRequest`
  schema.
- `POST /combined-audit` → `submit_combined_audit(url, max_depth=0,
  max_pages=20, wcag_level="AAA", email=None, lang="auto")` (lines 229-271):
  a **query-parameter convenience endpoint** (not a JSON body) — builds a
  `CombinedRequest` with every audit toggle forced `True` and calls
  `_admit_run`.
- `_admit_run(payload, *, rerun_of=None) -> dict` (lines 275-309): the
  shared submission path for both routes above (and `rerun_combined_audit`
  below) — generates a `job_id`, calls `assert_public_url(url)` (the SSRF
  gate — note this runs **before** the job is queued, so a blocked URL
  never reaches the dispatcher/crawler at all), seeds the hot `_jobs` entry,
  calls `dispatcher.enqueue(job_id, payload)`.
- `POST /{job_id}/rerun` (lines 312-337): looks up the original run's stored
  params from SQLite, reconstructs a `CombinedRequest`, and re-submits via
  `_admit_run` — returns a **new** `job_id` (the original run is preserved
  for comparison), explicitly for re-running after an engine improvement
  without re-entering the URL/toggles.
- `_inject_image_urls` / `_apply_reviews_to_job` / `_finalize_job_view`
  (lines 340-388): shared post-processing applied to every job dict before
  it's returned to a client — rewrites any still-bare on-disk image path
  into a servable URL (fallback for images that predate the content-
  addressed asset store, or weren't registered for some reason), and
  overlays stored manual-review decisions (`apply_reviews` from `report.py`)
  so the returned score always reflects the latest review state.
- `GET /history` (lines 390-405): paginated (`limit`≤200, `offset`≥0)
  listing straight from the durable `runs` table — available even for runs
  evicted from the hot cache.
- `_job_from_db(job_id) -> Optional[dict]` (lines 408-433): reconstructs a
  `JobStatusResponse`-shaped dict from SQLite for a job no longer in
  `_jobs` (restart or TTL eviction) — only fetches the full report
  (`repo.get_report`) if the run's status is `completed`.
- `POST /{job_id}/cancel` (lines 436-453): **cooperative** cancellation —
  marks the run `cancelled` in the DB (and hot cache, if present); the
  actual worker is expected to check this status between stages and abort
  (the check point observed directly in `runner.py` is only at the very
  start of `_run_job_body`, before any stage launches — meaning a job
  already past that check runs to completion regardless of a later cancel
  request; this route's own docstring's claim that "the worker checks the
  DB status between stages" is not borne out by what `_run_job_body` itself
  actually checks, which is a discrepancy worth verifying against `stages.py`
  before relying on mid-run cancellation).
- `GET /{job_id}` (lines 456-480): the main polling endpoint — hot-cache
  lookup with a **durable fallback** (`_job_from_db`) if not found in
  `_jobs`; reads the hot entry under its per-job lock and makes a shallow
  copy (plus a fresh copy of the mutable `stages` list) so a concurrent
  `runner.py` update can't be observed half-applied; always runs
  `_finalize_job_view` before returning.
- `GET /{job_id}/reviews` (lines 483-490) and `POST
  /{job_id}/findings/{finding_id}/review` (lines 493-537): list/record
  manual-review decisions — the POST validates the `finding_id` actually
  corresponds to a current `needs_review` item in the report before
  accepting the review (rejecting reviews on findings that don't exist or
  aren't reviewable), persists via `repo.set_finding_review`, logs a
  `finding_reviewed` event.
- `GET /{job_id}/timings` (lines 540-588): returns the same
  `compute_run_timing` structure documented in `03-MODULES-config-utils.md`
  (`utils/run_timing.py`) — from the hot cache if present (safe to poll
  mid-run — unfinished stages report `duration_s: null`), else rebuilt from
  the durable `stage_timings` table for an evicted/restarted run.
- `GET /{job_id}/image` (lines 591-678) — the **legacy, deprecated** image
  server, explicitly marked as superseded by the content-addressed
  `/api/v1/assets/{id}` route, kept only for images that predate that
  system:
  1. Validates the requested `path` query param exactly matches one of the
     paths recorded in the job's own `contrast_report`/`image_audit_report`
     `images` list (an allowlist derived from the job's own data, not an
     open filesystem read).
  2. Resolves both the request and every valid path to their canonical
     absolute form and compares as strings (defeats `../`-style traversal
     attempts that would otherwise still string-match a listed path).
  3. **Second containment layer** (lines 630-672): even given a valid
     recorded path, checks the resolved path is still inside the configured
     output root **or** the job's own output directory **or its parent**
     (the parent is included because the image crawler's own
     domain+timestamp directory is a *sibling* of the combined job's
     `..._combined` directory, not nested inside it) — defense-in-depth
     against a "poisoned" auditor record somehow pointing at a symlink
     escaping the tree.
  4. Serves via `FileResponse` with a guessed MIME type.
- `GET /{job_id}/stream` (lines 681-774) — the SSE endpoint:
  - If the job isn't in the hot cache, falls back to a **one-shot terminal
    event** synthesized from the durable store (`job_complete`/`job_failed`/
    a bare `job_state`) rather than 404ing a since-completed run.
  - Otherwise: registers a fresh `asyncio.Queue` in `_subscribers[job_id]`;
    the generator first replays the job's *current* state (either an
    immediate terminal event if already done, or a `job_state` snapshot of
    `current_stage`/`stages` if in progress) so a client connecting mid-run
    isn't starting from nothing; then loops reading the queue with a 25s
    timeout, sending a `: keepalive` comment line on timeout (SSE
    heartbeat, also prevents some proxies from closing the idle
    connection), breaking on a `None` sentinel or a terminal event; always
    deregisters its queue in a `finally`.

---

## (E) Narrower standalone endpoints

### `ka11y/api/v1/crawl.py` (173 lines)
`POST /api/v1/crawl/` — the original, simplest pipeline: crawl → OCR
(optional) → image audit (optional), all sharing one output directory via
FastAPI's `Depends` system. Structurally near-identical to `pipeline.py`
below (this file predates it, per the docstrings' phrasing) — builds its own
`audit_summary` dict inline (total/passed/failed/pass_rate/per-criterion
fail counts/`by_classification`) rather than reusing
`findings._build_image_audit_report`. On any exception, generates an opaque
`error_id`, logs the full traceback server-side, and returns a generic 500
with only the `error_id` — the same "never leak internals to the client"
pattern used throughout the `combined/` subsystem.

### `ka11y/api/v1/pipeline.py` (368 lines)
`POST /api/v1/pipeline/` — the same three-step flow as `crawl.py`, plus a
structured `contrast_report` built by its own `extract_contrast_report`
(lines 49-217) — a near-duplicate of `findings._build_contrast_report`
minus the `page_url`/`classification` enrichment (this endpoint has no
multi-page-crawl page-grouping concept). `PipelineRequest`'s five
dead `run_*_audit` fields (documented under (B) above) are accepted but
never read by this handler.

### `ka11y/api/v1/rule_evaluator.py` (186 lines)
`POST /api/v1/test/rule` — the "Individual Rule Tester" backing a UI feature
that lets someone switch between rules against the same URL without
re-crawling every time.
- `_SNAPSHOT_CACHE: Dict[str, Any]` (module-level, line 40): caches the full
  `PageSnapshot` per URL string across requests within this process's
  lifetime (no TTL) — `force_refresh` on the request bypasses it.
- `JOB_ID = "rule_evaluator"` (line 42): a **single shared, fixed job ID**
  for every rule-test request (not a per-request UUID) — `_ensure_job_registered()`
  (lines 52-65) lazily creates a minimal `_jobs["rule_evaluator"]` entry
  since the stage-lifecycle helpers this file reuses (`_stage_start` etc.,
  called transitively through `_stage_image_audit`/
  `_stage_media_audit_universal`) assume `_jobs[job_id]` exists. **Practical
  consequence**: concurrent rule-test requests share one job's `stages`
  list and SSE-adjacent state — fine for a single-operator testing UI, not
  safe for concurrent multi-user use of this specific endpoint.
- `POST /rule` → `execute_rule_test(request: TestRuleRequest)` (lines 68-185):
  1. For `rule_id` in `{wcag_3_2_3, wcag_3_2_4, wcag_3_1_3, wcag_2_4_10}`
     (consistent-navigation, consistent-identification, unusual-words,
     section-headings — all **Node-side** rules with no Python
     implementation): proxies directly to `{NODE_BASE_URL}/api/v1/rules/{sc}/analyse-url`
     and returns its findings verbatim.
  2. For `wcag_1_2_1`/`wcag_1_2_2`: gets or builds the cached snapshot, calls
     `_stage_media_audit_universal` directly (bypassing `_run_python_stages`
     entirely — a lighter-weight direct call), filters findings to the
     requested SC.
  3. For `wcag_1_1_1`/`wcag_1_4_3`/`wcag_1_4_5`/`wcag_1_4_6`/`wcag_1_4_11`/
     `wcag_4_1_2`: calls `_stage_image_audit` directly (`run_ocr` only set
     `True` for the two contrast rules, to skip an unnecessary OCR pass for
     the others), filters to the requested SC.
  4. Anything else: `400 Bad Request` — "Rule '...' is not supported." This
     is the confirmation that, unlike `rules/run_router.py`'s dynamically
     generated `/rules/{rule_id}/run` endpoints (which accept *any* rule ID
     in `RULE_FLAGS`, including ones with no working auditor — see (F)
     below), this narrower tester only accepts rule IDs it can actually
     evaluate.

---

## (F) `rules/` — WCAG metadata + per-rule background-job runner

### `ka11y/api/v1/rules/__init__.py` (12 lines)
Mounts `metadata_router` and `run_router` under `APIRouter(prefix="/rules")`.

### `ka11y/api/v1/rules/metadata.py` (106 lines)
`GET /api/v1/rules/wcag?lang=...` — returns the full WCAG rules catalogue
(id, level, severity, name, description, suggested_fix, each with a
localized `*_label` companion) plus top-level localized dictionaries for
severities/levels/statuses, sourced entirely from `i18n.loader.load_bundle`/
`load_rules` (`09-MODULES-text-classifier-i18n.md`). Sanitizes the `lang`
query param to `[a-zA-Z-]`, max 10 chars, before use. `_sc_sort_key` (lines
53-58) sorts SC IDs numerically component-by-component (`"1.4.12"` sorts
after `"1.4.2"`, unlike a plain string sort) — unparseable IDs sort last via
a `(999,)` fallback key.

### `ka11y/api/v1/rules/run_router.py` (144 lines)
Dynamically generates two POST routes per rule ID in `RULE_FLAGS` — **19
entries covering both still-implemented and long-removed criteria**
(`1.1.1, 1.2.1, 1.4.3, 1.4.6, 1.4.11, 1.4.5, 3.3.1, 3.3.2, 2.5.3, 2.2.2,
2.5.8, 1.4.12, 1.4.4, 1.4.10, 1.3.4, 1.4.13, 2.4.11, 2.4.12, 1.3.3`):
`/{rule_id}/run` (full `RuleRunRequest` — depth/pages/internal_links/lang)
and `/{rule_id}/analyse-url` (URL-only, depth forced to 0).
- `create_rule_handler`/`create_rule_url_only_handler` (lines 41-64): closure
  factories producing the actual route coroutines, both delegating to
  `_submit_rule_job`.
- `_submit_rule_job(*, rule_id, url, max_depth, lang, internal_links=True,
  max_pages=50)` (lines 67-123):
  1. `await assert_public_url(url)` (imported from `combined/routes.py` —
     the same SSRF guard, reused rather than duplicated a fourth time).
  2. **Builds the `flags` dict**: starts with every `run_*` field on
     `CombinedRequest` set `False`, then updates with `RULE_FLAGS[rule_id]`.
     **As established above under (B) and in `01-OVERVIEW-AND-ENTRYPOINT.md`'s
     correction note**: for a `rule_id` whose `RULE_FLAGS` entry names a flag
     that doesn't exist on the current `CombinedRequest` (everything except
     `1.1.1`, `1.2.1`, `1.4.3`, `1.4.6`, `1.4.11`, `1.4.5` — i.e. `3.3.1`,
     `3.3.2`, `2.5.3`, `2.2.2`, `2.5.8`, `1.4.12`, `1.4.4`, `1.4.10`,
     `1.3.4`, `1.4.13`, `2.4.11`, `2.4.12`, `1.3.3`), that extra key is
     silently dropped by Pydantic's default `extra="ignore"` behavior when
     `CombinedRequest(url=..., **flags)` is constructed (line 89-96) — no
     error, no warning. The resulting job runs with **every** real audit
     flag `False` (since the base dict zeroed them all and the one meant to
     turn one back on for this rule never took effect), so it completes
     "successfully" but produces **zero findings for any criterion**,
     including the one requested. This is a live, reachable HTTP endpoint
     (`POST /api/v1/rules/2.5.3/run`, etc.) that silently does nothing
     useful for 13 of its 19 advertised rule IDs.
  3. Registers the job in `_jobs`, launches `asyncio.create_task(_run_job(job_id,
     combined_payload, filter_rule=rule_id))` — **note**: this bypasses the
     durable dispatcher entirely (calls `runner._run_job` directly, not
     `dispatcher.enqueue`), so jobs submitted through this router are
     **not crash-recoverable** and don't appear in `repo`'s `runs` table
     the way `combined/routes.py`-submitted jobs do.
  4. Logs and returns the job dict.
- Route registration loop (lines 127-143): for each `rule_id`, registers
  both routes via `router.add_api_route(...)`, response model
  `JobStatusResponse`, status code 202 — this is what makes all 19×2 = 38
  routes show up in the Swagger/OpenAPI docs even though only 6 rule IDs
  actually produce non-empty results.
