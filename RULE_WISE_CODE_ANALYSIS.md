# Rule-wise Code Analysis

- Generated at (UTC): `2026-04-13`
- Scope: `a11y-node/src/custom-checks`, `a11y-node/src/services`, `a11y-python/a11y/crawler`, `a11y-python/a11y/accessibility/rules`, `a11y-python/a11y/accessibility/rendered/evaluators`, shared `config/universal.yml`
- Method: current-state code review of the live production path, not the older standalone crawler-only model
- Status baseline: includes the 2026-04-13 shared-config, TLS-handling, localization, and fixture-review changes already merged into the repo

---

## Executive Summary

The codebase is materially better than the older report suggested, but it is not at a "zero bug" end state.

- Frontend compatibility is improved: Node Puppeteer and Python Playwright now both default to `browser.ignore_https_errors` from `config/universal.yml`, so an expired target certificate no longer becomes a generic frontend-breaking Node `500` in the normal path.
- Node localization is no longer flat-English-only, but it is still incomplete: several custom rules still embed Japanese strings in JS instead of loading them from shared config.
- Python's production crawler architecture is stronger than the legacy crawler set because `UniversalPageLoader` now feeds seven static rule families through one normalized snapshot, but cross-origin frames, OCR budgets, and runtime-only states still produce partial coverage rather than complete certainty.
- The largest remaining structural defect across both stacks is still the absence of a universal `reason_code` plus `reason_params` contract. Failures are still mostly prose strings, which makes EN/JA parity, fixture reuse, and frontend reason handling more fragile than they should be.

---

## Current Production Path

### Node

- `a11y-node` still owns `axe-core` plus 24 custom checks.
- Static checks run in parallel; interactive checks run sequentially.
- Shared config now reaches the service layer and custom checks, so `lang` and selected EN/JA assets can be reused instead of being fully hardcoded.
- Flat mapping now preserves more structured evidence such as selector, target, snippet, and media query.

### Python

- The production static path is now `UniversalPageLoader` -> `SnapshotNormalizer` -> existing auditors.
- `AsyncImageCrawler` still owns OCR, screenshots, image classification, and contrast/image auditing.
- `RenderedLayoutCrawler` still owns orientation, reflow, resize-text, hover/focus, and focus-obscuration checks.
- Legacy direct crawler classes still exist for compatibility, but the combined pipeline does not rely on them as the primary extraction path anymore.

---

## Cross-cutting Findings

| Area | Current state | Remaining limitation | Impact |
| --- | --- | --- | --- |
| Shared config | Node and Python now both read repo-root `config/universal.yml` for browser/TLS and some language assets | Only part of the rule language surface is config-backed; many heuristics still live in code | EN/JA parity is improved but not universal |
| TLS / cert failures | Shared `browser.ignore_https_errors` prevents the recent expired-cert frontend break in the normal path | If the flag is turned off, bad target certificates still block navigation by design | Correct behavior, but must be surfaced clearly to clients |
| Localization | Node flat metadata now localizes `criterion_name`; grouped/flat routes accept `lang` | Many custom failure reasons are still string-built in code, especially on Python and some Node rules | Mixed localization quality across rule families |
| Failure contract | Selected Node checks now use shared reason templates | There is still no universal `reason_code` and `reason_params` schema across Node and Python | Harder to translate, test, deduplicate, and render reliably in frontend |
| Static extraction | Universal snapshot handles same-origin iframes, open shadow roots, and warning sampling | Cross-origin frames remain partial by design; late JS mutations can still be missed | More accurate than before, but not complete |
| OCR / CV | OCR is budgeted and contrast/image analysis is productionized | OCR can still skip assets on heavy pages, and token-based matching is weak for CJK/non-spaced text | Some false passes and false reviews remain likely |
| Interactive/runtime checks | Node and Python both have interactive/rendered paths for focus and layout issues | Delayed transitions, post-load listeners, pseudo-elements, same-URL SPA updates, and hidden controls still evade some checks | Most remaining gaps are runtime-shape gaps, not simple bugs |
| Japanese support | Shared YAML now drives several Node EN/JA rule assets and crawler CJK settings | Python still keeps major JP heuristics in source; some Node JP heuristics are still source-driven too | Japanese behavior can still drift by service |

