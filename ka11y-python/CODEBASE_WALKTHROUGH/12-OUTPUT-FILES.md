# 7. Output Directory & File Creation (Detailed)

Every `mkdir`/`os.makedirs` and every file-write call in `ka11y-python/ka11y/`,
found via `grep -rn "\.mkdir(\|os\.makedirs(" ` and `grep -rn 'open(...,"w"\|write_text\|write_bytes\|\.open("a"'` over the whole package. Line
numbers are as of commit `b734e3b`.

## 7.1 Where the root output directory comes from

`config["input"]["output_dir"]` — `"crawled_images"`, a **relative path**,
read from (in priority order) `<repo_root>/config/universal.yml` if it
exists, else `<ka11y-python>/ka11y/config/config.yml`
(`utils/config_loader.load_config`, `03-MODULES-config-utils.md`). Because
it's relative, **every directory this service creates under it is rooted at
whatever the process's current working directory happens to be when it
first resolves the path** — in the Docker image that's `/app` (the
`WORKDIR`); running locally it's wherever you launched `uvicorn` from.
Three independent call sites resolve it slightly differently:

- `api/v1/dependencies.get_output_dir` (`dependencies.py:58`) —
  `Path(config["input"]["output_dir"]).resolve()`, then builds
  `<base>/<safe_domain>_<MMDD_HHMM>_<uuid8>` and asserts the final resolved
  path still starts with the resolved base (traversal guard, § `07-MODULES-api.md` (C)).
- `crawler/optimized/optimized_crawler.OptimizedImageCrawler.__init__`
  (`optimized_crawler.py:83-86`) — `base_out = CONFIG["input"]["output_dir"]`
  used **unresolved** (no `.resolve()`), building
  `f"{base_out}/{domain}_{timestamp}"` as a plain string.
- `api/v1/combined/runner._run_job_body` (`runner.py:317-321`) — same
  pattern as above but with a `_combined` suffix:
  `f"{config['input']['output_dir']}/{domain}_{ts}_{job_id[:8]}_combined"`.

