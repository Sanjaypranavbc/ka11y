# 8. Extensibility / Plugin Points

No dynamic plugin discovery (no entry-point scanning, no `importlib`-based
auto-registration, no directory-glob-and-load mechanism) exists anywhere in
this codebase. Every extension point is a **manually-edited registration
list** that a developer adds a line to. This section documents each one,
plus the two documented-in-this-walkthrough exceptions where an
extension point exists in the code but its "consumer" is currently
disconnected.

## 8.1 Adding a new Python WCAG rule (the sanctioned path)

Documented verbatim in `api/v1/combined/__init__.py`'s module docstring
(`07-MODULES-api.md` (D)) — the six steps, with the module each step
touches:

1. **Crawler** (`ka11y/crawler/`) — implement `async crawl() -> List[Dict]`
   + a save-raw-JSON step, following the pattern in
   `crawler/optimized/engine.py` or extend `universal_page.py`'s
   `_COMBINED_EXTRACT_JS` to capture the new signal in-browser.
2. **Auditor** (`ka11y/accessibility/rules/<category>/`) — implement
   `generate_audit_report(items) -> List[Dict]`; each record must include
   `<rule_key>_status` (`"FAILED"|"PASSED"|"NEEDS_REVIEW"|"N/A"`),
   `<rule_key>_violation`, plus `html_snippet`/`element_id`/`tag`. Follow
   the pattern in `accessibility/rules/media/media_auditor.py` (a
   gate-chain per criterion) or `accessibility/rules/non_text/alttext.py`
   (a per-classification branch with reason-code stamping).
3. **Finding converter** (`api/v1/combined/findings.py`) — add
   `_myrule_to_findings(records, page_url) -> List[Dict]`; call
   `_make_finding()`, resolve severity via `_PYTHON_SEVERITY[wcag_sc]`
   (`auditor_field_map.py`'s `get_status`/`get_reason` for the typo-safe
   field lookups); register it in `IMAGE_AUDIT_RECORD_CONVERTERS` or
   `OCR_RESULT_CONVERTERS` (or write the record-shaped equivalent for a new
   auditor family, as `_media_to_findings` does).
4. **Metadata** (`api/v1/combined/constants.py`, ultimately backed by
   `i18n/rules.yml`) — add the new SC's `severity` and `suggested_fix`
   entries (and, ideally, `reason_templates` per status code, so
   `render_reason` can localize the finding text rather than falling back
   to the raw English string).
5. **Stage wiring** (`api/v1/combined/stages.py`) — add a `_stage_myrule()`
   coroutine following the `_stage_image_audit`/`_stage_media_audit_universal`
   pattern (own `_stage_start`/`_stage_complete` lifecycle calls, its own
   `asyncio.to_thread`/`asyncio.gather` for CPU-bound work); add it to the
   `stage_coros`/`stage_labels` lists inside `_run_python_stages`, and add
   its weight to `constants.STAGE_WEIGHTS` (keeping the total at 100).
6. **Request toggle** (`api/v1/combined/models.py`) — add `run_my_audit:
   bool = True` to `CombinedRequest`; thread it through
   `runner._run_job_body` → `stages._run_python_stages` → your new stage
   function's parameters; if the new SC should be individually testable via
   a `success_criteria_id`, add it to `_SC_STAGE_PREREQUISITES`.

