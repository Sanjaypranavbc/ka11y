# a11y-node — Rule-by-Rule Analysis

> Generated: 2026-04-10
> Scope: `/src/custom-checks/` (24 checks) + axe-core integration
> Node: Express + Puppeteer + axe-core

---

## Architecture & Request Flow

```
HTTP POST /api/v1/analyse-url
           │
           ▼
  ┌─────────────────────────────┐
  │  SSRF Guard (DNS + intercept│
  │  block private IP ranges)   │
  └────────────┬────────────────┘
               │
               ▼
  ┌─────────────────────────────┐
  │  Puppeteer: launch browser  │
  │  navigate to URL / inject   │
  │  HTML                       │
  └────────────┬────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
  axe-core.run()   Custom Checks
  (automated)      (static + interactive)
       │                │
       └───────┬────────┘
               │
               ▼
  ┌─────────────────────────────┐
  │  Merge + deduplicate results│
  │  Map to WCAG SC → findings  │
  └─────────────────────────────┘
               │
               ▼
     JSON response to client
```

### Custom Check Execution Model

```
Custom Checks Index
       │
       ├── Static checks (parallel)
       │     Every check runs page.evaluate() — no focus/navigation
       │
       └── Interactive checks (sequential — avoid state collision)
             focus-visible → focus-appearance → on-focus → on-input → keyboard-trap
```

---

## Language, Japanese Sites, and Config Readiness

### Current State (verified)

| Layer | Current behavior | Status |
|------|------------------|--------|
| Request language | `/analyse-url-flat` accepts `lang`, validates it, and passes it to the flat result mappers | ✅ |
| Localized rule copy | `rulesLoader.js` merges `i18n/rules.yml` with `i18n/locales/<lang>.yml`; `ja.yml` exists | ✅ |
| Japanese finding text | Rule names, descriptions, and suggested fixes can already be returned in Japanese | ✅ |
| Custom-check behavior | Many checks still embed JP/CJK words, patterns, and thresholds directly in JS | ❌ |
| Cross-repo consistency with `a11y-python` | No shared config contract for behavioral language assets | ❌ |

Verified examples of hardcoded JP/CJK behavior in checks:

- `audio-transcript.check.js` embeds transcript keywords in English + Japanese
- `pointer-cancellation.check.js` embeds Japanese action terms such as `送信`, `購入`, `削除`
- `multiple-ways.check.js` embeds multilingual search terms including Japanese
- `link-purpose.check.js` includes Japanese equivalents of vague link text
- `consistent-help.check.js` includes Japanese chat/support widget heuristics
- `error-prevention.check.js` and `redundant-entry.check.js` embed Japanese commerce/process terms
- `pronunciation.check.js` hardcodes CJK language prefixes and the CJK density threshold

### Required Production Direction

Japanese support in `a11y-node` must be split into two explicit layers:

1. `i18n/locales/ja.yml`
   Keeps localized rule metadata and suggested fixes.
2. `i18n/check-assets/ja.yml`
   Holds Japanese/CJK detection behavior for custom checks.

### Proposed Flow

```
HTTP POST /api/v1/analyse-url-flat (lang="ja")
               │
               ├── getRules("ja")
               │      -> localized rule names / descriptions / fixes
               │
               ├── getCheckAssets("ja")
               │      -> transcript keywords / action verbs / search terms /
               │         support-widget labels / commerce patterns / CJK thresholds
               │
               └── runAll(page, { lang: "ja", assets })
                        ├── static checks use assets inside page.evaluate(...)
                        └── interactive checks use assets in JS + post-processing
```

### Suggested Config Files

| File | Purpose |
|------|---------|
| `i18n/check-assets/en.yml` | Default behavior assets for custom checks |
| `i18n/check-assets/ja.yml` | Japanese/CJK-specific behavior assets |
| `src/utils/checkAssetsLoader.js` | Cache and merge check assets by language |
| `src/custom-checks/index.js` | Pass `{ lang, assets }` into each custom check |
| `src/services/accessibility.service.js` | Load assets once per request and pass them to `runAll()` |

### Suggested Asset Shape

```yaml
media:
  transcript_keywords:
    - "書き起こし"
    - "文字起こし"
    - "トランスクリプト"
    - "字幕"
    - "キャプション"

interaction:
  action_verbs:
    - "送信"
    - "購入"
    - "削除"
    - "確認"
    - "登録"
    - "注文"

navigation:
  search_terms:
    - "検索"

support:
  help_widget_labels:
    - "チャット"
    - "お問い合わせ"
    - "サポート"
    - "ヘルプ"

commerce:
  high_risk_terms:
    - "購入"
    - "決済"
    - "お支払い"
    - "請求"
    - "注文確認"

cjk:
  lang_prefixes: ["ja", "ja-JP", "zh", "zh-TW", "zh-CN", "ko"]
  ratio_threshold: 0.05
  ruby_coverage_threshold: 0.30
```

### Japanese Edge Cases The Node Plan Must Keep

| Edge case | Required behavior |
|----------|-------------------|
| Pure Japanese page with `lang="ja"` | Use Japanese assets immediately |
| Mixed EN/JA page with explicit `lang="ja"` sections | Run CJK-sensitive checks at section level, not only page level |
| Unlabelled Japanese page | Fall back to CJK-density heuristics |
| Full-width punctuation / kana / kanji | Normalize safely before keyword matching |
| Japanese support widgets | Use JP labels for help-widget detection |
| Japanese transcript links / `<details>` transcripts | Match JP transcript keywords from config |
| Kana-only or mixed-script content | Avoid assuming all pronunciation issues are kanji-only |
| Threshold drift between node and python | Keep shared asset keys and values aligned |