None of these three naming schemes coordinate with each other beyond
sharing the same `output_dir` root — a combined-audit run's own directory
(`..._combined`) is a **sibling** of the image crawler's own
`{domain}_{timestamp}` directory it spawns internally (this is exactly why
`combined/routes.py`'s legacy image-serving endpoint has to check both the
job's own dir **and its parent** for containment, § `07-MODULES-api.md` (D)).

## 7.2 The combined-audit run directory (the primary output tree)

**Created**: `runner._run_job_body`, `runner.py:319-322` —
`output_dir.mkdir(parents=True, exist_ok=True)` — eagerly, as the very
first filesystem action of the job body, before any crawling starts.
**Name**: `crawled_images/{domain}_{MMDD_HHMM}_{job_id[:8]}_combined/`.
**Overwrite**: `exist_ok=True`, but the `job_id[:8]` + minute-resolution
timestamp make a collision astronomically unlikely in practice; nothing
guards against one if it happened. **Lifecycle**: deleted by
`combined/store._safe_remove_job_dir` after 1 hour in the hot cache
(in-memory job eviction, not tied to whether the DB row still exists) —
`store.py:143-158`, gated on the directory name ending in `_combined`.

Files/subdirectories written under it, in the order they're created during
a run:

| Path (relative to the run dir) | Written by | Site | When | Overwrite |
|---|---|---|---|---|
| `combined_execution_steps.jsonl` | `ExecutionStepLogger.__init__` → `append_step_log` | `step_logger.py:76` (mkdir `step_logs/` — see next row), `:58` (append) | Eagerly at job start; appended throughout | Append-only |
| `step_logs/` (subdir) | `ExecutionStepLogger.__init__` | `step_logger.py:76` | Eagerly at job start | n/a |
| `step_logs/combined_execution_steps_summary.json` | `ExecutionStepLogger.finalize` | `step_logger.py:124` | Once, at job end (success or failure) | Overwritten (`"w"`) |
| `crawler_timings.log` | `CrawlerTimingLogger.__init__`/`.record` | `crawler_timing.py:83` (mkdir parent — the run dir itself, already exists), `:86` (header, once), `:129` (append per crawler) | Header on first crawler to finish; rows appended per crawler call | Header written once; rows appended |
| `universal_snapshot.har` | `UniversalPageLoader.load` (Playwright's own `record_har_path`) | `universal_page.py:673` (context kwarg — Playwright writes it, not this codebase directly) | Only if `record_har=True` — **not currently passed as `True` anywhere in the live call chain** (`_load_universal_snapshot` calls `load(..., record_har=False)`), so this file is never actually produced in the traced execution path, only if some other caller opts in | n/a |
| `universal_snapshot_raw.json` | `UniversalPageLoader.save_snapshot` | `universal_page.py:1360-1365` | Once, right after the BFS crawl completes, only when `needs_crawl` was true | Overwritten |
| `universal_snapshot_normalized.json` | `SnapshotNormalizer.save` | `snapshot_normalizer.py:117-131` | Once, right after normalization | Overwritten |
| `universal_snapshot_warnings.json` | `stages._load_universal_snapshot` | `stages.py:618-623` | Only if extraction produced warnings | Overwritten |
| `_raw/` (subdir) + one `*.json` per crawled page | `optimized.engine.Crawler._write_page_json` | `engine.py:1956-1960` (atomic `.json.tmp` → rename) | One file per page, as each page finishes crawling | Each page's file overwritten atomically on retry |
| `_raw/_state/crawl-log.jsonl` | `optimized.engine.CrawlState` | `engine.py:687-720` | Appended per enqueue/done event, for crash-resumability | Append-only |
| `_raw/screenshots/<page_slug>/*.png` | `optimized.engine.Crawler._capture_assets` / `_capture_carousel_slides` | `engine.py:2101,2328,2400,2434` (mkdir), various `handle.screenshot(...)` calls nearby | Per captured image element, during the image-audit crawl | New file per element; carousel duplicates are deleted (`engine.py:2170`) |
| `_raw/assets/<page_slug>/*.<ext>` | `optimized.engine.Crawler._download_asset` | `engine.py:2065-2066` (mkdir + write) | Per downloadable image asset | New file per asset |
| `<classification>/<sub_type>/img_<hash>[_<suffix>].<ext>` (e.g. `informative/img_ab12cd34ef56.png`) | `optimized.adapter.build_image_data` (copies from `_raw/`) | `adapter.py:213` (mkdir), `:224` (`shutil.copy2`) | Once per captured image, moving it from the private `_raw/` scratch space into the shared, servable output tree | Same-content images share a name (deduped); different content gets a disambiguating suffix (§ `04-MODULES-crawler.md` `_unique_basename`) |
| `<classification>/<sub_type>/ctx_<hash>.png` | `optimized.adapter.build_image_data` | `adapter.py:248-249` | Only for icon/logo elements with a captured 1.4.11 context screenshot | Overwritten if re-run |
| `text_detected/` + 4 category subfolders (`button_text/`, `informational_text/`, `logo_text/`, `with_text/`) + `text_detected/contrast/` | `text_detector.OCRPreprocessing.__init__` | `text_detector.py:134,136` | Eagerly, when the OCR stage's `OCRPreprocessing` is constructed | n/a |
| `text_detected/<category>/<filename>` (image copy) | `text_detector.OCRPreprocessing.detect_text_in_image` | `text_detector.py:495` (`shutil.copy2`, not in the mkdir grep since the dir already exists) | Per image found to contain OCR text | New copy per image |
| `text_detected/text_detection_report.json` | `text_detector.TextClassification.save_reports` | `text_detector.py:640` | Once, at the end of the OCR stage | Overwritten |
| `text_detected/contrast/contrast_report.csv` | `text_detector.TextClassification._generate_contrast_csv` | `text_detector.py:729` | Once, end of OCR stage | Overwritten |
| `text_detected/contrast/contrast_report.json` | `text_detector.TextClassification._generate_contrast_json` | `text_detector.py:829` | Once, end of OCR stage | Overwritten |
| `text_detected/contrast/contrast_report.md` | `text_detector.TextClassification._generate_contrast_markdown` | `text_detector.py:677` | Once, end of OCR stage | Overwritten |
| `audit_report.csv` | `AltTextAccessibilityAuditor.generate_audit_report` | `alttext.py:1453` | Once, end of the image-audit auditor pass | Overwritten |
| `metadata/` + `images_data.json`, `images_report.json` | `OptimizedImageCrawler.save_results` | `optimized_crawler.py:137-138,179` | Once, after `crawl_page()` returns (§ note below — **only reached via the narrower `/crawl` and `/pipeline` endpoints, not the combined-audit path**, which never calls `save_results()`) | Overwritten |
| `images_with_alt_text.csv` | `OptimizedImageCrawler._export_csv` | `optimized_crawler.py:190` | Same caveat as above | Overwritten |
| `audit_media_report.csv` | `MediaAuditor._write_csv` | `media_auditor.py:923` | Once, end of the media-audit stage (only if `run_media_audit`/`run_captions_audit` and there's ≥1 record) | Overwritten |
| `output/transcripts/<timestamp>_<md5(url)[:10]>.txt` | `quality_engine._save_transcript_locally` | `quality_engine.py:124` (mkdir), `:132` (write) | Per Deepgram transcription performed (1.2.1 Gate 5 / 1.2.2 Gate 6) | New file per transcription |
| `output/media/{audio\|video}/<timestamp>_<md5(url)[:10]>.<ext>` | `quality_engine._download_media` | `quality_engine.py:715` (mkdir), write via streamed chunks nearby | Per media file downloaded for quality checking — **never deleted** (explicit design choice, `runner.py`'s comment and `quality_engine.py`'s own "we NO LONGER unlink" comments) | New file per download |
| `combined_report.json` | `runner._run_job_body` | `runner.py:507-511` | Once, near the very end of the job, after the report is fully built and assets registered | Overwritten |

**Lazy vs. eager**: almost everything above is **eager within its own
stage** — the owning class creates its directories in `__init__`, before
any actual work happens, rather than lazily on first write. The one
partially-lazy case is `crawler_timing.CrawlerTimingLogger`, which only
writes its header the first time any crawler actually finishes (so a run
where every crawler stage failed before completing never produces
`crawler_timings.log` at all, even though the directory it would live in
already exists).

## 7.3 Directories independent of any single run

| Path | Created by | Site | Purpose |
|---|---|---|---|
| `<ka11y-python>/logs/` | `config.logger.setup_logger` | `logger.py:92` (`os.makedirs`) | The rotating app-log directory — created on **every** `setup_logger()` call, i.e. effectively at import time of nearly every module in the codebase; the very first filesystem write of the whole process. |
| `<ka11y-python>/logs/{name}_{date}.log` | `config.logger.setup_logger` | `logger.py:118-128` (`RotatingFileHandler`, 5MB × 5 backups) | The plain-text mirror of console log output, one file per logger `name` per day. |
| `<ka11y-python>/logs/ka11y.db` (or `$KA11Y_DB_PATH`) | `store.db.Database.start` | `db.py:90` (mkdir parent) | The SQLite database file itself — created by `sqlite3.connect` on first open, its parent dir explicitly via `mkdir`. |
| `<ka11y-python>/logs/assets/` (or `$KA11Y_ASSET_DIR`) | `store.assets.put_asset` | `assets.py:90` (mkdir per-asset parent, i.e. `.../assets/{run_id}/{kind}/{sha[:2]}/`) | The content-addressed asset byte store. |
| `<ka11y-python>/logs/timings/` | `utils.stage_timing._write_row` / `emit_summary` | `stage_timing.py:137,311` | Fine-grained per-step JSONL timing files (`<run_id>.jsonl`) and their human-readable summaries (`<run_id>.summary.log`). |
| `<ka11y-python>/logs/run_timings.log` | `utils.run_timing.log_run_timing` | `run_timing.py:238-239` (mkdir parent + append) | One human-readable block appended per finished run (success or failure) — durable, survives job/DB TTL. |

## 7.4 Trace: user request → path decided → directory created → results written → path returned

For the primary combined-audit path (§ `10-EXECUTION-FLOW.md`):

1. `POST /combined-audit` — no path decided yet.
2. `runner._run_job_body` (Step 3.3 of the execution-flow doc) computes
   `output_dir` from `config["input"]["output_dir"]` + domain + timestamp +
   `job_id[:8]` — **this is the only point the path is decided** for the
   combined-audit flow; **created immediately** via `.mkdir(...)`.
3. Every stage below writes into that same `output_dir` (or a subdirectory
   of it) — see the table in §7.2. The image-audit stage additionally
   creates and writes into `_raw/` (private scratch, later partially copied
   out) and the OCR stage's own `text_detected/` tree.
4. `combined_report.json` is written last, once the full report is
   assembled.
5. The path is exposed to the client three ways: `_jobs[job_id]["output_dir"]`
   (internal, not directly returned by any route), `run["output_dir"]` in
   the durable `runs` table (surfaced as `report_path` in
   `JobStatusResponse` via `_job_from_db`, `routes.py:424`), and indirectly
   through every `image_url`/`element.image_src` in the report, which after
   `register_report_assets` point at `/api/v1/assets/{id}` rather than the
   raw path — **the raw filesystem path itself is never returned to an
   external client**, only opaque asset IDs and (for the legacy fallback
   route) a `?path=` query value that's validated against the job's own
   recorded image list before ever touching the filesystem again
   (`combined/routes.py`'s `get_job_image`, § `07-MODULES-api.md` (D)).

## 7.5 Resulting folder tree from a typical multi-page combined run

```
crawled_images/                                  ← config["input"]["output_dir"]
└── example_com_0301_1400_a1b2c3d4_combined/      ← runner.py: per-job output_dir
    ├── combined_execution_steps.jsonl            ← ExecutionStepLogger
    ├── step_logs/
    │   └── combined_execution_steps_summary.json
    ├── crawler_timings.log                       ← Markdown-table crawler durations
    ├── universal_snapshot_raw.json                ← UniversalPageLoader.save_snapshot
    ├── universal_snapshot_normalized.json         ← SnapshotNormalizer.save
    ├── universal_snapshot_warnings.json           ← only if extraction had warnings
    ├── _raw/                                      ← optimized.engine's private scratch dir
    │   ├── _state/crawl-log.jsonl                 ← crash-resumable crawl state
    │   ├── <page-slug-1>.json                     ← one per crawled page, raw facts
    │   ├── <page-slug-2>.json
    │   ├── screenshots/<page-slug>/*.png           ← per-element captures
    │   └── assets/<page-slug>/*.<ext>              ← downloaded original image bytes
    ├── informative/                                ← copied-out, classified images
    │   └── img_<hash>.png
    ├── decorative/
    ├── functional/
    │   ├── buttons/btn_<hash>.png
    │   ├── icons/img_<hash>.png
    │   │   └── ctx_<hash>.png                      ← 1.4.11 padded context capture
    │   ├── logos/svg_<hash>.png
    │   └── images/
    ├── complex/
    │   ├── charts/
    │   └── emojis/
    ├── text_detected/                              ← OCR output
    │   ├── button_text/  informational_text/  logo_text/  with_text/  (image copies)
    │   ├── contrast/
    │   │   ├── contrast_report.csv
    │   │   ├── contrast_report.json
    │   │   └── contrast_report.md
    │   └── text_detection_report.json
    ├── audit_report.csv                            ← WCAG 1.1.1/4.1.2/1.4.5/1.4.11 per-image
    ├── audit_media_report.csv                      ← WCAG 1.2.x/1.4.2 per-media-element
    ├── output/
    │   ├── transcripts/<ts>_<hash>.txt              ← Deepgram transcripts (never deleted)
    │   └── media/{audio,video}/<ts>_<hash>.<ext>    ← downloaded media (never deleted)
    └── combined_report.json                        ← the final merged report
```

Sibling, outside this job's own directory (created by the image crawler's
*own* directory-naming logic when it's the narrower `/crawl` or `/pipeline`
endpoint driving it — not part of a combined-audit run's tree, but able to
exist as a same-parent sibling):

```
crawled_images/
└── example_com_0301_1358/                          ← OptimizedImageCrawler's own naming
    ├── metadata/
    │   ├── images_data.json
    │   └── images_report.json
    └── images_with_alt_text.csv
```

And, entirely outside `crawled_images/` (the durable, cross-run
infrastructure):

```
ka11y-python/logs/
├── KAC_2026-03-01.log                              ← rotating app log (+ .1 .. .5 backups)
├── ka11y.db                                         ← SQLite (+ ka11y.db-wal, -shm)
├── run_timings.log                                  ← appended per finished run, forever
├── timings/<run_id>.jsonl / .summary.log            ← fine-grained per-step telemetry
└── assets/<run_id>/<kind>/<sha[:2]>/<sha>.<ext>      ← content-addressed image store
```

## 7.6 Temp dirs, cleanup, atexit/error-handling deletion

- **No `tempfile`/`atexit` usage** anywhere in the audit path itself.
  `rule_evaluator.py` is the one exception: it uses
  `tempfile.TemporaryDirectory()` (context-managed, auto-deleted on exit)
  as the scratch output dir for its direct `_stage_image_audit`/
  `_stage_media_audit_universal` calls — the only place in the codebase
  that cleans up its own output directory automatically.
- **Downloaded media and saved transcripts are explicitly never deleted**
  (`quality_engine.py`'s and `runner.py`'s own "we NO LONGER unlink"
  comments) — they accumulate under `<run_dir>/output/` for the life of
  that run directory.
- **Job directory deletion** happens on two independent schedules, neither
  of which is a crash/error handler — both are steady-state background
  sweeps: `combined.store._evict_old_jobs` (in-memory hot-cache eviction,
  1-hour TTL, every 5 minutes, `store.py:143-181`) and
  `store.retention.run_retention_loop` (durable-store retention, default
  30-day TTL, hourly, deleting the SQLite rows via `repo.retention_sweep`
  then the on-disk **asset** directory via `assets.prune_run_assets` — note
  this second sweep prunes the *asset store*, not the job's own
  `..._combined` output directory itself, which only the first,
  hot-cache-tied sweep removes; a run evicted from the SQLite `runs` table
  after 30 days but whose `..._combined` directory somehow survived the
  1-hour in-memory sweep — e.g. the process was restarted and the hot
  cache lost track of it before the 1-hour timer fired, so it was never in
  `_jobs` to be swept — would leak that directory indefinitely; there is no
  independent disk-sweep-by-directory-age mechanism scanning
  `crawled_images/` directly).
- **On error**, `runner._run_job_body`'s `except` block does **not** delete
  the partially-written output directory — a failed run's artifacts (step
  logs, whatever crawl/OCR output made it to disk before the failure) are
  left in place for post-mortem debugging, subject to the same TTL sweeps
  as a successful run.
