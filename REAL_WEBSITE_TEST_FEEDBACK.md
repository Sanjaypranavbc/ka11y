# Real Website Test Feedback

Date: 2026-04-14

Tester module:
- `a11y-python/scripts/live_stage_audit.py`
- Plan: `a11y-python/scripts/live_stage_plan.realtime_image_smoke.yml`

Scope:
- Live combined smoke runs against `https://www.gov.uk/` (`en`) and `https://www.kao.com/jp/` (`ja`)
- Node flat analysis enabled
- Python image audit enabled
- OCR intentionally disabled to validate the frontend image path when `contrast_report` is empty

Artifacts:
- Plan summary: `/tmp/a11y_realtime_image_smoke_20260414/live_stage_summary.json`
- GOV.UK combined report: `crawled_images/gov_uk_0414_1027_162a551e_combined/combined_report.json`
- GOV.UK step log: `crawled_images/gov_uk_0414_1027_162a551e_combined/step_logs/combined_execution_steps.jsonl`
- Kao JP combined report: `crawled_images/kao_com_0414_1028_bb41980c_combined/combined_report.json`
- Kao JP step log: `crawled_images/kao_com_0414_1028_bb41980c_combined/step_logs/combined_execution_steps.jsonl`

## Live Result Summary

| Run | URL | Lang | Status | Violations | Needs Review | Passes | Image Audit Images | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `govuk_image_smoke` | `https://www.gov.uk/` | `en` | `completed` | 8 | 8 | 835 | 17 | `contrast_report` empty by design, `image_audit_report` present |
| `kao_jp_image_smoke` | `https://www.kao.com/jp/` | `ja` | `completed` | 79 | 37 | 965 | 47 | JP image audit present, Node JP output verified after restart |

Key payload checks from the combined reports:
- `gov.uk`: `image_audit_report.images = 17`, `contrast_report = null`
- `kao.com/jp`: `image_audit_report.images = 47`, `contrast_report = null`
- Both combined reports include per-image `image_url`, so the frontend can render audited images even when OCR/contrast data is absent

## Bugs Identified

### 1. Python/frontend image bug: image audit existed, but the frontend had no image data

Status: fixed

Reproduction:
- Run combined audit with `run_image_audit=true` and `run_ocr=false`
- Python image crawler and alt-text auditor complete successfully
- `contrast_report` is empty because OCR did not run
- Old frontend path depended on `contrast_report` only, so the image tab appeared empty even when image audit findings existed

Live evidence:
- `gov.uk` produced `17` audited images and `5` failed image checks
- `kao.com/jp` produced `47` audited images and `31` failed image checks
- In both runs, `contrast_report` is `null`, but `image_audit_report.images[*].image_url` is present

Code changes behind the fix:
- Python report surfacing:
  - `a11y-python/a11y/api/v1/combined/findings.py`
  - `a11y-python/a11y/api/v1/combined/stages.py`
  - `a11y-python/a11y/api/v1/combined/runner.py`
  - `a11y-python/a11y/api/v1/combined/report.py`
  - `a11y-python/a11y/api/v1/combined/routes.py`
- Frontend consumption:
  - `a11y-frontend-sdk/src/types/audit.ts`
  - `a11y-frontend-sdk/src/hooks/useAudit.ts`
  - `a11y-frontend-sdk/src/pages/Index.tsx`
  - `a11y-frontend-sdk/src/components/audit/ImageVisualisationTab.tsx`

Result:
- “No image audit happened” no longer reproduces on these live sites
- The frontend now has a fallback image view driven by `image_audit_report` when OCR/contrast output is absent

### 2. Node Japanese localization bug: custom-rule reasons still leaked English fragments

Status: fixed

Reproduction on live JP output before restarting the Node API:
- `custom-focus-appearance` emitted English detail fragments such as `outline-width ... (area requirement)` and `no-indicator`
- `custom-meaningful-sequence` emitted `Container has mixed floated...`
- `custom-keyboard-trap` emitted `arrow-key trap in [role="tablist"]`

Code changes:
- `a11y-node/src/custom-checks/focus-appearance.check.js`
- `a11y-node/src/custom-checks/meaningful-sequence.check.js`
- `a11y-node/src/custom-checks/keyboard-trap.check.js`

Regression coverage added:
- `a11y-node/tests/custom-checks/focus-appearance.check.test.js`
- `a11y-node/tests/custom-checks/meaningful-sequence.check.test.js`
- `a11y-node/tests/custom-checks/keyboard-trap.check.test.js`

Verification:
- Targeted Jest suites passed
- After restarting `a11y-node`, a fresh live `POST /api/v1/analyse-url-flat` for `https://www.kao.com/jp/` with `lang=ja` returned `mixedLanguageHits = []`

### 3. Node live-site latency remains high

Status: open limitation

Evidence from live step logs:
- `gov.uk`
  - `combined_job` start: `2026-04-14T04:57:39.976297+00:00`
  - `axe_core_summary`: `2026-04-14T04:58:24.445140+00:00`
  - Approximate Node flat stage wall time: `44.5s`
- `kao.com/jp`
  - `combined_job` start: `2026-04-14T04:58:24.489511+00:00`
  - `axe_core_summary`: `2026-04-14T04:59:14.848491+00:00`
  - Approximate Node flat stage wall time: `50.4s`

Impact:
- The frontend receives correct results, but public-site jobs still feel slow because the Node flat stage is the longest branch

This run did not attempt a performance rewrite. The latency is documented here as the main remaining production limitation from the live smoke run.

## Verification Performed

- `pytest -q a11y-python/tests/test_image_audit_stage.py a11y-python/tests/test_crawler_settings.py`
  - `5 passed`
- `python -m py_compile ...` on the touched Python modules
  - passed
- `npx jest --runInBand tests/custom-checks/focus-appearance.check.test.js tests/custom-checks/meaningful-sequence.check.test.js tests/custom-checks/keyboard-trap.check.test.js`
  - `22 passed`
- `npm run build` in `a11y-frontend-sdk`
  - passed
- Live smoke plan completed successfully for both sites
- Direct live JP Node recheck after restart
  - `statusCode = 200`
  - `custom = 26`
  - `mixedLanguageHits = []`

## Short Conclusion

The image-audit frontend bug is fixed in the live combined payload path. Public English and Japanese sites now return image audit data even when OCR is off, and the frontend has image URLs to render that data.

The remaining Node bug in Japanese custom-rule reasons is also fixed after patching the structured detail renderers and restarting the Node API. The main issue still open after this run is real-site Node latency, not correctness.
