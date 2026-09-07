# 4. Module-by-Module Breakdown — Group 7: OCR/Text-Detector, Classifier, Preprocessor, i18n

The "content understanding" support layer: OCR engines behind a common
interface, pixel-level color/contrast preprocessing, an (as it turns out,
orphaned) AI image classifier, and the localization loader every
user-facing string in the report ultimately passes through.

> **Second orphaned-module finding**, confirmed the same way as
> `accessibility/pipeline/` in `05-MODULES-pipeline.md`: `grep -rn
> "ClassifyAssets\|from ka11y.classifier" ka11y/ --include=*.py` (excluding
> the file itself) returns **one hit** — a comment in `alttext.py`'s module
> docstring ("Classifier (already embedded in ImageData via ClassifyAssets)")
> — and no actual import or call anywhere. `classifier/classifier.py`'s
> `ClassifyAssets.classify_image` (a Playwright-element-based, keyword/
> heuristic classification cascade) is never invoked. The classification
> fields that actually populate `ImageData.classification`/`sub_type`/
> `is_logo`/`is_icon`/`is_button` (etc.) in the live pipeline come from the
> **in-browser JS extraction** in `optimized/engine.py`'s `EXTRACT_JS`
> (`04-MODULES-crawler.md`) instead — an independently-implemented,
> in-page equivalent of the same decision cascade documented below, not a
> call into this module. Documented in full below since it's real, working,
> testable code — just not reachable from any live endpoint today.

---

## `ka11y/text_detector/__init__.py` (4 lines)

`from ka11y.text_detector.ocrbase import OCRReader; __all__ = ["OCRReader"]`
— re-exports the EasyOCR-backed reader class as the package's default
`OCRReader` (the PaddleOCR variant is imported directly by name,
`paddleocrbase.OCRReader`, where needed — see `text_detector.py` below).

---

## `ka11y/text_detector/ocrbase.py` (82 lines)

**Purpose**: the default (Latin-script) OCR engine wrapper — EasyOCR.

**Imports**: `threading`, `typing.Optional` (stdlib); `easyocr`, `torch`
(third-party).

**Module-level side effect**: `torch.set_num_threads(1)` (line 19) — set at
**import time**. The comment (lines 7-18) explains why: EasyOCR's CPU
backend uses PyTorch's intra-op thread pool *within* a single `readtext()`
call, defaulting to the CPU count; since `text_detector.py` separately
parallelizes *across* images via its own worker thread pool, leaving
intra-op threading at its default would oversubscribe the box (N workers ×
M intra-op threads each). Capping to 1 hands all the parallelism to the
worker pool, which is what actually gives near-linear speedup for "many
small independent images." Documented as safe to set at import time because
`easyocr.Reader(...)` construction doesn't reset this setting later.

**Thread-local reader cache**: `_thread_local = threading.local()` (line
31) — EasyOCR models (~200MB) are loaded **once per thread**, not once per
process, because `Reader.readtext()` has no documented thread-safety
guarantee for concurrent calls against one shared instance; each of
`text_detector.py`'s worker threads gets and keeps its own `Reader`.

- `get_ocr_reader(lang="en") -> easyocr.Reader` (lines 34-50): maps the
  requested language to a list of EasyOCR language codes — always includes
  `"en"`, adds `"ja"` if `lang` is `"ja"`/`"jp"` (so mixed English+Japanese
  text on a Japanese page is handled by one reader); caches by the joined
  language-list string per thread; constructs `easyocr.Reader(langs,
  gpu=False, verbose=False)` on first use for that key.

**Class `OCRReader`**:
- `__init__(self, source_directory, output_directory=None, lang="en")`
  (lines 55-63): stores config (the `source_directory`/`output_directory`
  are accepted for interface parity with the PaddleOCR variant but not
  actually used inside this class beyond storage).
- `reader` property (lines 65-68): lazily resolves `get_ocr_reader(self.lang)`.
- `readtext(self, image_path)` (lines 73-81): calls
  `self.reader.readtext(image_path, detail=1, paragraph=False,
  text_threshold=0.75, low_text=0.5, link_threshold=0.4)` — the specific
  threshold tuning (vs. EasyOCR's defaults) that governs detection
  sensitivity; a commented-out simpler `readtext` (lines 70-71) shows the
  pre-tuning version, left in place as a reference.

**Side effects**: loads a ~200MB model per unique thread+language
combination on first use (CPU, no GPU).

**Used elsewhere**: `text_detector.py`'s `_select_ocr_reader_class` (default
choice for non-Japanese pages).

---

## `ka11y/text_detector/paddleocrbase.py` (126 lines)

