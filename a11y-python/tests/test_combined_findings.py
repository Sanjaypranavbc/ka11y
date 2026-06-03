from __future__ import annotations

from types import SimpleNamespace

from a11y.api.v1.combined import (
    IMAGE_AUDIT_RECORD_CONVERTERS,
    OCR_RESULT_CONVERTERS,
    _contrast_enhanced_to_findings,
    _contrast_to_findings,
    _crawler_text_spacing_to_findings,
    _make_finding,
    _name_role_value_to_findings,
    _non_text_contrast_to_findings,
)
from a11y.api.v1.combined.findings import _sensory_to_findings
from a11y.api.v1.combined.models import CombinedRequest
from a11y.api.v1.combined.stages import _allowed_levels

# R-2: canonical form of the root URL keeps the trailing slash (WHATWG URL).
# Tests should use the canonical form so equality assertions don't churn.
PAGE_URL = "https://example.com/"


def _ocr_result(*, compliance: dict | None = None) -> SimpleNamespace:
    detection = SimpleNamespace(
        text="Hello",
        confidence=0.99,
        contrast_info={"compliance": compliance or {}},
        color_info={},
        wcag_violations=[],
    )
    return SimpleNamespace(
        has_text=True,
        filename="sample.png",
        original_path="/tmp/sample.png",
        contrast_violations_count=0,
        detections=[detection],
    )


def test_image_audit_converter_registry_covers_all_raw_status_keys():
    assert {key for key, _ in IMAGE_AUDIT_RECORD_CONVERTERS} == {
        "wcag_1_1_1_status",
        "wcag_4_1_2_status",
        "wcag_1_4_5_status",
        "wcag_1_4_11_status",
    }


def test_ocr_converter_registry_covers_all_combined_contrast_rules():
    assert {key for key, _ in OCR_RESULT_CONVERTERS} == {"1.4.3", "1.4.6"}


def test_1_4_3_missing_contrast_compliance_becomes_needs_review():
    findings = _contrast_to_findings([_ocr_result()], PAGE_URL)

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.4.3"
    assert findings[0]["status"] == "needs_review"
    assert "Manual review required" in findings[0]["reason"]
    assert findings[0]["level"] == "AA"


def test_1_4_6_missing_contrast_compliance_becomes_needs_review():
    findings = _contrast_enhanced_to_findings([_ocr_result()], PAGE_URL)

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.4.6"
    assert findings[0]["status"] == "needs_review"
    assert "Manual review required" in findings[0]["reason"]
    assert findings[0]["level"] == "AAA"


