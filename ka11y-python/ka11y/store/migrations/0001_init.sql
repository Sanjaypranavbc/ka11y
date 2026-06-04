-- ka11y schema v1
-- One row per audit job. Source of truth for job state (replaces the in-memory
-- _jobs dict, which is now a hot cache layered on top of this table).
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    status          TEXT NOT NULL,              -- queued|running|completed|failed|cancelled
    lang_requested  TEXT,
    lang_resolved   TEXT,
    wcag_level      TEXT,
    params_json     TEXT NOT NULL,              -- full CombinedRequest (toggles, depth, max_pages)
    max_depth       INTEGER,
    max_pages       INTEGER,
    submitted_at    TEXT NOT NULL,
    run_started_at  TEXT,
    completed_at    TEXT,
    queue_wait_ms   INTEGER,
    wall_ms         INTEGER,
    error_id        TEXT,
    error_stage     TEXT,
    summary_json    TEXT,                        -- {violations, needs_review, passes, score}
    attempt         INTEGER NOT NULL DEFAULT 0,  -- crash-requeue counter
    worker_pid      INTEGER,
    output_dir      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_runs_status    ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_url       ON runs(url);
CREATE INDEX IF NOT EXISTS idx_runs_submitted ON runs(submitted_at DESC);

-- Per-page crawl record (enables page-scoped reporting straight from the DB).
CREATE TABLE IF NOT EXISTS run_pages (
    id           INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    page_url     TEXT NOT NULL,                  -- RESOLVED url (post-redirect)
    depth        INTEGER,
    http_status  INTEGER,
    crawl_ms     INTEGER,
    snapshot_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_pages_run ON run_pages(run_id);

-- The full report, zlib-compressed JSON. One row per run.
CREATE TABLE IF NOT EXISTS run_reports (
    run_id      TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    report_zlib BLOB NOT NULL,
    bytes_raw   INTEGER,
    bytes_stored INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Individual findings, denormalized for querying (top-N, by SC, by page).
CREATE TABLE IF NOT EXISTS findings (
    id           INTEGER PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    page_url     TEXT,
    wcag_sc      TEXT,
    level        TEXT,
    status       TEXT,                           -- fail|needs_review|pass
    source       TEXT,                           -- axe|python
    reason_code  TEXT,
    selector     TEXT,
    element_json TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_findings_run    ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_sc     ON findings(run_id, wcag_sc);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(run_id, status);

-- Asset registry: bytes on disk under KA11Y_ASSET_DIR, metadata here.
CREATE TABLE IF NOT EXISTS assets (
    id          INTEGER PRIMARY KEY,
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    page_url    TEXT,
    kind        TEXT NOT NULL,                   -- screenshot|ocr_crop|har|dom_snapshot|contrast_region
    rel_path    TEXT NOT NULL,                   -- relative to KA11Y_ASSET_DIR
    sha256      TEXT NOT NULL,
    mime        TEXT,
    width       INTEGER,
    height      INTEGER,
    bytes       INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(run_id, rel_path)
);
CREATE INDEX IF NOT EXISTS idx_assets_run ON assets(run_id);
CREATE INDEX IF NOT EXISTS idx_assets_sha ON assets(sha256);

-- Telemetry: one row per fine-grained step (replaces the 4 log-file formats).
CREATE TABLE IF NOT EXISTS stage_timings (
    id          INTEGER PRIMARY KEY,
    run_id      TEXT NOT NULL,
    page_url    TEXT,
    depth       INTEGER,
    stage       TEXT NOT NULL,
    sub_stage   TEXT,
    rule        TEXT,
    duration_ms REAL,
    item_count  INTEGER,
    status      TEXT,                            -- ok|error|timeout
    error       TEXT,
    extra_json  TEXT,
    ts          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timings_run   ON stage_timings(run_id);
CREATE INDEX IF NOT EXISTS idx_timings_stage ON stage_timings(run_id, stage);

-- Job lifecycle / SSE event log (durable progress; survives restart; SSE replay).
CREATE TABLE IF NOT EXISTS run_events (
    id        INTEGER PRIMARY KEY,
    run_id    TEXT NOT NULL,
    event     TEXT NOT NULL,
    data_json TEXT,
    ts        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);