---

## Node Custom Rules

| SC | Rule file | Mode | Current detection strength | Main limitation or bug risk | JP / config status | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| 3.3.8 | `accessible-auth.check.js` | Static | Good coverage for password/login context, CAPTCHA markers, paste blocking, and passkey hints | Misses custom or obfuscated CAPTCHA flows and runtime auth widgets; still depends on text and DOM markers | Japanese auth/CAPTCHA terms are still source-driven | High |
| 1.2.1 | `audio-transcript.check.js` | Static | Detects `<track>`, nearby links, `figcaption`, `details`, and `aria-describedby` | Cannot verify transcript quality/content or cross-origin/iframe transcript pages | Config-backed EN/JA via `checks.audio_transcript` | Medium |
| 2.1.4 | `character-key-shortcuts.check.js` | Static | Good for `accesskey`, inline handlers, and inline script listeners with missing modifier guards | Misses dynamically attached listeners and framework-bound shortcuts | Language-agnostic | Medium |
| 3.2.6 | `consistent-help.check.js` | Static | Good keyword and widget detection for help/contact/support presence | Cannot prove site-wide consistency from one page; hidden/modal-only help can be missed | Config-backed EN/JA via `checks.consistent_help` | Medium |
| 2.5.7 | `dragging-movements.check.js` | Static | Good for native draggable elements and common library markers | Misses custom pointer-drag implementations without recognizable markers | Language-agnostic | Medium |
| 3.3.4 | `error-prevention.check.js` | Static | Good first-pass detection of legal, financial, and destructive forms plus review safeguards | Static only; modals, timed confirmations, and script-driven previews can be missed | Config-backed EN/JA via `checks.error_prevention` | High |
| 3.3.3 | `error-suggestion.check.js` | Static | Good detection of terse vs corrective error text in visible error elements | Runtime/server-returned errors and tooltip-only guidance are missed | Config-backed EN/JA via `checks.error_suggestion` | Medium |
| 2.4.13 | `focus-appearance.check.js` | Interactive | Good for focus indicator presence, size, and contrast on sampled focusables | Pseudo-elements, delayed transitions, and parent-level `:focus-within` indicators remain weak spots | Language-agnostic | Medium |
| 2.4.7 | `focus-visible.check.js` | Interactive | Good for style-diff based visible focus detection | Same pseudo-element and delayed-animation blind spots as focus appearance | Language-agnostic | Medium |
| 4.1.1 | `html-parsing.check.js` | Static | Reliable duplicate ID, broken ARIA reference, and orphan label checks | It is DOM-validity oriented, not a full parser or template-syntax validator | Language-agnostic | Low |
| 1.4.5 | `images-of-text.check.js` | Static | Useful heuristic triage from filenames, alt text, CSS, and SVG text | No OCR/pixel verification, so false positives and false negatives remain materially possible | Language-agnostic | High |
| 2.1.2 | `keyboard-trap.check.js` | Interactive | Good coverage for single-element loops, two-element loops, reverse tabbing, widgets, and iframe traps | Closed shadow DOM and delayed/dynamic traps can still evade detection | Language-agnostic | Medium |
| 2.4.9 | `link-purpose.check.js` | Static | Good accessible-name resolution and generic-link filtering | Limited context reasoning; misses title-only/generated labels and can still over-flag short but meaningful text | Japanese generic-link patterns are still source-driven | Medium |
| 2.4.8 | `location.check.js` | Static | Good breadcrumb, `aria-current`, active-nav, sitemap, step, and JSON-LD detection | Visual-only location cues and SPA updates after navigation can be missed | Config-backed EN/JA via `checks.location` | Medium |
| 1.3.2 | `meaningful-sequence.check.js` | Static | Good flex/grid/order/float heuristics with RTL awareness | Absolute positioning, transform-based reordering, and layout-engine-only reorder cases remain out of scope | Language-agnostic | Medium |
| 2.4.5 | `multiple-ways.check.js` | Static | Good first-pass detection of search, sitemap, nav, breadcrumb, and TOC mechanisms | Site-wide navigation availability cannot be proven from one page; async menus can be missed | Config-backed EN/JA via `checks.multiple_ways` | Medium |
| 3.2.1 | `on-focus.check.js` | Interactive | Good for URL/history-based context changes on focus | Same-URL modal/dialog/content changes can still be missed | Language-agnostic | High |
| 3.2.2 | `on-input.check.js` | Interactive | Good for URL/history-based context changes on input for major control types | JS-only submissions and same-URL state transitions remain a blind spot | Language-agnostic | High |
| 1.3.4 | `orientation.check.js` | Static | Strongest Node static rule: manifest, viewport, scripts, CSS media rules, writing mode, and structural evidence | Runtime/external-script locks and layout behavior that only appears after interaction remain partial | Language-agnostic; evidence preservation now improved | Medium |
| 2.5.2 | `pointer-cancellation.check.js` | Static | Good for inline down-event actions and matching up-event safeguards | Framework listeners and non-inline event wiring remain weakly visible | Config-backed EN/JA via `checks.pointer_cancellation` | Medium |
| 3.1.6 | `pronunciation.check.js` | Static | Good CJK detection plus ruby-coverage analysis for page and section scope | Furigana outside `<ruby>`, SVG text, and post-load annotation remain out of scope | Config-backed EN/JA and shared CJK settings | Medium |
| 3.3.7 | `redundant-entry.check.js` | Static | Strong heuristic set for repeated personal-data fields, confirmation exemptions, and reuse controls | Similarity/process heuristics can still false-positive; dynamic prefill and storage-backed reuse are invisible | Japanese process/reuse phrases are still source-driven | High |
| 4.1.3 | `status-messages.check.js` | Static | Good for live-region presence, dynamic-context detection, and `aria-atomic` checks | Runtime-only status updates remain invisible to static DOM review | One remaining JP search-result pattern is still source-driven | Medium |
| 1.4.1 | `use-of-color.check.js` | Static | Good inline-link cue detection across underline, border, outline, weight, style, and background changes | Shadow DOM, canvas-rendered links, and icon-only distinction remain weak | Language-agnostic | Medium |

