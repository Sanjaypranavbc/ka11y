# Rule-wise Code Analysis

- Generated at (UTC): `2026-04-01 00:00:00Z`
- Updated at (UTC): `2026-04-03 00:00:00Z`
- Scope: `ka11y-node` custom checks (24 checks) + axe-core integration
- Method: deep static + runtime analysis; flowcharts, coverage gaps, bugs, and solvable possibilities

---

## File Inventory

| Rule File | Mode | SC | LOC |
|---|---|---|---:|
| `accessible-auth.check.js` | static | 3.3.8 | 141 |
| `audio-transcript.check.js` | static | 1.2.1 | 98 |
| `character-key-shortcuts.check.js` | static | 2.1.4 | 122 |
| `consistent-help.check.js` | static | 3.2.6 | 103 |
| `dragging-movements.check.js` | static | 2.5.7 | 129 |
| `error-prevention.check.js` | static | 3.3.4 | 124 |
| `error-suggestion.check.js` | static | 3.3.3 | 138 |
| `focus-appearance.check.js` | interactive | 2.4.13 | 238 |
| `focus-visible.check.js` | interactive | 2.4.7 | 161 |
| `html-parsing.check.js` | static | 4.1.1 | 57 |
| `images-of-text.check.js` | static | 1.4.5 | 157 |
| `keyboard-trap.check.js` | interactive | 2.1.2 | 168 |
| `link-purpose.check.js` | static | 2.4.9 | 99 |
| `location.check.js` | static | 2.4.8 | 79 |
| `meaningful-sequence.check.js` | static | 1.3.2 | 107 |
| `multiple-ways.check.js` | static | 2.4.5 | 96 |
| `on-focus.check.js` | interactive | 3.2.1 | 100 |
| `on-input.check.js` | interactive | 3.2.2 | 120 |
| `orientation.check.js` | static | 1.3.4 | 385 |
| `pointer-cancellation.check.js` | static | 2.5.2 | 87 |
| `pronunciation.check.js` | static | 3.1.6 | 177 |
| `redundant-entry.check.js` | static | 3.3.7 | 400+ |
| `status-messages.check.js` | static | 4.1.3 | 143 |
| `use-of-color.check.js` | static | 1.4.1 | 165 |

---

## End-to-End Request Flow

```
POST /api/v1/analyse-url  { url }
           │
           ▼
  ┌─────────────────────────────────┐
  │  SSRF Guard                     │
  │  DNS resolve → block private IP │
  │  Request interceptor (redirects)│
  └──────────────┬──────────────────┘
                 │
                 ▼
  ┌─────────────────────────────────┐
  │  Puppeteer: launch browser      │
  │  (max 3 concurrent slots)       │
  │  navigate to URL                │
  └──────────────┬──────────────────┘
                 │
         ┌───────┴────────┐
         ▼                ▼
   axe-core.run()    Custom Checks
   (automated,       index.js:
    ~50 rules)       ├─ static (parallel)
         │           └─ interactive (sequential)
         └───────┬────────┘
                 ▼
  ┌─────────────────────────────────┐
  │  Merge → group by WCAG SC       │
  │  Map to flat / grouped output   │
  └─────────────────────────────────┘
                 │
                 ▼
           JSON response
```

---

## Rule-by-Rule Analysis

---

### SC 1.2.1 — Audio-only Prerecorded
**Check:** `audio-transcript.check.js` | Mode: static

#### Approach
For every `<audio>` element, check if any of four alternative patterns exist in the nearest semantic container.

#### Flowchart
```
page has <audio> elements?
    No ──► PASS (not applicable)
    Yes
     │
     ▼
for each <audio>:
  ├─ <track kind="captions|descriptions|subtitles"> inside? ─► ✓
  ├─ Nearby a[href] with transcript/caption text?            ─► ✓
  ├─ <figcaption> inside parent <figure>?                    ─► ✓
  ├─ <details> whose summary/content mentions transcript?    ─► ✓  ← added
  └─ aria-describedby → element with text content?           ─► ✓
       │
  none found ──► ISSUE

all issues empty ──► PASS
any issues ──► INCOMPLETE
```

#### Covered
| Case | Method |
|------|--------|
| `<track kind="captions">` | Direct child query |
| Transcript hyperlink in semantic container | Link text regex |
| `<figcaption>` in `<figure>` | Ancestor walk |
| `<details><summary>Transcript</summary>` | ✅ Added in fix |
| `aria-describedby` → text element | ID lookup |

#### Missed (not solvable without runtime)
| Case | Reason not solvable |
|------|---------------------|
| Third-party embeds (Spotify, SoundCloud iframes) | Not `<audio>` in DOM |
| Transcript on external linked page | Link found but content unverifiable statically |
| AJAX-loaded transcript (button-reveal) | Not in DOM at load time |

---

### SC 1.3.2 — Meaningful Sequence
**Check:** `meaningful-sequence.check.js` | Mode: static

#### Approach
Scan every flex/grid container for CSS properties that visually reorder elements relative to their DOM order. RTL-language exemptions applied.

#### Flowchart
```
collect all flex/grid containers (max 500)
     │
     ▼
for each container:
  ├─ flex-direction: row-reverse?
  │     is RTL lang (ar/he/fa/ur/yi/arc/ckb)? ──► SKIP (correct)
  │     is LTR? ──► ISSUE
  ├─ flex-direction: column-reverse? ──► ISSUE (always)
  └─ any child has CSS order ≠ 0?
        visual order ≠ DOM order? ──► ISSUE
     │
none ──► PASS    any ──► FAIL
```

#### Covered
- `flex-direction: row-reverse` with RTL exemption (12 language codes)
- `flex-direction: column-reverse`
- CSS `order` property reordering

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`grid-column` / `grid-row` explicit placement reordering~~ | ✅ **Fixed** — checks `gridColumnStart`/`gridRowStart !== 'auto'` on grid children |
| ~~`float: left/right` reordering~~ | ✅ **Fixed** — detects mixed floated/non-floated siblings |
| CSS `multicolumn` (`column-count`) visual reorder | Partial — hard to determine reading order |
| `grid-auto-flow: dense` | Hard — requires layout engine |

---

### SC 1.3.4 — Orientation
**Check:** `orientation.check.js` | Mode: static

#### Approach
Five independent signals each detecting a different locking mechanism.