---

## Rule-by-Rule Analysis

---

### 1.2.1 — Audio-only & Video-only (Prerecorded)
**Check:** `audio-transcript.check.js`

#### Flowchart
```
page has <audio> elements?
       │
      No ──► PASS (not applicable)
       │
      Yes
       │
       ▼
for each <audio>:
  ├── has <track kind="captions|descriptions|subtitles">? ──► ✓
  ├── nearby transcript link in semantic container?         ──► ✓
  │     (a[href] with "transcript|caption|text version|…")
  ├── <figcaption> in parent <figure>?                     ──► ✓
  ├── aria-describedby → element with text?                ──► ✓
  └── none found ──► ISSUE
       │
all issues empty ──► PASS
any issues ──► INCOMPLETE (manual verification needed)
```

#### Cases Covered
| Case | Detection Method |
|------|-----------------|
| `<track kind="captions">` inside audio | Direct DOM query |
| Transcript hyperlink in parent container | Link text regex match |
| `<figcaption>` in wrapping `<figure>` | DOM ancestor walk |
| `<details>` transcript block in nearby container | Summary/text regex match |
| `aria-describedby` → text element | ID lookup |

#### Cases Missed / False Negative Risks
| Case | Why missed |
|------|-----------|
| Third-party embeds (Spotify, SoundCloud iframes) | Not `<audio>` in DOM |
| Transcript on separate linked page (PDF, external URL) | Link detected but content unverified |
| Dynamically rendered transcripts (AJAX/button-reveal) | Not present at page load |
| Transcript patterns inside shadow DOM | Check uses document-scoped selectors only |

---

### 1.3.2 — Meaningful Sequence
**Check:** `meaningful-sequence.check.js`

#### Flowchart
```
collect all flex/grid containers (max 500)
       │
       ▼
for each container:
  ├── flex-direction: row-reverse?
  │     └── is RTL language (ar/he/fa/ur/yi/…)? ──► SKIP (correct for RTL)
  │     └── is LTR? ──► ISSUE (visual vs DOM order mismatch)
  ├── flex-direction: column-reverse? ──► ISSUE (always)
  └── has children with CSS order ≠ 0?
        └── do visual order indices differ from DOM order? ──► ISSUE
       │
no issues ──► PASS
any issues ──► FAIL
```

#### Cases Covered
| Case | Detection |
|------|-----------|
| `flex-direction: row-reverse` on LTR | getComputedStyle comparison |
| `flex-direction: column-reverse` | getComputedStyle |
| CSS `order` property reordering | parseInt(order) vs DOM index |
| RTL exemption (12 language codes) | `lang` attribute match |

#### Cases Missed
| Case | Why |
|------|-----|
| `grid-column / grid-row` explicit placement | Only checks flex-direction + order |
| `float: left/right` reordering | Not detected |
| CSS multicolumn (`column-count`) | Not detected |
| `grid-auto-flow: dense` reordering | Not detected |

---

### 1.3.4 — Orientation
**Check:** `orientation.check.js`

#### Flowchart
```
┌──────────────────────────────────────────┐
│ Check 1: Inline script lock detection    │
│  screen.orientation.lock() / mozLock…   │
│  webkitLock… / window.orientation = …   │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ Check 2: CSS forced rotation             │
│  transform: rotate(90deg/270deg) on      │
│  structural containers (flex/grid/main…) │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ Check 3: @media orientation queries      │
│  that hide content (display:none,        │
│  visibility:hidden, opacity:0…)          │
│  OR break layout (fixed/absolute + vw/vh)│
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ Check 4: <meta name="viewport"           │
│  content="orientation=…">               │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ Check 5: Web App Manifest                │
│  fetch manifest → orientation field      │
└────────────────┬─────────────────────────┘
                 │
any issue ──► FAIL / INCOMPLETE
none ──► PASS
```

#### Cases Covered
- JS API lock (`screen.orientation.lock`, vendor prefixes)
- CSS rotation on structural elements
- `@media (orientation: portrait/landscape)` display:none
- `<meta viewport>` orientation attribute
- Web App Manifest orientation field
- Cross-origin stylesheets → flagged for manual review

#### Cases Missed
| Case | Why |
|------|-----|
| `max-aspect-ratio` / `min-aspect-ratio` media queries effectively locking | Not orientation keyword |
| `writing-mode: vertical-rl` locking visual layout | Not detected |
| Fullscreen API + orientation request | Not detected |
| `maximum-scale=1` in viewport (prevents rotation resize) | Not orientation lock per se |

---

### 1.4.1 — Use of Color
**Check:** `use-of-color.check.js`

#### Flowchart
```
collect inline-text links: p a, li a, td a, th a,
  blockquote a, article > p a, dd a (max 150)
       │
       ▼
for each link:
  skip if: no text content (icon-only)
       │
  compute getComputedStyle
       │
  walk up DOM to find non-<a> ancestor styles
       │
  ┌──────── Has non-color visual cue? ─────────────────┐
  │ • textDecorationLine ≠ "none"         (underline)  │
  │ • borderBottomWidth > 0               (fake UL)    │
  │ • outlineWidth > 0                    (outline)    │
  │ • backgroundColor differs from ancestor (bg change)│
  │ • fontWeight ≥ ancestor + 100         (bold delta) │
  │ • fontStyle differs from ancestor     (italic)     │
  └────────────────────────┬───────────────────────────┘
                           │
                    Has cue? ──► PASS
                           │
                          No
                           │
                     link color actually differs from
                     ancestor color (> 15 per channel)?
                           │
                    Yes ──► FAIL (color-only distinction)
                          No ──► PASS (no visual distinction at all)
```

