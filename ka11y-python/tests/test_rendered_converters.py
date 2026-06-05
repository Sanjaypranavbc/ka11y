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
    _rendered_text_spacing_to_findings,
    _crawler_text_spacing_to_findings,
    _orientation_to_findings,
    _hover_focus_content_to_findings,
    _focus_not_obscured_min_to_findings,
    _focus_not_obscured_enh_to_findings,
)
from ka11y.api.v1.combined.findings import _lang_ctx

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
    (_resize_text_to_findings,              "wcag_1_4_4",   "1.4.4",   "python_1_4_4_resize_text"),
    (_reflow_to_findings,                   "wcag_1_4_10",  "1.4.10",  "python_1_4_10_reflow"),
    (_rendered_text_spacing_to_findings,    "wcag_1_4_12",  "1.4.12",  "python_1_4_12_text_spacing_rendered"),
    (_orientation_to_findings,              "wcag_1_3_4",   "1.3.4",   "python_1_3_4_orientation"),
    (_hover_focus_content_to_findings,      "wcag_1_4_13",  "1.4.13",  "python_1_4_13_hover_or_focus_content"),
    (_focus_not_obscured_min_to_findings,   "wcag_2_4_11",  "2.4.11",  "python_2_4_11_focus_not_obscured_minimum"),
    (_focus_not_obscured_enh_to_findings,   "wcag_2_4_12",  "2.4.12",  "python_2_4_12_focus_not_obscured_enhanced"),
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


# Converters that emit a synthetic page-level pass when records is empty
_SYNTHETIC_PASS_FNS = {
    _resize_text_to_findings,
    _reflow_to_findings,
    _hover_focus_content_to_findings,
    _focus_not_obscured_min_to_findings,
    _focus_not_obscured_enh_to_findings,
}


@pytest.mark.parametrize("fn,rule_key,expected_sc,expected_rid", _CONVERTER_CASES)
def test_empty_records(fn, rule_key, expected_sc, expected_rid):
    findings = fn([], PAGE_URL)
    if fn in _SYNTHETIC_PASS_FNS:
        assert len(findings) == 1, f"{fn.__name__} should emit a synthetic pass for empty records"
        f = findings[0]
        assert f["status"] == "pass"
        assert f["reason_code"] == "pass_no_records"
        assert f["wcag_sc"] == expected_sc
        assert f["rule_id"] == expected_rid
        assert f["element"] is None
    else:
        assert findings == []


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


# ── Crawler text-spacing converter tests ───────────────────────────────────────


def test_crawler_text_spacing_failed():
    """FAILED (fixed height + overflow:hidden) → 'fail' with static rule_id."""
    records = [{
        "wcag_1_4_12_status": "FAILED",
        "wcag_1_4_12_violation": "Fixed height with overflow hidden may clip text.",
        "html_snippet": "<div style='height:50px;overflow:hidden'>text</div>",
        "element_id": "box",
        "tag": "div",
    }]
    findings = _crawler_text_spacing_to_findings(records, PAGE_URL)
    assert len(findings) == 1
    f = findings[0]
    _check_schema(f)
    assert f["status"] == "fail"
    assert f["wcag_sc"] == "1.4.12"
    assert f["rule_id"] == "python_1_4_12_text_spacing_static"
    assert f["severity"] is not None
    assert f["element"] is not None


def test_crawler_text_spacing_warning_becomes_needs_review():
    """WARNING (fixed height only) must produce 'needs_review' — previously silently dropped."""
    records = [{
        "wcag_1_4_12_status": "WARNING",
        "wcag_1_4_12_violation": "Fixed height may cause clipping.",
        "html_snippet": "<div style='height:50px'>text</div>",
        "element_id": None,
        "tag": "div",
    }]
    findings = _crawler_text_spacing_to_findings(records, PAGE_URL)
    assert len(findings) == 1
    f = findings[0]
    _check_schema(f)
    assert f["status"] == "needs_review"
    assert f["wcag_sc"] == "1.4.12"
    assert f["rule_id"] == "python_1_4_12_text_spacing_static"


def test_crawler_text_spacing_passed():
    records = [{
        "wcag_1_4_12_status": "PASSED",
        "wcag_1_4_12_violation": "",
        "html_snippet": "",
        "element_id": None,
        "tag": None,
    }]
    findings = _crawler_text_spacing_to_findings(records, PAGE_URL)
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["element"] is None


def test_crawler_text_spacing_na_skipped():
    records = [{"wcag_1_4_12_status": "N/A", "wcag_1_4_12_violation": ""}]
    assert _crawler_text_spacing_to_findings(records, PAGE_URL) == []


def test_crawler_text_spacing_empty():
    assert _crawler_text_spacing_to_findings([], PAGE_URL) == []


def test_crawler_vs_rendered_have_distinct_rule_ids():
    """Static and rendered 1.4.12 findings must use different rule_ids to avoid confusion."""
    static_rec = [{
        "wcag_1_4_12_status": "FAILED",
        "wcag_1_4_12_violation": "overflow hidden",
        "html_snippet": "<div/>", "element_id": None, "tag": "div",
    }]
    rendered_rec = [{
        "wcag_1_4_12_status": "FAILED",
        "wcag_1_4_12_violation": "text clipped after override",
        "html_snippet": "<p/>", "element_id": None, "tag": "p", "page_url": PAGE_URL,
    }]
    static_f = _crawler_text_spacing_to_findings(static_rec, PAGE_URL)
    rendered_f = _rendered_text_spacing_to_findings(rendered_rec, PAGE_URL)
    assert static_f[0]["rule_id"] != rendered_f[0]["rule_id"]
    assert static_f[0]["wcag_sc"] == rendered_f[0]["wcag_sc"] == "1.4.12"


def test_rendered_reflow_pass_reason_is_specific():
    """A 1.4.10 reflow PASS renders the rule-specific localized message (it
    tells the user *what* passed — content reflows at 320 CSS px), not the
    generic SC catalogue description. The message still comes from i18n YAML
    via reason_code, so localization remains centralized."""
    token = _lang_ctx.set("ja")
    try:
        records = [{
            "wcag_1_4_10_status": "PASSED",
            "wcag_1_4_10_violation": "",
            "html_snippet": "",
            "element_id": None,
            "tag": "",
            "page_url": PAGE_URL,
        }]
        findings = _reflow_to_findings(records, PAGE_URL)
        assert len(findings) == 1
        assert findings[0]["status"] == "pass"
        assert findings[0]["reason"].startswith(
            "320 CSS ピクセル幅でも横スクロールなしでコンテンツが正しく折り返されます"
        )
    finally:
        _lang_ctx.reset(token)
