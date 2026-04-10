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
8. [Proposed Architecture: Universal Production Crawler](#8-proposed-architecture-universal-production-crawler)
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

### 3.10 `UniversalPageLoader` — `universal_page.py` (UNUSED / PARTIAL)

- **Purpose:** Load the page once, extract all static data in one `evaluate()` pass, optionally record a HAR
- **Status:** ✅ Implemented — ❌ **not wired into the pipeline** — ❌ **not production-ready as-is**
- **Verification:** `grep -rn "UniversalPageLoader" ka11y/api/` → 0 matches
- **Wait strategy (lines 701–731):**
  1. `domcontentloaded` (30s) → fallback `commit` (15s)
  2. `networkidle` (15s, best-effort)
  3. Poll SPA signals: `__NEXT_DATA__`, `__nuxt`, `__vue_app__`, `window.React`, `window.angular`, `window.Ember`, `window.__svelte`, `[data-reactroot]`
  4. DOM stability: MutationObserver, 600ms no mutations, 12s max
  5. Lazy-scroll (6 steps) + IntersectionObserver trigger
  6. Second stability check
  7. Single `page.evaluate(_COMBINED_EXTRACT_JS)`
- **Shadow DOM:** ⚠️ Partial
  - Forms / interactive / target sizes use `queryShadow()`
  - Moving content / media / text spacing still use `document.querySelectorAll(...)`
  - Label and ARIA ID resolution still uses `document.querySelector(...)` / `document.getElementById(...)`, so shadow-contained labels and `aria-describedby` targets can still be missed
  - Forms found in a shadow root still use `form.querySelectorAll(...)`, so nested shadow descendants under that form are missed
- **Iframe:** ❌ No frame-tree traversal
- **Output contract:** ❌ Raw dict lists only; does not normalize into existing Pydantic models
- **HAR recording:** ⚠️ Saved to `session.har`, but current `RenderedLayoutCrawler` cannot consume it
- **Combined JS output:** `{ forms, interactive, target_sizes, moving_content, media, text_spacing }`
- **Missing:** `sensory`, same-origin frame extraction, cross-origin frame metadata, canonical element identity, extractor error reporting, normalization layer

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

### BUG-002 · HIGH — Shadow DOM Support Is Incomplete Across Both Legacy Crawlers And `UniversalPageLoader`

**Files:** `forms_crawler.py:93`, `interactive_crawler.py:209`, `media_crawler.py`, `moving_content_crawler.py`, `target_size_crawler.py`, `sensory_crawler.py`, `universal_page.py`

Six of the seven legacy static crawlers still use `document.querySelectorAll(...)`, so open shadow roots are invisible. `universal_page.py` only partially fixes this: forms / interactive / target sizes use `queryShadow()`, but moving content / media / text spacing still do not, and shadow-root label resolution is still document-scoped. Shadow coverage is therefore incomplete in both the current runtime and the current redesign draft.

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

### BUG-012 · HIGH — `UniversalPageLoader` Still Misses Labels / ARIA References Inside Shadow Roots

**Files:** `universal_page.py:115–124`, `universal_page.py:145–155`, `universal_page.py:208`, `universal_page.py:212`, `universal_page.py:226`, `universal_page.py:552–555`

The combined extractor finds some elements via `queryShadow()`, but helper resolution still relies on `document.getElementById(...)`, `document.querySelector(...)`, and `form.querySelectorAll(...)`. Those calls do not pierce shadow boundaries, so fields inside shadow roots can still lose:

- explicit `<label for="...">` matches
- `aria-labelledby` text
- `aria-describedby` error text
- nested controls under a discovered shadow-contained `<form>`

The production fix has to be root-aware, not just selector-aware.

---

### BUG-013 · HIGH — No Same-Origin Frame Tree Extraction In The Universal Path

**Files:** `universal_page.py`, all static crawlers

The current plan still treats the page as a single DOM. In reality, Playwright exposes `page.frames()`, and accessibility-relevant DOM often lives in same-origin frames (checkout widgets, embedded account areas, CMS blocks, custom players). Without a frame-tree walk, the "universal" crawler is not actually universal.

---

### BUG-014 · MEDIUM — `UniversalPageLoader` Keeps The Same `commit` Fallback Problem As Legacy Crawlers

**Files:** `universal_page.py:769–781`

`_navigate()` falls back to `wait_until="commit"` exactly like the legacy crawlers. That may return a partially hydrated or effectively empty DOM while the extraction still appears successful. The plan needs explicit partial-extraction signaling, not silent continuation.

---

### BUG-015 · MEDIUM — Raw Snapshot Has No Canonical Element Identity Or Partial-Extraction Schema

**Files:** `universal_page.py`, `runner.py`, `findings.py`

The current raw snapshot only contains per-rule dict lists. It does not carry a stable `element_ref` / frame path / shadow host chain / selector hint sidecar, and it does not distinguish complete extraction from partial extraction. This blocks robust deduplication, frame-aware evidence, and safe rollback diagnostics.

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

## 8. Proposed Architecture: Universal Production Crawler

### Design Principle
> Load the static DOM once, extract across the full same-origin frame tree and open shadow roots, normalize into the current Pydantic models, and keep provenance in a sidecar so auditors stay unchanged while findings become deduplicable and production-traceable.

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                               KA11yConfig                                   │
│   crawlers.config.yml + languages/{lang}.yml + site-profiles/*.yml         │
│   (optional profile resolved at runtime from request URL / host / rules)   │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│             UniversalCrawlerEngine  (1 browser, 1 root page load)           │
│                                                                              │
│  1. goto(url) + smart wait + lazy-load trigger                              │
│  2. enumerate page.frames()                                                 │
│  3. same-origin frames  -> run combined extractor bundle                    │
│  4. cross-origin frames -> record frame metadata + limitation reason        │
│  5. aggregate RawPageSnapshot + ElementRef sidecar + extractor errors       │
│  6. optionally persist storage_state.json for future crawler reuse          │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ RawPageSnapshot
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                             SnapshotNormalizer                              │
│                                                                              │
│  raw.forms          -> List[FormInputData]                                  │
│  raw.interactive    -> List[InteractiveElementData]                         │
│  raw.target_sizes   -> List[TargetSizeData]                                 │
│  raw.moving_content -> List[MovingContentData]                              │
│  raw.media          -> List[MediaElementData]                               │
│  raw.text_spacing   -> List[TextSpacingData]                                │
│  raw.sensory        -> List[SensoryElementData]                             │
│                                                                              │
│  sidecar: ref_id -> frame_path / frame_url / shadow_host_chain / selector   │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │ NormalizedSnapshot
         ┌──────────────────────┼────────────────────────────────────────┐
         ▼                      ▼                                        ▼
 FormAccessibility        LabelInName / Target /                 Media / Sensory /
 Auditor                  PauseStopHide / TextSpacing            other static auditors
 (existing signatures)    (existing signatures)                  (existing signatures)
         │
         └─ all static auditors run in parallel via `asyncio.to_thread(...)`

Keep separate browsers:
  AsyncImageCrawler      -> screenshots + OCR + contrast
  RenderedLayoutCrawler  -> multi-viewport rendering + focus/hover scenarios

Future optimization:
  reuse `storage_state.json` once image/rendered crawlers support it
  do NOT plan around HAR replay until a real consumer exists
```

### 8.1 The `RuleExtractor` Protocol

```python
# ka11y/crawler/extractor_protocol.py

from typing import Any, Callable, Protocol, Sequence
from pydantic import BaseModel


class RuleExtractor(Protocol):
    id: str
    snapshot_field: str
    js_extract: str
    model_class: type[BaseModel]
    normalizer: Callable[[Sequence[dict[str, Any]], "NormalizationContext"], list[BaseModel]]
    language_assets: list[str]
```

This is the key difference from the current draft: extractors do not stop at raw dicts. Every extractor must declare how its raw payload becomes the existing model class already consumed by the auditor.

### 8.2 Smart Wait + Frame Walk

```python
async def collect_static_snapshot(page, root_url: str) -> RawPageSnapshot:
    await _wait_for_dom_stability(page)
    await _lazy_scroll(page)
    await _wait_for_dom_stability(page)

    same_origin_frames = []
    cross_origin_frames = []

    for frame in page.frames:
        if _is_same_origin(root_url, frame.url):
            same_origin_frames.append(await _extract_frame(frame))
        else:
            cross_origin_frames.append(_frame_metadata(frame, reason="cross_origin"))

    return _merge_frame_snapshots(
        root_url=root_url,
        frame_snapshots=same_origin_frames,
        cross_origin_frames=cross_origin_frames,
    )
```

Production rules for this layer:

- One root navigation, not seven duplicate static crawler loads
- Same-origin iframes are first-class citizens, not post-hoc exceptions
- Cross-origin iframes are not silently ignored; they produce structured limitations
- `commit` fallback must set a partial-extraction flag when DOM completeness is uncertain
- Extraction may run as one combined JS bundle per same-origin frame, but payload size must stay bounded for large pages

### 8.3 SnapshotNormalizer (mandatory, not optional)

```python
class SnapshotNormalizer:
    @staticmethod
    def normalize(raw: RawPageSnapshot) -> NormalizedSnapshot:
        ctx = NormalizationContext(
            root_url=raw.page_url,
            element_refs=raw.element_refs,
            bucket_ref_ids=raw.bucket_ref_ids,
        )

        return NormalizedSnapshot(
            page_url=raw.page_url,
            forms=[FormInputData(page_url=raw.page_url, **item) for item in raw.forms],
            interactive=[InteractiveElementData(page_url=raw.page_url, **item) for item in raw.interactive],
            target_sizes=[TargetSizeData(page_url=raw.page_url, **item) for item in raw.target_sizes],
            moving_content=[MovingContentData(page_url=raw.page_url, **item) for item in raw.moving_content],
            media=[MediaElementData(page_url=raw.page_url, **item) for item in raw.media],
            text_spacing=[TextSpacingData(page_url=raw.page_url, **item) for item in raw.text_spacing],
            sensory=[SensoryElementData(page_url=raw.page_url, **item) for item in raw.sensory],
            element_refs=raw.element_refs,
            bucket_ref_ids=raw.bucket_ref_ids,
            extractor_errors=raw.extractor_errors,
            cross_origin_frames=raw.cross_origin_frames,
        )
```

Important compatibility rule:

- `page_url` stays the audited root URL for backward compatibility with current reports
- frame-specific provenance lives in the sidecar, not inside the current model classes
- `MediaAuditor` can keep receiving `model_dump()` output until its signature is made typed

### 8.4 Refactored `_run_python_stages`

```python
async def _run_python_stages(..., config: KA11yConfig):
    raw_snapshot = await UniversalCrawlerEngine.load(
        url=url,
        output_dir=output_dir,
        config=config,
    )
    snapshot = SnapshotNormalizer.normalize(raw_snapshot)

    image_task = asyncio.create_task(_stage_image_audit(url, output_dir, ...))
    rendered_task = asyncio.create_task(
        _stage_rendered_layout_audit(url, output_dir, ...)
    )

    results = await asyncio.gather(
        asyncio.to_thread(_run_form_auditor, snapshot.forms, output_dir),
        asyncio.to_thread(_run_lin_auditor, snapshot.interactive, output_dir),
        asyncio.to_thread(_run_ts_auditor, snapshot.target_sizes, output_dir),
        asyncio.to_thread(_run_psh_auditor, snapshot.moving_content, output_dir),
        asyncio.to_thread(_run_media_auditor, [m.model_dump() for m in snapshot.media], output_dir),
        asyncio.to_thread(_run_tsp_auditor, snapshot.text_spacing, output_dir),
        asyncio.to_thread(_run_sensory_auditor, snapshot.sensory, output_dir, lang),
        image_task,
        rendered_task,
        return_exceptions=True,
    )

    return _enrich_and_dedup(flatten(results), snapshot.element_refs), contrast_report
```

This keeps the auditor contracts stable and removes the unsupported `har_path -> RenderedLayoutCrawler` assumption from the near-term design.

### 8.5 Snapshot Contracts

```python
@dataclass
class ElementRef:
    ref_id: str
    extractor: str
    frame_path: str
    frame_url: str
    selector_hint: Optional[str] = None
    element_id: Optional[str] = None
    shadow_host_chain: List[str] = field(default_factory=list)
    html_snippet: str = ""


@dataclass
class RawPageSnapshot:
    page_url: str
    forms: List[Dict[str, Any]] = field(default_factory=list)
    interactive: List[Dict[str, Any]] = field(default_factory=list)
    target_sizes: List[Dict[str, Any]] = field(default_factory=list)
    moving_content: List[Dict[str, Any]] = field(default_factory=list)
    media: List[Dict[str, Any]] = field(default_factory=list)
    text_spacing: List[Dict[str, Any]] = field(default_factory=list)
    sensory: List[Dict[str, Any]] = field(default_factory=list)
    element_refs: Dict[str, ElementRef] = field(default_factory=dict)
    bucket_ref_ids: Dict[str, List[str]] = field(default_factory=dict)
    cross_origin_frames: List[Dict[str, str]] = field(default_factory=list)
    extractor_errors: List[str] = field(default_factory=list)
    storage_state_path: Optional[str] = None


@dataclass
class NormalizedSnapshot:
    page_url: str
    forms: List[FormInputData] = field(default_factory=list)
    interactive: List[InteractiveElementData] = field(default_factory=list)
    target_sizes: List[TargetSizeData] = field(default_factory=list)
    moving_content: List[MovingContentData] = field(default_factory=list)
    media: List[MediaElementData] = field(default_factory=list)
    text_spacing: List[TextSpacingData] = field(default_factory=list)
    sensory: List[SensoryElementData] = field(default_factory=list)
    element_refs: Dict[str, ElementRef] = field(default_factory=dict)
    bucket_ref_ids: Dict[str, List[str]] = field(default_factory=dict)
    cross_origin_frames: List[Dict[str, str]] = field(default_factory=list)
    extractor_errors: List[str] = field(default_factory=list)
```

### 8.6 Production Edge Cases

| Scenario | Required behavior |
|----------|-------------------|
| Open shadow roots | Traverse recursively for every static extractor, not just three buckets |
| Nested shadow descendants inside a discovered `<form>` | Use `queryShadow(form, ...)`, not `form.querySelectorAll(...)` |
| Labels / `aria-labelledby` / `aria-describedby` inside shadow roots | Resolve references in the current DOM root / host chain, not only via `document.*` |
| Closed shadow roots | Record an explicit limitation; never silently PASS because content was inaccessible |
| Same-origin iframes | Extract fully and merge with `frame_path` provenance |
| Cross-origin iframes | Record frame metadata and emit `needs_review` only when the rule depends on inaccessible content |
| SPA hydration that never fully settles | Time-box waiting, mark extraction as partial, continue with warning |
| Very large DOMs / huge sensory pages | Enforce payload budgets, truncate evidence, and allow chunked extraction if one giant payload is unsafe |
| Unknown media duration | Carry `duration_known=False`; auditor returns `needs_review`, not false FAIL |
| Repeated components with near-identical HTML | Deduplicate by canonical element ref, not truncated HTML prefixes |
| Japanese / CJK pages | Use language packs for transcript keywords, sensory taxonomies, stop words, instruction patterns, and text-spacing flags |
| Consent banners / overlays / lazy loaders | Preserve DOM-stability warning state; do not treat partially loaded extraction as clean PASS evidence |

---

## 9. Config Integration

### Current State

`ka11y/config/__init__.py` is **an empty file**. No `KA11yConfig` loader exists yet.

Language support today is **fragmented, not absent**:

- `_lang_ctx: ContextVar[str]` localizes WCAG names and suggested fixes in `findings.py`
- `MediaAuditor` already hardcodes EN + JA transcript keywords
- `SensoryCharacteristicsAuditor` already contains EN + JA taxonomies, stop words, instruction patterns, and CJK heuristics
- `RenderedLayoutCrawler` already hardcodes CJK text-spacing exceptions in CSS

What is missing is a single config source that preserves that behavior while making it injectable into the crawler and auditors.

### Site Overrides Must Be Runtime-Resolved

Site-specific overrides are **optional runtime profiles**, not a fixed compile-time `site_id`.

The production shape should be:

- request comes in with a URL
- config layer resolves zero-or-one matching site profile from host / path / framework hints / explicit override
- crawler uses the merged config view: global defaults -> language assets -> resolved site profile

That means the config contract should look like:

```yaml
site_profiles:
  - id: "shopify_generic"
    match:
      host_suffixes: ["myshopify.com"]
      frameworks: ["shopify"]
    overrides:
      consent_banner_selectors: [".shopify-policy__container"]

  - id: "example_checkout"
    match:
      host_regex: "^checkout\\.example\\.com$"
      path_prefixes: ["/jp/", "/checkout/"]
    overrides:
      lazy_load_wait_ms: 2500
```

Important rule:

- the plan should never assume `sites/{site_id}.yml` is known ahead of time
- site profiles are discovered dynamically per request
- if nothing matches, the crawler runs with global + language config only

### `crawlers.config.yml` — Revised Schema

```yaml
version: "3.0"

static_extractors:
  - id: "FormsExtractor"
    snapshot_field: "forms"
    model: "FormInputData"
    normalizer: "normalize_forms"
    auditor: "FormAccessibilityAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets: ["required_field_patterns"]

  - id: "InteractiveExtractor"
    snapshot_field: "interactive"
    model: "InteractiveElementData"
    normalizer: "normalize_interactive"
    auditor: "LabelInNameAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets: []

  - id: "TargetSizeExtractor"
    snapshot_field: "target_sizes"
    model: "TargetSizeData"
    normalizer: "normalize_target_sizes"
    auditor: "TargetSizeAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets: []

  - id: "MovingContentExtractor"
    snapshot_field: "moving_content"
    model: "MovingContentData"
    normalizer: "normalize_moving_content"
    auditor: "PauseStopHideAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets: ["pause_keywords"]

  - id: "MediaExtractor"
    snapshot_field: "media"
    model: "MediaElementData"
    normalizer: "normalize_media"
    auditor: "MediaAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets:
      - "media.transcript_keywords"
      - "media.alternative_keywords"

  - id: "TextSpacingExtractor"
    snapshot_field: "text_spacing"
    model: "TextSpacingData"
    normalizer: "normalize_text_spacing"
    auditor: "TextSpacingAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets: ["text_spacing"]

  - id: "SensoryExtractor"
    snapshot_field: "sensory"
    model: "SensoryElementData"
    normalizer: "normalize_sensory"
    auditor: "SensoryCharacteristicsAuditor"
    enabled: true
    frame_scope: "same_origin_all_frames"
    shadow_scope: "open_shadow_roots"
    language_assets:
      - "sensory.categories"
      - "sensory.generic_ui_nouns"
      - "sensory.stop_words"
      - "sensory.instruction_patterns"
      - "sensory.quote_pairs"
      - "sensory.cjk_ratio_threshold"

independent_crawlers:
  - id: "AsyncImageCrawler"
    enabled: true
    reuse_storage_state: "future"

  - id: "RenderedLayoutCrawler"
    enabled: true
    reuse_storage_state: "future"
    language_assets: ["text_spacing"]
```

### `languages/ja.yml` — Minimum Viable Japanese Coverage

```yaml
media:
  transcript_keywords:
    - "書き起こし"
    - "文字起こし"
    - "トランスクリプト"
    - "字幕"
    - "キャプション"
    - "テキスト版"

sensory:
  categories:
    color: ["赤", "青", "緑", "黄色", "白", "黒"]
    shape: ["丸", "円形", "四角", "三角形"]
    size: ["大きい", "小さい", "大", "小"]
    position: ["左", "右", "上", "下", "中央"]
    orientation: ["横向き", "縦向き", "水平", "垂直"]
    sound: ["音", "通知音", "ベル", "ブザー"]
    brightness: ["明るい", "暗い", "光る"]
    texture: ["滑らか", "粗い", "ざらざら"]
  generic_ui_nouns:
    - "ボタン"
    - "リンク"
    - "入力欄"
    - "チェックボックス"
    - "ラジオボタン"
  stop_words:
    - "の"
    - "に"
    - "は"
    - "を"
    - "が"
    - "ください"
  instruction_patterns:
    - "クリック"
    - "選択"
    - "入力"
    - "押して"
  quote_pairs:
    - ["「", "」"]
    - ["『", "』"]
  cjk_ratio_threshold: 0.15

text_spacing:
  apply_letter_spacing: false
  apply_word_spacing: false
```

### Cross-Repo Language Contract (`ka11y-python` + `ka11y-node`)

Japanese support must be treated as a **behavioral config problem across both services**, not only a report-localization problem.

| Layer | Current state | Required production state |
|-------|---------------|---------------------------|
| `ka11y-python` crawler/auditor behavior | JP/CJK logic exists but is scattered and partly hardcoded | Read crawler + auditor behavior from `config/languages/ja.yml` |
| `ka11y-node` finding text | Already localized via `i18n/locales/ja.yml` and `lang='ja'` | Keep as-is |
| `ka11y-node` custom-check behavior | JP/CJK keywords and thresholds are still embedded in JS checks | Move to config-backed language assets |
| Cross-repo consistency | Python and node can drift on transcript keywords, CJK thresholds, support-widget labels, etc. | Keep aligned asset keys across both repos |

Verified node-side current state:

- `analyseUrlFlat(url, level, lang)` already accepts `lang` and passes it to the result mappers
- `rulesLoader.js` already merges `i18n/rules.yml` with `i18n/locales/ja.yml`
- custom-check behavior still embeds JP/CJK logic directly in checks such as:
  - `audio-transcript.check.js`
  - `pointer-cancellation.check.js`
  - `consistent-help.check.js`
  - `link-purpose.check.js`
  - `error-prevention.check.js`
  - `redundant-entry.check.js`
  - `multiple-ways.check.js`
  - `pronunciation.check.js`

Shared asset families that should stay aligned across both repos:

```yaml
media:
  transcript_keywords: [...]
interaction:
  action_verbs: [...]
navigation:
  search_terms: [...]
support:
  help_widget_labels: [...]
commerce:
  high_risk_terms: [...]
cjk:
  lang_prefixes: ["ja", "ja-JP", "zh", "zh-TW", "zh-CN", "ko"]
  ratio_threshold: 0.15
  ruby_coverage_threshold: 0.30
```

### Rendered Text Spacing: Config-Driven CSS

```python
flags = config.get_text_spacing_flags()   # from languages/ja.yml text_spacing block
css = "\n".join(filter(None, [
    "* { line-height: 1.5 !important; }",
    "* { letter-spacing: 0.12em !important; }" if flags.apply_letter_spacing else "",
    "* { word-spacing: 0.16em !important; }"   if flags.apply_word_spacing   else "",
    "p,li,dt,dd,blockquote { margin-bottom: 2em !important; }",
]))
```

This preserves the current Japanese / CJK behavior instead of flattening it down to a few word lists. The present draft under-scoped this migration.

### Adding a New WCAG Rule

1. `ka11y/crawler/extractors/new_rule.py` — implement `RuleExtractor`
2. `ka11y/crawler/snapshot_normalizer.py` — add the raw-to-model adapter
3. Register the extractor in `STATIC_EXTRACTORS`
4. Add language assets to `config/languages/*.yml` if the rule is language-sensitive
5. Register the rule in `crawlers.config.yml`
6. Add or reuse a findings converter if the auditor produces a new report shape

**No new static browser launch. No new static page load.**

---

## 10. Complete Field Contract

> Verified from source — what each auditor actually reads today. The universal crawler must normalize to these fields exactly. Frame / shadow / extraction-status provenance should live beside these models, not replace them.

### Shared Provenance Sidecar (new, not part of current models)

| Field | Used For |
|-------|---------|
| `ref_id` | Stable join key across raw snapshot, normalized snapshot, and final findings |
| `extractor` | Which bucket produced the element |
| `frame_path` | Distinguish identical markup in different iframes |
| `frame_url` | Evidence and limitation reporting |
| `shadow_host_chain` | Debugging and shadow-root provenance |
| `selector_hint` | Preferred `element.target` in final findings |
| `element_id` | Fallback identity for reports |
| `partial_extraction` | Prevent false confidence when extraction was incomplete |

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

### Phase 0 — Correctness Hardening Before Cutover

| Bug | File | Change |
|-----|------|--------|
| BUG-002 | `forms_crawler.py`, `interactive_crawler.py`, `media_crawler.py`, `moving_content_crawler.py`, `target_size_crawler.py`, `text_spacing_crawler.py`, `sensory_crawler.py` | Use shared shadow-aware helpers where feasible so the parity baseline improves before replacement |
| BUG-012 | `universal_page.py` | Replace document-scoped label / ID resolution with root-aware helpers; use `queryShadow(form, ...)` for nested controls |
| BUG-004 | `moving_content_crawler.py` | Add `duration_known` and downgrade unknown-duration cases to `needs_review` |
| BUG-005 | `target_size_crawler.py` | `Math.round` → `Math.ceil` for required offsets |
| BUG-006 | `forms_crawler.py` | Collect orphan controls regardless of whether any `<form>` exists |
| BUG-007 | `rendered_layout_crawler.py` | Build text-spacing CSS from config instead of hardcoded CJK rules |
| BUG-010 / BUG-014 | `forms_crawler.py`, `interactive_crawler.py`, `universal_page.py` | `commit` fallback must emit a partial-extraction warning instead of silently looking successful |
| BUG-011 | `forms_crawler.py`, `interactive_crawler.py` | `print()` → structured logger |

### Phase 1 — Build The Universal Raw Extraction Engine

1. Keep `universal_page.py` as the entrypoint, but refactor it into a true `UniversalCrawlerEngine`.
2. Add the missing `sensory` bucket.
3. Traverse `page.frames()` and extract all same-origin frames.
4. Record cross-origin frames as structured limitations instead of silent misses.
5. Emit `ElementRef`, `bucket_ref_ids`, `extractor_errors`, and `cross_origin_frames` alongside the raw buckets.
6. Persist `universal_raw_snapshot.json` for debugging and rollout diffing.

### Phase 2 — Normalize Into Existing Pydantic Models

1. Implement `ka11y/crawler/snapshot_normalizer.py`.
2. Convert every raw bucket into the existing models:
   - `FormInputData`
   - `InteractiveElementData`
   - `TargetSizeData`
   - `MovingContentData`
   - `MediaElementData`
   - `TextSpacingData`
   - `SensoryElementData`
3. Persist `universal_normalized_snapshot.json`.
4. Keep auditor signatures unchanged.
5. Keep frame/shadow identity in the sidecar rather than forcing model-class changes in Phase 2.

### Phase 3 — Integrate Into `stages.py`

1. Replace the seven static crawler loads with one universal load when any static rule is enabled.
2. Fan out the normalized model lists to the existing auditors in parallel.
3. Keep `_stage_image_audit()` unchanged in this phase.
4. Keep `_stage_rendered_layout_audit()` unchanged in this phase.
5. Do **not** pass `har_path` into rendered layout until a real consumer exists.
6. Optional later optimization: pass `storage_state.json` once the image and rendered crawlers accept it.

### Phase 4 — Finding Enrichment And Deduplication

```python
def _finding_key(finding: dict) -> tuple[str, str, str]:
    ref_id = finding.get("element_ref_id") or ""
    el = finding.get("element") or {}
    selector = ((el.get("target") or [""])[0] if isinstance(el.get("target"), list) else "") or ""
    element_id = el.get("element_id") or ""
    html = (el.get("html") or "")[:120].lower()
    return (
        finding.get("wcag_sc", ""),
        finding.get("status", ""),
        ref_id or selector or element_id or html,
    )
```

Rules for this phase:

- Enrich Python findings with `element_ref_id` and `selector_hint` from the sidecar
- Use canonical element identity before falling back to HTML snippets
- Deduplicate structural and rendered `1.4.12` findings only when they truly target the same element
- Keep separate findings when the two `1.4.12` paths point at different elements or different failure modes

### Phase 5 — Config And Language Externalization

1. Implement `ka11y/config/loader.py` and load `config/crawlers.config.yml`.
2. Create `config/languages/en.yml` and `config/languages/ja.yml`.
3. Migrate current hardcoded EN / JA / CJK logic into config without changing behavior.
4. Inject only the needed language assets into each extractor.
5. Move rendered text-spacing CSS generation to language config.
6. Add runtime-resolved site profiles for framework-specific selectors, consent banners, or known page-behavior quirks.

### Phase 6 — Parity, Performance, And Rollout Gates

1. Add parity tests comparing legacy crawler output vs universal normalized output for all seven static rule families.
2. Add dedicated fixtures for:
   - open shadow DOM
   - nested shadow-root forms
   - same-origin iframe content
   - cross-origin iframe limitations
   - orphan controls
   - duplicate repeated components
   - unknown video duration
   - Japanese / CJK pages
   - large DOM payloads
3. Add performance budgets:
   - one static root page load
   - bounded extraction payload size
   - bounded wait time
   - bounded memory growth on large pages
4. Roll out behind a feature flag.
5. Retire legacy static crawlers only after parity + performance gates pass.

---

## 12. Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `ka11y/crawler/extractor_protocol.py` | `RuleExtractor` Protocol |
| `ka11y/crawler/element_ref.py` | Canonical element identity / provenance sidecar |
| `ka11y/crawler/snapshot_normalizer.py` | Raw snapshot -> existing Pydantic models |
| `ka11y/crawler/extractors/__init__.py` | `STATIC_EXTRACTORS` list |
| `ka11y/crawler/extractors/forms.py` | `FormsExtractor` |
| `ka11y/crawler/extractors/interactive.py` | `InteractiveExtractor` |
| `ka11y/crawler/extractors/target_size.py` | `TargetSizeExtractor` |
| `ka11y/crawler/extractors/moving_content.py` | `MovingContentExtractor` |
| `ka11y/crawler/extractors/media.py` | `MediaExtractor` |
| `ka11y/crawler/extractors/text_spacing.py` | `TextSpacingExtractor` |
| `ka11y/crawler/extractors/sensory.py` | `SensoryExtractor` |
| `ka11y/config/loader.py` | `KA11yConfig` class (replaces empty `config/__init__.py`) |
| `config/crawlers.config.yml` | Extractor + independent crawler registry |
| `config/languages/en.yml` | English keyword lists and text-spacing flags |
| `config/languages/ja.yml` | Japanese keyword lists, instruction patterns, quote pairs, and text-spacing flags |
| `tests/test_universal_snapshot_normalizer.py` | Verifies raw -> model normalization |
| `tests/test_universal_crawler_parity.py` | Legacy crawler vs universal parity tests |
| `tests/test_universal_shadow_iframe.py` | Shadow-root and iframe edge-case coverage |

### Modified Files

| File | What Changes | Bug Fixed |
|------|-------------|-----------|
| `ka11y/crawler/universal_page.py` | Refactor into frame-aware raw extractor; add `sensory`, sidecar identity, partial-extraction reporting | BUG-001, 012, 013, 014, 015 |
| `ka11y/api/v1/combined/stages.py` | Replace 7 static crawler calls with one universal load + normalization path | BUG-001 |
| `ka11y/api/v1/combined/findings.py` | Enrich findings with canonical element refs before dedup | BUG-003, 015 |
| `ka11y/api/v1/combined/runner.py` | Use canonical dedup key instead of HTML-prefix-only fallback | BUG-003, 015 |
| `ka11y/crawler/forms_crawler.py` | Shared shadow helpers, orphan controls, partial-extraction warnings, logger | BUG-002, 006, 010, 011 |
| `ka11y/crawler/interactive_crawler.py` | Shared shadow helpers, partial-extraction warnings | BUG-002, 010 |
| `ka11y/crawler/media_crawler.py` | Shared shadow helpers for parity baseline | BUG-002 |
| `ka11y/crawler/moving_content_crawler.py` | `duration_known`, shared shadow helpers, better pause-control detection hooks | BUG-002, 004 |
| `ka11y/crawler/target_size_crawler.py` | `Math.round` → `Math.ceil`, shared shadow helpers | BUG-002, 005 |
| `ka11y/crawler/text_spacing_crawler.py` | Shared shadow helpers for parity baseline | BUG-002 |
| `ka11y/crawler/sensory_crawler.py` | Shared shadow helpers for parity baseline | BUG-002 |
| `ka11y/crawler/rendered_layout_crawler.py` | Config-driven text-spacing CSS builder | BUG-007 |
| `ka11y/accessibility/rules/media/media_auditor.py` | Config-based transcript / alternative keywords | Config |
| `ka11y/accessibility/rules/non_text/sensory_auditor.py` | Config-based JA / EN sensory assets without losing current heuristics | Config |
| `tests/test_combined_findings.py` | Add canonical dedup coverage for `1.4.12` | BUG-003 |

---

## Summary: Before vs After

| Metric | Before (verified) | After (proposed) |
|--------|-------------------|-----------------|
| Browser launches per audit | **9** | **3** steady-state (static + image + rendered) |
| Static page loads per audit | **7 duplicate loads** | **1** |
| Static data contract | **independent crawler outputs** | **raw snapshot + normalized existing Pydantic models** |
| JS wait strategy | **2000ms / 1500ms / none** (per crawler) | **DOM-stability + lazy-load + partial-extraction signaling** |
| JS helpers (copies) | **4 copies, diverging** | **1 canonical helper set** |
| Shadow DOM support | **❌ inconsistent** | **✅ open-shadow recursive + root-aware label resolution** |
| iFrame coverage | **❌ none** | **✅ same-origin extraction + cross-origin limitation records** |
| Language support | **fragmented hardcoded EN / JA / CJK** | **central config preserving current JA behavior** |
| CJK text-spacing CSS | **❌ hardcoded** | **✅ language-pack flags** |
| 1.4.12 dedup | **❌ HTML-prefix collisions / misses** | **✅ canonical element-ref dedup** |
| Unknown media duration | **❌ false FAIL risk** | **✅ `needs_review` path** |
| Target size precision | **❌ Math.round** | **✅ Math.ceil** |
| Rendered integration | **❌ unsupported HAR assumption** | **✅ phase-separated, optional future storage-state reuse** |
| Rollout safety | **❌ no parity plan** | **✅ parity + performance gates before retirement** |
| Adding new static WCAG rule | **touch 5+ files, new page load risk** | **extractor + normalizer + config registration; no new static page load** |
