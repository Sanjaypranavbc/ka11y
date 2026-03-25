from __future__ import annotations

from types import SimpleNamespace

from ka11y.api.v1.combined import (
    IMAGE_AUDIT_RECORD_CONVERTERS,
    OCR_RESULT_CONVERTERS,
    _contrast_enhanced_to_findings,
    _contrast_to_findings,
    _crawler_text_spacing_to_findings,
    _name_role_value_to_findings,
    _non_text_contrast_to_findings,
)
from ka11y.api.v1.combined.stages import _allowed_levels

PAGE_URL = "https://example.com"


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
