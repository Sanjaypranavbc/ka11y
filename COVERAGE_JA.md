# Japanese Sites Coverage Report (English)

## Scope

This file tracks Japanese-site coverage readiness for the same implemented WCAG rule set in `a11y-node` and `a11y-python`.

- Default result language remains English unless `lang: "ja"` is explicitly requested.
- Japanese campaigns can now be run separately and exported independently.
- Heuristic checks are JP-augmented, not JP-perfect; treat `WARN` as manual-review priority.

## Current Rule Coverage (Implementation-Level)

- `a11y-node`: **52** SCs
- `a11y-python`: **27** SCs
- Combined: **63 / 87** SCs (**72.4%**)

## Japanese Enablement Added

- Node custom heuristics expanded with Japanese keyword support in:
  - `accessible-auth`, `audio-transcript`, `consistent-help`, `error-suggestion`
  - `multiple-ways`, `location`, `status-messages`, `images-of-text`
- Python heuristics expanded in:
  - rotate-overlay detection (`rendered/heuristics.py`)
  - pause/stop control detection (`moving_content_crawler.py`)
  - alt-text/logo/icon keyword logic (`alttext.py`)
  - classifier keyword sets (`classfier.py`)
  - CJK-safe Label-in-Name matching (`label_in_name_auditor.py`)
- OCR language selection now supports Japanese campaigns (`ja + en`) while preserving English default runs.

## Generate Separate Japanese Coverage Outputs

Run:

```bash
python scripts/wcag_audit_runner.py --lang en --site-set global --include-japanese
```

Outputs:

- Per-site JP XLSX reports: `./wcag_reports/jp_ja/`
- JP aggregate XLSX report: `./wcag_reports/jp_ja/wcag_aggregate_report_<DATE>_ja.xlsx`
- JP markdown summary (English): `./COVERAGE_JA.md` (overwritten by runner)