### Node-level Remaining Structural Gaps

- The remaining source-driven Japanese Node rules are the highest-priority parity risk:
  - `accessible-auth.check.js`
  - `link-purpose.check.js`
  - `redundant-entry.check.js`
  - `status-messages.check.js`
- Node still does not expose a universal semantic failure contract. Most rule outputs still rely on rendered prose instead of a frontend-safe `reason_code` and `reason_params`.

---

## Python Crawlers and Extraction Layer

| Component | Role in current system | Current strength | Main limitation or bug risk | JP / config status | Priority |
| --- | --- | --- | --- | --- | --- |
| `context_factory.py` | Shared Playwright context creation for crawlers | Centralizes HTTPS and SSRF defaults | If `ignore_https_errors` is turned off, bad target certs still fail by design; that is correct but must be handled clearly upstream | Shared config-backed | Medium |
| `_ssrf_guard.py` | Blocks private-IP and redirect abuse during browsing | Essential baseline hardening for Node/Python parity | Like any SSRF guard, it is protective but not a complete substitute for broader network isolation | Language-agnostic | Medium |
| `universal_page.py` | Primary production static extractor | Same-origin iframes, open shadow roots, structured warning capture, universal snapshot output | Cross-origin frames remain partial; runtime late content can still fall into `page_extract_failed` or warning-only extraction | Language-agnostic, shared-config-backed reporting/budgets | High |
| `snapshot_normalizer.py` | Converts universal raw snapshot into existing Pydantic model families | Lets old auditors run on the new production path without duplicate crawls | Any raw-schema evolution can silently drop or flatten evidence unless the normalizer evolves in lockstep | Language-agnostic | High |
| `crawler.py` (`AsyncImageCrawler`) | OCR, screenshots, image metadata, and multimodal entry point | Still the production owner of image/OCR work and contrast/image auditing | OCR budgets can skip assets on heavy pages; invisible or non-image-rendered content remains hard | OCR language behavior is partly source-driven | High |
| `rendered_layout_crawler.py` | Production rendered/layout evaluator driver | Owns orientation, reflow, resize-text, hover/focus, and focus-obscuration scenarios | Bounded by hover/focus candidate caps and timing windows; delayed or unusual UI states can still be missed | Uses shared crawler limits and CJK settings | High |
| `forms_crawler.py` | Legacy direct form extractor | Useful compatibility path and fallback mental model | Not the main production path now, so drift risk is real if maintained less aggressively than universal extraction | Language handling is mostly code-driven in downstream auditor, not here | Medium |
| `interactive_crawler.py` | Legacy direct interactive-element extractor | Useful for compatibility and isolated testing | Same production-drift risk as `forms_crawler.py` | Language-agnostic | Medium |
| `media_crawler.py` | Legacy direct media extractor | Preserves a dedicated media-record contract | Same drift risk versus universal snapshot and normalizer path | Language-agnostic | Medium |
| `moving_content_crawler.py` | Legacy direct moving-content extractor | Clear standalone model for pause/stop/hide inputs | Same drift risk versus universal extraction | Language-agnostic | Medium |
| `sensory_crawler.py` | Legacy direct sensory extractor | Clear specialized contract for sensory-auditor input | Same drift risk versus universal extraction | Language-agnostic | Medium |
| `target_size_crawler.py` | Legacy direct target-size extractor | Good compatibility path for hitbox records | Same drift risk versus universal extraction | Language-agnostic | Medium |
| `text_spacing_crawler.py` | Legacy direct text-spacing extractor | Useful compatibility path for the older model contract | Same drift risk versus universal extraction and rendered text-spacing evaluation | Uses shared CJK settings indirectly only at rendered stage | Medium |

