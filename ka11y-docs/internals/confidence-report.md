# ka11y Rule Confidence Report

**Generated:** 2026-03-23
**Scope:** All 12 Python auditor rules + 5 supporting infrastructure layers
**Method:** Full static analysis of every auditor, crawler, evaluator, converter, and shared utility

> Confidence is defined as **"probability that a ka11y finding (pass or fail) reflects reality for the average production page"**.
> It is distinct from WCAG coverage — a rule can be 100% correct and still only cover 60% of the spec.

---

## Score legend

| Score | Meaning |
|-------|---------|
| 90–100% | High confidence — result is almost always accurate |
| 70–89%  | Good — occasional edge-case misses or false positives |
| 50–69%  | Moderate — heuristic-dependent; expect manual verification needed |
| < 50%   | Low — structural flaw, missing exception, or fragile detection |

---

## Summary table

| # | Rule | WCAG SC | Engine | Confidence | Critical issues |
|---|------|---------|--------|-----------|-----------------|
| 1 | Alt Text | 1.1.1 | py-static | **62%** | OCR substring matching; icon validation too permissive |
| 2 | Contrast (OCR) | 1.4.3 | py-static | **72%** | OCR accuracy ceiling; no font-size context |
| 3 | Form Labels / Errors | 3.3.1, 3.3.2 | py-static | **68%** | aria-describedby resolves only first ID; placeholder-as-label gap |
| 4 | Label in Name | 2.5.3 | py-static | **82%** | Good — depends on crawler accuracy |
| 5 | Pause / Stop / Hide | 2.2.2 | py-static | **65%** | Carousel detection framework-only; pause button via naive regex |
| 6 | Target Size | 2.5.8 | py-static | **55%** | UA-controlled logic **inverted**; 3 of 5 WCAG exceptions missing |
| 7 | Reflow | 1.4.10 | py-rendered | **75%** | 5 px scroll threshold; exempt-detection keyword list |
| 8 | Text Spacing | 1.4.12 | py-rendered | **63%** | Element matching via tag+text prefix is fragile |
| 9 | Resize Text | 1.4.4 | py-rendered | **65%** | Same fragile element matching; only detects *new* horizontal scroll |
| 10 | Orientation | 1.3.4 | py-rendered | **60%** | Regex too exact; interactive-count ratio gives false hits on menus |
| 11 | Content on Hover/Focus | 1.4.13 | py-rendered | **45%** | No persistence test; hover-direction hardcoded; selector too narrow |
| 12 | Focus Not Obscured (Min) | 2.4.11 | py-rendered | **58%** | Overlays collected once; absolute-positioned overlays missed; opacity ignored |
| 13 | Focus Not Obscured (Enh) | 2.4.12 | py-rendered | **55%** | All issues from 2.4.11 + tighter threshold raises false positive rate |

---

## Rule-by-rule breakdown

---

### 1 · Alt Text — WCAG 1.1.1 · Confidence: 62%

**What it does**
OCR-backed alt text checker. Classifies images (decorative, informative, functional, complex) and validates alt attributes for each class.

**Why 62%**

| Issue | Severity | Impact |
|-------|----------|--------|
| OCR matching uses **substring** (`if w in norm_alt`) not word-boundary | High | "search" in `norm_alt` matches alt="Research" → false PASS |
| Icon validation allows any `len(alt) >= 2 and not isdigit` | High | alt="hi", alt="ok", alt="++" all PASS |
| Complex images (charts) only require non-empty, non-generic alt | Medium | alt="Chart" PASSES; WCAG requires long description |
| `title` attribute ignored as fallback name source | Medium | Elements with `title` but no `alt` reported as failures |
| `missing_alt` classification branch appears dead | Low | Unreachable code path |

**False positive risk:** Medium — overly permissive for icons and complex images.
**False negative risk:** Medium — OCR substring matching can miss genuine failures.

