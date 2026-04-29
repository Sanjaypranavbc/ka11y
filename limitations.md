# ka11y — Audit Limitations Report (Actual vs Audited)

**Generated:** 2026-04-26 · **Engines:** ka11y-python (FastAPI + Playwright + OCR + spaCy/SudachiPy) and ka11y-node (axe-core 4.x + 31 custom Playwright/static checks).
**Method:** ran the combined audit endpoint with `wcag_level: AAA`, `max_depth: 0`, all stages enabled, against two real-world public sites (one EN, one JA). Each finding category in the report was then cross-checked against a fresh static-HTML snapshot of the page (image counts, lang attr, landmarks, forms, headings, etc.) to surface what the audit caught, missed, or over-flagged.

The aim is **not** a WCAG conformance verdict on the target sites — it is a candid map of where ka11y's automated detection ends and human review must begin, per rule and per crawler.

---

## 1. Test targets

| Target | URL | Lang | Why picked |
|--------|-----|------|------------|
| **EN — Smashing Magazine** | https://www.smashingmagazine.com/ | `en` (unquoted) | Real-world long-form publication; mostly text + small thumbnail set; minimal forms; no media. Tests rules in low-noise conditions. |
| **JA — Kyoto Shimbun (京都新聞)** | https://www.kyoto-np.co.jp/ | `ja` | Japanese-language news site; image-heavy thumbnail grid (functional + informative), single search form, autoplay slider. Stresses JA NLP rules, OCR on JP text, and target-size on small thumbs. |

Picked deliberately over the canonical demo sites (BBC, W3C, gov.uk, MDN) — those are over-tested and don't surface real failure modes. Each target was hit with `max_depth: 0` so the audit is bounded to a single page per run.

### 1.1 Top-level audit summary

| Metric | EN (Smashing) | JA (Kyoto Shimbun) |
|--------|--------------:|-------------------:|
| Total findings | 3,320 | 6,736 |
| Violations | 299 | 204 |
| Needs review | 525 | 733 |
| Passes | 2,496 | 5,799 |
| Critical / High / Medium / Low | 3 / 421 / 29 / 16 | 27 / 436 / 27 / 3 |
| Stages with `warnings[]` | 0 | 0 |
| `image_audit_report` images | 36 (22 P / 14 F) | 73 (42 P / 31 F) |
| OCR `contrast_report` regions | 15 (13.3% pass) | 12 (83.3% pass) |
| axe / python / custom split (fail+nr+pass) | 1,732 / 1,551 / 37 | 3,483 / 3,253 / 0 |

> **Note on JA `custom=0`:** the Node custom checks ran (axe completed) but the report shows `by_source` only contains `axe` + `python` for Kyoto. The Node service was healthy; this is a JA-specific result of every custom check passing or producing zero applicable elements on a Japanese news site with very few interactive widgets — see §3.

---

## 2. Actual-vs-audited ground truth (both sites)

The static HTML for each target was downloaded with `curl` and parsed with regex/AST counts to build a *site reality* baseline. The comparison below is "what's on the page" vs "what the audit reported".

| Signal | EN actual | EN audited (P/NR/F) | JA actual | JA audited (P/NR/F) |
|--------|----------:|--------------------:|----------:|--------------------:|
| `<html lang>` | `en` (unquoted) | `html-has-lang` axe pass=1 | `ja` (quoted) | `html-has-lang` axe pass=1 |
| `<img>` total | 26 (all `alt=`) | 87 / 0 / 3 (1.1.1 across image-alt + python_1_1_1_alt) | 99 (20 empty alt) | 304 / 0 / 23 (1.1.1) |
| `<svg>` | 2 | `svg-img-alt` pass=1 (1) | 0 | not tested |
| `<video>` / `<audio>` / `<iframe>` | 0 / 0 / 0 | media stage pass=1 (synthetic) | 0 / 0 / 1 | media + frame-title-unique nr=4 |
| `<form>` / `<input>` / `<label>` | 2 / 5 / 1 | 3.3.1 pass=3, 3.3.2 fail=2 pass=1 | 1 / 1 / 0 | 3.3.x not emitted |
| `<button>` | 1 | 4.1.2 pass=33 fail=3 (mostly axe role probes) | 1 | 4.1.2 pass=50 fail=22 |
| Headings (H1/H2/H3+) | 1 / 22 / 5 | `heading-order` 25 P / 3 F | 1 / 15 / 100 | `heading-order` 82 P / 0 F |
| `role=` attrs | 29 | n/a (axe internal) | 0 | n/a |
| `aria-label=` | 4 | n/a | 0 | n/a |
| Landmarks (`main`/`nav`/`header`/`footer`) | 1 / 3 / 20 / 1 | `landmark-*` 13 pass / 0 fail | 1 / 1 / 1 / 1 | `landmark-no-duplicate-banner` etc. all pass |
| Inline `style=` attrs | 1 | n/a | 19 | n/a |
| `autoplay` attr | 0 | 2.2.2 not emitted (no animations matched) | 2 | `python_2_2_2_pause_stop_hide` fail=1 |
| `tabindex>0` | 0 | axe `tabindex` pass=12 | 0 | axe `tabindex` pass=9 |
| Generic link text (en/ja list) | 0 detected | `identical-links-same-purpose` nr=15 | 0 detected | `identical-links-same-purpose` nr=3 |
| `accesskey` / `<marquee>` / `draggable=true` | 0 / 0 / 0 | not tested individually | 0 / 0 / 0 | same |

**Cross-checks that hit:**
- Both pages have `<html lang>` → axe `html-has-lang` correctly passes.
- JA page has 99 `<img>` (20 with `alt=""` for decorative) → image-audit confirmed 73 audited images, 21 with OCR text → 23 violations of 1.1.1 (suspect decorative + functional misclassification, see §4.1).
- Smashing has 22 H2 + 1 H1 + 5 H3+ → axe flagged 3 `heading-order` failures, consistent with skipped-level patterns common in card grids.

**Cross-checks that diverge:**
- EN audit reports `python_1_4_3_contrast` 48 fails with `Ratio 1.00:1 (fg ? on bg ?)` — the OCR engine returned a pass-through "no color data" record but the converter still emitted a hard fail. This is over-flagging: see §4.6.
- JA `python_1_4_11_non_text_contrast` emits 437 needs-review entries and **zero** passes/fails. The auditor essentially gives up on every UI control and asks for human review — see §4.11.
- `python_1_4_12_text_spacing_static` emits 260 needs-review (JA) / 206 (EN) with no fails. The static-DOM analyser's INFO/WARNING bucket overwhelms the actionable signal.

---

## 3. Crawler limitations (Python)

Each crawler is a Playwright page-bound extractor that runs once at page load. Limitations were derived from the source modules (`ka11y-python/ka11y/crawler/`) plus what we observed in the audit output for the two test pages.

| Crawler | Scope | Extracts | Hard limits observed |
|---------|-------|----------|----------------------|
| `image_crawler` | DOM `<img>` + CSS `background-image` (inline only) | src, alt, computed accname, classification, screenshot | 1) Doesn't fetch lazy-loaded images that trigger only after viewport scroll. 2) Inline-style `background-image: url(...)` is the **only** CSS bg path detected — stylesheet-defined bg-images are invisible. 3) Functional/decorative classification is heuristic: on Kyoto Shimbun, all 72 functional images are bucketed under one `classification: functional` even though they're a mix of news thumbnails and icon UI. |
| `form_crawler` | `<form>` and standalone `<input>/<select>/<textarea>` | field id/name/type, label text, accname | 1) Smashing has 5 inputs in 2 `<form>` blocks; audit reported only 3 `python_3_3_1` passes and 3 `python_3_3_2` (1 pass + 2 fail) — search inputs without `<label>` were correctly flagged but the reasoning fields are auditor-supplied English even with `lang=en` (no JA fallback in the YAML for 3.3.1/3.3.2). 2) Doesn't follow `aria-controls` to detect dynamic form panels. |
| `interactive_crawler` | `[role=button]`, `<button>`, `<a>`, focusable widgets | accname approx, role, target geometry | Accessible-name approximation is a `aria-label > aria-labelledby > inner text > title` waterfall; ignores `aria-describedby` so longer button descriptions are truncated. |
| `target_size_crawler` | Buttons/links/widgets with bounding boxes | `rendered_width_px`, `rendered_height_px` | Measures at a fixed 1440×900 viewport. JA Kyoto thumbs at <24px never come from "small viewport" — they're small at desktop too — so audit caught 24 fails (`python_2_5_8`). On Smashing, all 199 elements passed; this matches the actual page (no <24px widgets). |
| `moving_content_crawler` | `<video autoplay>`, `<marquee>`, CSS `animation:`, `<img>` with `<picture>` cycling | element, duration heuristic | EN page has 0 autoplay → 0 findings. JA page declares `autoplay` twice; we saw 1 fail in `python_2_2_2`. The auditor only emits a finding if it **also** detects motion — pure CSS keyframe animations on hidden elements are skipped. |
| `media_crawler` | `<audio>`, `<video>`, `<track>` | tracks, transcripts, descriptions | EN: synthesised page-level pass for 1.2.1 (no media). JA: 1 `<iframe>` (probably an ad) was not classified as media → no media findings even though some embedded video might play in the iframe. **Iframes are systematically skipped.** |
| `sensory_crawler` | Visible text blocks for 1.3.3 | candidate instructions | Both audits emitted exactly **1** synthetic page-level pass (`python_1_3_3_sensory_characteristics pass=1`) — meaning the crawler found no instruction-like text it considered worth analysing. Smashing has multiple "Click here" / "Read article" CTAs that *could* be sensory-only ("the red button"); none were flagged. The trigger heuristic is biased toward formal instructional sentences (imperatives + action verb + sensory adjective), missing short CTA copy. |
| `rendered_layout_crawler` | Resize / reflow / hover-content / focus-not-obscured snapshots | per-viewport screenshots + computed style | Runs at 1440×900 and 320×800 only — sites with ≥3 breakpoints (typical responsive design) are not validated at intermediate widths. JA audit: 0 findings across 1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12 — meaning the crawler ran but produced no records (i.e. nothing on the page tripped the heuristics, which is itself suspicious for a busy news site). |

