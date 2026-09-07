# 4. Module-by-Module Breakdown — Group 4: Bespoke Rule Auditors (`accessibility/rules/`)

As established in `02-ARCHITECTURE.md`, only two subpackages exist here:
`non_text/` (WCAG 1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11 for images) and `media/`
(WCAG 1.2.1, 1.2.2, 1.2.3, 1.4.2 for audio/video). Both are dict/CSV-based —
unlike the typed `accessibility/pipeline/` group — because they operate
directly on `ImageData`/raw dicts from the crawler rather than the pipeline's
`ElementContext` model.

---

## `ka11y/accessibility/rules/non_text/contrast_analyser.py` (370 lines)

**Purpose**: pixel-level, OpenCV-based contrast measurement — segments text
from its background inside a cropped image region and computes the WCAG
contrast ratio, independently of (and more precisely than) the pipeline's
CSS-computed-style-based `ContrastEngine` (`05-MODULES-pipeline.md`), because
here there often is no CSS to read (the "text" is baked into image pixels).

**Imports**: `cv2`, `numpy as np`, `typing.*`. No internal imports (pure
CV/math module).

**Functions**:
- `srgb_to_linear(channel: np.ndarray) -> np.ndarray` (lines 12-15):
  vectorized sRGB→linear-light conversion (the standard piecewise formula:
  linear division below the `0.04045` knee, gamma curve above it) — applied
  per color channel across a whole image array at once via NumPy.