**What to fix first**
Replace substring match with `re.search(rf'\b{re.escape(w)}\b', norm_alt)` in `_check_1_1_1_informative`. Raise icon validation minimum length to 4+ characters and require at least one real word.

---

### 2 · Contrast (OCR-backed) — WCAG 1.4.3 · Confidence: 72%

**What it does**
Runs EasyOCR on crawled images, extracts foreground/background colour, computes contrast ratio, reports AA compliance.

**Why 72%**

| Issue | Severity | Impact |
|-------|----------|--------|
| Depends on EasyOCR text detection accuracy | High | Missed or hallucinated text regions upstream → wrong findings |
| No font-size context — applies normal text threshold (4.5:1) universally | Medium | Large text (≥18pt) should use 3:1; false FAIL for large headings |
| Background palette picks dominant colour, not closest pixel | Medium | Gradient backgrounds → wrong background reference |
| Confidence field present but not gated (low-confidence OCR passes through) | Medium | Garbled OCR text can produce spurious colour readings |
| No de-duplication of findings across multiple images | Low | Same text region found in two crawled variants → double-counted |

**False positive risk:** Medium — font-size threshold gap causes false failures on large text.
**False negative risk:** Low-Medium — OCR misses text in unusual fonts or very high-contrast renders.

**What to fix first**
Add font-size context from image metadata or a minimum confidence gate (skip detections with `confidence < 0.5`). Add AA-large path: if detected text is large (heuristic: font-size > 18px equivalent), apply 3:1 threshold.

---

### 3 · Form Labels / Error Messages — WCAG 3.3.1 & 3.3.2 · Confidence: 68%

**What it does**
Crawls form fields, checks for accessible labels (3.3.2) and error-message associations via aria-describedby + role="alert" / aria-live (3.3.1).

**Why 68%**

| Issue | Severity | Impact |
|-------|----------|--------|
| `aria-describedby` resolves only the **first** space-separated ID | High | Error messages linked by later IDs silently dropped |
| Placeholder counted as label fallback; WCAG explicitly prohibits this | High | Fields with only placeholder PASS when they should FAIL |
| `aria-describedby` target not checked for actual error content | Medium | Points-to-a-div but empty div PASSES |
| Autocomplete detection uses substring on field name | Medium | `photo_url` matches `url`; `newsletter_email_promo` matches `email` → false FAIL |
| No visibility check — hidden form fields are included | Medium | Shadow forms or CSS-hidden groups generate spurious findings |
| Fields visually marked required ("*") but lacking `required` attr → no violation | Low | Missed best-practice flag |

**False positive risk:** Medium — autocomplete substring matching; hidden fields included.
**False negative risk:** Medium — multi-ID aria-describedby; placeholder-as-label gap.

**What to fix first**
Split `aria-describedby` on whitespace and resolve ALL referenced IDs. Add visibility filter: skip elements where `getComputedStyle(el).display === 'none'`.

---

### 4 · Label in Name — WCAG 2.5.3 · Confidence: 82%

**What it does**
Verifies that the accessible name of an interactive element contains its visible label text (for voice-control users saying the visible button text).

**Why 82%**

| Issue | Severity | Impact |
|-------|----------|--------|
| Depends entirely on crawler's `visible_label` accuracy | Medium | If crawler extracts wrong text, this rule is wrong |
| Accessible name source not validated for visibility | Low | An invisible aria-label that contains the visible text PASSES |
| Word-boundary regex works for multi-word labels, but only tested for English | Low | CJK characters or non-space-delimited languages may behave unexpectedly |

**False positive risk:** Low.
**False negative risk:** Low-Medium — accuracy depends on crawler quality.

**What to fix first**
Add a source-verification step: log which attribute supplied the `visible_label` and the `accessible_name` so mismatches can be diagnosed.

---

### 5 · Pause / Stop / Hide — WCAG 2.2.2 · Confidence: 65%

