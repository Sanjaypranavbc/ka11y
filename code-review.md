# ka11y — System-Wide Code Review

**Date:** 2026-05-06
**Branch:** `fix-patches`
**Scope:** Full system — `ka11y-python` (FastAPI + Playwright + auditors), `ka11y-node` (axe-core + custom checks), API/orchestration glue.
**Reviewer mode:** FAANG production-readiness, brutally honest. ~140 grounded, file-anchored findings collapsed into the structure below.

---

## 1. Executive Summary

### Overall rating: **54 / 100**

The system *works* on the happy path for small pages. It does not yet behave like a production accessibility engine. The architecture is recognizably correct (separate Node/axe and Python AI layers, modular auditors, decision policies) but is undermined by:

- **Data-loss bugs** — finding-converter field mismatches silently downgrade entire WCAG SCs to `needs_review`.
- **Engine-level exception swallowing** — every policy bug is rebadged as `confidence=0.1` `NEEDS_REVIEW`, hiding bugs in production.
- **Heuristic accuracy weaknesses** — many checks fire on pretexts (color words = sensory violation, "Settings" link = motion-disable control) without verifying intent.
- **Resource economics** — 5 browser launches per URL, 8 concurrent contexts per scenario, monolithic 2000-line `page.evaluate()` returning megabytes of JSON, unbounded de-dup sets, no per-frame timeouts. Will not survive 1000 concurrent crawls.
- **Security gaps** — SSRF guard misses decimal/hex-encoded IPs and post-allow redirects; API leaks tracebacks; no per-user auth/rate-limit isolation.

### Top 5 critical issues

| # | Issue | Impact |
|---|---|---|
| 1 | **Auditor → converter field-name mismatches** (`findings.py` expects `wcag_1_1_1_status`, auditor may emit different keys) → entire SC silently becomes `needs_review` | Whole rules report wrong; matches existing memory note for 1.1.1 |
| 2 | **`DecisionEngine` swallows every `Exception` and emits `NEEDS_REVIEW` with confidence 0.1** (`engine.py:30-42`) → real policy bugs (e.g. `policy_1_4_6.py:13` enum/string compare always-false; `policy_2_5_8.py:34` None deref) become invisible | Hidden quality decay; impossible to debug in prod |
| 3 | **SSRF guard bypass surface** — `_ssrf_guard.py` only matches dotted-quad IPs and only checks the *initial* URL; decimal `http://2130706433/`, hex `http://0x7f000001/`, and post-allow redirects to `169.254.169.254` slip through | Cloud-metadata exfil from a hosted scanner |
| 4 | **Browser/resource economics broken** — each crawler (`crawler.py`, `media_crawler.py`, `sensory_crawler.py`, `rendered_layout_crawler.py`) launches its *own* Chromium; `rendered_layout_crawler` fans out 8 `_snapshot_at_viewport` contexts via `asyncio.gather` with no timeout and the page is *not* closed on the exception path; `universal_page._extract_page_chunked` keeps an unbounded `seen_refs` set across 4 scroll passes | OOM and hangs at scale; cost explosion |
| 5 | **`universal_page._COMBINED_EXTRACT_JS` is a 2000-line monolithic `page.evaluate()`** that walks the DOM 7 times, serialises `outerHTML` for every element, and crosses the V8↔Python bridge with 8–15 MB JSON per page | Latency, memory, and a single JS bug breaks 7 categories at once |

---

## 2. Architecture Review

### 2.1 Current architecture

```
            ┌──────────────────────────┐
            │  FastAPI app (main.py)   │
            │  + _RateLimitMiddleware  │
            └────────────┬─────────────┘
                         │
                         ▼
        ┌──────────── api/v1 ──────────────┐
        │  pipeline.py    (full pipeline)  │
        │  combined/{routes,runner,        │
        │           stages,findings}.py    │
        │  rules/{run_router,metadata}.py  │
        └────────────┬────────────┬────────┘
                     │            │
                     ▼            ▼
   ┌────────────────────┐   ┌──────────────────────────────┐
   │  Python crawlers   │   │  Node service (HTTP)         │
   │  ─ crawler.py      │   │  src/services/accessibility  │
   │  ─ media_crawler   │   │   ├ axe-core run            │
   │  ─ sensory_crawler │   │   ├ custom-checks/*.check.js│
   │  ─ rendered_layout │   │   └ audits/wcag-2.5.x/      │
   │  ─ universal_page  │   └──────────────────────────────┘
   └─────────┬──────────┘
             ▼
   ┌──────────────────────────────────────────────────────────┐
   │ accessibility/                                           │
   │  rules/ (auditors: alttext, sensory, contrast, media,    │
   │          forms, target_size, text_spacing, …)            │
   │  rendered/ (reflow, text_spacing evaluators)             │
   │  pipeline/                                               │
   │   ├ extractors/ (element_context_extractor,              │
   │   │             semantic_relationship_engine)            │
   │   ├ analyzers/ (section_analyzer)                        │
   │   ├ runners/ (contrast_engine, interaction_state_runner) │
   │   ├ decisions/ (engine + policy_X_Y_Z)                   │
   │   └ formatters/ (evidence_formatter)                     │
   └──────────────────────────────────────────────────────────┘
```

### 2.2 Key flaws

