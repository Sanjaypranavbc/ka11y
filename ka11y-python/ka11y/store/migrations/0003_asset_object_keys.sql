-- ka11y schema v3: where an asset's bytes live in object storage (S3 or the
-- local artifact dir). NULL = never uploaded (storage off) — the on-disk
-- rel_path under KA11Y_ASSET_DIR is then the only copy.
ALTER TABLE assets ADD COLUMN object_key TEXT;
ALTER TABLE assets ADD COLUMN object_bucket TEXT;
