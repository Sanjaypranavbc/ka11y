-- ka11y schema v2: manual-review decisions on needs_review findings.
-- A reviewer adjudicates a "Manual Review Required" item to pass/violation; the
-- effective score (counts of violations / needs_review / passes) reflects it.
CREATE TABLE IF NOT EXISTS finding_reviews (
    run_id      TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    finding_id  TEXT NOT NULL,           -- report._finding_signature → sha1[:16]
    status      TEXT NOT NULL,           -- 'pass' | 'violation'
    note        TEXT,
    reviewer    TEXT,
    wcag_sc     TEXT,
    page_url    TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, finding_id)
);
CREATE INDEX IF NOT EXISTS idx_finding_reviews_run ON finding_reviews(run_id);
