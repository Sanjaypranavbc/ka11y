# ka11y-python — Complete Architecture & Audit Analysis

> Generated: 2026-04-06 | Auditor Version: current `pranav` branch

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Crawler Modules — Data Dictionary](#2-crawler-modules--data-dictionary)
3. [Checker/Auditor Modules](#3-checkerauditor-modules)
4. [Live Audit Results — 5 Websites](#4-live-audit-results--5-websites)
5. [Rule Limitation Analysis](#5-rule-limitation-analysis)
6. [Japanese Language Limitations](#6-japanese-language-limitations)
7. [Known Bugs & Issues](#7-known-bugs--issues)
8. [Universal Crawler — Existing vs Optimal Plan](#8-universal-crawler--existing-vs-optimal-plan)

---

## 1. Architecture Overview

ka11y-python is a multi-stage, rule-based WCAG 2.1/2.2 accessibility auditor built on Playwright for headless browser crawling, FastAPI for the REST backend, and a suite of ML/CV tools for visual analysis.

### Pipeline Flow

```
POST /api/v1/combined/
        │
        ▼
  Validate URL (SSRF guard)
        │
        ▼
  Generate job_id → background task
        │
        ├─── Stage 1: AsyncImageCrawler  ──► AltTextAccessibilityAuditor  (1.1.1, 1.4.5, 1.4.11, 4.1.2)
        │                                    + ContrastAnalyser             (1.4.3, 1.4.6)
        │
        ├─── Stage 2: AsyncFormCrawler   ──► FormAccessibilityAuditor      (3.3.1, 3.3.2)
        │
        ├─── Stage 3: InteractiveElementCrawler ──► LabelInNameAuditor     (2.5.3)
        │
        ├─── Stage 4: MovingContentCrawler ──► PauseStopHideAuditor        (2.2.2)
        │
        ├─── Stage 5: TargetSizeCrawler  ──► TargetSizeAuditor             (2.5.8)
        │
        ├─── Stage 6: AsyncTextSpacingCrawler ──► TextSpacingAuditor       (1.4.12 static)
        │
        └─── Stage 7: RenderedLayoutCrawler ──► Multiple evaluators:
                                                  orientation.py            (1.3.4)
                                                  resize_text.py            (1.4.4)
                                                  reflow.py                 (1.4.10)
                                                  text_spacing.py           (1.4.12 rendered)
                                                  hover_focus_content.py    (1.4.13)
                                                  focus_not_obscured_*.py   (2.4.11, 2.4.12)
        │
        ▼
  Merge all stage results → combined_audit_report.json
```

All 7 stages run in parallel via `asyncio.create_task`. Total audit timeout: 600 seconds per stage, 300 seconds for image crawl.

### Middleware Stack

| Middleware | Purpose |
|---|---|
| `RateLimitMiddleware` | 30 POST req / 60s per IP (sliding window) |
| `SecurityHeadersMiddleware` | X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| `CORSMiddleware` | Allow all origins, credentials=False |
| `_ssrf_guard.py` | Blocks requests to RFC-1918, loopback, link-local, test CIDRs |

### Key Dependencies

| Package | Purpose |
|---|---|
| `playwright >= 1.57.0` | Headless browser crawling |
| `easyocr >= 1.7.2` | Text detection in images (OCR) |
| `opencv-python >= 4.13.0.90` | Contrast analysis, image processing |
| `torch >= 2.10.0` | ML inference (image classification) |
| `transformers >= 5.1.0` | Vision model pipelines |
| `faster-whisper >= 1.1.0` | Audio transcript generation |
| `google-generativeai >= 0.8.6` | Gemini API for complex descriptions |
| `pydantic >= 2.12.5` | Data models and validation |
| `fastapi >= 0.135.1` | REST API |

---

## 2. Crawler Modules — Data Dictionary

The project currently has **9 specialized crawlers**, each tailored to one or more WCAG rules. All crawlers use Playwright in async mode and share an SSRF guard installed at context level.

### 2.1 `crawler.py` — AsyncImageCrawler

**Feeds**: WCAG 1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2

**Data Collected** (`ImageData`):

| Field | Type | Description |
|---|---|---|
| `url` | str | Page URL |
| `src` | str | Resolved absolute image URL |
| `alt_text` | Optional[str] | None = missing attribute, "" = explicit empty |
| `title` | str | `title` attribute |
| `classification` | str | functional / informative / decorative / complex |
| `sub_type` | Optional[str] | buttons / icons / images / charts / logos |
| `is_functional` | bool | Inferred from context (parent button/link) |
| `is_decorative` | bool | Inferred from alt="" + presentational role |
| `is_complex` | bool | Inferred from size, OCR density |
| `is_text_image` | bool | OCR text detected inside image |
| `is_logo` | bool | Logo classification flag |
| `is_icon` | bool | Icon classification flag |
| `is_button` | bool | Part of button context |
| `file_format` | Optional[str] | PNG, SVG, JPG, WEBP, etc. |
| `element_id` | Optional[str] | Stable hash for dedup |
| `screenshot_path` | str | Local path to captured screenshot |
| `filename` | str | Base filename |

**Playwright APIs**: `page.goto()`, `page.locator()`, `page.evaluate()`, `element.screenshot()`, `element.get_attribute()`

**Lazy-load strategy**: Scrolls to multiple viewport positions, dispatches `lazyload` events, clicks hidden tabs/accordions/dropdowns, triggers load-more buttons.

**Pass order**:
1. `img, input[type="image"]`
2. `button, input[type="button|submit|reset"], [role="button"], a[class*="btn"]`
3. `svg` (inline)
4. Hidden panels via tab/accordion/carousel revelation

---

### 2.2 `media_crawler.py` — AsyncMediaCrawler

**Feeds**: WCAG 1.2.1

**Data Collected** (`MediaElementData`):

| Field | Type | Description |
|---|---|---|
| `tag` | str | AUDIO / VIDEO |
| `src` | Optional[str] | Media source URL |
| `has_autoplay` | bool | autoplay attribute |
| `has_controls` | bool | controls attribute |
| `tracks` | List[Dict] | `<track>` children: kind, src, srclang, label |
| `nearby_links` | List[Dict] | Transcript links in parent containers |
| `nearby_text` | str | Parent container text (500 chars) |
| `nearby_details` | List[Dict] | `<details>` summary + content |

**Live detection heuristic**: HLS (`.m3u8`) or DASH (`.mpd`) URLs → classified as live.

---

### 2.3 `forms_crawler.py` — AsyncFormCrawler

**Feeds**: WCAG 3.3.1, 3.3.2

**Data Collected** (`FormInputData`):

| Field | Type | Description |
|---|---|---|
| `has_explicit_label` | bool | `<label for="id">` found |
| `has_wrapping_label` | bool | `<label><input></label>` |
| `has_any_label` | bool | Any label source present |
| `label_text` | Optional[str] | Resolved label text |
| `required` | bool | Native `required` attribute |
| `aria_required` | Optional[str] | aria-required value |
| `aria_invalid` | Optional[str] | Current aria-invalid state |
| `autocomplete` | Optional[str] | autocomplete attribute |
| `error_element_id` | Optional[str] | aria-describedby target |
| `error_has_role_alert` | bool | Error container has role="alert" |
| `error_has_aria_live` | Optional[str] | polite / assertive |

---

### 2.4 `interactive_crawler.py` — InteractiveElementCrawler

**Feeds**: WCAG 2.5.3

**Data Collected** (`InteractiveElementData`):

| Field | Type | Description |
|---|---|---|
| `visible_label` | Optional[str] | What sighted users see (innerText/label) |
| `accessible_name` | Optional[str] | AccName-1.1 computed name |
| `aria_labelledby_text` | Optional[str] | Resolved text of referenced elements |

**AccName resolution order**: aria-labelledby → aria-label → input value/alt → label text → title → textContent

---

### 2.5 `target_size_crawler.py` — TargetSizeCrawler

**Feeds**: WCAG 2.5.8

**Data Collected** (`TargetSizeData`):

| Field | Type | Description |
|---|---|---|
| `rendered_width_px` | float | getBoundingClientRect().width |
| `rendered_height_px` | float | getBoundingClientRect().height |
| `is_inline_exception` | bool | `<a>` with CSS display:inline |
| `is_ua_controlled_exception` | bool | Native checkbox/radio, appearance:auto |
| `is_offset_exception` | bool | Offset to nearest target sufficient |
| `passes_size` | bool | width >= 24 AND height >= 24 |

**Minimum**: 24 × 24 CSS px (WCAG 2.5.8 AA)

---

### 2.6 `text_spacing_crawler.py` — AsyncTextSpacingCrawler

**Feeds**: WCAG 1.4.12 (static pre-check)

**Data Collected** (`TextSpacingData`):

| Field | Type | Description |
|---|---|---|
| `has_fixed_height` | bool | CSS `height` matches `/^\d+(\.\d+)?px$/` |
| `has_overflow_hidden` | bool | overflow: hidden or clip |
| `is_clipped` | bool | scrollHeight > clientHeight at runtime |

---

### 2.7 `moving_content_crawler.py` — MovingContentCrawler

**Feeds**: WCAG 2.2.2

**Data Collected** (`MovingContentData`):

| Field | Type | Description |
|---|---|---|
| `content_type` | str | video_autoplay / animated_gif / css_animation / carousel_autoplay / marquee_element / blink_element |
| `animation_duration_seconds` | Optional[float] | Duration from WAAPI/CSS |
| `loops` | bool | Infinite iteration |
| `has_mechanism` | bool | Pause/stop/hide control found nearby |

**Pause keyword regex**: `/pause|stop|一時停止|停止|止める/`

---

### 2.8 `rendered_layout_crawler.py` — RenderedLayoutCrawler

**Feeds**: WCAG 1.3.4, 1.4.4, 1.4.10, 1.4.12 (rendered), 1.4.13, 2.4.11, 2.4.12

**Viewports Used**:

| Scenario | Viewport | Rule |
|---|---|---|
| `baseline` | 1280×720 | Reference |
| `reflow_320` | 320×640 | 1.4.10 |
| `portrait` | 390×844 | 1.3.4 |
| `landscape` | 844×390 | 1.3.4 |
| `text_resize_200` | 1280×720 + 200% font | 1.4.4 |
| `text_spacing_override` | 1280×720 + spacing CSS | 1.4.12 |
| `focus_steps` | 1280×720 + Tab traversal | 2.4.11, 2.4.12 |
| `hover_results` | 1280×720 + hover trigger | 1.4.13 |

---

### 2.9 `_ssrf_guard.py` — SSRF Route Guard

Blocks all requests to:
- `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- `169.254.0.0/16` (link-local)
- `::1/128`, `fc00::/7` (IPv6)
- Test CIDRs: `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`

Installed at **context level** (applies to all pages and redirects).

---

## 3. Checker/Auditor Modules

### 3.1 `alttext.py` — AltTextAccessibilityAuditor (WCAG 1.1.1, 1.4.5, 1.4.11, 4.1.2)

**Decision logic per classification**:

| Classification | Pass Condition |
|---|---|
| Decorative | `alt=""` only |
| Informative | Alt text contains ≥1 OCR word (3+ chars); no generic alts |
| Logo | Alt contains "logo" or "home" |
| Icon | Alt indicates purpose/brand with "icon" |
| Button | Alt contains word from `_BUTTON_ACTION_WORDS` set |
| Functional | Alt not in `_EMPTY_OR_GENERIC` set |

**Generic Alt Detection Set** (`_EMPTY_OR_GENERIC`):
`""`, `"image"`, `"img"`, `"photo"`, `"picture"`, `"graphic"`, `"figure"`, `"icon"`, `"untitled"`, `"placeholder"`, `"null"`, `"none"`, `"n/a"`, `"na"`, `"image of"`, `"photo of"`, `"spacer"`, `"decoration"`, `"decorative"`

---

### 3.2 `form_auditor.py` — FormAccessibilityAuditor (WCAG 3.3.1, 3.3.2)

**Required field detection regex** (multi-language):
```
\* | \(required\) | \brequired\b | 必須 | 必要 | obligatoire | obrigatório | pflichtfeld | erforderlich | requerido
```

**Personal field types** (trigger autocomplete check):
`email`, `tel`, `url`, `password`, `name`

---

### 3.3 `label_in_name_auditor.py` — LabelInNameAuditor (WCAG 2.5.3)

**Match logic**:
- Latin text: `\b{visible}\b` regex (word boundaries)
- CJK text: simple substring match (no word boundaries in CJK script)
- Both: NFC-normalized, casefolded, whitespace-collapsed

---

### 3.4 `pause_stop_hide_auditor.py` — PauseStopHideAuditor (WCAG 2.2.2)

**Applicability**: element must be `starts_automatically=True` AND (`duration > 5s` OR `loops=True`) AND `has_mechanism=False`.

---

### 3.5 `target_size_auditor.py` — TargetSizeAuditor (WCAG 2.5.8)

**Minimum**: 24px × 24px. Three exception gates checked in order: inline, UA-controlled, offset.

---

## 4. Live Audit Results — 5 Websites

Sites chosen as non-mainstream but representative of different content types and languages.

### Site 1 — arts.ac.uk (Arts University London)

**Runtime**: 16.9s | **Total findings**: 190

| WCAG Rule | Status | Violations | Key Finding |
|---|---|---|---|
| 1.1.1 Non-text Content | N/A | 0/0 | No `<img>` found — JS lazy-loading bypasses domcontentloaded detection |
| 1.4.12 Text Spacing | PASS | 0/1 | OK |
| 2.2.2 Pause/Stop/Hide | N/A | 0/0 | No moving content detected |
| 2.5.8 Target Size | PASS | 0/54 | All targets adequate |
| 3.3.1 Error Identification | **FAIL** | 2/4 | Search + icon submit inputs lack error association |
| 3.3.2 Labels or Instructions | **FAIL** | 2/4 | `<input type="submit" class="search-btn">` and `<input class="btn-icon">` have no visible label |
| 2.5.3 Label in Name | **FAIL** | 56/121 | Accessible names don't contain visible text for many controls |
| 1.3.4 Orientation | PASS | — | |
| 1.4.4 Resize Text | PASS | — | |
| 1.4.10 Reflow | WARN | — | Needs manual review at 320px |
| 1.4.13 Hover/Focus Content | PASS | — | |
| 2.4.11 Focus Not Obscured (Min) | PASS | — | |
| 2.4.12 Focus Not Obscured (Enh) | PASS | — | |

**Critical observation**: The JS lazy-loading (`data-src`, Intersection Observer) means the entire image alt text audit (1.1.1) returned N/A. The site almost certainly has real violations invisible to the crawler.

---

### Site 2 — govt.nz (New Zealand Government)

**Runtime**: 16.0s | **Total findings**: 8

| WCAG Rule | Status | Violations | Key Finding |
|---|---|---|---|
| 1.1.1 Non-text Content | N/A | 0/0 | No images at depth 0 |
| 3.3.2 Labels | N/A | 0/0 | No forms detected |
| 2.5.8 Target Size | N/A | 0/0 | No interactive elements detected |
| 1.3.4 Orientation | WARN | 0/2 | Orientation lock needs manual review |
| 1.4.10 Reflow | PASS | — | |
| 1.4.13 Hover/Focus | PASS | — | |
| 2.4.11 Focus Not Obscured | PASS | — | |
| 2.4.12 Focus Not Obscured | PASS | — | |

**Critical observation**: Only 8 total findings — the government site is heavily JS-rendered (Next.js/SPA). Almost all content loads after `domcontentloaded` completes. The crawler misses nearly everything. This is the starkest example of the fundamental JS-rendering blind spot.

---

### Site 3 — w3schools.com/accessibility/ (W3Schools Accessibility Tutorial)

**Runtime**: 154.4s | **Total findings**: 1,986

| WCAG Rule | Status | Violations | Key Finding |
|---|---|---|---|
| 1.1.1 Non-text Content | **FAIL** | 9/58 | Decorative images with empty alt used as informative |
| 1.4.3 Contrast (Min) | **FAIL** | 38/47 | Code samples and sidebar text below 4.5:1 |
| 1.4.5 Images of Text | **FAIL** | 41/57 | Heavy use of embedded code screenshots |
| 1.4.6 Contrast (Enh) | **FAIL** | 38/47 | Same elements fail 7:1 threshold |
| 1.4.10 Reflow | **FAIL** | 1/4 | Horizontal scroll appears at 320px width |
| 1.4.11 Non-text Contrast | **FAIL** | 33/54 | UI component borders below 3:1 |
| 1.4.12 Text Spacing | WARN | 0/605 | 605 elements borderline |
| 2.4.11 Focus Not Obscured (Min) | **FAIL** | 75/79 | Sticky top nav obscures 75/79 focusable elements |
| 2.4.12 Focus Not Obscured (Enh) | **FAIL** | 79/79 | All 79 fully obscured by sticky nav |
| 2.5.3 Label in Name | **FAIL** | 307/759 | Widespread mismatch (JS-modified labels) |
| 3.3.2 Labels | PASS | 0/8 | |
| 2.5.8 Target Size | PASS | 0/122 | |
| 4.1.2 Name/Role/Value | **FAIL** | 9/56 | Same images as 1.1.1 violations |

**Notable**: W3Schools fails its own accessibility tutorial page on 9 separate WCAG criteria, with the sticky navigation bar causing 100% focus-obscuration (2.4.11/2.4.12).

---

### Site 4 — ookla.com (Speedtest)

**Runtime**: 301.2s | **Total findings**: 607

| WCAG Rule | Status | Violations | Key Finding |
|---|---|---|---|
| 1.1.1 Non-text Content | **FAIL** | 1/4 | `alt="Ookla global product image"` — non-descriptive generic alt |
| 1.4.4 Resize Text | **FAIL** | 1/1 | Text overflows container at 200% font |
| 1.4.5 Images of Text | **FAIL** | 4/4 | Product hero images embed text |
| 1.4.12 Text Spacing | WARN | 0/295 | 295 elements borderline |
| 2.4.11 Focus Not Obscured (Min) | **FAIL** | 25/31 | Sticky header overlaps focused elements |
| 2.4.12 Focus Not Obscured (Enh) | **FAIL** | 31/31 | All 31 fully obscured |
| 2.5.3 Label in Name | **FAIL** | 28/179 | Mismatches in icon+text buttons |
| 2.5.8 Target Size | **FAIL** | 4/29 | `.wp-block-button__link` buttons below 24×24px |
| 3.3.2 Labels | **FAIL** | 1/7 | `<select>` with no `<label>` association |
| 1.4.3 Contrast | PASS | 0/— | |
| 1.4.6 Contrast Enh | PASS | 0/— | |
| 3.3.1 Error ID | PASS | 0/— | |
| 4.1.2 Name/Role/Value | PASS | 0/— | |

---

### Site 5 — kagawa-u.ac.jp (Kagawa University, Japan) — Japanese Language Site

**Runtime**: 106.0s | **Total findings**: 1,461

| WCAG Rule | Status | Violations | Key Finding |
|---|---|---|---|
| 1.1.1 Non-text Content | **FAIL** | 32/91 | Logo `alt="香川大学"` flagged; icons with `alt=""`; functional images missing alt |
| 1.4.3 Contrast (Min) | **FAIL** | 9/23 | Japanese text overlaid on images |
| 1.4.5 Images of Text | **FAIL** | 19/87 | Banner images embedding kanji/hiragana text |
| 1.4.6 Contrast (Enh) | **FAIL** | 13/23 | |
| 1.4.11 Non-text Contrast | **FAIL** | 2/31 | |
| 1.4.12 Text Spacing | WARN | 0/489 | 489 elements borderline |
| 2.4.11 Focus Not Obscured (Min) | **FAIL** | 23/23 | 100% failure — fixed header |
| 2.4.12 Focus Not Obscured (Enh) | **FAIL** | 23/23 | 100% failure |
| 2.5.3 Label in Name | **FAIL** | 159/465 | CJK substring matching issues (see Section 6) |
| 2.5.8 Target Size | **FAIL** | 4/112 | Slick carousel dot-buttons too small |
| 3.3.2 Labels | **FAIL** | 2/2 | Search `<input>` has only placeholder, no `<label>` |
| 4.1.2 Name/Role/Value | **FAIL** | 31/86 | Images missing accessible names |

---

### Cross-Site Summary

| WCAG Rule | arts.ac.uk | govt.nz | w3schools | ookla.com | kagawa-u.ac.jp |
|---|---|---|---|---|---|
| 1.1.1 Non-text Content | N/A (lazy-load) | N/A (SPA) | **FAIL** 9 | **FAIL** 1 | **FAIL** 32 |
| 1.2.1 Audio/Video | N/A | N/A | N/A | N/A | N/A |
| 1.4.3 Contrast Min | N/A | N/A | **FAIL** 38 | PASS | **FAIL** 9 |
| 1.4.4 Resize Text | PASS | PASS | — | **FAIL** 1 | — |
| 1.4.5 Images of Text | N/A | N/A | **FAIL** 41 | **FAIL** 4 | **FAIL** 19 |
| 1.4.10 Reflow | WARN | PASS | **FAIL** 1 | — | — |
| 1.4.11 Non-text Contrast | N/A | N/A | **FAIL** 33 | — | **FAIL** 2 |
| 1.4.12 Text Spacing | PASS | PASS | WARN 605 | WARN 295 | WARN 489 |
| 1.4.13 Hover/Focus | PASS | PASS | — | — | — |
| 2.2.2 Pause/Stop/Hide | N/A | N/A | N/A | N/A | N/A |
| 2.4.11 Focus Obscured Min | PASS | PASS | **FAIL** 75 | **FAIL** 25 | **FAIL** 23 |
| 2.4.12 Focus Obscured Enh | PASS | PASS | **FAIL** 79 | **FAIL** 31 | **FAIL** 23 |
| 2.5.3 Label in Name | **FAIL** 56 | — | **FAIL** 307 | **FAIL** 28 | **FAIL** 159 |
| 2.5.8 Target Size | PASS | N/A | PASS | **FAIL** 4 | **FAIL** 4 |
| 3.3.1 Error ID | **FAIL** 2 | N/A | — | PASS | — |
| 3.3.2 Labels | **FAIL** 2 | N/A | PASS | **FAIL** 1 | **FAIL** 2 |
| 4.1.2 Name/Role/Value | N/A | N/A | **FAIL** 9 | PASS | **FAIL** 31 |

---

## 5. Rule Limitation Analysis

Each rule has functional limitations (technical gaps in the implementation) documented here.

### WCAG 1.1.1 — Non-text Content

| Limitation | Severity | Description |
|---|---|---|
| JS lazy-loading blind spot | **Critical** | Images using `data-src`, Intersection Observer, or JS bundle injection are never seen at `domcontentloaded`. arts.ac.uk had 0 images crawled despite dozens on-screen. |
| Lazy-scroll depth | High | Scroll-trigger logic uses fixed viewport positions; infinite-scroll pages beyond 3× viewport height miss late images |
| SVG title / desc | Medium | Complex SVGs with `<title>` + `<desc>` are audited as icons; multi-path SVGs with embedded text not OCR-processed |
| Image maps | Medium | `<map><area alt>` elements are not audited — area-level alt text is ignored entirely |
| CSS background images | High | `background-image: url(...)` in CSS not detected at all (requires visual layout analysis) |
| Generic alt classifier | Medium | `_EMPTY_OR_GENERIC` is English-only. Japanese/Chinese generic alts (`画像`, `写真`, `アイコン`) are not flagged |
| Logo classification | Low | Only passes if alt contains "logo" or "home" — Japanese site logos (e.g. `alt="香川大学"`) are flagged as failures even when appropriate |
| CAPTCHA exemption | Low | WCAG 1.1.1 Exception 4 (CAPTCHA) not implemented; CAPTCHA images may be false positives |
| `role="presentation"` inside links | Low | Presentational image inside `<a>` should inherit link's accessible name; auditor treats it independently |

---

### WCAG 1.2.1 — Audio-only and Video-only (Prerecorded)

| Limitation | Severity | Description |
|---|---|---|
| Live stream detection | High | Only checks for `.m3u8` / `.mpd` URLs — live streams on custom CDNs (e.g. Akamai, Wowza) or WebRTC not detected |
| Video-only detection | Medium | Classification `video_only` requires `muted + loop + autoplay`; some ambient loops omit `loop` attribute |
| Transcript proximity | Medium | Transcript search only looks 3 parent levels up for links/details; deeply nested transcript containers missed |
| Keyword list (EN only) | High | Transcript link keywords (`"transcript"`, `"text version"`) are English-only |
| Audio descriptions quality | Not Implemented | Gate 5 (transcript accuracy/completeness) noted as `# TODO` |
| IFrame media | High | Video players inside `<iframe>` (YouTube embeds, Vimeo) are not audited |

---

### WCAG 1.3.4 — Orientation

| Limitation | Severity | Description |
|---|---|---|
| CSS media query detection | Medium | Only checks viewport screenshot diff; does not parse `@media (orientation: landscape) { overflow: hidden }` in stylesheets |
| Fixed layout vs locked | Low | Some legitimate fixed-orientation apps (e.g. banking) may false-positive |
| Dynamic resizing apps | Medium | Apps that detect orientation via JS and re-render may pass snapshot diff but still restrict orientation |

---

### WCAG 1.4.3 / 1.4.6 — Contrast (Minimum / Enhanced)

| Limitation | Severity | Description |
|---|---|---|
| Gradient backgrounds | High | Otsu segmentation picks one threshold; multi-zone gradients split incorrectly |
| Transparency / alpha | High | RGBA text on layered elements; `opacity` + `rgba` compound effects not resolved |
| Text over images | Medium | Image background contrast uses average luminance, not per-character worst case |
| Placeholder text | Medium | Placeholder contrast not checked (WCAG 1.4.3 does not require it, but some implementations include it) |
| Canvas / WebGL text | Not Implemented | Text rendered via `<canvas>` or WebGL shaders is invisible to the auditor |
| Japanese CJK rendering | Medium | EasyOCR may misidentify CJK characters, affecting OCR-derived contrast boxes |

---

### WCAG 1.4.4 — Resize Text

| Limitation | Severity | Description |
|---|---|---|
| Zoom vs font-size | Medium | The test injects `document.documentElement.style.fontSize = '200%'` — this differs from browser zoom (which rescales everything including layout). Not equivalent to actual OS-level zoom. |
| Relative unit assumption | Medium | Pages using `rem`/`em` resize correctly; `px`-based pages fail correctly. But `vw`-based text is not resized by font-size injection. |
| Overflow detection | Medium | Relies on screenshot diff; overflow text that wraps invisibly (ellipsis, clipping) may not change pixel signature |

---

### WCAG 1.4.5 — Images of Text

| Limitation | Severity | Description |
|---|---|---|
| EasyOCR language models | High | Default EasyOCR models cover Latin, Chinese, Japanese, Korean. Arabic, Hindi, Thai, Hebrew not loaded by default |
| OCR confidence threshold | Medium | Hardcoded confidence threshold; low-contrast text-in-images may be missed |
| Logotype exception | Medium | WCAG 1.4.5 Exception: logos are exempt. Auditor has `is_logo` flag but does not universally skip logos for 1.4.5 |
| Background image text | Not Implemented | CSS `background-image` text-in-image not crawled |

---

### WCAG 1.4.10 — Reflow

| Limitation | Severity | Description |
|---|---|---|
| Screenshot-only comparison | High | Detects horizontal scroll bar presence via pixel comparison; does not detect content loss (hidden/clipped text that doesn't trigger scroll) |
| 320px fixed viewport | Medium | Uses 320×640; WCAG requires equivalent to 320 CSS px at 400% zoom, which is different from a narrow viewport resize in some cases |
| Sticky overlays | Medium | Fixed/sticky headers that remain at 320px are not identified as the root cause of reflow failures |

---

### WCAG 1.4.11 — Non-text Contrast

| Limitation | Severity | Description |
|---|---|---|
| Icon boundary detection | High | Otsu segmentation defines icon boundary; thin icons on white backgrounds may produce incorrect boundary |
| Focus indicator detection | Not Implemented | Focus ring contrast not measured (requires tabbing through elements and capturing focus indicator pixel data) |
| Component state contrast | Medium | Inactive/disabled states have lower contrast requirement (3:1 only for default state); state detection not implemented |

---

### WCAG 1.4.12 — Text Spacing

| Limitation | Severity | Description |
|---|---|---|
| Static heuristics only | High | Static checker flags `height:fixed + overflow:hidden` as WARNING, not FAIL. Rendered checker (CSS injection) is the real check. |
| CSS specificity conflicts | Medium | Injected spacing CSS may be overridden by `!important` rules in the target site, producing false passes |
| Pseudo-element text | Medium | `::before`/`::after` text not captured in spacing override check |
| CJK line-height | High | Japanese/Chinese text with tighter line-heights set for typographic reasons is flagged the same as Latin text — no language-aware threshold |
| Vertical text | Not Implemented | CSS `writing-mode: vertical-rl` (used in Japanese) — text spacing CSS overrides don't handle vertical axes |

---

### WCAG 1.4.13 — Content on Hover or Focus

| Limitation | Severity | Description |
|---|---|---|
| Custom tooltip libraries | High | Libraries that create tooltips via `document.body.appendChild` (not inline in DOM tree) may not be found by hover-target scan |
| Focus-only content | Medium | Elements that appear only on keyboard focus (not mouse hover) may be missed if Tab traversal in `focus_steps` doesn't reach them |
| Pointer cancel requirement | Not Implemented | 1.4.13 requires hover content to remain on hover; timing/persistence not tested |

---

### WCAG 2.2.2 — Pause, Stop, Hide

| Limitation | Severity | Description |
|---|---|---|
| **0/5 sites detected anything** | **Critical** | CSS animations and carousels were not detected on any of the 5 test sites. Root cause: `document.getAnimations()` at `domcontentloaded` returns animations not yet started or already completed. |
| Carousel detection | High | Bootstrap/Swiper/Slick carousel detection looks for class names at DOM-ready; dynamically initialized carousels are missed |
| RequestAnimationFrame loops | Not Implemented | JS-only animation loops using `requestAnimationFrame` are not detected |
| Background video | Medium | `<video>` in fixed/absolute position backgrounds without `autoplay` attribute but started via JS is missed |
| GIF detection | Medium | Animated GIFs inside `<picture>` fallback or as CSS background are missed |

---

### WCAG 2.4.11 / 2.4.12 — Focus Not Obscured

| Limitation | Severity | Description |
|---|---|---|
| CSS transform offsets | High | Elements shifted off-screen by `transform: translateY(-100%)` are not detected as obscuring overlays |
| `z-index` calculation | Medium | Only `position:fixed|sticky` elements checked; z-index stacking context not resolved across layers |
| Scroll position dependency | Medium | Test tabs at document top only; elements obscured only mid-page or at scroll position X are missed |
| Partial obscuration | Medium | 2.4.11 allows partial visibility; pixel-percentage overlap not measured — only full-rect intersection |

---

### WCAG 2.5.3 — Label in Name

| Limitation | Severity | Description |
|---|---|---|
| High false-positive rate | High | 307/759 violations on w3schools, 159/465 on kagawa-u — suggests pattern matches are over-triggering on icon buttons, decorative elements, and cases where visible text is intentionally short |
| Icon-only buttons | Medium | Buttons with visible icon only (no text) fire 2.5.3 check but have `visible_label=None` — should be N/A |
| Punctuation stripping | Low | `_strip_punctuation()` removes all non-alphanumeric; symbols like `+` or `>` as visible labels become empty strings and trigger N/A instead of PASS |
| ARIA-expanded toggles | Low | Toggle buttons showing "Show more" but with accessible name "Toggle navigation section X" are flagged — debatable whether this is correct |

---

### WCAG 2.5.8 — Target Size (Minimum)

| Limitation | Severity | Description |
|---|---|---|
| Inline exception accuracy | Medium | `isInlineLink` only checks CSS `display: inline`; links styled as `display:inline-block` but visually inline are not exempted |
| Offset exception measurement | Medium | "Nearest target gap" is computed as bounding-rect distance; overlapping or nested targets may produce incorrect gap values |
| `<area>` elements | Not Implemented | Image map `<area>` elements not measured |
| Touch vs pointer | Low | WCAG 2.5.8 is pointer-specific; the crawler doesn't distinguish desktop vs mobile contexts |

---

### WCAG 3.3.1 — Error Identification

| Limitation | Severity | Description |
|---|---|---|
| Static error checking | High | Checks DOM-ready state only; does not submit forms and observe error state |
| Error injection simulation | Not Implemented | Actual validation errors (e.g. empty required field + submit) are not triggered |
| Client-side validation | Medium | Error containers present in DOM but hidden (display:none) are seen as "no error" even if they activate later |
| Multi-step forms | Not Implemented | Multi-step/wizard forms show one step at a time; steps 2+ are not audited |

---

### WCAG 3.3.2 — Labels or Instructions

| Limitation | Severity | Description |
|---|---|---|
| `placeholder` as label | Medium | Placeholder text is not a substitute for a visible label, but some sites use only placeholder — auditor correctly flags this |
| Implicit form fields | Medium | Inputs outside `<form>` elements are sometimes missed (only caught when using document.body fallback) |
| Dynamic field injection | High | Fields added to DOM via JS after `domcontentloaded` (e.g. React form components) are missed |
| fieldset / legend | Low | `<fieldset><legend>` as group label not resolved as label for individual radio/checkbox inputs |

---

### WCAG 4.1.2 — Name, Role, Value

| Limitation | Severity | Description |
|---|---|---|
| ARIA validity | Not Implemented | Invalid ARIA attribute values (e.g. `aria-label=""`) not flagged |
| Custom widget states | Not Implemented | `aria-checked`, `aria-selected`, `aria-expanded` state correctness not verified |
| Role inheritance | Low | Implicit roles from HTML semantics not fully computed (e.g. `<li>` → listitem) |

---

## 6. Japanese Language Limitations

This table covers specific limitations when auditing Japanese-language websites (hiragana, katakana, kanji, vertical text).

| WCAG Rule | Limitation | Impact | Root Cause |
|---|---|---|---|
| **1.1.1** Non-text Content | Japanese generic alt text (`画像`, `写真`, `アイコン`, `バナー`) not in `_EMPTY_OR_GENERIC` set | False negatives — Japanese generic alts pass incorrectly | `_EMPTY_OR_GENERIC` is English-only |
| **1.1.1** Non-text Content | Japanese logo alt text (e.g. `alt="香川大学"`) incorrectly fails — institution name in kanji is valid | False positives on Japanese logos | Logo check requires "logo" or "home" literally, not institution names |
| **1.1.1** Non-text Content | EasyOCR Japanese model (`ja`) must be explicitly enabled; kanji recognition accuracy ~78% vs ~95% for Latin | OCR-detected text violations may miss ~22% of Japanese text in images | EasyOCR default language list |
| **1.2.1** Audio/Video | Transcript link detection keywords (`"transcript"`, `"text version"`) are English-only; Japanese equivalents (`テキスト版`, `字幕`, `音声解説`, `全文`) not included | Japanese transcript links never detected | Hardcoded English keyword list in `media_crawler.py` |
| **1.4.3** Contrast | EasyOCR CJK bounding boxes are often larger than individual glyphs; contrast measurement area may include non-text pixels | Inaccurate contrast ratios for small kanji at 10-12px | CJK character aspect ratios and bounding box semantics differ from Latin |
| **1.4.4** Resize Text | Japanese text rendered with `font-family: "Noto Sans JP"` or system CJK fonts reflows differently; some CJK-specific line-break rules not respected in CSS injection test | False positives when kanji text reflows unexpectedly at 200% | CJK text does not hyphenate; line-break opportunities differ |
| **1.4.5** Images of Text | `ja` model in EasyOCR does not reliably detect vertical (`writing-mode: vertical-rl`) text in images | Vertical text banners not flagged for 1.4.5 | EasyOCR processes horizontal text by default |
| **1.4.12** Text Spacing | `letter-spacing` override (0.12em) significantly distorts CJK text rendering — in Japanese typography, negative or zero letter-spacing is standard; forced 0.12em causes layout breaks | False positives on Japanese text containers with fixed heights | CSS letter-spacing applies uniformly; CJK standard is tighter than Latin WCAG override |
| **1.4.12** Text Spacing | Vertical text (`writing-mode: vertical-rl`) has height/width axes swapped; `line-height` override applies to wrong axis | CSS spacing injection does not test vertical text correctly | CSS spacing properties are horizontal-axis-centric |
| **2.2.2** Pause/Stop/Hide | Japanese pause/stop keywords partially supported (`一時停止`, `停止`, `止める`) but `再生停止`, `動画を止める`, `スライドショーを停止` and UI text like `■` (stop symbol) not recognized | Some Japanese pause controls are missed | Incomplete Japanese keyword coverage in pause button detection |
| **2.5.3** Label in Name | CJK substring matching (no word boundaries) is correct in theory but produces false positives when short Japanese labels (2-4 chars) appear as substrings of longer accessible names unintentionally | High false-positive rate (kagawa-u: 159/465 violations) | Japanese has no word boundaries; 2-character labels match anywhere |
| **2.5.3** Label in Name | Fullwidth vs halfwidth character normalization (`Ａ` vs `A`, `１` vs `1`) not applied; visually identical labels may not match | False negatives when site mixes fullwidth/halfwidth | Unicode normalization only applies NFC, not NFKC (which collapses fullwidth) |
| **3.3.2** Labels | Required field regex includes `必須` and `必要` but not `要入力`, `入力必須`, `必ず入力`, `※印は必須` | Some Japanese required indicators not recognized | Incomplete Japanese required-field pattern coverage |
| **3.3.2** Labels | Japanese placeholder text in forms (e.g. `placeholder="キーワードで検索"`) correctly identified as not a label — but many Japanese sites rely on placeholder alone as the visible label | Correct behavior but common Japanese design pattern causes legitimate failures | Japanese UX convention differs from WCAG expectation |
| **4.1.2** Name/Role/Value | `aria-label` values in Japanese are not validated against accessible name best practices | Japanese aria-labels with only punctuation or short symbols accepted without review | No language-specific validation |
| **General** | The `lang` attribute check is not implemented — pages without `lang="ja"` but serving Japanese content are not flagged | Screen readers default to wrong language pronunciation for Japanese content | No lang-attribute auditor implemented |
| **General** | Ruby annotations (`<ruby>`, `<rt>`, `<rp>`) used for furigana above kanji are not accounted for in accessible name computation | Ruby text may double-count characters or be excluded from visible label | AccName spec treatment of `<ruby>` not implemented |

---

## 7. Known Bugs & Issues

### Bug 1 — SSRF Guard Install (Fixed)
- **Status**: Fixed in current code
- **Issue**: Guard was defined but never installed; all pages were unprotected
- **Fix**: Install at context level via `install_ssrf_guard(context)`

### Bug 2 — JS Lazy-load Images (Active — Critical)
- **Symptom**: Sites with Intersection Observer lazy-loading (arts.ac.uk, govt.nz) show 0 images crawled
- **Current mitigation**: Scroll + `lazyload` event dispatch; click hidden panels
- **Root cause**: Images injected by React/Vue/Next.js bundle after `domcontentloaded` are not triggered by DOM-level events
- **Fix needed**: Use `waitUntil: "networkidle"` or post-scroll wait; or inject IntersectionObserver mock

### Bug 3 — WCAG 2.2.2 Always Returns 0 (Active — Critical)
- **Symptom**: `PauseStopHideAuditor` found 0 violations on all 5 sites despite visible carousels and animations
- **Root cause**: `document.getAnimations()` at `domcontentloaded` returns empty (animations start after JS loads); carousel class detection runs before Bootstrap/Swiper init
- **Fix needed**: Add explicit wait for JavaScript frameworks; run moving content detection after `networkidle` + 2s delay

### Bug 4 — SPA/CSR Sites Return Near-Zero Results (Active — Critical)
- **Symptom**: govt.nz (Next.js) returns 8 findings; arts.ac.uk returns 0 images
- **Root cause**: `wait_until="domcontentloaded"` fires before React/Next.js hydration
- **Fix needed**: Use `wait_until="networkidle"` + additional wait for hydration signals

### Bug 5 — 2.5.3 False Positive Rate (Active — Medium)
- **Symptom**: 307/759 violations on w3schools, 159/465 on kagawa-u
- **Root cause**: Icon-only buttons (visible_label="") should be N/A but pass through as mismatches; Japanese 2-char labels match as substrings
- **Fix needed**: Skip elements where `visible_label` is empty or None before running label-in-name check

### Bug 6 — 2.4.11/2.4.12 Over-reports (Active — Medium)
- **Symptom**: 100% failure rates on 3/5 sites (75–79/79 on w3schools, 23/23 on kagawa-u)
- **Root cause**: Sticky header height is counted as obscuring ALL elements below it, even when only partially overlapping
- **Fix needed**: Only flag when overlay rect fully contains the focused element's rect (not just intersects)

### Bug 7 — logo alt text false positives on non-English sites (Active — Medium)
- **Symptom**: `alt="香川大学"` on university logo is flagged as a failure
- **Root cause**: Logo check requires alt to contain "logo" or "home" literally
- **Fix needed**: If `is_logo=True`, accept any non-empty, non-generic alt text as valid (institution names are appropriate logo alts)

### Bug 8 — `alt=None` vs `alt=""` propagation (Fixed in F18)
- **Status**: Fixed — `alt=None` means attribute missing, `alt=""` means explicit empty

---

## 8. Universal Crawler — Existing vs Optimal Plan

> **This section is a planning document only — no code has been changed.**

### 8.1 Current Architecture (9 Separate Crawlers)

```
AsyncImageCrawler         → opens page, waits domcontentloaded, collects images
AsyncMediaCrawler         → opens page, waits domcontentloaded, collects audio/video
AsyncFormCrawler          → opens page, waits domcontentloaded, collects forms
InteractiveElementCrawler → opens page, waits domcontentloaded, collects interactive elements
TargetSizeCrawler         → opens page, waits domcontentloaded, measures element sizes
AsyncTextSpacingCrawler   → opens page, waits domcontentloaded, collects containers
MovingContentCrawler      → opens page, waits domcontentloaded, collects moving content
RenderedLayoutCrawler     → opens page, runs 8 viewport/interaction scenarios, screenshots
```

**Problems**:

| Problem | Impact |
|---|---|
| Each crawler opens a separate Playwright page (8-9 page instances per audit) | 8× memory, 8× network round-trips, 8× page load time |
| All crawlers use `wait_until="domcontentloaded"` | JS-heavy/SPA sites return near-zero data for all crawlers |
| Shared context setup (SSRF guard, viewport, cookies) duplicated across crawlers | Code duplication; any update must be applied in 9 places |
| No shared JavaScript execution state | JS functions like visibility check, accName computation, aria-labelledby resolver are reimplemented independently in each crawler |
| Crawl results not shared across rules | If image crawler data would be useful to the interactive element checker, it can't be without a second crawl |
| No retry/fallback strategy | If one crawler times out, nothing retries the specific failing element type |
| No wait strategy for SPA hydration | All crawlers use the same broken `domcontentloaded` wait |

---

### 8.2 Optimal Architecture — Universal Page Snapshot

The idea is a single **PageSnapshot** object built from one browser page lifecycle, which all auditors read from rather than independently crawling.

#### Phase 1 — Single Page Load

```
UniversalCrawler
  └── open page (one Playwright page instance)
       ├── waitUntil: "domcontentloaded"
       ├── wait for JS framework hydration signal
       │     (window.__nuxt, window.__NEXT_DATA__, window.__vue__, etc.)
       ├── trigger lazy-load (scroll + IntersectionObserver mock)
       ├── wait for networkidle OR timeout 15s
       └── capture full DOM snapshot
```

#### Phase 2 — Single Extraction Pass (one page.evaluate call)

```javascript
// One giant JS evaluation that collects ALL data types simultaneously:
{
  images: [...],           // for 1.1.1, 1.4.5, 1.4.11
  media: [...],            // for 1.2.1
  forms: [...],            // for 3.3.1, 3.3.2
  interactive: [...],      // for 2.5.3
  targetSizes: [...],      // for 2.5.8
  textContainers: [...],   // for 1.4.12
  movingContent: [...],    // for 2.2.2
  overlays: [...]          // for 2.4.11, 2.4.12
}
```

This eliminates 7 of the 8 separate page loads.

#### Phase 3 — Multi-Scenario Rendering (parallel)

```
RenderedLayoutCrawler (unchanged conceptually, but sharing the base page)
  Scenarios run in parallel in separate page contexts:
  ├── Scenario A: Reflow (320px)           → 1.4.10
  ├── Scenario B: Text resize (200%)       → 1.4.4
  ├── Scenario C: Text spacing (CSS inject) → 1.4.12
  ├── Scenario D: Portrait/Landscape       → 1.3.4
  ├── Scenario E: Focus traversal          → 2.4.11, 2.4.12
  └── Scenario F: Hover/focus triggers     → 1.4.13
```

#### Comparison Table

| Dimension | Current (9 crawlers) | Optimal (1 universal + scenarios) |
|---|---|---|
| **Page loads per audit** | 8–9 separate pages | 1 base page + N scenario pages (N≈6) |
| **Memory usage** | 8× page instance memory | 1× base + 6× scenario (lower peak, scenarios are sequential) |
| **Network round-trips** | 8× full page load | 1× full load + 6× lightweight scenario |
| **Audit wall-clock time** | Sum of 8 independent crawls | Base crawl time + parallel scenario time |
| **SPA/CSR support** | None (all use domcontentloaded) | Centralized hydration wait strategy, applied once |
| **JS utility functions** | Duplicated across 8 JS eval strings | Shared JS helper library injected once |
| **Lazy-load coverage** | Partially addressed in image crawler only | Applied once before extraction; benefits all rules |
| **Code duplication** | SSRF guard, viewport setup, error handling × 8 | Single setup in UniversalCrawler base class |
| **Maintainability** | Update 8 files when page load strategy changes | Update 1 file |
| **Cookie/auth session** | Must be passed to each crawler separately | Set once, all extraction shares the session |
| **Cross-rule data sharing** | Not possible | Image data can inform interactive element checks; media data can inform form checks |

#### Proposed Module Structure

```
ka11y/
  crawler/
    universal_crawler.py          # NEW: UniversalCrawler base class
    snapshot_extractor.py         # NEW: Single-pass JS extraction (all data types)
    js/
      extract_all.js              # NEW: Shared JS bundle for extraction
      helpers.js                  # NEW: accName, visibility, aria-labelledby helpers
    scenarios/
      base_scenario.py            # NEW: BaseScenario ABC
      reflow_scenario.py          # replaces: part of rendered_layout_crawler.py
      resize_text_scenario.py     # replaces: part of rendered_layout_crawler.py
      text_spacing_scenario.py    # replaces: part of rendered_layout_crawler.py
      orientation_scenario.py     # replaces: part of rendered_layout_crawler.py
      focus_scenario.py           # replaces: part of rendered_layout_crawler.py
      hover_scenario.py           # replaces: part of rendered_layout_crawler.py
    _ssrf_guard.py                # unchanged
    models.py                     # extended: PageSnapshot aggregate model
    __init__.py
  # Legacy crawlers kept as deprecated aliases during transition
```

#### Migration Plan (zero breaking changes)

1. **Phase 1**: Build `UniversalCrawler` + `SnapshotExtractor` that outputs the same data models as existing crawlers
2. **Phase 2**: Wire new universal crawler into stages.py as an optional flag (`use_universal=True`)
3. **Phase 3**: Run A/B tests against 20 sites comparing violation counts
4. **Phase 4**: Deprecate individual crawlers, redirect their `crawl()` methods to call universal crawler + filter from snapshot
5. **Phase 5**: Remove individual crawlers

#### Key Implementation Decisions

| Decision | Recommended Choice | Reason |
|---|---|---|
| Wait strategy | `networkidle` with 30s timeout + hydration detection | Catches SPA hydration; networkidle catches late assets |
| JS extraction | Single `page.evaluate()` call with shared helper functions | Reduces browser ↔ Node IPC overhead |
| Scenario parallelism | `asyncio.gather` with per-scenario browser contexts | Scenarios don't share mutable page state |
| Lazy-load trigger | IntersectionObserver mock + scroll + explicit timeout | Most reliable approach for all lazy-load strategies |
| Screenshot strategy | One full-page screenshot + on-demand element crops | Avoids re-screenshotting elements already captured |
| SPA detection | Check `window.__NEXT_DATA__`, `window.__nuxt`, `window.React`, `window.Vue` | Cover major frameworks |

---

*End of Analysis — ka11y-python WCAG Audit System*