#### Cases Covered
- Underline / overline / line-through
- Fake underline (border-bottom)
- Outline
- Background color change
- Font-weight increase ≥ 100 units
- Font style (italic)
- RGB channel comparison with 15-unit tolerance

#### Cases Missed
| Case | Why |
|------|-----|
| Links in `<section>` without `<p>` wrapper | Selector narrowed intentionally |
| SVG `<text>` or `<a>` elements with color-only cue | Not queried |
| Links in High Contrast Mode | OS-level override not detectable |
| Links distinguished by icon color only (no text color change) | Icon styling not checked |

---

### 1.4.5 — Images of Text
**Check:** `images-of-text.check.js`

#### Flowchart
```
for each img[src] with non-empty alt:
  skip if: alt="" OR role=presentation/none
  skip if: LOGO_PATTERN matches alt/src/class/id
       │
  Scoring:
  ├── src path matches text-image keywords?    → +2 pts (strong)
  ├── class/id matches text-image keywords?    → +1 pt
  ├── alt text ≥ 5 words (or ≥ 8 CJK chars)?  → +1 pt
  └── alt looks like sentence (punctuation,
      capital + 4+ words, CJK ≥ 12 chars)?    → +1 pt
       │
  score ≥ 3 → FAIL
  score = 2 → INCOMPLETE (needs review)
  score < 2 → pass

Also check CSS background-image on elements with text content:
  [style*="background-image"], [class*="bg-"], [class*="background"]
  → only flagged if src matches text-image src pattern
```

#### Cases Covered
- `<img>` with text-image src path keywords (banner, headline, quote, etc.)
- Class/id signal matching
- Long or sentence-structured alt text
- Logo/brand exemption
- CSS background-image with text-like URL

#### Cases Missed
| Case | Why |
|------|-----|
| `<canvas>` with rendered text | Not an `<img>` |
| `<svg>` with embedded `<text>` elements | Not checked |
| Very short text images (< 2 words in alt) | Score < 2 |
| Infographic images (complex but valid) | Heuristic may over-flag |

---

### 2.1.2 — No Keyboard Trap
**Check:** `keyboard-trap.check.js`

#### Flowchart
```
Tab forward up to 200 times (60ms settle each):
  track last 4 focused elements by stable key
       │
  Cycle detected?
  ├── Single-element stuck: [A, A, A, A]
  └── Two-element cycle:    [A, B, A, B]
       │
  Yes → press Escape → Tab again
          │
       Still same? ──► FAIL (confirmed trap)
          │
         No ──► continue (Escape broke it, not a WCAG violation)
       │
  Also run: Tab backward (Shift+Tab, 50 attempts)
  Same cycle detection logic
       │
any trap found ──► FAIL
none ──► PASS
```

#### Cases Covered
- Single-element focus loops
- Two-element alternating cycles
- Escape key verification (distinguishes modal traps from bugs)
- Forward and backward Tab testing

#### Cases Missed
| Case | Why |
|------|-----|
| Arrow key traps in custom widgets (tree, listbox, grid) | Only Tab/Shift+Tab tested |
| Traps in iframes / Shadow DOM | Puppeteer stays in main frame |
| Traps requiring > 200 Tab presses to trigger | Limit too low |
| Modal that opens on focus then traps | Not simulated (no click) |

---

### 2.1.4 — Character Key Shortcuts
**Check:** `character-key-shortcuts.check.js`

#### Flowchart
```
Scan 1 — accesskey attributes:
  find all elements with [accesskey]
  filter: single letter/symbol (not digit, not multi-char)
  → ISSUE for each (no modifier required in HTML spec)

Scan 2 — inline event handlers:
  find onkeydown / onkeypress / onkeyup attributes
  handler matches single-char key pattern?
  (event.key === 'x', e.keyCode in 65-90, etc.)
       │
  Check within 200 chars for modifier guard
  (ctrlKey, altKey, metaKey, shiftKey)?
       │
  No guard → ISSUE

Scan 3 — inline <script> addEventListener:
  scan script text blocks for 'keydown'/'keypress'/'keyup'
  matches single-char handler?
  check nearby (120 chars) for modifier guard?
  No guard → ISSUE
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- `accesskey` attribute (single-char letters/symbols)
- Inline `onkeydown/onkeypress/onkeyup` handlers
- Inline `<script>` addEventListener with key check
- Modifier guard detection (Ctrl/Alt/Meta/Shift)

#### Cases Missed
| Case | Why |
|------|-----|
| External script file shortcuts | Can't read cross-origin scripts |
| Delegated handlers on `document`/`window` | Not scanned per element |
| Arrow key shortcuts without modifiers | Not in key pattern regex |
| Framework event bindings (Vue v-on:keydown, React onKeyDown) | Runtime handlers not in DOM |

---

### 2.4.5 — Multiple Ways
**Check:** `multiple-ways.check.js`

#### Flowchart
```
Count navigation mechanisms:
  1. Search: input[type=search] / [role=search] /
             form[action*=search] / placeholder*=search / aria-label*=search
  2. Sitemap: a[href*=sitemap] / text "sitemap" in links
  3. Navigation: <nav> / [role=navigation] elements (count distinct)
  4. Breadcrumb: aria-label=breadcrumb / class*=breadcrumb / schema BreadcrumbList
  5. Table of contents: [id*=toc] / [class*=toc] / aria-label*="table of contents"
       │
  mechanisms ≥ 2 → PASS
  mechanisms = 1 → FAIL
  mechanisms = 0 → FAIL (or not applicable for single-page)
