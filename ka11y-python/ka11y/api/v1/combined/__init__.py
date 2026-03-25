"""
ka11y/api/v1/combined/
=======================
Combined Python + Node axe-core accessibility audit — package entry point.

Re-exports the FastAPI router and the _evict_old_jobs background task so
that existing callers (api/router.py, main.py) continue to work unchanged:

    from ka11y.api.v1.combined import router        # api/router.py
    from ka11y.api.v1.combined import _evict_old_jobs  # main.py

Package layout
──────────────
  constants.py   — _WCAG_NAMES, _WCAG_LEVEL, _SUGGESTED_FIX, _PYTHON_SEVERITY
  models.py      — CombinedRequest, JobStatusResponse
  store.py       — in-memory job store, SSE bus, TTL eviction
  stage_events.py— _stage_start / _stage_complete / _stage_error helpers
  findings.py    — _make_finding factory + all per-rule converters
  report.py      — _build_report
  stages.py      — per-stage coroutines + _run_python_stages orchestrator
  runner.py      — _run_job background task
  routes.py      — FastAPI router with all route handlers

HOW TO ADD A NEW PYTHON RULE
──────────────────────────────
Step 1 — Crawler  (ka11y/crawler/)
  Implement async crawl() → List[Dict] + save_raw_json().

Step 2 — Auditor  (ka11y/accessibility/rules/<category>/)
  Implement generate_audit_report(items) → List[Dict].
  Each record must include:
    <rule_key>_status    "FAILED" | "PASSED" | "NEEDS_REVIEW" | "N/A"
    <rule_key>_violation  str
    html_snippet, element_id, tag

Step 3 — Finding converter  (findings.py)
  Add _myrule_to_findings(records, page_url) → List[Dict].
  Call _make_finding() and _PYTHON_SEVERITY[wcag_sc].
  Register it in the appropriate converter registry so the combined result
  pipeline automatically includes it.

Step 4 — Register metadata  (constants.py)
  Add to _PYTHON_SEVERITY and _SUGGESTED_FIX.

Step 5 — Wire stage  (stages.py)
  Add _stage_myrule() following the existing pattern.
  Add it to asyncio.gather() inside _run_python_stages().

Step 6 — Expose toggle  (models.py)
  Add run_my_audit: bool = True to CombinedRequest.
  Pass it through runner.py → stages.py.
"""

from .routes import router
from .store import _evict_old_jobs
from .report import _build_report
from .findings import (
    IMAGE_AUDIT_RECORD_CONVERTERS,
    OCR_RESULT_CONVERTERS,
    _make_finding,
    _alt_text_to_findings,
    _name_role_value_to_findings,
    _contrast_to_findings,
    _contrast_enhanced_to_findings,
    _crawler_text_spacing_to_findings,
    _form_to_findings,
    _images_of_text_to_findings,
    _lin_to_findings,
    _non_text_contrast_to_findings,
    _psh_to_findings,
    _ts_to_findings,
    _resize_text_to_findings,
    _reflow_to_findings,
    _rendered_text_spacing_to_findings,
    _orientation_to_findings,
    _hover_focus_content_to_findings,
    _focus_not_obscured_min_to_findings,
    _focus_not_obscured_enh_to_findings,
)

__all__ = [
    "router",
    "_evict_old_jobs",
    "_build_report",
    "IMAGE_AUDIT_RECORD_CONVERTERS",
    "OCR_RESULT_CONVERTERS",
    "_make_finding",
    "_alt_text_to_findings",
    "_name_role_value_to_findings",
    "_contrast_to_findings",
    "_contrast_enhanced_to_findings",
    "_crawler_text_spacing_to_findings",
    "_form_to_findings",
    "_images_of_text_to_findings",
    "_lin_to_findings",
    "_non_text_contrast_to_findings",
    "_psh_to_findings",
    "_ts_to_findings",
    "_resize_text_to_findings",
    "_reflow_to_findings",
    "_rendered_text_spacing_to_findings",
    "_orientation_to_findings",
    "_hover_focus_content_to_findings",
    "_focus_not_obscured_min_to_findings",
    "_focus_not_obscured_enh_to_findings",
]
