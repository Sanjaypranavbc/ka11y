# 4. Module-by-Module Breakdown — Group 6: Durable Store (`store/`)

Persistence, deliberately separated from `api/`: SQLite (WAL, single
writer), a content-addressed asset store, a shared CPU process pool, and a
retention sweep. Reused by background tasks (dispatcher, retention) that
aren't triggered by an HTTP request at all.

---

## `ka11y/store/__init__.py` (29 lines)

Package docstring (module map: `db.py`, `repo.py`, `assets.py`,
`cpu_pool.py`) and three stated **design invariants** worth repeating
verbatim since they explain every other file in this group: (1) **one
writer** — all writes funnel through a single background thread owning one
connection, so SQLite never raises "database is locked"; (2) **degrade,
never fail** — persistence on the audit hot-path is wrapped so a DB error
logs and is swallowed, never fails an audit; (3) **SQLite-swappable** — all
SQL is parameterized and lives in this package, so a future Postgres move
is mechanical. Re-exports `Database`, `get_db`, `init_db`, `shutdown_db`
from `db.py`.

---

## `ka11y/store/db.py` (283 lines)

**Purpose**: the single-writer SQLite wrapper — the foundation everything
else in this group sits on.

**Imports**: `asyncio`, `os`, `queue`, `sqlite3`, `threading`,
`concurrent.futures.Future`, `pathlib.Path`, `typing.*` (stdlib only);
`ka11y.config.logger.setup_logger` (internal).

**Module-level**: `_MIGRATIONS_DIR` (line 44, `store/migrations/`);
`_SHUTDOWN = object()` (line 47, sentinel pushed onto the write queue to
stop the writer thread — a unique sentinel object rather than `None`, so it
can never collide with a legitimate queue item).

**`_default_db_path() -> str`** (lines 50-57): `$KA11Y_DB_PATH` override,
else `<ka11y-python>/logs/ka11y.db` — deliberately placed next to the
rotating app logs so one mounted volume (`logs/`) captures both in Docker.

**Class `_WriteItem`** (lines 60-65): a `__slots__`-optimized carrier for
`(fn, future)` pairs pushed onto the write queue.

**Class `Database`** — the single-writer wrapper:
- `__init__(self, path=None)` (lines 71-77): stores the path, a
  `queue.Queue` for writes, a `threading.local()` for per-thread read
  connections, a `threading.Event` (`_started`) and `threading.Lock`
  (`_start_lock`) for idempotent startup.
- `start(self)` (lines 85-99): under `_start_lock`, no-ops if already
  started; else creates the DB directory, **runs migrations synchronously
  on a throwaway connection** (so a migration failure surfaces immediately
  at process startup, not silently later), then spawns the writer thread
  (`daemon=True` — never blocks process exit) and marks started.
- `stop(self)` (lines 101-107): pushes `_SHUTDOWN`, joins the writer thread
  (10s timeout), clears the started flag.
- `_configure(conn)` (lines 111-116): sets `row_factory = sqlite3.Row`,
  `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`,
  `foreign_keys=ON` — applied to **every** connection this class opens
  (writer and every thread-local reader).
- `_open(self) -> sqlite3.Connection` (lines 118-121):
  `sqlite3.connect(path, timeout=30, check_same_thread=False)` +
  `_configure`.
- `_read_conn(self) -> sqlite3.Connection` (lines 123-129): lazily opens
  and caches one connection per calling thread in `self._tls.conn` — since
  WAL mode lets readers never block the writer (and vice versa), each
  thread gets its own persistent read connection rather than opening one
  per query.
- `_migrate(self)` (lines 133-158): creates a `schema_migrations` bookkeeping
  table if absent; reads which versions are already applied; for each
  `*.sql` file in `_MIGRATIONS_DIR` (sorted — so `0001_init.sql` runs before
  `0002_finding_reviews.sql`) not yet applied, runs the whole file via
  `conn.executescript(...)` and records it as applied, committing after
  each file individually (so a later migration failing doesn't roll back
  ones already successfully applied).