**What it does**
Detects autoplay videos, animated GIFs, CSS animations > 5s, carousels, and marquee elements, then checks for a pause/stop mechanism.

**Why 65%**

| Issue | Severity | Impact |
|-------|----------|--------|
| Carousel detection is **framework-specific** (Bootstrap, Slick, Swiper, Owl, Flickity, Glide, Splide only) | High | Custom carousels entirely missed |
| Pause button detection via `/pause|stop/` regex — fragile | High | "Stop-motion gallery" → false PASS; non-English UI → always FAIL |
| Video `duration` checked before `loadedmetadata` fires | Medium | NaN treated as unknown; actual duration never captured for async-loaded videos |
| Animated GIF timeout (3 s/GIF) on slow networks → assumed animated | Medium | False FAIL on non-animated GIFs on slow connections |
| CSS animation deduplication collapses same `animationName` on one element | Low | Multiple animations reported as one |
| `prefers-reduced-motion` check only works if page uses `animation-play-state` | Low | Most sites use `display:none` under reduced-motion instead → not detected |

**False positive risk:** Medium — slow-network GIF timeout; regex overmatch.
**False negative risk:** High — custom (non-framework) carousels entirely missed.

**What to fix first**
Replace regex with a semantic button check (role="button" OR `<button>`) + aria-label containing pause/stop/play concepts. Add a fallback carousel heuristic that looks for element sequences with `overflow:hidden` parent + transition/animation.

---

### 6 · Target Size — WCAG 2.5.8 · Confidence: 55%

**What it does**
Measures rendered width/height of interactive targets and checks against the 24×24 px minimum.

**Why 55%**

| Issue | Severity | Impact |
|-------|----------|--------|
| **UA-controlled exception logic is inverted** (returns `true` when custom-styled) | Critical | Custom-styled radios/checkboxes exempt when they should not be |
| Only 2 of 5 WCAG exceptions implemented (inline + UA-controlled) | High | Offset, equivalent, and essential exceptions entirely absent → false FAILs |
| Padding measured but never evaluated (spacing exception not implemented) | High | Small buttons with large surrounding space still flagged |
| Inline exception uses simple `String.replace()` — breaks with duplicate text | Medium | Links whose text appears elsewhere in parent → wrong exemption |
| No hover-state measurement | Low | Elements that expand on hover may be under-measured |

**False positive risk:** High — missing exceptions cause legitimate small controls to fail.
**False negative risk:** Low — the check itself is straightforward once applied.

**What to fix first (Critical)**
Fix the inverted UA-controlled logic:
```javascript
// CURRENT (wrong): returns true for custom-styled
return !['none', 'auto'].includes(app) || app === 'auto';
// CORRECT: UA-controlled if appearance is not overridden
return !['none', ''].includes(app) || app === 'auto';
```
Then implement the offset exception: if `padding + size >= 24` in both axes, mark as PASS.

---

### 7 · Reflow — WCAG 1.4.10 · Confidence: 75%

**What it does**
Renders page at 320 px width, checks whether horizontal scroll is required.

**Why 75%**

| Issue | Severity | Impact |
|-------|----------|--------|
| 5 px scroll tolerance (`scrollWidth > viewportWidth + 5`) may miss rounding errors | Medium | Subpixel rendering in some browsers can give true 1–4 px false positives |
| Exempt-tag detection keyword list (codemirror, monaco, data-chart) is incomplete | Medium | Custom charting/code libraries not in the list flagged as violations |
| Reports max 5 overflowing elements even if 50 exist | Low | Underrepresents scope of issue |
| `exempt_only` returns `False` if no elements found — defaults to FAIL even when no specific element caused overflow | Low | Could flag page-level scroll caused by body margin/padding |

**False positive risk:** Low.
**False negative risk:** Low-Medium — custom exempt content not in keyword list.

**What to fix first**
Increase scroll tolerance to 10 px. Expand exempt keyword list. Log count of overflowing elements even when only 5 are shown.

