# ka11y — Release Notes

**Release:** 2026-09-15 (POC build, `production` branch)
**Components:** ka11y-python (audit engine), ka11y-ui (dashboard), Docker deployment
**Prepared for:** Kao Corporation — accessibility audit POC

Each item below is a closed action item. IDs are stable and can be referenced in acceptance testing.

---

## 1. Audit engine — performance and reliability

| ID | Status | Item |
|----|--------|------|
| R-01 | Fixed | **Every page was audited twice.** The engine navigated each page once to collect media and links, then a second time, in a second browser, to collect images. Both passes are now one visit per page: media, links, page language and image capture are collected together. Multi-page audits use half the page loads and one browser process instead of two. |
| R-02 | Fixed | **Bot protection could serve the crawler a challenge page.** The image crawler carried an anti-bot browser profile but the main crawler did not, so sites behind Akamai or Cloudflare could return a "Just a moment…" page, which audits as an empty page with no findings. The same profile now applies to every browser session. Verified on `kao.com/global/en/`: 356 elements, 50 image elements, 35 captured. |
| R-03 | Fixed | **Page language was never recorded per page.** OCR engine selection (PaddleOCR for Japanese, EasyOCR for other languages) fell back to the language of the whole run. Each page's `<html lang>` is now captured, so Japanese pages inside an English crawl, and the reverse, are read with the correct engine. |
| R-04 | Fixed | **A page whose final URL could not be read was reported as `about:blank`.** Findings are now stamped with the requested URL in that case. |
| R-05 | Improved | **Long crawls no longer time out the whole audit.** The crawl has a wall-clock budget (300 s floor, scaled per discovered page, 600 s ceiling). When it is reached the crawl stops opening new pages, finishes the pages in flight, and the audit continues on what was gathered with a `crawl_time_budget_exceeded` warning in the report. |
| R-06 | Improved | **Browser crash recovery.** If the audit browser process dies, the service relaunches it on the next audit instead of failing every audit until the service is restarted. Optional recycling by memory or age is available (off by default). |
| R-07 | Improved | **OCR text categories come from the crawler's own classification** (button, logo, informational) rather than from folder-name matching, so a storage-layout change can no longer silently re-categorise images. |
| R-08 | Improved | **All artefacts of one audit are in one folder.** Captured images, OCR output and the alt-text report now live under the job's own directory instead of a sibling timestamped folder. |
| R-09 | Changed | **Work with no consumer removed from every page visit.** Two per-page extractions whose output nothing read (unified-pipeline contexts, CSS background images) are off by default. They remain available behind configuration flags. |
| R-10 | Changed | **One concurrency setting for browser work.** Two separate limits guarded the same browser resource. `KA11Y_MAX_BROWSER_CONTEXTS` is now the single setting; the previous names (`KA11Y_MAX_BROWSERS`, `KA11Y_HEAVY_STAGE_CONCURRENCY`) are still accepted. |
| R-11 | Changed | **Security and consent handling consolidated.** The private-network request guard (SSRF), cookie-consent rejection and browser profile each existed twice and had drifted. There is now one implementation of each, covered by parity tests, used by every crawl. |
| R-12 | Changed | **External tracing off in Docker.** Arize / Phoenix tracing is disabled (`KA11Y_TRACING_ENABLED=0`) and the Phoenix service is not started. No audit data leaves the host. |
| R-13 | Deprecated | **Legacy endpoints `POST /api/v1/crawl/` and `POST /api/v1/pipeline/`.** Not used by the dashboard or SDK; they return a different result shape and use the standalone crawler. They are marked deprecated in the API documentation, log a warning on each call, and will be removed in a later release. |

## 2. Dashboard

| ID | Status | Item |
|----|--------|------|
| U-01 | Fixed | **Reason text is shown in bold** on the Fail, Needs Review and Passes tables. |
| U-02 | Fixed | **"No preview" image box removed for rules that do not involve an image.** Media findings (1.2.1, 1.2.2, 1.2.3, 1.4.2) and axe-core findings no longer show an empty image placeholder. Image-based findings keep the preview; an image rule whose capture failed still shows "No preview" so reviewers can see the gap. |

## 3. Verification

| ID | Status | Item |
|----|--------|------|
| V-01 | Done | **Live audit of `https://www.kao.com/global/en/`** through the API after the changes: one crawl of 29.7 s, image stage 0.03 s (no second navigation), OCR 102 s on 20 candidates, 51 images audited. 94 findings after level filtering: 6 violations, 32 needs review, 56 passes across 1.1.1, 1.2.x, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2. |
| V-02 | Done | **Automated tests:** 457 passed. One pre-existing failure unrelated to this release (`test_durable_store::test_rerun_creates_new_run_from_stored_params`). |
| V-03 | Added | **Findings regression tool** (`scripts/findings_diff.py`): captures findings for a fixed set of URLs and diffs a later run against them, so future changes can be checked for unintended finding changes. |
| V-04 | Added | **Per-step timing** for the image stage (crawl, OCR, alt-text audit) in the run timing table. |
| V-05 | Fixed | **Test suite isolated from live data.** Running the tests on a machine with a running ka11y server could restart that server's in-progress audit. Tests now use a throwaway database. |

## 4. Deployment notes

| Setting | Default | Purpose |
|---------|---------|---------|
| `KA11Y_MAX_BROWSER_CONTEXTS` | 2 | Concurrent audits sharing the one browser process (replaces `KA11Y_MAX_BROWSERS` / `KA11Y_HEAVY_STAGE_CONCURRENCY`, which still work). |
| `KA11Y_BROWSER_MAX_MEMORY_MB` / `KA11Y_BROWSER_MAX_LIFETIME_S` | 0 (off) | Recycle the browser between audits when it exceeds this memory or age. |
| `KA11Y_IMAGE_CRAWL_PER_PAGE_SECONDS` / `KA11Y_IMAGE_CRAWL_TIMEOUT_CEILING` | 20 / 600 | Crawl time budget per discovered page, and its ceiling. |
| `KA11Y_TRACING_ENABLED` | 0 in Docker | Set to 1 and restore the Phoenix service in `docker-compose.yml` to re-enable tracing. |

No database migration is required. Existing audit results remain readable; images captured by earlier releases are still served from their previous location.

## 5. Known limitations

- Sites that use a Cloudflare **managed challenge** (for example `w3.org`) block all headless browsers regardless of profile. Such pages audit as an empty document. This is unchanged from earlier releases and is now visible in the report as a near-empty page rather than a silent zero.
- Because pages are now audited after stricter readiness checks (network idle, framework hydration, DOM stability) and the same image-reveal steps as before, pages with late-loading content may report slightly more images than earlier releases. The regression tool in V-03 is provided to review such differences.
