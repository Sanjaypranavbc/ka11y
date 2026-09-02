# Python Rule Accuracy Review

**Scope:** `ka11y-python` accessibility rule logic, as it runs on the `production` branch today.
**Method:** Traced the real request path (`api/v1/combined/stages.py::_run_python_stages` → `_stage_image_audit` / `_stage_media_audit_universal`) to confirm which modules actually produce the findings in a live audit report, then read every rule file in full and verified the highest-impact claims by hand (dead-attribute greps, classifier value traces, threshold math).

**Update — fixes applied.** Every item below has been triaged; status is marked inline (✅ Fixed / 🔁 Revised / ⏸ Left as-is / ⏭ Deferred). See **[Fix Log](#fix-log)** at the bottom for the full status table, verification notes, and three cases where deeper investigation during implementation showed the *originally diagnosed* fix would itself have made accuracy worse — those are called out explicitly rather than silently applied. All changes are covered by the existing test suite (361 passing, plus 27 new/updated test cases); 4 pre-existing, unrelated test failures on `production` were confirmed via `git stash` to predate this work.

---

## 0. Read this first: half the "rule engine" in this repo never runs

Before going rule-by-rule, the single most consequential finding: **the codebase contains two parallel implementations of WCAG 1.1.1 / 1.4.3 / 1.4.5 / 1.4.6 / 1.4.11, and the one described in `ka11y-docs` is not the one that executes.**

| | "Unified Pipeline" (`accessibility/pipeline/**`) | Legacy auditor (actually live) |
|---|---|---|
| Files | `pipeline_stage.py`, `decisions/engine.py`, `decisions/policies/policy_*.py`, `router/rule_target_router.py`, `formatters/evidence_formatter.py`, `extractors/*.py` | `rules/non_text/alttext.py`, `rules/non_text/contrast_analyser.py`, `text_detector/text_detector.py`, `rules/media/*.py` |
| Docs say | "Full" coverage engine for 1.1.1/1.3.1/1.4.3/1.4.5/1.4.6/1.4.11 (`ka11y-docs/rules/overview.mdx`, `coverage-matrix.mdx`) | Not mentioned |
| Actually wired into `_run_python_stages`? | **No.** `stages.py` line ~715: *"The pipeline stage (`_run_pipeline_stage`) has been removed — it is out of scope for this run configuration."* `stage_coros` only contains `_stage_image_audit` and `_stage_media_audit_universal`. | **Yes** — this is what every combined audit, PDF/email report, and the `/rule` single-rule tester actually calls. |
| Unit tests | `test_decision_engine.py`, `test_contrast_engine.py` — pass, but exercise only the dead module in isolation | `test_alt_text_auditor.py`, `test_media_auditor.py` — exercise the live path |
| Side effect | `crawler/universal_page.py` still runs `ElementContextExtractor`/`SemanticRelationshipEngine` to build `pipeline_pages` for every crawled page — CPU and browser time spent building data that is never consumed. | — |

**Why this matters for "rule accuracy":** every gap the docs *don't* mention (because they describe the dead engine as "Full") is actually present in production, and several bugs found inside the dead engine (e.g. `policy_1_4_11.py` — see below) are irrelevant to real audits but will resurface if anyone "fixes" and re-wires that module without knowing the live path has since diverged.

**Recommended fix:** pick one.
- **(A) Delete** `accessibility/pipeline/` (policies, engine, router, formatters, and the extractors/analyzers that only feed it) and its isolated tests, and correct `ka11y-docs/rules/overview.mdx` + `coverage-matrix.mdx` to describe `alttext.py`/`media_auditor.py` as the actual engines. Lowest risk, matches what ships today.
- **(B) Finish and re-wire it** as the real engine (it has a cleaner architecture — typed `RuleVerdict`, explicit `PolicyError` semantics) — but only after fixing the bugs listed in §2 below, and then retire the duplicate logic in `alttext.py` so there's a single source of truth.

Either way, **do not leave both alive** — right now a developer reading `coverage-matrix.mdx` or `policy_1_4_3.py` to understand "how does ka11y check contrast" will learn the wrong thing.

---

## 1. WCAG 1.1.1 — Non-text Content (`rules/non_text/alttext.py`, `classifier/classifier.py`)

### 1.1 Decorative check skips `aria-hidden`/`role="presentation"` whenever `alt` is non-empty — false FAIL
**File:** `alttext.py`, `generate_audit_report` (~line 1001-1011) vs. `classifier.py` STEP 0 (~line 252-260)
`classifier.py` classifies an element as `decorative/presentational` purely from `aria-hidden="true"` or `role="presentation"/"none"`, independent of what `alt` says. But `generate_audit_report` only routes to the aria-hidden-aware check when `alt_text is None`; if `alt` is *non-empty*, it instead calls `_check_1_1_1_decorative(alt_text)`, which only checks `alt == ""`.
**Concrete failure:** `<img aria-hidden="true" alt="Company logo">` → classifier says decorative/presentational, but the report calls `_check_1_1_1_decorative("Company logo")` → **FAIL** *"Decorative image must have alt="" (empty). Found: 'Company logo'"* — wrong, because `aria-hidden` already removes the whole element (and its `alt`) from the accessibility tree, so this is a compliant no-op image, not a violation.
**Fix:** route on the classifier's `decorative/presentational` sub_type first, regardless of whether `alt` is empty or not.

### 1.2 `_check_1_1_1_button` accepts any 3+ character non-numeric string as a valid action description
**File:** `alttext.py:610-621`
`if len(norm) >= 3 and not norm.isdigit(): return True` — no check that the text is a real word or names an action.
**Concrete failure:** functional button image with `alt="xyz"` → PASS *"Button alt is non-empty... (verify it describes the button action)"*.
**Fix:** require the token to match a dictionary/word-shape check, or at minimum reuse the same word-quality heuristic already used elsewhere in the file for icon alt text.

### 1.3 `_SOCIAL_BRAND_NAMES` whitelist includes the bare letter "x" — masks a common bad close-icon label
**File:** `alttext.py:73-92`, consumed at `_check_1_1_1_icon` (~561-565)
The brand-name shortcut (meant for X/Twitter icons) includes `"x"`. But `alt="X"` is also one of the most common *wrong* labels for a generic modal "close" icon.
**Concrete failure:** `<img alt="X">` on a close button (functional/icons) → PASS *"Icon alt names the linked service: 'X'"*. Without the shortcut, `len("x")=1 < MIN_ICON_ALT_LENGTH` would correctly fail it.
**Fix:** only apply the brand-name shortcut when the image is also classified as a social-share/follow icon (e.g. src/class contains `twitter`/`x.com`/`social`), not for every icon on the page.

### 1.4 OCR-vs-alt mismatch check silently passes short CJK text
**File:** `alttext.py:491` — `ocr_words = [w for w in norm_ocr.split() if len(w) >= 3]`
The 3-character floor is Latin-script-calibrated; complete Japanese/CJK words are frequently 1-2 characters, and the ASCII-only `abbr_words` rescue regex doesn't help.
**Concrete failure:** baked-in Japanese text "検索" (2 chars, "Search") with an unrelated `alt="トップ"` → the OCR token is filtered out entirely → *"PASS — OCR tokens too short to match; alt is non-empty"* instead of flagging the mismatch for review.
**Fix:** use a language-aware minimum (character count for CJK scripts, not word-length).

### 1.5 CSS-background exemption asserts equivalence instead of checking it
**File:** `alttext.py:416-439` (`_context_exemption`)
Any CSS background image without its own accessible name is passed with *"conveys no information that is not already available as text"* — a claim, not a verification.
**Concrete failure:** `<div style="background-image:url(sales-infographic.png)">` with no nearby text conveying the same data → unconditional PASS even though the infographic may be the only place that information appears.
**Fix:** downgrade to `needs_review` instead of `PASS` when no such text can be located nearby (the doc's own "Known limitations" note for F3 already flags the related Node check as heuristic-only — this Python path should be consistent, not silently optimistic).

### 1.6 Classifier's `ico` icon keyword is too short and matches unrelated words
**File:** `classifier/classifier.py:52-64` (`_ICON_KEYWORDS`)
`"ico"` (3 chars) is a substring of ordinary words like `silicon`, `unicorn`, `reciprocal`. Any image whose `src`/`class` happens to contain one of these gets misclassified as an icon.
**Concrete failure:** `src="silicon-valley-photo.jpg"` → `_is_icon` returns `True` via the `"ico" in src_l` keyword match → an informative photograph is routed through icon-specific (looser) 1.1.1 logic instead of standard informative-image logic.
**Fix:** drop the bare `"ico"` token from `_ICON_KEYWORDS`, or require a word boundary (`\bico\b`) / require it in combination with a size/context signal.

### 1.7 `_is_button` exception handler defaults to "not a button" with no review flag
**File:** `classifier/classifier.py:426-449`
`except Exception: return False`. If the Playwright `evaluate()` call throws (detached node, navigation race, etc.), the element silently loses its `functional/buttons` classification.
**Concrete failure:** a button image with a genuinely missing accessible name, whose classification evaluate() throws → never gets `sub_type="buttons"` → `_check_4_1_2` (which only runs for `classification=="functional"`) never executes → reported as `N/A` instead of a 4.1.2 violation.
**Fix:** on exception, mark the element for `needs_review` rather than silently downgrading to "not interactive."

### 1.8 Decorative FP follow-up — `_check_1_1_1_decorative` hard-FAILs on names it can't hard-FAIL on
**File:** `alttext.py`, `_check_1_1_1_decorative` (~353) + decorative branch of `generate_audit_report` (~1073-1094)
§1.1's fix routes `aria-hidden`/`role=presentation` images to a PASS, but everything else that reaches `_check_1_1_1_decorative` was still `alt == "" or _is_empty(alt) → PASS, else → FAIL "must have alt=\"\" (empty). Found: '<x>'"`. Two problems remain:
1. The value passed in is the **resolved accessible name** (`adapter._alt_text`: `accessibility_snapshot_name or alt_value`), not the literal `alt` attribute. In the live pipeline an image is only classified `decorative` when it carries `alt=""` (JS `classifyBlock`), so a non-empty value here means an `aria-label`/`aria-labelledby`/`title` is overriding the empty alt, or the classifier is wrong — a **conflict**, not the "author forgot `alt=\"\"`" failure the message describes.
2. `_is_empty` only catches `nan/none/""/null`, so a resolved name of `"image"`, `"photo"`, `"spacer"`, `"decoration"`, … (common on `<img alt="" title="spacer">`) produced a confident FAIL.
**Concrete failure:** `<img alt="" aria-label="Company logo">` → live JS classifies `decorative` (alt is empty) → `_alt_text` resolves `"Company logo"` from the snapshot → `_check_1_1_1_decorative("Company logo")` → **FAIL** *"Decorative image must have alt=\"\" (empty). Found: 'Company logo'"* — but the alt **is** empty; the real (minor) issue is the conflicting label.
**Fix:** placeholder/normalised-empty resolved names (`_norm(alt) in _EMPTY_OR_GENERIC`) now PASS as `decorative_valid`; a genuinely descriptive resolved name now returns **INCOMPLETE** with code `needs_review_decorative_conflict` (new i18n key) instead of FAIL — the classifier may be wrong or the label may be noise, and either way a human should look. `_check_1_1_1_missing_alt` and the §1.1 aria-hidden PASS are unchanged.

### 1.9 Same bug in the dead pipeline (`policy_1_1_1.py`) — NOT fixed, by direction
**File:** `accessibility/pipeline/decisions/policies/policy_1_1_1.py:18-32`
`Policy111`'s decorative branch FAILs (`decorative_invalid`) for **any** `accessible_name.name.strip()`, with no `aria-hidden` / `role=presentation` / title-only / generic-name carve-out — the pre-§1.1 bug, still present. Left untouched because `accessibility/pipeline/**` is out of the live path (§0) and explicitly not modified this pass. If that engine is ever re-wired, port the §1.8 logic: generic/empty name → PASS; name only from `title` or from an element with `role`/ancestor-role `presentation`/`none` → `needs_review`; real conflicting name → low-confidence `fail`.

---

## 2. WCAG 1.4.3 / 1.4.6 — Contrast (Minimum / Enhanced)

### 2.1 Logo contrast exemption never fires — typo'd against the classifier's real values
**File:** `alttext.py:1138` — `if classification in ("logo", "decorative") and not is_button:`
`classifier.py` never sets `classification` to the literal string `"logo"` — it only ever sets `classification="functional"` or `"informative"` with `sub_type="logos"` (see classifier.py lines 282, 335). The check is checking the wrong field/value pair.
**Concrete failure:** a stylized brand wordmark, `classification="functional"`, `sub_type="logos"`, OCR-measured contrast 2.1:1 (well below AA) → the exemption never matches → 1.4.3 evaluates for real and **FAILS**, dragging `overall_status` to FAILED — even though WCAG 1.4.3 explicitly exempts logotype text from any contrast minimum.
**Fix:** `if sub_type == "logos" or (classification == "decorative")`.

### 2.2 Button/icon OCR text is scored against the wrong threshold (4.5:1 instead of 3:1)
**File:** `text_detector.py:279` (`is_ui_component = category == "button_text"`) — computed, then **never used** anywhere else in the function. Neither `analyze_text_region(...)` (line 281-283) nor any of the three `check_wcag_compliance(...)` calls (lines 324-329, 343-347, 382-386) receive it. `analyze_ui_component()` — the function that actually applies the 3:1 threshold — is never called from `text_detector.py` at all; its only caller is the separate DOM-based 1.4.11 path in `alttext.py`.
**Concrete failure:** OCR text baked into a button, ratio 3.5:1, 16px regular. Correct 1.4.11 verdict: 3.5 ≥ 3.0 → PASS. Actual: scored as regular text → needs 4.5:1 → **FAIL** *"Fails AA Normal vs BG ..."* — a false positive on every non-large button/icon label detected by OCR.
**Fix:** thread `is_ui_component` through to `analyze_ui_component()`/`check_wcag_compliance(..., is_ui_component=...)` as the comment already claims it does.

### 2.3 `is_bold` is silently dropped on the primary OCR contrast call
**File:** `text_detector.py:281-283` — `analyze_text_region(img, clean_bbox, font_size_px=font_size_px)` omits the `is_bold` computed one line earlier (line 273). Inside `analyze_text_region`, `check_wcag_compliance` therefore always runs with `is_bold=False`.
**Concrete failure:** bold 20px OCR text, true ratio 3.8. Correct: bold + ≥18.5px → large text → 3:1 → PASS. Actual: not-bold assumed → not large (20<24) → 4.5:1 → **FAIL**. This wrong threshold is what several live finding-formatters (`_contrast_to_findings`, `_contrast_enhanced_to_findings` in `combined/findings.py`) fall back to whenever the richer color-cluster path errors out.
**Fix:** pass `is_bold=is_bold` into the call.

### 2.4 `estimate_boldness` is polarity-blind — light text on dark backgrounds is misread as bold
**File:** `utils/text_detector_helper.py:5-26` — hardcodes `text_pixels = np.sum(thresh == 0)` ("dark pixels = text"). For light/white text on a dark background — a very common pattern for hero banners and CTA buttons, exactly this tool's target case — the dark pixels are the *background majority*, not the text, so the density heuristic reports `is_bold=True` for ordinary-weight text.
**Concrete failure:** regular-weight white 20px text on a dark banner, true ratio 4.0. Correct: not bold, not large → 4.5:1 → FAIL. Actual: mis-flagged bold → large → 3:1 → **PASS** (wrong, hides a real violation).
**Fix:** detect polarity (which cluster is text vs. background, already computed in `contrast_analyser.segment_text_region`) before measuring stroke density, or share the polarity result instead of recomputing blind.

### 2.5 Bold/large-text cutoff is 18.5px instead of WCAG's 18.6667px (14pt)
**File:** `contrast_analyser.py:176` — `is_bold and font_size_px >= 18.5`. WCAG's 14pt bold cutoff is 18.6667px (14 × 96/72). The gap (18.5–18.667px) incorrectly classifies borderline bold text as "large," applying the looser 3:1 threshold instead of 4.5:1.
**Fix:** change to `18.6667` (already done correctly in `pipeline/config/thresholds.py` / `policy_1_4_3.py`'s dead-code path — copy that constant here).

### 2.6 Fabricated `AAA_passes` for non-text/UI contrast
**File:** `contrast_analyser.py:165-172` (`check_wcag_compliance`, `is_ui_component` branch) returns `"AAA_passes": ratio >= 3.0`. **WCAG 2.2 has no AAA-level success criterion for non-text contrast at all** — 1.4.11 is AA-only. This key becomes a real, wrong value the moment §2.2's dead-plumbing bug is fixed and `is_ui_component` starts reaching this function.
**Fix:** return `"AAA_passes": None` (not applicable) for the UI-component branch.

### 2.7 `aaa_threshold_used` is read but never written — every 1.4.6 finding shows the wrong required threshold
**File:** `combined/findings.py` (`_contrast_enhanced_to_findings`, ~843/861) reads `compliance.get("aaa_threshold_used", 7.0)`, but `check_wcag_compliance` (`contrast_analyser.py:181-187`) only ever sets `"aa_threshold_used"` — the AAA key is never produced. Every large-text 1.4.6 finding therefore reports "requires 7.0:1" even when the correct large-text AAA threshold is 4.5:1 (the PASS/FAIL verdict itself is computed correctly elsewhere — only the displayed number is wrong).
**Fix:** add `"aaa_threshold_used": aaa_threshold` to `check_wcag_compliance`'s return dict.

### 2.8 Segmentation/extraction errors are silently dropped from the OCR report artifacts (not the main findings list)
**File:** `text_detector.py:291, 376-379` — when `analyze_text_region`/`extract_colors_from_mask` return `{"error": ...}`, both the color-extraction and OCR-proxy-violation blocks are skipped with no `needs_review` marker recorded on `DetailedDetection`. This deflates `contrast_violations_count` in the standalone `text_detection_report.json` / `contrast_report.csv` / `contrast_report.md` artifacts (`TextClassification.save_reports()`, invoked live from `stages.py`). Segmentation is most likely to fail exactly when foreground/background luminance are nearly identical — i.e. the worst-contrast images. (The primary `findings.py`-based finding list is *not* affected — it separately emits `needs_review` for this case.)
**Fix:** record a `needs_review` detection in `save_reports()`'s data model too, not just in the main findings converter.

---

## 3. WCAG 1.4.5 — Images of Text

### 3.1 Wordmark FAIL branch is dead code — every plain-text logo auto-passes
**File:** `alttext.py:701-716` (`_check_1_4_5`). `if is_logo: return True` (line 704) runs *before* the intended exception check `if sub_type == "logos" and has_ocr_text: return False` (line 710, labeled "F12 FIX" — meant to catch a plain wordmark stored as an image, which is *not* exempt). Since `classifier.py` always sets `is_logo=True` whenever `sub_type=="logos"` (STEP 1b/STEP 2), line 704 fires first on every single case line 710 was written to catch.
**Concrete failure:** an image that is literally the plain text "ACME Corporation" rendered as a PNG (not a stylized logotype — the actual 1.4.5 violation this rule exists to catch) with `alt="ACME Corporation"` → unconditional PASS *"Logo/logotype exception"*.
**Fix:** delete line 704 (or move it after the F12 check and only exempt when the classifier's logo confidence excludes "plain wordmark" sub-cases).

---

## 4. WCAG 1.4.11 — Non-text Contrast

### 4.1 The "pixel-accurate" boundary-contrast path is 100% dead code — reads attributes that are never set
**File:** `alttext.py:1120-1121` — `getattr(img, "full_page_screenshot_path", None)` / `getattr(img, "page_bbox", None)`. Repo-wide grep confirms these two attribute names appear **nowhere else in the codebase** — not on the `ImageData` model (`crawler/models.py`), not set by any crawler stage. The guard in `_check_1_4_11` (`if full_page_image is not None and component_bbox is not None:`) therefore never passes.
**Impact:** every icon-only UI component (no baked-in text — e.g. a hamburger menu icon, a plain-fill button) falls through to `_check_1_4_11`'s Path 2, finds no OCR text, and returns `(None, "INCOMPLETE ... manual check required")` — forever. **The majority of real-world 1.4.11 violations (a low-contrast icon/button with no text on it) can never be automatically detected by this pipeline.**
**Fix:** either populate `full_page_screenshot_path`/`page_bbox` on `ImageData` from the crawler (the capability clearly exists — `contrast_analyser.analyze_ui_component()` is fully implemented and correct, it's just never fed real data), or remove the dead Path 1 code and be explicit in the docs that 1.4.11 is OCR-text-proxy-only today.

### 4.2 Even the fallback (Path 2) measures the wrong thing
**File:** `alttext.py:800-839`. When a UI component *does* have baked-in text, Path 2 computes the minimum contrast of the **text glyphs against their own immediate background** — not the **component's border/fill against the surrounding page**, which is what 1.4.11 actually requires.
**Concrete failure:** a button with dark text on a light face (internal text contrast 8:1) whose fill/border is only 1.2:1 against the surrounding white page → reported **PASS** *"Boundary contrast... meets the 3:1 minimum"* — the button is effectively invisible against the page, a real 1.4.11 failure reported as a pass.
**Fix:** this is really a symptom of §4.1 — once real page-context pixels are available, retire the OCR-text proxy for 1.4.11 entirely (it answers a 1.4.3 question, not a 1.4.11 one) and fall back to `needs_review` when no page context is available, rather than a false PASS/FAIL from mismatched data.

### 4.3 (Dead code, flag for cleanup) `policy_1_4_11.py` always returns `needs_review`
**File:** `accessibility/pipeline/decisions/policies/policy_1_4_11.py:46-49` — regardless of any computed boundary/border color, the function's final statement is an unconditional `return self._needs_review(...)`. It imports `ContrastEngine` but never calls it. Not reachable in production (see §0), but if this module is ever re-wired per Option B, this is the first thing that needs a real implementation — right now it can never produce PASS or FAIL for any element.

---

## 5. WCAG 1.2.1 / 1.2.2 / 1.2.3 — Media Alternatives & Captions (`rules/media/media_auditor.py`, `quality_engine.py`)

### 5.1 The literal word "live" anywhere in nearby text exempts genuinely prerecorded media
**File:** `media_auditor.py`, `_gate_1_is_prerecorded` (~line 136) — `re.search(r"\blive\b", text)` against `aria_label`/`nearby_text`.
**Concrete failure:** `nearby_text = "This interview was recorded live in our studio last year and is now archived."` next to an `<audio>` with no transcript → Gate 1 fires → status **N/A** ("live streaming... does not apply") → the real missing-transcript violation is never evaluated.
**Fix:** require an actual live-stream signal (HLS/`m3u8`, `data-live` attribute) as ka11y-node's live-captions check already does, not a bare keyword match on prose.

### 5.2 Video-only content defaults to "has audio" unless a narrow autoplay/muted/loop combination holds
**File:** `media_auditor.py`, `_gate_2_media_type` (~lines 164-181) — anything that isn't `is_muted AND has_loop AND has_autoplay` is classified `"synchronized"`.
**Concrete failure:** a click-to-play silent demo `<video>` (no audio track, not autoplaying) → misclassified `"synchronized"` → routed to the 1.2.2 caption check instead of 1.2.1 → the caption check FAILs it for "missing `<track kind="captions">`" — the wrong criterion — while the real 1.2.1 transcript violation is never reported at all.
**Fix:** detect audio-track presence directly (e.g. `HTMLMediaElement.webkitAudioDecodedByteCount`/`mozHasAudio`, or a muted/duration heuristic) instead of inferring it from autoplay/loop/muted state.

### 5.3 `kind="subtitles"` is accepted as satisfying both 1.2.1 transcripts and 1.2.2 captions
**File:** `media_auditor.py`, `_gate_4_check_captions` (~line 295: `if kind in ("captions", "subtitles")`) and `_ALT_TRACK_KINDS` (line 89, consumed by `_gate_4_find_transcript`). Subtitles cover translated dialogue only — not non-speech audio cues or (for 1.2.1) visual-content description.
**Concrete failure:** `<video><track kind="subtitles" src="dialogue-only.vtt"></video>` with meaningful non-speech sounds (alarms, doorbells) never described → passes Gate 4 for 1.2.2 as if it had real captions.
**Fix:** only `kind="captions"` satisfies 1.2.2; only `kind="descriptions"` (or a verified full transcript) satisfies 1.2.1 for video-only content.

### 5.4 Overly broad "alternative for"/"audio description of" keyword match exempts media with no alternative at all
**File:** `media_auditor.py`, `_MEDIA_ALT_KEYWORDS` (lines 71-86) used by `_gate_3_is_labeled_alternative`, reused for both 1.2.1 (line ~184-208) and 1.2.2 (line ~498).
**Concrete failure:** unrelated footer boilerplate — *"Check our accessibility page — it has an alternative for users with visual impairments"* — appearing anywhere near an undescribed video-only element → Gate 3 matches `"alternative for"` → element marked **N/A** "clearly labeled alternative... exempt," even though no transcript exists anywhere on the page.
**Fix:** require the matched text to be a link/label whose target is verified to contain substantial text near the media element, not any prose containing the phrase.

### 5.5 HTTP 405 on caption-track HEAD request is always treated as "not broken," with no GET fallback
**File:** `media_auditor.py`, `_gate_5_validate_track_url` (~line 322) — `if resp.status_code >= 400 and resp.status_code != 405`. A server that 405s all HEAD requests (including for files that don't exist) lets a genuinely broken caption URL through Gate 5; the later GET-and-parse step then fails and is downgraded to `NEEDS_REVIEW` instead of staying `FAILED` (an F8 violation).
**Fix:** on 405, retry with GET before deciding, rather than assuming the URL is fine.

### 5.6 `evaluate_captions_quality` returns `"PASS"` instead of the contract's `"PASSED"` — passing 1.2.2 findings vanish from the report entirely
**File:** `quality_engine.py:1001, 1015` — `status = "PASS"`. Every other status in this module (see the `_check_result` docstring, line 269) uses `"PASSED"|"FAILED"|"NEEDS_REVIEW"|"N/A"`. `combined/findings.py::_media_to_findings` (~lines 1153-1177) branches only on those four exact strings — `"PASS"` matches none of them.
**Concrete failure:** a fully compliant captioned video (5% WER) gets `wcag_1_2_2_status = "PASS"` → `_media_to_findings` produces **no finding at all** for that element — not even a pass record — silently corrupting pass/fail counts and coverage stats in every report.
**Fix:** change both to `"PASSED"`. This is a one-character-class bug with an outsized effect — add a unit test asserting the returned status is in the same fixed vocabulary as every other check.

### 5.7 A transcript with zero non-speech-event annotations always fails, even when the source audio has none to annotate
**File:** `quality_engine.py`, `_check_non_speech_events` (lines 444-492) unconditionally returns `FAILED` when a transcript has no bracketed descriptors like `[applause]`, with no check on whether the source audio *contains* any non-speech events. `evaluate_transcript_quality` (line 918) treats any single sub-check `FAILED` as overall `FAILED`.
**Concrete failure:** a plain narrated article, 100%-verbatim transcript, genuinely no music/applause/sound effects in the source → Check 3 still returns FAILED *"No bracketed audio event descriptors found"* → the entire transcript is marked **FAILED** despite being a fully equivalent, compliant alternative.
**Fix:** only require event annotations when an audio-event-detection pass on the source actually found events, or downgrade this specific check to `NEEDS_REVIEW` rather than a transcript-quality-tanking `FAILED`.

### 5.8 Speaker-ID and non-speech-event checks silently fall back to English patterns for every language except Japanese
**File:** `quality_engine.py:405, 468` — `_SPEAKER_PATTERNS.get(lang, _SPEAKER_PATTERNS["en"])` / `_AUDIO_EVENT_KEYWORDS.get(lang, _AUDIO_EVENT_KEYWORDS["en"])`. `lang` is caller-configurable end-to-end (from `stages.py`), but only `"en"`/`"ja"` have real pattern tables.
**Concrete failure:** a Korean transcript with correctly labeled speakers ("화자1: 안녕하세요") and a Deepgram-reported `speaker_count=2` → falls back to English regex (`^[A-Z]...`, meaningless for Hangul) → **FAILED** *"No speaker identification labels found... but Deepgram detected 2 speakers"* despite correct labeling.
**Fix:** either add pattern tables for the site's other supported languages (German, per the i18n docs) or downgrade to `NEEDS_REVIEW` for unsupported languages instead of silently applying English rules.

### 5.9 Same 15%-WER threshold, two different comparison operators — inconsistent verdict at the boundary
**File:** `quality_engine.py` — `_check_verbatim` (line 364) uses `score <= 0.15` → PASS; `evaluate_captions_quality` (line 1014) uses `error_rate < 0.15` → PASS (0.15 itself becomes `NEEDS_REVIEW`). A transcript/caption at exactly 15% WER gets a different verdict depending on which of the two code paths evaluates it, for what the docs describe as one shared threshold.
**Fix:** pick one operator (`<=`, matching the documented "15% or better") and use it in both places.

### 5.10 WCAG 1.2.3 and 1.4.2 are not implemented anywhere in the Python pipeline, despite being referenced as in-scope
**File:** `media_auditor.py` docstring (lines 14, 487) references "see 1.2.2/1.2.3" as if 1.2.3 is handled; `stages.py::_stage_media_audit_universal` never computes a status for 1.2.3 (Audio Description or Media Alternative) or 1.4.2 (Audio Control) — no audio-description-track check and no autoplay/mute/pause-mechanism logic exists in either audited file.
**Impact:** every page silently gets *zero* coverage — not even an `N/A` finding — for these two criteria. A page with autoplaying background audio >3s and no pause control (a textbook 1.4.2 F23 failure) is never flagged by anything in this pipeline.
**Fix:** this matches the doc's own "Unimplemented WCAG 2.2 A/AA SCs" table for 1.2.5/2.2.1/2.3.1 — add 1.2.3 and 1.4.2 to that same explicit "not implemented" list so it's an documented gap rather than a silent one, and prioritize 1.4.2 (autoplay detection from `<video>`/`<audio>` `autoplay`+`muted`/`volume` attributes is cheap to add and is a common real-world violation).

---

## Priority-ordered fix list

| # | Issue | SC | Effect | Effort |
|---|---|---|---|---|
| 1 | §0 Dead "Unified Pipeline" vs. live `alttext.py`/`media_auditor.py` split | 1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11 | Docs mislead about the real engine; wasted crawl/CPU building unused context trees | Delete or finish — pick one, both are cheap relative to leaving it |
| 2 | §5.6 `"PASS"` vs `"PASSED"` typo | 1.2.2 | Passing findings vanish from every report silently | Trivial (2-line fix) |
| 3 | §4.1 1.4.11 boundary-contrast path unreachable (`full_page_screenshot_path`/`page_bbox` never populated) | 1.4.11 | Icon-only low-contrast UI components can never be auto-failed | Medium — wire real screenshot/bbox data through the crawler |
| 4 | §3.1 1.4.5 wordmark-FAIL branch unreachable | 1.4.5 | Plain-text-as-image "logos" always pass | Trivial (reorder 2 branches) |
| 5 | §2.1 Logo contrast exemption checks the wrong field value | 1.4.3, 1.4.6 | Logos wrongly fail contrast (or, if a real `"logo"` value ever appears, wrongly always pass) | Trivial |
| 6 | §2.2/§2.3 `is_ui_component`/`is_bold` dead variables in OCR contrast call | 1.4.3, 1.4.6, 1.4.11 | Wrong threshold applied to bold and button/icon OCR text | Trivial (pass the already-computed variables through) |
| 7 | §2.4 `estimate_boldness` polarity-blind on light-on-dark text | 1.4.3, 1.4.6 | Real contrast failures on light text over dark banners silently pass | Small |
| 8 | §5.1–§5.4 Media auditor keyword/classification heuristics | 1.2.1, 1.2.2 | Real missing-transcript/caption violations exempted as N/A | Small–Medium each |
| 9 | §5.10 1.2.3 / 1.4.2 entirely unimplemented | 1.2.3, 1.4.2 | Zero detection, not even flagged as a gap | Medium (1.4.2), Larger (1.2.3) |
| 10 | §1.1–§1.7 alt-text/classifier edge cases | 1.1.1, 4.1.2 | Assorted false pass/fail on specific alt-text and classification patterns | Small each |
| 11 | §2.5–§2.8 Contrast math/threshold precision issues | 1.4.3, 1.4.6 | Boundary-value mis-scoring, wrong displayed AAA threshold, silently dropped violations in report artifacts | Small each |

---

## Fix Log

Applied in this pass. `accessibility/pipeline/**` (§0) was **explicitly left untouched** per direction — only the live code paths (`alttext.py`, `classifier.py`, `contrast_analyser.py`, `text_detector.py`, `media_auditor.py`, `quality_engine.py`, the crawler capture/adapter layer, and `combined/findings.py`) were fixed.

| § | Finding | Status | Note |
|---|---|---|---|
| 0 | Dead "Unified Pipeline" vs. live split | ⏸ Left as-is | Explicit choice this pass — not deleted, not re-wired. Docs (`ka11y-docs`) still need correcting separately. |
| 1.1 | aria-hidden decorative bypass ignored when `alt` non-empty | ✅ Fixed | `alttext.py`: decorative branch now checks `_is_aria_hidden_from_at` before falling to the empty-alt-only check. |
| 1.2 | `_check_1_1_1_button` accepted any 3+ char non-numeric string | ✅ Fixed | Recognised action words still auto-pass; unrecognised text now needs a vowel or 2+ words to auto-pass, else `INCOMPLETE` (needs review) instead of an automatic PASS. |
| 1.3 | `"x"` in `_SOCIAL_BRAND_NAMES` collides with close-icon `alt="X"` | 🔁 Investigated, kept as-is | An explicit test (`test_single_char_brand_passes`) locks in `"X"` as correct for the X/Twitter icon, and close controls are almost always classified `functional/buttons` (routed through `_check_1_1_1_button`, a different function) rather than `functional/icons` — the collision risk was narrower than first assessed. Documented the reasoning in code instead of removing it. |
| 1.4 | 3-char OCR floor drops short CJK words | ✅ Fixed | Tokens containing any non-ASCII character bypass the length floor. |
| 1.5 | CSS background-image exemption asserts (doesn't verify) equivalence | ⏸ Left as-is | Deliberate, already-documented tradeoff (the code's own docstring explains reporting every CSS background as a violation would be worse); downgrading it broadly risked flooding audits with needs-review noise on the majority-decorative common case. |
| 1.8 | `_check_1_1_1_decorative` hard-FAILs on the *resolved name* (not the raw `alt`) and on placeholder tokens — false positives on `<img alt="" aria-label="…">` / `<img alt="" title="spacer">` | ✅ Fixed | Placeholder / normalised-empty names now PASS (`decorative_valid`); a real conflicting name now returns **INCOMPLETE** / `needs_review_decorative_conflict` (new i18n key in `rules.yml` + `ja.yml`) instead of FAIL. 3 unit tests + 1 integration test updated to the corrected behaviour; 2 new cases added. |
| 1.9 | Same missing carve-out in `policy_1_1_1.py` (`decorative_invalid` for any name) | ⏸ Left as-is | Part of §0 — `accessibility/pipeline/**` not modified. Port instructions recorded in §1.9 for whenever that engine is re-wired. |
| 1.6 | Classifier `"ico"` keyword (3-char substring) false-matches unrelated words | ✅ Fixed | Removed from `_ICON_KEYWORDS`. |
| 1.7 | Classifier `_is_button` exception swallow → silent non-functional classification | ⏭ Deferred | Correct fix needs a `needs_review` classification value threaded through every downstream consumer (alttext.py, findings.py, CSV schema) — bigger than warranted for this narrow, already-non-fatal edge case. |
| — | `overall_status` `all([]) == True` bug (INCOMPLETE-only rows reported PASSED) | ✅ Fixed | Overall now derived from the already-computed per-criterion status strings: `FAILED` > `INCOMPLETE` > `PASSED`. Updated one test that had encoded the bug as expected behaviour. |
| 2.1 | 1.4.3/1.4.6 logo exemption checks `classification == "logo"`, a value that's never produced | ✅ Fixed | Now checks `sub_type == "logos"`, matching what the classifier actually emits. |
| 2.2 | `is_ui_component` dead variable in `text_detector.py` | 🔁 Investigated, revised | The originally-diagnosed "fix" (wiring `is_ui_component=True` through to the shared per-detection `compliance` dict) would have applied the 3:1 UI threshold to real 1.4.3/1.4.6 **text**-contrast checks for any button/icon OCR text — a new inaccuracy, not a fix (WCAG text-contrast thresholds don't relax because the text sits inside a button). Removed the dead variable and misleading comment instead; confirmed 1.4.11's own approximation (in `alttext.py`) already does its own independent 3:1 comparison on the raw ratio, unaffected by this dict. |
| 2.3 | `is_bold` dropped on the primary `analyze_text_region` call | ✅ Fixed | Now passed through; large-text threshold no longer silently defaults to "not bold". |
| 2.4 | `estimate_boldness` reads background as text on light-on-dark images | ✅ Fixed | Uses the minority pixel class (text is always thinner than its background) instead of hardcoding "dark = text". |
| 2.5 | Bold large-text cutoff `18.5px` vs. WCAG's `18.6667px` (14pt) | ✅ Fixed | |
| 2.6 | Fabricated `AAA_passes` for non-text/UI contrast (1.4.11 has no AAA tier) | ✅ Fixed | Now `None`. |
| 2.7 | `aaa_threshold_used` never returned — 1.4.6 findings always displayed 7.0:1 | ✅ Fixed | Now returned; large-text findings correctly show 4.5:1. |
| 2.8 | Segmentation/extraction errors silently dropped from OCR-side CSV/JSON reports | ✅ Fixed | New `DetailedDetection.needs_review` flag + `contrast_needs_review_count`; CSV/JSON/summary now surface these instead of omitting them. |
| 3.1 | 1.4.5 wordmark-FAIL branch (F12 FIX) unreachable | 🔁 Investigated, revised | On reflection, "fixing" the FAIL branch to be reachable would itself have been WCAG-*inaccurate*: a plain-text wordmark used as an organisation's logo is still exempt under 1.4.5's "essential presentation" exception (WCAG's own example), so failing it was never correct. Removed the dead/misleading code and documented why the blanket logo exemption is correct, rather than un-shadowing a check whose premise was wrong. |
| 4.1 | 1.4.11 boundary-contrast path unreachable (`full_page_screenshot_path`/`page_bbox` never populated) | ✅ Fixed | Real fix, not a stub: crawler now captures a padded context screenshot + local bbox for icon/logo elements (`optimized/engine.py`), copies it through (`optimized/adapter.py`), and `ImageData` carries it (`crawler/models.py`) to the already-correct `analyze_ui_component()` path in `alttext.py`. Additive and non-fatal — falls back to the prior OCR-text-proxy behaviour wherever context capture isn't available. |
| 4.2 | Path 2 (OCR-text proxy) measures the wrong quantity for non-text-only components | ✅ Improved (as a consequence of 4.1) | Icon/logo elements now use real boundary contrast (Path 1) when context capture succeeds; the proxy remains as documented fallback elsewhere. |
| 4.3 | Dead `policy_1_4_11.py` always returns `needs_review` | ⏸ Left as-is | Part of §0 — untouched by direction. |
| 5.1 | Gate 1 "live" keyword false-positives on long prose | ✅ Fixed | Keyword scan capped to short (≤40 char), label-like text. |
| 5.2 | Gate 2 video-only misclassification defaults to "synchronized" | 🔁 Investigated, reverted | Attempted classifying ambiguous `<video>` as "unknown"/needs-review; this made the confident `video_only` pattern the *only* way to ever leave "synchronized" unreached, which would have routed **every** video on every audited site to needs-review and made the entire (valuable, mostly-correct) 1.2.2 captions pipeline unreachable — trading a narrow false-negative for a much larger regression. Reverted the classification logic; instead made the 1.2.1 N/A reason text explicitly say this is an assumption, not a confirmed fact, so it's visible without changing routing. |
| 5.3 | `kind="subtitles"` silently accepted as satisfying 1.2.2 captions | ✅ Fixed | Still accepted at Gate 4 (avoids false-failing common mislabeled-but-compliant tracks), but a clean WER score on a `subtitles`-kind track now caps at `NEEDS_REVIEW` instead of a confident PASS, since dialogue-accuracy alone doesn't confirm non-speech-cue coverage. |
| 5.4 | Overly broad `_MEDIA_ALT_KEYWORDS` substring match in nearby prose | ✅ Fixed | `aria_label` match (deliberate, author-set) stays a confident `N/A`; `nearby_text`-only match (arbitrary surrounding prose) downgraded to `NEEDS_REVIEW`. Updated two tests that had asserted the old, overconfident behaviour. |
| 5.5 | HTTP 405 on HEAD treated as "fine", no GET fallback | ✅ Fixed | Retries with GET (streamed, closed without reading body) before deciding. |
| 5.6 | `"PASS"` vs. `"PASSED"` typo — passing 1.2.2 findings vanished from reports | ✅ Fixed | |
| 5.7 | `_check_non_speech_events` always FAILED on zero descriptors | ✅ Fixed | Downgraded to `NEEDS_REVIEW` — the function has no signal about whether the source audio actually contains non-speech events to note. |
| 5.8 | Speaker-ID / non-speech-event checks silently fall back to English for unsupported languages | ✅ Fixed | Both now return `NEEDS_REVIEW` for any language outside the real `en`/`ja` pattern tables instead of running English regex/keywords against it. |
| 5.9 | WER boundary inconsistency (`<=0.15` vs `<0.15`) between the two quality-check paths | ✅ Fixed | Both now use `<=` against the shared `_WER_PASS` constant. |
| 5.10 | WCAG 1.2.3 and 1.4.2 entirely unimplemented | ✅ Implemented | New `_check_1_2_3_audio_description` (descriptions-track / labeled-alternative / needs-review — matches the judgment-heavy automation ceiling already accepted elsewhere in this codebase, e.g. 2.5.4) and `_check_1_4_2_audio_control` (autoplay+muted/controls detection, reusing crawler data already captured — no new capture step needed) in `media_auditor.py`, wired into `combined/findings.py` and `auditor_field_map.py`. `i18n/rules.yml` already had metadata provisioned for both SCs with `severity: null`, suggesting these were planned but never implemented — the check logic was the actual gap. |

### Verification

- `python -m pytest tests/ -q` → 361 passed (4 pre-existing failures on unmodified `production`, confirmed via `git stash`, unrelated to this work: a missing `ka11y.crawler.forms_crawler` module, a stale `PageSnapshot.interactive` reference, a stale `_COMBINED_EXTRACT_JS` key-name check, and an unrelated `CombinedRequest` re-run param assertion).
- 27 test cases added or updated across `test_alt_text_auditor.py` and `test_media_auditor.py` to lock in the corrected behaviour, including updating tests that had encoded the bugs themselves as "expected" (`test_complex_image_without_long_description_needs_review`'s own assertion contradicted its name; `test_video_tag_default_is_synchronized`'s docstring now explains the assumption is stated, not asserted, as fact; `test_non_speech_events_missing_fails` → renamed and re-asserted as `NEEDS_REVIEW`).
- Every fix was applied directly to the module that's actually reachable from `_run_python_stages` (per §0) — dead code in `accessibility/pipeline/**` was read for context but not modified.

---

*Compiled by reading `ka11y-python/ka11y/accessibility/**`, `ka11y-python/ka11y/classifier/classifier.py`, `ka11y-python/ka11y/text_detector/text_detector.py`, `ka11y-python/ka11y/preprocessor/extract_color.py`, `ka11y-python/ka11y/utils/text_detector_helper.py`, and `ka11y-python/ka11y/api/v1/combined/{stages,findings}.py` in full, cross-checked against `ka11y-docs/rules/{overview,coverage-matrix}.mdx` and the `production` branch's git history.*
