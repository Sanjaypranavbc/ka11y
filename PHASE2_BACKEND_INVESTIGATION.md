# Backend / Functional Work — Investigation & Changes

**Date:** 2026-09-02
**Scope:** three items marked "to do" + one Phase-2 item left as investigation only.

| # | Item | Status |
|---|---|---|
| 1 | Item disappearance on status change + UI copy | ✅ Investigated + fixed |
| 2 | Exclude Kao logo images from WCAG 1.4.3 contrast checks | ✅ Implemented |
| 3 | Exclude OneTrust cookie-consent components from audit scope | ✅ Implemented (Python crawler + Node axe) |
| 4 | False-negative reporting mechanism | ⏸ Phase 2 — not implemented (notes below) |

---

## 1. Does a Needs-Review item disappear after a status change, or need a refresh?

### What was found (before this change)

File: `ka11y-ui/src/app/dashboard/needs-review/page.tsx`

- `updateStatus(id, status)` did **only** `setItems(prev => prev.map(...))` — it rewrote the
  row's `status` field in local React state. It did **not** remove the row.
- The rendered list (`items → byPage → filtered → visibleItems`) was filtered by **WCAG level**
  and **page URL** only — never by status. So after "Move to Pass" / "Move to Violation" the
  row **stayed on the Needs Review list**, only its status badge changed (Pending → Pass/Violation).
- The change was **local component state only**:
  - not written to `sessionStorage` (the audit lives under `kao:last-audit`, see
    `AuditDataContext.tsx`);
  - no API/network call anywhere — there is no status-persistence endpoint;
  - the Violations and Passes pages build their rows from `auditData` via `toViolationRows()` /
    `toPassesRows()`, so a "moved" item **never appeared there**.
- Lifetime of the change: lost on navigating away from the page and back (component remount
  re-seeds `items` from source), on browser refresh (audit re-parsed from `sessionStorage`,
  new object identity → `toNeedsReviewRows()` recomputes), and on re-running an audit.

**Answer:** it did **not** disappear at all, and a refresh **destroyed** the change rather than
revealing it.

### What was changed

- `needs-review/page.tsx`: the list is now derived from `pending = items.filter(status === "pending")`.
  A triaged row leaves the Needs Review list **immediately, with no refresh**. The "Showing X of Y
  (Z total)" line counts remaining pending items so it stays self-consistent after triage.
- `ka11y-ui/src/lib/i18n/translations.ts` (`needsReview.manualAction`, EN + JA): copy now states
  the true behaviour — the row leaves the list right away, the change applies to the current
  report view only, it is not saved, and a new audit rebuilds the list.

### Still open (Phase 2, if persistence is wanted)

There is no backend for triage decisions. Persisting "this needs-review item was accepted /
rejected" across refresh, across audits, or across users would need a store keyed by
(site, page_url, rule_id, element identity) and a write path from this page. Out of scope here.

---

## 2. Exclude Kao logo images from WCAG 1.4.3 (and 1.4.6)

### Context

WCAG 1.4.3 / 1.4.6 explicitly exempt **logotype** text from contrast minimums. A generic
exemption already exists on both engine paths:

- `alttext.py::generate_audit_report` — `sub_type == "logos"` (or `decorative`) → 1.4.3/1.4.6 = N/A.
- `findings.py::_contrast_to_findings` / `_contrast_enhanced_to_findings` — skip when
  `_infer_classification(original_path)` is `"logo"` / `"decorative"`.

**Gap:** both depend on the classifier tagging the mark as a logo. A Kao brand wordmark the
classifier files as `informative` (a plain `<img alt="Kao">` in the header, an inline SVG
wordmark, a filename with no "logo" keyword) is still contrast-checked and can false-fail,
dragging the element's `overall_status` to FAILED.

### What was changed

`ka11y-python/ka11y/accessibility/rules/non_text/alttext.py`

- New `_is_brand_logo(src, alt, title)` + module constants `_BRAND_LOGO_NAME_TOKENS`
  (`kao`, `花王`, `KAO Corporation`, …) and `_BRAND_LOGO_SRC_RE` (a brand token adjacent to a
  `logo`/`brand`/`wordmark` token in the src/filename, either order, separator-bounded so
  `kao` does not match inside unrelated words). Brand-agnostic in shape — more brands can be
  added to the two constants.
- `generate_audit_report`: the 1.4.3/1.4.6 exemption branch now also fires when
  `_is_brand_logo(src, alt_text, title)` is true (still gated on `not is_button`).

`ka11y-python/ka11y/api/v1/combined/findings.py`

- Both OCR contrast converters now also skip a detection when `_is_brand_logo()` matches, using
  the `src_by_filename` map already threaded in for the real-filename work. (`alt` is not
  available on the OCR result, so the src/filename patterns carry this path.)

Tests: `tests/test_alt_text_auditor.py` — `TestIsBrandLogo` (5 cases) +
`test_kao_brand_logo_exempt_from_contrast_even_when_misclassified` (a Kao wordmark classified
`informative` with baked-in OCR text → 1.4.3 and 1.4.6 come back N/A).

