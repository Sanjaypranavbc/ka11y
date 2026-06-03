# Crawler Fixture Plan

Date: `2026-04-06`

Status: `proposal only`

This document is the pre-approval plan for crawler fixes. No crawler code or crawler docs have been changed yet as part of this plan.

## Evidence base

Real-site evidence already collected from the live rerun campaign:

- `wcag_reports/raw/ten_site_deep_en_20260406_rerun/`
- `wcag_reports/ten_site_deep_en_20260406_rerun/`
- `a11y-python/logs/AC_2026-04-06.log`
- `wcag_reports/crawler_recheck_20260406/`

Primary reproduced issues from real sites:

- `govt.nz`: challenge page / WAF iframe (`/_Incapsula_Resource`) was audited as if it were the real page
- `ookla.com`: image crawler exceeded `300s`, partial image set used
- `mozilla.org`: image crawler exceeded `300s`, partial image set used
- `css-tricks.com`: navigation degraded after `Page.goto` timeout and fallback
- final live run: late Playwright `TargetClosedError` after reports were already written

## Re-run check update

I re-ran the crawler check on the high-risk site set and stored the refreshed artifacts under:

- `wcag_reports/crawler_recheck_20260406/govt_nz_recheck/`
- `wcag_reports/crawler_recheck_20260406/css_tricks_com_recheck/`
- `wcag_reports/crawler_recheck_20260406/ookla_com_recheck/`
- `wcag_reports/crawler_recheck_20260406/mozilla_org_recheck/`

### Re-run findings

#### `govt.nz`

- `recheck_summary.json` shows `warnings: []`
- `image_audit` still completed with `findings_count: 0`
- universal snapshot still extracted real-looking content (`forms=1`, `interactive=39`, `target_sizes=38`, `text_spacing=184`) while the image crawler captured zero images from the effective page shell

Conclusion:

- the challenge/interstitial problem is still present
- it is still not surfaced as a persisted warning

#### `css-tricks.com`

- `wcag_reports/crawler_recheck_20260406/css_tricks_com_recheck/recheck_summary.json` shows `warnings: []`
- `a11y-python/logs/AC_2026-04-06.log` now records repeated:
  - `networkidle timeout`
  - `readyState timeout`
- the rerun console also surfaced repeated `Task was destroyed but it is pending!` route-task leaks during the image crawl

Conclusion:

- crawler degradation is broader than a single `Page.goto` fallback
- route/stabilizer cleanup is not fully clean under heavy real pages

#### `ookla.com`

- `wcag_reports/crawler_recheck_20260406/ookla_com_recheck/recheck_summary.json` still shows `warnings: []`
- `a11y-python/logs/AC_2026-04-06.log` records another partial-image-set warning for `crawled_images/ookla_com_0406_1822`
- the rerun also showed transient asset download failures during capture
- a late `TargetClosedError` was reproduced again after the timeout path
- only `2` images made it into the final OCR/audit phase of this rerun

Conclusion:

- the partial-image-set bug is still active
- it is still not persisted into warnings
- timeout cleanup is still unsafe

#### `mozilla.org`

- `wcag_reports/crawler_recheck_20260406/mozilla_org_recheck/recheck_summary.json` still shows `warnings: []`
- `a11y-python/logs/AC_2026-04-06.log` records another partial-image-set warning for `crawled_images/mozilla_org_0407_1011`
- the rerun reproduced another late `TargetClosedError`
- OCR then failed to reopen multiple crawler-produced `.png` files with `Could not find a backend to open ... .png`

Conclusion:

- the timeout path is still producing partial image sets
- some saved image artifacts are likely incomplete or invalid by the time OCR consumes them
- this is now a distinct fixture, not just a side note

## Fixtures proposed

### Fixture 1: unify crawler navigation and stabilization

Problem:

- `forms_crawler.py`, `interactive_crawler.py`, `media_crawler.py`, `moving_content_crawler.py`, `target_size_crawler.py`, and `text_spacing_crawler.py` each use their own `page.goto(...)` plus fixed `wait_for_timeout(2000)` logic.
- `universal_page.py` already has a better retry chain and post-load stabilization path, but it is not reused consistently.

Fix to implement:

- introduce a shared navigation helper for non-image crawlers
- remove duplicated one-off retry logic where possible
- replace fixed sleeps with shared stabilization where safe
- make `text_spacing_crawler.py` consistent with the rest of the stack

Expected outcome:

- fewer inconsistent crawl states across static crawlers
- fewer false differences caused by one crawler seeing a hydrated page while another sees only DOM-ready state

### Fixture 2: detect challenge/interstitial pages before auditing

Problem:

- `govt.nz` produced findings against `#main-iframe` and `/_Incapsula_Resource...`
- current crawlers treat that response as a valid page instead of a blocked/interstitial state