**Purpose**: the CJK-optimized OCR engine wrapper — PaddleOCR, used for
Japanese pages (per the commit history's stated goal: "route Japanese OCR
through PaddleOCR, English stays on EasyOCR").

**Imports**: `os`, `threading`, `typing.Optional` (stdlib);
`paddleocr.PaddleOCR` — wrapped in `try/except ImportError`, setting
`PaddleOCR = None` if the optional dependency isn't installed, so the
module still imports cleanly and fails only when actually asked to OCR
(`get_ocr_reader` returns `None`, `readtext` raises `RuntimeError`).

**Module-level side effect**: `os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK",
"True")` (line 7) — suppresses PaddleOCR's startup connectivity check to
its model-hosting servers (models still download on first actual use; this
only skips an upfront network ping).

**Thread-local reader cache**: same pattern as `ocrbase.py`.

- `get_ocr_reader(lang="en") -> Optional[PaddleOCR]` (lines 27-59): returns
  `None` immediately if the `paddleocr` package isn't installed; maps
  `"ja"`/`"jp"` → PaddleOCR's own `"japan"` language code; caches per
  thread+language. **Constructs with `use_doc_orientation_classify=False,
  use_doc_unwarping=False`** (lines 54-58) — a documented correctness fix:
  PaddleOCR's default pipeline runs a document-orientation classifier and a
  UVDoc geometric-unwarping model ahead of detection, built for
  photographed/scanned paper pages; this project's images are flat web
  screenshots, so that preprocessing has no upside and a real downside —
  unwarping remaps coordinates, and the rest of the pipeline
  (`text_detector.detect_text_in_image`) assumes the returned bbox lines up
  directly with the *original* image file it separately loads for contrast/
  color analysis.

**Class `OCRReader`** — documented in its own docstring as a **drop-in
replacement** for the EasyOCR-backed one: same constructor signature, same
`readtext(image_path)` return shape (`list[(bbox, text, confidence)]`),
compatible bbox format (four `[x,y]`/`(x,y)` corner points either way) so
`text_detector.py`'s `clean_bbox = [(int(p[0]), int(p[1])) for p in bbox]`
line works unmodified against either engine's output.
- `reader` property (lines 92-95): lazily resolves via `get_ocr_reader`.
- `readtext(self, image_path)` (lines 97-125): raises `RuntimeError` if
  PaddleOCR isn't installed; calls `reader.predict(image_path)` (PaddleOCR
  v3's inference API, distinct from EasyOCR's `readtext`), then reshapes its
  per-image dict response (`dt_polys`, `rec_texts`, `rec_scores`) into the
  same `(bbox, text, confidence)` tuple list EasyOCR produces, converting
  NumPy int64 box corners to plain Python `int` tuples.

**Side effects**: loads PaddleOCR models per unique thread+language on
first use.

**Used elsewhere**: `text_detector.py`'s `_select_ocr_reader_class`, only
for Japanese-language OCR groups.

---

## `ka11y/text_detector/text_detector.py` (864 lines)

**Purpose**: the OCR orchestration driver — scans a directory (or an
explicit file allowlist) of crawled images, runs the appropriate OCR engine
per image, computes contrast for every detected text region, and writes the
JSON/CSV/Markdown reports.

**Imports**: `os`, `json`, `shutil`, `sys`, `gc`, `csv`, `threading`,
`concurrent.futures.ThreadPoolExecutor`, `pathlib.Path`, `typing.*`,
`datetime.datetime` (stdlib); `ka11y.preprocessor.extract_color`,
`ka11y.accessibility.rules.non_text.contrast_analyser`,
`ka11y.preprocessor.text_helper_models.*`,
`ka11y.utils.text_detector_helper.*`, `ka11y.config.logger.setup_logger`,
`ka11y.utils.config_loader.load_config` (internal).

**Module-level state**: `config = load_config()` (line 30, evaluated once
at import time).

**OCR worker pool** (lines 35-62): `_OCR_MAX_WORKERS` (`$KA11Y_OCR_WORKERS`,
default 4); `_get_ocr_executor() -> ThreadPoolExecutor` — a lazily-created,
**process-wide and persistent** (not per-call) thread pool, double-checked
locking. The module comment explains the design: OCR inference is
CPU-bound but releases the GIL during the actual NumPy/torch/OpenCV
compute, so concurrent images on a multi-core box cut wall time
substantially; each worker thread lazily loads its own OCR reader on first
use and keeps it for the process lifetime (a fresh-pool-per-call design
would re-pay the model-load cost every audit).

**Per-language engine selection** (lines 64-95): imports `EasyOCRReader`
unconditionally; attempts to import `PaddleOCRReader`, setting
`_PADDLEOCR_AVAILABLE = False` (and logging an info line) if the import
fails or `PaddleOCR is None`. `_select_ocr_reader_class(lang)`:
`PaddleOCRReader` for `lang in {"ja", "jp"}` **if available**, else falls
back to `EasyOCRReader` with a warning; every other language always uses
`EasyOCRReader`.

