# ka11y Full Codebase — Code Report
**Services:** `ka11y-node` (axe-core + custom checks) · `ka11y-python` (crawlers + OCR + auditors)
**Date:** 2026-03-26

---

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [ka11y-node — Rule Analysis](#2-ka11y-node--rule-analysis)
   - [Infrastructure bugs](#21-infrastructure--service-layer)
   - [Per-rule custom check failures](#22-custom-checks--per-rule)
3. [ka11y-python — Rule Analysis](#3-ka11y-python--rule-analysis)
   - [API / pipeline layer](#31-api--pipeline-layer)
   - [Crawler failures](#32-crawlers)
   - [Auditor failures](#33-auditors)
   - [OCR / contrast pipeline](#34-ocr--contrast-pipeline)
4. [Cross-service bugs](#4-cross-service-integration-bugs)
5. [Security issues](#5-security)
6. [Priority matrix](#6-priority-matrix)

---

## 1. Architecture Overview

```
Browser / Frontend
       │
       ▼
ka11y-python FastAPI  ──────────────►  ka11y-node Express
  (port 8000)           HTTP POST        (port 3000)
  /api/v1/combined      /api/v1/         /api/v1/analyse-url-flat
       │                axe results           │
       │◄────────────────────────────────────┘
       │
  Python stages (parallel asyncio.gather)
  ├── image_audit   → EasyOCR → contrast_analyser
  ├── form_audit    → form_auditor
  ├── label_in_name → label_in_name_auditor
  ├── pause_stop_hide → psh_auditor
  ├── target_size   → ts_auditor
  ├── text_spacing  → ts_auditor
  └── rendered_layout → Playwright scenarios
```

---

## 2. ka11y-node — Rule Analysis

### 2.1 Infrastructure / Service Layer

---

#### N1 — No page-load wait after `domcontentloaded` before axe runs
**File:** `accessibility.service.js:208`
```javascript
await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
// axe injected immediately — no settling delay
await page.addScriptTag({ path: this._axeCorePath });
```
Dynamic SPA content (React/Vue lazy mounts) hasn't rendered. axe-core runs against a partially hydrated DOM → missing `<img>`, `<button>`, ARIA landmarks → false passes on violations that are visually present.

**Suggested fixture:** SPA page where nav links render 200ms after `domcontentloaded` — confirm axe catches missing focus management.

---

#### N2 — `analyseUrlFlat` runs interactive checks on every call (expensive + slow)
**File:** `accessibility.service.js:306`
```javascript
const customResults = await runAll(page);   // static + interactive
```
`analyseUrlFlat` is the hot path called by ka11y-python for every audit job. All 5 interactive checks (focus-visible, focus-appearance, on-focus, on-input, keyboard-trap) run, each tabbing through up to 40 elements. On large pages this adds 20–60 seconds to every combined audit.

**Suggested fixture:** Page with 50 form inputs — measure flat endpoint response time; confirm interactive checks fire.

---

#### N3 — Semaphore not released on `_assertPublicUrl` throw
**File:** `accessibility.service.js:187-188`
```javascript
await _assertPublicUrl(url);   // throws → no slot acquired
await this._acquireSlot();
```
SSRF guard throws before `_acquireSlot()` → no slot consumed, no issue here. This is safe. But if order were reversed (slot acquired first), it would deadlock. Worth noting as a latent architectural hazard if order changes.

---

#### N4 — `analyze(html)` skips interactive checks entirely
**File:** `accessibility.service.js:157`
```javascript
const customResults = await runStaticChecks(page);  // only static
```
`analyze` (raw HTML endpoint) never runs `focus-visible`, `focus-appearance`, `on-focus`, `on-input`, `keyboard-trap`. Clients using the HTML endpoint get incomplete WCAG coverage for 2.4.7, 2.4.13, 3.2.1, 3.2.2, 2.1.2. There is no documentation of this limitation.

---

#### N5 — `mergeWithAxe` dedup operates on `successCriteriaId` only
**File:** `custom-checks/index.js:152-165`
```javascript
if (map.has(entry.successCriteriaId)) {
    map.get(entry.successCriteriaId).rules.push(...entry.rules);  // appends
}
```
If axe already has a finding for `1.4.5` AND the custom images-of-text check also fires for `1.4.5`, both sets of rules are concatenated into one SC bucket. A user sees potentially duplicate findings for the same element with no deduplication at rule/element level.

---

#### N6 — No rate limiting on Node endpoints
**File:** `server.js` (all routes)
Node has no rate limiting middleware. ka11y-python's rate limiter (30 POST/60s) only protects the Python side. The Node service can be DoS'd independently with concurrent `analyse-url` requests, each launching a Puppeteer browser.

---

### 2.2 Custom Checks — Per-Rule

---

#### WCAG 1.2.1 — `audio-transcript.check.js`

**Bug A1 — Only checks `<audio>` elements, misses `<video>` audio-only content**
```javascript
const audioEls = document.querySelectorAll('audio');
```
A `<video>` element containing only a audio track (no visual content) must also satisfy 1.2.1. The check completely misses `<video>` elements.

**Bug A2 — `figcaption` accepted as transcript without verifying it contains text**
```javascript
const hasFigcaption = audio.closest('figure')?.querySelector('figcaption') != null;
```
An empty `<figcaption></figcaption>` or one containing only whitespace is accepted as a valid transcript → false pass.

**Suggested fixtures:**
- `<video><source src="audio-only.mp3"></video>` — should flag 1.2.1
- `<figure><audio src="a.mp3"></audio><figcaption>  </figcaption></figure>` — empty figcaption, should fail

---

#### WCAG 1.3.2 — `meaningful-sequence.check.js`

**Bug A3 — Visibility filter uses `offsetParent` which fails on `position:fixed`**
```javascript
const isVisible = el => el.offsetParent !== null || el.tagName === 'BODY';
```
`position:fixed` elements have `offsetParent === null` even when visible. Fixed headers/navs with flex-direction:row-reverse are missed entirely.

**Bug A4 — CSS `order` baseline comparison ignores implicit `0`**
```javascript
if (orders.every(o => o === orders[0])) continue; // all same → skip
```
If some children have explicit `order:0` and others have no `order` attribute, they all compute to 0 → the check skips the container. But if one child has `order:-1`, the array is `[-1, 0, 0, 0]` → skip is NOT triggered, but the check may emit a false positive if the DOM order was already correct.

**Suggested fixtures:**
- Fixed header with `display:flex; flex-direction:row-reverse`
- Grid where `order:-1` reorders a visually prominent element to front

---

#### WCAG 1.4.1 — `use-of-color.check.js`

**Bug A5 — 15-unit RGB threshold is arbitrary and undocumented**
```javascript
const colorDiff = Math.abs(r1-r2) + Math.abs(g1-g2) + Math.abs(b1-b2);
if (colorDiff > 15) { hasCue = true; }
```
WCAG 1.4.1 does not define a color-difference number. The threshold 15 (out of 765 total possible) is extremely low — nearly identical colors pass. A link with `color: rgb(0,0,200)` against body `color: rgb(0,0,210)` would be flagged as "different enough" with a non-color cue present.

**Bug A6 — Only checks inline links (`a` inside `p, li, td`) — misses standalone links**
```javascript
const candidates = document.querySelectorAll(
    'p a[href], li a[href], td a[href], dd a[href], blockquote a[href]'
);
```
A link in a `<div>` or `<section>` that is purely color-distinguished is missed.

**Suggested fixtures:**
- `<div><a href="#" style="color:blue">Link</a> adjacent text</div>` — should flag
- Link pair where only color distinguishes them from body text, rgb diff < 15

---

#### WCAG 1.4.5 — `images-of-text.check.js`

**Bug A7 — Scoring heuristic has no ground truth; logo exception is path-based**
```javascript
if (/logo|brand|wordmark/i.test(src + cls + id)) score -= 3; // logo exemption
```
Any image with "logo" in its src, class, or id skips 1.4.5 regardless of whether it actually qualifies for the WCAG logo exception (which requires custom typography). A plain-text company name in Arial stored at `/images/logo.png` passes unchecked.

**Bug A8 — Score threshold 3 produces false negatives on social-share images**
Infographic screenshots (e.g., `share-image.png`) typically have numeric src names with no text-related classes → score stays at 0–1 → always pass despite containing large text overlays.

**Suggested fixtures:**
- `/images/logo.png` containing "Company Name" in Arial — should flag or needs_review
- `/share/og-image.png` containing a headline — should flag

---

#### WCAG 2.1.2 — `keyboard-trap.check.js`

**Bug A9 — Only checks the LAST focused element, not accumulated sequence**
```javascript
// Tracks last N elements, not cumulative history
```
A modal dialog that cycles through 4 elements (A→B→C→D→A) is a trap, but if N > 4, the rolling window never shows consecutive repeats → no trap detected.

**Bug A10 — Escape key test is unreliable for custom traps**
```javascript
await page.keyboard.press('Escape');
await page.waitForTimeout(300);
// checks if focus moved outside
```
Many modals close on Escape and ARE properly trapping (which is allowed per WCAG 2.1.2 if Escape provides an exit). Others intercept Escape via `preventDefault()` — the check fires Escape, nothing moves, but this is flagged as a PASS (trap confirmed releasable). The logic is inverted for dialogs that use Escape-as-exit.

**Suggested fixtures:**
- 4-element focus cycle in a custom widget (no native dialog role)
- Modal with `role="dialog"` that traps on Tab/Shift+Tab but exits on Escape — should pass
- Widget that intercepts and blocks Escape — should fail

---

#### WCAG 2.4.5 — `multiple-ways.check.js`

**Bug A11 — Single-page apps with client-side routing count as 0 ways**
```javascript
const hasSitemap = document.querySelector('a[href*="sitemap"]') != null;
const hasSearch = document.querySelector('[role="search"], input[type="search"]') != null;
```
SPAs often implement search via a modal or overlay toggled by JS — the `<input type="search">` may not exist in the DOM until the user opens search. Static DOM scan returns 0 even though the page has search functionality.

**Suggested fixture:** SPA with Algolia search widget (input rendered on button click)

---

#### WCAG 2.4.7 — `focus-visible.check.js`

**Bug A12 — 80ms settle time too short for CSS transition-based focus indicators**
```javascript
await page.waitForTimeout(80);
const after = await page.evaluate(...);
```
Many design systems use `transition: outline 0.2s ease` or `transition: box-shadow 0.15s`. The 80ms window captures the element mid-transition → style values read as partially applied → incorrectly reports "no focus change" when the indicator eventually appears.

**Bug A13 — `outline: none` paired with `box-shadow` is accepted, but may be invisible on Windows High Contrast**
The check accepts ANY style change as proof of a visible indicator. `box-shadow` is invisible in Windows High Contrast mode (forced-color). The check gives a pass when the only visual change is a box-shadow.

**Suggested fixtures:**
- Button with `transition: outline-color 0.2s` — wait for full transition
- Element with only `box-shadow` on focus — verify pass/fail intent

---

#### WCAG 2.4.8 — `location.check.js`

**Bug A14 — `aria-current="page"` on ANY element counts as location indicator**
```javascript
const hasAriaCurrent = document.querySelector('[aria-current="page"]') !== null;
```
A decorative element with `aria-current="page"` (e.g., a highlighted hero banner) satisfies the check even though it doesn't function as navigation. No verification that the element is inside a navigation landmark.

**Suggested fixture:** `<section aria-current="page">Hero content</section>` — should not satisfy 2.4.8

---

#### WCAG 2.4.13 — `focus-appearance.check.js`

**Bug A15 — Luminance calculation uses CSS `rgb()` string parsing without handling `rgba()`, `oklch()`, `color()`**
```javascript
const m = rgb.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
```
Modern CSS uses `oklch()`, `color(display-p3, ...)`, `rgba()`. `getComputedStyle` in Chromium returns legacy `rgb()` for most colours, but `oklch` and `color()` values from CSS custom properties may pass through unparsed → luminance calculation returns `null` → check falls through to "pass" silently.

**Bug A16 — Focus area check measures outline width only, not enclosed perimeter**
WCAG 2.4.13 requires the focus indicator area to be at least the perimeter of the component times 2px. The check measures `outline-width >= 2px` but does not compute the actual enclosed pixel area against the perimeter requirement.

**Suggested fixtures:**
- Button styled with `oklch(0.5 0.2 240)` outline
- Small 16×16 icon button with a 2px outline (perimeter 64px, required area 128px²)

---

#### WCAG 2.5.2 — `pointer-cancellation.check.js`

**Bug A17 — Only checks elements with `onpointerdown` — misses `addEventListener`**
```javascript
const elements = document.querySelectorAll('[onpointerdown], [onmousedown]');
```
Any element that registers `pointerdown` via `addEventListener('pointerdown', fn)` is completely invisible to this check. The vast majority of modern JS frameworks use `addEventListener`, not inline handlers.

**Suggested fixture:** React component with `onPointerDown` prop (compiled to `addEventListener`)

---

#### WCAG 2.5.7 — `dragging-movements.check.js`

**Bug A18 — Alternative detection looks for buttons/links anywhere on page, not near draggable**
```javascript
const alternatives = document.querySelectorAll('button, a[href]');
hasSinglePointerAlternative = alternatives.length > 0;
```
If the page has ANY button or link, the check reports an alternative exists. A drag-sortable list with no reorder buttons passes because there happens to be a "Home" link in the nav.

**Suggested fixtures:**
- Page with `react-beautiful-dnd` sortable list and zero reorder buttons (only a nav link exists)

---

#### WCAG 3.2.1 — `on-focus.check.js`

**Bug A19 — Monitors `framenavigated` but not `console` errors from JS navigation**
```javascript
page.on('framenavigated', () => { navigationOccurred = true; });
```
`history.pushState()` and client-side routing (React Router, Next.js) do NOT trigger `framenavigated`. A focus event that calls `router.push('/dashboard')` on a SPA is completely missed.

**Suggested fixture:** Next.js page where focusing a button triggers `router.push()`

---

#### WCAG 3.3.3 — `error-suggestion.check.js`

**Bug A20 — Terse message detection uses English-only keywords**
```javascript
const tersePatterns = ['invalid', 'error', 'required', 'incorrect', 'wrong'];
```
Internationalized pages showing errors in French ("invalide"), Spanish ("inválido"), or German ("ungültig") are never flagged even if the error message provides no correction guidance.

**Suggested fixture:** Form with French error messages that provide no correction guidance

---

#### WCAG 3.3.4 — `error-prevention.check.js`

**Bug A21 — Financial form detection misses generic checkout flows**
```javascript
const keywords = ['payment', 'checkout', 'purchase', 'credit card', 'billing'];
```
"Order summary", "Complete order", "Place order" are not in the keyword list. Standard e-commerce checkout pages are missed unless they use literal "checkout" text.

**Bug A22 — Safeguard detection looks for "confirm" text in buttons — misses two-step flows that use "Next"**
A multi-page form (Step 1 → Step 2 → Review → Submit) satisfies 3.3.4 by having a review step, but the check only looks for a single-page review button — it doesn't traverse multi-page flows.

---

#### WCAG 3.3.8 — `accessible-auth.check.js`

**Bug A23 — Only detects Google reCAPTCHA and hCaptcha by iframe src / class name**
```javascript
const captchaIframes = iframes.filter(src =>
    /recaptcha|hcaptcha|turnstile/.test(src)
);
```
Cloudflare Turnstile, FunCAPTCHA (Arkose Labs), AWS WAF CAPTCHA, and custom image-grid CAPTCHAs are not detected. A site using a bespoke CAPTCHA with no audio alternative is always marked as pass.

**Suggested fixture:** Page with a custom image-grid CAPTCHA (no audio alt)

---

## 3. ka11y-python — Rule Analysis

### 3.1 API / Pipeline Layer

---

#### P1 — CORS allows all origins in production
**File:** `main.py`
```python
CORSMiddleware(app, allow_origins=["*"], ...)
```
Node service uses a whitelist. Python service allows any origin. Browsers will freely cross-origin POST to the Python service from any domain.

---

#### P2 — Rate limiter uses `time.monotonic()` — not wall-clock safe
**File:** `main.py:41`
```python
now = time.monotonic()
window_start = now - self._WINDOW_SECONDS
```
`time.monotonic()` is correct for measuring elapsed time, but the window timestamps stored in `_requests` are also monotonic. After a server restart, monotonic values reset to near-zero, making all previously stored timestamps appear as extremely old → window is cleared → rate limit resets on every restart. In-memory store is lost anyway on restart, so this is low risk but still incorrect semantics.

---

#### P3 — In-memory job store lost on restart
**File:** `store.py`
```python
_jobs: Dict[str, Any] = {}
```
All running/completed jobs vanish on server restart. Clients polling `GET /combined/{job_id}` after a restart receive 404 with no explanation. Long-running audits (>10 minutes) silently fail if the server restarts.

---

#### P4 — `_evict_old_jobs` runs every 5 minutes but TTL is 1 hour — jobs can grow unbounded between evictions
**File:** `store.py`
```python
_JOB_TTL_SECONDS = 3600
# background task sleeps 300s between passes
```
Under high load, 60 new jobs created per minute × 60 minutes = 3600 jobs accumulate in memory before the first eviction pass fires. Each job holds a full report dict (potentially several MB for large audits).

---

#### P5 — SSE heartbeat swallows subscriber queue exceptions silently
**File:** `routes.py` (SSE stream handler)
```python
try:
    event = await asyncio.wait_for(queue.get(), timeout=25.0)
except asyncio.TimeoutError:
    yield ": heartbeat\n\n"
```
If `queue.get()` raises a `CancelledError` (client disconnects), the generator does not close the subscriber cleanly. The job's `_subscribers[job_id]` list retains the dead queue, and future `_broadcast()` calls try to put into a closed queue.

---

#### P6 — Image serving endpoint — path traversal risk
**File:** `routes.py:285`
```python
img_path = Path(path)                      # constructed from user input
if img_path not in valid_paths:            # set membership check
    raise HTTPException(404, ...)
# → img_path.read_bytes() served
```
`valid_paths` is built from `img["path"]` values in the stored report. If an attacker submits a crafted path that resolves canonically to a path already in `valid_paths` (e.g., `/foo/../foo/bar.png` == `/foo/bar.png`), the `Path` comparison may succeed or fail inconsistently depending on how paths were stored. Use `Path.resolve()` on both sides of the comparison.

---

### 3.2 Crawlers

---

#### WCAG 1.1.1 / All image rules — `crawler.py`

**Bug C1 — Pass 1 icon screenshots have no `timeout` parameter**
```python
# Line 426 — parent screenshot for icons
await ph.screenshot(path=save_path)   # no timeout — defaults to 60s
```
Only button (Pass 2) and font-icon (Pass 4) screenshots received the `timeout=5_000` fix. Pass 1 icon-type images that fall back to a parent screenshot still use the default 60s timeout.

**Bug C2 — Pass 3 SVG files saved as `.svg` — OCR cannot process them**
```python
svg_content = await svg.evaluate("el => el.outerHTML")
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg_content)
```
`text_detector.py` only scans `{.png, .jpg, .jpeg, .gif, .webp}`. All Pass 3 SVG icons are skipped by OCR → no 1.4.3 / 1.4.6 findings for SVG icons with text content.

**Bug C3 — `seen_srcs` dedup by URL loses same-image-multiple-context coverage**
The same image used as both an informative product photo and a decorative placeholder is captured once with one classification. The second (different) classification is discarded.

**Bug C4 — Background image classification ignores `role="img"` without label**
```python
# Lines 849-860
else:
    cls, sub = "decorative", "decorative"   # role="img" with no aria-label lands here
```
A `<div role="img" style="background-image:url(x.jpg)">` with no `aria-label` needs a text alternative per 1.1.1, but is classified decorative and never audited.

---

#### WCAG 2.2.2 — `moving_content_crawler.py`

**Bug C5 — Retry logic retries with identical parameters**
```python
try:
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
except Exception:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)  # identical
    except Exception:
        await page.goto(url, wait_until="commit", timeout=15_000)
```
The first retry repeats the exact same call. A timeout failure will timeout again. The fallback to `"commit"` is only reached after two 30-second timeouts = 60+ seconds wasted.

**Bug C6 — Animated GIF detection `Image.open()` resource not explicitly closed**
```python
img = Image.open(io.BytesIO(resp.content))
try:
    while True:
        img.seek(img.tell() + 1)
        frames += 1
except EOFError:
    pass
```
`img` is never closed. In a long scan with many GIFs, file descriptors / memory accumulate. PIL recommends using `img.close()` or a context manager.

**Bug C7 — CSS animation duration parsing misses `s` vs `ms` unit conversion**
```python
duration_seconds = float(duration_str.rstrip("s"))
```
A CSS `animation-duration: 500ms` would strip the `s` from `ms`, leaving `500m`, which `float()` raises on → uncaught `ValueError` → animation silently skipped.

---

#### WCAG 2.5.3 — `interactive_crawler.py`

**Bug C8 — `aria-labelledby` is crawled but not resolved**
The crawler collects `aria-labelledby` attribute values but doesn't resolve the IDs to their referenced text. The label_in_name auditor receives the raw ID string (e.g., `"btn-label"`) instead of the referenced text (`"Close dialog"`), making the 2.5.3 comparison meaningless for labelledby-labelled elements.

---

#### WCAG 2.5.8 — `target_size_crawler.py`

**Bug C9 — Floating-point zero comparison**
```javascript
if (rect.width === 0 && rect.height === 0) return;
```
Elements with sub-pixel dimensions (0.001px) pass through and receive a "fails 24px" verdict correctly, but elements rendered off-screen with `visibility:hidden` may have non-zero dimensions and are incorrectly included.

**Bug C10 — `box-sizing: border-box` not accounted for in padding exception check**
The inline exception (WCAG 2.5.8 E1) checks if padding makes the clickable area large enough. With `box-sizing: border-box`, padding is INCLUDED in `width/height`, not additional. The check adds padding to `getBoundingClientRect()` values, double-counting and making undersized elements pass the inline exception incorrectly.

---

#### WCAG 1.4.12 / 1.4.10 / 1.4.4 — `rendered_layout_crawler.py`

**Bug C11 — Focus selector construction has operator precedence bug**
```python
await page.focus(
    cand.get("selector", "") or f"#{cand_id}" if cand_id else tag
)
```
Python evaluates this as: `(cand.get("selector", "") or f"#{cand_id}") if cand_id else tag`. When `cand_id` is `None` and `tag` is a non-unique tag like `"div"`, `page.focus("div")` is called → focuses an arbitrary div → wrong element's styles are measured.

**Bug C12 — Hardcoded 1280×720 desktop viewport skips wide-format checks**
```python
_DESKTOP_W, _DESKTOP_H = 1280, 720
```
WCAG 1.4.10 (Reflow) requires content to work at 320px width without horizontal scrolling (scrolling direction only). Checks at 320px (portrait) are done, but 1280px is used as desktop baseline. Sites that only break at 1024px-wide viewports are missed.

**Bug C13 — Shadow DOM elements invisible to all rendered-layout checks**
`document.querySelectorAll(...)` used throughout all evaluators does not pierce shadow DOM. Web components using shadow roots (Material Design, Lit, custom elements) have their focusable and overflow elements completely invisible.

---

### 3.3 Auditors

---

#### WCAG 1.1.1 — `alttext.py`

**Bug D1 — Generic alt text list does not cover all common generic phrases**
```python
_EMPTY_OR_GENERIC = {"image", "img", "photo", "picture", "graphic", ...}
```
Common CMS-generated alts like `"DSC_0042.jpg"`, `"image001"`, `"thumbnail"`, `"featured"`, `"banner"`, `"hero"` are not in the list → false passes for auto-generated filenames used as alt text.

**Bug D2 — 3-character minimum for icon alt text is too permissive**
```python
if len(norm) >= 3 and not norm.isdigit():
    return (True, "PASS [1.1.1] Icon alt is non-empty...")
```
`"box"`, `"pic"`, `"img"`, `"btn"` are all 3 characters and pass. None meaningfully describe the icon's purpose.

**Bug D3 — Logo alt text is only checked for non-emptiness**
```python
# Logo: any non-empty alt is acceptable
if alt:
    return (True, "PASS [1.1.1] Logo alt present.")
```
`alt="logo"` on a company logo passes, but "logo" is a generic description. It does not convey the company name or the logo's destination when it's a link.

---

#### WCAG 3.3.1 / 3.3.2 — `form_auditor.py`

**Bug D4 — `aria-required="false"` causes false positive**
```python
is_marked_required = f.required or (f.aria_required or "").strip().lower() == "true"
```
An element with `required=False, aria-required="false"` is correctly not required. But if `aria_required` is the string `"false"`, the check `== "true"` correctly returns `False`. This is actually safe. However, `aria-required=""` (empty string) after `.strip().lower()` equals `""`, which also correctly returns False. Edge case: `aria-required="TRUE"` after `.lower()` returns `"true"` → correctly flags. This particular check appears safe, but `f.required` comes from the crawler's JavaScript which uses `el.required` (a boolean DOM property) — this is correct for HTML5 `required` attribute but misses CSS-driven required states via some frameworks.

**Bug D5 — `autocomplete` check fires on all text inputs, not just personal-data fields**
```python
if f.type in ("text", "email", "tel", "url") and not f.autocomplete:
    status = "FAILED"
```
WCAG 1.3.5 (autocomplete) only applies to inputs collecting personal data. A "Search" text box or "Filter by name" field failing because it lacks `autocomplete` is a false positive.

**Bug D6 — Placeholder-as-label detection misses CSS-based floating labels**
```python
if not f.has_label and f.placeholder:
    # flag as placeholder-only
```
Many modern UI kits implement floating labels using CSS — visually the placeholder text floats up as a label, but in the DOM it's still a placeholder. The auditor would flag these correctly. However, some frameworks use `<label>` positioned absolutely over the input via CSS — `has_label` may be True (label exists in DOM) but the user experience is identical to placeholder-only → false pass.

---

#### WCAG 2.5.3 — `label_in_name_auditor.py`

**Bug D7 — `_strip_punctuation` uses `\W` which strips Unicode letters**
```python
return re.sub(r"[^\w\s]", "", text).strip()
```
The Python `\w` in regex includes Unicode word chars by default — BUT the NFC normalization + casefold then feeds into `re.sub` with `re.ASCII` implicit in the caller pattern. For scripts like Arabic or Chinese, visible label text is correctly stripped of punctuation but word-boundary matching breaks for non-Latin scripts.

**Bug D8 — Short label false-negative: labels under 3 characters skip word-boundary check**
```python
if len(vis_words) <= 1 and len(vis_norm) <= 2:
    return "N/A", ""  # too short to check meaningfully
```
A visible label of "OK" or "Go" (2 chars) is skipped. A button with accessible name "Go to homepage" and visible label "Go" should fail 2.5.3 (accessible name doesn't START with visible label). Instead it's N/A.

---

#### WCAG 2.2.2 — `pause_stop_hide_auditor.py`

**Bug D9 — `loops=True` with `duration_seconds=None` is incorrectly passed**
```python
if (
    not is_infinite
    and not item.loops
    and item.duration_seconds is not None
    and item.duration_seconds <= 5.0
):
    return "PASSED", ""
```
When `loops=True` and `duration_seconds=None`, none of the pass conditions are met → falls through to FAILED. This is actually correct behaviour. But when `loops=False` and `duration_seconds=None`, the condition `duration_seconds is not None` is False → also falls through to FAILED. A single-play animation with unknown duration is always failed, which is overly strict.

**Bug D10 — Pause mechanism detection checks element text, not ARIA label**
```python
if any(kw in (item.pause_btn_text or "").lower() for kw in ["pause", "stop", "hide"]):
```
An icon-only pause button (`<button aria-label="Pause">⏸</button>`) has empty `innerText`. Its `pause_btn_text` is empty → mechanism not detected → false fail even though a valid pause control exists.

---

#### WCAG 2.5.8 — `target_size_auditor.py`

**Bug D11 — Exception 2 (equivalent control) is always needs_review — never automated**
All elements without a clear native control type receive `"Exception: Equivalent control (INCOMPLETE — manual review required)"`. This may flood the report for pages with many non-native interactive elements.

---

### 3.4 OCR / Contrast Pipeline

---

#### WCAG 1.4.3 / 1.4.6 — `text_detector.py` + `contrast_analyser.py`

**Bug E1 — `is_bold = False` hardcoded — large/bold text threshold never applied correctly**
```python
# text_detector.py:199
is_bold = False
```
Bold text ≥18.5px has an AA threshold of 3.0:1 instead of 4.5:1. Since bold is never detected, text in bold headings at ratio 3.8:1 is reported as a fail. No font-weight extraction from pixel data is implemented.

**Bug E2 — Font size from bbox height is DPR-unaware**
```python
bbox_height = abs(clean_bbox[2][1] - clean_bbox[0][1])
font_size_px = max(bbox_height, 8)
```
On 2× DPR (retina) screenshots, a 16px CSS font has a 32px bbox → classified as large text → AA threshold drops to 3.0:1 → false passes for text that fails at 4.5:1. The browser viewport does not set `deviceScaleFactor`.

**Bug E3 — Alpha-channel PNG read without `IMREAD_UNCHANGED`**
```python
img = cv2.imread(image_path)   # alpha discarded → transparent → black
```
Transparent regions (button backgrounds, icon canvases) become `rgb(0,0,0)`. White text on a transparent background computes as white-on-black → extreme contrast → false pass for elements that are actually rendered on a coloured page background.

**Bug E4 — Otsu inversion heuristic fails on text-dominant images**
```python
# contrast_analyser.py:34-37
if np.sum(thresh == 255) > thresh.size / 2:
    mask = cv2.bitwise_not(thresh)
```
When text occupies >50% of image pixels (e.g., a text-heavy call-to-action button, a wordmark), Otsu labels background as text and text as background → inverted luminance → wrong ratio → false pass or false fail depending on polarity.

**Bug E5 — EasyOCR bbox vertex height estimation breaks for rotated text**
```python
bbox_height = abs(clean_bbox[2][1] - clean_bbox[0][1])
```
For text rotated >15°, the top-left y and bottom-right y coordinates converge → near-zero height → floored to 8px → classified as tiny normal text with 4.5:1 threshold even if the actual glyph height would qualify as large text.

**Bug E6 — SVG files never scanned by OCR**
```python
image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
```
Pass 3 of the crawler saves inline SVGs as `.svg`. These are skipped by `scan_directory()` → zero 1.4.3 findings for SVG icons containing `<text>` elements.

**Bug E7 — CSS `animation-duration: 500ms` crashes duration parser**
```python
duration_seconds = float(duration_str.rstrip("s"))   # strips "s" from "ms" → "500m" → ValueError
```
`"ms"`.rstrip(`"s"`) → `"m"` → `float("500m")` raises `ValueError` → animation silently skipped, no finding emitted.

---

## 4. Cross-service Integration Bugs

---

#### X1 — Node `analyseUrlFlat` timeout is 30s; Python stage timeout is 600s — mismatch
**Files:** `accessibility.service.js`, `stages.py`

If a page is complex (heavy JS, many ARIA widgets), axe-core may take longer than 30s in Node and throw. Python catches this as `node_findings=[]` and continues with Python-only findings. The report appears complete but silently drops all axe findings. No warning surfaces in the UI about the axe timeout.

---

#### X2 — `_merge_findings` dedup key uses `element.html[:120].lower()` — fails for dynamic IDs
**File:** `runner.py:_merge_findings`
```python
el_html = (element.get("html") or "").strip()[:120].lower()
```
Frameworks like React and Angular generate dynamic class names / IDs (e.g., `class="sc-1a2b3c"`, `id="ember123"`). Two findings for the same logical element have different generated attributes → different dedup keys → not deduplicated → duplicate findings in report.

---

#### X3 — Python level filter applied AFTER merge; axe findings not filtered by level
**File:** `runner.py:160-166`
```python
python_findings = [f for f in python_findings if f.get("level") in allowed ...]
# node_findings NOT filtered
all_findings = _merge_findings(node_findings, python_findings)
```
When `wcag_level="A"`, Python findings are filtered to Level A only, but ALL axe findings (including Level AA and AAA rules run by `_tagsForLevel`) pass through unfiltered. The report contains axe AA findings mixed with Python A-only findings.

---

#### X4 — axe-core uses `domcontentloaded`; Python Playwright crawler also uses `domcontentloaded`
Both services navigate to the same URL independently. Each launches its own browser. If the target URL has rate limiting or bot detection (Cloudflare, AWS WAF), two concurrent headless Chromium instances hitting the same page may trigger a block → one or both return empty results with no informative error.

---

#### X5 — Contrast report `image_url` injection uses unvalidated `img['path']` from stored report
**File:** `runner.py:135-139`
```python
for img in report["contrast_report"].get("images", []):
    img["image_url"] = (
        f"/api/v1/combined/{job_id}/image?path={quote(img['path'], safe='')}"
    )
```
`img['path']` comes from OCR results which store `abs_path = str(Path(image_path).resolve())`. If the crawler output directory is under a world-readable path, the absolute path is exposed to frontend clients via `image_url`, revealing the server filesystem layout.

---

## 5. Security

| ID | Location | Issue | Severity |
|----|----------|-------|----------|
| S1 | `main.py` | `allow_origins=["*"]` in CORS | Medium |
| S2 | `routes.py:285` | Path traversal — use `Path.resolve()` on both sides | High |
| S3 | `runner.py:135` | Absolute filesystem path exposed in `image_url` | Low |
| S4 | `accessibility.service.js` | No rate limiting on Node endpoints | Medium |
| S5 | `routes.py` (Python SSRF) | IPv4-mapped IPv6 (`::ffff:10.x.x.x`) not in blocklist | High |
| S6 | `forms_crawler.py` | Raw DOM ID interpolated into `querySelector` string — XSS if ID contains `"` | Medium |

**S5 detail:**
```python
# Python routes.py SSRF guard
_PRIVATE_PREFIXES = ["127.", "10.", "192.168.", "169.254.", "::1", "fc", "fd", "fe80"]
```
`::ffff:10.0.0.1` (IPv4-mapped IPv6) is not matched by any of these patterns → SSRF bypass possible on dual-stack servers.

**S6 detail (forms_crawler.py):**
```javascript
const labelEl = id ? document.querySelector('label[for="' + id + '"]') : null;
```
If a form field has `id='x" class="evil'`, the selector becomes `label[for="x" class="evil"]` → selector parse error or unintended element match. This is a DOM-level concern (no server RCE), but could cause incorrect audit data.

---

## 6. Priority Matrix

### Critical — Fix immediately (false results / data loss)

| ID | Service | Rule | Description |
|----|---------|------|-------------|
| E3 | Python | 1.4.3 / 1.4.6 | Alpha PNG read without `IMREAD_UNCHANGED` → all transparent images give wrong contrast |
| E4 | Python | 1.4.3 / 1.4.6 | Otsu inversion on text-heavy images → wrong fg/bg polarity |
| C7 | Python | 2.2.2 | `500ms` duration crashes float parser → animations silently skipped |
| X3 | Both | All | axe findings not filtered by WCAG level → level filter is Python-only |
| A17 | Node | 2.5.2 | `addEventListener` pointer handlers never detected (only inline `onpointerdown`) |
| C5 | Python | 2.2.2 | Retry navigator repeats same timeout → doubles wait time |

### High — Fix before next release (significant false positives/negatives)

| ID | Service | Rule | Description |
|----|---------|------|-------------|
| E1 | Python | 1.4.3 / 1.4.6 | `is_bold=False` hardcoded → bold text threshold never applied |
| E2 | Python | 1.4.3 / 1.4.6 | DPR-unaware font size → retina screenshots misclassify text size |
| E6 | Python | 1.4.3 | SVG files skipped by OCR entirely |
| C1 | Python | 1.1.1 | Pass 1 icon parent screenshots still use 60s default timeout |
| C8 | Python | 2.5.3 | `aria-labelledby` collected but not resolved → meaningless comparison |
| D10 | Python | 2.2.2 | Icon-only pause button not detected → false fail |
| A12 | Node | 2.4.7 | 80ms settle too short for CSS transition focus indicators |
| A19 | Node | 3.2.1 | `history.pushState()` / client-side routing not detected |
| N1 | Node | All | No settling delay after `domcontentloaded` for SPA content |
| S2 | Python | — | Path traversal in image serve endpoint |
| S5 | Python | — | IPv4-mapped IPv6 SSRF bypass |

### Medium — Address in backlog

| ID | Service | Rule | Description |
|----|---------|------|-------------|
| A5 | Node | 1.4.1 | Arbitrary 15-unit RGB threshold for color difference |
| A9 | Node | 2.1.2 | Rolling focus window too large — small cycle traps missed |
| A15 | Node | 2.4.13 | `oklch()` / `color()` values not parsed for luminance |
| C11 | Python | Multiple | Operator precedence bug in focus selector construction |
| D1 | Python | 1.1.1 | Generic alt list missing common CMS-generated filenames |
| D5 | Python | 1.3.5 | `autocomplete` flagged on non-personal-data fields |
| X1 | Both | All | axe 30s timeout not surfaced as warning in combined report |
| X2 | Both | All | Dynamic class/ID generation defeats `_merge_findings` dedup |
| N4 | Node | Multiple | `analyze(html)` silently skips all 5 interactive checks |
| P1 | Python | — | CORS allows all origins |

### Low — Improvements / Nice-to-have

| ID | Service | Rule | Description |
|----|---------|------|-------------|
| E5 | Python | 1.4.3 | Rotated text bbox height near-zero → floor to 8px |
| C6 | Python | 2.2.2 | PIL Image resource not closed → memory accumulation |
| A3 | Node | 1.3.2 | `offsetParent` fails for `position:fixed` elements |
| A14 | Node | 2.4.8 | Any `aria-current="page"` satisfies location check |
| D8 | Python | 2.5.3 | 2-char labels skipped → "OK" / "Go" not checked |
| P4 | Python | — | Job store can grow unbounded between eviction passes |
| X5 | Python | — | Absolute filesystem path exposed in `image_url` |