**A parallel, independent registration is needed for the per-rule HTTP
endpoints** (`api/v1/rules/run_router.py`'s `RULE_FLAGS` dict) if the new
rule should be reachable via `POST /api/v1/rules/{sc}/run` — as documented
at length in `07-MODULES-api.md` (F), **adding an entry here alone is not
enough**: the flag name in `RULE_FLAGS[sc]` must also actually exist as a
field on `CombinedRequest` (step 6 above), or the route silently produces
empty results for that rule (Pydantic drops the unknown kwarg). This is
exactly the trap 13 of the 19 currently-registered `RULE_FLAGS` entries are
caught in.

## 8.2 Adding a new WCAG rule's *metadata only* (no auditor)

`i18n/rules.yml` (shared between `ka11y-python` and `ka11y-node`) is the
single source of truth for name/description/level/severity/suggested_fix
per SC, consumed by `i18n/loader.py`. An SC can be *listed* (and shown in
`GET /api/v1/rules/wcag`) without any Python auditor backing it — this is
exactly the state of the 13 "removed" SCs discussed throughout section 4:
their metadata likely still exists in the YAML (not verified file-by-file
in this walkthrough, but consistent with `run_router.py` still advertising
them), while their code doesn't.

## 8.3 Adding a new locale

Drop `i18n/locales/<lang>.yml` next to the existing ones (only `en`
implicit via `rules.yml` itself, plus whatever locale files exist — this
walkthrough didn't enumerate the `i18n/locales/` directory contents, but
the loading mechanism in `i18n/loader.py` requires no code change: any
`<lang>.yml` file is picked up automatically by `_load_bundle_cached` the
first time that language string is requested, sanitized through
`_safe_lang`). Overlay only the fields you want to translate — anything
omitted falls back through locale → base `rules.yml` → hardcoded English
default, per `_merge_label_map`/`_build_entries`' merge precedence
(`09-MODULES-text-classifier-i18n.md`).

## 8.4 Adding a new OCR language / engine

`text_detector.py`'s `_select_ocr_reader_class(lang)` is the single switch
point — currently a two-way branch (Japanese → PaddleOCR if available,
everything else → EasyOCR). Adding a third engine means: implement a class
matching the `OCRReader` interface (`__init__(source_directory,
output_directory=None, lang=...)`, `readtext(image_path) ->
list[(bbox, text, confidence)]` — see `ocrbase.py`/`paddleocrbase.py` for
the two existing implementations and the exact bbox-format compatibility
contract they maintain), then extend `_select_ocr_reader_class`'s branch.
`_ocr_lang_for_page` (`stages.py`) would also need extending if the new
engine should be selected per-page rather than per-run.

## 8.5 The two currently-disconnected extension surfaces

Both are fully-built, testable subsystems that a wiring change (not a
rewrite) could reconnect:

- **`accessibility/pipeline/` (the decision-policy engine)** — adding a
  new criterion here means: define a `WCAGPolicy` subclass in
  `decisions/policies/` (following `policy_1_1_1.py`'s pattern — `_pass`/
  `_fail`/`_needs_review`/`_not_applicable` helpers from `base_policy.py`),
  register its applicability in `router/rule_target_router.py`'s
  `get_applicable_rules`, and register an instance in
  `pipeline_stage._build_policies`. **None of this currently affects any
  live audit**, because `stages.py`'s `_run_python_stages` never calls
  `_run_pipeline_stage` at all (§ `05-MODULES-pipeline.md`,
  `07-MODULES-api.md` (D)). Re-wiring it would mean either (a) adding a
  call to `stages._run_pipeline_stage(url, job_id, run_image_audit,
  run_contrast_audit, lang, snapshot)` inside `_run_python_stages`'
  `stage_coros` list (it's already written and stage-lifecycle-wrapped,
  just unreferenced), and reconciling its findings with the overlapping
  ones `AltTextAccessibilityAuditor`/`contrast_analyser.py` already
  produce for the same five criteria (1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11)
  — `_merge_findings`' dedup logic would need the two sources' element
  identities to actually line up, which is not guaranteed given they're
  independently-computed selector/ID schemes; or (b) using it to cover
  *different* criteria than the ones `alttext.py` already handles (the
  framework is generic — `RuleTargetRouter`/`DecisionEngine` don't care
  which SC a policy targets), which avoids the overlap problem entirely and
  is the more natural way to bring back e.g. 2.5.8 (target size) using the
  `adjacent_spacing_px` data `ElementContextExtractor`'s JS already
  computes but that no policy currently reads.
- **`classifier/classifier.py`'s `ClassifyAssets`** — reconnecting this
  would mean calling `classify_image(img_element, page)` somewhere in a
  crawler's per-element loop and using its returned dict instead of (or to
  cross-check) the classification fields the in-browser `EXTRACT_JS`
  already computes in `optimized/engine.py`. Given the in-browser version
  already does the equivalent job as part of the single DOM-walk `page.evaluate()`
  call (no extra round-trip per element), reconnecting this specific module
  would mostly be useful for a **second, cross-validating classification
  pass**, not as the primary mechanism — the JS version is structurally
  cheaper (one browser round-trip for the whole page vs. one Playwright
  `evaluate()` call per element here).

## 8.6 Configuration-driven tuning (not code changes)

Most numeric/behavioral knobs are environment-variable-gated rather than
requiring a code change at all — collected here for reference (each
documented at its point of use in section 4):

`KA11Y_MAX_BROWSERS`, `KA11Y_UNIVERSAL_PARALLEL_PAGES`,
`KA11Y_MAX_CONCURRENT_JOBS`, `KA11Y_HEAVY_STAGE_CONCURRENCY`,
`KA11Y_IMAGE_CRAWL_PER_PAGE_SECONDS`, `KA11Y_IMAGE_CRAWL_TIMEOUT_CEILING`,
`KA11Y_OCR_WORKERS`, `KA11Y_CPU_WORKERS`, `KA11Y_JOB_TIMEOUT_SECONDS`,
`KA11Y_NODE_TIMEOUT_SECONDS`, `KA11Y_NODE_HTTP_BASE_TIMEOUT_SECONDS`,
`KA11Y_NODE_HTTP_PER_PAGE_TIMEOUT_SECONDS`, `NODE_BASE_URL`,
`KA11Y_DB_PATH`, `KA11Y_ASSET_DIR`, `KA11Y_RUN_RETENTION_DAYS`,
`KA11Y_RETENTION_SWEEP_SECONDS`, `KA11Y_STAGE_TIMING_DIR`,
`KA11Y_STAGE_TIMING_DISABLE`, `KA11Y_TELEMETRY_FILES`,
`KA11Y_RUN_TIMING_LOG`, `KA11Y_I18N_DIR`, `KA11Y_MAX_ATTEMPTS`,
`DEEPGRAM_API_KEY`, `SMTP_SERVER`/`SMTP_PORT`/`SENDER_EMAIL`/
`SENDER_PASSWORD`. Plus `config/universal.yml`/`config/config.yml`'s own
tunables (crawl depth defaults, OCR budgets, CJK language list, target-size/
contrast/focus thresholds — the last three currently only partially
consumed, per `05-MODULES-pipeline.md`'s `config/thresholds.py` entry).