Fix to implement:

- add challenge/interstitial detection during navigation
- detect common patterns such as WAF iframes, captcha markers, challenge resources, access-denied shells
- emit explicit degradation warnings and short-circuit normal page-level conclusions where appropriate

Expected outcome:

- challenge pages stop polluting WCAG findings with false page-structure failures

### Fixture 3: persist degradation warnings into saved artifacts

Problem:

- logs show partial image sets for `ookla.com` and `mozilla.org`
- saved `warnings.json` files stay empty
- frontend/export consumers cannot tell that coverage was partial

Fix to implement:

- route crawler degradation events into persisted stage/job warnings
- include partial-image-set, fallback-navigation, and challenge-page states
- verify they reach raw artifacts and combined report warnings

Expected outcome:

- degraded runs become visible in APIs, saved artifacts, and frontend/report consumers

### Fixture 4: make image crawler timeout handling cancellation-safe

Problem:

- image crawl is wrapped in `asyncio.wait_for(...)` with a `300s` cap
- after timeout, the pipeline proceeds on partial images, but a late Playwright `TargetClosedError` still appeared after completion
- this strongly suggests cancellation/cleanup is not fully coordinated in the image crawl path

Fix to implement:

- make `AsyncImageCrawler.crawl_page()` and screenshot loops cancellation-safe
- ensure page/context/browser cleanup is deterministic under timeout cancellation
- suppress or capture post-close screenshot errors as warnings instead of leaking them after successful completion

Expected outcome:

- no late Playwright cleanup exceptions after successful report generation

### Fixture 5: reduce image crawler wall time on heavy pages

Problem:

- `ookla.com` and `mozilla.org` hit the image crawler cap
- image-heavy sites dominate overall runtime

Fix to implement:

- audit screenshot/download sequencing inside `crawler.py`
- avoid spending too much time on low-value or duplicate captures
- tighten slow fallback paths for icon/button/image capture
- consider bounded per-element retries and earlier skip decisions

Expected outcome:

- fewer partial image-set runs
- lower Python runtime on image-heavy sites

### Fixture 6: document the actual crawler architecture in `a11y-docs`

Problem:

- docs describe each crawler in isolation, but they do not explain the current split between:
  - universal snapshot-backed static crawlers
  - separate image crawler
  - rendered-layout crawler with HAR reuse
  - degraded-run behavior

Fix to implement:

- update crawler docs to reflect the real execution model
- add degradation/timeout/challenge-page notes
- document which crawlers now use shared navigation/stabilization and which do not

Expected outcome:

- docs match runtime behavior and make crawler limitations explicit

### Fixture 7: validate screenshot file integrity before OCR consumes crawler output

Problem:

- the rerun on `mozilla.org` reproduced OCR file-open failures on crawler-produced `.png` assets after the partial-image-set timeout path
- earlier logs also showed the same class of failure on other sites

Fix to implement:

- validate screenshot/download outputs before handing them to OCR
- skip zero-byte or unreadable image files
- make timeout/cancellation paths leave either a valid file or no file
- surface invalid-image skips as warnings instead of silent downstream OCR errors

Expected outcome:

- OCR only receives valid image assets
- partial timeout paths stop leaving unreadable crawler artifacts behind

## File-by-file review

### Review: `a11y-python/a11y/crawler/crawler.py`

Current state:

- strongest crawler in terms of feature coverage
- also the most operationally risky
- owns page load, lazy-load triggers, hidden-content expansion, five capture passes, downloading, screenshots, and classification

Review findings:

- navigation is still bespoke and not aligned with `universal_page.py`
- the fallback log message says `'load' timed out` while the code is already using `wait_until="domcontentloaded"`, which is misleading
- the crawl is large enough that stage-level cancellation can interrupt mid-screenshot sequence
- image capture policy is expensive on large marketing pages
- degradation is logged but not propagated into saved warnings

Proposed action:

- highest-priority crawler file to fix first

### Review: `a11y-python/a11y/crawler/universal_page.py`

Current state:

- best shared navigation/stabilization logic in the crawler layer
- already has retry chain, SPA waits, and carousel waits
- already feeds most static crawlers through snapshot reuse

Review findings:

- this is the right place to centralize common navigation behavior
- the rest of the crawler layer is not fully aligned to it
- challenge/interstitial detection should likely live here or beside it, not be duplicated

Proposed action:

- use this as the central path for crawler load-state consistency

### Review: `a11y-python/a11y/crawler/forms_crawler.py`

Current state:

- snapshot-aware
- fallback path still uses direct `goto` plus fixed `2000ms` wait

Review findings:

- operationally okay, but inconsistent with the shared navigation/stabilization strategy
- a fixed sleep is a weak proxy for hydration/render completion

Proposed action:

- move fallback crawling onto shared navigation helper

### Review: `a11y-python/a11y/crawler/interactive_crawler.py`

Current state:

- same pattern as forms crawler

Review findings:

- same navigation inconsistency
- because `2.5.3` is currently noisy, crawler determinism matters more here

Proposed action:

- align navigation/stabilization with shared helper before further `2.5.3` rule work

### Review: `a11y-python/a11y/crawler/media_crawler.py`

Current state:

- duplicated retry chain
- snapshot-aware

Review findings:

- lower-risk crawler, but still duplicates navigation logic
- one retry branch repeats `domcontentloaded` twice before `commit`, which is unnecessary

Proposed action:

- simplify onto shared navigation helper

### Review: `a11y-python/a11y/crawler/moving_content_crawler.py`

Current state:

- duplicated retry chain
- post-load fixed wait of `2000ms`

Review findings:

- moving-content detection is timing-sensitive
- using fixed waits instead of shared stabilization can create non-deterministic results on JS-heavy pages

Proposed action:

- align with shared stabilization, then retest on real animated/carousel pages

### Review: `a11y-python/a11y/crawler/target_size_crawler.py`

Current state:

- duplicated retry chain
- static fixed wait

Review findings:

- lower operational risk than image crawler
- still vulnerable to hydration timing inconsistencies

Proposed action:

- move to shared navigation/stabilization

### Review: `a11y-python/a11y/crawler/text_spacing_crawler.py`

Current state:

- weakest navigation path in the crawler layer
- no explicit timeout in `page.goto`
- no fallback chain
- no stabilization beyond direct DOM-ready load

Review findings:

- highest-risk non-image crawler from an operational perspective
- especially problematic because `1.4.12` warning volume is already very high

Proposed action:

- fix immediately after image crawler

### Review: `a11y-python/a11y/crawler/rendered_layout_crawler.py`

Current state:

- uses its own `_load_and_stabilize()` plus HAR replay path
- does not appear to be the source of the main crawl-time failures found in the latest run

Review findings:

- structurally stronger than most single-purpose crawlers
- worth reviewing only after image crawler and shared navigation issues are addressed

Proposed action:

- secondary priority

### Review: `a11y-python/a11y/accessibility/rendered/stabilizer.py`

Current state:

- shared rendered-page stabilizer used by the rendered-layout pipeline

Review findings:

- the re-run on `css-tricks.com` reproduced repeated `networkidle` and `readyState` degradation
- this does not currently flow into persisted warnings
- stabilizer degradation is operationally important enough to surface in crawler diagnostics

Proposed action:

- review warning propagation and interaction with shared navigation/stabilization

### Review: `a11y-python/a11y/text_detector/text_detector.py`

Current state:

- consumes crawler output directly for OCR and contrast analysis

Review findings:

- the re-run on `mozilla.org` reproduced OCR failures reopening crawler-generated `.png` assets
- this means the crawler/OCR handoff is not robust under partial-timeout conditions
- OCR currently logs the issue but the combined job still does not persist the degradation clearly

Proposed action:

- add this file to the first fix pass for crawler-output integrity and warning surfacing

### Review: `a11y-python/a11y/api/v1/combined/stages.py`

Current state:

- orchestrates timeouts and stage fallbacks
- image stage allows partial-set continuation after timeout

Review findings:

- current behavior is resilient, but not transparent enough
- stage warnings are not fully persisted to the saved artifacts
- timeout handling should integrate with crawler cleanup more explicitly

Proposed action:

- update warning propagation together with crawler timeout fixes

### Review: `a11y-docs/guides/crawlers.mdx`

Current state:

- good per-crawler field reference
- incomplete on runtime architecture and degraded behavior

Review findings:

- missing universal snapshot/HAR reuse explanation
- missing challenge-page and partial-image-set limitations
- missing guidance on how real-site fallback states should be interpreted

Proposed action:

- update after code fixes, not before

## Proposed implementation order

1. `crawler.py`
2. `stages.py`
3. `universal_page.py`
4. `text_detector.py`
5. `stabilizer.py`
6. `text_spacing_crawler.py`
7. `forms_crawler.py`
8. `interactive_crawler.py`
9. `media_crawler.py`
10. `moving_content_crawler.py`
11. `target_size_crawler.py`
12. `a11y-docs/guides/crawlers.mdx`

## Explicit non-goals for the first fix pass

- no rule-logic changes for `2.5.3`, `1.1.1`, `4.1.2`, or `2.4.11`/`2.4.12` in this pass
- no frontend changes in this pass
- no workbook/report format changes in this pass

## Approval request

If you approve this plan, the next step will be:

1. implement the crawler fixes in the order above
2. run real-site validation loops again
3. update crawler docs to match the new behavior
4. provide a code review summary for each changed file after the fix pass
