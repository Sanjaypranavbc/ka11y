"""
ka11y/api/v1/combined/constants.py
====================================
WCAG metadata now loaded from the shared i18n/rules.yml via the i18n loader.

All module-level names (_WCAG_NAMES, _WCAG_LEVEL, _SUGGESTED_FIX,
_PYTHON_SEVERITY) are preserved so existing callers in findings.py continue
to work without any changes.
"""

from __future__ import annotations

from ka11y.i18n.loader import get_severities, get_suggested_fixes, get_wcag_levels, get_wcag_names

# ---------------------------------------------------------------------------
# Public dicts — same names and shapes as before, now YAML-backed.
# ---------------------------------------------------------------------------

#: {sc_id: human-readable name}  (English, refreshed from rules.yml)
_WCAG_NAMES: dict[str, str] = get_wcag_names("en")

#: {sc_id: level}  ("A" | "AA" | "AAA")
_WCAG_LEVEL: dict[str, str] = get_wcag_levels()

#: {sc_id: suggested fix text}  (English)
_SUGGESTED_FIX: dict[str, str] = get_suggested_fixes("en")

#: {sc_id: severity}  Only rules with an explicit severity entry are included.
_PYTHON_SEVERITY: dict[str, str] = get_severities()


# ---------------------------------------------------------------------------
# Progress-bar stage weights.
# Calibrated against a typical t3.large 4–7 min audit (see PLAN_FOR_EC2.md §4.2).
# Sum is 100 → `index * weight / 100` gives an honest percent-complete.
# ---------------------------------------------------------------------------
STAGE_WEIGHTS: dict[str, int] = {
    "axe_core": 4,
    "image_audit": 40,
    "pipeline": 10,              # 2.5.3 / 2.5.8 / 1.1.1 / focus / contrast
    "form_audit": 2,
    "label_in_name": 1,
    "pause_stop_hide": 2,
    "target_size": 1,
    "text_spacing": 2,
    "rendered_layout_audit": 20,
    "media_audit": 18,
    "sensory_audit": 2,
}