### Deliberately not done

Not touched: the classifier itself (teaching it to bucket the Kao mark as `logos`). The
audit-engine exemption is more direct and does not perturb classification-dependent behaviour
elsewhere. Not touched: `accessibility/pipeline/**` (dead per `PYTHON_RULE_ACCURACY_REVIEW.md`
§0).

---

## 3. Exclude OneTrust cookie-consent components from audit scope

### Context

OneTrust / Optanon is the CMP vendor's injected markup, present on every page — banner,
preference-centre modal (`#onetrust-pc-sdk`), and the **persistent "Cookie Settings" launcher**
(`#ot-sdk-btn-floating`, `.ot-floating-button`) that stays after the banner is dismissed. Kao
does not want it counted as findings.

**Before:**

- **Python crawler** (`crawler/optimized/engine.py`, the live image-audit path):
  `reject_cookies()` clicks reject-all and force-removes overlay containers matching
  `COOKIE_OVERLAY_SELECTORS`, but only when `is_visible()`. The persistent launcher and any
  hidden preference-centre nodes survive, and the element-extraction DOM walk had **no**
  consent-UI filter — so OneTrust nodes leaked into 1.1.1 / 1.4.3 / 1.4.11 / 4.1.2 findings.
  (`crawler/universal_page.py` has an `isConsentUi()` filter, but that path builds the unused
  `pipeline_pages` — see `PYTHON_RULE_ACCURACY_REVIEW.md` §0.)
- **Node engine** (`accessibility.service.js`): `axe.run(document, …)` scans the whole
  document. There is **no cookie handling at all** on the Node side, so the full OneTrust
  banner is in axe scope.

### What was changed

`ka11y-python/ka11y/crawler/optimized/engine.py`

- New `CONSENT_SCOPE_SEL` (OneTrust/Optanon id + class signatures, incl. `[id^="onetrust-"]`,
  `[id^="ot-sdk-"]`, `[class*="onetrust-"]`, `[class*="optanon"]`).
- Element-extraction DOM walk: `if (el.closest(CONSENT_SCOPE_SEL)) continue;` right after the
  existing tag/SVG skips — anything inside a OneTrust widget is dropped from the crawl
  regardless of visibility or removal timing.
- `COOKIE_OVERLAY_SELECTORS` extended with `#onetrust-pc-sdk`, `#ot-sdk-btn-floating`,
  `.ot-floating-button` for screenshot cleanup consistency.

`ka11y-python/ka11y/crawler/cookie_handler.py` — same three selectors added to `_OVERLAY_SELECTORS`
(keeps the two overlay lists in sync).

`ka11y-node/src/services/accessibility.service.js`

- New `CONSENT_EXCLUDE_SELECTORS` constant.
- `_runAxeWithTimeout` (the single funnel for every `axe.run` in this service): the in-page
  evaluate now builds an axe **context** with `exclude: [[sel], …]` for the OneTrust selectors
  **that are actually present on the page**; when none match, the context stays `document`
  (byte-for-byte the old behaviour). `include` still defaults to the whole document.

### Notes / limits

- Selector-prefix matching (`ot-sdk-*`, `onetrust-*`, `optanon*`) is a heuristic; a site is
  extremely unlikely to use those namespaces for its own content, but if a site embeds a
  first-party "Cookie preferences" link with `id="ot-sdk-btn"` in its own footer, that link is
  now also out of scope — which matches the stated intent ("OneTrust components are not Kao's
  responsibility").
- Other CMPs (Cookiebot, Didomi, SourcePoint, …) are still only handled by the existing
  reject/overlay-removal pass, not the new hard exclusion. Extend `CONSENT_SCOPE_SEL` /
  `CONSENT_EXCLUDE_SELECTORS` if the same treatment is wanted for them.

---

## 4. False-negative reporting mechanism — Phase 2, not implemented

Flagged by Kao as out of scope for the POC. Not started. When picked up, the shape is: a way
for a reviewer to mark "this passed check is actually wrong / this element was missed", captured
against the same (site, page_url, rule_id, element identity) key that a persisted triage store
(see §1) would use, and surfaced back into the report + a feedback queue. Depends on the same
missing persistence layer as §1, so the two are best planned together.

---

## Verification

- **Python:** `python -m pytest tests/ -q` → **404 passed**, 9 failed. All 9 failures pre-date
  this work (confirmed against a clean `HEAD` worktree): 5 × `test_api_smoke.py::TestAppStartup`
  (combined POST route returns 404 in the test app), `test_browser_pool` (missing
  `forms_crawler` module), `test_durable_store` re-run param assertion,
  `test_universal_page_cookie_filter`, `test_universal_page_js_loaders`. New: `TestIsBrandLogo`
  + brand-logo exemption test in `test_alt_text_auditor.py` (113 passed in that file).
- **Node:** `npx jest tests/services` → 4 passed, 3 failed; the 3 failures reproduce on a clean
  `HEAD` worktree (CSP-retry count + two criterion-filter assertions), unrelated to this change.
  `node -c accessibility.service.js` clean.
- **UI:** `npx tsc --noEmit` clean.
