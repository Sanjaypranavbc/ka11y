# ka11y-python Crawler: Complete Analysis, Bugs & Universal Redesign

> **Written:** 2026-04-10 — verified against full repo  
> **Scope:** All 9 crawlers + orchestrator (`stages.py`, `runner.py`, `findings.py`) + `universal_page.py`  
> **Cross-references:** `CRAWLER_METADATA.md` (field contracts), `PLUGPLAY_CONFIG_PLAN.md` (config architecture)

---

## Table of Contents

1. [What the Crawler Module Does](#1-what-the-crawler-module-does)
2. [End-to-End Data Flow](#2-end-to-end-data-flow)
3. [Every Crawler — Verified Details](#3-every-crawler--verified-details)
4. [Every Auditor — What It Reads](#4-every-auditor--what-it-reads)
5. [Pipeline Orchestration](#5-pipeline-orchestration)
6. [Bug Report — Verified](#6-bug-report--verified)
7. [Why 9 Separate Crawlers Is the Problem](#7-why-9-separate-crawlers-is-the-problem)
8. [Proposed Architecture: Universal Config-Driven Crawler](#8-proposed-architecture-universal-config-driven-crawler)
9. [Config Integration](#9-config-integration)
10. [Complete Field Contract](#10-complete-field-contract)
11. [Migration Plan](#11-migration-plan-phased)
12. [Files to Create / Modify](#12-files-to-create--modify)

---

## 1. What the Crawler Module Does

The crawler module is the **data-collection layer** of ka11y-python. It:

1. Launches a headless Chromium browser via Playwright
2. Navigates to the target URL
3. Runs JavaScript inside the page to extract DOM data
4. Returns typed Pydantic models to the auditors
5. Auditors apply WCAG logic to those models and produce findings

Crawlers **do not** make WCAG decisions. They only observe and collect.

---

## 2. End-to-End Data Flow

```
POST /combined/
        │
        ├─ assert_public_url(url)   ← SSRF guard (routes.py)
        ▼
_run_job(job_id, payload)   ← runner.py
        │
        ├─ asyncio.gather(return_exceptions=True):
        │       ├─ _call_node_flat()  →  ka11y-node (axe-core + 24 custom checks)
        │       └─ _run_python_stages()
        │                │
        │                │  asyncio.gather(return_exceptions=True, timeout=600s each)
        │                │
        │       ┌────────┴──────────────────────────────────────────────────┐
        │       │  9 concurrent stages                                       │
        │       │  image_audit │ form_audit │ label_in_name │ pause_stop_hide│
        │       │  target_size │ text_spacing │ rendered_layout │ media_audit│
        │       │  sensory_audit                                             │
        │       └────────────────────────────────────────────────────────────┘
        │
        ├─ _merge_findings(node_findings, python_findings)
        │       Dedup key: (wcag_sc, status, element_signature)
        │       Python findings win over axe-core on collision
        │
        ├─ Filter by WCAG level (A / AA / AAA)
        ├─ Sort by status (fail → needs_review → pass)
        └─ Save combined_report.json
```

### Stage → Crawler → Auditor → WCAG Coverage

| Stage | Crawler | Auditor | WCAG Criteria |
|-------|---------|---------|---------------|
| `image_audit` | `AsyncImageCrawler` | `AltTextAccessibilityAuditor` | 1.1.1, 4.1.2, 1.4.3, 1.4.5, 1.4.11 |
| `form_audit` | `AsyncFormCrawler` | `FormAccessibilityAuditor` | 3.3.1, 3.3.2 |
| `label_in_name` | `InteractiveElementCrawler` | `LabelInNameAuditor` | 2.5.3 |
| `pause_stop_hide` | `MovingContentCrawler` | `PauseStopHideAuditor` | 2.2.2 |
| `target_size` | `TargetSizeCrawler` | `TargetSizeAuditor` | 2.5.8 |
| `text_spacing` | `AsyncTextSpacingCrawler` | `TextSpacingAuditor` | 1.4.12 (structural) |
| `rendered_layout_audit` | `RenderedLayoutCrawler` | `run_all_evaluators()` | 1.4.4, 1.4.10, 1.4.12 (rendered), 1.3.4, 1.4.13, 2.4.11, 2.4.12 |
| `media_audit` | `AsyncMediaCrawler` | `MediaAuditor` | 1.2.1 |
| `sensory_audit` | `AsyncSensoryCrawler` | `SensoryCharacteristicsAuditor` | 1.3.3 |

---

## 3. Every Crawler — Verified Details

### 3.1 `AsyncImageCrawler` — `crawler.py`

- **JS Selectors:** `img`, `svg`, `canvas`, `[role="img"]`, CSS background images via `getComputedStyle`
- **Wait:** `networkidle` + own DOM stability logic
- **Shadow DOM:** No — `document.querySelectorAll`
- **Iframe:** No
- **Extra:** Downloads icon-sized images for OCR; GIFs verified with PIL frame count (async, 3s per GIF); screenshots capped at 5s each
- **Output model:** `ImageMetadata` (60+ fields in `models.py`)
- **Stage timeout:** Hard-capped at `_CRAWL_TIMEOUT_SECONDS = 300`; OCR continues on partial set if exceeded

### 3.2 `AsyncFormCrawler` — `forms_crawler.py`

- **JS Selector (lines 93–96):**
  ```javascript
  document.querySelectorAll('form')
  // if no forms → [document.body]
  form.querySelectorAll('input:not([type="hidden"]),select,textarea')
  ```
- **Wait:** `domcontentloaded` → `wait_for_timeout(2000)`
- **Shadow DOM:** ❌ `document.querySelectorAll` only — misses Web Components
- **Iframe:** ❌ No
- **Error resolution:** Resolves `aria-describedby` IDs; prefers `role="alert"` / `aria-live` target over first match
- **Output model:** `FormInputData` (Pydantic, 20+ fields)
- **Saves:** `forms_raw.json`

### 3.3 `InteractiveElementCrawler` — `interactive_crawler.py`

- **JS Selectors (lines 209–221):**
  ```javascript
  // Pass 1: native interactive elements
  document.querySelectorAll(
      'button, a[href], input[type="submit"], input[type="button"],
       input[type="reset"], input[type="image"]'
  )
  // Pass 2: ARIA-role elements on non-native tags
  document.querySelectorAll('[role]')
  // INTERACTIVE_ROLES = { button, link, menuitem, menuitemcheckbox,
  //   menuitemradio, option, tab, treeitem, radio, checkbox, switch, combobox, listbox }
  // Skips elements already in pass 1
  ```
- **Accessible name — 7-step AccName-1.1 (lines 77–129):**
  1. `aria-labelledby` (resolve IDs to text)
  2. `aria-label`
  3. Input-type-specific (`value` for submit/button/reset, `alt` for image)
  4. `<label for="id">` or wrapping `<label>`
  5. `title` attribute
  6. Text content (buttons / links / role=button)
  7. Empty string fallback
- **Dedup:** `WeakSet` prevents same element being added twice
- **Wait:** `domcontentloaded` → `wait_for_timeout(2000)`
- **Shadow DOM:** ❌ `document.querySelectorAll` only
- **Iframe:** ❌ No
- **Saves:** `interactive_elements_raw.json`

### 3.4 `MovingContentCrawler` — `moving_content_crawler.py`

- **Content types detected:**
  1. `video_autoplay` — `<video autoplay>` or `data-autoplay`
  2. `animated_gif` — `img[src$=".gif"]` verified via PIL frame count (async, 3s timeout, conservative)
  3. `css_animation` — computed `animation-name ≠ none` (catches CSS @keyframes)
  4. `carousel_autoplay` — Bootstrap, Swiper, Slick, Owl, Flickity, Glide, Splide (library-specific)
  5. `marquee_element` — deprecated `<marquee>`
  6. `blink_element` — deprecated `<blink>`
- **Video duration logic:**
  ```javascript
  const vidDuration = isFinite(el.duration) ? el.duration : null;
  if (vidDuration !== null && vidDuration <= 5) return;  // skip confirmed-short
  // null duration → included as potential violation  ← BUG-004
  ```
- **Wait:** `domcontentloaded` → `wait_for_timeout(2000)`
- **Shadow DOM:** ❌ No
- **Iframe:** ✅ Partial — detects YouTube, Vimeo, Dailymotion, Wistia, Twitch, Facebook, TED iframes by hostname; does NOT extract controls from within iframes
- **Saves:** `moving_content_raw.json`

### 3.5 `TargetSizeCrawler` — `target_size_crawler.py`

- **JS Selectors:**
  ```javascript
  // button, a[href], input[type="submit|button|reset|image|checkbox|radio"]
  // + [role] filtered by INTERACTIVE_ROLES
  ```
- **Offset exception geometry:**
  ```javascript
  required_x = max(0, (24 - width) / 2)
  required_y = max(0, (24 - height) / 2)
  // Inflate rect by required offset, check intersections with neighbours
  cur.required_offset_x_px = Math.round(reqX * 100) / 100;  // ← BUG-005: should be ceil
  ```
- **Wait:** `domcontentloaded` → `wait_for_timeout(2000)`
- **Shadow DOM:** ❌ No (individual crawler); `universal_page.py` version uses `queryShadow`
- **Iframe:** ❌ No
- **Saves:** `target_size_raw.json`

### 3.6 `AsyncTextSpacingCrawler` — `text_spacing_crawler.py`

- **JS Logic (lines 61–126):** Block-like elements (`display: block|inline-block|flex|grid`) with `text_length >= 20`
  - `has_fixed_height`: height matches `/^\d+(\.\d+)?px$/`
  - `has_overflow_hidden`: `overflow in ["hidden", "clip"]`
  - `is_clipped`: `scrollHeight > clientHeight` OR `scrollWidth > clientWidth`
- **Wait:** `domcontentloaded` only — **no `wait_for_timeout` call** (unlike other crawlers)
- **Shadow DOM:** ❌ No
- **Iframe:** ❌ No
- **Scope:** Static structural analysis only; actual rendered spacing test is in `RenderedLayoutCrawler`
- **Saves:** `text_spacing_raw.json` (via `save_json()`)

### 3.7 `RenderedLayoutCrawler` — `rendered_layout_crawler.py`

- **Viewports:** Desktop 1280×720, Reflow 320×640, Portrait 390×844, Landscape 844×390
- **Concurrent scenarios (asyncio.gather):**
  1. `baseline` — 1280×720
  2. `reflow_320` — 320×640
  3. `text_spacing_baseline` — 1280×720 (before CSS)
  4. `text_spacing_override` — 1280×720 + WCAG 1.4.12 CSS injection:
     ```css
     * { line-height: 1.5 !important; letter-spacing: 0.12em !important;
         word-spacing: 0.16em !important; }
     p,li,dt,dd,blockquote { margin-bottom: 2em !important; }
     /* CJK hardcoded — BUG-007: should be config-driven */
     :lang(ja), :lang(zh), [lang="ja"], [lang="zh"] {
         letter-spacing: normal !important; word-spacing: normal !important; }
     ```
  5. `resize_text_200` — `document.documentElement.style.fontSize = '200%'`
  6. `orientation_portrait` — 390×844
  7. `orientation_landscape` — 844×390
- **Sequential scans:**
  - Focus scan — Tab through focusable elements; captures `FocusStep` with `covering_elements` overlay data
  - Hover scan — hovers over tooltip/dropdown candidates; captures `HoverInteractionResult`
- **Wait:** `domcontentloaded` → `stabilize()` from `ka11y/accessibility/rendered/stabilizer.py` (adaptive, not hardcoded)
- **SSRF Guard:** ✅ `install_ssrf_guard(ctx)` on line 310
- **Shadow DOM:** No
- **Iframe:** No
- **Saves:** `rendered_layout_raw.json`

### 3.8 `AsyncMediaCrawler` — `media_crawler.py`

- **JS Selectors:** `document.querySelectorAll('audio')` + `document.querySelectorAll('video')`
- **Extracted:** `<track>` children (kind, src, srclang, label), controls, autoplay, loop, muted, parent container text (500 chars), nearby `<a>` links, nearby `<details>` blocks
- **Wait:** `domcontentloaded` → `wait_for_timeout(2000)`
- **Shadow DOM:** ❌ No
- **Iframe:** ❌ No
- **Saves:** `media_raw.json`

### 3.9 `AsyncSensoryCrawler` — `sensory_crawler.py`

- **JS Selector (TARGET_SELECTOR, lines 87–92):**
  ```
  p, li, label, legend, button, input, textarea, select, option,
  a, caption, th, td, span, div, h1-h6,
  summary, figcaption, dt, dd
  ```
- **Filtering (lines 169–201):**
  1. Skip `input[type="hidden"]`
  2. Skip `display:none`, `visibility:hidden`, `opacity:0`
  3. Min text: CJK ≥ 1 char (≥15% CJK chars), others ≥ 3 chars
  4. Skip div/span with only block-level children and no direct text > 5 chars
- **Wait:** `domcontentloaded` → `wait_for_timeout(1500)` ← **1500ms, not 2000ms**
- **Shadow DOM:** ❌ No
- **Iframe:** ❌ No
- **Saves:** `sensory_raw.json`

### 3.10 `UniversalPageLoader` — `universal_page.py` (UNUSED)

- **Purpose:** Load page once, extract all static data in one `evaluate()` call
- **Status:** ✅ Fully implemented (805 lines) — ❌ **never imported or called in the pipeline**
- **Verification:** `grep -rn "UniversalPageLoader" ka11y/api/` → 0 matches
- **Wait strategy (lines 701–731):**
  1. `domcontentloaded` (30s) → fallback `commit` (15s)
  2. `networkidle` (15s, best-effort)
  3. Poll SPA signals: `__NEXT_DATA__`, `__nuxt`, `__vue_app__`, `window.React`, `window.angular`, `window.Ember`, `window.__svelte`, `[data-reactroot]`
  4. DOM stability: MutationObserver, 600ms no mutations, 12s max
  5. Lazy-scroll (6 steps) + IntersectionObserver trigger
  6. Second stability check
  7. Single `page.evaluate(_COMBINED_EXTRACT_JS)`
- **Shadow DOM:** ✅ `queryShadow()` used throughout — pierces shadow roots recursively
- **HAR recording:** Optional, saves to `session.har` in output_dir
- **Combined JS output:** `{ forms, interactive, target_sizes, moving_content, media, text_spacing }`
- **Missing:** `sensory` section not yet in combined JS

---

## 4. Every Auditor — What It Reads

### 4.1 `FormAccessibilityAuditor` (3.3.1 / 3.3.2)

**WCAG 3.3.1 — Error Identification:**
```
required==True AND no aria-describedby               → FAIL
aria-describedby references non-existent element     → FAIL
error_element_id present, no role=alert, no aria-live → FAIL
```

**WCAG 3.3.2 — Labels or Instructions:**
```
NOT has_any_label                                    → FAIL "Input has no accessible label"
Field appears required (regex) but NOT marked        → FAIL
placeholder is the ONLY label                        → FAIL "Placeholder is sole label"
personal-data field, no autocomplete                 → FAIL
```

**Required field heuristic regex:** `\*`, `(required)`, `\brequired\b`, `必須`, `必要`, `obligatoire`, `obrigatório`, `pflichtfeld`, `erforderlich`, `requerido`

**Saves:** `audit_form_report.csv`

---

### 4.2 `LabelInNameAuditor` (2.5.3)

```
visible_label empty or no word chars   → N/A  "No visible text label"
accessible_name empty                  → FAIL "No accessible name found"
accessible_name does NOT contain
  visible_label (word-boundary check)  → FAIL "Accessible name does not contain visible label"
```

**Normalization:** NFC + casefold + collapse whitespace  
**Word boundary:** `\b` for Latin; substring for CJK  
**Saves:** `audit_label_in_name_report.csv`

---

### 4.3 `TargetSizeAuditor` (2.5.8)

```
is_inline_exception        → N/A "Inline link exception"
is_ua_controlled_exception → N/A "User-agent-controlled exception"
is_offset_exception        → N/A "Offset exception — sufficient spacing"
w >= 24 AND h >= 24        → PASS
otherwise                  → FAIL "{W}×{H}px — increase size or padding"
```

**Saves:** `audit_target_size_report.csv`

---

### 4.4 `PauseStopHideAuditor` (2.2.2)

```
starts_automatically == False                     → PASS (rule doesn't apply)
duration <= 5s AND not loops AND not infinite     → PASS (too short to apply)
has_mechanism == True                             → PASS
otherwise                                         → FAIL "{type} starts automatically with no pause mechanism"
```

**Saves:** `audit_pause_stop_hide_report.csv`

---

### 4.5 `MediaAuditor` (1.2.1) — 4-Gate Logic

1. **Gate 1 — Live?** src ends `.m3u8`/`.mpd` OR "live" in aria_label/nearby_text → N/A
2. **Gate 2 — Media type:** AUDIO → `audio_only`; VIDEO + muted+loop+autoplay → `video_only`; VIDEO → `synchronized`
3. **Gate 3 — Labeled alternative?** aria_label/nearby_text contains "audio/video version/alternative" → N/A
4. **Gate 4 — Transcript:** `<track kind="captions|descriptions|subtitles">`, nearby `<a>` with transcript keywords (EN + JA), nearby `<details>`, `aria-describedby` text > 50 chars → PASS if any found, else FAIL

**Saves:** `audit_media_report.csv`

---

### 4.6 `SensoryCharacteristicsAuditor` (1.3.3)

1. Filter to instructional elements (imperative verbs + instructional patterns)
2. Per sentence: sensory-only reference (color/shape/size/position/orientation/sound/brightness/texture word) with no non-sensory identifier → FAIL
3. Sensory + visible label → PASS

**Language detection:** `lang` field from element; falls back to CJK density (≥15% CJK chars)  
**Word lists:** EN (8 categories, ~100 words) + JA (parallel 8-category taxonomy in kanji/hiragana)  
**Saves:** `audit_sensory_report.csv`

---

### 4.7 `TextSpacingAuditor` (1.4.12 — structural only)

`has_fixed_height AND has_overflow_hidden AND is_clipped` → FAIL  
Rendered check (applying WCAG CSS) is separate in `RenderedLayoutCrawler`.

---

## 5. Pipeline Orchestration

### `runner.py` — Job Entry Point

```
_run_job(job_id, payload)
  │
  ├─ Set _lang_ctx = payload.lang   ← asyncio ContextVar, inherited by all child tasks
  │     All _make_finding() calls read _lang_ctx.get() for WCAG names/suggested fixes
  │     No need to thread lang through every function signature
  ├─ Create output_dir
  │
  ├─ asyncio.gather(
  │     _call_node_flat(),           ← POST to ka11y-node
  │     _run_python_stages()         ← all 9 Python stages
  │   )
  │
  ├─ _merge_findings(node, python)   ← dedup by (wcag_sc, status, element_signature)
  │     element_signature = target_selector OR element_id OR html[:120].lower()
  │     Python findings WIN over axe-core on collision
  │
  ├─ Filter by WCAG level
  ├─ Sort by status
  └─ Save combined_report.json
```

### `stages.py` — Python Stages

`_run_python_stages()` runs all 9 stages concurrently via `asyncio.gather(return_exceptions=True)`, each wrapped with `asyncio.wait_for(..., timeout=600)`.

**Result shape:**
- Stage 0 (image_audit): returns `(findings, contrast_report)` — unique
- All other stages: return `List[Dict]`

**Note:** No deduplication happens inside `_run_python_stages()` — that's `_merge_findings()` in `runner.py`.

### `findings.py` — Converter Functions

Each converter reads specific field names from auditor output:

| Converter | Reads | Output `wcag_sc` |
|-----------|-------|-----------------|
| `_alt_text_to_findings` | `wcag_1_1_1_status`, `wcag_1_1_1_reason`, `src`, `alt_text` | `1.1.1` |
| `_name_role_value_to_findings` | `wcag_4_1_2_status`, `wcag_4_1_2_reason` | `4.1.2` |
| `_contrast_to_findings` | `dominant_contrast`, `contrast_ratio`, `AA_passes` | `1.4.3` |
| `_form_to_findings` | `wcag_3_3_1_status`, `wcag_3_3_2_status` | `3.3.1`, `3.3.2` |
| `_media_to_findings` | `wcag_1_2_1_status`, `wcag_1_2_1_violation` | `1.2.1` |
| `_psh_to_findings` | `wcag_2_2_2_status`, `wcag_2_2_2_violation` | `2.2.2` |
| `_lin_to_findings` | `wcag_2_5_3_status`, `wcag_2_5_3_violation` | `2.5.3` |
| `_ts_to_findings` | `wcag_2_5_8_status`, `wcag_2_5_8_violation` | `2.5.8` |
| `_crawler_text_spacing_to_findings` | `wcag_1_4_12_status` | `1.4.12` |
| `_rendered_text_spacing_to_findings` | `wcag_1_4_12_status` | `1.4.12` |
| `_sensory_to_findings` | `wcag_1_3_3_status`, `wcag_1_3_3_violation` | `1.3.3` |

The **contrast report** is a separate structured object (`summary`, `table`, per-image `detections`), not in `all_findings`.

### Existing Deduplication (what already works)

`_merge_findings()` in `runner.py` deduplicates across **node + python** findings by `(wcag_sc, status, element_signature)`. Python wins over axe-core. This is working.

What it does NOT fix: two Python stages both emitting `1.4.12` findings for the same element with slightly different `html_snippet` representations → they get different `element_signature` values → both survive dedup.

---

## 6. Bug Report — Verified

### BUG-001 · CRITICAL — `UniversalPageLoader` Exists But Is Never Called

**Files:** `universal_page.py` (805 lines), `stages.py`

`grep -rn "UniversalPageLoader" ka11y/api/` → **0 matches**. Dead code. Nine separate Playwright contexts open instead.

```
9 crawlers × (browser launch ~1s + page.goto ~3s + wait ~1.5–2s)
= ~54s of redundant overhead running in the background
```

---

### BUG-002 · HIGH — Shadow DOM Invisible to 6 of 7 Static Crawlers

**Files:** `forms_crawler.py:93`, `interactive_crawler.py:209`, `media_crawler.py`, `moving_content_crawler.py`, `target_size_crawler.py`, `sensory_crawler.py`

All use `document.querySelectorAll(...)`. Shadow roots (Web Components, Lit, Polymer, FAST, Shoelace) are completely invisible. `universal_page.py` has the correct `queryShadow()` fix — unused by individual crawlers.

---

### BUG-003 · HIGH — WCAG 1.4.12 Double-Reported, Dedup Not Guaranteed

**Files:** `stages.py:387–422`, `stages.py:425–518`

Both `AsyncTextSpacingCrawler` + `RenderedLayoutCrawler` emit findings tagged `wcag_sc="1.4.12"`. The `_merge_findings()` dedup uses `html[:120].lower()` as element signature. The two stages generate their `html_snippet` differently, so the signatures often differ → same element appears as two findings.

---

### BUG-004 · HIGH — Null Video Duration = False Positives (2.2.2)

**File:** `moving_content_crawler.py` (JS)

```javascript
const vidDuration = isFinite(el.duration) ? el.duration : null;
if (vidDuration !== null && vidDuration <= 5) return;
// null duration (metadata not loaded) → passes through → flagged as violation
// WCAG 2.2.2 only applies to content > 5 seconds
```

**Fix:** Add `duration_known: bool`. Auditor marks unknown-duration as `needs_review`.

---

### BUG-005 · MEDIUM — Target Size Offset Uses `Math.round` (Should Be `Math.ceil`)

**File:** `target_size_crawler.py` JS

```javascript
cur.required_offset_x_px = Math.round(reqX * 100) / 100;
// reqX = 0.0049 → rounds to 0.00 → element incorrectly passes offset exception
// Should be: Math.ceil(reqX * 100) / 100
```

---

### BUG-006 · MEDIUM — Forms Outside `<form>` Tags Silently Dropped

**File:** `forms_crawler.py:84–88`

```javascript
const formList = forms.length > 0 ? forms : [document.body];
// If page has >= 1 <form>, inputs outside all forms are silently lost
```

---

### BUG-007 · MEDIUM — Hardcoded CJK Text Spacing CSS

**File:** `rendered_layout_crawler.py:69–102`

```css
/* Not configurable — should come from languages/{lang}.yml text_spacing block */
:lang(ja), :lang(zh), [lang="ja"], [lang="zh"] {
    letter-spacing: normal !important;
    word-spacing: normal !important;
}
```

`PLUGPLAY_CONFIG_PLAN.md` defines `apply_letter_spacing: false` / `apply_word_spacing: false` for CJK — these flags should drive the CSS builder.

---

### BUG-008 · MEDIUM — No iFrame DOM Extraction (Except URL-Pattern Detection)

**Files:** `forms_crawler.py`, `interactive_crawler.py`, `media_crawler.py`

`MovingContentCrawler` detects video platform iframes by URL pattern only. No crawler extracts DOM from within iframes. Forms in iframes, social buttons, custom video controls in iframes are all missed.

---

### BUG-009 · LOW — JS Helpers Copy-Pasted 4+ Times, Already Diverging

**Files:** `forms_crawler.py`, `interactive_crawler.py`, `target_size_crawler.py`, `universal_page.py`

`resolveAriaLabelledby`, `computeAccessibleName`, `getVisibleLabel`, `INTERACTIVE_ROLES` — 4 copies with subtle differences. `universal_page.py`'s `computeAccessibleName` handles `role="group"`; `interactive_crawler.py`'s version does not.

---

### BUG-010 · LOW — `wait_until="commit"` Fallback Returns Empty DOM Silently

**Files:** `forms_crawler.py:224`, `interactive_crawler.py:263`

```python
except Exception:
    await page.goto(url, wait_until="commit", timeout=15_000)
    # "commit" fires on HTTP headers — DOM is empty
    # evaluate() returns [] with no exception raised
    # Stage reports 0 findings, no error logged
```

---

### BUG-011 · LOW — `print()` Instead of Structured Logger

**Files:** `forms_crawler.py:249`, `interactive_crawler.py:285`

```python
print(f"[FormCrawler] Error on {url}: {exc}")  # all other crawlers use setup_logger()
```

---

### NOT A BUG — `_merge_findings` Already Deduplicates Node vs Python

Working correctly. BUG-003 is specifically about two Python stages producing duplicate 1.4.12 findings that `_merge_findings` can't catch because their element signatures differ.

### NOT A BUG — Stage Event Race Already Fixed

`runner.py` had a race between stage-event broadcasts and subscriber cleanup. Fixed via `await asyncio.sleep(0)` before closing (line 253). Already resolved.

---

## 7. Why 9 Separate Crawlers Is the Problem

### Performance (verified numbers)

```
Stage              Own Browser  page.goto  wait              Total
──────────────────────────────────────────────────────────────────
image_audit        yes          ~3s        (own logic)       ~5s (hard cap 300s)
form_audit         yes          ~3s        2000ms            ~5s
label_in_name      yes          ~3s        2000ms            ~5s
pause_stop_hide    yes          ~3s        2000ms            ~5s
target_size        yes          ~3s        2000ms            ~5s
text_spacing       yes          ~3s        (none)            ~3s
rendered_layout    yes          ~3s        stabilize()       ~15s (7 scenarios)
media_audit        yes          ~3s        2000ms            ~5s
sensory_audit      yes          ~3s        1500ms            ~4.5s
──────────────────────────────────────────────────────────────────
Network requests to same URL         ×9
DOM parses of same DOM               ×9
Wall-clock (asyncio.gather)     ≈ 15s (bounded by rendered_layout)
Background redundant load time  ≈ 40s across 8 extra browsers
```

### What Genuinely Needs Its Own Browser

| Crawler | Needs Own Load? | Reason |
|---------|----------------|--------|
| Forms, Interactive, Target Size, Moving Content, Media, Text Spacing, Sensory | **No** | Pure `evaluate()` — one load covers all |
| `AsyncImageCrawler` | **Partially** | Screenshots + file I/O per image |
| `RenderedLayoutCrawler` | **Yes** | Multi-viewport, CSS injection, Tab/hover simulation |

**Optimal: 3 browser launches** (universal static + image + rendered), not 9.

---

## 8. Proposed Architecture: Universal Config-Driven Crawler

### Design Principle
> Load the page once. Extract everything in one `evaluate()` call. Route typed data to each auditor. Language-aware extraction via config constants injected into JS at build time.

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         KA11yConfig                                   │
│  crawlers.config.yml + languages/{lang}.yml + sites/{site_id}.yml    │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│         UniversalStaticCrawler  (1 browser, 1 page load)              │
│                                                                       │
│  1. goto(url)                                                         │
│  2. _wait_for_dom_stability()  ← networkidle + MutationObserver       │
│  3. _lazy_scroll()             ← trigger lazy-load                    │
│  4. page.evaluate(_COMBINED_JS)  ← 1 round-trip, built from:         │
│       shared helpers (queryShadow, computeAccessibleName, ...)        │
│       FormsExtractor.js_extract + lang constants                      │
│       InteractiveExtractor.js_extract                                 │
│       TargetSizeExtractor.js_extract                                  │
│       MovingContentExtractor.js_extract                               │
│       MediaExtractor.js_extract + KA11Y_TRANSCRIPT_KEYWORDS=[...]     │
│       TextSpacingExtractor.js_extract                                 │
│       SensoryExtractor.js_extract + KA11Y_SENSORY_COLOR_WORDS=[...]   │
│  5. Return PageSnapshot                                               │
│  6. Record HAR → RenderedLayoutCrawler                                │
└────────────────────────────┬─────────────────────────────────────────┘
                             │  PageSnapshot
         ┌───────────────────┼───────────────────────────┐
         ▼                   ▼                           ▼
snapshot.forms     snapshot.interactive        snapshot.moving_content
snapshot.media     snapshot.target_sizes       snapshot.text_spacing
snapshot.sensory                               snapshot.har_path
         │
 ┌───────┼──────────────────────────────────────────┐
 ▼       ▼          ▼           ▼           ▼        ▼
Form  LabelInName Target  PauseStop   Media   Sensory
Aud.    Aud.       Aud.    Aud.       Aud.    Aud.
     (all: asyncio.to_thread, CPU-bound, in parallel)

Keep separate browsers:
  AsyncImageCrawler      → AltTextAuditor  (screenshots + OCR)
  RenderedLayoutCrawler  → run_all_evaluators (multi-viewport rendering)
```

### 8.1 The `RuleExtractor` Protocol

```python
# ka11y/crawler/extractor_protocol.py

from typing import Protocol

class RuleExtractor(Protocol):
    wcag_criterion: str       # "3.3.1"
    snapshot_field: str       # "forms"
    js_extract: str           # JS IIFE; sets window.__ka11y_{snapshot_field}__
    auditor_class: type       # FormAccessibilityAuditor
    language_aware: bool
    language_keys: list[str]  # keys from KA11yConfig.lang_config
```

### 8.2 Combined JS Builder

```python
class UniversalStaticCrawler:

    @staticmethod
    def _build_combined_js(extractors: list, config: KA11yConfig) -> str:
        parts = [_SHARED_JS_HELPERS]       # single canonical copy of all helpers
        for ex in extractors:
            if ex.language_aware:
                parts.append(_inject_lang_constants(ex, config))
            parts.append(ex.js_extract)
        fields = ", ".join(
            f"{ex.snapshot_field}: __ka11y_{ex.snapshot_field}__"
            for ex in extractors
        )
        return f"() => {{\n{''.join(parts)}\nreturn {{ {fields} }};\n}}"
```

Language constants injected as inline JS before each extractor:

```javascript
// MediaExtractor receives (lang="ja"):
const KA11Y_TRANSCRIPT_KEYWORDS = ["書き起こし", "文字起こし", "トランスクリプト", "字幕"];

// SensoryExtractor receives (lang="ja"):
const KA11Y_SENSORY_COLOR_WORDS = ["赤", "青", "緑", "黄色", "白", "黒"];
const KA11Y_SENSORY_SHAPE_WORDS = ["丸", "四角", "円形", "三角"];
```

### 8.3 Smart Wait (replaces all hardcoded waits)

```python
async def _wait_for_dom_stability(page, stable_ms=600, timeout_ms=12_000):
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass  # falls through for SPA pages
    for signal in _SPA_SIGNALS:
        try:
            if await page.evaluate(f"() => !!({signal})"): break
        except Exception:
            pass
    await page.evaluate(f"""
        new Promise(resolve => {{
            let timer = setTimeout(resolve, {stable_ms});
            const obs = new MutationObserver(() => {{
                clearTimeout(timer); timer = setTimeout(resolve, {stable_ms});
            }});
            obs.observe(document.body, {{ subtree: true, childList: true }});
            setTimeout(() => {{ obs.disconnect(); resolve(); }}, {timeout_ms});
        }})
    """)
```

### 8.4 Refactored `_run_python_stages`

```python
async def _run_python_stages(..., config: KA11yConfig):
    # 1 static load (replaces 7 crawlers)
    snapshot = await UniversalStaticCrawler.load(url=url, output_dir=output_dir, config=config)

    # Image + rendered keep own browsers
    image_task   = asyncio.create_task(_stage_image_audit(url, output_dir, ...))
    rendered_task = asyncio.create_task(_stage_rendered_layout_audit(
        url, output_dir, ..., har_path=snapshot.har_path
    ))

    # All static auditors: CPU-only, run in parallel
    results = await asyncio.gather(
        asyncio.to_thread(_run_form_auditor,    snapshot.forms,          url, output_dir),
        asyncio.to_thread(_run_lin_auditor,     snapshot.interactive,    url, output_dir),
        asyncio.to_thread(_run_ts_auditor,      snapshot.target_sizes,   url, output_dir),
        asyncio.to_thread(_run_psh_auditor,     snapshot.moving_content, url, output_dir),
        asyncio.to_thread(_run_media_auditor,   snapshot.media,          url, output_dir),
        asyncio.to_thread(_run_tsp_auditor,     snapshot.text_spacing,   url, output_dir),
        asyncio.to_thread(_run_sensory_auditor, snapshot.sensory,        url, output_dir, lang),
        image_task,
        rendered_task,
        return_exceptions=True,
    )
    return _deduplicate_1412(flatten(results)), contrast_report
```

### 8.5 `PageSnapshot` — Canonical (add `sensory`)

```python
@dataclass
class PageSnapshot:
    page_url: str
    forms: List[Dict[str, Any]]          = field(default_factory=list)
    interactive: List[Dict[str, Any]]    = field(default_factory=list)
    target_sizes: List[Dict[str, Any]]   = field(default_factory=list)
    moving_content: List[Dict[str, Any]] = field(default_factory=list)
    media: List[Dict[str, Any]]          = field(default_factory=list)
    text_spacing: List[Dict[str, Any]]   = field(default_factory=list)
    sensory: List[Dict[str, Any]]        = field(default_factory=list)  # ADD
    har_path: Optional[str]              = None
    load_time_ms: Optional[float]        = None
    dom_stability_reached: bool          = True
    extractor_errors: List[str]          = field(default_factory=list)
```

---

## 9. Config Integration

### Current State

`ka11y/config/__init__.py` is **an empty file**. No `KA11yConfig` loader exists yet.

Language support today: `_lang_ctx: ContextVar[str]` set in `runner.py`, read in `findings.py` for WCAG names and suggested fixes. Crawlers and auditors have **zero language awareness** — keyword lists are hardcoded.

### `crawlers.config.yml` — Revised Schema

```yaml
version: "2.0"

static_extractors:           # run inside UniversalStaticCrawler (no extra browser)
  - id: "FormsExtractor"
    snapshot_field: "forms"
    wcag_criteria: ["3.3.1", "3.3.2"]
    auditor: "FormAccessibilityAuditor"
    enabled: true
    language_aware: true
    language_keys: ["confirm_field_patterns"]

  - id: "InteractiveExtractor"
    snapshot_field: "interactive"
    wcag_criteria: ["2.5.3"]
    auditor: "LabelInNameAuditor"
    enabled: true
    language_aware: false

  - id: "TargetSizeExtractor"
    snapshot_field: "target_sizes"
    wcag_criteria: ["2.5.8"]
    auditor: "TargetSizeAuditor"
    enabled: true
    language_aware: false

  - id: "MovingContentExtractor"
    snapshot_field: "moving_content"
    wcag_criteria: ["2.2.2"]
    auditor: "PauseStopHideAuditor"
    enabled: true
    language_aware: false

  - id: "MediaExtractor"
    snapshot_field: "media"
    wcag_criteria: ["1.2.1"]
    auditor: "MediaAuditor"
    enabled: true
    language_aware: true
    language_keys: ["transcript_keywords"]   # replaces hardcoded EN list in auditor

  - id: "TextSpacingExtractor"
    snapshot_field: "text_spacing"
    wcag_criteria: ["1.4.12"]
    auditor: "TextSpacingAuditor"
    enabled: true
    language_aware: true
    language_keys: []       # reads text_spacing block (apply_letter_spacing etc.)

  - id: "SensoryExtractor"
    snapshot_field: "sensory"
    wcag_criteria: ["1.3.3"]
    auditor: "SensoryCharacteristicsAuditor"
    enabled: true
    language_aware: true
    language_keys:
      - sensory_color_words
      - sensory_shape_words
      - sensory_size_words
      - sensory_position_words
      - sensory_orientation_words
      - sensory_sound_words
      - sensory_brightness_words
      - sensory_texture_words

independent_crawlers:        # keep own browser
  - id: "AsyncImageCrawler"
    wcag_criteria: ["1.1.1", "4.1.2", "1.4.3", "1.4.5", "1.4.11"]
    enabled: true
    language_aware: false

  - id: "RenderedLayoutCrawler"
    wcag_criteria: ["1.4.4", "1.4.10", "1.4.12", "1.3.4", "1.4.13", "2.4.11", "2.4.12"]
    enabled: true
    language_aware: true     # CJK text_spacing flags drive CSS builder
    language_keys: []        # reads text_spacing block from lang config
```

### CJK Text Spacing: Config-Driven CSS

**Now (hardcoded in `rendered_layout_crawler.py`):**
```css
:lang(ja), :lang(zh), [lang="ja"], [lang="zh"] {
    letter-spacing: normal !important;
    word-spacing: normal !important;
}
```

**After:**
```python
flags = config.get_text_spacing_flags()   # from languages/ja.yml text_spacing block
css = "\n".join(filter(None, [
    "* { line-height: 1.5 !important; }",
    "* { letter-spacing: 0.12em !important; }" if flags.apply_letter_spacing else "",
    "* { word-spacing: 0.16em !important; }"   if flags.apply_word_spacing   else "",
    "p,li,dt,dd,blockquote { margin-bottom: 2em !important; }",
]))
```

### Adding a New WCAG Rule

1. `ka11y/crawler/extractors/new_rule.py` — implement `RuleExtractor`
2. Add `new_rule: List[Dict]` to `PageSnapshot`
3. Add `NewRuleExtractor()` to `STATIC_EXTRACTORS`
4. Add keyword lists to `config/languages/*.yml`
5. Register in `crawlers.config.yml`

**Zero changes to `stages.py`. Zero new browser launches.**

---

## 10. Complete Field Contract

> Verified from source — what each auditor actually reads.

### Forms (3.3.1 / 3.3.2)

| Field | Used For |
|-------|---------|
| `tag`, `type` | Input classification |
| `has_any_label`, `has_explicit_label`, `has_wrapping_label` | Label presence |
| `aria_label`, `aria_labelledby`, `label_text` | Accessible name |
| `required`, `aria_required`, `aria_invalid` | Validation state |
| `error_element_id`, `error_element_role`, `error_has_role_alert`, `error_has_aria_live` | Error quality |
| `autocomplete` | Personal data field |
| `placeholder` | Sole label detection |
| `html` | Violation evidence |

### Interactive → Label in Name (2.5.3)

| Field | Used For |
|-------|---------|
| `visible_label` | What sighted users see |
| `accessible_name` | Computed AccName-1.1 |
| `aria_label`, `aria_labelledby_text` | Accessible name inputs |
| `tag`, `role`, `input_type` | Element classification |
| `html_snippet` | Violation evidence |

### Target Sizes (2.5.8)

| Field | Used For |
|-------|---------|
| `rendered_width_px`, `rendered_height_px` | Size check ≥ 24px |
| `is_inline_exception` | Exception E1 (inline links) |
| `is_ua_controlled_exception` | Exception E4 (native checkbox/radio) |
| `is_offset_exception` | Exception E5 (spacing) |
| `required_offset_x_px`, `required_offset_y_px` | Offset needed (BUG-005: Math.round) |
| `nearest_target_gap_x_px`, `nearest_target_gap_y_px` | Actual gap to neighbours |
| `passes_size` | Pre-computed flag |

### Moving Content (2.2.2)

| Field | Used For |
|-------|---------|
| `content_type` | Type label in findings |
| `starts_automatically` | Rule applicability gate |
| `duration_seconds` | 5s threshold (null = BUG-004) |
| `loops`, `animation_iteration_count` | Infinite loop detection |
| `has_mechanism` | Pass condition |

### Media (1.2.1)

| Field | Used For |
|-------|---------|
| `tag`, `is_muted`, `has_loop`, `has_autoplay` | Media classification |
| `tracks` (kind, srclang) | Caption/description track |
| `aria_label`, `aria_describedby_text` | Transcript proxy |
| `nearby_links`, `nearby_text`, `nearby_details` | External transcript |

### Text Spacing (1.4.12 — structural)

| Field | Used For |
|-------|---------|
| `has_fixed_height` | Clipping risk |
| `has_overflow_hidden` | Clipping risk |
| `is_clipped` | Confirmed overflow |

### Sensory (1.3.3)

| Field | Used For |
|-------|---------|
| `text`, `aria_label`, `placeholder`, `value`, `title` | Instruction text |
| `lang` | Language-aware NLP |
| `nearest_heading`, `role`, `parent_tag` | False-positive filtering |

---

## 11. Migration Plan (Phased)

### Phase 0 — Immediate Bug Fixes (no architecture change)

| Bug | File | Change |
|-----|------|--------|
| BUG-002 | `interactive_crawler.py:209,215` | `document.querySelectorAll` → `queryShadow` |
| BUG-002 | `forms_crawler.py:84,93` | `document.querySelectorAll('form')` → `queryShadow(document, 'form')` |
| BUG-004 | `moving_content_crawler.py` JS | Add `duration_known: vidDuration !== null` to result |
| BUG-005 | `target_size_crawler.py` JS | `Math.round(reqX * 100) / 100` → `Math.ceil(reqX * 100) / 100` (×2) |
| BUG-006 | `forms_crawler.py:84` | Collect orphan inputs regardless of `<form>` count |
| BUG-010 | `forms_crawler.py:224`, `interactive_crawler.py:263` | `commit` fallback: log warning + return empty |
| BUG-011 | `forms_crawler.py:249`, `interactive_crawler.py:285` | `print()` → `logger.warning()` |

### Phase 1 — Activate `UniversalPageLoader`

1. Add `sensory` section to `_COMBINED_EXTRACT_JS` in `universal_page.py` (copy selector logic from `sensory_crawler.py`)
2. Add `sensory: List[Dict]`, `extractor_errors: List[str]` to `PageSnapshot`
3. Refactor `_run_python_stages()` — replace 7 crawler calls with `UniversalPageLoader.load()`
4. Pass snapshot fields directly to each auditor's `generate_audit_report()`
5. Keep `_stage_image_audit` and `_stage_rendered_layout_audit` unchanged

### Phase 2 — Config Integration

1. Implement `ka11y/config/loader.py` — `KA11yConfig` class
2. Create `config/crawlers.config.yml`, `config/languages/en.yml`, `config/languages/ja.yml`
3. Inject config into `UniversalStaticCrawler._build_combined_js()`
4. Replace hardcoded CJK CSS in `rendered_layout_crawler.py` with `config.get_text_spacing_flags()`
5. Replace hardcoded transcript keywords in `MediaAuditor` with `config.get_keyword_list("transcript_keywords")`
6. Replace hardcoded sensory word lists in `SensoryCharacteristicsAuditor` with config lookup

### Phase 3 — Deduplication Fix (BUG-003)

```python
# findings.py — add before returning from _run_python_stages

def _deduplicate_1412(findings: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out = []
    for f in findings:
        if f.get("wcag_sc") == "1.4.12":
            el = f.get("element") or {}
            key = ("1.4.12", f.get("status", ""), (el.get("html") or "")[:80])
            if key in seen:
                continue
            seen.add(key)
        out.append(f)
    return out
```

### Phase 4 — `RuleExtractor` Protocol

Refactor each JS section of `universal_page.py` into `ka11y/crawler/extractors/*.py`. `UniversalStaticCrawler` assembles combined JS dynamically from `STATIC_EXTRACTORS` at startup.

---

## 12. Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `ka11y/crawler/extractor_protocol.py` | `RuleExtractor` Protocol |
| `ka11y/crawler/extractors/__init__.py` | `STATIC_EXTRACTORS` list |
| `ka11y/crawler/extractors/forms.py` | `FormsExtractor` |
| `ka11y/crawler/extractors/interactive.py` | `InteractiveExtractor` |
| `ka11y/crawler/extractors/target_size.py` | `TargetSizeExtractor` |
| `ka11y/crawler/extractors/moving_content.py` | `MovingContentExtractor` |
| `ka11y/crawler/extractors/media.py` | `MediaExtractor` |
| `ka11y/crawler/extractors/text_spacing.py` | `TextSpacingExtractor` |
| `ka11y/crawler/extractors/sensory.py` | `SensoryExtractor` |
| `ka11y/crawler/universal_static_crawler.py` | Refactored loader + config injection + smart wait |
| `ka11y/config/loader.py` | `KA11yConfig` class (replaces empty `config/__init__.py`) |
| `config/crawlers.config.yml` | Extractor + independent crawler registry |
| `config/languages/en.yml` | English keyword lists |
| `config/languages/ja.yml` | Japanese keyword lists (matches PLUGPLAY_CONFIG_PLAN.md schema) |

### Modified Files

| File | What Changes | Bug Fixed |
|------|-------------|-----------|
| `ka11y/crawler/universal_page.py` | Add `sensory` section to combined JS; add fields to `PageSnapshot` | BUG-001 prep |
| `ka11y/api/v1/combined/stages.py` | Replace 7 crawler calls with `UniversalStaticCrawler.load()`; add `config` param | BUG-001 |
| `ka11y/api/v1/combined/findings.py` | Add `_deduplicate_1412()` | BUG-003 |
| `ka11y/crawler/interactive_crawler.py` | `document.querySelectorAll` → `queryShadow` | BUG-002 |
| `ka11y/crawler/forms_crawler.py` | Shadow DOM, orphan inputs, commit fallback, logger | BUG-002, 006, 010, 011 |
| `ka11y/crawler/moving_content_crawler.py` | Add `duration_known` field | BUG-004 |
| `ka11y/crawler/target_size_crawler.py` | `Math.round` → `Math.ceil` for offset | BUG-005 |
| `ka11y/crawler/rendered_layout_crawler.py` | Config-driven CJK CSS builder | BUG-007 |
| `ka11y/accessibility/rules/media/media_auditor.py` | Config-based transcript keywords | Config |
| `ka11y/accessibility/rules/non_text/sensory_auditor.py` | Config-based sensory word lists | Config |

---

## Summary: Before vs After

| Metric | Before (verified) | After (proposed) |
|--------|-------------------|-----------------|
| Browser launches per audit | **9** | **3** (static + image + rendered) |
| Page loads per audit | **9** | **3** |
| JS wait strategy | **2000ms / 1500ms / none** (per crawler) | **DOM stability observer** |
| JS helpers (copies) | **4 copies, diverging** | **1 canonical** |
| Shadow DOM support | **❌ 6 of 7 crawlers** | **✅ all via queryShadow** |
| Language-aware extraction | **❌ hardcoded EN** | **✅ config-injected JS constants** |
| CJK text-spacing CSS | **❌ hardcoded** | **✅ config flags** |
| 1.4.12 dedup | **❌ double violations** | **✅ pre-merge dedup** |
| Null video duration | **❌ false positives** | **✅ duration_known flag** |
| Target size precision | **❌ Math.round** | **✅ Math.ceil** |
| `config/__init__.py` | **empty** | **KA11yConfig loader** |
| Adding new WCAG rule | **touch 5+ files, new browser** | **1 extractor file + register** |