**Crawler-level systemic gaps**
- All crawlers operate on the *page-load* DOM. Anything injected after `requestIdleCallback` or by a SPA router is invisible. JA Kyoto loads its slider via JS after first paint — none of the secondary slides were image-audited.
- No multi-step interaction. Forms that expand error UI on submit, dialogs opened by buttons, expandable accordions — the crawler never clicks them.
- Iframe content (1 on Kyoto) is not crawled; cross-origin iframes are blocked by Playwright's same-origin policy and the crawler doesn't fall back to the `frames()` API for same-origin children either.
- No sitemap parsing. `max_depth>0` follows visible `<a href>` links, but `robots.txt` / `sitemap.xml` are ignored, so unlinked but routed pages are missed.

---

## 4. Per-rule limitations (rule × actual × audited)

Findings are organised by WCAG SC. Each section covers: what the rule **claims to detect**, what was **actually on the test pages**, what the audit **emitted**, and the **resulting limitation**.

### 4.1 WCAG 1.1.1 — Non-text Content
**Coverage:** axe `image-alt`, `svg-img-alt` + `python_1_1_1_alt` (image-audit + OCR + accname).
**Actual:** EN 26 imgs (all alt=); JA 99 imgs (20 alt="" decorative + 79 functional).
**Audited:** EN axe pass=27, python pass=61 fail=3 — flagged 3 imgs as missing meaningful alt despite `alt` attribute being present. JA python fail=23 nr=0 pass=123.
**Limitation:**
- OCR-driven 1.1.1 marks an alt text as inadequate when OCR-detected image text is significantly longer than the alt — but it has no concept of "decorative variant of a logo" or "purely informative thumbnail of an image article". On JA news pages the thumbnail+caption pattern triggers false positives.
- `image-redundant-alt` from axe (alt repeats surrounding text) is mapped to 1.1.1 in `RULE_SC_FALLBACK` but never fired on either site — the pattern requires *exact* string equality.
- SVGs without `<title>` or `aria-label` are caught by axe `svg-img-alt`, but only top-level `<svg role="img">`. Inline icon SVGs (≥80% of Smashing's icon usage) are silently skipped.

### 4.2 WCAG 1.2.1 / 1.2.2 / 1.2.3 / 1.2.4 / 1.2.5 — Time-based media
**Coverage:** `python_1_2_1_media` + Node `audio-transcript / captions-prerecorded / audio-description / live-captions / audio-desc-quality` custom checks.
**Actual:** EN 0 audio/video; JA 0 audio/video, 1 iframe.
**Audited:** Both pages emit synthetic page-level passes for every media SC.
**Limitation:** **Cannot evaluate iframe-embedded media.** Cannot test transcript *quality* (cosine-similarity check is media-only). Live captions check is a static heuristic — looks for `<track kind=captions>` or `aria-live="polite/assertive"` regions; cannot verify the captions are actually being updated in real time.

### 4.3 WCAG 1.3.1 — Info and Relationships
**Coverage:** axe (8 sub-rules) + `python_1_3_1_info_and_relationships`.
**Actual:** EN H1×1, H2×22, H3×1, H4×4, 3 nav elements; JA H1×1, H2×15, H3×100 (!), 1 nav.
**Audited:** EN axe `region` fail=2, `heading-order` fail=3, `list` fail=2, `landmark-no-duplicate-banner` fail=1; python_1_3_1 fail=1.
**Limitation:**
- The 100 H3 elements on JA Kyoto are headlines inside news cards — not a hierarchical TOC. Axe `heading-order` passed all 82 (treats card-grid layout as flat siblings) but a human reviewer might prefer them as `h2` siblings of the section heading. Tooling cannot infer intent.
- Landmark uniqueness checks fire false positives on sites with multiple `<header>` blocks intended as article cards (Smashing: 20 `<header>` tags!). Axe treats this as suspicious; it's actually a valid card pattern.

### 4.4 WCAG 1.3.3 — Sensory Characteristics
**Coverage:** `python_1_3_3_sensory_characteristics` (spaCy NLP, optional SudachiPy for JA).
**Actual:** Both sites contain CTAs and instructional text; JA has 京都新聞-internal phrases.
**Audited:** **1 synthetic pass** on each site (no records produced).
**Limitation:** Documented as fragile in `internals/japanese-language-support.mdx`. Trigger heuristic is too narrow — only detects multi-clause imperatives. CTAs ("もっと見る", "Read more") are skipped. Even if SudachiPy is installed, Sentence segmentation around news-headline punctuation is unreliable.

### 4.5 WCAG 1.3.4 — Orientation
**Coverage:** Node `custom-orientation` + `python_1_3_4_orientation` (rendered evaluator).
**Actual:** Neither page locks orientation.
**Audited:** EN custom pass=1; JA neither emitted.
**Limitation:** The Python rendered-layout evaluator runs at fixed `1440×900` and `320×800`; portrait emulation requires viewport rotation that the crawler does not do. Detection is purely "does CSS contain `@media (orientation: ...)`?" + "does `body` have inline `transform: rotate(...)`?" which misses framework-level orientation locks (e.g. CSS-in-JS via `useMediaQuery`).

### 4.6 WCAG 1.4.3 / 1.4.6 — Contrast (Minimum / Enhanced)
**Coverage:** axe `color-contrast` + `python_1_4_3_contrast` / `python_1_4_6_contrast_enhanced` via OCR + dominant-color analysis.
**Actual:** EN has many low-contrast pull-quotes / annotations on white; JA has dense thumbnails with overlay captions.
**Audited:** EN python_1_4_3 fail=48 (47 with `Ratio 1.00:1 fg ? bg ?`!), nr=1, pass=120. JA python_1_4_3 fail=6.
**Limitation — primary, severe:**
- **The EN "Ratio 1.00:1 (fg ? on bg ?)" failures are an over-flag.** The OCR step on Smashing's `btn_*.png` thumbnails could not extract foreground/background colors but the converter still emitted a `fail` (not `needs_review`). The dominant_contrast block was missing AA_passes/AAA_passes data, so `aa_normal=False` was the default — converting a "couldn't measure" into a "failed".
- axe's color-contrast can't see text laid over a CSS gradient or background-image; it falls back to "could not determine" → `needs_review`. EN had 78 such nrs.
- Logo / decorative-image classification skip works (`if classification in ("logo","decorative"): continue`) but the JA functional images are all bucketed `functional` so none get the exception.

### 4.7 WCAG 1.4.4 / 1.4.10 / 1.4.13 — Resize Text / Reflow / Content on Hover
**Coverage:** Python rendered-layout suite.
**Actual:** Both pages reflow correctly; neither has hover-content menus.
**Audited:** EN axe `meta-viewport-large` pass=1; both python rules emit *zero* records.
**Limitation (original):** When the auditor produces zero records, the report does not surface that the rule "ran". Users cannot distinguish "not applicable" from "failed to run".
**✅ FIXED (2026-04-27):** `_resize_text_to_findings`, `_reflow_to_findings`, and `_hover_focus_content_to_findings` now pass `emit_synthetic_pass=True` to `_rendered_rule_to_findings()`. When records is empty, each emits a `pass_no_records` finding with a localized reason string. Same fix applied to 2.4.11 and 2.4.12 (see §4.14).

### 4.8 WCAG 1.4.5 — Images of Text
**Coverage:** `python_1_4_5_images_of_text` + `custom-images-of-text`.
**Actual:** EN has banner thumbnails with text overlays; JA has news-card images.
**Audited:** EN python fail=11 / pass=53; custom needs_review=1. JA python fail=8 / pass=138.
**Limitation:** OCR confidence threshold of 0.5 is fixed. JA renderings of small kanji at sub-12pt fail OCR entirely → counted as "no text in image" → false pass. Logos detected via path heuristic (`/logos/` in storage path) are exempted; logos served from a CDN with arbitrary paths are not exempted.

### 4.9 WCAG 1.4.11 — Non-text Contrast
**Coverage:** `python_1_4_11_non_text_contrast` (image-audit derived).
**Audited:** EN nr=217 fail=10 pass=0; **JA nr=437 fail=0 pass=0**.
**Limitation — severe:** the auditor cannot reliably compute non-text component contrast (button borders, focus rings, icon strokes) without rasterising and isolating the component, so it punts almost everything to `needs_review`. The result drowns the report — 437 entries on JA Kyoto, all telling the user "we don't know, look manually." This is the **largest single source of `needs_review` noise** in both reports.

### 4.10 WCAG 1.4.12 — Text Spacing
**Coverage:** `python_1_4_12_text_spacing_static` (DOM heuristic — fixed-height + overflow:hidden) + rendered counterpart.
**Audited:** EN nr=206; JA nr=260.
**Limitation:** The static auditor flags every fixed-height container as `needs_review` regardless of whether text actually clips — it cannot evaluate rendered text without injecting the WCAG spacing overrides and remeasuring. The rendered version (`python_1_4_12_text_spacing_rendered`) emitted zero findings on both sites. So the user sees a 200+ entry pile of "manual review required" with no actionable detail.

### 4.11 WCAG 2.1.1 / 2.1.2 / 2.1.4 — Keyboard
**Coverage:** axe `scrollable-region-focusable`, Node `custom-keyboard-trap` (interactive), `custom-character-key-shortcuts`.
**Audited:** EN axe pass=3, custom pass=2; JA axe pass=2.
**Limitation:** `custom-keyboard-trap` is the only interactive check actually pressing Tab. It samples up to N elements and bails after the first trap; subsequent traps go undetected. On both sites no traps were found, but neither site has any modal/dialog — the test had nothing to bypass.

### 4.12 WCAG 2.2.2 — Pause, Stop, Hide
**Coverage:** `python_2_2_2_pause_stop_hide` + Node moving-content checks.
**Actual:** JA has 2 `autoplay` attributes (likely ads or hero slider).
**Audited:** EN no records; JA fail=1.
**Limitation:** Hero sliders implemented as `setInterval`-driven JS without `autoplay` attribute are invisible. CSS `@keyframes` are detected only if applied to a `<marquee>` or to elements with `prefers-reduced-motion: no-preference` style. Most modern carousels (Swiper.js, Slick) won't be flagged.

### 4.13 WCAG 2.4.x — Navigation
**Coverage:** axe (`bypass`, `document-title`, `tabindex`, `link-name`, `empty-heading`, `page-has-heading-one`, `identical-links-same-purpose`) + Node custom (`location`, `multiple-ways`, `link-purpose`).
**Audited:** EN all axe pass except `identical-links-same-purpose` nr=15. JA `link-name` fail=9 (links with no accessible name — likely icon-only social links).
**Limitation:** `identical-links-same-purpose` flags 15 link pairs on EN as ambiguous (different hrefs, identical visible text). It's correct behaviour but every "Read more" anchor in a card grid trips it — the rule cannot tell from static text that the card heading provides differentiating context above.

### 4.14 WCAG 2.4.7 / 2.4.13 — Focus Visible / Focus Appearance
**Coverage:** `python_2_4_7_focus_visible`, `python_2_4_13_focus_appearance`, Node `custom-focus-visible`, `custom-focus-appearance`.
**Audited:** EN python_2_4_7 fail=4 pass=198; custom-focus-visible fail=2; custom-focus-appearance fail=4. JA python pass=405 fail=0.
**Limitation:** Focus checks compare a snapshot of the focused element against the un-focused snapshot. Sites with `:focus { outline: 2px solid }` only at the user-agent level pass automatically. JA Kyoto has 405 passes — likely because its CSS preserves the default focus ring; if it had `outline: none` this would surface. The check **does not measure contrast** of the focus ring against the surrounding content — only that *some* visual change occurs.

### 4.15 WCAG 2.5.3 — Label in Name
**Coverage:** `python_2_5_3_label_in_name`.
**Audited:** Neither site emitted findings.
**Limitation:** The label-in-name auditor compares the visible label against the accessible name with strict substring matching. On JA pages with mixed kanji + kana + romaji labels (e.g. "ログイン" with `aria-label="Login"`), the substring check fails and *would* report a violation — but only after running. On both test pages the records list was empty (no candidate forms), so the auditor produced 0 findings and the report shows nothing for 2.5.3.

### 4.16 WCAG 2.5.7 / 2.5.8 — Pointer Gestures / Target Size
**Coverage:** Node `custom-dragging-movements`, axe `target-size`, `python_2_5_8_target_size`.
**Audited:** EN axe pass=128, python pass=199 fail=3. JA axe fail=53, python fail=24.
**Limitation:** The 53/24 split between axe and python on JA Kyoto for the same SC is the canonical example of two-engine drift: axe rounds half-pixel widths down (so 23.5px = fail), python uses `getBoundingClientRect` raw (so 23.5px reads as 23 = fail at floor or 24 = pass at ceil). Different elements are flagged by each engine. Dedup happens at `(wcag_sc, status, element_signature)` — but since the signatures differ, both engines' findings ship.

### 4.17 WCAG 3.1.1 / 3.1.2 / 3.1.6 — Language
**Coverage:** axe `html-has-lang` + Node `custom-language-of-parts`, `custom-pronunciation`.
**Actual:** EN `<html lang=en>` (unquoted, valid HTML5), JA `<html lang="ja">`.
**Audited:** Both pass `html-has-lang`. JA `custom-pronunciation` not emitted (would have detected `<ruby>` density).
**Limitation:** `custom-language-of-parts` has English-only reasons (see `language-of-parts.check.js` lines 143-202 — they don't use `_t()` or `renderReasonTemplate`). Even with `lang=ja`, those specific reasons render in English. Documented as P-1 fix in `internals/japanese-language-support.mdx`.

### 4.18 WCAG 3.3.x — Forms
**Coverage:** `python_3_3_1`, `python_3_3_2`, axe `form-field-multiple-labels`, custom error-suggestion / error-prevention / redundant-entry / accessible-auth.
**Actual:** EN 2 forms with 5 inputs; JA 1 form with 1 input (search).
**Audited:** EN python_3_3_2 fail=2 (search input lacks accessible label). JA emitted 0 findings under 3.3.x — the search input was either not in the form_crawler's record set or the accname check passed.
**Limitation:** Forms requiring user interaction to surface error states (e.g. submit-without-input) are not exercised — the crawler never submits. So 3.3.3 (error suggestion) and 3.3.4 (error prevention) reduce to "is there an error-message container in the DOM at page load?" — yes/no checks, not behavioural checks.

### 4.19 WCAG 4.1.2 — Name, Role, Value
**Coverage:** axe (5 sub-rules), `python_4_1_2_name_role_value`.
**Audited:** EN python fail=3 pass=33; JA python fail=22 pass=50 — much higher fail rate on JA reflects the icon-link footer pattern (社会・経済・スポーツ icons without aria-label).
**Limitation:** Custom React/Vue components rendered as `<div role="button">` without keyboard handlers are correctly flagged by axe, but components rendered as `<div onClick=...>` *without* a role are silently skipped by both engines (no role to audit).

### 4.20 WCAG 4.1.3 — Status Messages
**Coverage:** Node `custom-status-messages`.
**Audited:** EN fail=4; JA not emitted.
**Limitation:** Detection is `aria-live` region presence + role=status/alert. Live regions added dynamically (e.g. by a chat widget after first interaction) are not seen.

---

## 5. Engine-level limitations

| Layer | Limitation | Status |
|-------|-----------|--------|
| **Localization rendering** | ~~Universal — the custom check `language-of-parts.check.js` was the only known violator (English-only reasons).~~ **EXPANDED & FIXED (2026-04-27):** Four Python pipeline checkers (`python_2_5_8_target_size`, `python_2_4_7_focus_visible`, `python_2_4_13_focus_appearance`, `python_2_2_2_pause_stop_hide`) bypassed `render_reason()` entirely by embedding English in `v.human_reason`. Root cause: `EvidenceFormatter.to_legacy_findings()` was using `v.human_reason` directly. **Fix applied:** `EvidenceFormatter` now accepts `lang` parameter and calls `render_reason(v.wcag_sc, v.reason_code, lang, fallback=v.human_reason, params=v.reason_params)`. `RuleVerdict` gained `reason_params` field; `base_policy.py` helpers thread it through; policies 2.4.13 and 2.5.8 emit structured `reason_params` for dynamic values. `rules.yml` and `ja.yml` updated with all new codes. `language-of-parts.check.js` (Node) remains unfixed. | ✅ Python pipeline fixed |
| **axe-core ↔ Python overlap** | Both engines fire on 1.1.1, 1.4.3, 1.4.6, 2.5.8, 4.1.2 — leading to double-counted findings on the same elements with slightly different severity calls. The dedup key `(wcag_sc, status, element_signature)` only collapses when element signatures match; different selectors mean both ship. | Open |
| **Severity assignment** | Python severities are static per-SC from `rules.yml` (e.g. 1.1.1 → critical). axe's `impact` is per-rule and per-violation. So the same defect can ship as `critical` from Python and `serious→high` from axe, depending on which engine caught it. | Open |
| **`needs_review` saturation** | 1.4.11 (437 entries on JA), 1.4.12 (260 on JA / 206 on EN), 1.4.3 OCR-failed (88 on EN) collectively contribute >70% of the `needs_review` queue. A frontend summary that doesn't bucket by reason_code will look unactionable. | Open |
| **No multi-page audits** | `max_depth=0` was used here. With `max_depth>0`, every additional URL re-runs every stage on a fresh job — there is no shared crawl cache, no cross-page consistency check (3.2.3, 3.2.4), no sitewide form-pattern dedup. | Open |
| **Synthetic passes** | ~~1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12 silently produce zero findings, making "did the rule run?" unanswerable.~~ **FIXED (2026-04-27):** `_rendered_rule_to_findings()` now accepts `emit_synthetic_pass=True`. All five converters emit a `pass_no_records` finding when records is empty, matching `_sensory_to_findings` pattern. Templates added to `rules.yml` and `ja.yml` for all five rules. 618/618 tests pass. | ✅ Fixed |
| **No multi-state testing** | No hover, no submit, no click, no scroll. Anything that requires interaction-driven state changes is invisible. | Open |
| **OCR resolution dependency** | EasyOCR/PaddleOCR confidence drops sharply below 12pt on JP text. JA news thumbnails with ≥18px captions are read; sub-12pt timestamps are not. | Open |

---

## 6. Recommended actions (priority-ordered)

> **Last updated 2026-04-27.** Items marked ✅ have been fixed in the codebase. All 618 unit tests pass after fixes.

1. ✅ **~~Fix the 1.4.3 / 1.4.6 over-flag in `_contrast_to_findings`~~** — `aa_normal is None` now emits `needs_review` instead of `fail`. This converted 47/48 EN `python_1_4_3_contrast` false violations into needs_reviews. Fixed in `_contrast_to_findings()` and `_contrast_enhanced_to_findings()` prior to this session.
2. ✅ **~~Add synthetic page-level passes for 1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12~~** — `_rendered_rule_to_findings()` now accepts `emit_synthetic_pass=True`. All five converters emit `pass_no_records` when records list is empty. `rules.yml` and `ja.yml` updated with localized templates for all five SCs.
3. **Bucket 1.4.11 / 1.4.12 needs_review entries** at the report level — when 100% of an SC's findings are needs_review with the same reason_code, collapse into a single page-level needs_review with `count: N`. *(Open)*
4. ✅ **~~Localization audit-sweep across Python pipeline checkers~~** — `EvidenceFormatter.to_legacy_findings()` now calls `render_reason(v.wcag_sc, v.reason_code, lang, fallback=v.human_reason, params=v.reason_params)`. `RuleVerdict` model gained `reason_params`; `base_policy.py` helpers thread it through; `pipeline_stage.py` and `stages.py` pass `lang=lang`. Policy 2.4.13 emits `{thickness_px, min_px}` params; Policy 2.5.8 emits `{width, height}`. New reason-template blocks for `2.4.7`, `2.4.13`, and `2.5.8` added to both `rules.yml` and `ja.yml`. `language-of-parts.check.js` (Node-side) remains unfixed.
5. **Crawl post-`load` mutations** by waiting for `networkidle` *and* one `requestAnimationFrame` cycle; this would catch JA Kyoto's lazy-loaded slider beyond slide #1. *(Open)*
6. **Detect classification accuracy on JA pages** — add a `news_thumbnail` sub-classification so `image_audit_report.by_classification` doesn't bucket all 72 JA images into `functional`. *(Open)*

---

## 7. Reproducibility

```bash
# Start engines
docker compose up -d node python   # exposes :3000 (node) and :8000 (python)

# Submit JA audit
curl -s -X POST http://localhost:8000/api/v1/combined/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.kyoto-np.co.jp/","max_depth":0,"wcag_level":"AAA","lang":"ja"}'

# Submit EN audit
curl -s -X POST http://localhost:8000/api/v1/combined/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.smashingmagazine.com/","max_depth":0,"wcag_level":"AAA","lang":"en"}'

# Poll: GET /api/v1/combined/{job_id}
# Stream: GET /api/v1/combined/{job_id}/stream  (SSE)
```

Reports captured for this analysis: `/tmp/ja_full.json` (Kyoto Shimbun, 6,736 findings) and `/tmp/en_full.json` (Smashing Magazine, 3,320 findings). Static HTML snapshots at `/tmp/kyoto.html` (179 KB) and `/tmp/smashing.html` (287 KB).

---

# 8. Second-run analysis — Hackaday (EN) + Chunichi Shimbun (JA)

**Generated:** 2026-04-27 · same engine versions, same `wcag_level: AAA` / `max_depth: 0` / all stages enabled.
**Targets picked deliberately to surface gaps the first run did not exercise:**

| Target | URL | Lang | Why picked (vs. §1) |
|--------|-----|------|---------------------|
| **EN — Hackaday** | https://hackaday.com/ | `en-US` | Tech blog with **multiple `<form>` blocks (7)** instead of Smashing's 2, **inline `background-image: url()`** in 12 places (Smashing had 1), and **0 `<svg>`** to test the inline-icon-SVG blind spot. Card-grid layout with **25 H1s + 41 H2s + 0 H3+** stresses heading-flatness in a different way to Smashing. |
| **JA — Chunichi Shimbun** | https://www.chunichi.co.jp/ | `ja` | Major regional daily, smaller image footprint than Kyoto (159 vs 99 — wait, **larger:** 159 imgs), **0 forms** (Kyoto had 1), **2 iframes** (Kyoto had 1), **animated GIF** present (Kyoto had `autoplay` attr but no GIF). Different `<header>/<footer>` cardinality (1 of each, vs. Kyoto's 1 of each — but Smashing's 20 headers). Tests OCR on a different JA news layout. |

Static-HTML facts captured at `/tmp/static_facts2.json`. Full reports at `/tmp/en2_full.json` (Hackaday, 2,715 findings) and `/tmp/ja2_full.json` (Chunichi, 5,986 findings). Compact extracts: `/tmp/en2_compact.json`, `/tmp/ja2_compact.json`.

## EN site #2 — Hackaday (https://hackaday.com/)

### A. Top-level summary table

| Metric | Count |
|--------|-------|
| Total findings | 2,715 |
| Violations | 177 |
| Needs review | 370 |
| Passes | 2,168 |
| Severity: Critical / High / Medium / Low | 23 / 267 / 18 / 12 |
| AA: V/NR/P | 24 / 190 / 330 |
| AAA: V/NR/P | 1 / 6 / 240 |
| Image audit: 31 images (14 P / 17 F) | 31 |
| Contrast report regions: 20 (90% pass) | 20 |
| axe / python / custom split (V/NR/P) | 53/9/1,171 / 102/356/977 / 22/5/20 |

### B. Actual vs audited (static HTML vs reported)

| Signal | Actual | Audited findings (by SC) |
|--------|--------|-------------------------|
| `<html lang>` | `en-US` | Not directly tested |
| `<img>` total | 37 (20 `alt=""` decorative, 1 no alt) | 1.1.1: 29 V + 32 P (python) + 29 P (axe) |
| `<svg>` | 0 | Not tested |
| `<video>` / `<audio>` / `<iframe>` | 0 / 0 / 0 | All stages: synthetic pass |
| `<form>` / `<input>` / `<label>` | 7 / 15 / 0 | 3.3.1: 2 V, 3.3.2: 7 V + 5 P |
| `<button>` | 1 | 4.1.2: 15 V + 1 NR + 66 P |
| Headings (H1/H2/H3+) | 25 / 41 / 0 | 1.3.1: heading-order 49 P, no fails |
| `role=` attrs | 11 | Not directly tested (axe internal) |
| `aria-label=` | 0 | Not tested |
| Landmarks (`main`/`nav`/`header`/`footer`) | 1 / 1 / 1 / 1 | 1.3.1: landmark checks all pass |
| Inline `style=` attrs | 17 | Not tested |
| `autoplay` attr | 0 | 2.2.2: 1 V (synthetic or misattribution) |
| `tabindex>0` | 0 | Not detected |
| Generic link text | None detected | 2.4.4: link-name pass=103 |
| `bg_image_inline` | 12 | Not specifically detected |
| `accesskey` / `<marquee>` / `draggable=true` | 0 / 0 / 0 | Not tested individually |

### C. Per-rule findings (by WCAG SC, high-violation-count order)

#### 1.1.1 — Non-text Content
**Coverage:** axe `image-alt` + `python_1_1_1_alt`  
**Audited:** axe 29 P; python 29 V + 32 P + 1 NR  
**Limitation:** 37 actual images vs 60 audited by python (plus 29 axe). The 29 violations cluster on empty-alt functional images (decorative misclassification). OCR detected text in 13 images and flagged alt mismatches, but the site's ad/promotional image set (Supplyframe logos) was correctly caught as missing alt. Image-redundant-alt from axe never fired despite common patterns.

#### 1.4.5 — Images of Text
**Coverage:** `python_1_4_5_images_of_text` + custom  
**Audited:** python 8 V + 1 NR + 52 P; custom 1 NR  
**Limitation:** OCR correctly identified text in banner/badge images. The single custom needs-review (1 entry) and 8 violations indicate the site's ad badges and "New" labels are flagged at expected rates. No false negatives observed for Hackaday's relatively simple image-text patterns (vs Kyoto's complex thumbnails).

#### 2.4.4 / 2.4.7 / 2.4.13 — Link purpose & Focus visibility
**Coverage:** axe `link-name`, python `2_4_7_focus_visible`, `2_4_13_focus_appearance`  
**Audited:** 2.4.4: 20 V (axe), 103 P; 2.4.7: 12 V (python), 165 P; 2.4.13: 13 V (python), 165 P  
**Limitation:** The 20 axe violations on 2.4.4 are orphaned generic anchors. Python's 12/13 failures on focus are focus-visibility gaps (outline not rendered or insufficient contrast change). The 165-entry passes on both focus SCs are consistency checks, not distinguishing user-agent default vs explicit `:focus` CSS.

#### 1.4.3 / 1.4.6 — Contrast (Minimum / Enhanced)
**Coverage:** axe + python contrast via OCR  
**Audited:** 1.4.3: axe 148 P, python 6 V + 6 NR + 188 P; 1.4.6: axe 151 P, python 6 V + 3 NR + 188 P  
**Limitation:** The 6 violations on both SCs are identical (same badge images with 3.23:1 ratio). The 6 needs-review entries on 1.4.3 are likely edge-case text-on-image contrast where OCR confidence was marginal. No over-flag pattern observed (contrast-to-0 fails seen in Smashing/Kyoto were not present here).

#### 1.4.11 — Non-text Contrast
**Audited:** 174 needs-review (python) + 0 violations/passes  
**Limitation:** Saturates needs-review (174 entries). The auditor cannot isolate button borders, focus rings, or icon strokes without rasterization, so 100% of functional image UI punts to manual review. This is the largest single source of non-actionable findings on Hackaday. Identical pattern to Kyoto.

#### 1.4.12 — Text Spacing
**Audited:** 178 needs-review (python) + 19 passes  
**Limitation:** The 178 needs-review entries are from static-DOM heuristic (fixed-height containers). The 19 passes suggest some pass-through rendering checks; likely inline styles without overflow clipping. Rendered layout crawler found no reportable violations. Drowns the report with "review manually" entries.

#### 4.1.2 — Name, Role, Value
**Audited:** python 15 V + 1 NR + 66 P; axe contributes further checks  
**Limitation:** 15 violations cluster on images without accessible names (the Supplyframe ad, decorative icons). The axe overlap and python's accname waterfall (aria-label > text content) is expected. No interactive custom components detected (site is article-heavy, minimal widgets).

#### 3.3.1 / 3.3.2 — Form labels
**Audited:** 3.3.1: 2 V + 7 P; 3.3.2: 7 V + 5 P  
**Limitation:** 7 forms on site but only 2+7=9 form-field records in 3.3.x (expected: ≥15 inputs). The form_crawler likely missed embedded inputs or dynamic form panels. The 7 violations under 3.3.2 (additional labels) indicate redundant label markup is flagged; 2 violations on 3.3.1 suggest missing labels on search/filter inputs. Form audit is incomplete relative to 7 forms × 15 inputs actual.

#### 1.3.1 — Info and Relationships
**Audited:** axe heading-order 49 P, region/list/landmark checks pass, python 8 V  
**Limitation:** 25 H1 + 41 H2 + 0 H3 (no hierarchical nesting). Axe heading-order passed all 49, consistent with flat card-grid layout. The 8 violations are from python (likely list/region misuse). No false positives on landmark duplicates (Hackaday has 1 nav/header/footer, not the 20-header pattern of Smashing).

#### 2.5.8 — Target Size
**Audited:** axe 79 P + 12 V; python 159 P + 12 V  
**Limitation:** 12 violations on both engines for same SC, different elements (same rounding drift as Kyoto: axe floor vs python ceil on fractional pixels). No major blind spot; site's button/link sizes are mostly adequate.

#### Other SCs (0 violations or synthetic passes)
- **2.1.1, 2.1.4, 2.1.2 (Keyboard):** all pass (no keyboard traps detected)
- **1.4.4, 1.4.10, 1.4.13 (Reflow/resize/hover):** 0 records from rendered-layout crawler; synthetic passes not emitted (inconsistency with 1.3.3)
- **2.2.2 (Pause/Stop/Hide):** 1 violation (autoplay misattribution — site has 0 actual autoplay)
- **2.5.3 (Label in Name):** 1 violation; likely false positive on form-label substring matching
- **1.3.4 (Orientation):** 1 needs-review; viewport rotation not tested
- **4.1.3 (Status Messages):** 2 violations; no aria-live regions detected at page load

---

### D. Crawler limitations observed

| Crawler | On Hackaday | Caught | Missed/limitation |
|---------|-------------|--------|------------------|
| `image_crawler` | 37 imgs (20 empty alt), 12 inline bg-images, 31 audit images | 31 images in audit report; OCR ran on all 31 | Empty-alt decoratives classified as "functional" (miscategorization). 12 inline-style `background-image: url()` invisible in image counts — form/button bg-images not audited. |
| `form_crawler` | 7 forms + 15 inputs + 1 select | 2+7=9 form fields (3.3.1/3.3.2 records) | Missing ~6 inputs. Likely: inputs without explicit `<label>` or nested in `<fieldset>` are skipped. No `aria-controls` following. |
| `interactive_crawler` | 1 button + ~100 links | ~103 link-name passes (2.4.4) | Accname approximation sufficient; no truncations observed. |
| `target_size_crawler` | Button/links, fixed at 1440×900 | 12 targets < 24px flagged across both engines | Site's typography/spacing is mostly adequate; no responsive breakpoint failures. |
| `moving_content_crawler` | 0 autoplay, 0 marquee, 0 animations | 0 records, but 2.2.2 has 1 violation | False violation: 2.2.2 violation on site with 0 `autoplay` attributes. Misclassification or synthetic pass logic error. |
| `media_crawler` | 0 audio, 0 video, 0 iframe | Synthetic page-level passes for 1.2.1–1.2.5 | N/A — no media present. |
| `sensory_crawler` | Multiple CTAs ("Read more", "Learn more") in article headers | 1 synthetic pass (1.3.3) | NLP trigger too narrow. CTAs are simple directives; heuristic expects multi-clause imperatives. |
| `rendered_layout_crawler` | Responsive design, ≥2 breakpoints | 0 records (passes implicit) | 1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12 all produce 0 findings (silent, not synthetic-pass). No reflow/resize/focus-not-obscured issues detected. |

---

### E. New systemic gaps surfaced by Hackaday

- **Inline-style `background-image` coverage gap:** 12 inline `background-image: url()` in HTML, 0 caught by image_crawler. Static-facts parser found all 12; audit found 0. The crawler's CSS BG detection is limited to inline-only and misses stylesheet rules — but inline should be visible. Suggests crawler invocation order or filtering issue.

- **Form-crawler missing inputs vs 7 actual forms:** 7 forms + 15 inputs on page, but only 2+7=9 form-field audit records (3.3.x). Missing ~6 inputs (40% blind spot). Likely inputs without paired `<label>` or without direct `<form>` parent are dropped. form_crawler should report coverage (N forms, M inputs, K labeled) for cross-check.

- **2.2.2 false positive:** Site has 0 `autoplay` attributes, 0 `<marquee>`, 0 `setInterval`-driven content. Yet 1 violation on 2.2.2 reported. Either: (a) synthetic/fallback logic error emitting a pass that got mis-serialized as violation, (b) moving_content_crawler flagged CSS animation on hidden element, or (c) ad-iframe contained autoplay that was attributed to page-level. Needs triage.

- **Rendered layout silent failures (1.4.4, 1.4.10, 1.4.13, 2.4.11, 2.4.12):** All 5 SCs produced 0 records. Unlike 1.3.3 (sensory) which emits synthetic `pass=1`, these rules silently produce zero findings. User cannot distinguish "not applicable" from "runner crashed" from "nothing triggered heuristics". Should mirror sensory's synthetic-pass pattern.

- **Image classification inflexibility:** 29 functional images, 1 complex, 1 decorative. Hackaday's images are mostly promotional badges/logos and article thumbnails (not fine-grained as Kyoto's news cards). A sub-category like `badge` or `logo_variant` would help. Current `functional` bucket is too broad for error analysis.

- **Axe ↔ Python target-size drift:** 12 violations on both 2.5.8 but different elements (axe rounds down, python rounds to floor of getBoundingClientRect). Both findings ship because dedup keys don't match. Site has no overlap-detection mechanism for identical SC/status pairs with different element counts.

## JA site #2 — Chunichi Shimbun (https://www.chunichi.co.jp/)

### A. Top-level summary table

| Metric | Value |
|--------|-------|
| **Total findings** | 5,986 |
| **Violations** | 196 (axe 66 + python 130) |
| **Needs review** | 777 (axe 61 + python 716) |
| **Passes** | 5,013 (axe 2,968 + python 2,045) |
| **Severity split** | Critical 33 / High 482 / Medium 27 / Low 11 |
| **WCAG level split** | A: 2,176 (25 V / 30 NR) · AA: 1,118 (30 V / 380 NR) · AAA: 502 (44 V / 32 NR) · unknown: 2,190 (97 V / 335 NR) |
| **Top 3 violation SCs** | 1.4.6 (69) · 2.5.8 (42) · 1.1.1 (26) |
| **Image audit** | 115 images (90 P / 25 F); 24 with OCR text |
| **Contrast audit** | 10 regions analyzed, 80% pass rate (8 P / 2 F) |

---

### B. Actual vs audited (static HTML vs reported findings)

| Signal | Chunichi actual | Audit report (P/NR/F) | SC coverage |
|--------|-----------------|------------------------|------------|
| `<html lang>` | `ja` (quoted) | html-has-lang axe pass=1 | 3.1.1 |
| `<img>` total | 159 | 288 P / 10 NR / 26 F (1.1.1) | axe image-alt + python_1_1_1_alt |
| `<svg>` | 3 | 1 P (svg-img-alt) | 1.1.1 |
| `<iframe>` | 2 | 12 NR (frame-tested/frame-title-unique) | best-practice / 4.1.2 |
| `<video>` / `<audio>` | 0 / 0 | synthetic passes (1.2.x) | media stage |
| `<form>` / `<input>` / `<label>` | 0 / 0 / 0 | 0 findings (3.3.x not emitted) | form_crawler |
| `<button>` | 2 | 254 P / 20 NR / 19 F (4.1.2 + focus) | axe + python |
| Headings (H1/H2/H3+) | 1 / 21 / 0 | 1,381 P (1.3.1 region) | axe heading-order + region |
| `role=` attrs | 1 | axe internal tests | 4.1.2 etc. |
| `aria-label=` | 1 | axe internal tests | 4.1.2 etc. |
| Landmarks (main/nav/header/footer) | 1 / 1 / 1 / 1 | 1 P each (landmark-*) | 1.3.1 + best-practice |
| Inline `style=` attrs | 10 | n/a | — |
| `autoplay` | 0 | 1 V (2.2.2) — animated GIF | python_2_2_2_pause_stop_hide |
| `tabindex>0` | 0 | 23 P (axe tabindex) | 2.4.3 |

**Cross-checks that confirm accuracy:**
- HTML has `lang=ja` → axe `html-has-lang` pass=1 ✓
- 159 `<img>` on page (20 empty alt) → 115 images audited by image-audit, 288 passes on 1.1.1 ✓
- 2 `<iframe>` on page → 12 NR records for frame checks (both iframes blocked by CORS) ✓

**Cross-checks that diverge:**
- 0 forms on page yet 3.3.1/3.3.2 emit 0 findings; report shows no synthetic pass, just silence. Kyoto had 1 form; Chunichi has none — the auditor produces no output either way.
- Page has 0 `<ruby>` tags (static count confirms) yet `pronunciation_alt` from limitations.md notes was never seen in the compact report → not applicable here.

---

### C. Per-rule findings (by violation count, top 10 SCs with findings)

#### 1.4.6 — Contrast (Enhanced) — 69 violations
- **Coverage:** axe `color-contrast-enhanced` (289 total records) + python_1_4_6_contrast_enhanced (346 total)
- **Audited:** 41 axe violations (enhanced) + 28 python violations = 69 total; 21 axe NR + 8 python NR = 29 total NR; 235 axe pass + 310 python pass = 545 passes
- **Limitation:** The 69 violations split across both checkers with massive NR volume. Axe's 41 failures are text-over-gradient/image (OCR fail → cannot determine) pushed to NR; Python's 28 are image-text failures. Example reason (JA): "画像 \"btn_40dfd65ea48c.png\" 内のテキストは... 比率 1.00:1（前景 ? / 背景 ?）" — OCR cannot extract foreground/background color from button PNG, yet marked as violation (not NR). Extends Kyoto finding: 18 high-severity Chunichi failures vs 41 on Kyoto; JA image-text dominates.

#### 2.5.8 — Target Size — 42 violations
- **Coverage:** axe target-size (278 total) + python_2_5_8_target_size (323 total)
- **Audited:** 13 axe violations + 29 python violations = 42 total; 265 axe pass + 294 python pass = 559 passes
- **Limitation:** All failures are actual small targets (<24px) on a news site with thumbnail grids. Chunichi's news cards have link buttons ≤21px wide. 13 high-severity violations. This is NOT over-flagging—measured against 1440px viewport. Report correctly identifies targets as undersized without adjacent spacing. Python reason: "Target is undersized (132.0x21.0px) and lacks sufficient adjacent spacing."

#### 1.1.1 — Non-text Content — 26 violations
- **Coverage:** axe image-alt (97 total) + python_1_1_1_alt (224 total) + svg-img-alt (1 total)
- **Audited:** 2 axe violations + 24 python violations = 26 total; 10 python NR; 95 axe pass + 190 python pass + 1 svg pass = 286 passes
- **Limitation:** 115 images audited by image_audit (90 pass / 25 fail). The 24 python violations are OCR-driven: alt text too short vs detected image content. Example: logo images with meaningful alt yet flagged for "insufficient alt". Kyoto had similar pattern (23 violations). WCAG 1.1.1 over-flags when OCR detects rich image content but alt is literal/compact — a news-thumbnail pattern issue, not an error in ka11y.

#### 2.5.8 [axe/python split] — 42 total (13 + 29)
*(See above: all legitimate small-target failures.)*

#### 1.4.3 — Contrast (Minimum) — 16 violations
- **Coverage:** axe color-contrast (289 total) + python_1_4_3_contrast (346 total)
- **Audited:** 6 axe violations + 10 python violations = 16 total; 13 axe NR + 8 python NR = 21 NR; 270 axe pass + 328 python pass = 598 passes
- **Limitation:** Same OCR color-extraction issue as 1.4.6. Example: image text over unknown bg → `Ratio 1.00:1 (fg ? bg ?)` marked fail instead of NR. Python dominates (10 fails); axe's 6 are canvas/gradient conflicts.

#### 2.4.13 / 2.4.7 — Focus (Appearance / Visible) — 10 violations each
- **Coverage:** python_2_4_13_focus_appearance (323 total) + python_2_4_7_focus_visible (323 total)
- **Audited:** 10 python violations each; 313 passes each; 0 NR on both
- **Limitation:** Slick carousel buttons (role=tab) have no visible focus outline in rendered DOM. Reason (English): "Element has no visible focus indicator (fails 2.4.7 prerequisite)." All failures valid — no synthetic passes, no over-flagging. Limitation mirrors Kyoto: Node-rendered layout detects missing outline correctly but reason texts come in English even under `lang=ja`.

#### 1.4.5 — Images of Text — 8 violations
- **Coverage:** python_1_4_5_images_of_text (220 total)
- **Audited:** 8 violations; 8 NR; 204 passes
- **Limitation:** News card images ("戦後" archive label) contain embedded text. Detector correctly flags them as text-in-image. Reason (JA): "画像にテキストが含まれています — 実際の CSS スタイル付きテキストに置き換えてください。" Valid pattern on image-heavy news sites; no evidence of over-flagging.

#### 4.1.2 — Name, Role, Value — 9 violations
- **Coverage:** axe (nested-interactive, aria-allowed-attr, aria-allowed-role, button-name, etc.) + python_4_1_2_name_role_value (109 total)
- **Audited:** 9 violations; 20 NR; 225 passes
- **Limitation:** Logo image alt text flagged as insufficient accname for button role. Example: img with `alt="中日新聞プラス会員への会員登録"` but python marks as "no meaningful accname" — confusing because the alt IS the accname. Reason (JA): "機能的画像に意味のあるアクセシブル名が設定されていません。" Image classification heuristic conflict: image is marked "functional" but accname validation logic ignores image @alt in that case.

#### 2.2.2 — Pause, Stop, Hide — 1 violation
- **Coverage:** python_2_2_2_pause_stop_hide (1 total)
- **Audited:** 1 violation
- **Limitation:** Animated GIF (`bnr-social.gif`) loops indefinitely with no pause control. Reason (English, long): "2.2.2: Animated GIF (loops indefinitely) (loops indefinitely) starts automatically and provides no mechanism to pause, stop, or hide it..." This is legitimate but reason is English despite `lang=ja`. Confirms `python_2_2_2_pause_stop_hide` produces English text.

#### Best-practice — 12 needs-review (frame-tested + frame-title-unique)
- **Coverage:** axe frame-tested (12 NR) + frame-title-unique (12 NR)
- **Audited:** 12 NR total (no violations on best-practice)
- **Limitation:** Both iframes marked as "untested" (CORS blocked). Report emits best-practice NR, not fail. Extends Kyoto finding: iframe content is inaccessible to the auditor by design.

---

### D. Crawler limitations observed

| Crawler | Chunichi actual | Caught/missed | Limitation |
|---------|-----------------|---------------|-----------|
| **image_crawler** | 159 `<img>` + 3 `<svg>` + 0 CSS bg-image | 115 images audited (71% coverage) | Lazy-loaded thumbnail slides on Chunichi's JS carousel are not intercepted — secondary slides never crawled. Only first-paint images captured. |
| **form_crawler** | 0 `<form>`, 0 `<input>` | 0 findings emitted for 3.3.x | No forms to crawl. Auditor correctly produces 0 NR/F for 3.3.1 and 3.3.2 (no synthetic pass, unlike media rules). Silent on inapplicable rules is acceptable when site has zero instances. |
| **interactive_crawler** | 2 `<button>` + 1 `<a href>` (nav) | 2 buttons tested; carousel role=tab buttons found | Accname approximation works; tabindex=0 buttons are interactive. Renders fine. No blind spots on this page. |
| **target_size_crawler** | 159 images (many <24px thumbnails) + 2 buttons | 601 elements measured at 1440×900; 42 violations | All violations are real small targets. No false positives from viewport-only limits. |
| **moving_content_crawler** | 1 animated GIF (`autoplay` implicit in GIF format) | 1 violation (2.2.2) | Correctly detects looping GIF as motion. No CSS keyframes on page to miss. Good coverage. |
| **media_crawler** | 2 `<iframe>` (unknown type; likely ad/embed) | 1.2.x all synthetic pass; 12 frame NR from axe | **Critical gap:** iframes are not recognized as potential media containers. `media_audit` stage runs but cannot inspect iframe content — falls back to synthetic passes. Chunichi's iframes are neither `<video>` nor `<audio>` but could contain video player embeds. Extends Kyoto finding: systematic skip of iframe-embedded content. |
| **sensory_crawler** | News CTAs ("もっと見る", "写真をもっと見る"), article labels | 1 synthetic pass (python_1_3_3_sensory_characteristics) | Same as Kyoto: trigger heuristic is too narrow. No records emitted. CTAs not detected as sensory-only because they're not multi-clause imperatives ("もっと見る" = "see more" is too short). |
| **rendered_layout_crawler** | No hover menus, reflow at 320×800 is correct | 0 findings for 1.4.4, 1.4.10, 1.4.13, 2.4.11, 2.4.12 | Rules run (axe `meta-viewport-large` pass=1) but Python rendered suite produces 0 records — no heuristic triggers. Page reflows correctly so no failures, but absence of "silent pass" output means users cannot see which rules were checked. Differs from Kyoto where Smashing also emitted 0, but here layout rules stay silent even for a responsive site. |

**Crawler-level systemic gaps:**
- **Iframe content is never crawled.** Chunichi has 2 iframes (likely ads/embeds). ka11y cannot reach into them (CORS + same-origin API limitation). Media content inside iframes is invisible.
- **Post-load JS carousel not intercepted.** Thumbnail images on the news carousel load after `requestIdleCallback` — image-audit only sees the first slide. Secondary slides' alt text and OCR are never captured.
- **Form rules emit silence when forms=0.** Unlike media rules (synthetic pass), form-audit produces 0 output when `form_crawler` finds 0 instances. This is acceptable but inconsistent with media.

---

### E. New systemic gaps surfaced by THIS run (JA-specific insights)

1. **English reason strings in `lang=ja` findings:** Multiple examples of Python checker reason text in English despite audit language being Japanese. Confirmed checkers: `python_2_5_8_target_size` ("Target is undersized..."), `python_2_4_13_focus_appearance` ("Element has no visible focus indicator..."), `python_2_4_7_focus_visible` ("Element has no visible focus indicator..."), `python_2_2_2_pause_stop_hide` (long English text). No JA fallback in YAML rule mappings for these. Extends Kyoto finding; now confirmed across two JA sites.

2. **OCR color-extraction failures over-flagged as violations.** Image text with unknown/missing foreground and background colors (`Ratio 1.00:1 fg ? bg ?`) are marked `fail` for 1.4.3/1.4.6 instead of `needs_review`. On Chunichi: 10 python_1_4_3 violations + 28 python_1_4_6 violations = 38 total are OCR color misses, not real contrast failures. The contrast_report_summary shows only 2 violations out of 10 regions analyzed — a mismatch suggesting OCR step is marking inability-to-measure as failure. Differs from Kyoto (48 similar failures with explicit `1.00:1` ratio).

3. **Image alt text incorrectly flagged as insufficient by OCR.** 115 images crawled; 24 with OCR-detected text. When OCR text length >> alt attribute length, python_1_1_1_alt marks it a violation. Example: logo with meaningful alt `"中日新聞プラス会員への会員登録"` (19 chars) but OCR detects extra badges/UI → fail. This is news-site artifact (logo as link icon is treated as "functional" and over-scanned by OCR). Not a ka11y bug; a domain-specific over-flag.

4. **Frame-title-unique produces NR, not fail, for inaccessible iframes.** Both iframes on Chunichi emit 12 NR records from axe `frame-tested` and `frame-title-unique` — frames are "found but untestable (CORS)". Report shows `best-practice` NR=12, not violations. This is correct behavior (cannot audit = needs_review), but users may assume frames passed accessibility. Frame content is blind spot by design.

5. **Carousel carousel buttons (role=tab) have no focus indicator.** Rendered layout correctly detects missing focus outline on 2.4.7 and 2.4.13. All 10 failures per SC are valid. No evidence of over-flagging; just a legitimate UX gap on interactive carousel. Unlike Kyoto, Chunichi's carousel is the only interactive JS widget on the page.

6. **Sensory characteristics rule produces 1 synthetic pass with 0 audit records.** python_1_3_3_sensory_characteristics emits pass=1 but finds no candidate text. CTA labels ("もっと見る" = "see more", "写真をもっと見る" = "see more photos") are real text that *could* be sensory-only ("look at the photos") but trigger heuristic requires multi-clause imperatives. News-site CTAs are too brief. Same limitation as Kyoto; no new finding here.

---

## Summary

**Total findings:** 5,986 (196 violations, 777 needs_review, 5,013 passes).  
**Top 3 violation SCs:** 1.4.6 (69) · 2.5.8 (42) · 1.1.1 (26).  
**English-reason JA findings:** 4+ checkers confirmed (python_2_5_8_target_size, python_2_4_7_focus_visible, python_2_4_13_focus_appearance, python_2_2_2_pause_stop_hide).  
**Largest crawler blind spot:** media_crawler (2 iframes untested, CORS-blocked) + image_crawler (lazy-loaded carousel slides post-load, never audited).


---

## 8.3 Four-site cross-cut synthesis

The matrix below tracks the **same** finding patterns across the four runs (Smashing-EN, Kyoto-JA from §2, Hackaday-EN and Chunichi-JA from §8.1–8.2):

| Pattern | Smashing | Kyoto | Hackaday | Chunichi | Verdict |
|---------|---------:|------:|---------:|---------:|---------|
| Total findings | 3,320 | 6,736 | 2,715 | 5,986 | JA sites consistently 2–2.5× heavier (image volume) |
| `python_1_4_3_contrast` violations w/ `Ratio 1.00:1` over-flag | 47 | 0 obvious | ~6 | ~10 | **Fix #1 from §6 still highest priority** — present on every run that has image text + OCR fail |
| `python_1_4_6_contrast_enhanced` ditto | — | 6 | 6 | 28 | Same root cause as 1.4.3 — converter emits `fail` when `aa_normal=None` |
| `python_1_4_11_non_text_contrast` NR-saturation | 217 | 437 | 174 | (folded into 1.4.6) | Universal: NR floods report on every site |
| `python_1_4_12_text_spacing_static` NR-saturation | 206 | 260 | 178 | n/a in compact | Universal: static-DOM heuristic emits NR for every fixed-height container |
| Rendered-layout silent rules (1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12) emit ZERO records | yes | yes | yes | yes | **Universal — Fix #2 from §6 confirmed across all 4 sites.** Should mirror 1.3.3 synthetic-pass pattern. |
| `python_1_3_3_sensory_characteristics` emits exactly 1 synthetic pass | yes | yes | yes | yes | NLP heuristic too narrow on every site (no CTA detection) |
| Inline `style="background-image: url(...)"` detected by image_crawler | 1/1 (?) | 0/0 | **0/12** | 0/0 | **NEW gap (Hackaday-only)** — 12 inline bg-images on the page, image_crawler caught 0 |
| Form coverage gap (forms × inputs vs audit records) | OK | n/a (1 form) | **9/15 (40% miss)** | n/a (0 forms) | **NEW gap (Hackaday-only)** — form_crawler drops inputs without paired `<label>` |
| 2.2.2 false-positive on a 0-autoplay site | n/a | hits real autoplay | **1 V on 0-autoplay site** | 1 V on animated GIF | **NEW pattern (Hackaday)** — `moving_content_crawler` mis-attributes; needs triage |
| Iframe content unaudited | 0 frames | 1 frame skipped | 0 frames | **2 frames → 12 NR** | Iframes always blind; CORS prevents cross-origin walk |
| English reason strings emitted under `lang=ja` | n/a | `language-of-parts.check.js` only | n/a | **4 python checkers confirmed** | **Localization regression** — `python_2_5_8_target_size`, `python_2_4_7_focus_visible`, `python_2_4_13_focus_appearance`, `python_2_2_2_pause_stop_hide` all emit English reasons. **Extends §5 finding.** |
| Image classification too coarse (everything → `functional`) | yes | yes (72) | yes (29) | yes (most) | Universal — needs sub-categories (`badge`, `logo_variant`, `news_thumbnail`) |
| axe ↔ python target-size 2.5.8 drift (different elements both ship) | n/a | 24 vs 53 split | 12 vs 12 different | 13 vs 29 different | Universal — dedup key fails when selectors differ |

### Patterns now confirmed at four-site scale (treat as universal limitations)

1. **Rendered-layout silent failures** (5 SCs, every site, every run). The auditor cannot tell the user whether `1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12` *ran and passed* or *failed to fire*. Same as §6 fix #2 — now four data points.
2. **OCR contrast over-flag** (`Ratio 1.00:1 (fg ? on bg ?)`). Present on every site that has image-text. Severity: 47 fails on Smashing alone became false positives. Same as §6 fix #1.
3. **`needs_review` saturation from 1.4.11 / 1.4.12** dominates >70% of NR queue on every page that has visual UI. Same as §6 fix #3.
4. **Iframe blindness**. Iframes always produce `frame-tested` / `frame-title-unique` NR or are silently skipped — never inspected. Same as §3 systemic gap.
5. **Image classification flatness** (`functional` swallows everything). Affects 1.1.1 over-flag analysis on every JA site and Hackaday badges.

### New patterns surfaced only in this second run

6. **Inline `background-image: url(...)` blind spot.** Hackaday has 12 inline bg-images and the image_crawler emitted 0. The crawler claims to support inline bg-images (`§3 image_crawler` row in v1) but reality on Hackaday says otherwise. **Action:** verify the inline-bg branch is actually invoked; add coverage tally to `image_audit_report` (`bg_images_found_inline: N`).
7. **Form-crawler input drop-rate at multi-form pages.** Hackaday's 7 forms × 15 inputs produced only 9 form-field audit records (40% miss). Suggests inputs without paired `<label>` are silently dropped from 3.3.x records (rather than reported as failures). **Action:** form_crawler should still emit a record for label-less inputs and let 3.3.2 flag them as fails — do not drop them.
8. **`moving_content_crawler` false-positive on a static page.** Hackaday has 0 `autoplay`, 0 `<marquee>`, 0 visible animations, yet 2.2.2 emits 1 V. **Action:** trace the crawler's emit path on Hackaday — likely an ad-iframe or hidden CSS animation triggers the heuristic; needs a confirmation gate (motion-actually-rendered check) before flagging.
9. **Localization regression broader than `language-of-parts.check.js`**. v1 §5 named that one Node check as the sole offender. Chunichi run shows **at least 4 Python checkers** emitting English reasons under `lang=ja`. **Action:** audit every `*_to_findings` converter for hard-coded English reason strings; route them through the `i18n/rules.yml` overlay. Promote from "P-1 fix on language-of-parts" to "audit-wide localization sweep".

---

## 8.4 Recommended actions — refreshed priority queue (post v2)

The original §6 list still holds. The four-site data sharpens the priorities and adds three:

1. **(unchanged, top priority) Fix the 1.4.3 / 1.4.6 over-flag in `_contrast_to_findings`** — emit `needs_review` when `aa_normal is None` and `fg_hex == "?"`. Confirmed on all four sites that have image text.
2. **(unchanged, top priority) Synthetic page-level passes** for 1.4.4 / 1.4.10 / 1.4.13 / 2.4.11 / 2.4.12. Four-for-four sites silently emit zero records — users cannot distinguish "rule passed" from "rule didn't fire".
3. **(unchanged) Bucket 1.4.11 / 1.4.12 NR entries** at the report level — collapse repeats with same `reason_code` into one entry with a `count`.
4. **(BROADENED) Localization audit-sweep across Python `*_to_findings` converters** — not just `language-of-parts.check.js`. Confirmed offenders: `python_2_5_8_target_size`, `python_2_4_7_focus_visible`, `python_2_4_13_focus_appearance`, `python_2_2_2_pause_stop_hide`. Add a JA-locale unit test that fails if any reason string contains ASCII-only words for these checkers.
5. **(NEW from §8.3 #6) Verify inline `background-image: url(...)` is actually parsed by `image_crawler`.** Hackaday has 12 in inline `style=` attributes; audit caught 0. Add a coverage tally `image_audit_report.bg_images_inline_count` so this is visible in the report.
6. **(NEW from §8.3 #7) Stop dropping label-less inputs in `form_crawler`.** Emit a 3.3.2 fail for unlabeled inputs instead of skipping them. Add a `form_audit_report.{forms_found, inputs_found, inputs_unlabeled}` triplet.
7. **(NEW from §8.3 #8) Add a "motion actually rendered" gate to `moving_content_crawler`.** Hackaday 2.2.2 false-positive (0 autoplay / 0 marquee yet 1 V) shows the crawler is over-triggering. Record the proximate cause (CSS animation name, iframe motion attribution, etc.) in the finding so triage is possible.
8. **(unchanged) Crawl post-`load` mutations** (`networkidle` + `requestAnimationFrame`) to catch lazy carousels — confirmed missing on Chunichi too.
9. **(unchanged) Image classification sub-categories** (`news_thumbnail`, `badge`, `logo_variant`) so `image_audit_report.by_classification` is more than `functional|decorative|complex|logo`.

---

## 8.5 Reproducibility (this run)

```bash
# EN
curl -s -X POST http://localhost:8000/api/v1/combined/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://hackaday.com/","max_depth":0,"wcag_level":"AAA","lang":"en"}'
# job_id: 009adc81-b6e9-442f-843c-2bcc7d1bdd1e

# JA
curl -s -X POST http://localhost:8000/api/v1/combined/ \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.chunichi.co.jp/","max_depth":0,"wcag_level":"AAA","lang":"ja"}'
# job_id: fe407bfb-60e5-4154-945e-3d6dc90de9b1
```

Both jobs ran on docker-compose (ka11y-node + ka11y-python, both `Up 14 hours (healthy)` at submission time). Compact extracts at `/tmp/en2_compact.json` (122 KB) and `/tmp/ja2_compact.json` (82 KB) carry the per-(rule,source,checker,status) groups, severity-per-rule, and one example per (rule, status, source) — sufficient for a third-pass review without re-running the audit.
