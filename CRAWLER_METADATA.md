# Crawler Metadata Reference

> Generated: 2026-04-09  
> Updated: 2026-04-13  
> Scope: `ka11y-node` (24 custom WCAG checks + axe-core) and `ka11y-python` (18 WCAG rules across the universal static pipeline, image crawler, and rendered-layout crawler)

This document exhaustively maps every piece of data extracted from a crawled page to the rules that consume it. It is the canonical reference for what each crawler must provide and what each rule consumes.

---

## Table of Contents

- [ka11y-node — Crawler Architecture](#ka11y-node--crawler-architecture)
- [ka11y-node — Rule-by-Rule Data Requirements](#ka11y-node--rule-by-rule-data-requirements)
- [ka11y-python — Crawler Architecture](#ka11y-python--crawler-architecture)
- [How universal crawler data is audited](#how-universal-crawler-data-is-audited)
- [ka11y-python — Crawler Data Models](#ka11y-python--crawler-data-models)
- [ka11y-python — Rule-by-Rule Data Requirements](#ka11y-python--rule-by-rule-data-requirements)
- [Cross-Service Field Mapping](#cross-service-field-mapping)

---

## ka11y-node — Crawler Architecture

ka11y-node does **not** produce a persistent snapshot object. Instead, Puppeteer's `page` object serves as the live data source. Each rule calls `page.evaluate()` with its own JavaScript extractor, pulls exactly the fields it needs, and returns structured JSON. Interactive rules additionally use `page.keyboard`, `page.mouse`, `page.on()`, and `page.frames()`.

```
HTTP POST /api/v1/analyse-url
        │
        ▼
AccessibilityService
  ├── Puppeteer page.goto(url)
  ├── axe-core injection → axe.run()
  ├── runStaticChecks(page)   — 18 checks, page.evaluate() per check
  └── runInteractiveChecks(page) — 6 checks, keyboard/focus/nav
```

**Shared page properties available to every check:**

| Property | Access Method | Description |
|----------|--------------|-------------|
| Full DOM | `document.querySelectorAll(selector)` | Any CSS selector |
| Computed styles | `window.getComputedStyle(el)` | All CSS computed values |
| Attributes | `el.getAttribute(name)` | Any HTML attribute |
| Text content | `el.textContent` / `el.innerText` | Visible + hidden text |
| Bounding rect | `el.getBoundingClientRect()` | Size and position |
| Page URL | `page.url()` / `window.location` | Current URL |
| Stylesheets | `document.styleSheets` | CSS rules (same-origin) |
| Active element | `document.activeElement` | Currently focused element |
| Frames | `page.frames()` | All iframes (same-origin) |

---

## ka11y-node — Rule-by-Rule Data Requirements

### 1.2.1 — custom-audio-transcript

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `<audio>` elements | `querySelectorAll('audio')` | Counts audio elements needing text alternatives |
| `<track>` children | child elements of `<audio>` | Checks for `kind="captions\|descriptions\|subtitles"` |
| Nearby transcript links | ancestor containers (figure, article, section, role=region/main) | Links with transcript/書き起こし/transcript keywords |
| `<figcaption>` | parent `<figure>` | Inline transcript caption |
| `<details>` blocks | parent/sibling `<details>` | Collapsible transcript content |
| `aria-describedby` | attribute on `<audio>` | Reference to external transcript element |
| Element HTML snippet | `el.outerHTML.slice(0, 300)` | Violation reporting |

**Violations detected:** `<audio>` with no `<track>`, no nearby transcript link, no `<figcaption>`, no `aria-describedby`.

---

### 1.3.2 — custom-meaningful-sequence

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Flex/grid containers | `display: flex\|inline-flex\|grid\|inline-grid` | Identifies layout containers to inspect |
| `flexDirection` | `getComputedStyle(el).flexDirection` | Detects reverse (`row-reverse`, `column-reverse`) on LTR pages |
| Document direction | `[dir="rtl"]`, `document.documentElement.lang` | Skip RTL pages from flex-reverse violation |
| Child `order` property | `getComputedStyle(child).order` | Detects CSS `order` reordering children |
| `gridColumnStart`, `gridRowStart` | computed style on grid children | Detects explicit grid placement reordering |
| `float` property | computed style | Detects mixed float/non-float siblings |
| Visibility | `display`, `visibility`, `opacity` | Skips hidden elements |
| Element tag + classes | `el.tagName`, `el.className` | Violation message construction |

**Violations detected:** flex-reverse on LTR, CSS order reordering, grid explicit placement, mixed floats.

---

### 1.3.4 — custom-orientation

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Web App Manifest | `link[rel="manifest"]` → `fetch(href)` → JSON | `manifest.orientation` field |
| Inline script content | `script:not([src])` text | `screen.orientation.lock()` / `screen.lockOrientation()` calls |
| CSS transform on layout elements | `getComputedStyle(el).transform` | Matrix/matrix3d parsing for 90°/270° rotation |
| `rotate` property | `getComputedStyle(el).rotate` | Direct rotate property values |
| CSS @media orientation rules | `document.styleSheets` → `CSSMediaRule` | `@media (orientation: portrait/landscape)` with hiding rules |
| `<meta name="viewport">` content | `document.querySelector('meta[name="viewport"]')` | `orientation=` and `maximum-scale=1` |
| `writing-mode` on body | `getComputedStyle(document.body).writingMode` | `vertical-rl`, `vertical-lr` |
| Layout element candidates | tag, role, id/class patterns | Which elements to check for rotation |

**Violations detected:** Script lock, CSS rotation, manifest lock, meta viewport lock, @media hiding, writing-mode vertical.

---

### 1.4.1 — custom-use-of-color

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Inline text links | `p a[href]`, `li a[href]`, `td a[href]`, `blockquote a[href]`, `article > p a[href]`, `dd a[href]`, `svg a[href]` | Links in text blocks to check color-only distinction |
| `textDecorationLine` | `getComputedStyle(link)` | Must be `underline` OR other visual differentiator |
| `borderBottomWidth`, `borderBottomStyle` | `getComputedStyle(link)` | Alternative to underline |
| `outlineWidth`, `outlineStyle` | `getComputedStyle(link)` | Alternative differentiator |
| `color` (link vs ancestor) | `getComputedStyle(link)`, `getComputedStyle(ancestor non-<a>)` | RGB extraction and luminance comparison |
| `backgroundColor` | both link and ancestor | Background color difference |
| `fontWeight`, `fontStyle` | both link and ancestor | Font-based differentiation |
| Visible text content | `el.textContent` | Filtering non-visible elements |

**Violations detected:** Link distinguishable from surrounding text by color only (no underline, border, bg, or font weight).

---

### 1.4.5 — custom-images-of-text

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `img[src]` elements | `querySelectorAll('img[src]')` | Non-decorative images to inspect |
| `alt` attribute | `img.getAttribute('alt')` | Word count, sentence structure analysis |
| `src` URL | `img.src` | Path keyword scoring (text, banner, heading, etc.) |
| `className`, `id` | `img.className`, `img.id` | Pattern scoring for text-image markers |
| `role` attribute | `img.getAttribute('role')` | Skip presentation/none images |
| Logo detection | alt/src/class/id keyword matching | Exempt logos from violation |
| CSS background images | `[style*="background-image"]`, `backgroundImage` computed | Background image with text overlay |
| Element text content length | `el.textContent.length` | Text over background image detection |
| `<svg>` with `<text>` children | `querySelectorAll('svg')` | SVG images containing text elements |
| SVG parent context | `a`, `button`, `[role="img"]`, `figure` | Functional SVG text detection |

**Violations detected:** Likely text-image (scored), CSS background with text overlay, SVG-as-image with text content.

---

### 2.1.2 — custom-keyboard-trap (Interactive)

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Focusable elements | `a[href]`, `button:not([disabled])`, `input:not([disabled]):not([type="hidden"])`, `select`, `textarea`, `[tabindex]:not([tabindex="-1"])` | Elements to Tab through |
| `document.activeElement` | After each `page.keyboard.press('Tab')` | Tracks focus position |
| Element `id`, `name` | `activeElement.id`, `activeElement.name` | Stable deduplication key |
| ARIA widget roles | `[role="tree\|grid\|listbox\|menu\|tablist\|radiogroup"]` | Arrow key navigation testing |
| Same-origin iframes | `page.frames()` | Tab trap detection in iframes |
| Trap verification | `page.keyboard.press('Escape')` + Tab | Confirms real trap vs. expected widget behavior |

**Violations detected:** Tab cycling on single element, A→B→A loop, arrow key trap in ARIA widget, iframe tab trap.

---

### 2.1.4 — custom-character-key-shortcuts

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `[accesskey]` elements | `querySelectorAll('[accesskey]')` | Single-char accesskey values |
| `accesskey` value | `el.getAttribute('accesskey')` | Single character check |
| Inline key handlers | `[onkeydown]`, `[onkeypress]`, `[onkeyup]` | Attribute text content |
| Handler modifier guards | Regex: `ctrlKey`, `altKey`, `metaKey` in handler text | Checks for modifier requirement |
| `<script>` tags | `querySelectorAll('script:not([src])')` | `addEventListener('key*')` pattern matching |
| Event key patterns | Regex: `event.key === 'x'`, `keyCode === 65-90` | Single-key handler detection |

**Violations detected:** Unguarded single-char accesskeys, inline key handlers without modifiers, addEventListener without modifiers.

---

### 2.4.5 — custom-multiple-ways

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Search inputs | `input[type="search"]`, `[role="search"]` | Navigation mechanism 1 |
| Navigation links | Text/aria-label regex: search, 検索, recherche, buscar, suche, cerca, zoeken, sök, 搜索, 搜尋, 검색 | Multi-language search detection |
| Sitemap links | `a[href*="sitemap"]` with text/href matching | Navigation mechanism |
| `<nav>` / `[role="navigation"]` count | DOM query | Multiple nav regions |
| Breadcrumb indicators | `[aria-label*="breadcrumb"]`, `[class*="breadcrumb"]`, `[itemtype*="BreadcrumbList"]`, `nav [aria-current="page"]` | Navigation mechanism |
| Table of contents | `[aria-label*="table of contents"]`, `[class*="toc"]`, `a` text matching TOC patterns | Navigation mechanism |

**Violations detected:** Fewer than 2 distinct navigation mechanisms.

---

### 2.4.7 — custom-focus-visible (Interactive)

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Focusable elements | `a[href]`, `button:not([disabled])`, `input:not([type="hidden"]):not([disabled])`, `select`, `textarea`, `[tabindex]:not([tabindex="-1"])` | Elements to focus-test |
| Stable selector | element `id` | Uniquely re-locate elements after focus |
| Pre-focus CSS: `outlineWidth`, `outlineStyle`, `outlineColor` | `getComputedStyle` before `.focus()` | Baseline |
| Pre-focus CSS: `boxShadow`, `borderColor`, `borderWidth` | `getComputedStyle` before `.focus()` | Baseline |
| Pre-focus CSS: `backgroundColor`, `color`, `transform` | `getComputedStyle` before `.focus()` | Baseline |
| Post-focus same CSS properties | `getComputedStyle` after `.focus({ preventScroll: true })` | Change detection |

**Violations detected:** Focusable element with no detectable CSS change on focus.

---

### 2.4.8 — custom-location

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Breadcrumb elements | `[aria-label*="breadcrumb"]`, `[class*="breadcrumb"]`, `[itemtype*="BreadcrumbList"]` | Location indicator |
| `aria-current="page"` in nav | `nav [aria-current="page"]` | Active page indicator |
| Active nav items | `.active` or `[aria-selected="true"]` in `nav` / `[role="navigation"]` | Location indicator |
| Sitemap links | `a[href*="sitemap"]`, `[aria-label*="site map"]` | Location indicator |
| Step indicators | `[aria-current="step"]` | Multi-step form location |
| JSON-LD | `script[type="application/ld+json"]` containing `"BreadcrumbList"` | Schema.org breadcrumb |

**Violations detected:** No location indicator of any kind present.

---

### 2.4.9 — custom-link-purpose

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| All `a[href]` elements | `querySelectorAll('a[href]')` | Links to evaluate |
| `aria-label` | `el.getAttribute('aria-label')` | Priority 1 accessible name |
| `aria-labelledby` IDs | `el.getAttribute('aria-labelledby')` → `document.getElementById(id)` | Priority 2 accessible name |
| `img[alt]` inside link | child `img.getAttribute('alt')` | Priority 3 for image-only links |
| Visible text via TreeWalker | `TreeWalker(TEXT_NODE)` excluding `display:none` | Priority 4 accessible name |
| `title` attribute | `el.getAttribute('title')` | Priority 5 accessible name |
| Generic link pattern | Regex: click here, read more, more, learn more, details, here, link, → | Generic text detection |

**Violations detected:** Links with non-descriptive accessible name (generic text).

---

### 2.4.13 — custom-focus-appearance (Interactive)

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Same focusable elements as custom-focus-visible | — | Same |
| All CSS focus properties from custom-focus-visible | `getComputedStyle` before/after | Same change detection |
| Outline width value | `getComputedStyle(el).outlineWidth` | Must be ≥ 2px |
| Box-shadow spread radius | First layer of `boxShadow` value | Parsed as focus indicator thickness |
| `body` `backgroundColor` | Fallback for transparent elements | Contrast calculation |
| Contrast ratio | Luminance formula: `(L1 + 0.05) / (L2 + 0.05)` | Must be ≥ 3:1 |

**Violations detected:** Outline < 2px, focus indicator contrast ratio < 3:1.

---

### 2.5.2 — custom-pointer-cancellation

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Pointer-down handlers | `[onmousedown]`, `[onpointerdown]`, `[onpointermove]`, `[ontouchstart]` | Elements with down-action potential |
| Handler text content | `el.getAttribute('onmousedown')` etc. | Action-triggering pattern detection |
| Cancellation paths | `[onmouseup]`, `[onpointerup]`, `[onclick]`, `[ontouchend]` | Presence of abort opportunity |
| Element HTML | `el.outerHTML.slice(0, 200)` | Violation reporting |
| Japanese handler patterns | `クリック`, `送信` patterns (via CJK regex) | Japanese action keyword detection |

**Violations detected:** Action-triggering down-handler without any up/click/touchend cancellation path.

---

### 2.5.7 — custom-dragging-movements

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `[draggable="true"]` elements | `querySelectorAll('[draggable="true"]')` | Native drag elements |
| `[ondragstart]` | attribute query | Inline drag handler |
| DnD library markers | `[data-rbd-draggable-id]`, `[data-dnd-kit-draggable]`, `.sortable-item`, `.ui-draggable`, `.gu-transit` | Library drag detection |
| Single-pointer alternatives | `button`, `[role="button"]`, `a[href]`, `input[type="button"]` in element or parent | Pointer alternative presence |

**Violations detected:** Draggable element without nearby single-pointer alternative.

---

### 3.1.6 — custom-pronunciation

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `<ruby>` elements | `querySelectorAll('ruby')` | Ruby annotation presence for Japanese/CJK |
| `<rt>` children | inside `<ruby>` | Furigana/reading aid content |
| Text lang attribute | `el.closest('[lang]')` | Language context detection |
| CJK character density | Unicode range check U+3000–U+9FFF | Japanese/Chinese content detection |

---

### 3.2.1 — custom-on-focus (Interactive)

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Focusable elements | Same selectors as focus-visible | Elements to trigger focus on |
| Page URL before focus | `page.url()` → `pathname + search` | Navigation baseline |
| `framenavigated` event | `page.on('framenavigated')` | Hard navigation detection |
| `history.pushState` intercept | `page.evaluate()` override | SPA soft navigation detection |
| `history.replaceState` intercept | `page.evaluate()` override | SPA soft navigation detection |
| URL after focus | compare `pathname + search` (excluding hash) | Navigation triggered by focus |

**Violations detected:** URL changes or context changes triggered by `.focus()`.

---

### 3.2.2 — custom-on-input (Interactive)

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Input elements | `input:not([type=submit/button/reset/hidden/file]):not([disabled])`, `textarea`, `select`, `[contenteditable="true"]` | Inputs to interact with |
| `type` attribute | `el.getAttribute('type')` | Determines test input value |
| URL tracking | Same as custom-on-focus | Navigation detection |
| Value typed | Type-specific: 'a' for text, '1' for number, 'a@b.co' for email | Realistic input simulation |
| `change` event dispatch | `el.dispatchEvent(new Event('change'))` | Triggers change handlers |
| Cleanup | backspace/re-toggle | Restores element state |

**Violations detected:** Input change triggers unexpected navigation.

---

### 3.2.6 — custom-consistent-help

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Help links | `a`, `button`, `[role="link"]`, `[role="button"]` text/aria-label/href matching help, support, faq, contact, 助け, ヘルプ | Help mechanism detection |
| Help link position | `el.closest('header')`, `el.closest('footer')`, `el.closest('nav')` | Location consistency |
| Chat widget selectors | `[id*="chat"]`, `[class*="chat"]`, `#intercom-container`, `#drift-widget`, `.crisp-client`, `[id*="zendesk"]` | Chat as help mechanism |
| Chat iframes | `iframe[src*="chat"]` | Embedded chat detection |
| Phone links | `a[href^="tel:"]` | Phone as help mechanism |
| Email links | `a[href^="mailto:"]` | Email as help mechanism |

**Violations detected:** No help/contact/support mechanism found on page.

---

### 3.3.3 — custom-error-suggestion

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Form count | `querySelectorAll('form')` | Gates the check |
| Error elements by role | `[role="alert"]`, `[aria-live="assertive"]` | Alert-based errors |
| `[aria-invalid="true"]` + siblings | `[aria-invalid="true"]` with adjacent live regions | ARIA invalid errors |
| `[aria-errormessage]` references | `getAttribute('aria-errormessage')` → `getElementById` | Linked error elements |
| `[aria-describedby]` on invalid | resolved target text | Description-based errors |
| `title` on `[aria-invalid]` | `el.getAttribute('title')` | Title-attribute errors |
| Form-scoped error classes | `.error-message`, `.field-error`, `.help-block.error` | Class-based errors |
| Error message text | `el.textContent.trim()` | Suggestion pattern analysis |
| Suggestion patterns | Regex: must, should, please, example, try, enter, provide | Guidance presence in error text |

**Violations detected:** Terse error messages without actionable correction guidance.

---

### 3.3.4 — custom-error-prevention

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `<form>` elements | `querySelectorAll('form')` | Forms to classify |
| Submit button/heading text | `button[type="submit"]`, `input[type="submit"]`, `h1-h6`, `legend` | Risk keyword detection |
| Form `id`, `action`, `name` | form attributes | Context for risk scoring |
| Financial keywords | payment, checkout, credit card, purchase, order, 支払い, 購入 | Financial risk classification |
| Legal keywords | terms, privacy, contract, agreement, 利用規約 | Legal risk classification |
| Destructive keywords | delete, cancel, deactivate, remove, 削除, キャンセル | Destructive risk classification |
| Review text presence | review, confirm, edit, preview, 確認, 見直し | Safeguard detection |
| Confirmation checkbox | `input[type="checkbox"][required]` | Safeguard detection |
| Multi-step indicators | `[class*="step"]`, `[class*="wizard"]`, `[class*="progress"]`, `[aria-label*="step"]` | Multi-step form safeguard |
| Element visibility | `display`, `visibility`, `opacity` | Skip hidden safeguards |

**Violations detected:** High-risk forms without review/confirm safeguard.

---

### 3.3.7 — custom-redundant-entry

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Multiple forms | `querySelectorAll('form')` | Multi-form process detection |
| `input`, `select`, `textarea` fields | per form | Field inventory |
| `type` attribute | each field | Email/tel/password classification |
| `autocomplete` attribute | each field | Personal data token matching |
| Input labels | `label[for]`, `aria-label`, nearby text | Label-based field type inference |
| Process type keywords | checkout, registration, booking, contact | Form process classification |
| Confirm/re-entry patterns | field name/label containing confirm, repeat, re-enter, 確認 | Explicit redundant entry detection |

**Violations detected:** Same personal data requested in multiple form fields without autocomplete or confirmation context.

---

### 3.3.8 — custom-accessible-auth

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| `input[type="password"]` | `querySelectorAll('input[type="password"]')` | Auth form detection |
| Form text | login, sign in, authenticate, register, forgot password, サインイン, ログイン | Auth form classification |
| CAPTCHA images | `img[src*="captcha"]`, `img[alt*="captcha"]`, `[class*="captcha"]`, `[id*="captcha"]` | CAPTCHA detection |
| reCAPTCHA | `iframe[src*="recaptcha"]`, `[class*="g-recaptcha"]`, `[data-sitekey]` | Google CAPTCHA |
| hCaptcha | `[class*="h-captcha"]`, `[data-hcaptcha-widget-id]` | hCaptcha detection |
| Cloudflare Turnstile | `.cf-turnstile`, `[data-cf-turnstile]` | Turnstile CAPTCHA |
| Audio CAPTCHA alternative | `[class*="captcha-audio"]`, `button[aria-label*="audio"]` | Accessible alternative |
| Passkey/WebAuthn | button/link text: passkey, webauthn, biometric, face id | Accessible auth alternative |
| Paste-blocking | `onpaste`, `oncopy` attributes + synthetic paste `defaultPrevented` | Clipboard restriction detection |
| Cognitive test patterns | form text matching math/puzzle/riddle keywords | Cognitive function test detection |

**Violations detected:** CAPTCHA without audio alternative, paste-blocked password, cognitive function test.

---

### 4.1.1 — custom-html-parsing

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| All `[id]` elements | `querySelectorAll('[id]')` | Duplicate ID detection |
| `element.id` values | attribute | Count occurrences per ID value |
| `[aria-labelledby]` references | `querySelectorAll('[aria-labelledby]')` | ARIA ref validity |
| `[aria-describedby]` references | `querySelectorAll('[aria-describedby]')` | ARIA ref validity |
| `[aria-controls]` references | `querySelectorAll('[aria-controls]')` | ARIA ref validity |
| `[aria-owns]` references | `querySelectorAll('[aria-owns]')` | ARIA ref validity |
| `document.getElementById(id)` | JS lookup | Verifies referenced IDs exist |
| `label[for]` elements | `querySelectorAll('label[for]')` | Orphaned label detection |
| `for` attribute value | `label.getAttribute('for')` | Checks target exists |

**Violations detected:** Duplicate IDs, broken ARIA references, orphaned `label[for]`.

---

### 4.1.3 — custom-status-messages

| Data Extracted | Source | How Used |
|---------------|--------|----------|
| Live regions | `[aria-live]`, `[role="status"]`, `[role="alert"]`, `[role="log"]`, `[role="timer"]`, `[role="marquee"]` | Live region inventory |
| `<form>` elements | `querySelectorAll('form')` | Dynamic content trigger |
| Search result areas | `[role="region"][aria-label*="result"]`, `[aria-live][id*="result"]`, `[id*="検索結果"]`, `[class*="検索結果"]` | Search result containers |
| Badge/counter elements | `[class*="badge"]` with numeric text or aria-label | Count indicators |
| Cart indicators | `[aria-label*="cart"]`, `[aria-label*="basket"]`, `[class*="cart-count"]` | E-commerce status |
| Notification areas | `[class*="notification"]`, `[class*="toast"]`, `[class*="snackbar"]`, `[class*="flash"]` | Notification containers |
| `[aria-invalid="true"]` | `querySelectorAll('[aria-invalid="true"]')` | Inline validation |
| `[aria-errormessage]` | attribute + referenced element | Error message live region |
| `[aria-atomic="true"]` | on alert/assertive regions | Atomic update flag |
| Live region ancestors | `el.closest('[aria-live],[role="status"],[role="alert"]')` | Whether error is within live region |

**Violations detected:** Forms/dynamic content without live regions, missing aria-atomic, inline validation outside live region.

---

## ka11y-python — Crawler Architecture

ka11y-python now has two execution modes:

- direct crawler classes still exist and preserve the original model contracts for debugging or compatibility
- the combined production endpoint now reuses **one universal static crawl** for seven DOM rule families, then normalizes that snapshot back into the existing Pydantic models

Direct answer: yes, the combined `ka11y-python` crawler is now universal for the static DOM rule families.

That does **not** mean every stage uses one crawler. Two specialized crawlers remain outside the universal static path:

- `AsyncImageCrawler` for screenshots, OCR, image classification, and image-specific auditing
- `RenderedLayoutCrawler` for viewport mutation, focus/hover simulation, reflow, resize-text, orientation, and focus-obscuration checks

```
POST /api/v1/combined
        │
        ▼
runner._run_job()
  ├── AsyncImageCrawler
  │     └── List[ImageMetadata]
  ├── UniversalPageLoader
  │     └── PageSnapshot
  │           ├── forms
  │           ├── interactive
  │           ├── target_sizes
  │           ├── moving_content
  │           ├── media
  │           ├── text_spacing
  │           ├── sensory
  │           ├── warnings
  │           └── element_refs
  ├── SnapshotNormalizer
  │     └── existing Pydantic models:
  │           FormInputData
  │           InteractiveElementData
  │           TargetSizeData
  │           MovingContentData
  │           MediaElementData
  │           TextSpacingData
  │           SensoryElementData
  └── RenderedLayoutCrawler
        └── PageSnapshot (portrait/landscape/zoom variants)
```

The universal static path is where ka11y-python now gets:

- same-origin iframe traversal
- open shadow-root traversal
- structured extraction warnings for cross-origin frames and partial failures
- sidecar provenance through `element_ref_id`, `selector`, and `frame_path`
- final-report `warning_details` with sampled frame metadata

Recent hardening on top of the universal path:

- `_merge_findings()` now prefers page-aware selector/target/ref evidence before HTML fallback
- OCR is now budgeted on heavy pages through `crawler.performance.max_ocr_images_per_run`
- rendered hover and focus probes are bounded by `max_hover_candidates` and `max_focus_steps`
- CJK text-spacing overrides are built from `crawler.language.cjk_langs`

Legacy crawler classes remain useful for direct debugging and compatibility, but the combined endpoint no longer needs seven separate static page loads.

### How universal crawler data is audited

The audit flow is intentionally **raw snapshot first, existing Pydantic models second, existing auditors third**.

This is the current production order:

1. `UniversalPageLoader.load()` does one Playwright session and extracts a `PageSnapshot`.
2. The raw snapshot is persisted as `universal_snapshot_raw.json`.
3. `SnapshotNormalizer.normalize()` converts each raw bucket into the existing Pydantic models.
4. The normalized snapshot is persisted as `universal_snapshot_normalized.json`.
5. `_run_python_stages()` creates one shared `snapshot_task` and passes it to every static auditor stage.
6. Each stage waits on the same normalized snapshot, calls the existing auditor unchanged, and receives structured audit rows back.
7. Stage-specific adapters convert those audit rows into unified combined findings.
8. The combined runner merges universal-static findings with image/OCR findings, rendered-layout findings, and `ka11y-node` findings into `combined_report.json`.
9. Rich step logs capture crawler counts, auditor counts, finding counts, OCR-budget decisions, and warning summaries in `step_logs/combined_execution_steps.jsonl`.

### Universal snapshot to auditor map

| Raw snapshot bucket | Normalized model | Stage function | Auditor | Main SCs |
|--------------------|------------------|----------------|---------|----------|
| `forms` | `FormInputData` | `_stage_form_audit_universal()` | `FormAccessibilityAuditor` | `3.3.1`, `3.3.2` |
| `interactive` | `InteractiveElementData` | `_stage_label_in_name_universal()` | `LabelInNameAuditor` | `2.5.3` |
| `moving_content` | `MovingContentData` | `_stage_pause_stop_hide_universal()` | `PauseStopHideAuditor` | `2.2.2` |
| `target_sizes` | `TargetSizeData` | `_stage_target_size_universal()` | `TargetSizeAuditor` | `2.5.8` |
| `text_spacing` | `TextSpacingData` | `_stage_text_spacing_universal()` | `TextSpacingAuditor` | `1.4.12` |
| `media` | `MediaElementData` | `_stage_media_audit_universal()` | `MediaAuditor` | `1.2.1` |
| `sensory` | `SensoryElementData` | `_stage_sensory_audit_universal()` | `SensoryCharacteristicsAuditor` | `1.3.3` |

### Files written by the universal audit path

| File | Purpose |
|------|---------|
| `universal_snapshot_raw.json` | Exact extracted static snapshot before model validation |
| `universal_snapshot_normalized.json` | Post-normalization records in existing Pydantic-compatible shapes |
| `universal_snapshot_warnings.json` | Cross-origin frame skips, detached-frame failures, normalization warnings, and other extraction limitations |
| `step_logs/combined_execution_steps.jsonl` | Rich-backed event log with crawler counts, auditor counts, finding counts, OCR-budget events, and warnings |
| `step_logs/combined_execution_steps_summary.json` | Rollup summary of the run |
| `combined_report.json` | Final merged output from universal static stages, image/OCR, rendered-layout, and node/axe checks, including `warning_details` |

**Universal fields present in normalized static records:**

| Field | Description |
|-------|-------------|
| `page_url` | URL of the crawled page |
| `element_index` | Sequential index of the element on the page |
| `html_snippet` | Truncated `outerHTML` (≤ 600 chars) |
| `selector` | Composed selector for evidence and deduplication |
| `element_ref_id` | Stable key into `PageSnapshot.element_refs` |
| `frame_path` | Same-origin iframe provenance (`main`, `main.1`, etc.) |

---

## ka11y-python — Crawler Data Models

### AsyncImageCrawler → `ImageMetadata`

**File:** `ka11y/crawler/crawler.py` + `ka11y/crawler/models.py`

| Field | Type | Description |
|-------|------|-------------|
| `src` | `str` | Resolved absolute image URL |
| `alt` | `str \| None` | `alt` attribute (`None` = missing, `""` = empty) |
| `title_attr` | `str` | `title` attribute |
| `aria_label` | `str` | `aria-label` attribute |
| `aria_labelledby` | `str` | Resolved text from `aria-labelledby` references |
| `aria_describedby` | `str` | Resolved description text |
| `aria_hidden` | `bool` | `aria-hidden="true"` |
| `role` | `str` | `role` attribute |
| `natural_width`, `natural_height` | `int` | Intrinsic image dimensions |
| `rendered_width`, `rendered_height` | `float` | `getBoundingClientRect()` dimensions |
| `aspect_ratio` | `float` | natural_width / natural_height |
| `in_link` | `bool` | Inside `<a>` element |
| `link_href` | `str` | Parent `<a>` href |
| `link_text` | `str` | Parent `<a>` visible text |
| `in_button` | `bool` | Inside `<button>` |
| `button_text` | `str` | Parent `<button>` visible text |
| `in_figure` | `bool` | Inside `<figure>` |
| `figcaption_text` | `str` | Associated `<figcaption>` text |
| `nearest_heading` | `str` | Closest ancestor `h1`–`h6` text |
| `surrounding_text` | `str` | 50 chars of surrounding text |
| `srcset` | `str` | `srcset` attribute |
| `sizes` | `str` | `sizes` attribute |
| `loading` | `str` | `loading` attribute (`lazy`/`eager`) |
| `decoding` | `str` | `decoding` attribute |
| `data_src` | `str` | `data-src` for lazy-load images |
| `crossorigin` | `str` | `crossorigin` attribute |
| `usemap` | `str` | `usemap` attribute |
| `css_display` | `str` | Computed `display` |
| `css_visibility` | `str` | Computed `visibility` |
| `css_opacity` | `str` | Computed `opacity` |
| `css_object_fit` | `str` | Computed `object-fit` |
| `css_position` | `str` | Computed `position` |
| `css_overflow` | `str` | Computed `overflow` |
| `classification` | `str` | Result of ClassifyAssets cascade |
| `sub_type` | `str` | Functional subtype (logos, icons, buttons) |
| `is_functional` | `bool` | Interactive image flag |
| `is_decorative` | `bool` | Decorative image flag |
| `is_complex` | `bool` | Complex image (charts, diagrams) |
| `is_text_image` | `bool` | OCR-detected text in image |
| `is_logo` | `bool` | Logo image |
| `is_icon` | `bool` | Icon image |
| `is_button` | `bool` | Button image |
| `html_snippet` | `str` | Truncated outerHTML (≤600 chars) |

---

### AsyncFormCrawler → `FormInputData`

**File:** `ka11y/crawler/forms_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | `INPUT`, `TEXTAREA`, or `SELECT` |
| `type` | `str` | Input type (`text`, `email`, `password`, etc.) |
| `element_id` | `str` | `id` attribute |
| `element_name` | `str` | `name` attribute |
| `placeholder` | `str` | `placeholder` attribute |
| `aria_label` | `str` | `aria-label` |
| `aria_labelledby` | `str` | Resolved labelledby text |
| `has_explicit_label` | `bool` | Has `<label for="id">` |
| `has_wrapping_label` | `bool` | Wrapped in `<label>` |
| `wrapping_label_text` | `str` | Wrapping label text |
| `label_text` | `str` | Text of associated `<label for>` |
| `has_any_label` | `bool` | Has any accessible label |
| `required` | `bool` | `required` attribute |
| `aria_required` | `bool` | `aria-required="true"` |
| `aria_invalid` | `str` | `aria-invalid` value |
| `autocomplete` | `str` | `autocomplete` attribute value |
| `aria_describedby` | `str` | `aria-describedby` attribute value |
| `error_element_id` | `str` | Resolved error element ID |
| `error_element_role` | `str` | Role of error element |
| `error_element_text` | `str` | Text content of error element |
| `error_has_role_alert` | `bool` | Error element has `role="alert"` |
| `error_has_aria_live` | `str` | `aria-live` value on error element |
| `html_snippet` | `str` | Truncated outerHTML (≤600 chars) |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### InteractiveElementCrawler → `InteractiveElementData`

**File:** `ka11y/crawler/interactive_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Element tag name |
| `role` | `str` | ARIA role (explicit or implicit) |
| `visible_label` | `str` | Visible text rendered on screen |
| `aria_label` | `str` | `aria-label` attribute |
| `aria_labelledby` | `str` | Resolved labelledby text |
| `title_attr` | `str` | `title` attribute |
| `value_attr` | `str` | `value` attribute (submit buttons) |
| `alt_attr` | `str` | `alt` attribute (input type=image) |
| `accessible_name` | `str` | Computed AccName 1.1 result |
| `element_id` | `str` | `id` attribute |
| `element_name` | `str` | `name` attribute |
| `input_type` | `str` | For `<input>`, the `type` attribute |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### TargetSizeCrawler → `TargetSizeData`

**File:** `ka11y/crawler/target_size_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `rendered_width_px` | `float` | `getBoundingClientRect().width` |
| `rendered_height_px` | `float` | `getBoundingClientRect().height` |
| `padding_top_px` | `float` | Computed top padding |
| `padding_right_px` | `float` | Computed right padding |
| `padding_bottom_px` | `float` | Computed bottom padding |
| `padding_left_px` | `float` | Computed left padding |
| `is_inline_exception` | `bool` | Inline `<a>` in text (exception 1) |
| `is_ua_controlled_exception` | `bool` | Native checkbox/radio (exception 4) |
| `is_offset_exception` | `bool` | Sufficient spacing (exception 5) |
| `required_offset_x_px` | `float` | Required X offset for exception 5 |
| `required_offset_y_px` | `float` | Required Y offset for exception 5 |
| `nearest_target_gap_x_px` | `float` | Gap to nearest X neighbor |
| `nearest_target_gap_y_px` | `float` | Gap to nearest Y neighbor |
| `passes_size` | `bool` | Pre-computed pass flag |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### MediaCrawler → `MediaElementData`

**File:** `ka11y/crawler/media_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | `AUDIO` or `VIDEO` |
| `element_id` | `str` | `id` attribute |
| `src` | `str` | Media source URL |
| `has_autoplay` | `bool` | `autoplay` attribute |
| `has_controls` | `bool` | `controls` attribute |
| `has_loop` | `bool` | `loop` attribute |
| `is_muted` | `bool` | `muted` attribute |
| `tracks` | `List[TrackData]` | `<track>` children (kind, src, srclang, label) |
| `aria_hidden` | `bool` | `aria-hidden="true"` |
| `role` | `str` | `role` attribute |
| `aria_label` | `str` | `aria-label` |
| `aria_describedby_text` | `str` | Resolved description text |
| `nearby_links` | `List[str]` | `<a>` elements in parent container |
| `nearby_text` | `str` | Parent container text |
| `nearby_details` | `List[str]` | `<details>` block summaries |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### MovingContentCrawler → `MovingContentData`

**File:** `ka11y/crawler/moving_content_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `content_type` | `str` | video_autoplay, animated_gif, css_animation, carousel_autoplay, marquee_element, blink_element |
| `tag` | `str` | Element tag |
| `element_id` | `str` | `id` attribute |
| `src` | `str` | Media source |
| `animation_name` | `str` | CSS animation name |
| `animation_duration_seconds` | `float` | Duration in seconds |
| `animation_iteration_count` | `str` | `"infinite"` or numeric |
| `loops` | `bool` | Loops flag |
| `duration_seconds` | `float` | Video duration (-1 = infinite) |
| `duration_known` | `bool` | Whether the media duration was known at extraction time |
| `starts_automatically` | `bool` | Auto-plays without user action |
| `has_video_controls` | `bool` | `<video controls>` present |
| `has_pause_button` | `bool` | Nearby pause/stop button detected |
| `has_mechanism` | `bool` | Any control mechanism present |
| `applicability_exception` | `str` | Structured exemption such as `loading_indicator` |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### SensoryCrawler → `SensoryElementData`

**File:** `ka11y/crawler/sensory_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Element tag |
| `element_id` | `str` | `id` attribute |
| `element_class` | `str` | `class` attribute |
| `text` | `str` | Visible inner text |
| `aria_label` | `str` | `aria-label` attribute |
| `aria_labelledby` | `str` | Resolved labelledby IDs |
| `placeholder` | `str` | `placeholder` attribute |
| `value` | `str` | `value` attribute (for button-like inputs) |
| `role` | `str` | ARIA role |
| `parent_tag` | `str` | Parent element tag |
| `nearest_heading` | `str` | Closest `h1`–`h6` ancestor text |
| `title` | `str` | `title` tooltip attribute |
| `lang` | `str` | Closest `lang=` ancestor value |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### TextSpacingCrawler → `TextSpacingData`

**File:** `ka11y/crawler/text_spacing_crawler.py`

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Element tag |
| `element_id` | `str` | `id` attribute |
| `class_name` | `str` | `class` attribute |
| `text_length` | `int` | Character count of visible text |
| `text_preview` | `str` | First 100 chars of text |
| `height` | `str` | CSS `height` value |
| `min_height` | `str` | CSS `min-height` value |
| `overflow` | `str` | CSS `overflow` value |
| `has_fixed_height` | `bool` | Height is pixel-fixed (not `auto`) |
| `has_overflow_hidden` | `bool` | `overflow: hidden` or `clip` |
| `is_clipped` | `bool` | `scrollHeight > clientHeight` or `scrollWidth > clientWidth` |
| `html_snippet` | `str` | Truncated outerHTML |
| `selector`, `element_ref_id`, `frame_path` | `str` | Provenance fields carried by the universal static snapshot |

---

### RenderedLayoutCrawler → `PageSnapshot` + `ElementSnapshot`

**File:** `ka11y/crawler/rendered_layout_crawler.py`

**PageSnapshot fields:**

| Field | Type | Description |
|-------|------|-------------|
| `page_url` | `str` | URL crawled |
| `viewport_width`, `viewport_height` | `int` | Active viewport dimensions |
| `document_scroll_width` | `int` | Total page width |
| `document_scroll_height` | `int` | Total page height |
| `has_horizontal_scroll` | `bool` | Page introduces horizontal scroll |
| `has_vertical_scroll` | `bool` | Page has vertical scroll |
| `elements` | `List[ElementSnapshot]` | All visible elements |

**ElementSnapshot fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tag` | `str` | Element tag |
| `element_id` | `str` | `id` attribute |
| `text` | `str` | Text content |
| `html_snippet` | `str` | Truncated outerHTML |
| `rect.x`, `rect.y`, `rect.width`, `rect.height` | `float` | Bounding box |
| `rect.top`, `rect.right`, `rect.bottom`, `rect.left` | `float` | Bounding box edges |
| `visible` | `bool` | Element visibility |
| `text_clipped` | `bool` | Text overflow detected |
| `focusable` | `bool` | Element is keyboard-focusable |

---

## ka11y-python — Rule-by-Rule Data Requirements

### 1.1.1 — Non-text Content (AltTextAccessibilityAuditor)

**Crawler:** `AsyncImageCrawler`

| Fields Used | Purpose |
|------------|---------|
| `alt`, `aria_label`, `aria_labelledby`, `aria_hidden`, `role` | Accessible name computation and presentational detection |
| `classification`, `sub_type`, `is_functional`, `is_decorative` | Determines expected alt pattern |
| `in_link`, `link_text`, `in_button`, `button_text` | Context-specific accessible name requirements |
| OCR `detections` | Compares detected text to `alt` text (cosine similarity) |

---

### 1.2.1 — Audio-only and Video-only (MediaAuditor)

**Crawler:** `MediaCrawler`

| Fields Used | Purpose |
|------------|---------|
| `tag`, `src`, `is_muted`, `has_loop`, `has_autoplay` | Media classification and gate checks |
| `tracks` (kind, srclang) | Transcript/description track detection |
| `aria_label`, `aria_describedby_text` | Accessible name and description as transcript proxy |
| `nearby_links`, `nearby_text`, `nearby_details` | External transcript detection |

---

### 1.3.3 — Sensory Characteristics (SensoryCharacteristicsAuditor)

**Crawler:** `SensoryCrawler`

| Fields Used | Purpose |
|------------|---------|
| `text`, `aria_label`, `aria_labelledby`, `placeholder`, `value` | Instruction text extraction |
| `role`, `title`, `nearest_heading` | Context determination |
| `lang` | Language-aware tokenization (EN spaCy vs CJK regex) |

**Language word taxonomies used:**

| Language | Sensory Category | Example Keywords |
|----------|-----------------|-----------------|
| English | Color | red, blue, green, color |
| English | Shape | round, square, circular |
| English | Size | large, small, big |
| English | Position | left, right, above, below |
| English | Orientation | horizontal, vertical, upward |
| English | Sound | loud, quiet, beeping |
| English | Brightness | bright, dark, dim |
| Japanese | Color | 赤, 青, 緑, 黄色 |
| Japanese | Shape | 丸, 四角, 円形 |
| Japanese | Size | 大きい, 小さい |
| Japanese | Position | 左, 右, 上, 下 |
| Japanese | Orientation | 横向き, 縦向き |
| Japanese | Sound | 音, 鳴る |
| Japanese | Brightness | 明るい, 暗い |
| Japanese | Texture | 滑らか, 粗い |

---

### 1.4.4 — Resize Text (TextResizeEvaluator)

**Crawler:** `RenderedLayoutCrawler` (baseline + 200% text size)

| Fields Used | Purpose |
|------------|---------|
| `elements[].text_clipped` | Clipping detection post-resize |
| `elements[].visible` | Visibility change detection |
| `has_horizontal_scroll` | Horizontal scroll introduced at 200% |
| `document_scroll_width` vs `viewport_width` | Overflow measurement |

---

### 1.4.5 — Images of Text (AltTextAccessibilityAuditor)

**Crawler:** `AsyncImageCrawler` + OCR `TextDetector`

| Fields Used | Purpose |
|------------|---------|
| `contains_text` | OCR text detection flag |
| `classification` | Exempt logos, diagrams, maps |
| OCR `detections` | Detected text evidence |

---

### 1.4.10 — Reflow (ReflowEvaluator)

**Crawler:** `RenderedLayoutCrawler` at 320px viewport

| Fields Used | Purpose |
|------------|---------|
| `document_scroll_width`, `viewport_width` | Horizontal overflow at 320px |
| `elements[].tag`, `elements[].html_snippet` | Exemption detection (table, svg, canvas, iframe, pre, code) |
| `elements[].rect.right` | Element overflow detection |

---

### 1.4.11 — Non-text Contrast (ContrastAnalyser)

**Crawler:** `AsyncImageCrawler` + OCR `TextDetector`

| Fields Used | Purpose |
|------------|---------|
| OCR `contrast_violations_count` | UI element contrast failures |
| Image foreground/background colors | Computed by OCR module |

---

### 1.4.12 — Text Spacing (TextSpacingAuditor)

**Crawler:** `TextSpacingCrawler` + `RenderedLayoutCrawler`

| Fields Used | Purpose |
|------------|---------|
| `has_fixed_height`, `has_overflow_hidden` | Static clipping risk |
| `is_clipped` | Scroll overflow before spacing applied |
| Rendered: `text_clipped` after CSS override | Actual clipping with WCAG 1.4.12 spacing applied |

---

### 1.3.4 — Orientation (OrientationEvaluator)

**Crawler:** `RenderedLayoutCrawler` (portrait + landscape snapshots)

| Fields Used | Purpose |
|------------|---------|
| Portrait vs landscape element counts | Content availability comparison |
| `elements[].focusable` counts | Interactive element availability |
| Rotate overlay text detection | "Please rotate" message |
| `css_transform_lock` heuristic | `body { transform: rotate(...) }` |
| `body_overflow_hidden` heuristic | Scrolling blocked in one orientation |

---

### 2.2.2 — Pause, Stop, Hide (PauseStopHideAuditor)

**Crawler:** `MovingContentCrawler`

| Fields Used | Purpose |
|------------|---------|
| `content_type` | Identifies the kind of moving content |
| `starts_automatically` | Gate 1: must auto-start |
| `duration_seconds`, `animation_iteration_count`, `loops` | Gate 2: must be long/infinite |
| `has_video_controls`, `has_pause_button`, `has_mechanism` | Gate 3: mechanism must be absent |

---

### 2.4.11 — Focus Not Obscured Minimum (FocusNotObscuredMinimumEvaluator)

**Crawler:** `RenderedLayoutCrawler` with focus simulation

| Fields Used | Purpose |
|------------|---------|
| Overlay elements (fixed/sticky) | Sticky header/footer identification |
| `overlay[].rect` | Bounding box of obscuring elements |
| `overlay[].z_index` | Stacking order |
| Focused element visible area | Post-focus visibility |
| Obscuration `> 50%` | Fail threshold (minimum: ≥1px visible) |

---

### 2.4.12 — Focus Not Obscured Enhanced (FocusNotObscuredEnhancedEvaluator)

**Crawler:** `RenderedLayoutCrawler` with focus simulation

| Fields Used | Purpose |
|------------|---------|
| Same as 2.4.11 | Same data |
| Obscuration `> 50%` | Fail threshold (enhanced: ≥50% visible) |

---

### 2.4.13 — Content on Hover or Focus (HoverFocusContentEvaluator)

**Crawler:** `RenderedLayoutCrawler` with hover simulation

| Fields Used | Purpose |
|------------|---------|
| Hover/focus trigger candidates | `aria-expanded`, `data-tooltip`, `title`, `aria-haspopup` |
| Content visibility before/after hover | Reveal detection |
| Escape key response | Dismissible check |
| Content hover persistence | Hoverable content check |
| Focus-triggered content | Focusable content check |

---

### 2.5.3 — Label in Name (LabelInNameAuditor)

**Crawler:** `InteractiveElementCrawler`

| Fields Used | Purpose |
|------------|---------|
| `visible_label` | The label users see |
| `accessible_name` | Computed programmatic name |
| `aria_label`, `aria_labelledby` | ARIA overrides |
| `title_attr`, `value_attr`, `alt_attr` | Native name sources |
| CJK detection | `visible_label` CJK → substring match instead of `\b` regex |

---

### 2.5.8 — Target Size Minimum (TargetSizeAuditor)

**Crawler:** `TargetSizeCrawler`

| Fields Used | Purpose |
|------------|---------|
| `rendered_width_px`, `rendered_height_px` | Primary size check (≥ 24×24) |
| `is_inline_exception` | Skip inline links |
| `is_ua_controlled_exception` | Skip native checkbox/radio |
| `is_offset_exception` | Skip targets with sufficient spacing |
| `required_offset_x_px`, `required_offset_y_px` | Exception 5 computation |
| `nearest_target_gap_x_px`, `nearest_target_gap_y_px` | Exception 5 verification |

---

### 3.3.1 — Error Identification (FormAccessibilityAuditor)

**Crawler:** `AsyncFormCrawler`

| Fields Used | Purpose |
|------------|---------|
| `required`, `aria_required` | Required field detection |
| `aria_describedby`, `error_element_id` | Error container linkage |
| `error_has_role_alert`, `error_has_aria_live` | Live region announcement |

---

### 3.3.2 — Labels or Instructions (FormAccessibilityAuditor)

**Crawler:** `AsyncFormCrawler`

| Fields Used | Purpose |
|------------|---------|
| `label_text`, `has_any_label`, `placeholder` | Accessible label presence |
| `required`, `aria_required` | Required field marking |
| `type`, `name`, `autocomplete` | Personal data autocomplete requirement |

---

## Cross-Service Field Mapping

Fields that exist in both services under different names:

| Concept | ka11y-node (page.evaluate) | ka11y-python (crawler field) |
|---------|---------------------------|------------------------------|
| Alt text | `el.getAttribute('alt')` | `ImageMetadata.alt` |
| ARIA label | `el.getAttribute('aria-label')` | `*.aria_label` |
| ARIA labelledby | `el.getAttribute('aria-labelledby')` + `getElementById` | `*.aria_labelledby` (pre-resolved) |
| ARIA describedby | `el.getAttribute('aria-describedby')` | `FormInputData.aria_describedby` |
| Role | `el.getAttribute('role')` | `*.role` |
| HTML snippet | `el.outerHTML.slice(0, N)` | `*.html_snippet` |
| Computed style | `getComputedStyle(el).property` | `*.css_*` fields or RenderedLayoutCrawler |
| Bounding rect | `el.getBoundingClientRect()` | `ElementSnapshot.rect.*` |
| Page URL | `page.url()` | `PageSnapshot.page_url` |
| Text content | `el.textContent.trim()` | `*.text` or `*.text_preview` |
| Required | `el.hasAttribute('required')` | `FormInputData.required` |
| Aria-required | `el.getAttribute('aria-required')` | `FormInputData.aria_required` |

**Resolution approach:** ka11y-node resolves references (aria-labelledby, aria-describedby) at query time inside `page.evaluate()`. ka11y-python resolves them during the crawler phase and stores the resolved text, so auditors receive pre-resolved values.
