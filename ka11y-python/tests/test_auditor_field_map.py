"""
Smoke test guarding against the field-name-mismatch class of bug that
silently downgrades whole WCAG SCs to ``needs_review``.

The test scans ``findings.py`` for every literal ``r.get("wcag_X_Y_Z_*")``
key and asserts the registry in ``auditor_field_map.py`` covers it. Any
new converter that uses an unregistered key fails CI loudly instead of
returning empty findings at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path

from ka11y.api.v1.combined import auditor_field_map as afm

FINDINGS_PATH = (
    Path(__file__).resolve().parents[1]
    / "ka11y"
    / "api"
    / "v1"
    / "combined"
    / "findings.py"
)

# Matches r.get("wcag_1_1_1_status"), r.get('wcag_4_1_2_reason'), etc.
_FIELD_RE = re.compile(r"""wcag_(\d+)_(\d+)_(\d+)_(status|reason)""")

# Matches get_status(record, "1.1.1") / get_reason(r, "2.5.3", default=...).
# After the B-2 migration, converters read through these helpers rather than
# raw key literals, so the SC argument is what now needs registry coverage.
_HELPER_CALL_RE = re.compile(
    r"""get_(?:status|reason)\(\s*[^,]+,\s*["'](\d+\.\d+\.\d+)["']"""
)


def _keys_referenced_in_findings() -> set[str]:
    src = FINDINGS_PATH.read_text(encoding="utf-8")
    return {match.group(0) for match in _FIELD_RE.finditer(src)}


def _sc_args_in_findings() -> set[str]:
    src = FINDINGS_PATH.read_text(encoding="utf-8")
    return {match.group(1) for match in _HELPER_CALL_RE.finditer(src)}


def _keys_declared_in_registry() -> set[str]:
    declared: set[str] = set()
    for sc, mapping in afm.AUDITOR_FIELD_MAP.items():
        declared.add(mapping["status"])
        declared.add(mapping["reason"])
    return declared


def test_registry_covers_every_field_used_in_findings():
    """Any wcag_*_status / wcag_*_reason literal in findings.py MUST be
    declared in AUDITOR_FIELD_MAP. Catches the data-loss class of bug at
    test time instead of on a live audit."""
    used = _keys_referenced_in_findings()
    declared = _keys_declared_in_registry()
    missing = used - declared
    assert not missing, (
        "findings.py references WCAG fields not in AUDITOR_FIELD_MAP — add "
        "them to ka11y/api/v1/combined/auditor_field_map.py so they are part "
        f"of the typed contract: {sorted(missing)}"
    )


def test_registry_status_keys_match_canonical_shape():
    """Status key for SC 'X.Y.Z' must be exactly 'wcag_X_Y_Z_status'."""
    for sc, mapping in afm.AUDITOR_FIELD_MAP.items():
        suffix = sc.replace(".", "_")
        assert mapping["status"] == f"wcag_{suffix}_status", sc
        assert mapping["reason"] == f"wcag_{suffix}_reason", sc


def test_every_helper_call_sc_is_registered():
    """Every SC passed to get_status()/get_reason() in findings.py MUST be a
    key in AUDITOR_FIELD_MAP. After the B-2 migration this is the primary
    guard: an unregistered SC raises KeyError at runtime, and this test makes
    that a CI failure instead. Also asserts the migration actually happened
    (helpers are in use), so we don't silently regress to raw key reads."""
    sc_args = _sc_args_in_findings()
    assert sc_args, "expected findings.py to call get_status/get_reason with SC literals"
    missing = sc_args - set(afm.AUDITOR_FIELD_MAP)
    assert not missing, (
        "findings.py calls get_status/get_reason with SCs not in "
        f"AUDITOR_FIELD_MAP: {sorted(missing)}"
    )


def test_helpers_read_through_registry():
    record = {"wcag_1_1_1_status": "FAILED", "wcag_1_1_1_reason": "missing alt"}
    assert afm.get_status(record, "1.1.1") == "FAILED"
    assert afm.get_reason(record, "1.1.1") == "missing alt"
    # Default fallback path
    assert afm.get_status({}, "1.1.1", default="UNKNOWN") == "UNKNOWN"
    assert afm.get_reason({}, "1.1.1", default="n/a") == "n/a"