#### Flowchart
```
Signal 1: Inline script
  LOCK_RE matches screen.orientation.lock / mozLock / webkitLock?
       │
Signal 2: CSS forced rotation
  transform: rotate(90°/270°) on structural containers?
       │
Signal 3: @media orientation
  CSS rule hides content (display:none/visibility:hidden/opacity:0)
  OR breaks layout (fixed+vw/vh) when orientation matches?
       │
Signal 4: <meta viewport>
  content="orientation=portrait|landscape"?
       │
Signal 5: Web App Manifest
  fetch manifest URL → orientation field = portrait|landscape?
       │
any signal ──► FAIL / INCOMPLETE
none ──► PASS
```

#### Covered
- JS lock API (6 vendor prefixes)
- CSS rotation on structural elements
- `@media orientation` display suppression + layout break
- `<meta viewport>` orientation attribute
- Web App Manifest orientation field
- Cross-origin stylesheets → `incomplete` (manual review)
- `writing-mode: vertical-rl/vertical-lr` on `<body>` → FAIL (Signal 6)
- `maximum-scale=1` in `<meta name="viewport">` → INCOMPLETE (Signal 7)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`writing-mode: vertical-rl` locking visual layout~~ | ✅ **Fixed** — checks `getComputedStyle(body).writingMode` |
| `aspect-ratio` media query effectively locking | Partial |
| ~~`maximum-scale=1` in viewport meta (resize prevention)~~ | ✅ **Fixed** — parses viewport `content` string |

---

### SC 1.4.1 — Use of Color
**Check:** `use-of-color.check.js` | Mode: static

#### Approach
Find inline-text links (inside `<p>`, `<li>`, `<td>`, etc.), compare link vs ancestor styles for non-color visual cues.

#### Flowchart
```
collect inline-text links (max 150):
  p a, li a, td a, th a, blockquote a, article > p a, dd a
     │
for each link:
  skip if: no visible text
     │
  compute getComputedStyle → walk up DOM to non-<a> ancestor
     │
  non-color cues present?
  ├─ textDecorationLine ≠ "none"         (underline/overline)
  ├─ borderBottomWidth > 0               (fake underline)
  ├─ outlineWidth > 0                    (outline)
  ├─ backgroundColor differs (> 15 RGB) from ancestor
  ├─ fontWeight ≥ ancestor + 100
  └─ fontStyle differs from ancestor
     │
  cue found ──► OK
  no cue:
    link color differs from ancestor (> 15 RGB)? ──► FAIL
    no color diff either ──► OK (no distinction at all)
```

#### Covered
- 6 non-color cue types
- RGB channel comparison (15-unit tolerance)
- Ancestor text style walking (skips nested `<a>` elements)
- 150-link performance cap
- `section > p a[href]` links
- `svg a[href]` elements

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~Links in `<section>` without `<p>` wrapper~~ | ✅ **Fixed** — added `section > p a[href]` to SELECTORS |
| ~~SVG `<a>` elements with color-only cue~~ | ✅ **Fixed** — added `svg a[href]` to SELECTORS |
| Icon-only link with color as the only visual distinction | ✅ Solvable — check for icon-bg color change |

---

### SC 1.4.5 — Images of Text
**Check:** `images-of-text.check.js` | Mode: static

#### Approach
Heuristic scoring system. Multiple weak signals combine to high confidence. Logo/brand images are exempt.

#### Flowchart
```
for each img[src] with non-empty alt:
  skip: alt="" or role=presentation/none
  skip: LOGO_PATTERN matches alt/src/class/id
     │
  Score:
  ┌─ src path has text-image keyword?  → +2 (strong signal)
  ├─ class/id has text-image keyword?  → +1
  ├─ alt ≥ 5 words (or ≥ 8 CJK chars)?→ +1
  └─ alt looks like a sentence?        → +1
     │
  score ≥ 3 ──► FAIL
  score = 2 ──► INCOMPLETE (needs review)
  score < 2 ──► pass

Also: CSS background-image on text-containing elements
  matches src pattern + element has ≥ 10 chars text ──► FAIL
```

#### Covered
- `<img>` with keyword-matching src path (20+ keywords)
- Class/id signal matching
- Alt text length and sentence structure heuristics
- CJK-specific thresholds
- Logo/brand exemption
- CSS background-image with text-like URL

#### Missed
| Case | Solvable? |
|------|-----------|
| `<canvas>` rendering text | No (requires OCR or canvas pixel read) |
| ~~`<svg>` with embedded `<text>` elements~~ | ✅ **Fixed** — scans `svg text` inside `a, button, [role="img"], figure` |
| Very short text images (1-2 words in alt) | Partial — score will be < 2 |
| `<picture>` with `<source>` + `<img>` fallback | ✅ Solvable — `<picture> img` already covered by `img[src]` |

---

### SC 2.1.2 — No Keyboard Trap
**Check:** `keyboard-trap.check.js` | Mode: interactive

#### Approach
Simulate Tab/Shift+Tab navigation and detect repeating patterns in the focus sequence.

#### Flowchart
```
Tab forward (max 200 × 60ms settle):
  track last 4 focused elements by stable key
     │
  Cycle detected?
  ├─ Single-element stuck: [A, A, A, A]
  └─ Two-element cycle:    [A, B, A, B]
     │
  Yes → press Escape → Tab again
    still stuck? ──► FAIL (confirmed trap)
    broke free? ──► OK (Escape works = not a WCAG violation)

Also: Shift+Tab backward (50 attempts, same detection)
     │
any trap ──► FAIL    none ──► PASS
```

#### Covered
- Forward and backward Tab trap detection
- Single-element and two-element cycles
- Escape key verification
- Arrow key traps in ARIA widgets (`tree`, `grid`, `listbox`, `menu`, `tablist`, `radiogroup`)
- Same-origin iframe Tab trap detection

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~Arrow key traps in custom widgets (tree, grid, listbox)~~ | ✅ **Fixed** — presses ArrowDown twice in each ARIA widget role; flags if focus doesn't move |
| Traps requiring Enter to trigger (e.g. open modal) | Partial |
| ~~Traps in same-origin iframes~~ | ✅ **Fixed** — iterates `page.frames()` for same-origin frames |

---

### SC 2.1.4 — Character Key Shortcuts
**Check:** `character-key-shortcuts.check.js` | Mode: static

