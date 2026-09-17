-- Severity per finding (critical|serious|moderate|minor), so the admin
-- console can rank failing criteria without decompressing every report.
ALTER TABLE findings ADD COLUMN severity TEXT;
