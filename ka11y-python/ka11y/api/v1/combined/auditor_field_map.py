"""
ka11y/api/v1/combined/auditor_field_map.py
==========================================
Single source of truth for the (auditor record key) ↔ (WCAG SC) mapping
used by every converter in `findings.py`.

Background
----------
Each Python auditor emits records that look like::

    {"wcag_1_1_1_status": "FAILED", "wcag_1_1_1_reason": "missing alt", ...}

The converter functions in `findings.py` historically read these via inline
``r.get("wcag_X_Y_Z_status", "")`` calls. A typo in either side silently
downgrades an entire SC to ``needs_review`` because ``.get`` returns the
default. The 1.1.1 alt-text rule was already biting from this class of bug.

This module:

1. Declares the canonical key shape per SC in :data:`AUDITOR_FIELD_MAP`.
2. Exposes :func:`get_status` / :func:`get_reason` helpers so converters can
   stop hard-coding strings.
3. Is paired with ``tests/test_auditor_field_map.py``, which scans
   ``findings.py`` for any ``r.get("wcag_X_Y_Z_*")`` literal and asserts the
   registry covers it. A new converter referencing an unregistered key
   fails CI.
"""

from __future__ import annotations

from typing import Dict, Tuple


def _keys_for(sc: str) -> Tuple[str, str]:
    """Canonical key shape for a Success Criterion identifier like '1.1.1'."""
    suffix = sc.replace(".", "_")
    return (f"wcag_{suffix}_status", f"wcag_{suffix}_reason")


# Every WCAG SC currently consumed by a converter in `findings.py`.
# When you add a new converter, add the SC here and the smoke test passes.
AUDITOR_FIELD_MAP: Dict[str, Dict[str, str]] = {
    sc: {"status": status_key, "reason": reason_key}
    for sc, (status_key, reason_key) in (
        (sc, _keys_for(sc))
        for sc in (
            "1.1.1",
            "1.2.1",
            "1.2.2",
            "1.2.3",
            "1.3.3",
            "1.4.2",
            "1.4.3",
            "1.4.5",
            "1.4.6",
            "1.4.11",
            "1.4.12",
            "2.2.2",
            "2.5.8",
            "3.3.1",
            "3.3.2",
            "4.1.2",
            "3.2.3",
            "3.2.4",
            "3.1.3",
            "2.4.10",
        )
    )
}


def status_key(sc: str) -> str:
    """Canonical status key for an SC. Raises KeyError if unregistered."""
    return AUDITOR_FIELD_MAP[sc]["status"]


def reason_key(sc: str) -> str:
    """Canonical reason key for an SC. Raises KeyError if unregistered."""
    return AUDITOR_FIELD_MAP[sc]["reason"]


def get_status(record: dict, sc: str, default: str = "") -> str:
    return record.get(status_key(sc), default)


def get_reason(record: dict, sc: str, default: str = "") -> str:
    return record.get(reason_key(sc), default) or default