- `_writer_loop(self)` (lines 162-189) — **the single-writer thread body**:
  opens one connection, then loops forever pulling `_WriteItem`s off the
  queue; for each, calls `item.fn(conn)`, commits, and resolves the
  item's `Future` with the result — or, on any exception, rolls back and
  either sets the exception on the `Future` (if one exists — the caller
  awaited it) or just logs a warning (fire-and-forget writes have no
  `Future` to fail). Exits on the `_SHUTDOWN` sentinel, always closing the
  connection in `finally`.
- `_submit(self, fn) -> Future` (lines 191-194): pushes a `_WriteItem`
  with a fresh `concurrent.futures.Future`, returns it (not yet
  resolved — the writer thread resolves it asynchronously).
- **Public async API**:
  - `execute(sql, params=()) -> Optional[int]` (lines 198-205): submits a
    single-statement write, awaits the wrapped future
    (`asyncio.wrap_future`), returns `cur.lastrowid`.
  - `executemany(sql, seq_params)` (lines 207-211): batch insert via
    `conn.executemany`.
  - `run_write(fn) -> Any` (lines 213-215): runs an arbitrary
    multi-statement callable atomically on the writer connection (used by
    `assets.py`'s insert-then-select-id pattern, documented below).
  - `enqueue(sql, params=())` (lines 217-229): **fire-and-forget** — pushes
    a `_WriteItem` with `future=None` directly onto the queue without
    awaiting anything; no-ops silently if the DB hasn't started
    (`_started` not set) — used by telemetry sinks (`stage_timings`,
    `run_events`) that must never block or fail the audit hot path.
  - `enqueue_fn(fn)` (lines 231-235): the fire-and-forget multi-statement
    variant.
  - `query(sql, params=()) -> List[Dict]` (lines 237-242): runs on the
    calling thread's cached read connection, offloaded via
    `asyncio.to_thread` (so a slow query doesn't block the event loop),
    returns `[dict(row) for row in cur.fetchall()]`.
  - `query_one(sql, params=()) -> Optional[Dict]` (lines 244-248): `query`
    + take the first row.

**Module singleton** (lines 251-283): `get_db()` lazily creates+starts a
process-wide `Database` under a module-level `threading.Lock` (double-
checked locking); `init_db(path=None)` is the explicit variant `main.py`'s
lifespan calls at startup (accepts an override path, useful for tests);
`shutdown_db()` stops and clears the singleton.

**Side effects**: opens SQLite connections; creates the DB file and its
parent directory; runs a background writer thread for the life of the
process.

**Used elsewhere**: every other file in this group, plus `runner.py`,
`dispatcher.py`, `stage_events.py`, `stage_timing.py`, `run_timing.py`
(via `repo`), and `api/v1/assets.py` (`admin_metrics` reads `get_db()`
directly for ad-hoc rollup SQL).

---

## `ka11y/store/repo.py` (490 lines)

**Purpose**: the high-level CRUD layer over `db.py` — every SQL statement
in the whole application lives here (per the module docstring's stated
Postgres-swap invariant), split into hot-path writes (errors swallowed) and
reads (errors propagate to the API layer as normal HTTP errors).

**Imports**: `json`, `time` (unused directly it seems — likely vestigial),
`zlib`, `datetime.datetime/timezone`, `typing.*` (stdlib);
`ka11y.config.logger.setup_logger`, `ka11y.store.db.get_db` (internal).

**Time helpers**: `_now() -> str` (ISO UTC now); `_parse_iso(ts)` (tolerant
ISO parse, `None` on failure); `_ms_between(a, b) -> Optional[int]`
(milliseconds between two ISO timestamps, `None` if either is missing).

**Run lifecycle** (hot-path writes, each wrapped in `try/except Exception`
logging a warning on failure — never raises):
- `create_run(*, run_id, url, status, lang_requested, wcag_level, params,
  max_depth, max_pages, submitted_at)` (lines 54-86): `INSERT OR REPLACE`
  into `runs`, serializing `params` (the full `CombinedRequest`) as JSON.
- `update_run(run_id, **fields)` (lines 89-99): **the generic single-row
  updater** every other `mark_*` function delegates to — builds `SET
  k1=?, k2=?, ...` dynamically from the kwargs' *keys* (never their
  values, which are always parameterized) — this is the dynamic-SQL
  fragment the earlier security review's SQLi analysis specifically
  checked and cleared: column names come only from hard-coded caller
  kwargs, never from request data.
- `mark_running` / `mark_queued` / `mark_completed` / `mark_failed` (lines
  102-149): each a thin `update_run(...)` call setting the relevant status
  and derived fields (`mark_running` computes `queue_wait_ms` via
  `_ms_between`; `mark_completed`/`mark_failed` compute `wall_ms`).
- `_pid()` (lines 152-155): `os.getpid()` (imported locally, not at module
  scope — minor style note).

**Report + findings**:
- `_compress_report(report) -> tuple` (lines 161-166): pure CPU function
  (JSON-serialize + zlib level 6) — deliberately a **top-level, picklable**
  function so it can run in the shared `ProcessPoolExecutor` (`cpu_pool.py`)
  for large multi-page reports without blocking the event loop.
- `save_report(run_id, report)` (lines 169-181): runs `_compress_report`
  via `cpu_pool.run_cpu`, `INSERT OR REPLACE` into `run_reports`
  (`report_zlib` BLOB, `bytes_raw`, `bytes_stored`).
- `save_findings(run_id, report)` (lines 184-223): flattens
  `violations`/`needs_review`/`passes` into individual `findings` rows
  (denormalized, for fast per-SC/per-page SQL queries later) — `selector`
  is JSON-stringified if it's a list; `element_json` is the whole element
  dict, truncated to 4000 chars; `source` derived from `f["source"]` or
  inferred `"axe"` if an `axe_rule_id` is present else `"python"`. Batched
  via `executemany`.
- `save_pages(run_id, pages)` (lines 226-250): inserts `run_pages` rows,
  filtering out any entry with no resolvable URL.

**Events/telemetry** (fire-and-forget, **not `async`** — called from any
context including a background thread):
- `insert_event(run_id, event, data=None)` (lines 256-264): enqueues an
  `run_events` row.
- `insert_timing(row: Dict)` (lines 267-291): enqueues a `stage_timings`
  row — this is the function `utils/crawler_timing.py`, `utils/stage_timing.py`,
  and `utils/run_timing.py` all call to mirror their file-based logs into
  the durable store (documented in `03-MODULES-config-utils.md`).

**Reads** (propagate exceptions — no `try/except` here):
- `get_run(run_id)`, `list_runs(*, limit, offset, url=None, status=None)`
  (lines 297-331 — builds a dynamic `WHERE` clause from optional filters,
  each condition still parameterized; deserializes `summary_json` into
  `summary` on each row), `get_report(run_id)` (decompresses `run_reports.report_zlib`
  back into the full report dict — catches and logs a decompression
  failure specifically, returning `None`), `get_events(run_id)`,
  `get_timings(run_id)`.

**Queue / crash recovery**:
- `requeue_running() -> List[Dict]` (lines 372-395) — called once at
  dispatcher startup: finds every row still `running` or `queued` from a
  prior process (a crash mid-job, or a queued-but-never-dispatched row);
  for each, increments its `attempt` counter — if it now exceeds
  `$KA11Y_MAX_ATTEMPTS` (default 2), marks it permanently `failed`
  (`error_stage="crash_recovery"`); otherwise resets it to `queued` and
  includes it in the returned "requeued" list.
- `next_queued(limit) -> List[Dict]` (lines 398-405): the dispatcher's
  drain query — up to `limit` `queued` rows, oldest `submitted_at` first
  (FIFO).
- `count_running()`, `is_cancelled(run_id)` (lines 408-417).

**Retention**:
- `retention_sweep(retention_days) -> List[str]` (lines 423-438): deletes
  every `completed`/`failed`/`cancelled` run older than the cutoff — `ON
  DELETE CASCADE` in the schema removes child rows (findings, reports,
  pages, asset metadata) automatically; returns the removed run IDs so
  `retention.py` can separately prune the corresponding **asset files**
  (the DB doesn't know about on-disk bytes).

**Manual-review decisions**:
- `set_finding_review(*, run_id, finding_id, status, note=None,
  reviewer=None, wcag_sc=None, page_url=None)` (lines 444-471): `status=
  "needs_review"` **deletes** the row (re-opening the item); otherwise
  `INSERT ... ON CONFLICT(run_id, finding_id) DO UPDATE` (upsert) into
  `finding_reviews`.
- `get_reviews(run_id) -> Dict[finding_id, Dict]` (lines 474-481): all
  review rows for a run, keyed by `finding_id` — the shape `report.apply_reviews`
  (`07-MODULES-api.md`) expects.
- `list_run_assets(run_id)` (lines 484-489): all `assets` rows for a run.

**Side effects**: every write function ultimately calls into `db.py`'s
writer thread (disk I/O, serialized). Nothing here touches the filesystem
directly except indirectly via SQLite's own file.

**Used elsewhere**: `api/v1/combined/dispatcher.py`, `runner.py`,
`routes.py`, `assets.py` (below), `api/v1/assets.py`'s `admin_metrics`
(direct `get_db()` SQL, bypassing `repo.py`), and the telemetry modules in
`utils/`.

---

## `ka11y/store/assets.py` (233 lines)

**Purpose**: the content-addressed asset store — every image the report
references gets deduplicated by content hash and served through
`/api/v1/assets/{id}` instead of a raw filesystem path.

**Imports**: `hashlib`, `mimetypes`, `os`, `shutil`, `dataclasses.dataclass`,
`pathlib.Path`, `typing.*` (stdlib); `ka11y.config.logger.setup_logger`,
`ka11y.store.db.get_db` (internal).

**`asset_dir() -> Path`** (lines 31-36): `$KA11Y_ASSET_DIR` override, else
`<ka11y-python>/logs/assets/` — placed under the same bind-mountable tree
as the app logs/DB, per the comment, "so existing volume mounts work."

**Class `AssetRef`** (`@dataclass`, lines 39-48): `asset_id`, `rel_path`,
`sha256`, `bytes`, with a computed `.url` property
(`/api/v1/assets/{asset_id}`).

**`_ext_for(mime, src_name) -> str`** (lines 51-58): prefers the source
filename's own extension, falls back to `mimetypes.guess_extension(mime)`,
defaults to `"bin"`.

**`put_asset(*, run_id, kind, data, page_url=None, mime=None, width=None,
height=None) -> Optional[AssetRef]`** (lines 61-130) — the write path:
1. Accepts either raw `bytes` or a path (`str`/`Path`) to read from.
2. `sha = hashlib.sha256(raw).hexdigest()`; builds `rel_path =
   "{run_id}/{kind}/{sha[:2]}/{sha}.{ext}"` — the `sha[:2]` fan-out
   directory is a classic technique to avoid tens of thousands of files in
   one flat directory.
3. **Side effect**: if `dest` doesn't already exist, writes to a `.tmp`
   sibling and `os.replace(tmp, dest)` — atomic publish, so a concurrent
   reader of the same content-addressed path (e.g. the same logo
   registered from two different findings) never observes a partially-
   written file.
4. **Critical correctness detail, documented at length in the code itself**
   (lines 97-106): the DB row is inserted via `INSERT OR IGNORE` (so a
   duplicate `(run_id, rel_path)` — the same image registered by a second
   finding — is a no-op, not an error), but the asset `id` **must be read
   back with a `SELECT`**, never taken from `lastrowid` — because when the
   `INSERT OR IGNORE` hits the `UNIQUE(run_id, rel_path)` constraint and
   does nothing, `sqlite3_last_insert_rowid()` still points at whatever the
   *previous* successful insert was, silently handing the caller a
   different image's asset ID. The comment documents this as a real,
   previously-shipped bug: any image referenced by more than one
   finding (the common case — the same crop gets registered once per rule
   that flags it: 1.1.1, then 4.1.2, 1.4.5, 1.4.11) had its first
   registration get the correct thumbnail and every subsequent finding
   silently render whichever *other* image happened to be inserted right
   before it. The fix — `_insert_and_resolve(conn)` (lines 107-118) running
   the `INSERT` and the `SELECT id ... WHERE run_id=? AND rel_path=?` in
   **one atomic writer callback** via `db.run_write(...)` — guarantees the
   returned ID is always for *this* `rel_path`, not whatever raced ahead of
   it.
5. Returns `None` (logging a warning) if the ID couldn't be resolved, or on
   any exception anywhere in the function — **never raises**.

**`get_asset(asset_id) -> Optional[Dict]`** (lines 133-151) — the read path
for the serving endpoint:
1. Looks up the DB row.
2. Resolves `abs_path = (asset_dir().resolve() / rel_path).resolve()`.
3. **Path-traversal guard**: `abs_path.relative_to(base)` — raises
   `ValueError` (caught, logged, returns `None`) if the resolved path
   somehow escapes `asset_dir()` — this is the exact containment check the
   earlier security review's path-traversal analysis of `GET
   /api/v1/assets/{id}` verified as adequate.
4. Returns `None` if the file doesn't actually exist on disk (DB/filesystem
   could have drifted, e.g. after a manual cleanup).

**`_is_local_path(src) -> bool`** (lines 154-163): `True` only for a real
on-disk file — explicitly excludes anything starting with `http://`,
`https://`, `data:`, or `/api/v1/` (already-served/remote/inline content
should never be re-registered as a local asset).

**`register_report_assets(run_id, report) -> int`** (lines 166-221) — the
**P2 integration point** called once per completed job by `runner.py`:
1. For every image in `contrast_report`/`image_audit_report`'s `images[]`
   list with a real on-disk `path`: registers it (`kind="contrast_region"`
   or `"ocr_crop"`), then rewrites `img["image_url"]`/`img["asset_id"]`/
   `img["asset_url"]` to point at the new content-addressed URL instead of
   the legacy `?path=` route.
2. For every finding across `violations`/`needs_review`/`passes` whose
   `element.image_src` is a local path (via `_is_local_path`): registers it
   (`kind="finding_image"`), rewrites `element["image_src"]` in place.
3. **Idempotent and best-effort**: wrapped in one outer `try/except` so a
   failure on any single image never aborts the rest of the loop or the
   audit; returns the count actually registered.

**`prune_run_assets(run_id)`** (lines 224-232, **sync**, not async — called
via `asyncio.to_thread` from `retention.py`): `shutil.rmtree(asset_dir() /
run_id, ignore_errors=True)` — the on-disk counterpart to the DB's `ON
DELETE CASCADE` removal of `assets` rows (rows go via cascade when
`retention_sweep` deletes the parent `runs` row; the actual bytes on disk
have to be deleted separately, since SQLite has no idea a `rel_path`
column refers to a real file).

**Side effects**: reads/writes files under `asset_dir()`; DB inserts/reads
via `db.py`.

**Used elsewhere**: `runner.py` (`register_report_assets` after building
the report), `api/v1/assets.py` (`get_asset` for serving), `utils/report_pdf.py`
(`get_asset` when resolving a `/api/v1/assets/{id}` src back to a file for
inlining into the PDF).

---

## `ka11y/store/cpu_pool.py` (92 lines)

**Purpose**: a shared `ProcessPoolExecutor` for CPU-bound work
(`_merge_findings` in `runner.py`, `_compress_report` in `repo.py`) that
would otherwise serialize on one core under `asyncio.to_thread` because of
the GIL.

**Imports**: `asyncio`, `os`, `concurrent.futures.ProcessPoolExecutor`,
`typing.*` (stdlib); `ka11y.config.logger.setup_logger` (internal).

**Contract documented in the module docstring** (lines 14-19): any callable
submitted here must be a **top-level, importable (picklable)** function —
not a lambda, not a closure, not a bound method holding a browser handle —
and its args/return value must be picklable plain data (never a Playwright
page or open file handle).

- `_default_workers() -> int` (lines 38-45): `$KA11Y_CPU_WORKERS` override,
  else `max(1, cpu_count - 1)` (leaves one core for the event loop/OS).
- `get_pool() -> Optional[ProcessPoolExecutor]` (lines 51-70): **opt-in** —
  returns `None` (meaning "use threads instead") unless `$KA11Y_CPU_WORKERS`
  is set to a nonzero value; this default keeps behavior identical to
  before this pool existed and specifically **avoids forking a process pool
  under pytest** (a common source of test-suite flakiness/hangs); lazily
  creates the pool on first real use, falling back to `None` (logged as a
  warning) if `ProcessPoolExecutor(...)` itself fails to start.
- `run_cpu(fn, *args) -> Any` (lines 73-84, async): the public entry point
  — if no pool is configured, `await asyncio.to_thread(fn, *args)`
  (unchanged legacy behavior); otherwise
  `loop.run_in_executor(pool, fn, *args)`, and **any** exception from that
  (pickling failure, a broken pool) is caught and logged, falling back to
  `asyncio.to_thread` — so callers never have to branch on whether the pool
  is actually usable.
- `shutdown_pool()` (lines 87-91): `pool.shutdown(wait=False,
  cancel_futures=True)` — called from `main.py`'s lifespan teardown.

**Side effects**: may spawn OS subprocesses (one interpreter per worker) if
opted in.

**Used elsewhere**: `runner.py` (`_merge_findings`), `repo.py`
(`_compress_report`).

---

## `ka11y/store/retention.py` (39 lines)

**Purpose**: the durable-store counterpart to `combined/store.py`'s
in-memory TTL eviction — periodically deletes old **rows** (and their
on-disk asset files), independent of whether a job is still in the
in-memory hot cache.

**Imports**: `asyncio`, `os` (stdlib); `ka11y.config.logger.setup_logger`,
`ka11y.store.repo`, `ka11y.store.assets.prune_run_assets` (internal).

**Module constant**: `_SWEEP_INTERVAL_SECONDS` (`$KA11Y_RETENTION_SWEEP_SECONDS`,
default 3600 = 1 hour).

**`run_retention_loop()`** (lines 27-38, async, the task `main.py`'s
lifespan starts alongside the dispatcher): reads
`$KA11Y_RUN_RETENTION_DAYS` (default 30) once at the top; loops forever —
sleeps `_SWEEP_INTERVAL_SECONDS`, calls `repo.retention_sweep(retention_days)`
(DB deletion, cascades child rows), then `prune_run_assets(run_id)` (via
`asyncio.to_thread`, since it does blocking `shutil.rmtree`) for every
removed run. `asyncio.CancelledError` re-raises (clean shutdown); any other
exception is caught, logged as a warning, and the loop continues (matches
the module docstring's "never raises" contract).

**Side effects**: deletes SQLite rows and on-disk asset directories on a
1-hour-default schedule.

**Used elsewhere**: started once from `main.py`'s `lifespan` alongside
`dispatcher.run_dispatcher()`.

---

## `ka11y/store/migrations/0001_init.sql` and `0002_finding_reviews.sql`

Not Python, but the schema every function above operates against — included
here for completeness since section 4's per-module contract references
these tables throughout.

**`0001_init.sql`** — the base schema (six tables):
- `runs` — one row per audit job; explicitly documented as "the source of
  truth for job state (replaces the in-memory `_jobs` dict, which is now a
  hot cache layered on top of this table)." Columns cover identity/status,
  requested vs. resolved language, the full `params_json`, timing
  (`submitted_at`/`run_started_at`/`completed_at`/`queue_wait_ms`/`wall_ms`),
  error info, `summary_json`, `attempt` (the crash-requeue counter),
  `worker_pid`, `output_dir`. Indexed on `status`, `url`, and
  `submitted_at DESC`.
- `run_pages` — one row per crawled page (`ON DELETE CASCADE` from `runs`),
  the resolved (post-redirect) URL, depth, HTTP status, crawl duration.
- `run_reports` — the full report as zlib-compressed JSON (one row per
  run), plus raw/stored byte counts for observability.
- `findings` — denormalized individual findings for fast querying (top-N,
  by SC, by page, by status) — indexed on `run_id`, `(run_id, wcag_sc)`,
  `(run_id, status)`.
- `assets` — the content-addressed registry (`UNIQUE(run_id, rel_path)`,
  indexed on `run_id` and `sha256`).
- `stage_timings` — one row per fine-grained instrumented step, explicitly
  noted as replacing "4 log-file formats" (the file-based timing logs in
  `utils/`) with one queryable table.
- `run_events` — the durable lifecycle/SSE event log, enabling SSE replay
  and post-hoc auditing of exactly what happened during a run.

**`0002_finding_reviews.sql`** — adds `finding_reviews` (composite primary
key `(run_id, finding_id)`, `ON DELETE CASCADE` from `runs`) for the
manual-review-decision feature (`report.apply_reviews`,
`07-MODULES-api.md`).

Both migrations are applied automatically, in filename order, by
`db.py`'s `_migrate()` — the migration mechanism is intentionally minimal
(a bookkeeping table of applied version-stems, each file run once via
`executescript`), with no down-migrations or rollback tooling.
