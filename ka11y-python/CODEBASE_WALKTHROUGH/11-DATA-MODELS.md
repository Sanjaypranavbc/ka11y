# 6. Key Data Structures / Models

Every non-trivial model is a Pydantic `BaseModel` (v2). Grouped by the
stage of the pipeline they carry data through.

## Request / response (API boundary)

| Model | Module | Purpose |
|---|---|---|
| `CombinedRequest` | `api/v1/combined/models.py` | The audit request — URL, depth/page budget, `wcag_level`, `success_criteria_id`, the four live `run_*` toggles, `lang`, `email`. Self-validates SC↔flag dependencies. **The authoritative list of what audit toggles actually exist** — see `07-MODULES-api.md` (B). |
| `JobStatusResponse` | `api/v1/combined/models.py` | The poll/response shape — status, timestamps, `result` (the full report once complete), sanitized error fields (`error`, `error_id`, `error_stage` — never raw exception detail). |
| `FindingReviewRequest` | `api/v1/combined/routes.py` | A reviewer's pass/violation/needs_review decision on one finding. |
| `PipelineRequest`/`PipelineResponse` | `api/v1/models/pipeline.py` | The narrower `/pipeline/` endpoint's shape — carries five dead `run_*_audit` fields the handler never reads (§ `07-MODULES-api.md` (B)). |
| `CrawlRequest`/`CrawlResponse` | `api/v1/models/crawl.py` | The narrower `/crawl/` endpoint's shape. |
| `RuleRunRequest`/`RuleUrlOnlyRequest` | `api/v1/rules/models.py` | Per-rule-endpoint request shapes. |
| `TestRuleRequest` | `api/v1/rule_evaluator.py` | The rule-tester's request shape (`url`, `rule_id`, `force_refresh`, `language`). |

## Crawler output (image pipeline)

| Model | Module | Purpose |
|---|---|---|
| `ImageData` | `crawler/models.py` | **The image pipeline's central record** — one per crawled image element. Carries classification (`classification`/`sub_type`/`is_*` flags), capture bookkeeping (`screenshot_path`, `capture_status`), WCAG 1.1.1/4.1.2 accessible-name context (`element_type`, `alt_present`, `in_link`, `in_labeled_control`, …), and WCAG 1.4.11 page-context capture (`full_page_screenshot_path`, `page_bbox`). Produced by `crawler/optimized/adapter.py`, consumed by `AltTextAccessibilityAuditor`, `text_detector.py`, `findings.py`. |
| `ImageMetadata` | `crawler/models.py` | A richer, largely-superseded parallel record with its own `compute_violations()` self-contained rule engine — still constructed by some legacy path but not the primary `ImageData` flow (§ `04-MODULES-crawler.md`). |
| `WcagViolation` | `crawler/models.py` | A single violation record inside `ImageMetadata.wcag_violations`. |
| `MediaElementData` | `crawler/media_crawler.py` | One `<audio>`/`<video>` element's raw attributes/context, feeding `MediaAuditor`. Pure DTO — extraction happens in JS, not in this model. |
| `PageSnapshot` | `crawler/universal_page.py` | The **multi-page BFS crawl's accumulator** — `media`, `background_images`, `pipeline_pages` (the orphaned decision-pipeline's raw contexts, still captured), `warnings`, `element_refs`, `page_summaries`, `pages_crawled`, `partial`, `har_path`. |
| `NormalizedPageSnapshot` | `crawler/snapshot_normalizer.py` | `PageSnapshot` with `media` validated into typed `MediaElementData` instances. |
| `CrawlPolicy` | `crawler/policy.py` | BFS rules — depth/page budget, same-origin filtering, URL normalization/canonicalization, query-param tracker stripping. Shared by both the universal crawler and (as `_REPORT_URL_POLICY`) the report builder's page-grouping. |
| `CrawlSummary`/`CrawlReport` | `crawler/optimized/optimized_crawler.py` | Per-crawl aggregate counts and the full `images_report.json` shape. |

## The orphaned decision-pipeline's models (defined, not live — see `05-MODULES-pipeline.md`)

| Model | Module | Purpose |
|---|---|---|
| `ElementContext` | `accessibility/pipeline/models.py` | The unit every `WCAGPolicy` evaluates — composes `SemanticContext`, `VisualContext`, `InteractionContext`, `AccessibleName`. |
| `SemanticContext` / `VisualContext` / `InteractionContext` / `AccessibleName` / `BoundingBox` | same | Structured evidence about one DOM element (landmark section, ARIA state, computed styles, OCR text, focus/click state, accessible-name source+text). |
| `RuleVerdict` | same | One policy's PASS/FAIL/NEEDS_REVIEW/NOT_APPLICABLE outcome + evidence + the whole source `ElementContext`. |
| `SectionType`, `VerdictStatus`, `AccessibleNameSource` | same | The three enums the models above use. |

## Text detection / OCR