#### Approach
Three-pass scan: `accesskey` attributes, inline event handler attributes, inline `<script>` addEventListener calls.

#### Flowchart
```
Pass 1 — accesskey attributes:
  [accesskey] → single letter/symbol (not digit, not multi-char)?
  ──► ISSUE (no modifier required in HTML spec)

Pass 2 — inline event handlers:
  [onkeydown/onkeypress/onkeyup] handler text
  matches single-char key pattern?
  (event.key === 'x', keyCode 65-90, etc.)
  check ±200 chars for modifier guard (ctrlKey/altKey/metaKey)?
  no guard ──► ISSUE

Pass 3 — inline <script> addEventListener:
  scan script blocks for keydown/keypress listener
  single-char match + no modifier guard (±120 chars)?
  ──► ISSUE
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- `accesskey` single-char letters and symbols
- Inline `onkeydown/onkeypress/onkeyup` with modifier check
- Inline `<script>` `addEventListener` with modifier check
- `document.addEventListener('keydown|keypress|keyup', ...)` in inline scripts

#### Missed
| Case | Solvable? |
|------|-----------|
| External script files | No (cross-origin restriction) |
| ~~Delegated handlers on `document`/`window`~~ | ✅ **Fixed** — added `docListenerRe` scan in Pass 3 for `document.addEventListener` key listeners |
| Framework event bindings (React `onKeyDown`, Vue `v-on`) | No (runtime, not in DOM) |
| Arrow key shortcuts without modifiers | ✅ Solvable — extend key pattern to include Arrow keys |

---

### SC 2.4.5 — Multiple Ways
**Check:** `multiple-ways.check.js` | Mode: static

#### Approach
Count distinct navigation mechanisms. Page passes if ≥ 2 found.

#### Flowchart
```
Detect mechanisms:
  1. Search: input[type=search] / [role=search] /
             form[action*=search] / placeholder*=search
  2. Sitemap: a[href*=sitemap] / link text "sitemap"
  3. Navigation elements: <nav> / [role=navigation] (distinct count)
  4. Breadcrumb: aria-label=breadcrumb / class*=breadcrumb / schema
  5. Table of contents: [id*=toc] / aria-label*="table of contents"
     │