### Crawler-level Failure Reasons That Still Matter

| Failure family | Current behavior | What still needs care |
| --- | --- | --- |
| Bad TLS certificate | Shared `ignore_https_errors` prevents the normal frontend break path | Explicit secure-mode runs will still fail on bad certs by design |
| Cross-origin frame | Preserved as warnings instead of silent loss | Static findings may still be incomplete |
| Extraction exception | `page_extract_failed` warnings preserve failure provenance | Frontend should continue surfacing warnings, not treat partial extraction as full success |
| OCR budget exceeded | Selected-vs-skipped images are logged | Findings remain only as good as the selected sample on heavy pages |
| Delayed runtime state | Rendered crawler probes many states, but not all | Late timers, hidden steps, and unusual state transitions still need fixture coverage |

---

## Python Auditors and Rendered Evaluators

| SC(s) | File | Stage | Current detection strength | Main limitation or bug risk | JP / config status | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| 3.3.1, 3.3.2, partial 4.1.2 | `forms/form_auditor.py` | Universal static | Good label, required-state, describedby, live-region, and autocomplete checks | Required-field heuristics are still text-pattern-driven; format guidance and richer instructions are still weak | Japanese required markers such as `必須` and `必要` are still source-driven | High |
| 2.5.3 | `input_modalities/label_in_name_auditor.py` | Universal static | Good normalization and visible-label vs accessible-name comparison | Embedded icons/images and richer speech-command phrasing remain hard | CJK behavior exists, but still source-driven rather than shared-config-backed | Medium |
| 2.5.8 | `input_modalities/target_size_auditor.py` | Universal static | Strong baseline for 24x24 size and core exemptions | Equivalent interaction points remain out of scope | Language-agnostic | Medium |
| Structural 1.4.12 support | `input_modalities/text_spacing_auditor.py` | Universal static | Useful structural-risk pre-check before rendered text-spacing evaluation | It is not a substitute for the rendered text-spacing pass | Language-agnostic | Low |
| 1.2.1 | `media/media_auditor.py` | Universal static | Good transcript discovery through tracks, nearby links, details, and aria-described alternatives | Still heuristic; cannot prove transcript quality or fetch-authenticated content reliably | Japanese transcript keywords are still source-driven | High |
| 1.2.1 quality gate | `media/quality_engine.py` | Local quality evaluation | Valuable local transcript-quality scoring when audio and transcript are both available | Heavy dependency path; speaker/non-speech checks still skew toward English-style transcript conventions | Mostly source-driven and not Japanese-config-backed | High |
| 1.1.1, 1.4.5, 1.4.11, partial 4.1.2 | `non_text/alttext.py` | Multimodal | Broadest Python rule file: alt text, image-of-text, non-text contrast support, and some role/name checks | OCR match uses substring token presence, which is fragile for CJK and can false-pass or false-review | OCR and matching are not yet shared-config-driven for Japanese | High |
| 1.4.3, 1.4.6, 1.4.11 | `non_text/contrast_analyser.py` | Multimodal | Strong luminance and segmentation baseline for contrast analysis | Complex backgrounds and multi-color text/components still challenge the segmentation model | Language-agnostic | Medium |
| 1.3.3 | `non_text/sensory_auditor.py` | Universal static | Strongest language-aware Python rule; has deep English and Japanese sensory-instruction handling | Large code-driven regex/NLP surface is hard to tune and hard to keep consistent with Node | Japanese handling is extensive but still source-driven, including `ja_core_news_sm` usage | High |
| 2.2.2 | `timing/pause_stop_hide_auditor.py` | Universal static | Good autoplay/duration/control heuristic set | Timer-driven background updates and icon-only controls remain weak | Language-agnostic | Medium |
| 1.3.4 | `rendered/evaluators/orientation.py` | Rendered | Good comparison of portrait vs landscape rendered states, overlays, clipping, and content loss | Does not directly inspect manifest/meta locks; complements Node but does not replace it | Language-agnostic | Medium |
| 1.4.10 | `rendered/evaluators/reflow.py` | Rendered | Strong for 320px horizontal-scroll failures and exemption handling | Hidden or interaction-triggered overflow can still be missed | Language-agnostic | Medium |
| 1.4.4 | `rendered/evaluators/resize_text.py` | Rendered | Good baseline vs 200% zoom comparison | Overlap and vertical clipping remain weaker than horizontal/page-scroll checks | Language-agnostic | Medium |
| 1.4.12 | `rendered/evaluators/text_spacing.py` | Rendered | Strongest actual text-spacing evaluation path; checks clipping and layout break under required overrides | Overlap and complex layout interactions remain imperfect | Uses shared `crawler.language.cjk_langs` for CJK-aware override behavior | Medium |
| 1.4.13 | `rendered/evaluators/hover_focus_content.py` | Rendered | Good for dismissible, hoverable, persistent popup behavior | Focus-only behavior that differs from hover can still be under-modeled | Language-agnostic | Medium |
| 2.4.11 | `rendered/evaluators/focus_not_obscured_minimum.py` | Rendered | Strong overlap-ratio based minimum-obscuration check | Transparent overlays and small-element edge cases remain tricky | Language-agnostic | Medium |
| 2.4.12 | `rendered/evaluators/focus_not_obscured_enhanced.py` | Rendered | Strong enhanced-threshold check built on the same rendered path | Very small but meaningful overlap can still be hard to classify cleanly | Language-agnostic | Medium |