| Model | Module | Purpose |
|---|---|---|
| `TextDetectionResult` | `preprocessor/text_helper_models.py` | Per-image OCR outcome — `has_text`, `detections`, violation/needs-review counts, `category`. |
| `DetailedDetection` | same | One OCR-detected text region — text, confidence, bbox, `contrast_info`, `color_info`, `wcag_violations`, `needs_review` (the "contrast genuinely undetermined vs. determined-and-passing" distinction, § `09-MODULES-text-classifier-i18n.md`). |
| `TextDetectionReport` | same | The full-scan aggregate written to `text_detection_report.json`. |

## Image classification (orphaned — see `09-MODULES-text-classifier-i18n.md`)

| Model | Module | Purpose |
|---|---|---|
| `ImageClassification` | `classifier/classifier.py` | The output of the never-called `ClassifyAssets.classify_image` cascade — same field shape as the live classification fields on `ImageData`, but produced by a different (unused) code path. |

## i18n / metadata

| Model | Module | Purpose |
|---|---|---|
| `RuleEntry` | `i18n/loader.py` | One WCAG SC's localized metadata — id, level, severity (never localized), name, description, suggested_fix, `reason_templates`. |
| `LocaleBundle` | `i18n/loader.py` | All `RuleEntry`s plus localized severity/level/status label maps for one language. |

## Combined report (the final output shape)

Not a Pydantic model — `findings.py`/`report.py` build **plain dicts**
deliberately (the module comment in `stages.py`'s `PythonStagesResult`
explains why elsewhere: avoiding Pydantic revalidation overhead on deeply
nested, heterogeneous, high-volume data). The shape, established across
`_make_finding` and `_build_report`:

```
Finding (dict):
  source: "python" | "axe"
  rule_id, wcag_sc, criterion_name
  level: "A"|"AA"|"AAA", level_label
  severity: "critical"|"high"|"medium"|"low"|None, severity_label
  status: "pass"|"fail"|"needs_review"|"inapplicable", status_label
  reason (localized text), reason_code, reason_params  [not always retained]
  detected_by: ["python"]
  suggested_fix (None for passes), help_url (always None from Python)
  element: {
    html, element_id, tag, target, selector, element_ref_id, frame_path,
    image_src, image_reference, image_text, page_url,
    quality_report?  (media findings only)
  } | None
  finding_id (16-hex sha1, stamped by report.py)
  manual_review (bool)
  review_status / review_note / reviewed  [only if manually reviewed]

Report (dict, from _build_report):
  url, generated_at, lang, labels: {severities, levels, statuses}
  summary: {
    total_findings, violations, needs_review, passes, manual_review_required,
    score (0-100 or None), by_severity, by_level, by_wcag_sc (+pages_affected),
    by_source, by_page, page_count,
    automated?, reviews?  (present only after apply_reviews has run)
  }
  violations / needs_review / passes: [Finding, ...]
  pages: [{page_url, summary: {...}, violations, needs_review, passes}, ...]
  pages_scanned: [{page_url, status, violations, needs_review, passes, error}, ...]
  contrast_report: {summary, table, images} | None
  image_audit_report: {summary, images} | None
  warnings: [str, ...]
  warning_details: [{code, count, samples}, ...]
```

`PythonStagesResult` (`stages.py`, a typed Pydantic wrapper specifically
*because* it replaced a positional tuple that silently broke on reordering
— the one place in this data-flow layer where a Pydantic model was chosen
deliberately for its field-name safety, not despite the overhead) carries
`findings`, `contrast_report`, `image_audit_report`, `crawled_pages` between
`_run_python_stages` and `runner.py`.

## Durable store rows (SQLite, `store/migrations/*.sql`)

`runs`, `run_pages`, `run_reports` (zlib-compressed full report JSON),
`findings` (denormalized, one row per finding for fast SQL queries),
`assets` (content-addressed registry), `stage_timings`, `run_events`,
`finding_reviews` — full column-level detail in `08-MODULES-store.md`.

## Where each crosses a module boundary

- `ImageData` list: `crawler/optimized/adapter.py` → `AltTextAccessibilityAuditor`
  (dict output) → `findings.py` converters → `Finding` dicts.
- `TextDetectionResult` list: `text_detector.OCRPreprocessing.results` →
  `findings._build_contrast_report` + `OCR_RESULT_CONVERTERS` → `Finding` dicts.
- `PageSnapshot`/`NormalizedPageSnapshot`: `universal_page.UniversalPageLoader.load`
  → `snapshot_normalizer.SnapshotNormalizer.normalize` →
  `MediaAuditor.generate_audit_report` (dict input via `.model_dump()`) →
  `findings._media_to_findings` → `Finding` dicts.
- `Finding` dicts (Python) + Node's own finding dicts →
  `runner._merge_findings` → `report._build_report` → the final report dict
  → `store/repo.py` (compressed JSON + denormalized rows) and
  `<output_dir>/combined_report.json` on disk.
