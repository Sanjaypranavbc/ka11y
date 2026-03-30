"""
ka11y/api/v1/rules.py
======================
GET /api/v1/rules/wcag  — Returns the full WCAG rules catalogue with
optional i18n support via the ?lang= query parameter.

Response shape:
  {
    "version": "1.0",
    "lang":    "en",
    "rules": [
      {
        "id":            "1.1.1",
        "level":         "A",
        "severity":      "critical",   // null for rules without a severity
        "name":          "Non-text Content",
        "description":   "...",
        "suggested_fix": "..."
      },
      ...
    ]
  }

Rules are sorted numerically by SC ID (1.1.1 < 1.2.1 < ... < 4.1.3).
"""

from __future__ import annotations

from functools import cmp_to_key
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ka11y.i18n.loader import load_rules

router = APIRouter(prefix="/rules", tags=["rules"])


def _sc_sort_key(entry: Dict[str, Any]) -> tuple:
    """Numeric sort key for a WCAG SC ID like '1.4.12'."""
    try:
        return tuple(int(x) for x in entry["id"].split("."))
    except (ValueError, KeyError):
        return (999,)


@router.get("/wcag", summary="WCAG rules catalogue")
async def get_wcag_rules(
    lang: str = Query(default="en", description="BCP-47 language code (e.g. 'en', 'de', 'ja')"),
) -> JSONResponse:
    """
    Returns all WCAG success criteria with level, severity, name,
    description, and suggested_fix, optionally localised.

    - **lang**: Two-letter language code.  Falls back to English for any
      untranslated entry.  Returns English if the locale file is not found.
    """
    # Sanitise lang — only allow [a-zA-Z-], max 10 chars
    safe_lang = "".join(c for c in lang if c.isalpha() or c == "-")[:10] or "en"

    rules_map = load_rules(safe_lang)

    rules_list: List[Dict[str, Any]] = [
        {
            "id":            entry.id,
            "level":         entry.level,
            "severity":      entry.severity,
            "name":          entry.name,
            "description":   entry.description,
            "suggested_fix": entry.suggested_fix,
        }
        for entry in rules_map.values()
    ]

    rules_list.sort(key=_sc_sort_key)

    return JSONResponse(
        content={
            "version": "1.0",
            "lang":    safe_lang,
            "rules":   rules_list,
        }
    )