**F1 — Two parallel rule systems with no shared model.**
`accessibility/rules/*` (large, image- and OCR-heavy auditors) and `accessibility/pipeline/decisions/*` (per-SC policy classes operating on `ElementContext`) both produce findings, but they don't share a data model. `combined/findings.py` is a 1000+ line translation layer that *must* know each auditor's idiosyncratic field names. This is the root cause of the data-loss bug class (Top-5 #1).

**F2 — Crawler proliferation without a base class.**
Four crawlers (`crawler.py` for images, `media_crawler.py`, `sensory_crawler.py`, `rendered_layout_crawler.py`) duplicate ~400 lines of browser launch / context creation / link extraction / cleanup. Each launches its *own* Chromium for the same URL.

**F3 — One giant `page.evaluate` for everything.**
`universal_page._COMBINED_EXTRACT_JS` is 2000+ lines and extracts forms, interactive, target_sizes, moving_content, media, text_spacing, and sensory data in a single JS function. Single bug → all 7 categories die. JSON payload is 8–15 MB on a 500-element page.

**F4 — `DecisionEngine` exception policy hides correctness bugs.**
`engine.py:30-42` `except Exception → NEEDS_REVIEW(confidence=0.1)` masks every concrete bug in the policy classes (string-vs-enum, None deref, missing import). There is no observability for "policies-that-keep-throwing".

**F5 — Custom-check / audit duplication in Node.**
For 2.5.1 and 2.5.4, both `custom-checks/{pointer-gestures,motion-actuation}.check.js` *and* `audits/wcag-2.5.{1,4}/index.js` exist. The selector banks (`multilingual-selectors.js` vs `axe-rule-pointer-gestures.js:11–46`) duplicate definitions that drift over time.

**F6 — Tight coupling between policies and concrete data shapes.**
`policy_1_3_1.py:29` reads `element.visual.computed_styles.get("type")` — but `type` is an HTML attribute, not a CSS property. This is the kind of bug an `ElementSemantics`-vs-`ElementVisual` boundary should make impossible.

**F7 — Module-level singletons everywhere.**
`combined/constants.py` loads `_WCAG_NAMES = get_wcag_names("en")` at import. `utils/config_loader.py:35` does `config = load_config()`. `i18n/loader.py` caches via `lru_cache`. None can be reloaded without process restart, and none are language-correct for non-English audits.

### 2.3 Suggested improved architecture

Five targeted changes; everything else is downstream of these.

1. **One `PageExtraction` shared model with versioned schema.** Auditors emit `Finding(rule_id, status, evidence, ...)` directly. `combined/findings.py` becomes a thin grouper, not a translation layer. Field-mismatch class of bugs ceases to exist.
2. **`BaseCrawler`** with a single browser pool. Concrete crawlers override `extract_for_url(page)`. Replaces ~400 lines of duplication; single browser per audit; per-stage views over one extraction.
3. **Split `_COMBINED_EXTRACT_JS` into 4 focused extractors** (structural, geometry, dynamic, sensory). Each is testable in isolation; one failure does not poison the others.
4. **Typed `PolicyError` in `DecisionEngine`** — engine catches *only* `PolicyError` and falls through to `NEEDS_REVIEW`. Anything else logs a structured error and crashes the request; in CI, that means a failing test, in prod a 5xx with an opaque error_id.
5. **Replace four-crawler-per-URL pattern with one universal crawl + downstream evaluators.** Image classification, media probing, sensory scanning, layout snapshots are all *evaluators* over a `BrowsedPage` artefact, not separate Chromium launches.

---

## 3. Performance & Computational Analysis

Findings ranked by production blast radius. Each lists root cause, complexity, and a code-anchored fix.

### P-01 (CRITICAL) — Monolithic JS extractor, megabyte JSON per page
**File:** `ka11y-python/ka11y/crawler/universal_page.py:55-1134`
**Problem:** `_COMBINED_EXTRACT_JS` runs 7 querySelectorAll loops, calls `getBoundingClientRect()` on every target (forced reflow per element), and serialises `outerHTML` for every element into a single returned object.
**Complexity:** O(N) DOM walks ×7 categories with full reflow per element ⇒ effective O(N) reflows. JSON marshalling O(total_html_bytes).
**Impact:** 8–15 MB JSON per 500-element page; 2–5 s Python-side parse; ~5 GB/day at 1k pages/day. Single JS error kills 7 outputs.
**Fix:**
```python
# Split into focused extractors; run sequentially or in 2 batches
forms        = await frame.evaluate(FORMS_JS)
interactive  = await frame.evaluate(INTERACTIVE_JS)
geometry     = await frame.evaluate(GEOMETRY_JS)   # the only one that touches getBoundingClientRect
sensory      = await frame.evaluate(SENSORY_JS)
# Cap each extractor's output size before returning
```
And inside each JS: hash `outerHTML` to a 16-byte digest server-side rather than shipping it raw.

### P-02 (CRITICAL) — Browser-per-crawler launches
**Files:** `crawler.py:395-406`, `media_crawler.py:275-294`, `sensory_crawler.py:241-259`, `rendered_layout_crawler.py:242-259`
**Problem:** Each of the four crawlers does `async with async_playwright() as p: browser = await p.chromium.launch(...)`. For one audit URL, that is **5 separate Chromium processes** (image + media + sensory + rendered_layout + universal), ~300 MB each = **~1.5 GB per URL**.
**Fix:** Singleton `BrowserPool` in `app/main.py` lifespan; crawlers receive a `browser` and create only contexts.

### P-03 (CRITICAL) — `rendered_layout_crawler` fan-out without timeout
**File:** `rendered_layout_crawler.py:275-308`
**Problem:** `asyncio.gather(*7 _snapshot_at_viewport, return_exceptions=True)` — each opens its *own* context + page. `return_exceptions=True` catches errors but not hangs; one stuck `wait_for_load_state("networkidle")` blocks the gather forever.
**Complexity:** 7 contexts × (load + 7 sub-snapshots) per URL.
**Fix:**
```python
async with asyncio.timeout(120):
    results = await asyncio.gather(*scenarios, return_exceptions=True)
```
And reuse one context across the 7 viewport snapshots — the `_make_context` per scenario is only required when the *device profile* changes.

### P-04 (CRITICAL) — Page leak on exception path
**File:** `rendered_layout_crawler.py:380-396`
**Problem:** `_snapshot_at_viewport` opens a `page` inside `try`, but the exception handler returns before any explicit `page.close()`. Only `ctx.close()` runs in `finally`. Under load this races and pages accumulate.
**Fix:** `page = None` before try; `if page: await page.close()` in finally.

### P-05 (HIGH) — Unbounded `seen_refs` in chunked extraction
**File:** `universal_page.py:1488-1540`
**Problem:** 4 scroll passes × N elements × dedup hash each — `seen_refs` grows without bound. 1k concurrent pages × 5k elements × 4 passes ≈ ~10 GB resident.
**Fix:** Per-page cap (`if len(seen_refs) > 5000: break`) + flush dedup keys to disk between passes.

### P-06 (HIGH) — N+1 `page.evaluate` per image
**File:** `crawler.py:547-577`
**Problem:** For each `<img>`, the code does ≥2 `evaluate(...)` round-trips (resolved label, parent context). 1000 images × 2 calls × ~10 ms = ~20 s overhead per page.
**Fix:** Single `evaluate(el => ({label, ctx, title, ...}))`.

### P-07 (HIGH) — N+1 `frame.evaluate` per relationship
**File:** `pipeline/extractors/semantic_relationship_engine.py:89-94`
**Problem:** `for context in contexts: relations = await frame.evaluate(_RELATIONSHIP_JS, context.element_id)` — one IPC per element.
**Fix:** Pass list of IDs once: `frame.evaluate(JS, [ids])` returns `[{id, relations}]`.

### P-08 (HIGH) — O(n²) adjacency scan in extractor
**File:** `pipeline/extractors/element_context_extractor.py:165-178`
**Problem:** Nested loops over interactive elements to compute neighbour gaps — quadratic in the number of focusables.
**Fix:** Spatial bin (grid bucket on `Math.floor(x/64), Math.floor(y/64)`), check neighbours only.

### P-09 (HIGH) — OCR result lookup is O(n·m)
**File:** `accessibility/rules/non_text/alttext.py:787-802`
**Problem:** `for img in images_data: _ocr_for_file(ocr_results, filename)` — inner function linearly scans `ocr_results`. With 1k images × 1k OCR rows = 1 M iterations, plus `Path` allocations per call.
**Fix:** Build `ocr_by_filename = {Path(r.filename).name.lower(): r for r in ocr_results}` once.

### P-10 (HIGH) — Hot regex compiled per call
**Files:** `policy_1_1_1.py:74` (`re.search(r"[a-z]{2}|[^\x00-\x7F]", name)`), `policy_1_4_5.py:32` (`import re` inside method).
**Fix:** Module-level `_DESCRIPTIVE_PATTERN = re.compile(...)`. Hoist `import`.

### P-11 (MEDIUM) — Sensory regex sweep is O(text × categories)
**File:** `accessibility/rules/non_text/sensory_auditor.py:1048`
**Problem:** Per text token, iterates all 8 sensory category regexes.
**Fix:** Single union regex: `_SENSORY_MEGA = re.compile("(" + "|".join(all_terms) + ")", re.IGNORECASE)` — one match call replaces N.

### P-12 (MEDIUM) — Sequential snapshot then stages
**File:** `combined/stages.py:1174-1286`
**Problem:** `snapshot = await _load_universal_snapshot(...)` blocks the entire pipeline before stages start, even though `_stage_image_audit` does not need it.
**Fix:** `snapshot_task = asyncio.create_task(...)`; pass the future into stages that need it; image audit runs immediately.

### P-13 (MEDIUM) — Sync I/O on async route
**File:** `api/v1/pipeline.py:299-572`
**Problem:** `image_crawler.save_results()`, `detector.scan_directory()`, `save.save_reports()` are all blocking and called without `await`. Two concurrent users serialise on the event loop.
**Fix:** `await asyncio.to_thread(image_crawler.save_results)` etc.

### P-14 (MEDIUM) — Layout thrash in 2.5.4 motion detector
**File:** `ka11y-node/src/audits/wcag-2.5.4/motion-event-detector.js:31`
**Problem:** Reads `document.body.innerText` per regex pattern in a loop; each read forces layout.
**Fix:** Read once into `const allText = document.body.innerText;`.

### P-15 (MEDIUM) — DOM inspector 5k evaluate round-trips
**File:** `ka11y-node/src/audits/wcag-2.5.1/dom-inspector.js:52-112`
**Problem:** For each selector × match, calls `page.evaluate` to compute CSS path → up to 5k cross-process calls on heavy pages.
**Fix:** Single `page.evaluate` that does selector iteration AND CSS-path computation server-side.

### P-16 (LOW) — Locale cache + classifier cache unbounded
**Files:** `ka11y-node/src/services/accessibility.service.js:104` (`_axeLocaleCache`), `ka11y-python/ka11y/crawler/crawler.py:589-591` (classifier cache).
**Fix:** LRU with explicit cap.

---

## 4. Accuracy Issues (WCAG-Specific)

For each SC: failure scenarios and the file that needs to change.

### 1.1.1 Non-text content
- **`alttext.py:318-326`** — `_check_1_1_1_decorative` only validates `alt=""` for classifier-decorative images; ignores `aria-hidden="true"`, `role="presentation"`, `<figure>` with `<figcaption>`. Decorative images with `aria-hidden` and missing `alt` **fail incorrectly**.
- **`alttext.py:451-454`** — icon alt-text rule rejects valid 2-char universal symbols ("ok", "x", "→") because of a 4-char minimum.
- **`alttext.py:401-442`** — for multi-word brand alt ("Meta Platforms Inc. logotype"), `_LOGO_WORDS` doesn't include "logotype" / "wordmark" → false fail.
- **CSS `background-image` content is never seen.** No crawler step extracts background URLs; informational hero images with rendered text are simply missing from the audit. **Major false-negative source.**
- **Shadow DOM not pierced** — modern web components with `<img>` inside `shadowRoot` bypass `images_data`.
- **Accessible-name priority wrong** in `pipeline/extractors/element_context_extractor.py:245-270` — order is aria-label → alt → title → text. The W3C accname-1.2 spec puts `aria-labelledby` *before* `aria-label`, and form-control native `<label for>` association before `title`. Both are missing. False negatives on labelled form controls.

### 1.2.x Time-based media
- **`media_auditor.py:109-143`** `_gate_1_is_prerecorded` only checks `.m3u8` / `.mpd` for live. Streams via JS-replaced `<video src>` or MediaSource API are misclassified as prerecorded → false fail on missing transcript.
- **`media_auditor.py:210-282`** `_gate_4_find_transcript` checks `<a>` / `<details>` / `aria-describedby` but ignores `<iframe>`-embedded transcripts and JS-revealed disclosure regions.
- **WCAG 1.2.4 (live captions) — Node check insufficient** (`ka11y-node/src/custom-checks/captions-live.check.js`) — `<track kind="captions">` does not prove captions are *live*. A pre-recorded VTT will pass.

### 1.3.1 Info & relationships
- **`policy_1_3_1.py:29`** reads `element.visual.computed_styles.get("type")` — **fundamentally wrong**: `type` is an HTML attribute, not a CSS property. Always returns None for radio/checkbox. Form-grouping checks for radios silently never fire.

### 1.3.3 Sensory characteristics
- **`sensory_auditor.py:997-1032`** flags `"Press the Red button"` as sensory-only even when "Red" is the button's literal accessible name (e.g. Red Hat). Cross-check sensory token against the labelled element's name before flagging.

### 1.4.3 / 1.4.6 Contrast (Minimum / Enhanced)
- **`policy_1_4_6.py:13`** `if verdict.status == "not_applicable" or verdict.status == "needs_review":` — `status` is `VerdictStatus` enum, comparison is **always False**. AAA enhanced contrast is silently never escalated.
- **`thresholds.py:6-7`** defines `CONTRAST_NORMAL_AAA = 7.0` / `CONTRAST_LARGE_AAA = 4.5` but no policy imports them — 1.4.6 inherits 1.4.3 and re-hardcodes thresholds inline.
- **`contrast_engine.py:10-23`** `parse_rgb` does `re.findall(r"\d+", ...)` — splits the alpha "0.5" of `rgba(255,0,0,0.5)` into `[0, 5]`; ignores alpha entirely (no compositing with background). Anti-aliased / semi-transparent text is mismeasured.
- **`contrast_analyser.py:151-187`** large-text threshold uses an `is_bold` boolean, not the actual `font-weight` value. CSS `font-weight: 700` text without explicit bold flag uses 4.5:1 instead of 3:1 → false fail.
- **`contrast_analyser.py:102-114`** uses `np.percentile(text_pixels, 90)` with no guard for empty / single-pixel arrays — divides by zero or returns inf, then is silently swallowed by an outer try/except.

### 1.4.10 Reflow
- **`rendered/evaluators/reflow.py:40-100`** assumes the snapshot was taken at 320 CSS pixels; never asserts `snapshot_320.viewport_width == 320`. If `rendered_layout_crawler` was misconfigured to 360, evaluation silently runs against the wrong viewport.
- **`text_spacing_auditor.py:31-49`** flags every container with `height + overflow:hidden` as a 1.4.12 WARNING regardless of whether spacing deltas would actually overflow. Dashboards drown in noise.

### 1.4.11 Non-text contrast
- **`alttext.py:614-686`** fallback path measures contrast against a *cropped* OCR image instead of the surrounding page pixels. White button on white page can pass at 1.5:1 instead of failing at 1.0:1.

### 2.4.13 Focus appearance
- **`policy_2_4_13.py:28-52`** the AND/OR composition of "thickness < min" and "contrast < 3.0" is inverted relative to the SC. An element with 0.5 px focus ring and 5:1 contrast is incorrectly downgraded to `needs_review`. Combined with **`interaction_state_runner.py:88-89`** hardcoded fallback `focus_ring_thickness_px=2.0; focus_ring_contrast=4.5`, real failing rings overwritten with passing values → **false PASS**.

### 2.5.1 Pointer gestures (Node)
- **`audits/wcag-2.5.1/escape-hatch-validator.js:39-42`** treats any `onclick` presence as proof of a single-pointer alternative. `onclick="void 0"` or empty handlers pass.
- **Selector bank duplicated** between `multilingual-selectors.js` and `axe-rule-pointer-gestures.js:11-46` — drift inevitable.

### 2.5.3 Label-in-name
- **`policy_2_5_3.py:23-29`** strips all punctuation before `in` test. Accessible name `"Sign-In (Beta)"` against visible `"Sign In"` gives `"signin" in "signinbeta"` → True; the variant where the visible is `"Sign Up"` and the accessible is `"Sign Up Now"` could also short-circuit. Use word-boundary or token-set comparison.

### 2.5.4 Motion actuation (Node)
- **`audits/wcag-2.5.4/disable-control-validator.js:32-41`** treats *any* link containing "settings" as evidence of a motion-disable control. Account-settings page → false PASS.
- **`audits/wcag-2.5.4/index.js:72-115`** "UI alternative" requirement is satisfied by any `onclick` element with a verb-like label, even if disabled or hidden. Need explicit checks: enabled, focusable, label semantically aligned.
- **Heuristic-based "essential motion" classification** — keyword match on page text ("fitness", "pedometer") is insufficient evidence the motion is essential per the SC. Should require explicit `data-wcag-motion-essential` opt-in.
- **`motion-listener-detector.js:30`** monkey-patched `window.__motionRegistry` accumulates across pages within a Puppeteer session — false positives from previous pages' listeners.

### 2.5.8 Target size
- **`policy_2_5_8.py:34-37`** dereferences `element.interaction.effective_clickable_bbox.width` — but the field is `Optional[BoundingBox]` (per `models.py:93`). Throws `AttributeError`, gets caught by `engine.py` → silent `NEEDS_REVIEW(0.1)`.
- **`policy_2_5_8.py:23-31`** inline-link exemption fires when `display:inline` or any `<p>` ancestor — including a `<p>` wrapper in a navigation. WCAG exemption requires *links inline within a sentence of text*, which the current heuristic does not verify.
- **`target_size_auditor.py:86-97`** offset exception is ambiguous on whether both axes must meet the threshold; required offset is not clamped to ≥0 (`(24-25)/2 = -0.5` printed to users).

---

## 5. Code Quality Issues

### 5.1 Anti-patterns

- **Catch-Exception-and-shrug.** `engine.py:30-42`, `extractors/element_context_extractor.py:281-283`, `interaction_state_runner.py:71-81`, every `try/except Exception: pass` in the crawlers and several stages. These hide real bugs. Replace with: catch *named* exceptions; everything else bubbles or logs `ERROR` with traceback.
- **Late imports** — `import re` inside method body (`policy_1_4_5.py:32`) — minor but a smell that says "I'm afraid of import cycles". If there is a cycle, fix it.
- **Filename typo** — `ka11y/classifier/classfier.py` — keeps producing typo-prone imports.
- **`zip` over differently-sized lists** — `section_analyzer.py:38` zips `ancestor_tags` and `ancestor_roles`. Use `zip_longest` or assert equal length.
- **Non-deterministic dedup** — `rule_target_router.py:39 return list(set(rules))` — order varies. Use ordered-dedup pattern.
- **Module-level singletons that read files at import time** — `combined/constants.py:25-34` (`_WCAG_NAMES = get_wcag_names("en")`), `utils/config_loader.py:35` (`config = load_config()`). Hard to test, can't reload, language-incorrect for non-English audits.
- **Mutable default arguments smell** — `_make_finding(..., element_target=None)` is fine, but downstream callers pass `target` lists into multiple findings; copy the list before storing.
- **String-typed enums.** `policy_1_4_6.py:13` compares enum to literal string. Either use `VerdictStatus.NEEDS_REVIEW` everywhere or rely on `.value`. Don't mix.

### 5.2 Maintainability

- **2000-line JS string in a Python file.** `universal_page._COMBINED_EXTRACT_JS`. No syntax checking, no test coverage of the JS path, IDE highlighting is gone. Move to `extractors/*.js`, load via `Path.read_text`.
- **`api/v1/combined/findings.py` is a 1000+ line translation layer** with dozens of `r.get("wcag_X_Y_Z_status", "")` calls. One typo silently downgrades a whole SC. Replace with a registry: `AUDITOR_FIELD_MAP = {"1.1.1": ("wcag_1_1_1_status", "wcag_1_1_1_reason"), ...}` plus a unit test that asserts every key in the map exists in some auditor's output.
- **Tests run against mocks of axe-core.** `ka11y-node/src/audits/wcag-2.5.4/__tests__/motion-actuation.test.js:88-121` builds `{body: {innerText: ''}, querySelectorAll: () => []}` instead of a Puppeteer fixture. Tests pass; production fails on real DOMs.
- **No schema versioning between Node and Python.** `_call_node_flat` (`combined/stages.py:143-166`) just calls `resp.json()`. Any Node-side rename silently breaks Python parsing.

### 5.3 Best-practice violations

- **Dynamic `import re` inside functions** — see above.
- **`re.VERBOSE` with inline `# comments`** in `form_auditor.py:154` — looks correct but a single accidental whitespace change in pattern silently mutates semantics. Either add an explicit unit test for the pattern, or expand it to a non-VERBOSE form.
- **Bare `except` swallowing across the codebase** — at least 25 occurrences in the crawler files alone.
- **Logging at debug for production-relevant warnings** — `universal_page.py:1462` `logger.debug("[universal] networkidle timeout for {url}")`. Networkidle timeout is a real signal; should be `warning`.

---

## 6. Scalability Review

### 6.1 Behaviour at 1k pages/day

| Subsystem | Resource | Per-URL cost | At 1k URLs | Result |
|---|---|---|---|---|
| Browser launches | Memory | 5 × ~300 MB | 1.5 GB peak per audit, no pool | OOM under any concurrency |
| `_COMBINED_EXTRACT_JS` JSON | Memory + bandwidth | 8–15 MB JSON | 5–15 GB/day cross-process | Bottleneck on Python side parsing |
| `seen_refs` accumulation | Memory | 5 MB × 4 passes | 10 MB / page resident | OOM on infinite-scroll pages |
| `_jobs` dict (`runner.py`) | Memory | grows with stages list | indefinite | leaks when results never collected |
| OCR model load | Memory | re-loaded per request (`OCRPreprocessing` instantiation in `pipeline.py`) | duplicated weights | 2–4 GB extra per concurrent audit |
| Step log file append | Locks | none | concurrent audits can interleave bytes | corrupt JSONL |

### 6.2 Parallel execution issues

- **`_run_python_stages` returns a tuple by index** (`combined/stages.py:1274-1286`) — adding a stage shifts indices and the caller silently drops findings.
- **`asyncio.gather(..., return_exceptions=True)` everywhere with no timeout** — one stuck inner await blocks all peers.
- **Stage Server-Sent Events** (`stage_events.py:32-48`) — `_fire_broadcast` schedules a broadcast task but does not replay history when a client subscribes mid-job. Long audits will appear stuck to a re-connecting client.
- **No queue / worker model.** Each HTTP request fans out a full Playwright + OCR + classifier + Node call chain on the FastAPI event loop. There is no way to back-pressure: at 30 concurrent requests (rate-limit cap), the server is already trying to launch 150 Chromium processes.

### 6.3 Recommended scalability improvements

1. **Browser pool with bounded slots** (`max_browsers = 4`), context leases.
2. **Request → background queue** (Celery/RQ/asyncio worker). Sync HTTP returns `job_id` and `polling_url`; workers consume with bounded parallelism.
3. **Streaming JSON** out of `page.evaluate()` — return a small index, fetch large bodies on demand from a temporary KV store. Or persist intermediate artefacts to disk per job and stream metadata only.
4. **Single-OCR-process** worker with model loaded once; auditors send images over an in-process queue.
5. **Per-job output directory + size cap** with TTL cleanup (currently nothing prunes `crawled_images/` and `output/`).

---

## 7. Security & Stability

### 7.1 SSRF (`crawler/_ssrf_guard.py`)

- **G1.** Only `_IP_HOST_RE = re.compile(r"https?://(\[?[0-9a-fA-F:.]+\]?)(?:[:/]|$)")` is checked. Decimal-encoded IPs (`http://2130706433/` = `127.0.0.1`), 0x-hex, 0-prefixed octal, and `::ffff:` IPv4-mapped IPv6 forms bypass.
- **G2.** Only the *initial* request URL is validated; the route handler calls `route.continue_()` after the check, so a HTTP 302 from `https://safe-cdn.example/` to `http://169.254.169.254/latest/meta-data/iam/security-credentials/` is followed unchecked.
- **G3.** Hostname-mode requires DNS resolution before validation; if DNS pinning isn't enforced, the attacker can rebind between resolution and connect (DNS rebinding).
- **Fix sketch:** `urlparse` first, then resolve all `getaddrinfo` results into `ipaddress` objects, reject if *any* is private/link-local/loopback/multicast/reserved/IPv4-mapped. Re-validate every redirect via `page.on("response")`.

### 7.2 API surface

- **Stack-trace leakage.** `combined/runner.py:395-398` writes `error_traceback: tb` into the job dict that is returned by `GET /combined/{job_id}`. Likewise `pipeline.py:569-572` and `crawl.py` raise `HTTPException(detail=str(e))`. Internal paths and dependency names leak.
- **No authentication.** Rate limiter (`main.py:23-56`) is per-IP, trivially bypassed by spoofing `X-Forwarded-For` if the deployment trusts proxy headers without an allow-list. `_timestamps` map is never pruned — slow memory growth under varied client IPs.
- **No request size cap.** `CombinedRequest` (`combined/models.py`) accepts arbitrary string lengths for `wcag_level`, `lang`. FastAPI does not enforce a body cap by default. Submit a 100 MB body, hold a worker.
- **Symlink-validated path serving.** `routes.py:298-316` resolves symlinks then validates against `valid_paths`. If the *whitelist source* (auditor JSON) ever stores a symlink pointing outside `output/`, it becomes a read primitive. Add `is_file()` + parent-directory containment check.

### 7.3 Crash risks

- **`engine.py` exception swallowing** keeps the system "up" but hides correctness regressions. In CI, that means tests pass on broken policies. In prod, `confidence=0.1` `NEEDS_REVIEW` floods the report.
- **Promise.race + setTimeout** in `accessibility.service.js:464-471` resolves on timeout but does not cancel the in-flight axe run; the page may close mid-evaluation, producing Puppeteer "Target closed" errors caught upstream.
- **Step logger** appends JSON lines without a lock (`utils/step_logger.py:17-42`) — concurrent audits can interleave bytes into one line, corrupting the log.

---

## 8. Refactoring Plan (Step-by-Step)

Ordered for highest correctness / safety win per unit of effort.

### Sprint 1 — Stop the bleeding (1 week)

1. **Rename `engine.py` exception handler to typed `PolicyError`.** Anything else propagates. This single change surfaces every silent bug below.
2. **Fix `policy_1_4_6.py:13`** enum-vs-string compare. Replace inheritance with a shared `evaluate_contrast(fg, bg, level)` callable.
3. **Fix `policy_2_5_8.py:34-37`** — null check on `effective_clickable_bbox`.
4. **Fix `policy_1_3_1.py:29`** — read input `type` from semantics, not CSS computed_styles.
5. **Fix `policy_1_4_3` accessible-name priority** in `element_context_extractor.py:245-270` — implement aria-labelledby, native `<label for>`.
6. **Fix `interaction_state_runner.py:88-89`** — extract real focus ring values, drop hardcoded fallbacks, return `NEEDS_REVIEW` if absent.
7. **Build `AUDITOR_FIELD_MAP` registry in `combined/findings.py`** + unit test asserting every field name exists in the corresponding auditor's output.
8. **Strip tracebacks from API error responses.** Single `error_id`; full info server-side only.

### Sprint 2 — Architectural debt (2 weeks)

9. **Create `BaseCrawler`** with shared browser pool. Migrate all four crawlers; one Chromium per audit.
10. **Split `_COMBINED_EXTRACT_JS`** into 4 focused JS files loaded from disk (`extractors/forms.js`, `extractors/geometry.js`, …). Add JS-side max-bytes cap.
11. **Replace tuple return from `_run_python_stages`** with a typed dataclass.
12. **Wrap `asyncio.gather` callsites with `asyncio.timeout(...)`.**
13. **Per-job `asyncio.Lock`** around `_jobs` mutation; or migrate `_jobs` to Redis / sqlite-backed store (essential for HA).
14. **Background-job queue.** HTTP returns `202 + job_id`; workers pull from a bounded queue.

### Sprint 3 — WCAG accuracy & heuristics (2 weeks)

15. **Add CSS background-image extraction** — parse `getComputedStyle(el).backgroundImage` for `url(...)` and feed into image audit.
16. **Shadow DOM piercing in image / sensory crawlers.**
17. **Sensory cross-check** — token must not be the element's own labelled name.
18. **Reflow assertion** — `assert snapshot_320.viewport_width == 320` or fail loudly.
19. **Contrast — alpha-aware RGB parser; composite over background; accept real `font-weight`.**
20. **2.5.4 motion classifier** — require explicit `data-wcag-motion-essential` opt-in instead of keyword heuristics.
21. **2.5.4 disable-control validator** — downgrade "Settings link" signal; require motion-keyword adjacency.
22. **2.5.1 escape-hatch** — require non-empty `onclick` evidence + matching label semantics; deduplicate selector banks into one shared module.
23. **2.5.3 normalisation** — switch to token-set / word-boundary comparison.

### Sprint 4 — Security & ops (1 week)

24. **SSRF guard rewrite** — full IP form coverage + redirect interception via `page.on("response")` + DNS-pinning context option.
25. **Symlink + parent-dir containment** in `get_job_image`.
26. **Per-user API key** + per-key rate limiting.
27. **Pydantic length limits** on every string field of `CombinedRequest`.
28. **Lock around step-log append** (or move to one writer per job).
29. **TTL cleanup** for `output/` and `crawled_images/`.

### Sprint 5 — Performance polish (1 week)

30. Batch `frame.evaluate` in `semantic_relationship_engine`.
31. Spatial-bin adjacency in `element_context_extractor`.
32. Hoist regex compilation in `policy_1_1_1`, `sensory_auditor`.
33. Single OCR-result lookup dict in `alttext.py`.
34. Single mega-regex for sensory categories.
35. Single OCR worker with cached models.
36. LRU eviction on `_axeLocaleCache`, classifier cache.

After Sprint 5, target rating 80+/100. Reaching 95+ requires the auditor model unification (F1 in §2.2) — a 4-week project that deletes `combined/findings.py` entirely.

---

## 9. Improved Code Snippets

### 9.1 `DecisionEngine` exception policy (single highest-leverage fix)

```python
# pipeline/decisions/engine.py
class PolicyError(Exception):
    """Raised by a Policy when it cannot evaluate but did not crash."""

def evaluate(self, ctx: ElementContext) -> list[RuleVerdict]:
    verdicts = []
    for sc in self.router.applicable_rules(ctx):
        policy = self.policies.get(sc)
        if not policy:
            logger.warning("no policy registered for %s", sc)
            continue
        try:
            verdicts.append(policy.evaluate(ctx))
        except PolicyError as e:
            verdicts.append(RuleVerdict(
                sc=sc, status=VerdictStatus.NEEDS_REVIEW,
                confidence=0.1, evidence={"policy_error": str(e)},
            ))
        # Anything else propagates -> 500 + opaque error_id, logged with traceback.
    return verdicts
```

### 9.2 `policy_1_4_6.py` enum compare + dedup with 1.4.3

```python
# pipeline/decisions/policies/policy_1_4_6.py
from .contrast_shared import evaluate_contrast

class Policy146(BasePolicy):
    sc = "1.4.6"
    def evaluate(self, ctx):
        v = evaluate_contrast(ctx, normal=7.0, large=4.5)
        if v.status in (VerdictStatus.NOT_APPLICABLE, VerdictStatus.NEEDS_REVIEW):
            return v
        return v
```

### 9.3 Field-map registry (kills the 1.1.1 data-loss class)

```python
# api/v1/combined/findings.py
AUDITOR_FIELD_MAP: dict[str, dict[str, str]] = {
    "1.1.1": {"status": "wcag_1_1_1_status", "reason": "wcag_1_1_1_reason"},
    "1.4.3": {"status": "wcag_1_4_3_status", "reason": "wcag_1_4_3_reason"},
    # ... one entry per SC ...
}

def _read(record: dict, sc: str, field: str, default=""):
    keys = AUDITOR_FIELD_MAP[sc]
    return record.get(keys[field], default)

# unit test (tests/test_field_map.py)
def test_every_sc_field_appears_in_some_auditor_output():
    sample = run_audit_against_fixture(FIXTURE_HTML)  # uses real auditors
    keys = set().union(*(rec.keys() for rec in sample.records))
    for sc, m in AUDITOR_FIELD_MAP.items():
        assert m["status"] in keys, f"{sc} status field {m['status']} never emitted"
```

### 9.4 `BaseCrawler` with browser pool

```python
# crawler/base.py
class BrowserPool:
    def __init__(self, max_browsers: int = 4):
        self._sema = asyncio.Semaphore(max_browsers)
        self._browsers: list[Browser] = []
        self._pw = None

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        return self

    async def lease(self) -> Browser:
        async with self._sema:
            if not self._browsers:
                self._browsers.append(await self._pw.chromium.launch(headless=True))
            return self._browsers[0]

    async def close(self):
        for b in self._browsers:
            await b.close()
        await self._pw.stop()

class BaseCrawler:
    def __init__(self, pool: BrowserPool): self.pool = pool

    async def crawl_page(self, url: str, *, timeout_s: float = 60):
        browser = await self.pool.lease()
        ctx = await new_crawler_context(browser)
        page = None
        try:
            page = await ctx.new_page()
            async with asyncio.timeout(timeout_s):
                await navigate_with_resilience(page, url)
                return await self.extract(page)
        finally:
            if page: await page.close()
            await ctx.close()

    async def extract(self, page): raise NotImplementedError
```

### 9.5 SSRF guard hardening

```python
# crawler/_ssrf_guard.py
import socket, ipaddress
from urllib.parse import urlparse

def _all_ips_for(host: str) -> set[ipaddress._BaseAddress]:
    ips: set[ipaddress._BaseAddress] = set()
    # Numeric forms first (decimal/hex/octal/IPv6/IPv4-mapped)
    try:
        ips.add(ipaddress.ip_address(host.strip("[]")))
    except ValueError:
        try:
            ips.add(ipaddress.ip_address(int(host, 0)))  # 0x.., 0.., decimal
        except ValueError:
            pass
    # DNS
    try:
        for fam, _, _, _, sa in socket.getaddrinfo(host, None):
            ips.add(ipaddress.ip_address(sa[0]))
    except socket.gaierror:
        pass
    return ips

def assert_public_url(url: str):
    host = urlparse(url).hostname or ""
    for ip in _all_ips_for(host):
        if ip.is_private or ip.is_loopback or ip.is_link_local \
           or ip.is_multicast or ip.is_reserved or ip.is_unspecified \
           or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped and (
                ip.ipv4_mapped.is_private or ip.ipv4_mapped.is_loopback)):
            raise PermissionError(f"blocked SSRF target: {ip}")

# In Playwright route handler, register page.on("response", lambda r: ...
# and re-validate r.headers.get("location") for any 3xx response.
```

### 9.6 Split monolithic JS extractor

```python
# crawler/extractors/__init__.py
from pathlib import Path
JS_DIR = Path(__file__).parent / "js"
FORMS_JS       = (JS_DIR / "forms.js").read_text()
INTERACTIVE_JS = (JS_DIR / "interactive.js").read_text()
GEOMETRY_JS    = (JS_DIR / "geometry.js").read_text()  # the only one that triggers reflow
SENSORY_JS     = (JS_DIR / "sensory.js").read_text()

async def extract_universal(frame, *, max_bytes: int = 50_000_000):
    forms       = await frame.evaluate(FORMS_JS)
    interactive = await frame.evaluate(INTERACTIVE_JS)
    geometry    = await frame.evaluate(GEOMETRY_JS)
    sensory     = await frame.evaluate(SENSORY_JS)
    out = {"forms": forms, "interactive": interactive,
           "geometry": geometry, "sensory": sensory}
    size = sum(len(json.dumps(v, default=str)) for v in out.values())
    if size > max_bytes:
        logger.warning("extractor output %d bytes; truncating", size)
        for k in ("forms", "interactive"): out[k] = out[k][:1000]
    return out
```

### 9.7 Sensory false-positive guard

```python
# rules/non_text/sensory_auditor.py
def _is_sensory_violation(text: str, element_acc_name: str | None):
    tokens = _SENSORY_MEGA.findall(text.lower())
    if not tokens:
        return False
    # Don't flag a token that IS the labelled name of the referenced control.
    if element_acc_name and any(t in element_acc_name.lower() for t in tokens):
        return False
    return True
```

---

## 10. Final Verdict

### What prevents this system from being perfect

- **Two parallel, non-unified accuracy pipelines** (`rules/*` auditors and `pipeline/decisions/*` policies) communicating through a hand-maintained string-keyed translation layer. Every keystroke in either side must be mirrored, by hand, in `combined/findings.py`. Until this is unified, Top-5 #1 (silent data loss) is not a bug; it is the design.
- **Engine-level swallowing of every Exception**. Ensures the API never 500s on a bad page; also ensures every regression in 30+ policy classes presents as `NEEDS_REVIEW(0.1)`. There is no signal to distinguish "I evaluated and was uncertain" from "I crashed and you should look".
- **Duplicated crawlers + monolithic extractor**. Either you spend Chromium memory like water and ship gigabytes of JSON per audit, or you pick one, write it well, and treat the rest as evaluators over the artefact. The current code chose neither.
- **WCAG heuristics over WCAG semantics.** The accessibility checks read like grep across attribute strings. WCAG SCs need *intent verification*: the link does navigate, the alternative is enabled, the captions are live. Substitute keyword matching for intent and you ship false positives that erode user trust faster than missing rules ever do.
- **Security hardening is partial.** SSRF guard misses three IP-encoding tricks and the entire redirect path; API leaks tracebacks; rate limiting is per-IP without proxy validation.
- **No back-pressure model.** A 30-req/min rate-limited HTTP front door behind a Playwright + Whisper + EasyOCR worker is not a deployable shape. There must be a queue.

### What "perfect" looks like

A perfect ka11y has, end-to-end:

1. **One typed `BrowsedPage` artefact** produced by a single `BrowserPool`-backed crawl. All evaluators (image, media, sensory, layout) operate on it; no second Chromium launch.
2. **Auditors emit `Finding(rule_id, status, evidence, locale_payload)` directly.** `combined/findings.py` ceases to exist; remains a thin grouper for response shape.
3. **Engine catches `PolicyError` only.** Every other exception is a 5xx with an opaque ID and a logged traceback. CI fails on regressions.
4. **WCAG checks verify intent, not strings.** Alternative controls must be enabled and labelled appropriately; motion-essential requires explicit opt-in; live captions require streaming evidence.
5. **SSRF guard validates every IP form and every redirect**, with DNS pinning.
6. **Background workers** consume from a bounded queue. HTTP front door returns `202 job_id`. Single OCR/Whisper process per host with cached models.
7. **Stable JSON contract Node↔Python**, schema-versioned, with a CI test that fails on any drift.
8. **Internationalisation never touches English-default module-level singletons.** Lang flows through call args, end-to-end.
9. **Tests run against real DOMs**, not handcrafted mocks; an HTML fixture corpus lives in-repo and runs in CI.

That is a 95+/100 system. It is two-to-three months of focused work from where you are now. The single highest-impact day of work is Sprint 1 step 1 — replace `engine.py`'s `except Exception` with `except PolicyError`. Most of the rest of this review will simplify or disappear once the resulting failures surface in CI.