---

### 8 · Text Spacing — WCAG 1.4.12 · Confidence: 63%

**What it does**
Injects WCAG text-spacing CSS overrides, compares before/after element snapshots, reports newly clipped text.

**Why 63%**

| Issue | Severity | Impact |
|-------|----------|--------|
| **Element matching uses `tag:text[:40]` fallback** — duplicate elements (100 "Learn More" links) match arbitrarily | High | Widespread false positives on list/nav pages |
| Skips elements with `len(text) < 3` | Medium | Short labels ("OK", "Go") never checked |
| Only detects `text_clipped` change; misses *vertical* overflow growth | Medium | Content pushing below the fold not detected |
| Reports only first 10 newly clipped elements | Low | Understates scope |
| `margin-bottom: 2em` applied universally, not per WCAG spec nuance | Low | May over-constrain what constitutes a violation |

**False positive risk:** Medium — fragile element matching.
**False negative risk:** Medium — short text and vertical overflow skipped.

**What to fix first**
Replace fallback key with a stable selector from `snapshot_collector.py` (already computed per element). Store `selector` alongside each `ElementSnapshot` and use it as the match key.

---

### 9 · Resize Text — WCAG 1.4.4 · Confidence: 65%

**What it does**
Applies 200% font-size via JavaScript, compares element snapshots before/after, reports clipped or newly-scrolling content.

**Why 65%**

| Issue | Severity | Impact |
|-------|----------|--------|
| **Same fragile element-matching issue as Text Spacing** | High | False positives on pages with repeated element text |
| Only flags *new* horizontal scroll; existing scroll treated as acceptable | Medium | Pages already requiring scroll won't be checked for worsening |
| Hidden elements in baseline not tracked | Medium | Elements revealed by font scaling not detected |
| `document.documentElement.style.fontSize = '200%'` vs browser zoom are not equivalent | Medium | WCAG 1.4.4 refers to browser text-zoom, not CSS override; some pages resist this method |

**False positive risk:** Medium.
**False negative risk:** Medium — existing scroll and revealed hidden elements missed.

**What to fix first**
Same selector-based element matching fix as Text Spacing. Also flag cases where existing scroll *increases significantly* after font-size override.

---

### 10 · Orientation — WCAG 1.3.4 · Confidence: 60%

**What it does**
Renders the page in portrait (390×844) and landscape (844×390), checks for rotate-device overlays, missing main content, and large interactive-element count disparity.

**Why 60%**

| Issue | Severity | Impact |
|-------|----------|--------|
| Rotate-overlay regex requires exact English phrases | High | "Rotate phone", "Please use landscape", "Turn device" → not detected |
| Interactive-element count ratio < 0.5 triggers NEEDS_REVIEW — most responsive menus fail this | High | Hamburger menu (10 items) vs expanded nav (50 items) → false flag |
| Missing-content heuristic requires 3 text elements > 20 chars in 8 specific tags | Medium | Image-heavy or dashboard pages consistently trigger false "missing content" |
| No check for `screen-orientation` JS lock or `<meta name="screen-orientation">` | Medium | Most common real-world orientation lock method not detected |

**False positive risk:** High — interactive-count ratio and missing-content heuristic over-fire on common responsive layouts.
**False negative risk:** High — orientation locks via JS API entirely missed.

**What to fix first**
Remove or significantly widen the interactive-count ratio check (use > 0.1 or remove it entirely). Add detection of `screen.orientation.lock()` calls and `<meta name="screen-orientation">`.

---

### 11 · Content on Hover or Focus — WCAG 1.4.13 · Confidence: 45%

**What it does**
Hovers over up to 20 candidate trigger elements, detects popups, tests Escape dismissibility, and tests pointer-can-move-over behaviour.

**Why 45%**

