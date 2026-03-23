"""
tests/test_rendered_converters.py
===================================
Unit tests for the rendered-layout finding converters in combined.py.
Verifies that FAILED → "fail", PASSED → "pass", NEEDS_REVIEW → "needs_review",
N/A → skipped, and that the finding schema is preserved exactly.
"""

import pytest

# Import converters from combined module
from ka11y.api.v1.combined import (
    _resize_text_to_findings,
    _reflow_to_findings,
    _text_spacing_to_findings,
    _orientation_to_findings,
    _hover_focus_content_to_findings,
    _focus_not_obscured_min_to_findings,
    _focus_not_obscured_enh_to_findings,
)

PAGE_URL = "https://example.com"

# ── Helpers ────────────────────────────────────────────────────────────────────

REQUIRED_KEYS = {
    "source", "rule_id", "wcag_sc", "criterion_name", "level",
    "severity", "status", "reason", "suggested_fix", "help_url", "element",
}


def _check_schema(finding: dict) -> None:
    """Assert the finding has all required top-level keys."""
    for key in REQUIRED_KEYS:
        assert key in finding, f"Missing key '{key}' in finding"


# ── Parametric converter tests ─────────────────────────────────────────────────

_CONVERTER_CASES = [
    # (converter_fn, rule_key, expected_wcag_sc, expected_rule_id)
    (_resize_text_to_findings,          "wcag_1_4_4",   "1.4.4",   "python_1_4_4_resize_text"),
    (_reflow_to_findings,               "wcag_1_4_10",  "1.4.10",  "python_1_4_10_reflow"),
    (_text_spacing_to_findings,         "wcag_1_4_12",  "1.4.12",  "python_1_4_12_text_spacing"),
    (_orientation_to_findings,          "wcag_1_3_4",   "1.3.4",   "python_1_3_4_orientation"),
    (_hover_focus_content_to_findings,  "wcag_1_4_13",  "1.4.13",  "python_1_4_13_hover_or_focus_content"),
    (_focus_not_obscured_min_to_findings, "wcag_2_4_11","2.4.11",  "python_2_4_11_focus_not_obscured_minimum"),
    (_focus_not_obscured_enh_to_findings, "wcag_2_4_12","2.4.12",  "python_2_4_12_focus_not_obscured_enhanced"),
]


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_failed_record_produces_fail_finding(fn, rule_key, expected_sc, expected_rid):
    records = [{
        f"{rule_key}_status": "FAILED",
        f"{rule_key}_violation": "Something broke.",
        "html_snippet": "<div>test</div>",
        "element_id": "el1",
        "tag": "div",
        "page_url": PAGE_URL,
    }]
    findings = fn(records, PAGE_URL)
    assert len(findings) == 1
    f = findings[0]
    _check_schema(f)
    assert f["status"] == "fail"
    assert f["wcag_sc"] == expected_sc
    assert f["rule_id"] == expected_rid
    assert f["source"] == "python"
    assert f["element"] is not None
    assert f["suggested_fix"] is not None
    assert f["severity"] is not None


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_passed_record_produces_pass_finding(fn, rule_key, expected_sc, expected_rid):
    records = [{
        f"{rule_key}_status": "PASSED",
        f"{rule_key}_violation": "",
        "html_snippet": "",
        "element_id": None,
        "tag": "",
        "page_url": PAGE_URL,
    }]
    findings = fn(records, PAGE_URL)
    assert len(findings) == 1
    f = findings[0]
    _check_schema(f)
    assert f["status"] == "pass"
    assert f["element"] is None
    assert f["suggested_fix"] is None
    assert f["severity"] is None


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_needs_review_record(fn, rule_key, expected_sc, expected_rid):
    records = [{
        f"{rule_key}_status": "NEEDS_REVIEW",
        f"{rule_key}_violation": "Not sure — check manually.",
        "html_snippet": "",
        "element_id": None,
        "tag": "",
        "page_url": PAGE_URL,
    }]
    findings = fn(records, PAGE_URL)
    assert len(findings) == 1
    assert findings[0]["status"] == "needs_review"


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_na_record_skipped(fn, rule_key, expected_sc, expected_rid):
    records = [{
        f"{rule_key}_status": "N/A",
        f"{rule_key}_violation": "",
        "html_snippet": "",
        "element_id": None,
        "tag": "",
        "page_url": PAGE_URL,
    }]
    findings = fn(records, PAGE_URL)
    assert findings == []


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_empty_records(fn, rule_key, expected_sc, expected_rid):
    assert fn([], PAGE_URL) == []


def test_mixed_records():
    """Multiple records with different statuses produce correct findings."""
    records = [
        {"wcag_1_4_10_status": "FAILED",  "wcag_1_4_10_violation": "Overflow.",
         "html_snippet": "<div/>", "element_id": None, "tag": "div", "page_url": PAGE_URL},
        {"wcag_1_4_10_status": "PASSED",  "wcag_1_4_10_violation": "",
         "html_snippet": "", "element_id": None, "tag": "", "page_url": PAGE_URL},
        {"wcag_1_4_10_status": "NEEDS_REVIEW", "wcag_1_4_10_violation": "Table?",
         "html_snippet": "", "element_id": None, "tag": "", "page_url": PAGE_URL},
        {"wcag_1_4_10_status": "N/A",     "wcag_1_4_10_violation": "",
         "html_snippet": "", "element_id": None, "tag": "", "page_url": PAGE_URL},
    ]
    findings = _reflow_to_findings(records, PAGE_URL)
    statuses = [f["status"] for f in findings]
    assert statuses == ["fail", "pass", "needs_review"]