```

#### Cases Covered
- Search form/widget
- Sitemap link
- Primary/secondary navigation elements
- Breadcrumb trail
- Table of contents

#### Cases Missed
| Case | Why |
|------|-----|
| Keyword/alphabetical index page | Not detected |
| Single-page apps with client-side routing | Nav detected but may not count as "multiple ways" |
| Non-English search input labels | Only English/Japanese patterns |
| Site with search-only navigation | Would pass with 1 nav + 1 search |

---

### 2.4.7 — Focus Visible
**Check:** `focus-visible.check.js` (interactive)

#### Flowchart
```
Collect up to 100 focusable elements:
  a[href], button:not([disabled]), input, select, textarea,
  [tabindex]:not([tabindex="-1"])
  Use stable selectors (unique id → #escape / fallback DOM index)
       │
for each element:
  ① blur() → capture unfocused styles
    (outline, boxShadow, border, backgroundColor, color)
       │
  ② focus() → wait 80ms (transitions settle)
       │
  ③ capture focused styles
       │
  ④ Compare:
    • outline changed AND not transparent/invisible? → visible
    • boxShadow changed AND ≠ "none"?               → visible
    • borderColor or borderWidth changed?            → visible
    • backgroundColor changed?                       → visible
    • color changed?                                 → visible
       │
  None changed → ISSUE
       │
  blur() → wait 80ms → next element

any issue → FAIL
none → PASS
```

#### Cases Covered
- Outline changes (incl. transparency check)
- Box-shadow appearance
- Border color/width change
- Background color change
- Text color change
- CSS transition settle delay (80ms)

#### Cases Missed
| Case | Why |
|------|-----|
| `:focus-visible` styles (not `:focus`) | `el.focus()` triggers `:focus`, not always `:focus-visible` |
| Focus indicators on pseudo-elements (`::before/::after`) | Not detectable via getComputedStyle on element |
| Scale/transform-based indicators | Not checked |
| Opacity fade-in indicator | Excluded (B16) to avoid false passes from animation children |

---

### 2.4.8 — Location
**Check:** `location.check.js`

#### Flowchart
```
Check for location indicators:
  ┌─ Breadcrumb ──────────────────────────────────────────────┐
  │ [aria-label*="breadcrumb" i]                              │
  │ [class*="breadcrumb" i] / [id*="breadcrumb" i]           │
  │ [itemtype*="BreadcrumbList"]                              │
  └───────────────────────────────────────────────────────────┘
  ┌─ Active location in nav ──────────────────────────────────┐
  │ aria-current="page" inside nav                            │
  │ .active or [aria-selected="true"] inside nav              │
  └───────────────────────────────────────────────────────────┘
  ┌─ Sitemap link ────────────────────────────────────────────┐
  │ a[href*="sitemap" i] / text "sitemap" in link             │
  └───────────────────────────────────────────────────────────┘
       │
  any found → PASS
  none → INCOMPLETE (multi-page sites need at least one)
```

#### Cases Covered
- Breadcrumb (ARIA, class, schema.org)
- `aria-current="page"` in navigation
- Active nav item patterns
- Sitemap link presence

#### Cases Missed
| Case | Why |
|------|-----|
| `aria-current="step"` (multi-step forms) | Only "page" value checked |
| Page title reflecting location | Not checked |
| JSON-LD breadcrumb (structured data) | Only DOM breadcrumb |

---

### 2.4.9 — Link Purpose (Link Only)
**Check:** `link-purpose.check.js`

#### Flowchart
```
for each a[href] (max 100):
  Build accessible name:
    1. aria-label attribute
    2. aria-labelledby → concat referenced elements' text
    3. img[alt] if icon-only link
    4. textContent (trim + collapse whitespace)
       │
  No accessible name → skip (axe link-name rule covers)
       │
  Test against GENERIC_LINK_RE:
  "click here", "here", "read more", "more", "learn more",
  "more info", "details", "continue", "go", "link", "this",
  "see more", "view more", "find out more", "click", "tap",
  "press here", "start", "begin", "open", "show", "hide", "toggle"
  + Japanese equivalents
       │
  matches → ISSUE
  no match → OK
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- All major generic link text patterns in English + Japanese
- ARIA accessible name precedence (label > labelledby > alt > text)
- Icon-only links deferred to axe

#### Cases Missed
| Case | Why |
|------|-----|
| Visually hidden text (`display:none` descendants) included in textContent | `textContent` ignores display |
| Links in tables where column header gives context | Context-based purpose (WCAG 2.4.4 SC) |
| Link with `title` attribute only (no aria-label, no text) | `title` not resolved |
| Short but specific links ("FAQ", "PDF") | May match "details" pattern incorrectly |

---

### 2.4.13 — Focus Appearance
**Check:** `focus-appearance.check.js` (interactive, WCAG 2.2 AA)

#### Flowchart
```
Collect up to 30 focusable elements (subset of focus-visible set)
       │
for each:
  ① Capture unfocused styles
  ② focus() → wait 80ms
  ③ Capture focused styles
       │
  Area check:
    outline-width ≥ 2px?  OR
    box-shadow spread ≥ 2px?
       │
  Contrast check:
    extract focus indicator color (outline or box-shadow color)
    extract effective background (element bg → body bg fallback)
    WCAG relative luminance formula:
      L = 0.2126*R + 0.7152*G + 0.0722*B
      (with linearization: c ≤ 0.03928 ? c/12.92 : ((c+0.055)/1.055)^2.4)
    contrast = (lighter + 0.05) / (darker + 0.05)
    contrast ≥ 3:1? → PASS indicator
       │
  area OK AND contrast OK → pass element
  area FAIL OR contrast FAIL → ISSUE

any issue → FAIL
none → PASS
```

#### Cases Covered
- Minimum area (2px outline/spread)
- 3:1 contrast ratio with background
- Transparent background fallback to body
- WCAG luminance formula

#### Cases Missed
| Case | Why |
|------|-----|
| Focus indicator on child element (not the focusable itself) | Only checks target element |
| CSS variables for colors (`var(--primary)`) | `getComputedStyle` resolves these — actually works |
| High Contrast Mode overrides | Not detectable from JS |
| Focus indicator via border (not outline/shadow) | Border checked in focus-visible but not for area/contrast here |

---

### 2.5.2 — Pointer Cancellation
**Check:** `pointer-cancellation.check.js`

#### Flowchart
```
find elements with [onmousedown] / [onpointerdown] / [onpointermove]
       │
for each:
  isVisualOnly = handler only changes styles / calls preventDefault?
    → skip (not an action)
  isAction = handler contains action keywords?
    (navigate, submit, location, dispatch, push, route, href,
     ajax, fetch, open, modal, dialog, cart, toggle, delete,
     update, save, confirm, trigger, activate, emit)
       │
  isAction AND not visual-only:
    has onmouseup / onpointerup / onclick on same element?
      Yes → cancellation path exists → OK
      No → ISSUE
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- `mousedown` / `pointerdown` / `pointermove` attribute handlers
- Action keyword detection in handler text
- Visual-only handler filtering
- Cancellation path via `mouseup` / `pointerup` / `click`

#### Cases Missed
| Case | Why |
|------|-----|
| Touch events (`ontouchstart`) | Not in selector |
| `addEventListener` handlers (not inline) | Not readable |
| Right-click suppression (`oncontextmenu="return false"`) | Not checked |
| Native input drag-to-select (false positive) | May flag `<input>` with onmousedown |

---

### 2.5.7 — Dragging Movements
**Check:** `dragging-movements.check.js`

#### Flowchart
```
Find draggable elements:
  native: [draggable="true"] / [ondragstart]
  libraries:
    react-beautiful-dnd: [data-rbd-draggable-id]
    dnd-kit: [data-dnd-kit-draggable]
    Sortable.js: .sortable-item / .ui-sortable / [data-sortable]
    jQuery UI: .ui-draggable
  deduplicate with Set
       │
for each draggable element:
  has single-pointer alternative nearby?
    button, [role=button], a[href]
    in: el itself / parent / siblings
      Yes → OK
      No → ISSUE
       │
any issue → FAIL
none (or no draggables) → PASS
```

#### Cases Covered
- Native HTML drag attributes
- Top 4 drag-and-drop libraries
- Single-pointer alternative detection (button/link nearby)
- Deduplication across detection methods

#### Cases Missed
| Case | Why |
|------|-----|
| `onpointerdown` + pointer move pattern (custom drag) | Not detected |
| Touch-only drag (`ontouchstart`) | Not detected |
| Libraries beyond the 4 supported (e.g. Interact.js) | Not in library list |
| Alternative is accessible but not a button/link | e.g. custom `role="menuitem"` |

---

### 3.1.6 — Pronunciation
**Check:** `pronunciation.check.js`

#### Flowchart
```
Detect CJK page:
  lang attribute: ja / zh / ko / ja-JP / zh-TW / etc.
  OR CJK character density ≥ 5% of visible text
       │
  Not CJK → PASS (not applicable)
       │
Count <ruby> elements
Count kanji text nodes inside vs outside ruby wrappers
(using TreeWalker over text nodes, Unicode CJK range check)
       │
ruby coverage = kanji-in-ruby / total-kanji
       │
coverage ≥ 30% → PASS
coverage > 0 but < 30% → INCOMPLETE (low coverage)
coverage = 0 → FAIL
```

#### Cases Covered
- Japanese, Chinese, Korean language detection
- `<ruby>` / `<rt>` element presence
- Kanji coverage percentage calculation
- CJK density heuristic for unlabeled pages
- Explicit section-level CJK `lang` scan on non-CJK pages

#### Cases Missed
| Case | Why |
|------|-----|
| Ruby on wrong reading order | Position not verified |
| Proper nouns needing ruby more than common kanji | Priority not differentiated |
| Kanji in `<img alt>` | Not in text nodes |
| Mixed CJK subsection without explicit `lang` inside mostly Latin page | Section scan depends on explicit `lang`, otherwise falls back to page/body heuristic |
| Kana-only ambiguous terms or non-kanji pronunciation issues | Check is ruby/kanji-centric |
| CJK thresholds per language/site | Thresholds are hardcoded, not config-driven |

---

### 3.2.1 — On Focus
**Check:** `on-focus.check.js` (interactive)

#### Flowchart
```
listen for 'framenavigated' on page
capture current URL (pathname + search)
       │
collect up to 60 focusable elements
       │
for each:
  focus element
  wait 100ms
  did URL (pathname + search) change?
    hash-only change → ignore (anchor navigation)
    Yes → ISSUE (stops testing — page may have navigated)
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- Focus-triggered URL navigation
- Hash-only change exclusion (anchor links)
- `framenavigated` event interception

#### Cases Missed
| Case | Why |
|------|-----|
| Client-side SPA routing (React Router, Next.js) | May not trigger `framenavigated` |
| AJAX content replacement without URL change | Not a navigation event |
| Modal/overlay appearing on focus | Page URL doesn't change |
| Delayed navigation (> 100ms) | Settle time too short |

---

### 3.2.2 — On Input
**Check:** `on-input.check.js` (interactive)

#### Flowchart
```
collect up to 30 inputs/selects/textareas
       │
for each:
  focus → record URL
  ├── select: change selectedIndex → dispatch 'change' event
  ├── checkbox/radio: click() → dispatch 'change' event
  └── text inputs: type safe value per type:
        email → 'a@b.co'
        url → 'https://x.com'
        number/tel/range → '1'
        default → 'a'
  wait 120ms
  URL changed? → ISSUE
  cleanup: backspace or re-toggle
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- All common input types with safe test values
- Select element change simulation
- Checkbox/radio toggle
- URL change detection

#### Cases Missed
| Case | Why |
|------|-----|
| `contenteditable` elements | Not in selector |
| Datalist auto-complete selection | Not simulated |
| Custom form controls (Shadow DOM) | Not detected |
| Auto-format inputs (phone, date) that reflow page | Not URL change |

---

### 3.2.6 — Consistent Help
**Check:** `consistent-help.check.js`

#### Flowchart
```
Scan page for help mechanisms:
  ├── Help links: a[href] text matches
  │     help / contact / support / faq / live chat / helpdesk
  │     + Japanese equivalents
  ├── Phone links: a[href^="tel:"]
  ├── Email links: a[href^="mailto:"]
  └── Chat widget: [id*="chat"], iframe[src*="chat"],
        [class*="chat"], [class*="live-chat"]

For each found: record location (header/footer/nav/body)
       │
mechanisms > 0 → PASS (with location info)
mechanisms = 0 → INCOMPLETE (manual check: single pages may not need help)
```

#### Cases Covered
- Help/support/FAQ/contact links
- Phone and email contact mechanisms
- Live chat widgets (iframe + class patterns)
- Position tracking (header/footer/nav)

#### Cases Missed
| Case | Why |
|------|-----|
| Consistency ACROSS pages | Single-page check only |
| Modal-based help (not in DOM until triggered) | Not present at load |
| Accessibility statement link (WCAG 3.2.6 requirement) | Not explicitly checked |
| Help via AI chatbot without "chat" in class/id | Pattern-dependent |

---

### 3.3.3 — Error Suggestion
**Check:** `error-suggestion.check.js`

#### Flowchart
```
formCount = 0 → PASS (not applicable)
       │
Collect error elements via:
  [role="alert"]
  [aria-live="assertive"]
  [aria-invalid="true"] ~ *[class*="error"]
  [aria-invalid="true"] ~ *[role="alert"]
  [aria-errormessage] → resolve referenced element
  [aria-invalid][aria-describedby] → resolve referenced element
  form .error-message / .field-error / .form-error / .validation-error
  form [class*="error-msg"] / [class*="error-text"]
       │
no errors found → INCOMPLETE
       │
for each error text:
  TERSE_RE match? (just "Invalid", "Error", "Required"…) → bad
  no SUGGESTION_RE AND text.length < 25? → bad
       │
any bad → FAIL
all good → PASS
```

#### Cases Covered
- ARIA error patterns
- Class-based form error selectors
- `aria-errormessage` and `aria-describedby` resolution
- Suggestion keyword pattern matching
- Terse error detection

#### Cases Missed
| Case | Why |
|------|-----|
| `<input title="…">` error messages | Not collected |
| Error in `<details>` or collapsed section | May have no text |
| Dynamic errors (shown after JS validation) | Not present at load |
| Multiple error messages per field (only one checked) | First found wins |

---

### 3.3.4 — Error Prevention
**Check:** `error-prevention.check.js`

#### Flowchart
```
Scan page for high-risk form context:
  Financial: payment / purchase / checkout / billing / credit card
  Legal: terms / consent / agreement / signature / contract / gdpr
  Destructive: delete / remove / cancel / unsubscribe
       │
  No high-risk context → PASS
       │
  High-risk context found:
  Check for safeguards:
    ├── Review/confirm text near submit button
    │     (review / confirm / summary / before you / order details)
    ├── Required confirmation checkbox
    │     input[type=checkbox][required] / [aria-required]
    ├── Review/preview button
    │     (preview / review order / check / verify / confirm)
    └── Multi-step indicator
          [aria-label*="step"] / .step-indicator / progress / ol.steps / .wizard
       │
  any safeguard → PASS
  none → FAIL
```

#### Cases Covered
- Financial, legal, destructive form detection
- Review/confirmation text detection
- Required confirmation checkbox
- Multi-step form indicator
- Preview/review button

#### Cases Missed
| Case | Why |
|------|-----|
| "Donate Now" high-risk without keywords | Not in keyword list |
| Undo functionality | Not checked (only pre-submit safeguards) |
| Safeguard is CSS-hidden (display:none) | Not filtered |
| Both financial AND destructive → mis-categorized | Priority order issue |

---

### 3.3.7 — Redundant Entry
**Check:** `redundant-entry.check.js`

#### Flowchart
```
Find all forms → extract fields with:
  autocomplete attribute → map to canonical token
  label / placeholder → semantic keyword match
       │
Group forms by process context
  (checkout / account / contact / etc.)
       │
for each pair of forms in same process:
  compute Jaccard similarity of field token sets
  similarity ≥ threshold → potential redundancy
       │
  has reuse control? (checkbox "same as", "copy from", etc.) → OK
  has confirmation field? (confirm email, re-enter password) → expected
  explicitly distinct purpose? (newsletter vs shipping) → OK
       │
  redundant required fields → ISSUE
       │
any issue → FAIL
none → PASS
```

#### Cases Covered
- Personal info autocomplete tokens (email, name, address, etc.)
- Label/placeholder semantic matching
- Confirmation field detection (re-enter, verify)
- Reuse control detection ("same as billing")
- Jaccard similarity for field set comparison
- Process grouping by form context

#### Cases Missed
| Case | Why |
|------|-----|
| Implicit semantic equivalence ("Shipping Address" vs "Address") | Different labels, same meaning |
| Prefill from saved profile | Dynamic behavior |
| Read-only re-display in review step | `readonly` input still counted |
| 2FA requiring email re-entry for security | Legitimate exception |

---

### 3.3.8 — Accessible Authentication
**Check:** `accessible-auth.check.js`

#### Flowchart
```
Find auth forms:
  form with input[type=password] OR login-related text
       │
  None → PASS (not applicable)
       │
for each auth form:
  ┌─ CAPTCHA detection ─────────────────────────────────────┐
  │ Image CAPTCHA: img[src*="captcha"] / [class*="captcha"] │
  │ reCAPTCHA: iframe[src*="recaptcha"] / .g-recaptcha /    │
  │            [data-sitekey][class*="recaptcha"]            │
  │ hCaptcha: .h-captcha / [data-hcaptcha-widget-id]        │
  └───────────────────────┬─────────────────────────────────┘
                          │
                     CAPTCHA found?
                          │
                    Yes → check for audio alternative:
                          audio button / specific aria-label
                          No alt → ISSUE
                          │
  ┌─ Cognitive test detection ──────────────────────────────┐
  │ Math equation: digit OP digit (5 + 3 = ?)               │
  │ Riddle: "what is the capital of…"                       │
  │ Pattern: "type the letters shown"                       │
  └───────────────────────┬─────────────────────────────────┘
                          │
  ┌─ Paste blocking detection ──────────────────────────────┐
  │ dispatch synthetic 'paste' event on password field       │
  │ e.defaultPrevented? → ISSUE                              │
  │ onpaste="return false" attribute? → ISSUE                │
  └───────────────────────┬─────────────────────────────────┘
                          │
any issue → FAIL
none → PASS
```

#### Cases Covered
- Image CAPTCHA and reCAPTCHA/hCaptcha (multi-signal detection)
- CAPTCHA audio alternative detection
- Math/riddle cognitive tests
- Password field paste blocking (event + attribute)

#### Cases Missed
| Case | Why |
|------|-----|
| WebAuthn / passkey flows | Not detected |
| Device-fingerprint CAPTCHA | No DOM indicators |
| Paste blocking via Shadow DOM listeners | Synthetic event can't pierce shadow |
| Paste blocking in external scripts | Runtime listener, not attribute |

---

### 4.1.1 — Parsing
**Check:** `html-parsing.check.js`

#### Flowchart
```
querySelectorAll('[id]')
  track seen IDs in null-prototype object
       │
  duplicate found → add to dupeIds list
       │
dupeIds.length > 0 → FAIL
none → PASS (reports total ID count)
```

#### Cases Covered
- Duplicate `id` attribute values (breaks ARIA references)
- All elements with `id` scanned

#### Cases Missed
| Case | Why |
|------|-----|
| Broken `aria-labelledby` / `aria-describedby` references | Not checked |
| Orphaned `<label for="…">` (no matching input) | Not checked |
| Missing required attributes (e.g. `<img>` without alt) | Delegated to axe |
| Duplicate IDs in Shadow DOM | Not traversed |

---

### 4.1.3 — Status Messages
**Check:** `status-messages.check.js`

#### Flowchart
```
Detect dynamic content contexts:
  ├── Forms present (formCount > 0)
  ├── Search results region detected
  ├── Cart/counter badges:
  │     badge with numeric text OR counter aria-label
  └── Notification areas (class*=notification/toast/snackbar/flash/alert/banner)
        NOT already inside live region ancestor
       │
  needsLiveRegions = any context found
       │
  Detect live regions:
    [aria-live] / [role="status|alert|log|timer|marquee"]
       │
  needsLiveRegions AND liveRegionCount=0 → FAIL
  needsLiveRegions AND liveRegionCount>0 → INCOMPLETE (verify wiring)
  liveRegionCount>0, no contexts → PASS
  neither → INCOMPLETE (manual check)
```

#### Cases Covered
- Form validation context detection
- Search results region
- Counter badge (numeric content only — avoids "New", "Beta" false positives)
- Toast/notification/snackbar areas (with live-region ancestor check)
- Live region type detection (assertive/polite)
- Empty live region flagging

#### Cases Missed
| Case | Why |
|------|-----|
| `aria-atomic` requirement verification | Not checked |
| Live regions populated only via JS (empty at load) | Flagged as warning but can't verify |
| AJAX result areas without live region | Detection heuristic only |

---

## Bugs Fixed in This Release

### Bug 1 — `redundant-entry.check.js`: Typo duplicate token
**File:** `src/custom-checks/redundant-entry.check.js`, line 13
**Issue:** `'honific-suffix'` (typo) duplicated alongside the correct `'honorific-suffix'` on line 14. The typo entry is never matched by any browser autocomplete value, wasting a slot and causing misleading token counts.
**Fix:** Removed the typo entry.

---

### Bug 2 — `status-messages.check.js`: `\bnew\b` false positive in badge detection
**File:** `src/custom-checks/status-messages.check.js`, line 42
**Issue:** `/\bnew\b/i` in the counter-badge aria-label regex matches "New York", "New Products", or "What's New" labels, causing false detection of dynamic counter badges on non-counter elements.
**Fix:** Changed to `/\b(count|counter|notification|unread|新着|件|通知|未読)\b/i` — removed `new` and added `新着` (Japanese "new arrivals") instead of the ambiguous English word.

---

### Bug 3 — `link-purpose.check.js`: `textContent` includes hidden text
**File:** `src/custom-checks/link-purpose.check.js`, line 47
**Issue:** `link.textContent` includes text from `display:none` / `visibility:hidden` child elements (e.g. screen-reader-only helper spans that say "open in new tab"). This can make a link appear to have a descriptive name ("click here open in new tab") when visually it just says "click here" — masking a real violation.
**Fix:** Filter to only include text from visible child text nodes using `getComputedStyle` visibility check.

---

### Bug 4 — `audio-transcript.check.js`: `<details>` transcript not detected
**File:** `src/custom-checks/audio-transcript.check.js`
**Issue:** A `<details><summary>Transcript</summary><p>…</p></details>` element adjacent to an audio element is a valid and common transcript pattern, but is not detected by the existing link-only or figcaption checks.
**Fix:** Added detection of `<details>` elements in the container whose summary or text content contains transcript-related keywords.

---

### Bug 5 — `error-suggestion.check.js`: Length-only terse check catches valid short messages
**File:** `src/custom-checks/error-suggestion.check.js`, line 108
**Issue:** `(!SUGGESTION_RE.test(text) && text.length < 25)` flags any short error message without a SUGGESTION_RE match as terse. Messages like "Enter 8+ characters" (21 chars) or "Use A–Z, 0–9 only" are good guidance but fail this filter because they don't contain SUGGESTION_RE keywords.
**Fix:** Added number-with-unit and format-pattern signals to the exception: messages containing a digit, `+`, format characters (`@`, `A–Z`, `0–9`), or specific format keywords (`only`, `format`, `characters`) are not flagged as terse even if short.

---

### Bug 6 — `use-of-color.check.js`: Transparent color string variants
**File:** `src/custom-checks/use-of-color.check.js`, line 95
**Issue:** When `ancestor` is null, the `hasBgChange` fallback only checks for `'rgba(0, 0, 0, 0)'` and `'transparent'`. Some browsers normalize alpha-zero colors differently (e.g. `rgba(0,0,0,0)` without spaces). The existing `colorsDiffer` function already handles this correctly via digit extraction, but the fallback path bypasses it.
**Fix:** Replaced the string comparison with a proper `colorsDiffer` call against the transparent sentinel.

---

## Japanese / Config Gap Summary

| Area | Already supported | Still missing for production |
|------|-------------------|------------------------------|
| Japanese output copy | `i18n/locales/ja.yml` | — |
| `lang="ja"` request handling | request param and result mapping | passing language assets into custom checks |
| Japanese transcript detection | hardcoded in `audio-transcript.check.js` | move keywords to config |
| Japanese pointer/action heuristics | hardcoded in `pointer-cancellation.check.js` | move verbs to config |
| Japanese commerce/process heuristics | hardcoded in `error-prevention.check.js` and `redundant-entry.check.js` | move patterns to config |
| Japanese support/search heuristics | partially hardcoded in `consistent-help.check.js`, `multiple-ways.check.js`, `link-purpose.check.js` | move terms to config |
| Japanese/CJK thresholds | hardcoded in `pronunciation.check.js` | move thresholds and lang prefixes to config |

---

## Coverage Summary

| WCAG SC | Criterion | Check File | Axe also? | Confidence |
|---------|-----------|------------|-----------|------------|
| 1.2.1 | Audio-only transcript | audio-transcript | — | Medium |
| 1.3.2 | Meaningful sequence | meaningful-sequence | — | Medium |
| 1.3.4 | Orientation | orientation | — | High |
| 1.4.1 | Use of color | use-of-color | — | Medium |
| 1.4.5 | Images of text | images-of-text | — | Low (heuristic) |
| 2.1.2 | No keyboard trap | keyboard-trap | axe partial | High |
| 2.1.4 | Character key shortcuts | character-key-shortcuts | — | Medium |
| 2.4.5 | Multiple ways | multiple-ways | — | Medium |
| 2.4.7 | Focus visible | focus-visible | axe | High |
| 2.4.8 | Location | location | — | Medium |
| 2.4.9 | Link purpose (link only) | link-purpose | axe partial | High |
| 2.4.13 | Focus appearance (2.2) | focus-appearance | — | Medium |
| 2.5.2 | Pointer cancellation | pointer-cancellation | — | Low (heuristic) |
| 2.5.7 | Dragging movements (2.2) | dragging-movements | — | Medium |
| 3.1.6 | Pronunciation | pronunciation | — | Medium |
| 3.2.1 | On focus | on-focus | axe partial | High |
| 3.2.2 | On input | on-input | — | High |
| 3.2.6 | Consistent help (2.2) | consistent-help | — | Low |
| 3.3.3 | Error suggestion | error-suggestion | — | Medium |
| 3.3.4 | Error prevention | error-prevention | — | Medium |
| 3.3.7 | Redundant entry (2.2) | redundant-entry | — | Medium |
| 3.3.8 | Accessible auth (2.2) | accessible-auth | — | Medium |
| 4.1.1 | Parsing | html-parsing | axe | High |
| 4.1.3 | Status messages | status-messages | — | Medium |

**Axe-core covers additionally (not in custom checks):**
1.1.1 (image alt), 1.3.1 (info & relationships), 1.3.3 (sensory characteristics), 1.3.5 (identify input purpose), 1.4.3 (contrast minimum), 1.4.4 (resize text), 1.4.10 (reflow), 1.4.11 (non-text contrast), 1.4.12 (text spacing), 2.1.1 (keyboard), 2.4.1 (bypass blocks), 2.4.2 (page titled), 2.4.3 (focus order), 2.4.4 (link purpose in context), 3.1.1 (language of page), 3.1.2 (language of parts), 3.3.1 (error identification), 3.3.2 (labels or instructions), 4.1.2 (name, role, value)