def test_1_4_11_incomplete_reason_becomes_needs_review():
    findings = _non_text_contrast_to_findings(
        [
            {
                "filename": "icon.png",
                "src": "/img/icon.png",
                "alt_text": "Search",
                "wcag_1_4_11_status": "N/A",
                "wcag_1_4_11_reason": (
                    "INCOMPLETE [1.4.11] No OCR contrast data available "
                    "manual check required"
                ),
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.4.11"
    assert findings[0]["status"] == "needs_review"
    assert findings[0]["severity"] == "high"


def test_1_4_3_stamps_per_page_url_from_page_by_filename():
    # D-1 regression: on multi-page crawls, contrast findings must be stamped
    # with the page the image actually came from, not the root URL — otherwise
    # every child-page contrast finding collapses onto the root tab in the UI.
    child_page = "https://example.com/child/page-b"
    findings = _contrast_to_findings(
        [_ocr_result()],
        PAGE_URL,
        page_by_filename={"sample.png": child_page},
    )
    assert len(findings) == 1
    assert findings[0]["element"]["page_url"] == child_page


def test_1_4_3_falls_back_to_page_url_when_filename_not_in_map():
    findings = _contrast_to_findings(
        [_ocr_result()],
        PAGE_URL,
        page_by_filename={"unrelated.png": "https://example.com/other"},
    )
    assert findings[0]["element"]["page_url"] == PAGE_URL


def test_1_4_6_stamps_per_page_url_from_page_by_filename():
    child_page = "https://example.com/child/page-b"
    findings = _contrast_enhanced_to_findings(
        [_ocr_result()],
        PAGE_URL,
        page_by_filename={"sample.png": child_page},
    )
    assert len(findings) == 1
    assert findings[0]["element"]["page_url"] == child_page


def test_1_4_11_true_na_is_still_skipped():
    findings = _non_text_contrast_to_findings(
        [
            {
                "filename": "photo.png",
                "src": "/img/photo.png",
                "alt_text": "Decorative divider",
                "wcag_1_4_11_status": "N/A",
                "wcag_1_4_11_reason": "N/A - 1.4.11 applies to UI components only",
            }
        ],
        PAGE_URL,
    )

    assert findings == []


def test_4_1_2_functional_image_is_exposed_in_combined_results():
    findings = _name_role_value_to_findings(
        [
            {
                "filename": "logo.png",
                "src": "/img/logo.png",
                "alt_text": "Brand Name",
                "wcag_4_1_2_status": "FAILED",
                "wcag_4_1_2_reason": "FAIL [4.1.2] Logo accessible name 'Brand Name' must include 'logo'.",
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "4.1.2"
    assert findings[0]["status"] == "fail"
    assert findings[0]["severity"] == "high"


def test_text_spacing_info_is_exposed_as_needs_review():
    findings = _crawler_text_spacing_to_findings(
        [
            {
                "wcag_1_4_12_status": "INFO",
                "wcag_1_4_12_violation": (
                    "1.4.12: Fixed height detected. Verify text does not clip "
                    "when spacing increases."
                ),
                "html_snippet": "<section style='height:40px'>Text</section>",
                "element_id": "section-1",
                "tag": "section",
                "page_url": PAGE_URL,
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.4.12"
    assert findings[0]["status"] == "needs_review"


def test_1_4_6_is_excluded_at_aa_and_kept_at_aaa():
    findings = [
        {"wcag_sc": "1.4.3", "level": "AA"},
        {"wcag_sc": "1.4.6", "level": "AAA"},
    ]

    aa_filtered = [
        f for f in findings if f.get("level") in _allowed_levels("AA") or f.get("level") is None
    ]
    aaa_filtered = [
        f for f in findings if f.get("level") in _allowed_levels("AAA") or f.get("level") is None
    ]

    assert [f["wcag_sc"] for f in aa_filtered] == ["1.4.3"]
    assert [f["wcag_sc"] for f in aaa_filtered] == ["1.4.3", "1.4.6"]


def test_combined_request_defaults_to_aaa():
    request = CombinedRequest(url="https://example.com")

    assert request.wcag_level == "AAA"


def test_make_finding_keeps_element_for_pass_when_provided():
    finding = _make_finding(
        source="python",
        rule_id="python_1_1_1_alt",
        wcag_sc="1.1.1",
        status="pass",
        reason="Image has adequate alt text.",
        severity=None,
        element_html='<img id="logo" alt="Logo" src="/logo.png">',
        element_id="logo",
        element_tag="img",
        page_url=PAGE_URL,
    )

    assert finding["status"] == "pass"
    assert finding["element"] == {
        "html": '<img id="logo" alt="Logo" src="/logo.png">',
        "element_id": "logo",
        "tag": "img",
        "target": None,
        "selector": None,
        "element_ref_id": None,
        "frame_path": None,
        "image_src": None,
        "image_reference": None,
        "image_text": None,
        "page_url": PAGE_URL,
    }


def test_pass_converters_include_element_metadata_when_available():
    findings = _name_role_value_to_findings(
        [
            {
                "filename": "logo.png",
                "src": "/img/logo.png",
                "alt_text": "Brand Name logo",
                "wcag_4_1_2_status": "PASSED",
                "wcag_4_1_2_reason": "Accessible name is descriptive.",
                "url": PAGE_URL,
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["element"] == {
        "html": '<img src="/img/logo.png" alt="Brand Name logo">',
        "element_id": "/img/logo.png",
        "tag": "img",
        "target": None,
        "selector": None,
        "element_ref_id": None,
        "frame_path": None,
        "image_src": None,
        "image_reference": "logo.png",
        "image_text": None,
        "page_url": PAGE_URL,
    }


def test_1_3_3_failed_record_becomes_fail_finding():
    findings = _sensory_to_findings(
        [
            {
                "page_url": PAGE_URL,
                "element_tag": "p",
                "element_id": "instructions",
                "sensory_categories": "shape",
                "wcag_1_3_3_status": "FAILED",
                "wcag_1_3_3_violation": (
                    '1.3.3: Instruction relies solely on sensory characteristic(s) '
                    '[shape] - "Click the round button."'
                ),
                "html_snippet": "<p id='instructions'>Click the round button.</p>",
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.3.3"
    assert findings[0]["status"] == "fail"
    assert findings[0]["severity"] == "serious"


def test_1_3_3_pass_record_becomes_pass_finding():
    findings = _sensory_to_findings(
        [
            {
                "page_url": PAGE_URL,
                "element_tag": "p",
                "element_id": "instructions",
                "sensory_categories": "color",
                "wcag_1_3_3_status": "PASSED",
                "wcag_1_3_3_violation": "",
                "html_snippet": "<p id='instructions'>Click the blue Submit button.</p>",
            }
        ],
        PAGE_URL,
    )

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.3.3"
    assert findings[0]["status"] == "pass"
    assert findings[0]["element"] == {
        "html": "<p id='instructions'>Click the blue Submit button.</p>",
        "element_id": "instructions",
        "tag": "p",
        "target": None,
        "selector": None,
        "element_ref_id": None,
        "frame_path": None,
        "image_src": None,
        "image_reference": None,
        "image_text": None,
        "page_url": PAGE_URL,
    }


def test_1_3_3_empty_records_become_synthetic_pass():
    findings = _sensory_to_findings([], PAGE_URL)

    assert len(findings) == 1
    assert findings[0]["wcag_sc"] == "1.3.3"
    assert findings[0]["status"] == "pass"
    assert findings[0]["reason"] == (
        "No sensory-characteristics-only instructions detected in the crawled content."
    )
    assert findings[0]["element"] is None