| Issue | Severity | Impact |
|-------|----------|--------|
| **Persistence (requirement 3) not tested at all** | Critical | One of three WCAG requirements completely unverified |
| Popup detected only via 4 narrow CSS selectors | High | Custom tooltip/popover implementations entirely missed |
| Mouse moves to `(cx, cy-60)` — assumes popup is above trigger | High | Popup below/beside trigger → movement causes dismissal → false FAIL |
| Escape dismissal does not verify focus didn't move | High | WCAG requires "without moving focus" — not tested |
| Candidate trigger selector limited to semantic attributes | High | Many hover effects triggered via CSS `:hover` only → no candidates found |
| Second popup vs. same popup not verified during hoverable test | Medium | A different popup appearing falsely PASSES the hoverable check |

**False positive risk:** High — hardcoded hover direction causes false failures.
**False negative risk:** Very High — most real-world hover implementations (CSS-only, custom JS) not detected.

**What to fix first**
This rule needs a fundamentally better detection strategy. As an interim: (1) Randomise movement direction (try all 4 directions and take the best result). (2) Expand candidate selector to include elements with CSS `:hover` that reveal `display:block` children. (3) Clearly mark all results as `needs_review`; never emit `fail` for this rule given automation limits.

---

### 12 · Focus Not Obscured (Minimum) — WCAG 2.4.11 · Confidence: 58%

**What it does**
Tabs through up to 100 focusable elements, collects bounding rects of `position:fixed/sticky` overlays, computes obscuration ratio.

**Why 58%**

| Issue | Severity | Impact |
|-------|----------|--------|
| Overlays collected **once before tabbing** — dynamic overlays (cookie banners appearing after scroll) missed | High | Main real-world scenario not covered |
| Only `position:fixed` or `position:sticky` overlays detected | High | `position:absolute` modals and z-index-stacked banners missed |
| Opacity not factored — a 5% opacity overlay scores 100% obscuration | Medium | Semi-transparent sticky header causing < 10% visual impact still triggers FAIL |
| 100 Tab-press limit — deep-page elements untested | Medium | Focus order issues in rich applications missed |
| 95% threshold for "entirely hidden" — 96% is functionally fully hidden | Low | Boundary is arguable vs. WCAG wording "not entirely hidden" |
| Overlays collected in desktop (1280×720) context only | Low | Sticky bars that only appear at certain scroll positions not captured |

**False positive risk:** Medium — opacity issue.
**False negative risk:** High — dynamic overlays and absolute-positioned modals missed.

**What to fix first**
Re-collect overlays after each Tab press (or at least every 10 steps). Add a `position:absolute` + high `z-index` check to the overlay query.

---

### 13 · Focus Not Obscured (Enhanced) — WCAG 2.4.12 · Confidence: 55%

**What it does**
Same focus scan as 2.4.11 but fails if obscuration ≥ 10% (any meaningful overlap).

**Why 55%**

All issues from 2.4.11 apply. The 10% threshold additionally raises the false-positive rate:

| Issue | Severity | Impact |
|-------|----------|--------|
| Anti-aliasing / subpixel rendering on focus ring can produce 2–4% measured overlap | Medium | Focus indicator edge bleeding under overlay → false FAIL |
| Border elements at viewport edge may overlap with sticky bar by a few pixels | Medium | Normal scroll-to-focus behaviour → false FAIL |
| 2.4.12 is technically **AAA** in WCAG 2.2, not AA — filter in `_WCAG_LEVEL` may mismatch | Low | Shown when `wcag_level = AA` even though it is AAA |

**What to fix first**
Fix the level metadata (`_WCAG_LEVEL["2.4.12"] = "AAA"`). Add a 5% grace margin below the 10% threshold to absorb subpixel errors (i.e., fail at ≥ 15%). Apply all 2.4.11 fixes first.

---

## Infrastructure confidence issues

These are not per-rule but affect multiple rules simultaneously.

### Snapshot element matching (affects 1.4.4, 1.4.12)

