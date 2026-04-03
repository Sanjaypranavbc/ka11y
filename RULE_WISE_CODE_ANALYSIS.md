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

#### Missed
| Case | Solvable? |
|------|-----------|
| Arrow key traps in custom widgets (tree, grid, listbox) | ✅ Solvable — add Arrow key navigation test after Tab |
| Traps requiring Enter to trigger (e.g. open modal) | Partial |
| Traps in same-origin iframes | ✅ Solvable — switch to iframe context with `page.frames()` |

#### Possibility: Arrow key trap in widgets
```js
const WIDGET_ROLES = ['tree', 'grid', 'listbox', 'menu', 'tablist', 'radiogroup'];
for (const role of WIDGET_ROLES) {
  const widget = await page.$(`[role="${role}"]`);
  if (widget) {
    await widget.focus();
    const before = await page.evaluate(() => document.activeElement?.id);
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    const after = await page.evaluate(() => document.activeElement?.id);
    // if before === after and focus didn't move out → possible trap
  }
}
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| External script files | No (cross-origin restriction) |
| Delegated handlers on `document`/`window` | ✅ Solvable — scan inline scripts for `document.addEventListener` |
| Framework event bindings (React `onKeyDown`, Vue `v-on`) | No (runtime, not in DOM) |
| Arrow key shortcuts without modifiers | ✅ Solvable — extend key pattern to include Arrow keys |

#### Possibility: Detect `document.addEventListener` shortcuts in inline scripts
```js
// In Pass 3, extend to also match document-level listeners:
const docListenerRe = /document\s*\.\s*addEventListener\s*\(\s*['"]key(down|press|up)['"]/;
if (docListenerRe.test(scriptText)) {
  // same single-char + modifier guard check
}
```

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
| French/German/Spanish search terms | ✅ Solvable — extend keyword list |
| Skip-nav link counting as a mechanism | Partial |

#### Possibility: Multi-language search keywords
```js
const searchKeywords = /search|recherche|suche|buscar|cerca|zoeken|sök|検索|搜索|검색/i;
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `:focus-visible`-only styles | ✅ Partial — could inject `Tab` key press instead of `.focus()` |
| Pseudo-element indicators (`::before`/`::after`) | No — `getComputedStyle` on pseudo needs `:focus` context |
| Scale/transform-based focus indicator | ✅ Solvable — add `transform` to compared properties |

#### Possibility: Add `transform` to focus style comparison
```js
// In unfocused/focused capture:
transform: cs.transform,
// In comparison:
const transformChanged = focused.transform !== unfocused.transform;
const isVisible = ... || transformChanged;
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `aria-current="step"` (multi-step wizard) | ✅ Solvable — add `aria-current="step"` check |
| JSON-LD breadcrumb (not in DOM) | ✅ Solvable — parse `<script type="application/ld+json">` for BreadcrumbList |

#### Possibility: Add `aria-current="step"` and JSON-LD
```js
// aria-current="step"
const hasAriaCurrentStep = !!document.querySelector('[aria-current="step"]');

// JSON-LD breadcrumb
const ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
const hasLdBreadcrumb = Array.from(ldScripts).some(s => {
  try { return /"BreadcrumbList"/.test(s.textContent); } catch { return false; }
});
```

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
- 30+ generic English patterns
- Japanese generic patterns
- Visible-only text (fixed: excludes `display:none` descendants)

#### Missed
| Case | Solvable? |
|------|-----------|
| `title` attribute as accessible name fallback | ✅ Solvable — add `link.getAttribute('title')` as 5th fallback |
| Context-based purpose (table column header gives meaning) | Not at link-only level (2.4.4 SC) |
| Short but specific links matching "go" pattern | Partial — "go" is in regex; could narrow |

#### Possibility: Add `title` attribute fallback
```js
if (!accessibleName) {
  accessibleName = (link.getAttribute('title') || '').trim();
}
```

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
- 2px minimum area (outline-width or box-shadow spread)
- 3:1 contrast ratio (WCAG luminance formula)
- Transparent background fallback to `<body>` background
- CSS variable resolution (browser resolves via `getComputedStyle`)

#### Missed
| Case | Solvable? |
|------|-----------|
| Border-based focus indicator area | ✅ Solvable — add `borderWidth` to area check |
| Focus indicator on child not the target element | Hard — would need to check all descendants |

#### Possibility: Include border-width in area check
```js
const borderWidth = parseFloat(focused.borderWidth) || 0;
const borderChanged = focused.borderWidth !== unfocused.borderWidth;
const areaMet = outlineWidth >= 2 || spreadRadius >= 2 || (borderChanged && borderWidth >= 2);
```

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
- `mousedown` / `pointerdown` / `pointermove` attribute handlers
- Action keyword detection
- Visual-only handler exclusion
- Cancellation via `mouseup` / `pointerup` / `click`

#### Missed
| Case | Solvable? |
|------|-----------|
| `ontouchstart` handlers | ✅ Solvable — add `[ontouchstart]` to selector |
| `oncontextmenu="return false"` suppression | ✅ Solvable — detect and flag separately |
| `addEventListener` handlers | No (not in DOM attributes) |

#### Possibility: Add touch event detection
```js
// Extend selector:
const SELECTOR = '[onmousedown], [onpointerdown], [onpointermove], [ontouchstart]';
// Add touchstart check analogous to mousedown check
```

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
- 4 major D&D libraries
- Single-pointer alternative detection
- Deduplication

#### Missed
| Case | Solvable? |
|------|-----------|
| `onpointerdown` + move custom drag (no `draggable` attr) | ✅ Solvable — add `[onpointermove]` with drag pattern check |
| `ontouchstart` drag implementations | ✅ Solvable — add `[ontouchstart]` with data-* context |
| Interact.js / Dragula / other libs | ✅ Solvable — add library class signatures |

#### Possibility: Add Interact.js and Dragula detection
```js
// In library markers:
{ sel: '[data-interact]',        name: 'Interact.js' },
{ sel: '.gu-transit',            name: 'Dragula' },
{ sel: '[data-drag-handle]',     name: 'generic drag handle' },
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| Section-level CJK in an English page | ✅ Solvable — scan `[lang="ja"]` sub-elements regardless of page lang |
| Kanji in `<img alt>` | No (alt text, not text node) |
| Ruby position correctness | Hard (requires linguistic knowledge) |

#### Possibility: Section-level CJK scan
```js
// Also check any element with an explicit CJK lang attribute:
const cjkSections = document.querySelectorAll('[lang^="ja"], [lang^="zh"], [lang^="ko"]');
// Re-run ruby coverage check on each section
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| SPA client-side routing (React Router, Next.js) | ✅ Solvable — intercept `pushState`/`replaceState` |
| Content replacement via AJAX (no URL change) | Hard — no navigation event |
| Modal/overlay on focus (content change, not navigation) | ✅ Solvable — detect large DOM mutations after focus |

#### Possibility: Detect SPA navigation via `pushState` interception
```js
// Before test, inject pushState monitor:
await page.evaluate(() => {
  window.__navChanges = 0;
  const orig = history.pushState.bind(history);
  history.pushState = function(...args) { window.__navChanges++; return orig(...args); };
});
// After each focus, check window.__navChanges
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `contenteditable` elements | ✅ Solvable — add `[contenteditable]` to selector, type 'a' |
| SPA routing on input change | ✅ Solvable — same `pushState` interception as 3.2.1 |
| Select with 0 options (no change fires) | ✅ Solvable — skip if `options.length < 2` |
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
- Help/support/FAQ/contact links
- Phone, email, chat mechanisms
- Location tracking (header/footer/nav/body)

#### Missed
| Case | Solvable? |
|------|-----------|
| Consistency across pages | No (single-page scan only) |
| Accessibility statement link | ✅ Solvable — add pattern for "accessibility" in link text |
| AI chatbot without "chat" in class/id | ✅ Solvable — add common chatbot div IDs (Intercom, Drift, Zendesk) |

#### Possibility: Add common chatbot platform detection
```js
// Known chatbot widget signatures:
const chatbotSelectors = [
  '#intercom-container', '#drift-widget',
  '#zendesk-widget', '[id*="helpscout"]',
  '.crisp-client', '[id*="tawk"]',
];
const hasChatbot = chatbotSelectors.some(s => !!document.querySelector(s));
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `<input title="…">` error guidance | ✅ Solvable — collect `[title]` on `[aria-invalid]` inputs |
| Dynamic errors (shown post-submit in JS) | No (static load only) |
| Error in collapsed `<details>` | Partial |

#### Possibility: Collect `title` attribute error messages
```js
for (const el of document.querySelectorAll('[aria-invalid="true"][title]')) {
  const text = (el.getAttribute('title') || '').trim();
  if (text.length > 3 && !seen.has(el)) {
    allErrors.push(text.slice(0, 120));
    seen.add(el);
  }
}
```

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
- Financial, legal, destructive context keywords
- 4 safeguard types
- Multi-language keywords (English + Japanese)

#### Missed
| Case | Solvable? |
|------|-----------|
| "Donate Now" high-risk without standard keywords | ✅ Solvable — add "donat" to financial keywords |
| Safeguards hidden in collapsed sections (`display:none`) | ✅ Solvable — filter elements with `display:none` |
| Undo functionality as a safeguard | Hard — requires runtime testing |

#### Possibility: Filter hidden safeguards
```js
function isVisible(el) {
  const cs = window.getComputedStyle(el);
  return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0';
}
// Apply isVisible() filter when checking for safeguards
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `readonly` re-display in review step (should be OK) | ✅ Solvable — skip `[readonly]` inputs |
| Implicit semantic equivalence ("Shipping Address" ≡ "Address") | ✅ Partial — improve token normalization |

#### Possibility: Skip `readonly` fields (they are re-display, not re-entry)
```js
// When extracting fields, skip readonly:
if (field.hasAttribute('readonly') || field.getAttribute('aria-readonly') === 'true') continue;
```

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
- Image, reCAPTCHA, hCaptcha detection (multi-signal)
- CAPTCHA audio alternative detection
- Math/riddle cognitive tests
- Password paste blocking (event + attribute)

#### Missed
| Case | Solvable? |
|------|-----------|
| WebAuthn / passkey login option | ✅ Solvable — detect `[type=button]` with webauthn/passkey text |
| Turnstile (Cloudflare) CAPTCHA | ✅ Solvable — detect `[class*="cf-turnstile"]` |
| Paste blocking via Shadow DOM | No (synthetic event can't pierce shadow boundary) |

#### Possibility: Detect Cloudflare Turnstile and WebAuthn
```js
// Turnstile:
const hasTurnstile = !!document.querySelector('.cf-turnstile, [data-cf-turnstile]');

// WebAuthn alternative:
const hasPasskeyOption = Array.from(document.querySelectorAll('button, a')).some(el =>
  /passkey|webauthn|biometric|fingerprint|face id/i.test(el.textContent + el.getAttribute('aria-label'))
);
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| Broken `aria-labelledby` / `aria-describedby` references | ✅ Solvable — resolve all referenced IDs and check existence |
| Orphaned `<label for="…">` (no matching input) | ✅ Solvable — verify label `for` → `id` chain |
| Duplicate IDs in Shadow DOM | No (shadow DOM not traversed) |

#### Possibility: Add broken ARIA reference check
```js
// After duplicate ID check:
const brokenRefs = [];
for (const el of document.querySelectorAll('[aria-labelledby], [aria-describedby], [aria-controls], [aria-owns]')) {
  for (const attr of ['aria-labelledby','aria-describedby','aria-controls','aria-owns']) {
    const val = el.getAttribute(attr);
    if (!val) continue;
    for (const id of val.split(/\s+/).filter(Boolean)) {
      if (!document.getElementById(id)) brokenRefs.push({ attr, id, el: el.outerHTML.slice(0,100) });
    }
  }
}
```

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

#### Missed
| Case | Solvable? |
|------|-----------|
| `aria-atomic` requirement | ✅ Solvable — check `aria-atomic="true"` on alerting live regions |
| AJAX-loaded result areas without `aria-live` | Hard (static) |
| Inline validation feedback (not in live region) | ✅ Solvable — check `[aria-invalid] + *` for live region ancestor |

#### Possibility: Check `aria-atomic` on assertive live regions
```js
const missingAtomic = liveRegions.filter(el =>
  (el.getAttribute('role') === 'alert' || el.getAttribute('aria-live') === 'assertive') &&
  !el.hasAttribute('aria-atomic')
);
```

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

---

## Solvable Possibilities Summary

These are missing cases that can be added with moderate effort without requiring OCR, external APIs, or browser engine internals.

| SC | Gap | Approach |
|----|-----|----------|
| 1.2.1 | `<details>` transcript | ✅ Done (Bug 4) |
| 1.3.2 | Grid placement reordering | Check `gridColumnStart`/`gridRowStart` vs DOM index |
| 1.3.2 | Float reordering | Detect `float` on sibling elements |
| 1.3.4 | `writing-mode: vertical-rl` body lock | Check `getComputedStyle(body).writingMode` |
| 1.3.4 | `maximum-scale=1` in viewport meta | Parse viewport `content` string |
| 1.4.1 | `section > p a` links | Add to SELECTORS list |
| 1.4.1 | SVG `<a>` elements | Add `svg a[href]` to SELECTORS |
| 1.4.5 | SVG `<text>` elements used as images | Scan `svg text` in `[role="img"]` context |
| 2.1.2 | Arrow key traps in ARIA widgets | Press ArrowDown inside `[role=tree|grid|listbox]` |
| 2.1.2 | Same-origin iframe traps | Switch to iframe context with `page.frames()` |
| 2.1.4 | `document.addEventListener` shortcuts | Extend inline script scan to match `document.add…` calls |
| 2.4.5 | Multi-language search keywords | Add FR/DE/ES/ZH/KO equivalents to search regex |
| 2.4.7 | Transform-based focus indicator | Add `transform` to style comparison properties |
| 2.4.8 | `aria-current="step"` (wizard location) | Add `[aria-current="step"]` to location checks |
| 2.4.8 | JSON-LD breadcrumb | Parse `<script type="application/ld+json">` for BreadcrumbList |
| 2.4.9 | `title` attribute link name | Add `link.getAttribute('title')` as 5th accessible name fallback |
| 2.4.13 | Border-width in area requirement | Add `borderWidth ≥ 2` to area check alongside outline/shadow |
| 2.5.2 | `ontouchstart` pointer cancellation | Add `[ontouchstart]` to selector |
| 2.5.7 | Interact.js / Dragula detection | Add class signatures `.gu-transit`, `[data-interact]` |
| 3.1.6 | Section-level CJK in English page | Scan `[lang^="ja|zh|ko"]` sub-elements |
| 3.2.1 | SPA `pushState` navigation detection | Intercept `history.pushState` before test |
| 3.2.2 | `contenteditable` input change | Add `[contenteditable]` to input selector |
| 3.2.2 | Select with 0 options (skip) | Guard: `if (el.options.length < 2) continue` |
| 3.2.6 | Chatbot platform detection | Add Intercom/Drift/Zendesk/Crisp selector signatures |
| 3.2.6 | Accessibility statement link | Add "accessibility" to help link keyword list |
| 3.3.3 | `title` attribute error messages | Collect `[aria-invalid][title]` as error source |
| 3.3.4 | "Donate" as financial keyword | Add `donat` to financial keyword pattern |
| 3.3.4 | Hidden safeguards (`display:none`) | Filter safeguards through `isVisible()` check |
| 3.3.7 | `readonly` re-display in review step | Skip `[readonly]` / `[aria-readonly="true"]` fields |
| 3.3.8 | Cloudflare Turnstile CAPTCHA | Detect `.cf-turnstile` / `[data-cf-turnstile]` |
| 3.3.8 | WebAuthn/passkey alternative | Detect button text "passkey"/"biometric"/"fingerprint" |
| 4.1.1 | Broken ARIA reference IDs | Resolve all `aria-labelledby/describedby/controls/owns` → check getElementById |
| 4.1.1 | Orphaned `<label for>` | Verify `label[for]` → matching input exists |
| 4.1.3 | Missing `aria-atomic` on assertive regions | Check `aria-atomic="true"` presence |
| 4.1.3 | Inline validation without live region ancestor | Check `[aria-invalid] + *` for live region ancestor |

---

## axe-core Coverage (no custom check needed)

These SCs are handled exclusively by axe-core's built-in rule engine:

`1.1.1` `1.2.2` `1.3.1` `1.3.5` `1.4.2` `1.4.3` `1.4.4` `1.4.6` `1.4.12` `2.1.1` `2.2.1` `2.2.2` `2.2.4` `2.4.1` `2.4.2` `2.4.3` `2.4.4` `2.4.6` `2.5.3` `2.5.8` `3.1.1` `3.1.2` `3.3.2` `4.1.2`

---

## Coverage Confidence Summary

| SC | Check | Confidence | Primary Gap |
|----|-------|-----------|-------------|
| 1.2.1 | audio-transcript | Medium | External audio embeds, AJAX transcripts |
| 1.3.2 | meaningful-sequence | Medium | Grid placement, float layouts |
| 1.3.4 | orientation | High | `writing-mode` body lock |
| 1.4.1 | use-of-color | Medium | SVG links, section-level links |
| 1.4.5 | images-of-text | Low | SVG text, canvas text, short text images |
| 2.1.2 | keyboard-trap | High | Arrow-key widget traps, iframes |
| 2.1.4 | character-key-shortcuts | Medium | External scripts, delegated listeners |
| 2.4.5 | multiple-ways | Medium | Multi-language terms, keyword index |
| 2.4.7 | focus-visible | High | `:focus-visible`-only styles |
| 2.4.8 | location | Medium | `aria-current="step"`, JSON-LD |
| 2.4.9 | link-purpose | High | `title`-only names, table context links |
| 2.4.13 | focus-appearance | Medium | Border-based area, child indicators |
| 2.5.2 | pointer-cancellation | Low | Touch events, addEventListener |
| 2.5.7 | dragging-movements | Medium | Touch drag, unlisted libraries |
| 3.1.6 | pronunciation | Medium | Section-level CJK, proper nouns |
| 3.2.1 | on-focus | High | SPA client-side routing |
| 3.2.2 | on-input | High | `contenteditable`, custom controls |
| 3.2.6 | consistent-help | Low | Cross-page consistency, chatbots |
| 3.3.3 | error-suggestion | Medium | Dynamic errors, `title` attribute |
| 3.3.4 | error-prevention | Medium | "Donate" gap, hidden safeguards |
| 3.3.7 | redundant-entry | Medium | `readonly` re-display, prefill |
| 3.3.8 | accessible-auth | Medium | Turnstile, WebAuthn, Shadow DOM |
| 4.1.1 | html-parsing | High | Broken ARIA refs, Shadow DOM |
| 4.1.3 | status-messages | Medium | `aria-atomic`, inline validation |
