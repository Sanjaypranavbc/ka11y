# ka11y Test Case Documentation

**Scope:** `ka11y-python/tests/` — every test class, every test function, with full reasoning for techniques and inputs.
**Date:** 2026-03-23

---

## Table of Contents

1. [Shared Infrastructure](#1-shared-infrastructure)
2. [test_rendered_geometry.py — Geometry Helpers](#2-test_rendered_geometrypy--geometry-helpers)
3. [test_rendered_evaluators.py — Rendered Layout Evaluators](#3-test_rendered_evaluatorspy--rendered-layout-evaluators)
4. [test_rendered_converters.py — Rendered Layout Converters](#4-test_rendered_converterspy--rendered-layout-converters)
5. [test_alt_text_auditor.py — WCAG 1.1.1 Alt Text](#5-test_alt_text_auditorpy--wcag-111-alt-text)
6. [test_form_auditor.py — WCAG 3.3.1 / 3.3.2 Forms](#6-test_form_auditorpy--wcag-331--332-forms)
7. [test_label_in_name_auditor.py — WCAG 2.5.3 Label in Name](#7-test_label_in_name_auditorpy--wcag-253-label-in-name)
8. [test_target_size_auditor.py — WCAG 2.5.8 Target Size](#8-test_target_size_auditorpy--wcag-258-target-size)
9. [test_pause_stop_hide_auditor.py — WCAG 2.2.2 Pause/Stop/Hide](#9-test_pause_stop_hide_auditorpy--wcag-222-pausestophide)

---

## 1. Shared Infrastructure

### `conftest.py`

**Fixture: `tmp_output(tmp_path) -> str`**

- **Purpose:** Provides each test with a fresh, isolated, writable directory path.
- **Technique:** Wraps pytest's built-in `tmp_path` fixture (which creates a unique `tempfile`-backed directory per test invocation) and converts it to a plain `str` because the auditors accept `output_dir: str`, not `Path`.
- **Why per-test isolation:** Auditors write CSV files as a side-effect of `generate_audit_report`. Without isolation, tests that check for CSV existence or column structure would interfere with each other when run in parallel or when a previous test left a stale file.
- **Why not a module-scoped fixture:** Module scope would share the directory across all tests in a file, meaning assertion order would matter. Function scope eliminates that coupling entirely.

---

<div id="2-test_rendered_geometrypy--geometry-helpers"></div>
## 2. `test_rendered_geometry.py` — Geometry Helpers

**WCAG context:** Supports all seven rendered-layout checks (1.4.4, 1.4.10, 1.4.12, 1.3.4, 1.4.13, 2.4.11, 2.4.12). These helper functions are the mathematical foundation for deciding whether elements overflow their containers, overlap overlays, or are scrolled off-screen. Getting the geometry wrong would silently produce incorrect pass/fail verdicts on every rendered check.

**Technique pattern:** All geometry tests use pure numeric inputs (no browser, no DOM). The functions accept plain dicts or named tuples representing bounding-box coordinates. This makes the tests deterministic, fast, and independent of Playwright, which cannot run in a CI environment without a real display.

---

### Class `TestRect`

#### `test_rect_from_dict_basic`
- **Function under test:** `rect_from_dict(d)`
- **Input:** `{"x": 10, "y": 20, "width": 100, "height": 50}`
- **Why this input:** The four keys (`x`, `y`, `width`, `height`) are exactly what `page.evaluate()` returns from `getBoundingClientRect()`. The values are small integers that produce trivially verifiable derived properties (right = 110, bottom = 70).
- **Technique:** Direct structural equality assertion on all six fields (x, y, width, height, right, bottom). Checks that the constructor correctly computes the derived `right` and `bottom` from the supplied primitives.

#### `test_rect_from_dict_zero_origin`
- **Input:** All zeros.
- **Why:** Zero-origin is the degenerate case — right == x == 0, bottom == y == 0. Catches off-by-one errors or missing addition in derived-field computation.

#### `test_rect_width_and_height_preserved`
- **Input:** `width=200, height=400` with non-zero origin.
- **Why:** Ensures width/height are stored verbatim, not recomputed from right−left. Some implementations compute right first and then derive width back, which can accumulate floating-point drift.

---

### Class `TestIntersectionArea`

#### `test_no_overlap_returns_zero`
- **Function under test:** `intersection_area(a, b)`
- **Input:** Two rects that do not touch (`a` ends at x=100, `b` starts at x=200`).
- **Why:** The canonical "completely separated" case. Any non-zero result here is a direct bug in the max/min clamp logic.

#### `test_partial_overlap_correct_area`
- **Input:** `a=(0,0,100,100)`, `b=(50,50,100,100)` → overlap region is `(50,50,50,50)` → area 2500.
- **Why:** Partial overlap is the most common real case (partially hidden focus indicators). The exact value 2500 is computed analytically, making the assertion precise rather than approximate.

#### `test_full_containment_returns_smaller_rect_area`
- **Input:** Small rect entirely inside larger rect.
- **Why:** Verifies the formula handles strict containment (the "focused element is completely hidden by an overlay" scenario for WCAG 2.4.11/2.4.12).

#### `test_touching_edges_returns_zero`
- **Input:** Two rects sharing an edge but not overlapping interior.
- **Why:** Boundary condition — `max(left_a, left_b) == min(right_a, right_b)` produces zero intersection width. This edge case trips up `>=` vs `>` comparisons.

#### `test_identical_rects_returns_full_area`
- **Why:** Maximal overlap. Validates that both clamp directions work correctly simultaneously.

---

### Class `TestOverlapRatio`

#### `test_zero_area_element_returns_zero`
- **Function under test:** `overlap_ratio(element_rect, overlay_rect)`
- **Input:** `element_rect` with width=0, height=0.
- **Why:** Zero-area element would cause division-by-zero if the ratio is computed as `intersection / element_area`. The function must guard this case and return 0 rather than raising `ZeroDivisionError`.

#### `test_fully_covered_element_returns_one`
- **Why:** The focus-obscured checks flag elements with `overlap_ratio >= 1.0`. This test ensures that ratio caps at exactly 1.0 (not 0.99 due to floating-point arithmetic on identical coordinates).

#### `test_half_covered_returns_point_five`
- **Input:** 100×100 element, 50×100 overlay covering the left half.
- **Why:** 0.5 is the natural midpoint assertion. Validates linear scaling of the ratio.

#### `test_no_overlap_returns_zero`
- **Why:** Complementary to `test_fully_covered`. Bookends the valid range [0, 1].

---

### Class `TestHasIntersection`

#### `test_returns_true_for_overlapping`
- **Function under test:** `has_intersection(a, b)`
- **Why:** `has_intersection` is a boolean shorthand used in the focus-obscured evaluators before computing the more expensive `overlap_ratio`. Tests the happy path.

#### `test_returns_false_for_non_overlapping`
- **Why:** Confirms the early-exit path for non-overlapping elements, which is the common case (most focused elements are not obscured).

#### `test_touching_edge_returns_false`
- **Why:** Consistent with `TestIntersectionArea` — touching edges are not an overlap for accessibility purposes. An element edge-touching an overlay is still fully visible.

---

### Class `TestIsClipped`

#### `test_fully_visible_element_not_clipped`
- **Function under test:** `is_clipped(element_rect, container_rect)`
- **Input:** Element entirely within container.
- **Why:** Baseline — an element within its scroll container should never be considered clipped.

#### `test_element_extending_beyond_right_edge_is_clipped`
- **Input:** Element right edge (200) > container right edge (150).
- **Why:** Horizontal overflow is the primary symptom of WCAG 1.4.10 (Reflow) violations. The right-edge check is the most common failure path.

#### `test_element_extending_below_container_is_clipped`
- **Why:** Vertical clipping — needed for detecting text overflow out of fixed-height containers (WCAG 1.4.4 Resize Text).

#### `test_element_starting_above_container_is_clipped`
- **Input:** Element y < container y.
- **Why:** Negative-offset clipping — happens with CSS `top: -n` used to visually hide content. Caught by the top-edge check.

---

### Class `TestIsOffscreen`

#### `test_visible_element_not_offscreen`
- **Function under test:** `is_offscreen(rect, viewport_width, viewport_height)`
- **Input:** `rect=(10, 10, 100, 50)`, viewport `(1440, 900)`.
- **Why:** Normal case — element well within viewport.

#### `test_element_completely_to_the_right_is_offscreen`
- **Input:** `rect.x = 2000` with viewport width 1440.
- **Why:** Horizontal scroll indicator — an element rendered beyond the viewport right edge is the direct symptom of WCAG 1.4.10 reflow failure at 320px.

#### `test_element_partially_outside_is_still_considered_visible`
- **Input:** Element partially outside right edge.
- **Why:** Partially visible elements are not "offscreen" — they pass the reflow check because the user can see the content without requiring a separate scroll axis. Only fully off-screen elements are flagged.

---

### Class `TestIsHidden`

#### `test_display_none_is_hidden`
- **Function under test:** `is_hidden(computed_style)`
- **Input:** `{"display": "none"}`
- **Why:** The most common way to hide elements. Hidden elements must be excluded from target-size and focus-obscured checks, because their bounding box is zero and they cannot receive focus.

#### `test_visibility_hidden_is_hidden`
- **Input:** `{"visibility": "hidden"}`
- **Why:** `visibility: hidden` elements still occupy layout space but are not interactive. Must also be excluded.

#### `test_opacity_zero_is_hidden`
- **Input:** `{"opacity": "0"}`
- **Why:** Zero opacity is visually identical to hidden, but `getBoundingClientRect` still returns a non-zero box. If not filtered, transparent focus indicators would cause false "not obscured" passes.

#### `test_visible_element_not_hidden`
- **Input:** `{"display": "block", "visibility": "visible", "opacity": "1"}`
- **Why:** Confirms the function returns False for the normal case — avoids over-aggressive filtering.

---

### Class `TestHasHorizontalScroll`

#### `test_no_overflow_returns_false`
- **Function under test:** `has_horizontal_scroll(scroll_width, client_width)`
- **Input:** `scroll_width=500, client_width=500`.
- **Why:** Exact equality — no overflow. Tests the boundary condition where scroll and client widths match.

#### `test_overflow_returns_true`
- **Input:** `scroll_width=600, client_width=500`.
- **Why:** 100px overflow — direct evidence of horizontal scroll, which is a WCAG 1.4.10 failure.

#### `test_scroll_width_less_than_client_returns_false`
- **Input:** `scroll_width=400, client_width=500`.
- **Why:** Scroll width can be less than client width when the viewport is larger than content. Must not be flagged as overflow.

---

### Class `TestTextContainerOverflows`

#### `test_non_overflowing_container_ok`
- **Function under test:** `text_container_overflows(element_rect, container_rect, threshold_px=5)`
- **Input:** Element fully within container bounds.
- **Why:** Normal case — text fits in its box. The 5px `threshold_px` default is tested implicitly.

#### `test_slight_overflow_within_threshold_ok`
- **Input:** Element overflows container by exactly 4px.
- **Why:** The 5px threshold accommodates sub-pixel rounding errors from different browser rendering engines. An overflow of 4px should not be flagged as a violation.

#### `test_overflow_beyond_threshold_detected`
- **Input:** Element overflows by 10px.
- **Why:** 10px is clearly beyond measurement noise. Validates that genuine text overflow (content cut off by `overflow: hidden`) is correctly detected.

#### `test_threshold_is_configurable`
- **Why:** The threshold is a parameter for flexibility (some auditors may use stricter or looser thresholds). Tests that passing `threshold_px=0` makes even 1px overflow detectable.

---

### Class `TestDocumentHasHorizontalScroll`

#### `test_document_with_scrollbar_flagged`
- **Function under test:** `document_has_horizontal_scroll(snapshot)`
- **Input:** A synthetic snapshot dict with `document_scroll_width > document_client_width`.
- **Why:** WCAG 1.4.10 requires that content reflows without horizontal scrolling at 320px width. This function checks the document-level scroll, which is the most reliable indicator.

#### `test_document_without_scrollbar_not_flagged`
- **Input:** `document_scroll_width == document_client_width`.
- **Why:** Baseline passing case.

---

<div id="3-test_rendered_evaluatorspy--rendered-layout-evaluators"></div>
## 3. `test_rendered_evaluators.py` — Rendered Layout Evaluators

**WCAG context:** Seven evaluators, one per rendered-layout WCAG SC: 1.4.10 (Reflow), 1.4.12 (Text Spacing), 1.4.4 (Resize Text), 1.3.4 (Orientation), 1.4.13 (Hover/Focus Content), 2.4.11 (Focus Not Obscured Min), 2.4.12 (Focus Not Obscured Enh).

**Technique pattern:** All evaluator tests use **synthetic Pydantic objects** via factory helpers (`_rect()`, `_el()`, `_snap()`). No browser, no Playwright, no network. The evaluators receive fully-constructed snapshot objects and return a `RuleAuditRecord`. This isolates the business logic from crawler infrastructure — a crawler bug cannot make an evaluator test fail.

**Factory helpers:**
- `_rect(**kw)` — builds a `BoundingRect` with sane defaults (e.g., `x=0, y=0, width=100, height=50`).
- `_el(**kw)` — builds a `RenderedElement` with a default rect, tag=`DIV`, no overflow.
- `_snap(**kw)` — builds a `RenderedSnapshot` wrapping a list of elements and document dimensions.

---

### Class `TestReflow` — WCAG 1.4.10

#### `test_no_overflow_passes`
- **Function under test:** `ReflowEvaluator.evaluate(snapshot)`
- **Input:** Snapshot where `document_scroll_width <= document_client_width` and all elements within viewport.
- **Why:** Establishes the baseline pass — content fits without horizontal scroll.

#### `test_document_horizontal_scroll_fails`
- **Input:** `document_scroll_width > document_client_width`.
- **Why:** Document-level horizontal scroll is the primary indicator of a reflow failure. The evaluator must catch this even if individual elements appear to fit, because the page-level `scrollWidth` is the authoritative measurement.

#### `test_element_overflowing_viewport_fails`
- **Input:** An element with `right > viewport_width`.
- **Why:** Even when the document `scrollWidth` is correct (e.g. due to `overflow: hidden` on body), individual elements can overflow their stacking context. This catches that scenario.

#### `test_exempt_element_skipped`
- **Input:** An element with `role="img"` or tag `VIDEO` (known exempt from reflow requirement).
- **Why:** WCAG 1.4.10 exempts content that requires 2D layout (video, images, maps, games). The evaluator should not flag exempt elements, even if their bounding boxes extend beyond the viewport.

#### `test_multiple_overflows_all_reported`
- **Input:** Three overflowing elements.
- **Why:** Confirms that the evaluator collects all failures, not just the first. The consumer (`combined/findings.py` converter path) needs the full list to generate per-element findings.

---

### Class `TestTextSpacing` — WCAG 1.4.12

#### `test_no_overflow_passes`
- **Function under test:** `TextSpacingEvaluator.evaluate(snapshot)`
- **Input:** Snapshot taken after the text-spacing injection (line-height 1.5×, letter-spacing 0.12em, word-spacing 0.16em, paragraph 2em) with no clipped elements.
- **Why:** Baseline — after the forced spacing, text still fits. Most pages should pass.

#### `test_clipped_element_fails`
- **Input:** An element with `overflows_container=True` (set by crawler after injecting CSS overrides).
- **Why:** Text spacing violations manifest as text overflowing a fixed-height container (`overflow: hidden`). The `overflows_container` flag is set by the crawler when `scrollHeight > offsetHeight` after the CSS injection.

#### `test_offscreen_element_ignored`
- **Input:** Element with `is_offscreen=True`.
- **Why:** Off-screen elements (e.g. modal backdrop content, off-canvas menus) are not rendered to the user and should not trigger spacing violations. They also have unreliable bounding boxes.

#### `test_zero_area_element_ignored`
- **Input:** Element with width=0, height=0.
- **Why:** Zero-area elements (collapsed or `display:none` content in the DOM) would produce meaningless overflow ratios. The evaluator must skip them to avoid false positives.

---

### Class `TestResizeText` — WCAG 1.4.4

#### `test_text_fits_at_200_percent_passes`
- **Function under test:** `ResizeTextEvaluator.evaluate(snapshot)`
- **Input:** Snapshot captured at 200% zoom (Playwright's `page.set_viewport_size` with doubled effective font size) with no clipped text elements.
- **Why:** WCAG 1.4.4 requires that text can be resized to 200% without loss of content or functionality. A passing snapshot means the page handled the zoom gracefully.

#### `test_clipped_text_at_200_percent_fails`
- **Input:** An element marked with `text_clipped=True` (set by crawler when `scrollHeight > clientHeight` at 200% zoom).
- **Why:** `text_clipped` is the direct evidence of failure — content is rendered but cut off by `overflow: hidden` or a fixed `height` that doesn't scale with font size.

#### `test_non_text_element_ignored`
- **Input:** Element with `contains_text=False` (e.g. a `<div>` used purely for layout).
- **Why:** WCAG 1.4.4 applies only to text content. Layout-only elements may legitimately overflow their containers without text being hidden.

#### `test_element_matching_by_css_selector`
- **Why:** The evaluator uses CSS selectors (not tag+text) for element matching between baseline and zoomed snapshots. This test verifies that the `css_selector` field is used as the primary join key, making match deterministic even when the DOM has multiple identical tags.

---

### Class `TestOrientation` — WCAG 1.3.4

#### `test_no_orientation_lock_passes`
- **Function under test:** `OrientationEvaluator.evaluate(snapshot)`
- **Input:** Snapshot where no element has `locks_orientation=True`.
- **Why:** Most pages do not lock orientation. The baseline must pass without false positives.

#### `test_css_orientation_lock_fails`
- **Input:** An element with `locks_orientation=True` and `lock_source="css"` (CSS `@media (orientation: landscape) { display: none }` applied to a rotate-device overlay).
- **Why:** CSS orientation locks are the most common violation pattern. The evaluator must detect the `locks_orientation` flag set by the crawler when it finds orientation-specific media queries that hide the entire page body.

#### `test_meta_viewport_lock_fails`
- **Input:** `lock_source="meta_viewport"` — the `<meta name="viewport" content="...user-scalable=no">` pattern that also implies orientation lock.
- **Why:** Some sites use the viewport meta tag to prevent both scaling and rotation. The crawler sets `lock_source` to distinguish the cause so the violation message can include actionable remediation.

#### `test_rotate_overlay_fails`
- **Input:** An element with `is_rotate_overlay=True` (a `<div>` containing "rotate your device" text, which is a common UX pattern that effectively locks orientation).
- **Why:** Rotate-device overlays are a heuristic detection — they imply the page only works in one orientation. The evaluator flags these even without explicit CSS locking.

---

### Class `TestHoverFocusContent` — WCAG 1.4.13

#### `test_no_hover_content_passes`
- **Function under test:** `HoverFocusContentEvaluator.evaluate(snapshot)`
- **Input:** Snapshot with no elements that triggered hover/focus-revealed content.
- **Why:** Pages without tooltips/popovers should cleanly pass. Baseline test.

#### `test_non_dismissible_tooltip_fails`
- **Input:** An element with `has_hover_content=True`, `content_dismissible=False`.
- **Why:** WCAG 1.4.13 requires that hover/focus content can be dismissed with Escape. If `content_dismissible` is False, the criterion is failed.

#### `test_disappearing_tooltip_fails`
- **Input:** `has_hover_content=True`, `content_persistent=False`.
- **Why:** Tooltip content must persist when the pointer moves toward it (so users with motor impairments can move the cursor to the tooltip). If `content_persistent=False`, the tooltip vanishes before the user can interact with it.

#### `test_fully_compliant_tooltip_passes`
- **Input:** `has_hover_content=True`, `content_dismissible=True`, `content_persistent=True`, `content_hoverable=True`.
- **Why:** All three 1.4.13 sub-requirements satisfied simultaneously. Confirms the AND logic — all three must be true for the element to pass.

#### `test_non_hoverable_content_fails`
- **Input:** `content_hoverable=False` (the tooltip disappears when the pointer moves onto it).
- **Why:** Validates the third 1.4.13 sub-requirement independently. The user must be able to move the pointer from the trigger to the tooltip without the tooltip disappearing.

---

### Class `TestFocusNotObscuredMinimum` — WCAG 2.4.11

#### `test_fully_visible_element_passes`
- **Function under test:** `FocusNotObscuredMinimumEvaluator.evaluate(snapshot)`
- **Input:** Focused element with no overlapping sticky/fixed overlays.
- **Why:** Baseline — most focused elements are fully visible. Must not generate false positives.

#### `test_completely_hidden_element_fails`
- **Input:** Focused element with `overlap_ratio=1.0` (fully covered by a sticky header).
- **Why:** WCAG 2.4.11 fails when the focused component is entirely hidden. `overlap_ratio=1.0` is the exact threshold.

#### `test_partially_obscured_element_passes_minimum`
- **Input:** Focused element with `overlap_ratio=0.5`.
- **Why:** WCAG 2.4.11 (Minimum) only requires that the component is not *completely* hidden. A partially visible element satisfies this criterion. The threshold is `< 1.0`, not `< 0.5`.

#### `test_zero_overlap_passes`
- **Input:** `overlap_ratio=0.0` (overlay exists but doesn't touch the focused element).
- **Why:** Confirms the range lower bound — no overlap means unambiguous pass.

---

### Class `TestFocusNotObscuredEnhanced` — WCAG 2.4.12

#### `test_fully_visible_element_passes`
- **Function under test:** `FocusNotObscuredEnhancedEvaluator.evaluate(snapshot)`
- **Input:** Same as 2.4.11 baseline.
- **Why:** The enhanced version has a stricter threshold but the same baseline.

#### `test_any_obscuring_fails`
- **Input:** `overlap_ratio=0.1` (even slight overlap).
- **Why:** WCAG 2.4.12 (Enhanced/AAA) requires that *no part* of the focused element is obscured. Any overlap > 0 is a failure. This distinguishes it from 2.4.11.

#### `test_zero_overlap_passes`
- **Why:** The only passing case for the enhanced criterion — absolutely zero overlap.

---

<div id="4-test_rendered_converterspy--rendered-layout-converters"></div>
## 4. `test_rendered_converters.py` — Rendered Layout Converters

**WCAG context:** Converters translate raw `RuleAuditRecord` dicts (with `{rule_key}_status` and `{rule_key}_violation` fields) into the unified finding format consumed by the combined pipeline and frontend.

**Technique pattern:** **Parametric tests** (`@pytest.mark.parametrize`) over the four possible status values: `FAILED`, `PASSED`, `NEEDS_REVIEW`, `N/A`. This ensures every converter handles all status codes correctly without duplicating test logic. Each parametrize group is a separate test class per converter (7 converters × 4 status cases = 28 primary tests, plus edge cases = 36 total).

**Why parametric over individual tests:** A converter that handles `FAILED` correctly but silently maps `NEEDS_REVIEW` to `fail` instead of `needs_review` would cause the frontend to show incorrect badge colours and counts. Parametrize catches these asymmetric bugs systematically.

---

### Converter Classes Tested

Each converter class follows the same pattern. Representative explanations below.

#### `TestReflowConverter` (representative for all 7)

**`test_failed_status_maps_to_fail`**
- **Function under test:** `ReflowConverter.convert(record)`
- **Input:** Record dict with `reflow_status: "FAILED"`, a non-empty `reflow_violation` string.
- **Why `FAILED` specifically:** `FAILED` is the most consequential status — it produces a finding that counts toward the violation total and must have `"fail"` (lowercase) as the result, matching the JSON schema the frontend expects.

**`test_passed_status_maps_to_pass`**
- **Input:** `reflow_status: "PASSED"`, empty violation string.
- **Why:** `"pass"` result means no finding is shown in the Violations tab. If a converter accidentally maps `PASSED` to `"fail"`, every element would appear as a violation.

**`test_needs_review_maps_to_needs_review`**
- **Input:** `reflow_status: "NEEDS_REVIEW"`.
- **Why:** `NEEDS_REVIEW` results are shown in the "Needs Review" tab (requiring human confirmation). An incorrect mapping to `"fail"` would overcount violations; mapping to `"pass"` would hide items needing attention.

**`test_na_status_maps_to_skip`**
- **Input:** `reflow_status: "N/A"`.
- **Why:** `N/A` records (elements exempt from the rule) must be silently skipped — they should not appear in any tab. `"skip"` signals this to the aggregator.

**`test_empty_records_returns_empty_list`**
- **Input:** `[]`
- **Why:** Converters must handle empty input gracefully. An empty list is the common case for rules that found no applicable elements (e.g. a page with no interactive elements for 2.5.8).

**`test_mixed_statuses_all_converted`**
- **Input:** A list containing all four status types.
- **Why:** Confirms the converter processes every record in the list, not just the first. Integration-style test that exercises the loop/map logic.

**Field preservation tests (per converter):**
- `html_snippet`, `element_id`, `tag`, `page_url` are all asserted to be copied verbatim from input to output.
- **Why:** The frontend uses these fields to show element context. If `html_snippet` is lost, the developer can't identify which element caused the violation without re-crawling.

---

<div id="5-test_alt_text_auditorpy--wcag-111-alt-text"></div>
## 5. `test_alt_text_auditor.py` — WCAG 1.1.1 Alt Text

**WCAG context:** WCAG 1.1.1 requires that every non-text content item has a text alternative. The auditor uses OCR (via EasyOCR), image classification, and OCR-word matching to detect missing, generic, or misleading alt text.

**Technique pattern:** Unit tests use **pre-built `ImageData` objects** (Pydantic models) populated with synthetic field values, bypassing the Playwright crawler and the OCR pipeline. This keeps tests fast and deterministic — OCR output is non-deterministic and browser-dependent.

---

### Class `TestNorm`

#### `test_norm_lowercases`
- **Function under test:** `_norm(text)`
- **Input:** `"Hello World"`
- **Why:** The normalizer is used to compare alt text against OCR output. Case-insensitive comparison is required because OCR may return `"ACME"` while the alt text says `"Acme"`.

#### `test_norm_strips_punctuation`
- **Input:** `"Hello, World!"`
- **Why:** Punctuation differences between OCR output and alt text should not cause false negatives (incorrectly flagging text as non-matching when it semantically matches).

#### `test_norm_collapses_whitespace`
- **Input:** `"Hello  World"` (double space)
- **Why:** OCR frequently introduces extra spaces at character boundaries or between OCR regions.

#### `test_norm_empty_string_returns_empty`
- **Input:** `""`
- **Why:** Boundary condition — normalizing empty string must not crash and must return empty (not None or whitespace).

---

### Class `TestIsEmpty`

#### `test_none_is_empty`
- **Function under test:** `_is_empty(text)`
- **Input:** `None`
- **Why:** `alt` attribute absent from the DOM is represented as `None` in the crawler output. Must be treated as missing (triggers 1.1.1 violation).

#### `test_empty_string_is_empty`
- **Input:** `""`
- **Why:** `alt=""` is used for **decorative** images. The `_is_empty` check is used in a different context (missing alt text), so empty string must return True only when the decorative flag is also absent.

#### `test_whitespace_only_is_empty`
- **Input:** `"   "`
- **Why:** Some developers set `alt="   "` thinking it satisfies the requirement. The normalizer strips it to empty, so it must be treated as missing.

#### `test_meaningful_text_not_empty`
- **Input:** `"company logo"`
- **Why:** Confirms meaningful alt text is not mistakenly flagged as empty.

---

### Class `TestCheck111Decorative`

#### `test_decorative_with_empty_alt_passes`
- **Function under test:** `_check_1_1_1_decorative(image_data)`
- **Input:** `ImageData(alt="", role="presentation", is_decorative=True)`
- **Why:** `alt=""` on a decorative image is the correct WCAG technique (Technique C9). The combination of empty alt + decorative classification must pass.

#### `test_decorative_with_non_empty_alt_needs_review`
- **Input:** `alt="background decoration"`, `is_decorative=True`
- **Why:** If the classifier thinks the image is decorative but the author provided text alt, it might be misclassified. `NEEDS_REVIEW` is appropriate — a human should verify whether the image truly is decorative.

#### `test_non_decorative_with_empty_alt_fails`
- **Input:** `alt=""`, `is_decorative=False`, `is_informative=True`
- **Why:** An informative image with `alt=""` is incorrectly marked as decorative. This is a WCAG 1.1.1 failure.

---

### Class `TestCheck111MissingAlt`

#### `test_missing_alt_fails`
- **Function under test:** `_check_1_1_1_missing_alt(image_data)`
- **Input:** `ImageData(alt=None)`
- **Why:** `alt=None` means no alt attribute at all — the most severe failure of WCAG 1.1.1. Must produce `FAILED` status.

#### `test_present_alt_passes`
- **Input:** `alt="Product photo"`
- **Why:** Any non-None alt text passes the missing-alt check (content quality is assessed separately).

---

### Class `TestCheck111Informative`

#### `test_generic_alt_fails`
- **Function under test:** `_check_1_1_1_informative(image_data)`
- **Input:** `alt="image"`, `is_informative=True`
- **Why:** Generic alt texts like "image", "photo", "picture" provide no information to screen reader users. They are in the hard-coded generic list.

#### `test_filename_as_alt_fails`
- **Input:** `alt="IMG_0042.jpg"`, `is_informative=True`
- **Why:** CMS-generated images often use the filename as alt text. Filenames (detected by `.jpg`, `.png` suffix patterns) are meaningless to screen reader users.

#### `test_ocr_text_present_in_alt_passes`
- **Input:** `alt="Sale 50% Off"`, `ocr_text="Sale 50% Off"`, `has_text_overlay=True`
- **Why:** When an image contains visible text (detected by OCR), the alt text should contain that text. Cosine similarity between `_norm(alt)` and `_norm(ocr_text)` must exceed the threshold (0.75). This input uses identical strings → similarity = 1.0.

#### `test_ocr_text_missing_from_alt_fails`
- **Input:** `alt="Summer promotion"`, `ocr_text="Sale 50% Off"`, `has_text_overlay=True`
- **Why:** The alt text describes the image conceptually but omits the actual text overlay. Screen reader users miss the specific text. Cosine similarity below 0.75 triggers failure.

---

### Class `TestCheck111Logo`

#### `test_logo_with_company_name_passes`
- **Function under test:** `_check_1_1_1_logo(image_data)`
- **Input:** `is_logo=True`, `alt="Acme Corporation logo"`
- **Why:** A logo with the company name in the alt text satisfies 1.1.1. The check verifies that `alt` contains the organisation name (detected from surrounding context or the classifier).

#### `test_logo_with_generic_alt_fails`
- **Input:** `is_logo=True`, `alt="logo"`
- **Why:** "logo" alone doesn't name the company. Blind users need to know whose logo it is.

---

### Class `TestCheck111Icon`

#### `test_icon_with_aria_label_passes`
- **Function under test:** `_check_1_1_1_icon(image_data)`
- **Input:** `is_icon=True`, `aria_label="Close menu"`, `alt=None`
- **Why:** Decorative icons inside labelled buttons can have `alt=None` if the parent element provides the accessible name via `aria-label`. The function must consider the `aria_label` field as an acceptable alternative.

#### `test_standalone_icon_without_alt_fails`
- **Input:** `is_icon=True`, `alt=None`, `aria_label=None`
- **Why:** A standalone icon image with no text alternative has zero information for screen reader users.

---

### Class `TestCheck412`

#### `test_image_button_without_alt_fails`
- **Function under test:** `_check_4_1_2(image_data)`
- **Input:** `tag="INPUT"`, `type="image"`, `alt=None`
- **Why:** `<input type="image">` is an interactive element (submit button). WCAG 4.1.2 requires Name/Role/Value for all interactive elements. Missing alt on an image button removes the button's accessible name entirely.

#### `test_image_button_with_alt_passes`
- **Input:** `tag="INPUT"`, `type="image"`, `alt="Submit order"`
- **Why:** The alt text provides the accessible name for the button.

---

### Class `TestAltTextAuditorReport`

#### `test_generates_records_for_all_images`
- **Function under test:** `AltTextAuditor.generate_audit_report(images)`
- **Input:** List of 5 `ImageData` objects.
- **Why:** One record per image. Confirms the auditor doesn't silently drop images.

#### `test_overall_status_critical_if_any_critical`
- **Input:** One image with missing alt (`CRITICAL`) among passing images.
- **Why:** The audit report header-level status must reflect the worst finding. If any image is CRITICAL, the overall report is CRITICAL.

#### `test_csv_written_to_output_dir`
- **Why:** The CSV is consumed by the combined image-audit pipeline as an intermediate artifact. If not written, the pipeline fails silently.

---

<div id="6-test_form_auditorpy--wcag-331--332-forms"></div>
## 6. `test_form_auditor.py` — WCAG 3.3.1 / 3.3.2 Forms

**WCAG context:** 3.3.2 requires that every input has a visible label. 3.3.1 requires that error messages are programmatically associated (via `aria-describedby` pointing to an element with `role="alert"` or `aria-live`).

**Technique pattern:** Synthetic `FormInputData` Pydantic objects, no browser. The `_field_appears_required` heuristic is tested independently because it is a pure function with complex branching logic (semantic HTML `required`, `aria-required`, `*` in placeholder, "(required)" in label text).

---

### Class `TestFieldAppearsRequired`

#### `test_html_required_attribute_detected`
- **Function under test:** `_field_appears_required(field)`
- **Input:** `FormInputData(required=True, ...)`
- **Why:** The HTML `required` attribute is the most semantically authoritative signal. Must be detected.

#### `test_aria_required_true_detected`
- **Input:** `aria_required="true"`
- **Why:** Some frameworks use `aria-required="true"` instead of the native attribute (e.g. on a `<div role="textbox">`). Must also be recognised.

#### `test_placeholder_asterisk_detected`
- **Input:** `placeholder="Email *"`
- **Why:** A common (but inaccessible) pattern is to put `*` in the placeholder to indicate required. The heuristic should detect this as a required field signal.

#### `test_label_contains_required_word_detected`
- **Input:** `label_text="Email (required)"`
- **Why:** Some designs put the word "required" in the label text. The heuristic uses a case-insensitive substring match.

#### `test_none_of_the_above_returns_false`
- **Input:** All required-signals absent.
- **Why:** Baseline negative case — a non-required field must not be flagged as required.

---

### Class `TestViolations331`

#### `test_no_error_element_returns_violation`
- **Function under test:** `_violations_331(field)`
- **Input:** `FormInputData(aria_describedby="err1", error_element_id=None, ...)`
- **Why:** `aria-describedby` points to an ID that does not exist in the DOM (the crawler couldn't resolve it). This is a broken association — the error message is not programmatically linked.

#### `test_error_element_without_role_alert_returns_violation`
- **Input:** `error_element_id="err1"`, `error_has_role_alert=False`, `error_has_aria_live=None`
- **Why:** 3.3.1 requires that error containers have `role="alert"` or `aria-live`, so AT announces them automatically when they appear. A plain `<div>` with text that appears dynamically will not be announced.

#### `test_error_element_with_role_alert_passes`
- **Input:** `error_element_id="err1"`, `error_has_role_alert=True`
- **Why:** `role="alert"` implies `aria-live="assertive"`. This is the canonical correct implementation.

#### `test_error_element_with_aria_live_polite_passes`
- **Input:** `error_has_aria_live="polite"`
- **Why:** `aria-live="polite"` is acceptable for non-critical error announcements. Must pass 3.3.1.

#### `test_no_describedby_no_violation_if_field_not_required`
- **Input:** `required=False`, `aria_required=None`, no `aria-describedby`.
- **Why:** 3.3.1 only applies when there is an error state to communicate. A non-required field with no error association is not a violation.

---

### Class `TestViolations332`

#### `test_no_label_at_all_fails`
- **Function under test:** `_violations_332(field)`
- **Input:** `has_any_label=False`, `aria_label=None`, `placeholder=None`
- **Why:** The most severe 3.3.2 violation — completely unlabelled input. Screen reader announces only the input type ("text, edit field") with no context.

#### `test_placeholder_only_fails`
- **Input:** `placeholder="Enter email"`, `has_any_label=False`
- **Why:** Placeholder text is not a label — it disappears once the user starts typing, leaving the field unlabelled. Cognitive accessibility issue.

#### `test_explicit_label_passes`
- **Input:** `has_explicit_label=True`, `label_text="Email address"`
- **Why:** `<label for="id">` is the primary accessible labelling technique. Must pass.

#### `test_wrapping_label_passes`
- **Input:** `has_wrapping_label=True`
- **Why:** `<label><input></label>` (implicit label) is equally valid. Must pass.

#### `test_aria_label_passes`
- **Input:** `aria_label="Email address"`
- **Why:** `aria-label` provides a programmatic label without a visible `<label>` element. Acceptable for icon buttons and inputs where visual context makes the label redundant.

#### `test_aria_labelledby_passes`
- **Input:** `aria_labelledby="heading-id"`
- **Why:** Another valid ARIA labelling pattern — references the text of another element.

---

### Class `TestFormAccessibilityAuditorReport`

#### `test_records_produced_for_all_fields`
- **Function under test:** `FormAccessibilityAuditor.generate_audit_report(fields)`
- **Input:** 6 `FormInputData` objects with varying label/error configurations.
- **Why:** One record per field. The auditor must not drop fields silently.

#### `test_statuses_correct_for_mixed_inputs`
- **Input:** Mix of labelled/unlabelled and error-associated/not-associated fields.
- **Why:** End-to-end correctness check — verifies the specific PASS/FAIL status for each field based on the combination of 3.3.1 and 3.3.2 rules.

#### `test_overall_status_fail_if_any_fail`
- **Why:** The record-level `overall_status` must be `FAILED` if either 3.3.1 or 3.3.2 fails. The auditor uses logical OR across all sub-rules.

#### `test_csv_written`
- **Why:** Required for pipeline continuity.

---

### Class `TestFormAccessibilityAuditorSummarize`

#### `test_total_fields_count`
- **Function under test:** `FormAccessibilityAuditor.summarize(records)`
- **Input:** Pre-built record dicts with known `wcag_3_3_1_status` and `wcag_3_3_2_status` fields.
- **Why:** Verifies the `total_fields` key counts every record regardless of status.

#### `test_331_failed_count`
- **Why:** The summary is used by the combined pipeline to populate the dashboard stats card. Wrong counts mislead developers about the severity of violations.

#### `test_332_failed_count`
- **Why:** Same reasoning.

#### `test_pass_rate_calculation`
- **Input:** 4 records with 2 passing both rules, 2 failing at least one.
- **Why:** Pass rate = (fields passing all rules) / total. Validates the formula, including correct handling of fields that fail only one of the two rules.

---

### Class `TestFormAuditorEdgeCases`

#### `test_empty_form_list_produces_no_records`
- **Input:** `[]`
- **Why:** Pages without forms should produce an empty list and not crash.

#### `test_submit_button_excluded`
- **Input:** `FormInputData(type="submit")`
- **Why:** Submit buttons don't need labels (they are already buttons) and don't have error states. The auditor must exclude submit/button/reset/image input types from form field analysis.

#### `test_hidden_input_excluded`
- **Input:** `FormInputData(type="hidden")`
- **Why:** Hidden inputs are not visible to users or AT. Never labelled, never error-associated. Excluded from the crawler JS (`input:not([type="hidden"])`), so this tests that any that slip through are filtered in the auditor.

---

<div id="7-test_label_in_name_auditorpy--wcag-253-label-in-name"></div>
## 7. `test_label_in_name_auditor.py` — WCAG 2.5.3 Label in Name

**WCAG context:** WCAG 2.5.3 requires that when an interactive element has a visible text label, the accessible name (from `aria-label`, `aria-labelledby`, or button text) must *contain* that visible label verbatim. This ensures voice-control users can activate elements by speaking the visible text.

**Technique pattern:** Pure function tests for `_normalize` and `_has_word_chars`, then synthetic `LabelData` objects for the main checker.

---

### Class `TestNormalize`

#### `test_lowercases_and_strips_punctuation`
- **Function under test:** `_normalize(text)`
- **Input:** `"Search!"`
- **Why:** Normalization must be identical for both the accessible name and the visible label to enable substring comparison. Punctuation and case differences between `aria-label="Search"` and visible `"Search!"` must not cause false failures.

#### `test_collapses_whitespace`
- **Input:** `"Sign  In"` (double space)
- **Why:** Multiple spaces between words in visible labels (e.g. from CSS letter-spacing) should not prevent a match.

#### `test_empty_string_returns_empty`
- **Why:** Guard against normalizing `None`-derived empty strings.

---

### Class `TestHasWordChars`

#### `test_word_characters_returns_true`
- **Function under test:** `_has_word_chars(text)`
- **Input:** `"Search"`
- **Why:** The helper gates the 2.5.3 check — if the visible label has no word characters (e.g. it's purely an icon or a symbol), the rule does not apply (N/A). Text with word chars must trigger the check.

#### `test_empty_string_returns_false`
- **Why:** An empty visible label means the element is probably icon-only. N/A.

#### `test_only_symbols_returns_false`
- **Input:** `"→"`
- **Why:** Arrow/icon symbols are not word characters. Elements whose visible label is purely symbolic are exempt from 2.5.3.

---

### Class `TestCheck253NA`

#### `test_no_visible_label_returns_na`
- **Function under test:** `_check_253(label_data)`
- **Input:** `LabelData(visible_label=None, accessible_name="Submit")`
- **Why:** N/A means the rule doesn't apply — there is no visible text label to match against. The function must return `"N/A"` to avoid treating elements without visible labels as violations.

#### `test_icon_only_button_returns_na`
- **Input:** `visible_label="★"` (pure symbol, `_has_word_chars` → False)
- **Why:** Icon-only buttons (hamburger menus, star ratings) have no words in their visible label. Voice control users speak words, not symbols — 2.5.3 does not apply.

#### `test_no_accessible_name_returns_na`
- **Input:** `accessible_name=None`, `visible_label="Search"`
- **Why:** Cannot check label-in-name if there is no accessible name to compare against. This is a 4.1.2 violation (missing name/role/value), not a 2.5.3 violation. The function returns N/A to avoid double-counting.

---

### Class `TestCheck253Failed`

#### `test_accessible_name_does_not_contain_visible_label_fails`
- **Function under test:** `_check_253(label_data)`
- **Input:** `visible_label="Search"`, `accessible_name="Find content"`
- **Why:** "Find content" does not contain the substring "search" (after normalization). Voice control users who say "search" cannot activate this button. Direct failure case.

#### `test_mismatch_due_to_aria_label_override_fails`
- **Input:** `accessible_name="Submit form"`, `visible_label="Send"`
- **Why:** Developer overrode the visible "Send" label with `aria-label="Submit form"`. The visible label "send" is not a substring of "submit form". Classic 2.5.3 failure pattern from ARIA misuse.

#### `test_case_difference_alone_does_not_fail`
- **Input:** `accessible_name="SEARCH"`, `visible_label="search"`
- **Why:** Normalization lowercases both strings before comparison. Case-only differences must not trigger a failure — voice control is case-insensitive.

---

### Class `TestCheck253Passed`

#### `test_accessible_name_contains_visible_label_passes`
- **Function under test:** `_check_253(label_data)`
- **Input:** `accessible_name="Search this site"`, `visible_label="Search"`
- **Why:** The accessible name contains the visible label text. A voice control user saying "Search" can activate this button. Classic 2.5.3 pass.

#### `test_exact_match_passes`
- **Input:** `accessible_name="Search"`, `visible_label="Search"`
- **Why:** Identity — the simplest pass case.

#### `test_accessible_name_starts_with_visible_label_passes`
- **Input:** `accessible_name="Search results"`, `visible_label="Search"`
- **Why:** WCAG 2.5.3 success technique G208 requires the accessible name to *start with* the visible label text. Tests that the substring check covers the start-of-string position.

---

### Class `TestLabelInNameAuditor`

#### `test_records_produced_for_all_elements`
- **Function under test:** `LabelInNameAuditor.generate_audit_report(labels)`
- **Input:** List of 4 `LabelData` objects.
- **Why:** One record per interactive element.

#### `test_failed_records_have_violation_message`
- **Input:** `LabelData` where visible label is not contained in accessible name.
- **Why:** The `wcag_2_5_3_violation` field must be non-empty for failures so the frontend can display remediation guidance.

#### `test_na_records_have_empty_violation`
- **Why:** N/A records must not generate a violation message — they should not appear in the Violations tab.

---

### Class `TestLabelInNameSummarize`

#### `test_total_elements`
- **Function under test:** `LabelInNameAuditor.summarize(records)`
- **Why:** Total count includes N/A records.

#### `test_checked_excludes_na`
- **Why:** The denominator for pass rate should be only the elements where the rule actually applied. N/A exclusion makes the pass rate meaningful.

#### `test_pass_rate_correct`
- **Input:** 3 checked elements, 2 passing.
- **Why:** `2/3 * 100 = 66.7%`. Validates the rounding and division.

---

<div id="8-test_target_size_auditorpy--wcag-258-target-size"></div>
## 8. `test_target_size_auditor.py` — WCAG 2.5.8 Target Size

**WCAG context:** WCAG 2.5.8 requires that interactive elements (buttons, links, etc.) have a minimum rendered size of 24×24 CSS px, with exceptions for inline text links and UA-controlled widgets (native checkboxes/radios).

**Technique pattern:** Synthetic `TargetSizeData` Pydantic objects via `make_item(**kwargs)` factory. No browser. The factory defaults to a 32×32 passing button, so tests override only the fields relevant to the specific assertion. This is the **minimal deviation pattern** — changing one field at a time to isolate the cause of each status change.

---

### Class `TestCheck258Exceptions`

#### `test_inline_exception_returns_na`
- **Function under test:** `_check_258(item)`
- **Input:** `is_inline_exception=True`, `rendered_width_px=10, rendered_height_px=10`
- **Why `is_inline_exception` with tiny size:** Verifies that the exception applies even when the element is smaller than 24px. The size doesn't matter if the exception is active — the rule is inapplicable regardless.
- **Why `"E1"` in message:** Exception codes (E1 = inline link, E4 = UA-controlled) are documented in the WCAG 2.5.8 understanding document. Including them in the violation message lets developers cross-reference the standard directly.

#### `test_ua_controlled_exception_returns_na`
- **Input:** `is_ua_controlled_exception=True`, tiny dimensions.
- **Why:** Native checkboxes and radios rendered by the browser cannot be resized by the developer (without `appearance: none`). Their size is determined by the OS/browser. WCAG 2.5.8 exception 4 exempts them.
- **Why `"E4"` code:** Matches the exception numbering in the WCAG 2.5.8 understanding doc.

#### `test_inline_exception_takes_precedence_over_ua`
- **Input:** Both `is_inline_exception=True` AND `is_ua_controlled_exception=True`.
- **Why:** Tests the priority order when multiple exceptions apply simultaneously. The result must still be N/A (either exception is sufficient). Also validates that the OR logic doesn't cause an exception to be ignored.

#### `test_no_exception_with_large_size_passes`
- **Input:** No exceptions, 48×48 element.
- **Why:** Confirms that large elements with no exceptions pass cleanly — the exception-checking code path doesn't accidentally interfere with passing elements.

---

### Class `TestCheck258SizeCheck`

#### `test_exactly_24x24_passes`
- **Input:** `rendered_width_px=24.0, rendered_height_px=24.0`
- **Why:** The WCAG 2.5.8 threshold is **24 CSS px**, and the specification uses `≥ 24`. At exactly 24×24, the element must pass. This boundary test catches an off-by-one error where `> 24` instead of `>= 24` is used.

#### `test_above_threshold_passes`
- **Input:** 44×44 — the iOS Human Interface Guidelines' recommended touch target size.
- **Why:** A common real-world passing case. Validates that well-sized targets are not incorrectly flagged.

#### `test_width_below_threshold_fails`
- **Input:** `rendered_width_px=20.0, rendered_height_px=30.0`
- **Why:** Width failure in isolation. Verifies that width and height are checked independently (an element that is tall enough but too narrow must still fail).
- **Why assert "width" in message:** The violation message must identify which dimension is too small so the developer knows whether to increase width, height, or both.

#### `test_height_below_threshold_fails`
- **Input:** Width OK, height failing.
- **Why:** Mirror of the width test. Independently validates the height dimension check.

#### `test_both_below_threshold_mentions_both`
- **Input:** Both dimensions below 24px.
- **Why:** When both dimensions fail, the message must mention both. A message that says only "width" when height also fails is misleading — the developer would fix width and then discover the height issue separately.

#### `test_zero_size_fails`
- **Input:** `0.0 × 0.0`
- **Why:** The extreme lower bound. A zero-size element is completely untappable. Also validates that no division-by-zero errors occur in the check function.

#### `test_just_below_threshold_fails`
- **Input:** `rendered_width_px=23.9, rendered_height_px=24.0`
- **Why:** Sub-pixel precision — 23.9 is clearly below 24 but might pass a `round()` or integer comparison. The check must use floating-point comparison: `23.9 < 24.0` → fail.

#### `test_violation_message_includes_wcag_reference`
- **Input:** Failing element.
- **Why:** Every violation message must contain the WCAG criterion number ("2.5.8") so the developer can look up the criterion. Without this, the message is harder to triage.

#### `test_violation_message_includes_dimensions`
- **Input:** 16×12 element.
- **Why:** The violation message must state the actual measured dimensions so the developer knows by how much the target needs to grow. "16 px wide, 12 px tall" is actionable; "too small" is not.

#### `test_passed_returns_empty_violation`
- **Why:** When status is PASSED, the violation message must be an empty string. Any non-empty violation on a passing element is a bug that would cause the frontend to show violation text alongside a green "pass" badge.

---

### Class `TestTargetSizeAuditorReport`

#### `test_record_count_matches_input`
- **Function under test:** `TargetSizeAuditor.generate_audit_report(items)`
- **Input:** 5 items.
- **Why:** One record per element. Auditor must not drop or duplicate records.

#### `test_csv_has_correct_columns`
- **Why:** The CSV schema is a contract between the auditor and the `combined/findings.py` converter. If a column is renamed or added, the converter must be updated. This test pins the schema as a regression guard.
- **Technique:** Reads the CSV header with `csv.DictReader` and asserts exact column list equality (order matters because some downstream tools process columns positionally).

#### `test_summary_row_present_in_csv`
- **Why:** The CSV always has a final summary row (`page_url == "── SUMMARY ──"`). This row is consumed by the CSV viewer in the frontend's Image Visualiser tab for quick stats. Absence would break that view.

#### `test_html_snippet_truncated_to_400`
- **Input:** `html_snippet` of 500+ characters.
- **Why:** The crawler JS caps snippets at 400 chars (`outerHTML.slice(0, 400)`). The auditor must enforce the same cap to prevent database/storage blowup from large SVG or table elements.

#### `test_mixed_statuses`
- **Input:** One PASSED, one FAILED, one N/A (inline exception).
- **Why:** Integration test verifying all three status paths in a single call. Statuses are keyed by `element_index` to avoid positional assumptions.

#### `test_output_dir_created_if_missing`
- **Input:** Non-existent nested directory path.
- **Why:** The auditor is responsible for creating its output directory. If it doesn't, the first file write would raise `FileNotFoundError`. Tests that `Path(out).mkdir(parents=True, exist_ok=True)` is called.

---

### Class `TestTargetSizeAuditorSummarize`

#### `test_checked_excludes_na`
- **Function under test:** `TargetSizeAuditor.summarize(records)`
- **Why:** The "checked" count is the denominator for pass rate. N/A records (exempted elements) are not checked — including them would artificially inflate the denominator and lower the apparent violation rate.

#### `test_zero_checked_no_division_error`
- **Input:** All records are N/A.
- **Why:** `checked == 0` would cause `ZeroDivisionError` if pass rate is computed as `passed / checked`. The function must return `0` (not `100%`, not raise) for this edge case.

#### `test_failed_by_tag_counts`
- **Input:** Mix of FAILED A and BUTTON tags.
- **Why:** The `failed_by_tag` breakdown tells developers which element types have the most target-size violations. If mostly `A` tags fail, the fix is CSS on links; if mostly `BUTTON`, it's button styling.

#### `test_all_keys_present`
- **Why:** The summarize output is consumed by the combined result pipeline without `.get()` guards. A missing key would raise `KeyError` at runtime. This test pins all required keys.

---

<div id="9-test_pause_stop_hide_auditorpy--wcag-222-pausestophide"></div>
## 9. `test_pause_stop_hide_auditor.py` — WCAG 2.2.2 Pause/Stop/Hide

**WCAG context:** WCAG 2.2.2 requires that automatically-playing moving content lasting more than 5 seconds can be paused, stopped, or hidden. This covers videos, carousels, GIFs, CSS animations, and deprecated `<marquee>`/`<blink>` elements.

**Technique pattern:** Synthetic `MovingContentData` Pydantic objects via `make_item(**kwargs)`. The rule is implemented as a three-gate decision tree (`starts_automatically` → duration/loops → `has_mechanism`). Tests are organised into four classes mirroring the gate structure, enabling independent verification of each decision point.

**Why gate-based test organisation:** The rule has seven fields that interact. Testing the entire space exhaustively would require 2^7 = 128 cases. Gate isolation reduces this to ~4 cases per gate while still covering the most common real-world failure modes.

---

### Class `TestCheck222Gate1StartsAutomatically`

#### `test_not_starting_automatically_passes`
- **Function under test:** `_check_222(item)`
- **Input:** `starts_automatically=False, has_mechanism=False`
- **Why `has_mechanism=False` with starts_automatically=False:** Deliberately uses a "would-fail" mechanism value. If the function incorrectly checks mechanism before the `starts_automatically` gate, it would fail. This validates the gate ordering.

#### `test_not_starting_automatically_ignores_mechanism_flag`
- **Input:** Long duration (60s) + no mechanism, but not auto-starting.
- **Why:** A 60s video that the user manually plays is fully compliant. WCAG 2.2.2 only applies to auto-started content. Tests that duration and mechanism flags are ignored when the first gate is clear.

#### `test_starting_automatically_proceeds_to_further_gates`
- **Input:** `starts_automatically=True, duration_seconds=60.0, has_mechanism=False`
- **Why:** With auto-start, long duration, and no mechanism, all subsequent gates fail. Validates that the function correctly applies all subsequent logic after passing Gate 1.

---

### Class `TestCheck222Gate2Duration`

#### `test_duration_under_5s_passes`
- **Input:** `duration_seconds=3.0`
- **Why:** 3s is well below the 5s threshold. Auto-started content lasting ≤5s does not need a pause mechanism (it finishes quickly enough). WCAG 2.2.2 explicitly states "more than five seconds".

#### `test_duration_exactly_5s_passes`
- **Input:** `duration_seconds=5.0`
- **Why:** Boundary test — exactly 5 seconds must pass (`<= 5` not `< 5`). A strict `<` comparison would incorrectly flag 5.0s content.

#### `test_duration_just_over_5s_requires_mechanism`
- **Input:** `duration_seconds=5.01`
- **Why:** Just beyond the threshold with no mechanism → must fail. Validates floating-point comparison accuracy at the boundary.

#### `test_duration_minus_one_is_infinite_requires_mechanism`
- **Input:** `duration_seconds=-1`
- **Why:** The crawler uses `-1` as a sentinel value for "infinite duration" (streaming video, infinite CSS animations). The gate must treat `-1` as "duration > 5" unconditionally.

#### `test_iteration_count_infinite_requires_mechanism`
- **Input:** `animation_iteration_count="infinite"`, `duration_seconds=2.0`
- **Why:** A CSS animation with `animation-iteration-count: infinite` loops forever regardless of the per-iteration duration. Even if each iteration is 2s, the content plays indefinitely. The gate must check `animation_iteration_count` separately from `duration_seconds`.

#### `test_loops_true_requires_mechanism_regardless_of_duration`
- **Input:** `duration_seconds=3.0, loops=True`
- **Why:** `loops=True` means the content repeats indefinitely. Even a 3s video that loops exceeds 5 seconds total (after the first repetition). The `loops` flag is a separate check from raw duration.

#### `test_duration_none_is_treated_as_applicable`
- **Input:** `duration_seconds=None`
- **Why:** When the crawler cannot determine the duration (e.g. a CSS animation with `duration` in a class not inlined), it uses `None`. The function must conservatively treat unknown duration as applicable ("when in doubt, require a mechanism"). This avoids false negatives for inaccessible content.

#### `test_short_looping_video_fails`
- **Input:** `duration_seconds=2.0, loops=True, content_type="video_autoplay"`
- **Why:** A 2s GIF or video that loops is visually equivalent to infinite content. Common pattern (looping hero videos, animated logos). Must fail despite the short per-loop duration.

---

### Class `TestCheck222Gate3Mechanism`

#### `test_has_mechanism_passes`
- **Input:** `has_mechanism=True`
- **Why:** The top-level flag that gates the final check. A compliant pause/stop/hide mechanism must produce a pass verdict.

#### `test_video_controls_constitutes_mechanism`
- **Input:** `has_video_controls=True, has_mechanism=True`
- **Why:** The HTML `controls` attribute on `<video>` provides a native browser pause button. This is a common correct implementation. Tests that the auditor recognises it.

#### `test_pause_button_constitutes_mechanism`
- **Input:** `has_pause_button=True, content_type="carousel_autoplay", has_mechanism=True`
- **Why:** Carousels cannot use the `controls` attribute (they're `<div>` based). A bespoke pause button detected by the crawler (via `aria-label`, button text, etc.) must also satisfy the requirement.

#### `test_no_mechanism_fails`
- **Input:** Long duration, `has_mechanism=False`.
- **Why:** The direct failure case — content starts automatically, runs long, and has no user-accessible control.

---

### Class `TestCheck222ViolationMessage`

#### `test_message_starts_with_wcag_number`
- **Why:** All violation messages in ka11y are prefixed with the WCAG criterion number (`"2.2.2: ..."`). This allows the frontend to group and sort by criterion without parsing unstructured text.

#### `test_message_contains_content_type_label_for_video`
- **Input:** `content_type="video_autoplay"`
- **Why:** The violation message must tell the developer *what* type of content is failing — "Video with autoplay" is more actionable than a raw content_type key. The label mapping (`video_autoplay → "Video with autoplay"`) is tested here.

#### `test_message_shows_loops_indefinitely_for_infinite_duration`
- **Input:** `duration_seconds=-1`
- **Why:** "loops indefinitely" in the message is more actionable than "-1 s". The function must translate the -1 sentinel into a human-readable phrase.

#### `test_message_shows_duration_in_seconds_for_finite_duration`
- **Input:** `duration_seconds=12.5`
- **Why:** For finite durations, showing "12.5 s" helps the developer understand why the rule triggered (vs. content that barely exceeds the 5s threshold).

#### `test_message_shows_unknown_duration_when_none`
- **Input:** `duration_seconds=None`
- **Why:** When duration is unknown, the message must say "unknown duration" (not "None s" or crash). Ensures the sentinel value is handled in the message formatter, not just in the gate logic.

#### `test_message_contains_remediation_hint_for_video`
- **Why:** The violation message is shown to developers in the frontend's Violations tab. It must include actionable guidance — for video, the hint is "add the `controls` attribute or a visible pause button".

#### `test_message_contains_remediation_hint_for_marquee`
- **Input:** `content_type="marquee_element"`
- **Why:** `<marquee>` is a deprecated HTML element. The remediation hint should say to remove it and replace with CSS animation + pause button, not just "add a mechanism".

#### `test_unknown_content_type_uses_fallback_label_and_hint`
- **Input:** `content_type="custom_widget"`
- **Why:** Future crawlers may detect new content types. The violation message must not crash for unknown types — it must fall back to using the raw `content_type` string as the label and a generic mechanism hint.

---

### Class `TestPauseStopHideAuditorReport`

#### `test_correct_statuses` (integration)
- **Input:** 5-item mixed list — passed video with controls, failed carousel, passed non-auto CSS animation, passed short animation, failed marquee.
- **Why:** Verifies the full five-item pipeline in one call, checking the exact status sequence `["PASSED", "FAILED", "PASSED", "PASSED", "FAILED"]`. This catches cross-item contamination bugs (e.g. shared state between records).

#### `test_overall_status_mirrors_wcag_status`
- **Why:** For this rule, `overall_status` is always identical to `wcag_2_2_2_status` (there is only one sub-rule). The test ensures the auditor copies rather than recomputes the status.

#### `test_axe_would_catch_preserved`
- **Input:** Records 1 (carousel, `axe_would_catch=False`) and 4 (marquee, `axe_would_catch=True`).
- **Why:** The `axe_would_catch` field distinguishes findings that axe-core would also detect from those unique to ka11y's crawler. This is used by the dashboard to quantify ka11y's unique coverage ("X violations that axe would have missed"). If this field is dropped, the coverage stats are wrong.

#### `test_csv_has_correct_columns`
- **Technique:** Uses `PauseStopHideAuditor.CSV_FIELDS` constant and asserts it's a subset of the CSV header.
- **Why subset (not equality):** The summary row adds extra columns for the aggregated stats. Subset check allows for summary-row columns without requiring them in the field-level data.

#### `test_gif_with_no_mechanism_fails`
- **Input:** `content_type="animated_gif"`, `duration_seconds=-1, loops=True, has_mechanism=False`
- **Why:** Animated GIFs are a common WCAG 2.2.2 failure — they loop indefinitely and have no native pause control. This content-type-specific test validates that the auditor covers GIFs, not just `<video>` elements.

#### `test_marquee_always_fails`
- **Input:** `content_type="marquee_element"`, `axe_would_catch=True`
- **Why:** `<marquee>` is inherently non-compliant (it loops indefinitely, has no pause mechanism, and is deprecated). Also tests with `axe_would_catch=True` since axe-core does flag marquee. The auditor must still record the failure (for completeness) even though axe would catch it.

---

### Class `TestPauseStopHideAuditorSummarize`

#### `test_axe_would_miss_count`
- **Function under test:** `PauseStopHideAuditor.summarize(records)`
- **Input:** 4 records with `axe_would_catch=False`, 1 with `True`.
- **Why:** `axe_would_miss` = count of elements where `axe_would_catch=False`. This is a unique metric that quantifies the value ka11y adds over running axe-core alone. An incorrect count here would misrepresent ka11y's unique detection capability.

#### `test_failed_by_type_breakdown`
- **Input:** 3 failed records with different `content_type` values.
- **Why:** The breakdown by type tells developers which category of moving content is most problematic. "3 carousels, 1 video" suggests carousel code needs more attention than video embeds.

#### `test_passed_by_type_breakdown`
- **Why:** The passing breakdown confirms which content types are generally compliant. Used for reporting completeness — developers can see "videos are compliant, carousels are not."

#### `test_empty_records_returns_zero_counts`
- **Why:** Pages without moving content should produce a summary with all-zero counts and empty type breakdowns, not a `KeyError` or `ZeroDivisionError`.

---

### Class `TestContentTypeSpecificBehavior`

#### `test_blink_element_fails_with_no_mechanism`
- **Input:** `content_type="blink_element"`, `tag="BLINK"`
- **Why:** `<blink>` is another deprecated element that loops indefinitely. Tests that the auditor covers it specifically, not just the common types. Also has `axe_would_catch=True` — axe flags blink elements as well.

#### `test_css_animation_with_pause_button_passes`
- **Input:** Full CSS animation metadata: `animation_name="slide"`, `animation_duration_seconds=8.0`, `animation_iteration_count="infinite"`, but with `has_pause_button=True, has_mechanism=True`.
- **Why:** Real-world compliant case — many modern hero sections use CSS animations with a visible pause button. Tests the full field set (animation_name, animation_duration_seconds, animation_iteration_count) are consumed correctly and don't override the mechanism flag.

#### `test_animation_fields_preserved_in_record`
- **Input:** CSS animation with `animation_name="bounce"`, `animation_duration_seconds=3.0`, `animation_iteration_count="infinite"`.
- **Why:** These three fields are CSS-animation-specific metadata stored in the audit record for developer debugging. They must not be lost during `generate_audit_report`. Validates the record dict includes all input fields verbatim.

#### `test_multiple_items_from_same_page`
- **Input:** 4 items all with the same `page_url`.
- **Why:** Tests that the auditor handles multiple moving content elements on the same page (common for pages with hero + carousel + background video). Records must not be merged or de-duplicated by URL.

---

*End of test case documentation.*