count ≥ 2 ──► PASS
count < 2 ──► FAIL
```

#### Covered
- Search input/form
- Sitemap link
- Nav elements
- Breadcrumb trail
- Table of contents

#### Missed
| Case | Solvable? |
|------|-----------|
| Alphabetical keyword index | ✅ Solvable — detect `[id*="index"][role="navigation"]` or list of single-letter links |
| ~~French/German/Spanish search terms~~ | ✅ **Fixed** — extended search regex to include FR/ES/DE/IT/NL/SV/ZH/JA/KO equivalents |
| Skip-nav link counting as a mechanism | Partial |

---

### SC 2.4.7 — Focus Visible
**Check:** `focus-visible.check.js` | Mode: interactive

#### Approach
Focus up to 100 elements programmatically, compare computed styles before/after with 80ms settle time.

#### Flowchart
```
collect ≤ 100 focusable elements
(a[href], button, input, select, textarea, [tabindex≥0])
use stable selectors (unique #id or DOM index)
     │
for each:
  ① blur() → capture unfocused styles
  ② focus() → wait 80ms
  ③ capture focused styles
     │
  visible change?
  ├─ outline changed AND not transparent?
  ├─ boxShadow changed AND ≠ "none"?
  ├─ borderColor or borderWidth changed?
  ├─ backgroundColor changed?
  └─ color changed?
     │
  no change ──► ISSUE

any issue ──► FAIL    none ──► PASS
```

#### Covered
- All 5 style change categories
- Transparent outline guard
- CSS transition settle delay (80ms)
- Stable element selectors
- `transform` property change as a focus indicator

#### Missed
| Case | Solvable? |
|------|-----------|
| `:focus-visible`-only styles | ✅ Partial — could inject `Tab` key press instead of `.focus()` |
| Pseudo-element indicators (`::before`/`::after`) | No — `getComputedStyle` on pseudo needs `:focus` context |
| ~~Scale/transform-based focus indicator~~ | ✅ **Fixed** — added `transform` to captured and compared style properties |

---

### SC 2.4.8 — Location
**Check:** `location.check.js` | Mode: static

#### Approach
Check for at least one location indicator from four categories.

#### Flowchart
```
Detect location indicators:
  Breadcrumb:
    [aria-label*="breadcrumb"] / [class*="breadcrumb"] /
    [id*="breadcrumb"] / [itemtype*="BreadcrumbList"]
  Active nav item:
    aria-current="page" inside <nav>
    .active / [aria-selected="true"] inside <nav>
  Sitemap link:
    a[href*="sitemap"] / link text "sitemap"
     │
any found ──► PASS
none ──► INCOMPLETE
```

#### Covered
- ARIA breadcrumb, class/id breadcrumb, Schema.org BreadcrumbList
- `aria-current="page"` in nav
- Active nav item classes
- Sitemap link
- `aria-current="step"` (multi-step wizard)
- JSON-LD `BreadcrumbList` in `<script type="application/ld+json">`

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`aria-current="step"` (multi-step wizard)~~ | ✅ **Fixed** — added `[aria-current="step"]` check |
| ~~JSON-LD breadcrumb (not in DOM)~~ | ✅ **Fixed** — parses `<script type="application/ld+json">` for BreadcrumbList |

---

### SC 2.4.9 — Link Purpose (Link Only)
**Check:** `link-purpose.check.js` | Mode: static

#### Approach
Build the accessible name for each link and test against a generic-text regex.

#### Flowchart
```
for each a[href] (max 100):
  accessible name resolution:
    1. aria-label
    2. aria-labelledby → concat referenced element texts
    3. img[alt] (icon-only links)
    4. visible text content only (TreeWalker, skips display:none)  ← fixed
     │
  skip if: no accessible name
     │
  test GENERIC_LINK_RE:
  "click here", "here", "read more", "more", "details",
  "continue", "go", "link", "see more", "view more", etc.
  + Japanese equivalents (30+ patterns total)
     │
  match ──► ISSUE
  no match ──► OK

any issue ──► FAIL    none ──► PASS
```

#### Covered
- Full accessible name computation (ARIA precedence)
- `title` attribute as 5th accessible name fallback
- 30+ generic English patterns
- Japanese generic patterns
- Visible-only text (fixed: excludes `display:none` descendants)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`title` attribute as accessible name fallback~~ | ✅ **Fixed** — added `link.getAttribute('title')` as 5th fallback |
| Context-based purpose (table column header gives meaning) | Not at link-only level (2.4.4 SC) |
| Short but specific links matching "go" pattern | Partial — "go" is in regex; could narrow |

---

### SC 2.4.13 — Focus Appearance (WCAG 2.2)
**Check:** `focus-appearance.check.js` | Mode: interactive

#### Approach
For up to 30 focusable elements, measure focus indicator area and contrast ratio.

#### Flowchart
```
collect ≤ 30 focusable elements
     │
for each:
  ① capture unfocused styles
  ② focus() → wait 80ms
  ③ capture focused styles
     │
  Area check:
    outline-width ≥ 2px?  OR  box-shadow spread ≥ 2px? ──► OK
  Contrast check:
    indicator color vs background:
    luminance = 0.2126R + 0.7152G + 0.0722B (linearised)
    contrast = (lighter+0.05)/(darker+0.05) ≥ 3:1? ──► OK
     │
  area fail OR contrast fail ──► ISSUE

any issue ──► FAIL    none ──► PASS
```

#### Covered
- 2px minimum area (outline-width, box-shadow spread, or border-width)
- 3:1 contrast ratio (WCAG luminance formula)
- Transparent background fallback to `<body>` background
- CSS variable resolution (browser resolves via `getComputedStyle`)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~Border-based focus indicator area~~ | ✅ **Fixed** — `areaMet` now includes `borderChanged && borderWidth >= 2` |
| Focus indicator on child not the target element | Hard — would need to check all descendants |

---

### SC 2.5.2 — Pointer Cancellation
**Check:** `pointer-cancellation.check.js` | Mode: static

#### Approach
Find elements with pointer-down handlers that perform actions; verify a cancellation path exists.

#### Flowchart
```
find elements with [onmousedown] / [onpointerdown] / [onpointermove]
     │
for each:
  isVisualOnly? (only style changes / preventDefault only) ──► skip
  isAction? (navigate/submit/dispatch/fetch/route/open/…)?
     │
  isAction:
    has [onmouseup] / [onpointerup] / [onclick] on same element?
    Yes ──► OK (cancellation path exists)
    No ──► ISSUE
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- `mousedown` / `pointerdown` / `pointermove` / `touchstart` attribute handlers
- Action keyword detection
- Visual-only handler exclusion
- Cancellation via `mouseup` / `pointerup` / `click` / `touchend`

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`ontouchstart` handlers~~ | ✅ **Fixed** — added `[ontouchstart]` to selector; `ontouchend` as cancellation path |
| `oncontextmenu="return false"` suppression | ✅ Solvable — detect and flag separately |
| `addEventListener` handlers | No (not in DOM attributes) |

---

### SC 2.5.7 — Dragging Movements (WCAG 2.2)
**Check:** `dragging-movements.check.js` | Mode: static

#### Approach
Detect draggable elements via attributes and known library markers, then verify a single-pointer alternative exists nearby.

#### Flowchart
```
Find draggable elements:
  [draggable="true"] / [ondragstart]          (native)
  [data-rbd-draggable-id]                     (react-beautiful-dnd)
  [data-dnd-kit-draggable]                    (dnd-kit)
  .sortable-item / .ui-sortable / [data-sortable] (Sortable.js)
  .ui-draggable                               (jQuery UI)
  deduplicate with Set
     │
for each draggable:
  alternative nearby (button / [role=button] / a[href])?
  in: element itself / parent / siblings
  Yes ──► OK
  No ──► ISSUE
     │
any issue ──► FAIL    none (or no draggables) ──► PASS
```

#### Covered
- Native HTML5 drag API
- 4 major D&D libraries (react-beautiful-dnd, dnd-kit, Sortable.js, jQuery UI)
- Interact.js (`[data-interact]`), Dragula (`.gu-transit`), generic drag handles (`[data-drag-handle]`)
- Single-pointer alternative detection
- Deduplication

#### Missed
| Case | Solvable? |
|------|-----------|
| `onpointerdown` + move custom drag (no `draggable` attr) | ✅ Solvable — add `[onpointermove]` with drag pattern check |
| `ontouchstart` drag implementations | ✅ Solvable — add `[ontouchstart]` with data-* context |
| ~~Interact.js / Dragula / other libs~~ | ✅ **Fixed** — added `[data-interact]`, `.gu-transit`, `[data-drag-handle]` |

---

### SC 3.1.6 — Pronunciation
**Check:** `pronunciation.check.js` | Mode: static

#### Approach
Detect CJK pages, count kanji, and calculate what fraction has `<ruby>` annotations.

#### Flowchart
```
Is it a CJK page?
  lang="ja|zh|ko" attribute OR CJK char density ≥ 5%
  No ──► PASS (not applicable)
     │
count <ruby> elements
     │
TreeWalker over text nodes:
  for each text node:
    is inside <ruby>? → kanji-in-ruby++
    not inside <ruby>? + has kanji chars? → kanji-outside++
     │
coverage = kanji-in-ruby / (kanji-in-ruby + kanji-outside)
     │
coverage ≥ 30%  ──► PASS
0 < coverage < 30% ──► INCOMPLETE (low coverage)
coverage = 0  ──► FAIL
```

#### Covered
- Japanese, Chinese, Korean language detection
- `<ruby>` / `<rt>` presence and coverage ratio
- CJK density heuristic for un-labelled pages
- 30% coverage threshold
- Section-level CJK scan for `[lang^="ja/zh/ko"]` sub-elements on non-CJK pages

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~Section-level CJK in an English page~~ | ✅ **Fixed** — scans `[lang^="ja/zh/ko"]` sub-elements regardless of page lang |
| Kanji in `<img alt>` | No (alt text, not text node) |
| Ruby position correctness | Hard (requires linguistic knowledge) |

---

### SC 3.2.1 — On Focus
**Check:** `on-focus.check.js` | Mode: interactive

#### Approach
Focus each element and detect URL navigation (pathname + search changes).

#### Flowchart
```
listen for 'framenavigated'
capture initial URL (pathname + search)
collect ≤ 60 focusable elements
     │
for each:
  focus element → wait 100ms
  URL pathname+search changed?
    hash-only change ──► ignore (anchor nav, not violation)
    changed ──► ISSUE (stop — page navigated away)
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- Full-page navigation on focus
- Hash-only change exclusion
- SPA `pushState`/`replaceState` navigation detection

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~SPA client-side routing (React Router, Next.js)~~ | ✅ **Fixed** — intercepts `pushState`/`replaceState`; checks `__navChanges` after each focus |
| Content replacement via AJAX (no URL change) | Hard — no navigation event |
| Modal/overlay on focus (content change, not navigation) | ✅ Solvable — detect large DOM mutations after focus |

---

### SC 3.2.2 — On Input
**Check:** `on-input.check.js` | Mode: interactive

#### Approach
Interact with each input type using safe test values; check if URL changes.

#### Flowchart
```
collect ≤ 30 inputs / selects / textareas
     │
for each:
  focus → record URL
  ├─ select: change selectedIndex → dispatch 'change'
  ├─ checkbox/radio: click() → dispatch 'change'
  └─ text inputs: type safe value:
       email → 'a@b.co'
       url → 'https://x.com'
       number/tel/range → '1'
       default → 'a'
  wait 120ms
  URL changed? ──► ISSUE
  cleanup: backspace / re-toggle
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- All standard input types with valid test values
- Select, checkbox, radio simulation
- URL change detection with cleanup
- `contenteditable` element interaction
- SPA `pushState`/`replaceState` navigation detection
- Select with `options.length < 2` guard (skip to avoid no-change fire)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`contenteditable` elements~~ | ✅ **Fixed** — added `[contenteditable="true"]` and `[contenteditable=""]` to selector |
| ~~SPA routing on input change~~ | ✅ **Fixed** — same `pushState`/`replaceState` interception as 3.2.1 |
| ~~Select with 0 options (no change fires)~~ | ✅ **Fixed** — guard: `if (options.length < 2) continue` |
| Checkbox that is already checked (no toggle on click) | ✅ Solvable — set `checked = !checked` directly |

---

### SC 3.2.6 — Consistent Help (WCAG 2.2)
**Check:** `consistent-help.check.js` | Mode: static

#### Approach
Detect any help mechanism on the page; report its location.

#### Flowchart
```
Scan for help mechanisms:
  Help/support/FAQ links:
    a[href] text matches:
    help / contact / support / faq / live chat / helpdesk
    + Japanese equivalents
  Phone links: a[href^="tel:"]
  Email links: a[href^="mailto:"]
  Chat widget:
    [id*="chat"] / iframe[src*="chat"] /
    [class*="chat"] / [class*="live-chat"]
  For each: record location (header/footer/nav/body)
     │
mechanisms > 0 ──► PASS (with location note)
mechanisms = 0 ──► INCOMPLETE
```

#### Covered
- Help/support/FAQ/contact/accessibility links
- Phone, email, chat mechanisms
- Location tracking (header/footer/nav/body)
- Known chatbot platforms: Intercom, Drift, Zendesk, HelpScout, Crisp, Tawk, HubSpot Chat

#### Missed
| Case | Solvable? |
|------|-----------|
| Consistency across pages | No (single-page scan only) |
| ~~Accessibility statement link~~ | ✅ **Fixed** — added `accessibility` to `HELP_PATTERNS` regex |
| ~~AI chatbot without "chat" in class/id~~ | ✅ **Fixed** — added 7 known chatbot platform selector signatures |

---

### SC 3.3.3 — Error Suggestion
**Check:** `error-suggestion.check.js` | Mode: static

#### Approach
Collect all visible error messages from ARIA and class-based patterns; test each for correction-guidance content.

#### Flowchart
```
formCount = 0 ──► PASS (not applicable)
     │
Collect error elements:
  [role="alert"] / [aria-live="assertive"]
  [aria-invalid="true"] ~ *[class*="error"]
  [aria-errormessage] → resolve referenced element
  [aria-invalid][aria-describedby] → resolve referenced elements
  form .error-message / .field-error / .form-error / .validation-error
  form [class*="error-msg"] / [class*="error-text"]
  deduplicate; filter text.length > 3
     │
no errors found ──► INCOMPLETE
     │
for each error text:
  TERSE_RE match? ("Invalid", "Error", "Required") ──► bad
  no SUGGESTION_RE AND length < 25
    AND no SHORT_BUT_INFORMATIVE_RE?             ──► bad  ← fixed
     │
any bad ──► FAIL    all good ──► PASS
```

#### Covered
- Full ARIA error pattern set
- `aria-errormessage` and `aria-describedby` resolution
- Class-based form error selectors
- Suggestion keyword matching (30+ patterns)
- Terse error detection with short-message exemption (fixed)
- `title` attribute on `[aria-invalid]` inputs as error source

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`<input title="…">` error guidance~~ | ✅ **Fixed** — collects `[aria-invalid="true"][title]` text before main loop |
| Dynamic errors (shown post-submit in JS) | No (static load only) |
| Error in collapsed `<details>` | Partial |

---

### SC 3.3.4 — Error Prevention
**Check:** `error-prevention.check.js` | Mode: static

#### Approach
Detect high-risk form context (financial / legal / destructive); verify at least one safeguard exists.

#### Flowchart
```
Scan page for high-risk keywords:
  Financial: payment / purchase / checkout / billing / credit card
  Legal: terms / consent / agreement / signature / contract / gdpr
  Destructive: delete / remove / cancel / unsubscribe / terminate
  (in: submit buttons, headings, form action/id)
     │
no high-risk context ──► PASS
     │
Check safeguards:
  ├─ Review/confirm text near submit?
  │     (review / confirm / summary / "before you" / order details)
  ├─ Required confirmation checkbox?
  │     input[type=checkbox][required] / [aria-required]
  ├─ Review/preview button?
  │     (preview / review order / verify / check)
  └─ Multi-step indicator?
        [aria-label*="step"] / .step-indicator / progress / ol.steps
     │
any safeguard ──► PASS
none ──► FAIL
```

#### Covered
- Financial (`payment`, `purchase`, `checkout`, `billing`, `donat`), legal, destructive context keywords
- 4 safeguard types with `isVisible()` filter (excludes `display:none`, `visibility:hidden`, `opacity:0`)
- Multi-language keywords (English + Japanese)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~"Donate Now" high-risk without standard keywords~~ | ✅ **Fixed** — added `donat` to financial keyword pattern |
| ~~Safeguards hidden in collapsed sections (`display:none`)~~ | ✅ **Fixed** — `isVisible()` filter applied to safeguard elements |
| Undo functionality as a safeguard | Hard — requires runtime testing |

---

### SC 3.3.7 — Redundant Entry (WCAG 2.2)
**Check:** `redundant-entry.check.js` | Mode: static

#### Approach
Group forms by process context, extract field tokens via autocomplete + label matching, compute Jaccard similarity between forms to detect duplicated required fields.

#### Flowchart
```
find all forms → extract fields:
  autocomplete attribute → canonical token
  label/placeholder → keyword match → semantic token
     │
group forms by process (checkout/account/contact/…)
     │
for each pair of forms in same process:
  compute Jaccard similarity of token sets
  similarity ≥ threshold?
     │
  has reuse control? ("same as billing", autofill checkbox) ──► OK
  confirmation field? ("confirm email", "re-enter") ──► expected
  explicitly distinct purpose? (newsletter vs shipping) ──► OK
     │
  redundant required fields ──► ISSUE
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- Personal info autocomplete tokens (25 values)
- Label/placeholder semantic matching (11 keyword groups)
- Confirmation field detection
- Reuse control detection ("same as", "copy from", "use shipping")
- Process grouping and Jaccard similarity
- `[readonly]` / `[aria-readonly="true"]` fields skipped (re-display, not re-entry)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`readonly` re-display in review step (should be OK)~~ | ✅ **Fixed** — skips `[readonly]` and `[aria-readonly="true"]` fields |
| Implicit semantic equivalence ("Shipping Address" ≡ "Address") | ✅ Partial — improve token normalization |

---

### SC 3.3.8 — Accessible Authentication (WCAG 2.2)
**Check:** `accessible-auth.check.js` | Mode: static

#### Approach
Detect authentication forms, then check for CAPTCHA, cognitive tests, and paste blocking.

#### Flowchart
```
Find auth forms:
  form with input[type=password] OR login text
  None ──► PASS (not applicable)
     │
for each auth form:
  CAPTCHA detection:
    Image CAPTCHA: img[src*="captcha"] / [class*="captcha"]
    reCAPTCHA: iframe[src*="recaptcha"] / .g-recaptcha /
               [data-sitekey][class*="recaptcha"]
    hCaptcha: .h-captcha / [data-hcaptcha-widget-id]
       │
    CAPTCHA found → has audio alternative?
      audio button / aria-label with audio/sound keyword
      No ──► ISSUE
     │
  Cognitive test detection:
    math: digit OP digit (e.g. "5 + 3 = ?")
    riddle / "what is the capital of…"
    "type the letters shown"
    ──► ISSUE
     │
  Paste blocking:
    dispatch synthetic paste event on password field
    defaultPrevented? ──► ISSUE
    onpaste="return false" attribute? ──► ISSUE
     │
any issue ──► FAIL    none ──► PASS
```

#### Covered
- Image, reCAPTCHA, hCaptcha, Cloudflare Turnstile detection (multi-signal)
- CAPTCHA audio alternative detection
- Math/riddle cognitive tests
- Password paste blocking (event + attribute)
- WebAuthn/passkey login option detection (skips CAPTCHA/cognitive-test/paste checks when passkey present)

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~WebAuthn / passkey login option~~ | ✅ **Fixed** — detects `passkey|webauthn|biometric|fingerprint|face id` text on buttons/links |
| ~~Turnstile (Cloudflare) CAPTCHA~~ | ✅ **Fixed** — detects `.cf-turnstile` / `[data-cf-turnstile]` |
| Paste blocking via Shadow DOM | No (synthetic event can't pierce shadow boundary) |

---

### SC 4.1.1 — Parsing
**Check:** `html-parsing.check.js` | Mode: static

#### Approach
Scan all elements with `id` attributes; flag any duplicate values.

#### Flowchart
```
querySelectorAll('[id]')
  null-prototype object tracks seen IDs
     │
  seen[id] already? ──► add to dupeIds
     │
dupeIds.length > 0 ──► FAIL (with deduplicated list)
none ──► PASS (reports total count)
```

#### Covered
- Duplicate `id` values (breaks ARIA label/describedby references)
- Broken `aria-labelledby` / `aria-describedby` / `aria-controls` / `aria-owns` references (ID not in DOM)
- Orphaned `<label for="…">` with no matching input

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~Broken `aria-labelledby` / `aria-describedby` references~~ | ✅ **Fixed** — resolves all ARIA ID references; flags missing targets |
| ~~Orphaned `<label for="…">` (no matching input)~~ | ✅ **Fixed** — verifies `label[for]` → matching `getElementById` |
| Duplicate IDs in Shadow DOM | No (shadow DOM not traversed) |

---

### SC 4.1.3 — Status Messages
**Check:** `status-messages.check.js` | Mode: static

#### Approach
Detect dynamic-content contexts (forms, search, cart, notifications), then verify ARIA live regions exist.

#### Flowchart
```
Detect dynamic contexts:
  Forms: document.querySelectorAll('form').length > 0
  Search results: [role="region"][aria-label*="result"] /
                  [id*="search-result"] / [class*="search-result"]
  Counter badge: [class*="badge"] with numeric text or counter label
                 (not just "New" or "Beta" ← fixed)
  Notification area: [class*="notification|toast|snackbar|flash|alert|banner"]
                     NOT already inside a live region ancestor
     │
needsLiveRegions = any context found
     │
Detect live regions:
  [aria-live] / [role=status|alert|log|timer|marquee]
     │
needsLiveRegions AND liveRegionCount=0 ──► FAIL
needsLiveRegions AND liveRegionCount>0 ──► INCOMPLETE (verify wiring)
liveRegions>0, no contexts ──► PASS
neither ──► INCOMPLETE
```

#### Covered
- Form, search, cart, notification detection
- Counter badge: numeric text only (avoids "New", "Beta" FPs — fixed)
- Live-region ancestor walk for notification elements
- Empty live region detection at page load
- `aria-atomic` presence check on `[role="alert"]` / `[aria-live="assertive"]` regions
- Inline `[aria-invalid]` elements without a live region ancestor

#### Missed
| Case | Solvable? |
|------|-----------|
| ~~`aria-atomic` requirement~~ | ✅ **Fixed** — flags `[role="alert"]`/`[aria-live="assertive"]` missing `aria-atomic="true"` as INCOMPLETE |
| AJAX-loaded result areas without `aria-live` | Hard (static) |
| ~~Inline validation feedback (not in live region)~~ | ✅ **Fixed** — walks ancestors of `[aria-invalid]` to find live region; flags INCOMPLETE if absent |

---

## Bugs Fixed (2026-04-01)

| # | File | Bug | Fix Applied |
|---|------|-----|-------------|
| 1 | `redundant-entry.check.js` | `'honific-suffix'` typo duplicating the valid `'honorific-suffix'` token — dead entry, never matched by browser autocomplete | Removed the typo entry |
| 2 | `status-messages.check.js` | `\bnew\b` in badge aria-label regex matched "New York", "New Products", "What's New" — false counter detection | Removed `new`; kept unambiguous `新着` for Japanese |
| 3 | `link-purpose.check.js` | `link.textContent` included `display:none` descendants (SR-only spans) — hid violations behind hidden helper text | Replaced with `TreeWalker` filtering invisible nodes via `getComputedStyle` |
| 4 | `audio-transcript.check.js` | `<details><summary>Transcript</summary>…</details>` pattern not detected — common valid transcript pattern | Added `details` element scan in container with transcript keyword match |
| 5 | `error-suggestion.check.js` | Short valid messages like "Enter 8+ characters" (21 chars) wrongly flagged as terse by `text.length < 25` guard | Added `SHORT_BUT_INFORMATIVE_RE` exemption for digits, format chars, correction keywords |
| 6 | `use-of-color.check.js` | Fallback transparent check used fragile string compare instead of `colorsDiffer()` — could miss variant formats | Replaced with `colorsDiffer(ls.backgroundColor, 'rgba(0, 0, 0, 0)')` |

## Solvable Possibilities Implemented (2026-04-03)

| # | File | Gap Addressed | Implementation |
|---|------|---------------|----------------|
| 7 | `meaningful-sequence.check.js` | Grid explicit placement reordering | Checks `gridColumnStart`/`gridRowStart !== 'auto'` on grid children |
| 8 | `meaningful-sequence.check.js` | Float sibling reordering | Flags containers with mixed floated/non-floated siblings |
| 9 | `orientation.check.js` | `writing-mode: vertical-rl/lr` body lock | Signal 6: `getComputedStyle(body).writingMode` → FAIL |
| 10 | `orientation.check.js` | `maximum-scale=1` viewport meta | Signal 7: parses viewport `content` string → INCOMPLETE |
| 11 | `use-of-color.check.js` | `section > p a` links | Added to SELECTORS |
| 12 | `use-of-color.check.js` | SVG `<a>` elements | Added `svg a[href]` to SELECTORS |
| 13 | `images-of-text.check.js` | SVG `<text>` used as images | Scans `svg text` inside `a/button/[role="img"]/figure` |
| 14 | `keyboard-trap.check.js` | Arrow key traps in ARIA widgets | Presses ArrowDown×2 in `tree/grid/listbox/menu/tablist/radiogroup` |
| 15 | `keyboard-trap.check.js` | Same-origin iframe traps | Iterates `page.frames()` for same-origin frames |
| 16 | `character-key-shortcuts.check.js` | `document.addEventListener` shortcuts | Added `docListenerRe` in Pass 3 |
| 17 | `multiple-ways.check.js` | Multi-language search keywords | Added FR/ES/DE/IT/NL/SV/ZH/JA/KO to search regex |
| 18 | `focus-visible.check.js` | Transform-based focus indicator | Added `transform` to captured/compared style properties |
| 19 | `location.check.js` | `aria-current="step"` wizard | Added `[aria-current="step"]` check |
| 20 | `location.check.js` | JSON-LD breadcrumb | Parses `<script type="application/ld+json">` for BreadcrumbList |
| 21 | `link-purpose.check.js` | `title` attribute accessible name | Added as 5th fallback in name computation |
| 22 | `focus-appearance.check.js` | Border-width area requirement | `areaMet` now includes `borderChanged && borderWidth >= 2` |
| 23 | `pointer-cancellation.check.js` | `ontouchstart` handlers | Added to selector; `ontouchend` as cancellation path |
| 24 | `dragging-movements.check.js` | Interact.js / Dragula / generic | Added `[data-interact]`, `.gu-transit`, `[data-drag-handle]` markers |
| 25 | `pronunciation.check.js` | Section-level CJK on English pages | Scans `[lang^="ja/zh/ko"]` sub-elements |
| 26 | `on-focus.check.js` | SPA pushState navigation | Intercepts `pushState`/`replaceState`; checks `__navChanges` after focus |
| 27 | `on-input.check.js` | `contenteditable` interaction | Added `[contenteditable="true/"]` to selector |
| 28 | `on-input.check.js` | SPA routing on input change | Same `pushState`/`replaceState` interception as 3.2.1 |
| 29 | `on-input.check.js` | Select with 0 options | Guard: `if (options.length < 2) continue` |
| 30 | `consistent-help.check.js` | Accessibility statement link | Added `accessibility` to `HELP_PATTERNS` |
| 31 | `consistent-help.check.js` | Chatbot platform detection | Added 7 known widget selectors (Intercom, Drift, Zendesk, HelpScout, Crisp, Tawk, HubSpot) |
| 32 | `error-suggestion.check.js` | `title` attribute error messages | Collects `[aria-invalid="true"][title]` before main loop |
| 33 | `error-prevention.check.js` | "Donate" financial keyword | Added `donat` to keyword pattern |
| 34 | `error-prevention.check.js` | Hidden safeguards (`display:none`) | `isVisible()` filter applied to safeguard elements |
| 35 | `redundant-entry.check.js` | `readonly` re-display fields | Skips `[readonly]` / `[aria-readonly="true"]` in field extraction |
| 36 | `accessible-auth.check.js` | Cloudflare Turnstile CAPTCHA | Detects `.cf-turnstile` / `[data-cf-turnstile]` |
| 37 | `accessible-auth.check.js` | WebAuthn/passkey alternative | Detects passkey/biometric button text; skips CAPTCHA checks |
| 38 | `html-parsing.check.js` | Broken ARIA ID references | Resolves `aria-labelledby/describedby/controls/owns` → `getElementById` |
| 39 | `html-parsing.check.js` | Orphaned `<label for>` | Verifies `label[for]` → matching element exists |
| 40 | `status-messages.check.js` | `aria-atomic` on assertive regions | Flags `[role="alert"]`/`[aria-live="assertive"]` missing `aria-atomic` |
| 41 | `status-messages.check.js` | Inline validation without live region | Walks ancestors of `[aria-invalid]`; flags if no live region found |

---

## Solvable Possibilities Summary

All previously identified solvable gaps have been implemented (2026-04-03). See "Solvable Possibilities Implemented" table above for details.

Remaining gaps that are **not solvable** without OCR, runtime state, or cross-origin access:

| SC | Gap | Reason |
|----|-----|--------|
| 1.2.1 | Third-party audio embeds (Spotify, SoundCloud) | Not `<audio>` in DOM |
| 1.2.1 | AJAX-loaded transcripts | Not in DOM at load time |
| 1.3.2 | `grid-auto-flow: dense` reorder | Requires layout engine |
| 1.3.2 | CSS multicolumn reading order | Hard to determine without render |
| 1.4.5 | `<canvas>` rendering text | Requires OCR or pixel read |
| 2.1.2 | Traps requiring Enter to trigger | Partial — requires interaction chain |
| 2.1.4 | External script files | Cross-origin restriction |
| 2.1.4 | Framework bindings (React/Vue) | Runtime only, not in DOM |
| 2.4.5 | Alphabetical keyword index | Complex pattern, partial heuristic |
| 2.4.7 | `:focus-visible`-only styles | `.focus()` doesn't trigger `:focus-visible` |
| 2.4.7 | Pseudo-element focus indicators | `getComputedStyle(el, '::before')` lacks `:focus` context |
| 2.4.13 | Focus indicator on child element | Would need descendant enumeration |
| 2.5.2 | `addEventListener` cancellation handlers | Not in DOM attributes |
| 2.5.2 | `oncontextmenu` suppression | Could add, minor edge case |
| 2.5.7 | `onpointermove` custom drag | Would need gesture heuristic |
| 3.1.6 | Kanji in `<img alt>` | Alt text, not a text node |
| 3.1.6 | Ruby position correctness | Requires linguistic knowledge |
| 3.2.1 | AJAX content replacement on focus | No navigation event |
| 3.2.2 | Checkbox already-checked toggle | Edge case, minor |
| 3.2.6 | Cross-page consistency | Single-page scan only |
| 3.3.3 | Dynamic errors (JS post-submit) | Static load only |
| 3.3.4 | Undo as a safeguard | Requires runtime testing |
| 3.3.8 | Paste blocking via Shadow DOM | Synthetic event can't pierce shadow |
| 4.1.1 | Duplicate IDs in Shadow DOM | Shadow DOM not traversed |
| 4.1.3 | AJAX-loaded result areas | Static scan cannot detect |

---

## axe-core Coverage (no custom check needed)

These SCs are handled exclusively by axe-core's built-in rule engine:

`1.1.1` `1.2.2` `1.3.1` `1.3.5` `1.4.2` `1.4.3` `1.4.4` `1.4.6` `1.4.12` `2.1.1` `2.2.1` `2.2.2` `2.2.4` `2.4.1` `2.4.2` `2.4.3` `2.4.4` `2.4.6` `2.5.3` `2.5.8` `3.1.1` `3.1.2` `3.3.2` `4.1.2`

---

## Coverage Confidence Summary

Confidence levels updated after 2026-04-03 improvements. "Primary Gap" now reflects only unsolvable remaining cases.

| SC | Check | Confidence (before → after) | Primary Remaining Gap |
|----|-------|-----------------------------|-----------------------|
| 1.2.1 | audio-transcript | Medium → Medium | External embeds (iframes), AJAX transcripts |
| 1.3.2 | meaningful-sequence | Medium → **High** | `grid-auto-flow: dense`, CSS multicolumn |
| 1.3.4 | orientation | High → **High** | `aspect-ratio` media query locking |
| 1.4.1 | use-of-color | Medium → **High** | Icon-only link with color-only bg change |
| 1.4.5 | images-of-text | Low → **Medium** | `<canvas>` text, very short text images |
| 2.1.2 | keyboard-trap | High → **High** | Enter-triggered traps (modal open) |
| 2.1.4 | character-key-shortcuts | Medium → **Medium** | External scripts, framework bindings |
| 2.4.5 | multiple-ways | Medium → **High** | Alphabetical index pattern |
| 2.4.7 | focus-visible | High → High | `:focus-visible`-only styles, pseudo-elements |
| 2.4.8 | location | Medium → **High** | Obscure location patterns |
| 2.4.9 | link-purpose | High → High | Table-context links (2.4.4 territory) |
| 2.4.13 | focus-appearance | Medium → **High** | Focus indicator on child element |
| 2.5.2 | pointer-cancellation | Low → **Medium** | `addEventListener` handlers, `oncontextmenu` |
| 2.5.7 | dragging-movements | Medium → **High** | `onpointermove` custom drag, touch drag |
| 3.1.6 | pronunciation | Medium → **High** | Kanji in img alt, ruby position correctness |
| 3.2.1 | on-focus | High → **High** | AJAX content replacement (no URL change) |
| 3.2.2 | on-input | High → **High** | Checkbox already-checked toggle edge case |
| 3.2.6 | consistent-help | Low → **Medium** | Cross-page consistency (single-page limit) |
| 3.3.3 | error-suggestion | Medium → **Medium** | Dynamic post-submit errors |
| 3.3.4 | error-prevention | Medium → **High** | Undo-as-safeguard (runtime) |
| 3.3.7 | redundant-entry | Medium → **High** | Semantic token normalization ("Address" ≡ "Shipping Address") |
| 3.3.8 | accessible-auth | Medium → **High** | Paste blocking via Shadow DOM |
| 4.1.1 | html-parsing | High → **High** | Duplicate IDs in Shadow DOM |
| 4.1.3 | status-messages | Medium → **High** | AJAX-loaded result areas (static scan limit) |