### Python-level Remaining Structural Gaps

- The highest-value Python language/config migrations still pending are:
  - `forms/form_auditor.py`
  - `media/media_auditor.py`
  - `media/quality_engine.py`
  - `non_text/alttext.py`
  - `non_text/sensory_auditor.py`
  - OCR adapters in `text_detector/ocrbase.py` and `text_detector/paddleocrbase.py`
- Python remains more language-aware than Node for sensory analysis, but it achieves that through source code, not through a shared universal rule asset layer.

---

## Japanese-language Analysis

### What is already shared-config-backed

The repo-root `config/universal.yml` is now the common reusable source for:

- `browser.ignore_https_errors`
- `language.supported`
- `crawler.language.cjk_langs`
- `checks.pronunciation`
- `checks.audio_transcript`
- `checks.multiple_ways`
- `checks.consistent_help`
- `checks.error_prevention`
- `checks.error_suggestion`
- `checks.location`
- `checks.pointer_cancellation`

This is the right direction because it makes frontend behavior, crawler behavior, and Node custom-rule language behavior move from the same configuration plane.

### Node gaps still specific to Japanese

These Node rules still keep Japanese logic in source and should move next:

- `accessible-auth.check.js`
- `link-purpose.check.js`
- `redundant-entry.check.js`
- `status-messages.check.js`