- `segment_text_region(region) -> np.ndarray` (lines 23-69): the core
  text/background segmentation.
  1. Converts to grayscale, applies a bilateral filter (edge-preserving
     smoothing, `d=9, sigmaColor=75, sigmaSpace=75`) to reduce noise without
     blurring text edges.
  2. Otsu thresholding (`cv2.threshold(..., THRESH_BINARY + THRESH_OTSU)`) —
     automatically picks a binarization threshold, producing two candidate
     masks: text-as-white and text-as-black (the inverse).
  3. `compute_separation(mask)` (nested closure): converts the region to
     linear-light luminance, computes the mean luminance of pixels under
     each candidate mask, returns the absolute difference — a proxy for "how
     well does this mask actually separate two distinct tones."
  4. Picks whichever candidate mask has the **larger** separation — this is
     the polarity-detection fix also seen in `utils/text_detector_helper.py`'s
     `estimate_boldness` (same underlying problem: you can't assume "dark =
     text" because light-text-on-dark-background is common).
- `calculate_luminance_contrast(region, mask) -> Tuple[float,float,float]`
  (lines 77-114): computes per-pixel linear luminance, splits into
  text-pixel and background-pixel populations by the mask; determines
  polarity (`text_is_light = mean(text) > mean(bg)`); uses **robust
  percentiles** rather than the raw mean — 90th percentile for the "lighter"
  population and 10th for the "darker" one (or the reverse, matching
  polarity) — "to avoid noise" (comment), i.e. anti-aliased edge pixels at
  the text/background boundary don't skew the measurement toward the
  average. Returns `(text_L, bg_L, contrast_ratio)` using the standard WCAG
  `(lighter+0.05)/(darker+0.05)` formula; returns `(None, None, None)` if
  either population is empty (segmentation totally failed).
- `get_average_rgb(region, mask) -> Tuple[RGB, RGB]` (lines 122-143):
  reporting-only — average RGB (not luminance) of the foreground and
  background pixel populations, defaulting to white/black respectively if a
  population is empty (so the returned tuple is always well-formed for
  display purposes).
- `check_wcag_compliance(ratio, font_size_px=16, is_bold=False,
  is_ui_component=False) -> Dict` (lines 151-192): the shared pass/fail
  classifier.
  - `is_ui_component=True` path: only an AA check against a flat **3.0:1**
    threshold (WCAG 1.4.11 is AA-only — no AAA tier exists for it, so
    `AAA_passes: None` is explicitly returned rather than a fabricated
    value, per the inline comment).
  - Otherwise: computes `is_large` (≥24px, or ≥18.6667px **and** bold —
    18.6667 = 14pt × 96/72 DPI conversion), then AA threshold 3.0/4.5 and AAA
    threshold 4.5/7.0 depending on size. Explicitly casts every boolean to
    plain Python `bool()` (comment lines 177-179: `font_size_px` can be a
    `np.float64` from `bbox_height_rotated`'s `np.linalg.norm`, which makes
    comparisons return `np.bool_` — not JSON-serializable by the stdlib
    `json` module, so this cast prevents a downstream serialization crash).
- `analyze_text_region(image, bbox, font_size_px=16, is_bold=False) -> Dict`
  (lines 200-258) — the **main entry point for text-in-image contrast**
  (used by the OCR/text-detector pipeline, not directly by `alttext.py`):
  1. Loads the image (path or already-decoded array).
  2. Computes the axis-aligned bounding rect of the (possibly rotated)
     `bbox` polygon via `cv2.boundingRect`, pads by 2px on each side
     (clamped to image bounds).
  3. Crops, segments, computes luminance/contrast/average colors.
  4. Runs `check_wcag_compliance` **always against the text-size thresholds,
     never the `is_ui_component` 3:1 shortcut** — an inline comment (lines
     236-241) clarifies this is deliberate: 1.4.3/1.4.6 apply to text based
     on the text's own size/weight regardless of whether it's inside a
     button; the separate 1.4.11 approximation for UI components is computed
     independently elsewhere (in `alttext.py`'s `_check_1_4_11`, off this
     same `contrast_ratio` value, against its own 3:1 threshold).
  5. Returns a dict with `region`, `mask` (raw arrays, for debugging/visual
     overlay), `foreground_color`, `background_color`, `luminance_fg/bg`,
     `contrast_ratio`, `compliance`. Any exception is caught and returned as
     `{"error": str(e)}`.
- `_compute_luminance_map(region) -> np.ndarray` (lines 266-277): the
  per-pixel linear-luminance array for a whole region (factored out for
  reuse by `analyze_ui_component`).
- `analyze_ui_component(image, bbox, context_pad=8) -> Dict` (lines
  280-369) — **the WCAG 1.4.11 boundary-contrast measurer**, documented in
  its own docstring as fixing two named issues ("F14" — page context wasn't
  included; "F15" — the `is_ui_component` compliance path wasn't actually
  used):
  1. Computes the component's bounding rect, then expands it by
     `context_pad` (default 8px, but `alttext.py` calls this via
     `contrast_analyser.analyze_ui_component` with the crawler's own
     40px-padded context screenshot — so in practice the real padding
     comes from the crawler capture, not this default) to include
     surrounding page pixels.
  2. **Edge check**: if the expanded region touches the image boundary
     (`x0==0 or y0==0 or x1==W or y1==H`), returns
     `{"needs_review": True, "reason": "Insufficient surrounding context..."}`
     — there's no real "surrounding" pixels to compare against.
  3. Builds a binary mask: `255` for the inner (component) region, `0` for
     the padding ring around it.
  4. Computes linear luminance for the whole padded crop, splits by mask,
     uses **median (50th percentile)**, not the 10th/90th used for
     text — presumably because a UI component's fill color is more uniform
     than antialiased text glyph edges, so the median is a reasonable robust
     center without needing polarity-aware percentile selection.
  5. Computes the ratio, calls `check_wcag_compliance(ratio,
     is_ui_component=True)`.
  6. Returns `{contrast_ratio, luminance_component, luminance_background,
     compliance, type: "ui_component"}`. Any exception → `{"error": ...}`.

**Side effects**: `cv2.imread` when given a file path (file I/O); otherwise
pure array computation.

**Used elsewhere**: `analyze_ui_component` is called directly from
`non_text/alttext.py`'s `_check_1_4_11`; `analyze_text_region` is called from
the OCR/text-detector pipeline (`09-MODULES-text-classifier-i18n.md`).

---

## `ka11y/accessibility/rules/non_text/alttext.py` (1,575 lines)

**Purpose**: the single largest rule-auditor file — merges `ImageData`
(crawler + classifier output) with OCR `TextDetectionResult`s and produces
one CSV row per crawled image covering WCAG 1.1.1, 4.1.2, 1.4.3, 1.4.5,
1.4.6, and 1.4.11. Despite the module's own docstring header still reading
`ka11y/accessibility/audit.py` (a stale copy-paste from before this file was
moved/renamed into `rules/non_text/`), this is the file actually imported as
`ka11y.accessibility.rules.non_text.alttext`.

**Imports**: `re`, `csv`, `pathlib.Path`, `datetime.datetime` (stdlib);
`ka11y.config.logger.setup_logger`,
`ka11y.accessibility.rules.non_text.contrast_analyser` (internal — imports
its own package sibling, used only by `_check_1_4_11`).

### Module-level constants (lines 44-277)

- `_EMPTY_OR_GENERIC` (lines 48-70): a set of alt-text strings/fragments
  treated as "effectively no alt text" — `""`, `"image"`, `"photo"`,
  `"placeholder"`, `"decorative"`, etc.
- `_SOCIAL_BRAND_NAMES` (lines 79-98): recognized brand/service names
  (`facebook`, `twitter`/`x`, `instagram`, `github`, …) that count as an
  adequate icon alt text on their own — with an inline comment explaining
  why bare `"x"` is kept despite colliding conceptually with inadequate
  `alt="X"` close-button labels (those route through the button check, not
  the icon check, and a named regression test locks in the behavior).
- `_LOGO_WORDS`, `_HOME_WORDS` (lines 101-102): English + Japanese
  logo/home keyword sets.
- `_BUTTON_ACTION_WORDS` (lines 105-241): a large English + Japanese list of
  recognized UI action verbs/labels (`menu`, `close`, `submit`, `メニュー`,
  `閉じる`, …) — the vocabulary `_check_1_1_1_button` and `_check_4_1_2`
  match against.
- `_REPORT_COLUMNS` (lines 244-277): the fixed CSV column order for
  `audit_report.csv`.
- `_BRAND_LOGO_NAME_TOKENS` / `_BRAND_LOGO_SRC_RE` (lines 306-325) — a
  **Kao-specific** allow-list (explicitly documented as such, "currently
  Kao," "keep it brand-agnostic in shape so more entries can be added") that
  extends the WCAG contrast logotype-text exemption to brand marks the image
  classifier's `sub_type == "logos"` heuristic misses (a plain `<img
  alt="Kao">` with no "logo" keyword, an inline SVG wordmark, etc.). This
  matches the "Kao-logo 1.4.3 exemption" noted as already-done in project
  memory.

### Helper functions (lines 285-392)

- `_norm(text) -> str` (lines 285-289): lowercase, strip punctuation
  (`[^\w\s]` → space), collapse whitespace.
- `_is_empty(value) -> bool` (lines 292-293): treats the literal strings
  `"nan"`, `"none"`, `""`, `"null"` (case-insensitive) as empty — guards
  against pandas/CSV-round-trip artifacts leaking through as real values.
- `_is_brand_logo(src, alt, title="") -> bool` (lines 328-339): checks the
  Kao allow-list against normalized alt/title text or a src/filename regex
  match.
- `_build_ocr_index(ocr_results) -> dict` (lines 342-353): pre-builds a
  `{basename.lower(): TextDetectionResult}` map — the docstring notes this
  replaced an O(n×m) `Path` allocation hot loop that ran per-image inside
  `generate_audit_report`, now O(1) per lookup.
- `_ocr_for_file(ocr_results, filename, index=None) -> (has_text,
  detected_texts, contrast_violations_count)` (lines 356-379) and
  `_ocr_result_for_file(ocr_results, filename, index=None)` (lines 382-391):
  both accept the optional precomputed `index` for O(1) lookup, falling back
  to an O(m) linear scan if not supplied (keeping the older call signature
  usable).

### WCAG 1.1.1 check functions (lines 399-720)

Each returns `(status: bool | None, reason: str)` — `True`=pass,
`False`=fail, `None`=needs review ("INCOMPLETE" in the reason text
convention used throughout this file).

- `_check_1_1_1_decorative(alt) -> (bool|None, str)` (lines 399-424): for
  images classified decorative. `alt` here is the **resolved accessible
  name**, not necessarily the raw `alt` attribute (per the docstring, citing
  `optimized/adapter._alt_text`). Passes if empty/generic (conformant,
  intentionally unnamed); returns `None` (INCOMPLETE) if it has a real name
  — a deliberate softening from an older "hard FAIL" implementation, since a
  non-empty name on a decorative-classified image is a conflicting signal
  needing human judgment, not an automatic violation.
- `_is_aria_hidden_from_at(aria_hidden, role) -> bool` (lines 427-435):
  `aria-hidden="true"` or `role` in `presentation`/`none`.
- `_check_1_1_1_missing_alt(sub_type, aria_hidden=None, role=None) ->
  (bool, str)` (lines 438-455): for a completely missing `alt` attribute —
  passes only if the element is programmatically hidden from AT, else fails.
- `_context_exemption(img, alt_text) -> tuple|None` (lines 461-530) — the
  most consequential function in this section, evaluating **context-driven**
  1.1.1 outcomes that override the per-classification checks below it:
  1. **CSS background images** (`element_type in
     {css_background_image, css_background_svg}`, no own name): passes if
     the element has its own rendered text content (the background is
     decoration behind real text) or if it's not inside an unlabeled
     control; **fails** only in the specific case of being the *sole*
     content of an unlabeled link/button (the background image alone is
     carrying the control's purpose).
  2. **Image inside an already-labeled control** with no own name: passes
     (`"functional_redundant"`) if `alt=""` was explicitly set (textbook
     pattern); returns `None`/INCOMPLETE if the `alt` attribute is missing
     entirely (the control's name covers the purpose, but a screen reader
     might still announce the image's bare filename without an explicit
     `alt=""`).
  Returns `None` if neither situation applies, signaling "run the normal
  per-classification check instead."
- `_check_1_1_1_informative(alt, detected_texts) -> (bool|None, str)`
  (lines 533-594): for classification `"informative"`. Fails if alt is
  empty/generic. If no OCR text was detected, passes with a "(manual review
  recommended)" caveat woven into the pass reason text (not a NEEDS_REVIEW
  status, but an advisory note). Otherwise tokenizes the OCR text (words
  ≥3 chars, or any length if non-ASCII — CJK words are routinely 1-2
  characters, so the length floor is skipped for them; 2-letter uppercase
  abbreviations like "UI"/"AI"/"OK" are separately recovered via a regex
  since `_norm` lowercases and would otherwise treat them the same as any
  other 2-char token and drop them) and checks whether any OCR word appears
  as a whole word in the alt text; matches → pass, no matches → `None`
  (INCOMPLETE) rather than a hard fail, since OCR misreads decorative
  flourishes/watermarks routinely (docstring explicitly weighs "an incorrect
  violation costs the reader far more than a review item").
- `_check_1_1_1_logo(alt) -> (bool, str)` (lines 597-620): passes as long as
  *any* non-generic name is present — the literal word "logo" is explicitly
  **not** required (docstring cites W3C WAI's own Images Tutorial example,
  `alt="Kao"`/`alt="Home"`, as correct), only fails on empty/generic.
- `_check_1_1_1_icon(alt) -> (bool, str)` (lines 623-667): passes for a
  recognized social/brand name alone (no "icon" suffix needed — same
  reasoning as logos), or if the alt contains an `icon`/`logo`/`button`/
  `link` qualifier word, or a recognized action word; otherwise requires
  ≥4 chars with at least one non-trivial (2 consecutive lowercase letters,
  or non-ASCII) content to pass as "non-empty, verify manually"; else fails.
- `_check_1_1_1_button(alt) -> (bool|None, str)` (lines 670-719): passes on
  a recognized action word (exact match or as a word within the string);
  fails if <3 chars or purely numeric; otherwise, for an unrecognized-but-
  plausible description (≥2 words, or contains a vowel, and has real
  letter/non-ASCII content) passes with a manual-verification caveat;
  anything left over (looks like meaningless filler, e.g. "xyz"/"qwerty"
  with no vowel) returns `None` (INCOMPLETE) rather than the previous
  behavior of auto-passing any 3+-character non-numeric string (explicitly
  called out as a fixed false-negative in the inline comment).

### WCAG 4.1.2 check (lines 727-766)

- `_check_4_1_2(alt, sub_type, *, control_named=False) -> (bool, str)`:
  4.1.2 only asks whether a name **exists and is programmatically
  determinable**, not how it's phrased (wording quality is 1.1.1's concern,
  per the docstring). Passes if the containing control already exposes a
  name (`control_named=True`) even when this element's own name is empty;
  otherwise fails only if genuinely nameless; a `sub_type == "logos"` name
  containing a logo/home keyword gets a slightly more specific pass message.

### WCAG 1.4.5 check (lines 774-834)

- `_check_1_4_5(classification, sub_type, is_logo, has_ocr_text) ->
  (bool|None, str)`: `None` (N/A) for decorative images (exempt); passes
  unconditionally for `complex`/`charts` classification (text is essential
  presentation) and for any logo (`is_logo`) — the docstring includes a long
  retrospective note (lines 799-817) explaining and justifying the **removal**
  of a previous "F12 FIX" that tried to fail logos containing OCR-readable
  text, on the grounds that (a) it could never actually execute because the
  `is_logo` branch always short-circuited first, and (b) its premise was
  wrong — a plain OCR-readable wordmark is still an exempt logotype under
  WCAG's own "essential presentation" exception, so making that dead code
  "work" would have created new false failures on ordinary text logos.
  Otherwise: passes if no text was detected at all, fails if text was
  detected in a non-exempt image.

### WCAG 1.4.11 check (lines 842-948)

- `_check_1_4_11(is_button, is_icon, sub_type, has_ocr_text, ocr_result, *,
  full_page_image=None, component_bbox=None) -> (bool|None, str)`: `None`
  (N/A) unless the element is a UI component (button/icon or matching
  sub_type). **Path 1** (preferred, "the F14 fix"): if a padded context
  screenshot + local bounding box were captured by the crawler (icon/logo
  elements only, per `optimized/engine.py`'s `_capture_assets`), calls
  `contrast_analyser.analyze_ui_component` for a real boundary-vs-surrounding-
  page-background measurement; a `needs_review` result (edge-of-page) or an
  `"error"` result falls through to **Path 2**: the OCR text-contrast proxy —
  the minimum contrast ratio across all OCR-detected text regions *inside*
  the component's own screenshot crop, explicitly documented as measuring
  something different (text-vs-its-own-background, not
  component-boundary-vs-page) and only an approximation.

### `AltTextAccessibilityAuditor` class (lines 956-1575)

- `generate_audit_report(self, images_data, ocr_results, output_dir) ->
  list[dict]` (lines 962-1461) — the ~500-line main method, one iteration
  per `ImageData`:
  1. Pulls raw fields off the `ImageData` model.
  2. **Capture-failure short-circuit** (lines 1007-1054): if
     `capture_status != "ok"`, emits a row with every WCAG status set to
     `INCOMPLETE`/`N/A` (never a false PASS/FAIL derived from data that was
     never actually captured) and `continue`s to the next image — this is a
     deliberate design choice so a screenshot-capture failure degrades to
     "needs manual review," not a silently-wrong verdict.
  3. OCR lookup via the prebuilt index; computes `text_flag` — `True` when
     OCR found text but the classifier's own `is_text_image` flag missed
     it (a disagreement worth surfacing).
  4. Derives `sub_type` from boolean flags if the classifier left it
     generic (`"images"`/empty).
  5. **1.1.1 dispatch** (lines 1094-1217): checks `_context_exemption`
     first (context always wins); then a special-cased
     `missing_alt`/`decorative-with-None-alt` path; then
     `classification`-based routing to `_check_1_1_1_decorative` /
     `_informative` / (for `functional`) `_logo`/`_icon`/`_button` by
     `sub_type` / a bespoke `complex` (chart/diagram) branch requiring both
     a short name **and** a long description (via `img.has_long_description()`,
     defined on the `ImageData` model — `04-MODULES-crawler.md`) — missing
     both → fail, name-only → `NEEDS_REVIEW`, both → pass; a catch-all
     `else` for any unrecognized classification just checks alt
     non-emptiness. Each branch also sets `wcag_1_1_1_code` — a
     machine-readable code the i18n formatter (`findings.py`, see
     `07-MODULES-api.md`) uses to localize the reason text.
  6. **4.1.2**: only computed for `classification == "functional"`
     (elsewhere left `N/A — not a functional image"`), or inside the
     context-exemption branch if applicable.
  7. **1.4.5**: calls `_check_1_4_5`, then a documented override (lines
     1229-1249): if `text_flag` is set (OCR found text the classifier
     missed) and the image isn't decorative/complex/logo, forces `FAIL`
     regardless of what `_check_1_4_5` returned — closing the gap where
     the classifier's own miss would otherwise silently pass a real
     images-of-text violation.
  8. **1.4.11**: calls `_check_1_4_11`, passing through the crawler's
     `full_page_screenshot_path`/`page_bbox` fields if present.
  9. **1.4.3 & 1.4.6** (lines 1273-1331): `N/A` for decorative/logo/brand-logo
     images (using `_is_brand_logo` — with an inline comment explaining a
     **prior bug**: the classifier never actually sets `classification` to
     the literal string `"logo"`, so a check that tested for that string
     could never fire, meaning the logotype-text contrast exemption was
     silently dead code before this fix); otherwise aggregates the
     per-OCR-detection AA/AAA compliance flags (preferring a
     `dominant_contrast` sub-object if present, falling back to the
     top-level `contrast_info`) — any `False` → fail, any `None` (missing
     data) with no `False` → INCOMPLETE, all `True` → pass. Computed
     independently for AA (1.4.3) and AAA (1.4.6).
  10. **Status-string derivation** (lines 1335-1389): converts each
      `bool|None` into `"PASSED"/"FAILED"/"INCOMPLETE"/"N/A"` — a small
      but important detail for 1.4.3/1.4.6/1.4.11: `None` maps to
      `"INCOMPLETE"` only if the reason text actually starts with
      `"INCOMPLETE"` (else `"N/A"`), since these checks use `None` for both
      "not applicable" and "needs review" depending on branch, distinguished
      only by the reason text prefix — a slightly fragile string-based
      discriminator worth knowing about if `alttext.py` is ever refactored.
  11. **Overall status** (lines 1390-1412): `FAILED` if any of
      `{1.1.1, 4.1.2, 1.4.3, 1.4.5, 1.4.11}` failed; else `INCOMPLETE` if any
      is incomplete; else `PASSED`. **1.4.6 (AAA) is deliberately excluded**
      from the overall verdict (an AAA-only enhancement doesn't gate the
      A/AA-focused overall result) — with an inline comment flagging a fixed
      prior bug where `all([])` on an empty status tuple vacuously evaluated
      `True`, so an image whose *only* applicable criterion was unresolved
      got reported as a definitive PASSED alongside its own "needs review"
      text.
  12. Appends the full row dict; after the loop, writes `audit_report.csv`
      (`csv.DictWriter`, fixed `_REPORT_COLUMNS` order) and calls
      `self._print_summary(...)`.
- `_print_summary(self, records, report_path)` (lines 1465-1574): prints a
  formatted console report — totals, PASSED/FAILED percentages, per-criterion
  pass/fail counts (1.1.1, 4.1.2, 1.4.5, 1.4.11), a by-classification table,
  OCR/contrast-violation counts, and a table of failed images (filename,
  classification, sub-type, alt-text preview, 1.1.1/4.1.2 status) — purely a
  human-readable console artifact, no return value.

**Side effects**: writes `<output_dir>/audit_report.csv`; extensive
`print()`/`logger.info()` console output.

**Used elsewhere**: `api/v1/combined/stages.py` (the image-audit stage)
instantiates `AltTextAccessibilityAuditor` and calls
`generate_audit_report` after the crawler + OCR + classifier stages have
run; the resulting `records` feed `api/v1/combined/findings.py`'s report
assembly.

---

## `ka11y/accessibility/rules/media/__init__.py` (1 line — a comment)

Trivial package marker, included here only for completeness (no logic).

---

## `ka11y/accessibility/rules/media/media_auditor.py` (985 lines)

**Purpose**: WCAG 1.2.1 (Audio-only/Video-only, Prerecorded), 1.2.2
(Captions, Prerecorded), 1.2.3 (Audio Description or Media Alternative), and
1.4.2 (Audio Control) — a 5(+)-gate decision tree per media element, per the
module's own extensive docstring.

**Imports**: `csv`, `re`, `pathlib.Path`, `typing.*` (stdlib); `requests`
(third-party, synchronous HTTP — notably **not** the `httpx`/async pattern
used elsewhere in this codebase, meaning the gate functions that call it
block the event loop while they run); `ka11y.config.logger.setup_logger`.

### Module-level constants (lines 46-89)

- `_TRANSCRIPT_LINK_KEYWORDS` (lines 46-68): English + Japanese phrases
  indicating a link leads to a transcript (`"transcript"`, `"text
  version"`, `書き起こし`, `字幕`, …).
- `_MEDIA_ALT_KEYWORDS` (lines 71-86): phrases indicating the media element
  *itself* is a labeled alternative for existing text (`"audio version"`,
  `音声版`, …).
- `_ALT_TRACK_KINDS = {"captions", "descriptions", "subtitles"}` (line 89).

### Helper (line 97)

- `_normalize(text) -> str`: lowercase + collapse whitespace, same pattern
  as every other rule-check helper in this codebase.

### Gate functions (lines 110-388) — each named after its position in the decision tree, returning `Optional[Tuple[status, message, gate_number]]` (`None` = "continue to the next gate")

- `_gate_1_is_prerecorded(item) -> Optional[Tuple]` (lines 110-152):
  detects **live** media via streaming-manifest file extensions (`.m3u8`
  HLS, `.mpd` DASH) or an explicit short "live" label (deliberately capped
  to ≤40 chars — a documented fix: scanning arbitrary long `nearby_text`
  prose for the bare word "live" false-matched sentences like "This
  interview was recorded live in our studio... and is now archived,"
  wrongly exempting genuinely prerecorded content). Returns `("N/A", ...,
  1)` if live (1.2.1 doesn't apply — see 1.2.9, which per the earlier
  grep is **not implemented** in this codebase), else `None`.
- `_gate_2_media_type(item) -> str` (lines 155-202): classifies
  `"audio_only"` (any `<audio>` tag), `"video_only"` (a `<video>` that is
  muted + looping + autoplaying — the "likely decorative background video"
  pattern), or `"synchronized"` (the default for everything else, including
  a `<video>` with no reliable signal). The function's docstring and the
  code's own inline comments (lines 165-170, 186-199) candidly document
  the automation ceiling here: reliably detecting whether a `<video>` truly
  carries an audio track needs the browser's JS media APIs
  (`audioTracks`/`webkitAudioDecodedByteCount`), which aren't populated
  until the browser starts actually loading the media — not available from
  a static crawl pass — so "synchronized" is a deliberate default bias
  (favoring the much more common case) rather than a confirmed fact, and
  the eventual 1.2.1 N/A reason text says so explicitly.
- `_gate_3_is_labeled_alternative(item) -> Optional[Tuple]` (lines
  205-251): a **confident** `("N/A", ..., 3)` if `_MEDIA_ALT_KEYWORDS`
  matches the element's own `aria-label` (an author-set, trustworthy
  signal); a softer `("NEEDS_REVIEW", ..., 3)` if the match is only in
  `nearby_text` (arbitrary surrounding prose that could be a coincidental,
  unrelated mention) — explicitly documented as a fix for a prior bug where
  a coincidental nearby-text match silently hid genuine missing-transcript
  violations behind an authoritative-looking N/A.
- `_gate_4_find_transcript(item) -> (info|None, fail_tuple|None)` (lines
  254-326): searches, in order, `<track>` children of kind
  captions/descriptions/subtitles, nearby `<a>` links matching
  `_TRANSCRIPT_LINK_KEYWORDS`, nearby `<details>` blocks whose summary
  matches, and a substantial (>50 char) `aria-describedby` text block
  (treated as likely *being* the transcript itself). Returns a `FAILED`
  tuple at gate 4 if none found.
- `_gate_4_check_captions(item) -> (info|None, fail_tuple|None)` (lines
  329-351): the **1.2.2-specific** variant — looks for a
  `captions`/`subtitles` track (subtitles accepted as a caption substitute,
  per the comment "can serve as captions if they include non-speech audio
  cues" — later downgraded at the point of use, see below).
- `_gate_5_validate_track_url(track_url) -> Optional[Tuple]` (lines
  354-387) — **network call**: `requests.head(track_url, timeout=5,
  allow_redirects=True)`; if the server responds `405` (Method Not
  Allowed — some servers blanket-reject HEAD), **retries with a streamed
  GET, closed immediately without reading the body**, specifically so a
  genuinely-404ing track on such a server is still caught here rather than
  silently downgrading to a later `NEEDS_REVIEW` (documented fix, lines
  367-373). Any status ≥400, or a network exception, fails at gate 5.

### WCAG 1.2.3 and 1.4.2 checks (lines 395-486)

- `_check_1_2_3_audio_description(item, tracks) -> (status, message)`
  (lines 395-434): passes if a `descriptions`-kind track exists; else falls
  back to the 1.2.3 exemption via `_gate_3_is_labeled_alternative`; else
  returns `NEEDS_REVIEW` — the docstring is candid that "does this video's
  visual track carry information the audio doesn't" is a judgment call this
  auditor cannot make automatically, explicitly comparing itself to the
  "all findings need manual review" ceiling documented elsewhere for WCAG
  2.5.4 (which, per the correction note in `01-OVERVIEW-AND-ENTRYPOINT.md`,
  no longer has its own auditor in this codebase — this comment is a
  historical cross-reference to a removed module).
- `_check_1_4_2_audio_control(item) -> (status, message)` (lines 442-485):
  `N/A` if the media doesn't autoplay; `PASSED` if it autoplays muted (no
  audible sound to control) or has native `controls`; else `FAILED`,
  explicitly caveated as an "F23-pattern" strong signal rather than an
  absolute — a custom JS-implemented pause/mute control elsewhere on the
  page wouldn't be visible to this static check, and the message says to
  verify before treating it as confirmed.

### VTT/SRT parsing (lines 488-522)

- `_download_and_parse_vtt(track_url) -> Optional[str]`: **network call**
  (`requests.get`, 10s timeout); strips the `WEBVTT` header, timestamp lines
  (`-->`), pure-numeric sequence-ID lines, and simple inline tags
  (`<b>`,`<i>`, `<c...>` styling spans) to recover the plain spoken-caption
  text — used to feed the WER-based caption-quality check in
  `quality_engine.evaluate_captions_quality`.

### `MediaAuditor` class (lines 529-984)

- `CSV_FIELDS` (lines 537-561): the fixed output column order for
  `audit_media_report.csv`, covering all four criteria plus transcript/
  quality-report metadata and element identity (`selector`,
  `element_ref_id`, `frame_path` — the same ref fields
  `universal_page.py`'s `_annotate_records` stamps, letting a media finding
  be traced back to its exact DOM element).
- `__init__(self, output_dir, lang="en")` (lines 563-566): **side effect**
  — `self.output_dir.mkdir(parents=True, exist_ok=True)`.
- `generate_audit_report(self, items, run_1_2_1=True, run_1_2_2=True) ->
  List[Dict]` (lines 568-596): iterates `items` (raw
  `MediaElementData.model_dump()` dicts), calling `_audit_single` per item,
  then writes the CSV and logs a summary.
- `_audit_single(self, item, run_1_2_1=True, run_1_2_2=True) -> Dict`
  (lines 598-883) — the ~285-line per-element decision-tree driver:
  1. Builds a `base` record with every status defaulted to `N/A`.
  2. **1.4.2 runs unconditionally first**, independent of the
     prerecorded/live gate chain below it (it applies to any
     automatically-playing audio regardless of that classification).
  3. **Gate 1** (live check) — if live, sets `media_type: "live"` and
     returns immediately (1.2.1/1.2.2/1.2.3 all stay N/A).
  4. **Gate 2** (media type). If `"synchronized"`: sets 1.2.1 to N/A with
     the "assumed synchronized" caveat text; **always** runs the cheap 1.2.3
     audio-description check (no network/transcription needed); then, if
     `run_1_2_2`, walks the **1.2.2 sub-chain**: gate 3 (labeled
     alternative) → gate 4 (captions track present) → gate 5 (track URL
     reachable) → **"Gate 6" — Deepgram caption verification**: downloads
     and parses the VTT/SRT (`_download_and_parse_vtt`), and if both the
     caption text and the media URL are available, calls
     `quality_engine.evaluate_captions_quality` (deferred import, avoiding
     a module-level dependency on the heavy Deepgram/spaCy/nltk stack for
     callers that never reach this path) to WER-compare against a fresh
     Deepgram transcription; the resulting status is capped at
     `NEEDS_REVIEW` if the track's `kind` was `"subtitles"` rather than
     `"captions"` even on a clean WER score — documented reasoning (lines
     770-789): a subtitles track is only required to carry dialogue, not
     non-speech audio cues (music, sound effects, speaker changes), which
     WCAG 1.2.2 captions must also describe, so a passing WER alone can't
     confirm full compliance.
  5. If media type is **not** synchronized (i.e. `audio_only`/`video_only`):
     runs the **1.2.1 gate chain** — gate 3 (labeled alternative) → an
     explicit decorative/`aria-hidden` check (N/A) → gate 4
     (`_gate_4_find_transcript`) → **Gate 5, mandatory quality checks**
     (`self._run_quality_checks`), whose result's `overall_status` becomes
     the final 1.2.1 verdict.
- `_run_quality_checks(self, media_src, transcript_info, media_type) ->
  Optional[Dict]` (lines 885-914): deferred-imports and calls
  `quality_engine.evaluate_transcript_quality`; returns `None` (rather than
  raising) on missing inputs or any exception, logged as a warning — so a
  quality-engine failure degrades the specific element to a generic
  `NEEDS_REVIEW` in `_audit_single` rather than aborting the whole audit.
- `_write_csv` / `_log_summary` (lines 918-942): straightforward CSV write
  (`extrasaction="ignore"` — tolerates records carrying extra keys beyond
  `CSV_FIELDS`, e.g. the earlier-computed `quality_report` dict which isn't
  itself a CSV column verbatim but happens to be present in the record) and
  a one-line pass/fail/review/na count log.
- `summarize(records) -> Dict` (staticmethod, lines 944-961): a
  report-assembly-facing summary dict (`total_elements`, `checked`,
  `passed`, `failed`, `needs_review`, `na`, `pass_rate_pct`,
  `wcag_1_2_1_failed`) — note this summary is 1.2.1-specific despite the
  auditor now also computing 1.2.2/1.2.3/1.4.2 (a scope the summary method
  hasn't been extended to cover).

**Side effects**: synchronous blocking HTTP requests (`requests.head`/`.get`)
for track-URL validation and VTT download — inside what is otherwise an
async codebase, meaning these gate calls (invoked from `_audit_single`,
itself called synchronously from `generate_audit_report`) will block
whichever thread/event-loop-turn runs them unless the caller offloads this
whole auditor to a thread (see `07-MODULES-api.md`/`10-EXECUTION-FLOW.md`
for whether `stages.py` does so); writes `audit_media_report.csv`.

**Used elsewhere**: `api/v1/combined/stages.py`'s media-audit stage.

---

## `ka11y/accessibility/rules/media/quality_engine.py` (1,099 lines)

**Purpose**: WCAG 1.2.1/1.2.2 "Gate 5" transcript/caption **quality**
evaluation — given a developer-provided transcript or caption track, decides
whether it's actually an equivalent alternative to the media, using a
Deepgram-API ground-truth transcription plus Word-Error-Rate (WER), speaker-
label regex matching, non-speech-event bracket-keyword matching, and (for
video-only content) NLTK/spaCy part-of-speech density as a weak proxy for
"does this describe visual content."

**Imports**: `os`, `re`, `tempfile` (unused directly it seems, likely
vestigial), `pathlib.Path`, `typing.*`, `hashlib`, `datetime.datetime`
(stdlib); `httpx` (async-capable client, used here synchronously via
`httpx.Client`), `nltk`, `spacy`, `jiwer.wer as compute_wer`,
`nltk.tokenize.word_tokenize` (third-party); `ka11y.config.logger.setup_logger`,
`ka11y.utils.not_implemented` (internal).

**Function `_verify_visual_equivalence_with_vision_model(...)`** (lines
46-58): decorated `@not_implemented(reason="vision-model verification... is
reserved for a future implementation")` — a genuine, live use of the
`utils/not_implemented.py` decorator documented in
`03-MODULES-config-utils.md`; calling this raises `NotImplementedError`. It
is the honest placeholder for what Check 4 (visual content) would ideally
be, versus what it actually is today (POS-tag heuristics only, always
`NEEDS_REVIEW`).

**Module-level NLTK bootstrap** (lines 61-69): at **import time**, checks
for `punkt_tab` and `averaged_perceptron_tagger_eng` NLTK data and downloads
them if missing (`nltk.download(..., quiet=True)`) — a runtime safety net on
top of the Dockerfile's build-time pre-download, for environments where the
image wasn't built with them.

**spaCy model loading**:
- `_SPACY_MODELS` (lines 76-79): `{"en": ("en_core_web_sm",), "ja":
  ("ja_core_news_lg", "ja_core_news_sm")}` — Japanese tries the large model
  first (what the Dockerfile installs), falling back to the small one.
- `_get_nlp(lang) -> Optional[spacy.Language]` (lines 83-99): a
  process-lifetime cache (`_nlp_cache` dict) — loads and caches the first
  candidate model that imports successfully for a language; logs a warning
  and caches `None` if nothing loads (so callers must handle a `None`
  return, and the cache prevents re-attempting a known-failed load on every
  call).

**Constants** (lines 102-116, 143-144, 147-252): `_MAX_DOWNLOAD_BYTES = 100
MB`, `_DOWNLOAD_TIMEOUT = 60.0`; WER thresholds `_WER_PASS_THRESHOLD=0.15` /
`_WER_FAIL_THRESHOLD=0.40` (duplicated as `_WER_PASS`/`_WER_FAIL` at lines
143-144 — two names for effectively the same pair of numbers, a minor
redundancy); `_AUDIO_EVENT_KEYWORDS` (English + Japanese non-speech event
vocabulary — "applause", "music", "拍手", "音楽", …); `_SPEAKER_PATTERNS`
(English + Japanese regexes for `Name:`/`[Name]`/`Speaker N:`/`話者1：`-style
speaker labels).

**Function `_save_transcript_locally(text, media_url, output_dir="")`**
(lines 118-142): **side effect** — writes the raw Deepgram transcript to
`<output_dir>/output/transcripts/{timestamp}_{md5(url)[:10]}.txt`
(creating the directory), prefixed with the source URL and audit
timestamp, for manual audit verification. Failure is caught and logged as a
warning, returning `None`.

**Function `_check_result(check_name, status, message, **extra) -> Dict`**
(lines 260-272): the standardized `{check, status, message, ...extra}`
result-dict factory used by every check function below.

**Function `_prepare_transcript(text, source_type) -> str`** (lines
280-312): strips HTML tags for `"link"`-sourced text; strips VTT/SRT headers,
timestamp lines, and bare sequence-number lines for `"track"`-sourced text;
passes `"inline"`/`"aria_describedby"` text through unchanged.

**Check 1 — `_check_verbatim(whisper_text, dev_transcript, lang="en") ->
Dict`** (lines 320-384): normalizes both texts (lowercase, collapses
acronym-dot patterns like "W.C.A.G." → "wcag" via a lookbehind/lookahead
regex, collapses whitespace); for Japanese, **tokenizes into words via
spaCy** before computing WER — the docstring/comment explicitly notes this
is *required* for Japanese (no whitespace word boundaries), falling back to
character-level tokenization if spaCy is unavailable; computes `jiwer.wer`
and classifies PASS (≤15%) / NEEDS_REVIEW (15-40%) / FAILED (>40%).

**Check 2 — `_check_speaker_ids(dev_transcript, whisper_segment_count=0,
speaker_count=0, lang="en") -> Dict`** (lines 392-449): if the language has
no entry in `_SPEAKER_PATTERNS` (only `en`/`ja` exist), returns
`NEEDS_REVIEW` rather than silently falling back to the English regex
patterns — explicitly justified (lines 406-411) because the English
patterns rely on Latin-script capitalization, which would simply never
match a script with no case distinction (Korean, Chinese, etc.) and falsely
report correctly-labeled speakers as `FAILED`. Otherwise counts regex
matches; `FAILED` only if Deepgram detected multiple distinct speakers
(`speaker_count > 1`) but zero labels were found in the transcript;
single-speaker content with no labels is `NEEDS_REVIEW`, not a fail (may be
legitimately unnecessary).

**Check 3 — `_check_non_speech_events(dev_transcript, lang="en") -> Dict`**
(lines 457-529): extracts bracketed/parenthesized text (Latin and Japanese
bracket forms `【】`/`（）`), and if none found returns `NEEDS_REVIEW` — not
`FAILED` — with a documented rationale (lines 470-479): this function only
sees the transcript text, with no way to know whether the *source audio*
actually contains any non-speech events worth noting at all, so "no
descriptors" could mean either "author omitted them" or "there weren't
any" — asserting `FAILED` unconditionally would wrongly penalize an
accurate transcript of plainly-narrated content with no music/sound
effects. If descriptors were found but the language has no keyword table,
also `NEEDS_REVIEW` (can't confirm the descriptors are recognized event
terms). Otherwise matches against `_AUDIO_EVENT_KEYWORDS[lang]`.

**Check 4 — `_check_visual_content(dev_transcript, lang="en") -> Dict`**
(lines 537-576): POS-tags the transcript (spaCy for Japanese, NLTK
`pos_tag`+`word_tokenize` for English, both capped to the first 2000
characters for speed), counts action verbs (`VERB`/tags starting `VB`) and
adjectives, computes verb density. **Always returns `NEEDS_REVIEW`** — this
check has no pass/fail threshold at all; it's purely diagnostic metadata
("cannot verify visual accuracy without a vision model," referencing the
not-implemented hook above) surfaced for a human reviewer.

**Check 5 — `_check_sequence(whisper_segments, dev_transcript, lang="en")
-> Dict`** (lines 584-678): divides the Deepgram segments into 4 time
quarters (by total duration) and the dev transcript into 4 quarters by word
count (again spaCy-tokenized for Japanese, whitespace-split for English);
computes word-set Jaccard overlap (`|A∩B| / |A∪B|`) per quarter pair;
`PASSED` if the average overlap across quarters is ≥30%, else `FAILED`
("content may be reordered"). `NEEDS_REVIEW` if there's insufficient data
(no segments, empty transcript, zero total duration).

**`_download_media(url, output_dir, media_type="audio") -> Optional[str]`**
(lines 686-739): **network + disk side effect** — streams the media file
via `httpx.Client` with a spoofed desktop Chrome `User-Agent` (documented as
needed to avoid 403s from CDNs like Wikimedia that block non-browser UAs),
checking `content-length` (and enforcing the same limit while streaming, in
case the header lied or was absent) against `_MAX_DOWNLOAD_BYTES` (100MB);
saves to `<output_dir>/output/media/{audio|video}/{timestamp}_{md5(url)[:10]}{ext}`.
Returns `None` on any failure/oversize condition (logged as a warning).

**`_transcribe_audio(audio_path, media_url="unknown_url", output_dir="") ->
Optional[Dict]`** (lines 747-831): **network side effect** — the Deepgram
API call. Reads `DEEPGRAM_API_KEY` from the environment (returns `None`
immediately, logging a warning, if unset); POSTs the raw audio bytes to
`https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&
utterances=true&diarize=true&punctuate=true` with a 120s timeout; parses
either the utterance-level diarized result (building `segments` with
`start`/`end`/`text`/`speaker`, and counting unique `speaker` values) or
falls back to the flat `channels[0].alternatives[0].transcript` if no
utterances came back; saves the transcript locally via
`_save_transcript_locally`; returns `None` on any exception.

**`evaluate_transcript_quality(*, media_url, transcript_text,
transcript_type="link", media_type="audio_only", output_dir="", lang="en")
-> Dict`** (lines 839-977) — the **Gate 5 orchestrator** for WCAG 1.2.1:
1. Cleans the transcript via `_prepare_transcript`; returns `NEEDS_REVIEW`
   immediately if it's under 10 characters.
2. For `media_type == "audio_only"`: downloads the media, transcribes it via
   Deepgram; if both succeed, runs **Checks 1, 2, 3, 5**; if Deepgram
   transcription fails (missing key, API error), falls back to **text-only**
   Checks 2 and 3 plus a synthetic `NEEDS_REVIEW` "verbatim" result
   explaining transcription wasn't possible; if the *download itself*
   failed, same text-only fallback. Notably, a comment (lines 922-924) says
   the downloaded temp file is **no longer deleted** ("as requested") —
   downloaded media accumulates in `output_dir/output/media/` across runs
   (see `12-OUTPUT-FILES.md` for the retention implications).
3. For `media_type == "video_only"`: runs **Check 4** and a static
   `NEEDS_REVIEW` "sequence" result (no audio timeline exists for
   video-only content to compare against).
4. **Overall status**: `FAILED` if any check failed; `PASSED` only if
   *every* check passed; otherwise `NEEDS_REVIEW` (mirroring the "any fail
   wins, else any incomplete wins" pattern seen throughout this codebase's
   other overall-status rollups).
5. Returns `{overall_status, message, checks, wer_score, wer_thresholds}`.

**`evaluate_captions_quality(*, media_url, caption_text, output_dir="",
lang="en") -> Dict`** (lines 980-1079) — the **1.2.2 Gate 6** counterpart:
downloads the video, transcribes via Deepgram, then computes WER between
the Deepgram ground truth and the developer-provided caption text (after a
locally-defined `clean_text` — lowercase + strip punctuation via
`str.translate`, distinct from `_prepare_transcript`/`_check_verbatim`'s own
normalizers, a third slightly-different text-cleaning implementation in this
file). Handles the "no speech detected" edge case (both empty → `PASSED`,
"no speech" with unexpected captions → `NEEDS_REVIEW`, likely covering
sound-effect-only captioning) before computing WER; classifies PASSED
(≤15%, using `<=` explicitly matching `_check_verbatim`'s boundary — the
inline comment at lines 1051-1055 documents this as a **fixed
inconsistency bug**: `_check_verbatim` used `<=` while an earlier version of
this function used `<`, so an identical WER of exactly 15% got a different
verdict from the two "same-threshold" checks); FAILED (>40%);
`NEEDS_REVIEW` otherwise. Any exception in the WER computation itself is
caught and returns `NEEDS_REVIEW` with the transcript preserved but no
score.

**Side effects**: outbound HTTP (media download, Deepgram API call);
filesystem writes (downloaded media, saved transcripts) that are **not
cleaned up** (explicit design choice per the inline comments); reads
`DEEPGRAM_API_KEY` from the environment.

**Used elsewhere**: `media_auditor.py`'s `_run_quality_checks` (1.2.1) and
the inline Gate 6 call inside `_audit_single` (1.2.2) are the only two call
sites.