**Class `OCRPreprocessing`** — the scanner:
- `__init__(self, source_directory, output_directory=None, lang="en",
  include_paths=None)` (lines 99-148):
  1. `self.include_paths` — resolved absolute paths, if an explicit
     allowlist was passed (the OCR-budget-selected subset from
     `stages.py`'s `_stage_image_audit`).
  2. Reads `config["ocr"]` for the base/contrast folder names and category
     folder names (`config/config.yml` or `universal.yml`, per
     `03-MODULES-config-utils.md`).
  3. **Side effect**: creates every category subdirectory and the contrast
     directory under `<output_dir>/text_detected/` via `Path.mkdir`.
  4. Instantiates the language-appropriate `reader_cls(source_directory,
     lang=lang)` — this is where the actual OCR model load happens (lazily,
     on first `readtext` call via the reader's own lazy property, not here).
  5. `self.results: List[TextDetectionResult] = []`;
     `self.skipped_images: List[str] = []`.
- `_determine_category(self, original_path) -> str` (lines 150-159):
  path-substring heuristic (`"button"` → `button_text`, `"logo"` →
  `logo_text`, `"informative"`/`"informational"` → `informational_text`,
  else `with_text`) — determines which category subfolder a
  text-containing image gets copied into.
- `is_valid_text(self, bbox, text, conf) -> bool` (lines 260-275): filters
  OCR noise — rejects confidence < 0.6, text ≤1 char after stripping, text
  with no alphanumeric character at all, or a bounding box smaller than 500
  px² (`width * height`, computed from the axis-aligned TL/TR/BL corners).
- `detect_text_in_image(self, image_path) -> TextDetectionResult` (lines
  277-511) — the per-image worker function (run concurrently across the
  thread pool):
  1. Resolves the image to an absolute path (so the API can serve it
     regardless of CWD); returns an empty `TextDetectionResult` immediately
     (and records it in `skipped_images`) if the file doesn't exist.
  2. Runs `self.reader.readtext(image_path)`.
  3. If any detections came back: loads the image via
     `load_image_with_alpha` (composites transparency onto white — see
     `03-MODULES-config-utils.md`'s `text_detector_helper.py`); returns
     early if the load failed.
  4. For each `(bbox, text, conf)`: skips if `not is_valid_text(...)`;
     clamps the bbox corners into image bounds (documented `NEW` fix);
     computes `bbox_height_rotated` (handles a rotated OCR box correctly,
     not just axis-aligned) and `font_size_px = max(bbox_height /
     device_pixel_ratio, 8)` (DPR-aware, floored at 8px — documented `F6`
     fix); estimates boldness via `estimate_boldness` (documented `F5`
     fix).
  5. Calls `contrast_analyser.analyze_text_region(img, clean_bbox,
     font_size_px=font_size_px, is_bold=is_bold)` — **always** scored
     against the text-size AA/AAA thresholds (never the 3:1
     `is_ui_component` shortcut), per the inline comment (lines 330-342)
     clarifying that this OCR detection is baked-in-image *text*, subject
     to 1.4.3/1.4.6, distinct from a UI component's own boundary contrast
     (1.4.11), which is computed separately (real page-context version in
     `alttext.py`'s `_check_1_4_11` → `contrast_analyser.analyze_ui_component`,
     or, as a fallback, by comparing this same detection's own raw ratio
     against 3:1 directly — never by relaxing this text detection's own
     compliance dict).
  6. If contrast analysis succeeded (has `region`/`mask` keys —
     `analyze_ui_component` results lack those and are explicitly skipped
     here to avoid a `KeyError`), calls
     `extract_color.extract_colors_from_mask(region, mask, k_bg=3)` to get
     the actual foreground/background color clusters; builds
     `contrast_checks` (one compliance dict per background cluster) and a
     single authoritative `dominant_contrast` (the highest-percent
     background cluster) used for the violation verdict and UI display.
  7. **Fallback path** (lines 437-455): if color extraction didn't produce
     `color_info` but the base `contrast_info` did succeed (not errored,
     not `needs_review`), falls back to a simpler compliance check using
     `contrast_info`'s own `contrast_ratio`/`background_color` directly.
  8. **`contrast_undetermined` tracking** (lines 459-476) — a documented
     fix: previously, a detection whose contrast analysis genuinely failed
     (segmentation error) looked identical in the output to one that was
     checked and found compliant (`wcag_violations == []` either way),
     silently deflating violation counts specifically for the
     low-contrast images most likely to make segmentation fail (foreground/
     background luminance nearly identical is exactly the hard case for
     Otsu thresholding). Now stamped as `DetailedDetection.needs_review=True`
     and counted in `result.contrast_needs_review_count` so it's
     distinguishable in every downstream report.
  9. **Side effect**: `shutil.copy2(image_path, dest_path)` — copies the
     image into its category subfolder.
  10. On any exception during processing: logs, adds to `skipped_images`,
      prints a traceback (not re-raised — the result object, however
      incomplete, is still returned).
- `scan_directory(self)` (lines 513-566) — the entry point
  `stages.py`/`crawl.py`/`pipeline.py` all call:
  1. If `self.include_paths` was given (the budget-selected allowlist),
     filters it to existing files with a recognized image extension
     (`.png/.jpg/.jpeg/.gif/.webp`).
  2. Otherwise, walks `source_directory` recursively, **explicitly skipping
     any path containing `"text_detected"` or `"contrast"`** (its own
     output directories, to avoid re-scanning already-processed output if
     it happens to live inside the source tree).
  3. **Side effect**: dispatches every image through
     `executor.map(self.detect_text_in_image, image_files)` on the shared
     OCR thread pool — `executor.map` preserves input order in its result
     iteration even though the underlying work completes out of order, so
     this is a drop-in replacement for what was previously a sequential
     loop; appends each `TextDetectionResult` to `self.results`, printing a
     one-line summary per image.
  4. **Side effect**: one `gc.collect()` call for the whole batch (not per
     image) — documented as a deliberate change from a prior per-image
     `gc.collect()`, which cost real time on every single iteration; one
     end-of-batch pass gives most of the same memory-pressure relief far
     more cheaply.
  5. Logs a warning listing every skipped image, if any.

**Class `TextClassification`** — the report writer:
- `__init__(self, source_directory, output_directory=None)` (lines
  571-587): computes `text_detected_dir`/`contrast_dir` paths and calls
  `_create_directories()`.
- `_create_directories(self)` (lines 588-605): **side effect** — creates
  the four fixed category subfolders (`button_text`, `informational_text`,
  `logo_text`, `with_text`) plus the contrast folder, hardcoded here
  (unlike `OCRPreprocessing.__init__`, which reads the category names from
  config — a minor duplication between the two classes).
- `save_reports(self)` (lines 607-672) — **side effects**, writes four
  files:
  1. `text_detection_report.json` — the full `TextDetectionReport`
     (`model_dump()`, `json.dump` with the `_json_serializer` default for
     NumPy types).
  2. `contrast/contrast_report.csv` (via `_generate_contrast_csv`).
  3. `contrast/contrast_report.json` (via `_generate_contrast_json`).
  4. `contrast/contrast_report.md` (via `_generate_contrast_markdown`).
  Also prints a formatted console summary (total images, with-text count,
  violation/needs-review counts, output paths).
- `_generate_contrast_markdown(self, output_path, violation_count)` (lines
  674-724): a human-readable Markdown report — per image with color info, a
  table of background clusters vs. AA/AAA pass/fail (rendered as ✅/❌
  emoji); note the `aa_lg`/`aaa_lg` columns are literally duplicates of
  `aa`/`aaa` (comment: "no separate large key anymore" — a vestige of an
  earlier schema that distinguished large-text thresholds as separate
  columns).
- `_generate_contrast_csv(self, output_path)` (lines 726-789): one row per
  detection-with-color-info (`Image, Image Path, Text, FG, BG, Ratio,
  AA Normal, AA Large, AAA Normal, AAA Large` — again `AA Normal`/`AA Large`
  are the same value written twice), **plus** one row per
  `needs_review`-flagged detection with every numeric/compliance column
  literally set to the string `"NEEDS_REVIEW"` — a documented fix so an
  undetermined-contrast detection is visible in the CSV rather than
  silently omitted (which previously made the report look identical to "no
  contrast problems here").
- `_generate_contrast_json(self, output_path)` (lines 791-830): a flat list
  of contrast records, similarly including explicit `needs_review: true`
  entries with `None` color fields for undetermined detections.

**`main()`** (lines 833-863): a standalone CLI entry — defaults to the most
recently modified subdirectory of `crawled_images/` if no path is given,
runs `OCRPreprocessing` + `TextClassification` end to end. **Note**: the
`if __name__ == "__main__": main()` guard at the bottom (lines 863-864) is
**commented out**, so running this file directly does nothing by default —
`main()` would need to be invoked explicitly (e.g. from a Python REPL or
another script) — this is effectively dead entry-point code as currently
written, distinct from the `main()` function itself being unused (it isn't
imported/called anywhere else either, per a targeted grep).

**Side effects**: OCR model loads (per thread); reads image files from
disk; copies images into category subfolders; writes four report files;
extensive `print`/`logger` output; spawns and reuses a process-wide thread
pool.

**Used elsewhere**: `api/v1/combined/stages.py`'s `_stage_image_audit`,
`api/v1/crawl.py`, `api/v1/pipeline.py` — all three construct
`OCRPreprocessing` + `TextClassification` directly.

---

## `ka11y/classifier/classifier.py` (738 lines) — orphaned, see the note at the top of this file

**Purpose (as designed)**: classify each crawled `<img>`/`<svg>`/`<canvas>`
element into the same `classification`/`sub_type` taxonomy the live JS
extractor now produces independently (informative / decorative / functional
/ complex, with sub-types logos/icons/buttons/images/charts), using
Playwright element handles + heuristic keyword/structural scoring — no
actual ML/CLIP model despite the group name "classifier" suggesting one
(there is no `torch`/`transformers` import in this file at all).

**Imports**: `os`, `hashlib`, `aiohttp` (stdlib/third-party);
`pydantic.BaseModel`, `rich.console.Console` (third-party);
`ka11y.config.logger.setup_logger`, `ka11y.crawler.models.ImageData`
(internal).

**Class `ImageClassification(BaseModel)`** (lines 16-26): the output shape —
`classification` (default `"informative"`), `sub_type`, `is_text_image`,
`is_functional`, `is_decorative`, `is_complex`, `is_logo`, `is_icon`,
`is_button`, `file_format` — the same field set `ImageData` (crawler/models.py)
carries, confirming this was designed to populate exactly those fields.

**Keyword constant tables** (lines 32-170): `_LOGO_KEYWORDS`, `_ICON_KEYWORDS`
(with an inline note that a bare `"ico"` substring was deliberately removed
— it false-matched "silicon"/"unicorn"/"reciprocal"), `_FONT_ICON_PREFIXES`
(FontAwesome/Material/Bootstrap-Icons/Feather/Lucide class prefixes),
`_CHART_KEYWORDS`, `_CHART_LIBS` (Chart.js, D3, Highcharts, Plotly, ECharts,
etc.), `_CHART_PARENT_CLASSES` (with a note that generic terms like
"figure"/"caption" are deliberately excluded to avoid false-positiving on
ordinary news-article photos in `<figure><figcaption>`).

**Class `ClassifyAssets`**:
- `__init__(self, output_dir)` (lines 175-177): stores `output_dir`, an
  empty `images_data: list[ImageData]`.
- `get_image_hash(self, src) -> str` (lines 181-182): first 12 hex chars of
  `md5(src)`.
- `_rich_result(self, label, cls, sub, color)` (lines 184-189): prints a
  one-line colorized classification result via `rich`.
- `classify_image(self, img_element, page=None) -> dict` (lines 193-414) —
  the **main cascade**, documented step-by-step in its own docstring
  (STEP 0 through STEP 4, reproduced faithfully here):
  1. Gathers `alt`/`src`/`role`/`aria-hidden` attributes via Playwright
     `get_attribute`.
  2. Builds a `ctx` dict via `img_element.evaluate(...)` — `inButton`,
     `inLink`, `inRealLink` (a link with a non-dead `href` — not empty,
     `#`, or `javascript:`), `linkHref`, `hasClick` (an `onclick` handler
     or `cursor: pointer` computed style) — falls back to all-`False` on
     any evaluation error.
  3. **STEP 0**: `aria-hidden="true"` or `role in (presentation, none)` →
     `decorative/presentational`, returns immediately.
  4. **STEP 1a**: in a button context or `_is_button` → `functional/buttons`.
  5. **STEP 1b**: in a real link **and** `_is_logo` → `functional/logos`
     (also sets `is_text_image=True` — a logo counts as "image of text" for
     the images-of-text criterion).
  6. **STEP 1c**: `_is_chart` → `complex/charts`.
  7. **STEP 1d**: in a link/clickable **and** `_is_icon` → `functional/icons`.
  8. **STEP 1e**: in a real link or clickable (none of the above matched) →
     `functional/images`.
  9. **STEP 2**: standalone (not in a link) `_is_logo` → `informative/logos`
     if it has real alt text, else `decorative/decorative` (a logo image
     with no alt is treated as decorative rather than a violation at this
     layer — the WCAG-violation judgment happens downstream in the
     auditor, not here).
  10. **STEP 3**: standalone `_is_icon` → same alt-present/absent split as
      step 2.
  11. **STEP 4** — the core WCAG 1.1.1 distinction: `alt is None` (attribute
      completely missing) → `decorative/missing_alt` (explicitly flagged as
      the WCAG-violation case); `alt == ""` (explicit empty) →
      `decorative/decorative`; otherwise → `informative`, sub-typed via
      `_informative_sub_type`.
- `_informative_sub_type(self, alt) -> str` (lines 420-426): word-count
  based — ≤3 words → `succinct_information`, ≤12 → `general_informative`,
  else `extended_description`.
- `_is_button(self, element) -> bool` (lines 428-451): JS evaluation
  checking tag `button`, `input[type=button|submit|reset]`,
  `role="button"`, an `onclick` handler, or (for `<img>`) a `button`/
  `[role=button]` ancestor, or a `btn` class token within 4 ancestor levels.
- `_is_logo(self, element, src, alt_text) -> bool` (lines 453-479): keyword
  match against `src`/`alt`, then `class`/`id`/`title`, then a JS check for
  "homepage link inside header/nav with a brand-suggesting aria-label."
- `_is_icon(self, element, src) -> bool` (lines 481-520): font-icon class
  prefix match for `<i>`/`<span>`; for `<svg>`, small size (≤96×96) or
  keyword class; for `<img>`, keyword match or small-and-roughly-square
  size heuristic (aspect ratio 0.33-3.0).
- `_is_chart(self, element, src, alt_text, page=None) -> bool` (lines
  522-678) — a **weighted scoring system**, threshold 3, documented in its
  own docstring with each signal's point value: chart JS library detected
  on the page (+2), chart keyword in alt (+3) / src (+2) / class (+2) /
  title (+1), ancestor `<figure>` (+1, once), chart-keyword ancestor class
  (+2), chart-keyword caption/figcaption text (+3), SVG with axis/legend
  markup (+4), SVG with many shapes+text labels (+3) or a complex group
  structure (+1), a large `<canvas>` (+3), an extreme aspect ratio on a
  large element (+1). Sums every applicable signal and returns
  `score >= 3`.
- `is_logo`/`is_icon`/`is_chart`/`is_button_image` (lines 681-691):
  **public aliases** delegating to the underscore-prefixed methods —
  "backward compat" per the comment, suggesting an earlier public API
  surface this file used to expose directly.
- `get_visual_container(self, img_element, page)` (lines 694-718): the
  same "text-overlaid-on-image" ancestor-walk JS as
  `optimized/engine.py`'s `OVERLAY_CONTAINER_JS` — a third, independent
  implementation of the identical overlay-detection heuristic (the others
  being `optimized/engine.py`'s module-level JS constant and, functionally,
  whatever `_capture_assets`'s overlay logic does — all three encode the
  same "walk up to 3 ancestors looking for an absolutely-positioned sibling
  with short overlapping text" algorithm independently).
- `_download_file(self, session, url, path) -> bool` (lines 721-736,
  truncated in this read but structurally complete): downloads a URL via
  `aiohttp` to `path`, creating parent directories, 30s timeout; returns
  `False` (logged) on a non-200 status or any exception.

**Side effects (if it were ever called)**: Playwright element
attribute/JS evaluation (read-only DOM inspection); outbound HTTP via
`aiohttp` (`_download_file`); console output via `rich`.

**Used elsewhere**: nothing, per the confirmation at the top of this file.

---

## `ka11y/preprocessor/extract_color.py` (214 lines)

**Purpose**: pixel-level color clustering and luminance math — the
foundation `text_detector.py` calls into for foreground/background color
extraction (distinct from, but complementary to, `accessibility/rules/
non_text/contrast_analyser.py`'s Otsu-segmentation-based approach; this
module works from an already-known text-region mask rather than deriving
one itself).

**Imports**: `cv2`, `numpy as np`, `easyocr` (only used in the
`__main__` demo block), `collections.Counter`. No internal imports.

**Functions**:
- `rgb_to_hex(rgb) -> str` (lines 11-12): standard `#rrggbb` formatting.
- `relative_luminance(rgb) -> float` (lines 15-18): the WCAG 2.1 formula,
  vectorized via NumPy over the 3-channel input (functionally identical to
  `pipeline/runners/contrast_engine.py`'s scalar version and
  `non_text/contrast_analyser.py`'s array version — a third independent
  implementation of the same math).
- `cluster_colors(pixels, k) -> List[Dict]` (lines 26-57): runs
  `cv2.kmeans` (`KMEANS_RANDOM_CENTERS`, 10 attempts, up to 50 iterations
  or 0.2 epsilon convergence) over a flat pixel array, clamping `k` to
  `[1, len(pixels)]`; returns one dict per resulting cluster (`rgb`, `hex`,
  `percent` of total pixels, `luminance`), sorted by `percent` descending
  (most dominant cluster first).
- `extract_global_colors(img_rgb, k=8) -> List[Dict]` (lines 65-67):
  `cluster_colors` over every pixel in the whole image, flattened.
- `extract_adjacent_text_pixels(img_rgb, bbox, padding=6) -> np.ndarray`
  (lines 75-94): crops a padded region around a text bbox, then masks
  **out** the bbox's own interior (`mask[ty0:ty1, tx0:tx1] = False`),
  returning only the pixels *surrounding* the text — used to sample
  background color without contamination from the text glyphs themselves.
- `_adaptive_k(pixels, max_k=5) -> int` (lines 97-101): picks a cluster
  count proportional to color diversity — counts unique pixel values,
  divides by 100, clamps to `[2, max_k]` — so a nearly-flat background gets
  fewer clusters than a busy, multi-color one.
- `extract_colors_from_mask(region, mask, k_bg=0) -> Dict` (lines 104-154)
  — the function `text_detector.py` actually calls:
  1. Converts BGR→RGB.
  2. Foreground pixels = `region_rgb[mask == 255]`.
  3. **Background erosion fix** (documented inline, lines 116-120,
     131-138): erodes the background mask by 2px (`cv2.erode`, 3×3 kernel,
     2 iterations) before sampling, to strip the 1-2px ring of
     anti-aliased/border-bleed pixels between text and true background —
     without this, minority edge colors (e.g. UI-chrome grey) could form
     spurious clusters that trigger false WCAG violations. Falls back to
     the un-eroded mask if erosion consumed every background pixel (tiny
     regions).
  4. Returns `{"error": ...}` if either pixel population ends up empty.
  5. Foreground: `cluster_colors(text_pixels, k=2)`, picks the
     highest-`percent` cluster as `fg_color`.
  6. Background: `cluster_colors(bg_pixels, k=effective_k_bg)` where
     `effective_k_bg` is either the caller-supplied `k_bg` or
     `_adaptive_k(bg_pixels)`.
  7. Returns `{"foreground": fg_color, "background_palette": bg_clusters}`.
- `extract_text_color(img_rgb, bbox) -> Dict` (lines 162-172): crops the
  bbox interior directly (no mask needed — this is used where the caller
  already knows the crop is "mostly text"), clusters `k=2`, returns the
  **brightest** cluster (`max` by `luminance`) as the presumed text color —
  a simpler, unmasked alternative to `extract_colors_from_mask`, used only
  by the `__main__` demo block below (not called from `text_detector.py`'s
  live path, which uses the mask-based function instead).
- `if __name__ == "__main__":` block (lines 179-214): a standalone demo —
  hardcodes a local path (`/home/meghana/Downloads/bc_asset1.jpg` — a
  developer's own machine, not portable), runs EasyOCR directly, and prints
  color/contrast analysis for each detected region. Not part of any
  production code path; exists purely as a manual testing/demo script.

**Side effects**: `cv2.imread` in the demo block only; otherwise pure array
computation.

**Used elsewhere**: `text_detector.py`'s `detect_text_in_image`
(`extract_colors_from_mask`).

---

## `ka11y/preprocessor/text_helper_models.py` (59 lines)

**Purpose**: the Pydantic models for OCR results, plus the shared
NumPy-aware JSON serializer.

**Imports**: `typing.*`, `numpy as np`, `pydantic.BaseModel/Field`. No
internal imports.

**Models**:
- `DetailedDetection(BaseModel)` (lines 6-22): `text`, `confidence`,
  `bbox: List[tuple[int,int]]`, `contrast_info`/`color_info` (opaque
  dicts), `wcag_violations: List[str]`, and `needs_review: bool = False` —
  the field documented at length in its own comment (reproduced in this
  module's `text_detector.py` write-up above) as the fix distinguishing
  "contrast determined and passing" from "contrast could not be
  determined at all."
- `TextDetectionResult(BaseModel)` (lines 25-36): `filename`,
  `original_path`, `has_text`, `detections: List[DetailedDetection]`,
  `contrast_violations_count`, `contrast_needs_review_count`, `new_path`
  (the copied-into-category-folder destination), `category` (default
  `"other"`).
- `TextDetectionReport(BaseModel)` (lines 38-47): the top-level report —
  `scan_date`, `source_directory`, totals, `results: List[TextDetectionResult]`.

**Function `_json_serializer(obj)`** (lines 50-58): a `json.dump(...,
default=...)` handler converting `np.ndarray`→`list`, `np.integer`/
`np.floating`→native Python via `.item()`, `np.bool_`→`bool`; raises
`TypeError` for anything else (the standard "I don't know how to serialize
this" signal `json.dump` expects from a `default` callback).

**Side effects**: none. **Used elsewhere**: `text_detector.py` (both the
models and the serializer), `runner.py` (imports `_json_serializer`
directly for the combined report's own JSON dump).

---

## `ka11y/i18n/loader.py` (386 lines)

**Purpose**: loads WCAG rule metadata (name, description, suggested fix,
level, severity, per-code reason templates) from a shared YAML file plus
per-language override files, with in-process caching — the single source
every localized string in a finding, the `/rules/wcag` endpoint, and
`report.py`'s label maps ultimately goes through.

**Imports**: `logging`, `os`, `re`, `functools.lru_cache`, `pathlib.Path`,
`typing.*` (stdlib); `pydantic.BaseModel/ConfigDict`, `yaml` (third-party).

**Directory resolution** (lines 37-41): `_REPO_ROOT = Path(__file__).parents[3]`
(walks up from `ka11y-python/ka11y/i18n/loader.py` to the monorepo root, the
same pattern `utils/config_loader.py` uses); prefers
`<repo_root>/i18n/` (shared between `ka11y-python` and `ka11y-node`) if it
exists, else falls back to `<ka11y-python>/i18n/`; `$KA11Y_I18N_DIR`
overrides either.

**Models**:
- `RuleEntry(BaseModel, frozen=True)` (lines 44-54): `id`, `level`,
  `severity` (Optional — never localized, "stable enum" per the comment at
  the build site), `name`, `description`, `suggested_fix`,
  `reason_templates: Mapping[str, str]`.
- `LocaleBundle(BaseModel, frozen=True)` (lines 57-65): `lang`,
  `rules: Mapping[str, RuleEntry]`, `severities`/`levels`/`statuses`
  (each a `{value: localized_label}` map).

**`_load_yaml(path) -> dict`** (lines 68-77): safe YAML load — returns `{}`
on `FileNotFoundError` or a YAML parse error (logged as a warning), never
raises.

**Default English label fallbacks** (lines 80-99):
`_DEFAULT_SEVERITY_LABELS_EN`, `_DEFAULT_LEVEL_LABELS_EN`,
`_DEFAULT_STATUS_LABELS_EN` — hardcoded, used only if neither the base
`rules.yml` nor a locale file defines a label for a given key.

**`_load_bundle_cached(lang) -> LocaleBundle`** (`@lru_cache(maxsize=16)`,
lines 102-145) — the core loader:
1. Loads `I18N_DIR/rules.yml` as the base (English-authoritative) data.
2. If `lang == "en"`, `locale_data = {}` (no overlay needed); else loads
   `I18N_DIR/locales/<lang>.yml`.
3. Calls `_build_entries` (rule-level merge) and `_merge_label_map` three
   times (severities/levels/statuses).
4. Returns the assembled `LocaleBundle`. Cached per `lang` string — up to
   16 distinct languages held in memory at once (an LRU eviction beyond
   that, though in practice this project ships only `en`/`de`/`ja` locale
   files per the i18n directory structure referenced elsewhere).

**`_merge_label_map(fallback_en, base, override) -> Dict[str,str]`** (lines
148-161): for the union of keys across the hardcoded English fallback, the
base YAML, and the locale override, picks (via `_pick`) the override value
if present, else the base value, else the English fallback.

**`_build_entries(base_rules, locale_rules, base_templates_top=None,
locale_templates_top=None) -> Dict[str, RuleEntry]`** (lines 164-226) — the
more involved per-rule merge:
1. Reason templates may be authored either **nested** under each rule
   (`rules.<sc>.reason_templates.<code>`) or in a **top-level**
   `reason_templates: {<sc>: {<code>: ...}}` block — this function merges
   both forms, with the top-level block winning over the nested form when
   both define the same code (documented precedence, lines 172-175).
2. Includes **synthetic SC IDs** that exist only in `reason_templates`
   (e.g. `"_generic"`, referenced by `render_reason`'s fallback logic
   below) even though they have no entry in `rules:` — so a shared
   catch-all message block can be looked up like any other rule.
3. For each SC ID: merges `name`/`description`/`suggested_fix`
   (override-wins-over-base-wins-over-empty via `_pick`), and merges the
   four possible template sources (top-override > nested-override >
   top-base > nested-base) per reason code.
4. `severity` is explicitly taken **only from `base`**, never overridden by
   locale data — reinforcing that it's a stable machine enum, not a
   display string.

**`_pick(override, fallback) -> str`** (lines 229-235): returns `override`
if it's a non-empty (after `.strip()`) value, else `fallback` (coerced to
`str`, or `""` if `fallback` is `None`).

**`_safe_lang(lang) -> str`** (lines 238-241): strips everything but
`[a-zA-Z-]`, truncates to 10 chars, strips leading/trailing hyphens,
defaults to `"en"` — the path-traversal guard for a `lang` value that
ultimately becomes part of a filesystem path (`locales/<lang>.yml`).

**Public API**:
- `load_bundle(lang="en") -> LocaleBundle` (lines 244-246): sanitizes
  `lang`, delegates to the cached loader.
- `load_rules(lang="en") -> Dict[str, RuleEntry]` (lines 249-254): returns
  a fresh `dict` copy of `load_bundle(lang).rules` (a copy, not the frozen
  model's own mapping, so callers can't accidentally mutate the cached
  bundle).
- `get_wcag_names`, `get_wcag_levels` (always English — level isn't
  localized), `get_suggested_fixes`, `get_severities` (only SCs with a
  non-`None` severity), `get_severity_labels`, `get_level_labels`,
  `get_status_labels`, `get_severity_label`/`get_level_label`/
  `get_status_label` (single-value lookups, each returning the raw value
  itself as a fallback if no label mapping exists) (lines 262-320) — these
  are exactly the functions `api/v1/combined/constants.py`,
  `api/v1/rules/metadata.py`, `findings.py`, and `report.py` all import.
- `render_reason(sc, code, lang="en", fallback="", params=None) -> str`
  (lines 323-378) — the localization workhorse every `_make_finding` call
  with a `reason_code` goes through:
  1. Injects a default `params["wcag_sc"] = str(sc)` so generic templates
     that reference `{wcag_sc}` render usefully even if the caller didn't
     pass one explicitly.
  2. Looks up `bundle.rules[sc].reason_templates[code]`.
  3. If not found and `lang != "en"`, falls back to the **English**
     version of the same `(sc, code)` template.
  4. If still not found, falls back to the shared `_generic` block's
     template for that `code` (in the requested language, then English) —
     so every SC participates in localization even without its own
     per-code templates.
  5. If no template was found anywhere, returns `fallback` verbatim.
  6. Otherwise, `template.format_map(_SafeDict(params))` — formats with the
     params dict, where missing placeholders render as `""` instead of
     raising `KeyError` (via `_SafeDict.__missing__`); a formatting
     exception (e.g. a malformed `{` in the template) is caught, logged,
     and returns `fallback or template` (the raw unformatted template
     string as a last resort, so the caller still gets *something*
     readable rather than an exception propagating).
  Docstring notes `params` is deliberately a plain dict argument rather
  than `**kwargs`, specifically so a placeholder name could collide with
  this function's own parameter names (`sc`, `code`, `lang`, `fallback`)
  without conflict.

**Class `_SafeDict(dict)`** (lines 381-385): overrides `__missing__` to
return `""` instead of raising — the mechanism behind point 6 above.

**Side effects**: reads YAML files from `I18N_DIR` (cached after first
read per language).

**Used elsewhere**: pervasively — `api/v1/combined/constants.py`,
`api/v1/combined/findings.py`, `api/v1/combined/report.py`,
`api/v1/rules/metadata.py`, and `accessibility/pipeline/formatters/evidence_formatter.py`
(the one place the orphaned pipeline engine still reaches into a live
module — see `05-MODULES-pipeline.md`).