Practical risk:

- Changing Japanese copy still requires JS edits.
- EN/JA fixture reuse remains incomplete.
- The same concept can drift between Node and Python because the canonical wording is not yet centralized.

### Python gaps still specific to Japanese

These Python areas still keep Japanese or CJK logic in source instead of shared config:

- `forms/form_auditor.py` required markers
- `media/media_auditor.py` transcript keywords
- `media/quality_engine.py` transcript-quality assumptions
- `non_text/alttext.py` OCR-token matching behavior
- `non_text/sensory_auditor.py` JP regex sets and `ja_core_news_sm`
- `text_detector/ocrbase.py` and `text_detector/paddleocrbase.py` JP alias handling

Practical risk:

- Python is still the more advanced Japanese path for some rules, but it is not reusable enough.
- Rule behavior remains harder to explain and fixture because the assets are spread across code rather than one universal config surface.

### Current parity conclusion

The codebase is no longer in the earlier "Node is English, Python is Japanese-aware" split. It is now in a transitional state:

- Node has started using shared EN/JA assets correctly for selected rules.
- Python still contains the deeper Japanese logic, but much of it is code-driven.
- Full parity still requires moving remaining JP keyword lists, regex families, and reason templates into shared config plus a shared reason contract.

---

## Highest-priority Backlog

### 1. Universal failure contract

Add a shared result shape for both Node and Python:

- `reason_code`
- `reason_params`
- `reason_text`

Why this is first:

- It makes frontend rendering stable.
- It makes EN/JA translation deterministic.
- It makes fixtures reusable across Node and Python.

### 2. Finish Node JP migration

Move the remaining Node source-driven Japanese assets into `config/universal.yml` and route them through shared helpers.

Why this matters:

- Node is already on the correct helper path, so these are mostly migration tasks, not architecture changes.

### 3. Move Python JP heuristics to shared config

Start with the highest duplication and highest drift surfaces:

- media keywords
- form required markers
- sensory keyword families
- OCR language aliases

Why this matters:

- Python is currently richer than Node for some language-sensitive logic, but it is harder to maintain.

### 4. Add cross-service EN/JA fixtures

Minimum fixture contract that should exist for every localized rule family:

- same `lang` request
- same `criterion_name`
- same `suggested_fix`
- same `reason_code`
- same rendered `reason_text`
- stable evidence fields

### 5. Keep crawler warnings first-class in frontend

Do not collapse these to a generic success/fail binary:

- TLS/cert handling state
- cross-origin frame warnings
- `page_extract_failed`
- OCR budget skips

Why this matters:

- The current crawler model is intentionally partial in some environments.
- Honest warning propagation is better than pretending extraction was complete.

---

## Bottom Line

The current production architecture is substantially better than the previous Node-only report captured. The major remaining work is not basic crawler stability anymore; it is consistency work:

- one shared reason contract
- one shared language/config surface
- one reusable EN/JA fixture strategy

Until those three pieces are completed, the system will remain strong in coverage but uneven in failure semantics, Japanese parity, and frontend explainability.
