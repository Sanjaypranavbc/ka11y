# ka11y-python — Complete Codebase Walkthrough

A deep, code-cited walkthrough of `ka11y-python`: a FastAPI service that crawls a
URL with Playwright and audits it for WCAG 2.2 accessibility conformance (plus
OCR-based image-text/contrast analysis and AI-assisted media/plain-language checks).

This is a multi-file document. Read in order, or jump to the section you need.

| # | File | Covers request section(s) |
|---|------|---------------------------|
| 00 | `00-INDEX.md` | (this file) |
| 01 | `01-OVERVIEW-AND-ENTRYPOINT.md` | 1. Project overview · 2. Installation → entry-point trace |
| 02 | `02-ARCHITECTURE.md` | 3. Architecture map |
| 03 | `03-MODULES-config-utils.md` | 4. Module breakdown — Config & Utilities layer |
| 04 | `04-MODULES-crawler.md` | 4. Module breakdown — Crawler layer |
| 05 | `05-MODULES-pipeline.md` | 4. Module breakdown — Rendered-state pipeline (`accessibility/pipeline/`) |
| 06 | `06-MODULES-rules.md` | 4. Module breakdown — Rule auditors (`accessibility/rules/`) |
| 07 | `07-MODULES-api.md` | 4. Module breakdown — API layer (`api/`) |
| 08 | `08-MODULES-store.md` | 4. Module breakdown — Durable store (`store/`) |
| 09 | `09-MODULES-text-classifier-i18n.md` | 4. Module breakdown — OCR/text-detector, classifier, preprocessor, i18n |
| 10 | `10-EXECUTION-FLOW.md` | 5. Full execution flow (code-level trace) |
| 11 | `11-DATA-MODELS.md` | 6. Key data structures / models |
| 12 | `12-OUTPUT-FILES.md` | 7. Output directory & file creation (detailed) |
| 13 | `13-EXTENSIBILITY.md` | 8. Extensibility / plugin points |
| 14 | `14-OUTPUT-TERMINATION-DIAGRAMS.md` | 9. Output/termination · 10. Summary diagrams |

## Scope and method

- Covers `ka11y-python/ka11y/` — the actual service package (113 `.py` files;
  92 non-trivial after excluding 21 empty `__init__.py` files). Test files
  (`ka11y-python/tests/`) and standalone scripts (`ka11y-python/scripts/`) are
  out of scope for the per-function breakdown in section 4, but are referenced
  where they illuminate execution flow or output behaviour.
- Every file path and line number below was read directly from the source at
  the time of writing (commit `b734e3b`, branch `production`). Line numbers
  will drift as the code changes — treat them as "as of this commit", and
  re-grep if the file has since been edited.
- "Trivial" `__init__.py` = zero lines, or a docstring/import-only re-export
  with no logic. Those are skipped per the request; every other `__init__.py`
  (`ka11y/__init__.py`, `store/__init__.py`, `text_detector/__init__.py`,
  `utils/__init__.py`, `api/v1/rules/__init__.py`, `api/v1/combined/__init__.py`,
  `accessibility/rules/media/__init__.py`) is documented in its group file.