**Problem:** When diffing baseline vs. override snapshots, elements are matched by `selector` (ID-based) with fallback to `tag:text[:40]`. On pages where many elements share tag + similar text (navigation lists, card grids), the fallback causes cross-matches between unrelated elements.

**Fix:** Always compute and store a unique stable CSS selector per element in `snapshot_collector.py`. Use `nth-of-type` or DOM-path approach as fallback, never text-content.

---

### Single overlay collection in focus scan (affects 2.4.11, 2.4.12)

**Problem:** `_OVERLAY_JS` runs once before any Tab press. Cookie consent banners and other overlays that appear after user interaction are invisible to the test.

**Fix:** Move `_OVERLAY_JS` call inside the Tab loop, either on every step or every N steps.

---

### 500-element cap per snapshot (affects 1.4.4, 1.4.10, 1.4.12)

**Problem:** `_MAX_ELEMENTS = 500` in `snapshot_collector.py`. Large pages (e-commerce, news sites) have far more elements. The cap biases analysis toward DOM-first elements.

**Fix:** Increase cap to 2000, or prioritise text-bearing / interactive elements over generic divs by reordering the selector.

---

### Field name contract (affects all rules)

**Problem:** There is no schema validation between what crawlers produce and what converters in `findings.py` expect. A field rename anywhere silently drops all findings for that rule.

**Fix:** Add a Pydantic model or TypedDict for each crawler's output record. Assert field presence at converter entry.

---

### Fixed 2000 ms JavaScript wait (affects all crawlers)

**Problem:** All crawlers wait a hard 2 seconds after `domcontentloaded`. JS-heavy SPAs (React, Angular, Vue) may not finish rendering in this time.

**Fix:** Use Playwright's `wait_for_load_state("networkidle")` with a timeout as the primary wait strategy, with the 2 s floor as a fallback.

---

## Priority fix matrix

| Priority | Fix | Rules affected | Effort |
|----------|-----|----------------|--------|
| 🔴 P0 | Fix inverted UA-controlled exception in `target_size_crawler.py` | 2.5.8 | 5 min |
| 🔴 P0 | Fix `aria-describedby` to resolve ALL IDs (not just first) | 3.3.1, 3.3.2 | 30 min |
| 🔴 P0 | Fix `_WCAG_LEVEL["2.4.12"]` to `"AAA"` | 2.4.12 | 1 min |
| 🟠 P1 | Replace tag+text fallback with stable CSS selector matching | 1.4.4, 1.4.12 | 2 hrs |
| 🟠 P1 | Re-collect overlays each N Tab steps | 2.4.11, 2.4.12 | 1 hr |
| 🟠 P1 | Replace OCR substring matching with word-boundary regex | 1.1.1 | 30 min |
| 🟠 P1 | Add offset spacing exception to target size | 2.5.8 | 2 hrs |
| 🟡 P2 | Expand overlay detection to absolute+high-z-index elements | 2.4.11, 2.4.12 | 2 hrs |
| 🟡 P2 | Add `screen.orientation.lock()` detection to orientation | 1.3.4 | 1 hr |
| 🟡 P2 | Widen interactive-count ratio threshold or remove it | 1.3.4 | 30 min |
| 🟡 P2 | Add hover-direction randomisation; mark all as needs_review | 1.4.13 | 3 hrs |
| 🟡 P2 | Add visibility filter to forms and interactive crawlers | 3.3.1, 3.3.2, 2.5.3 | 1 hr |
| 🔵 P3 | Replace fixed 2000 ms wait with `networkidle` strategy | All crawlers | 2 hrs |
| 🔵 P3 | Raise 500-element cap; reprioritise element selector order | 1.4.4, 1.4.10, 1.4.12 | 1 hr |
| 🔵 P3 | Add Pydantic schema validation at converter entry | All rules | 4 hrs |
| 🔵 P3 | Add font-size context to contrast threshold selection | 1.4.3 | 2 hrs |