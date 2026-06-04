"""
Tests for WCAG 1.1.1 (Non-text Content) + WCAG 4.1.2 (Name, Role, Value)
Covers: _norm, _is_empty, all _check_1_1_1_* helpers, _check_4_1_2,
        AltTextAccessibilityAuditor.generate_audit_report
"""

import csv
from pathlib import Path
from typing import List, Optional


from ka11y.accessibility.rules.non_text.alttext import (
    AltTextAccessibilityAuditor,
    _check_1_1_1_button,
    _check_1_1_1_decorative,
    _check_1_1_1_icon,
    _check_1_1_1_informative,
    _check_1_1_1_logo,
    _check_1_1_1_missing_alt,
    _check_1_4_5,
    _check_4_1_2,
    _is_empty,
    _norm,
)
from ka11y.crawler.models import ImageData


# ── Helpers / factories ───────────────────────────────────────────────────────


def make_image(**kwargs) -> ImageData:
    """Factory for ImageData with sensible defaults."""
    defaults = dict(
        url="https://example.com",
        src="https://example.com/img.png",
        alt_text="",
        title="",
        classification="informative",
        sub_type=None,
        is_functional=False,
        is_decorative=False,
        is_complex=False,
        is_text_image=False,
        is_logo=False,
        is_icon=False,
        is_button=False,
        file_format=None,
        screenshot_path="/tmp/img.png",
        filename="img.png",
    )
    defaults.update(kwargs)
    return ImageData(**defaults)


class _MockDetection:
    def __init__(self, text: str):
        self.text = text


class _MockOCRResult:
    """Minimal stand-in for TextDetectionResult."""

    def __init__(
        self,
        filename: str,
        has_text: bool = False,
        texts: Optional[List[str]] = None,
        contrast_violations_count: int = 0,
    ):
        self.filename = filename
        self.has_text = has_text
        self.detections = [_MockDetection(t) for t in (texts or [])]
        self.contrast_violations_count = contrast_violations_count


# ── _norm ─────────────────────────────────────────────────────────────────────


class TestNorm:
    def test_lowercases(self):
        assert _norm("HELLO WORLD") == "hello world"

    def test_strips_punctuation(self):
        # punctuation replaced with space, then whitespace collapsed → single space
        assert _norm("hello, world!") == "hello world"

    def test_collapses_whitespace(self):
        assert _norm("hello   world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _norm("  hello  ") == "hello"

    def test_empty_string(self):
        assert _norm("") == ""

    def test_already_normalised(self):
        assert _norm("hello world") == "hello world"

    def test_mixed_case_and_punctuation(self):
        result = _norm("Brand, Logo!")
        assert "brand" in result
        assert "logo" in result


# ── _is_empty ────────────────────────────────────────────────────────────────


class TestIsEmpty:
    def test_empty_string(self):
        assert _is_empty("") is True

    def test_whitespace_only(self):
        assert _is_empty("   ") is True

    def test_nan_string(self):
        assert _is_empty("nan") is True

    def test_none_string(self):
        assert _is_empty("None") is True

    def test_null_string(self):
        assert _is_empty("null") is True

    def test_meaningful_text(self):
        assert _is_empty("hello") is False

    def test_logo_text(self):
        assert _is_empty("Brand logo") is False


# ── _check_1_1_1_decorative ──────────────────────────────────────────────────


class TestCheck111Decorative:
    def test_empty_alt_passes(self):
        passed, msg = _check_1_1_1_decorative("")
        assert passed is True
        assert "PASS" in msg

    def test_nan_alt_passes(self):
        passed, _ = _check_1_1_1_decorative("nan")
        assert passed is True

    def test_descriptive_alt_fails(self):
        passed, msg = _check_1_1_1_decorative("A red flower")
        assert passed is False
        assert "FAIL" in msg

    def test_fail_message_includes_found_value(self):
        _, msg = _check_1_1_1_decorative("decorative image")
        assert "decorative image" in msg

    def test_single_space_alt_passes(self):
        # space-only is treated as empty by _is_empty
        passed, _ = _check_1_1_1_decorative("   ")
        assert passed is True


# ── _check_1_1_1_missing_alt ─────────────────────────────────────────────────


class TestCheck111MissingAlt:
    def test_always_fails(self):
        passed, msg = _check_1_1_1_missing_alt("missing_alt")
        assert passed is False
        assert "FAIL" in msg

    def test_message_mentions_alt_attribute(self):
        _, msg = _check_1_1_1_missing_alt("missing_alt")
        assert "alt" in msg.lower()

    def test_works_for_any_sub_type(self):
        for sub in ("missing_alt", "decorative", "informative"):
            passed, _ = _check_1_1_1_missing_alt(sub)
            assert passed is False


# ── _check_1_1_1_informative ─────────────────────────────────────────────────


class TestCheck111Informative:
    def test_empty_alt_fails(self):
        passed, msg = _check_1_1_1_informative("", [])
        assert passed is False
        assert "FAIL" in msg

    def test_generic_alt_image_fails(self):
        passed, _ = _check_1_1_1_informative("image", [])
        assert passed is False

    def test_generic_alt_photo_fails(self):
        passed, _ = _check_1_1_1_informative("photo", [])
        assert passed is False

    def test_generic_alt_graphic_fails(self):
        passed, _ = _check_1_1_1_informative("graphic", [])
        assert passed is False

    def test_good_alt_no_ocr_passes_with_note(self):
        passed, msg = _check_1_1_1_informative("A scenic mountain view", [])
        assert passed is True
        assert "manual review" in msg.lower() or "no ocr" in msg.lower() or "non-empty" in msg.lower()

    def test_good_alt_ocr_match_passes(self):
        passed, msg = _check_1_1_1_informative("Buy Now button", ["Buy", "Now"])
        assert passed is True
        assert "PASS" in msg

    def test_good_alt_ocr_no_match_fails(self):
        passed, msg = _check_1_1_1_informative("Mountain scenery", ["Buy", "Now", "Sale"])
        assert passed is False
        assert "FAIL" in msg

    def test_case_insensitive_ocr_match(self):
        passed, _ = _check_1_1_1_informative("SALE banner", ["SALE"])
        assert passed is True

    def test_short_ocr_tokens_skipped(self):
        # OCR words < 3 chars are skipped — alt is accepted
        passed, _ = _check_1_1_1_informative("My image", ["hi", "ok", "no"])
        assert passed is True

    def test_none_alt_fails(self):
        # None alt treated as empty
        passed, _ = _check_1_1_1_informative(None, [])
        assert passed is False


# ── _check_1_1_1_logo ────────────────────────────────────────────────────────


class TestCheck111Logo:
    def test_empty_alt_fails(self):
        passed, msg = _check_1_1_1_logo("")
        assert passed is False
        assert "FAIL" in msg

    def test_generic_alt_fails(self):
        passed, _ = _check_1_1_1_logo("image")
        assert passed is False

    def test_alt_with_logo_word_passes(self):
        passed, msg = _check_1_1_1_logo("Kao logo")
        assert passed is True
        assert "PASS" in msg

    def test_alt_logo_case_insensitive(self):
        passed, _ = _check_1_1_1_logo("BRAND LOGO")
        assert passed is True

    def test_alt_with_home_word_passes(self):
        passed, _ = _check_1_1_1_logo("Home")
        assert passed is True

    def test_alt_with_japanese_logo_word_passes(self):
        passed, _ = _check_1_1_1_logo("企業ロゴ")
        assert passed is True

    def test_brand_name_without_logo_fails(self):
        passed, msg = _check_1_1_1_logo("Brand Name")
        assert passed is False
        assert "logo" in msg.lower()

    def test_fail_message_shows_found_alt(self):
        _, msg = _check_1_1_1_logo("Company Name")
        assert "Company Name" in msg

    def test_none_alt_fails(self):
        passed, _ = _check_1_1_1_logo(None)
        assert passed is False


# ── _check_1_1_1_icon ────────────────────────────────────────────────────────


class TestCheck111Icon:
    def test_empty_alt_fails(self):
        passed, msg = _check_1_1_1_icon("")
        assert passed is False

    def test_social_brand_name_alone_fails(self):
        # "twitter" alone is insufficient
        passed, msg = _check_1_1_1_icon("twitter")
        assert passed is False
        assert "icon" in msg.lower()

    def test_social_brand_plus_icon_passes(self):
        passed, _ = _check_1_1_1_icon("Twitter icon")
        assert passed is True

    def test_action_word_passes(self):
        passed, _ = _check_1_1_1_icon("search")
        assert passed is True

    def test_icon_word_in_alt_passes(self):
        passed, _ = _check_1_1_1_icon("settings icon")
        assert passed is True

    def test_japanese_icon_qualifier_passes(self):
        passed, _ = _check_1_1_1_icon("設定アイコン")
        assert passed is True

    def test_non_empty_non_brand_passes_with_note(self):
        passed, msg = _check_1_1_1_icon("arrow")
        assert passed is True

    def test_single_char_fails(self):
        passed, _ = _check_1_1_1_icon("X")
        assert passed is False

    def test_generic_alt_image_fails(self):
        passed, _ = _check_1_1_1_icon("image")
        assert passed is False

    def test_none_alt_fails(self):
        passed, _ = _check_1_1_1_icon(None)
        assert passed is False

    def test_facebook_brand_alone_fails(self):
        passed, _ = _check_1_1_1_icon("facebook")
        assert passed is False

    def test_facebook_icon_passes(self):
        passed, _ = _check_1_1_1_icon("Facebook icon")
        assert passed is True


# ── _check_1_1_1_button ──────────────────────────────────────────────────────


class TestCheck111Button:
    def test_empty_alt_fails(self):
        passed, _ = _check_1_1_1_button("")
        assert passed is False

    def test_generic_alt_fails(self):
        passed, _ = _check_1_1_1_button("image")
        assert passed is False

    def test_known_action_word_passes(self):
        passed, msg = _check_1_1_1_button("submit")
        assert passed is True
        assert "PASS" in msg

    def test_action_word_in_phrase_passes(self):
        passed, _ = _check_1_1_1_button("click to search")
        assert passed is True

    def test_descriptive_non_action_passes_with_note(self):
        passed, msg = _check_1_1_1_button("Profile picture")
        assert passed is True

    def test_single_digit_fails(self):
        passed, _ = _check_1_1_1_button("5")
        assert passed is False

    def test_none_alt_fails(self):
        passed, _ = _check_1_1_1_button(None)
        assert passed is False

    def test_close_action_word_passes(self):
        passed, _ = _check_1_1_1_button("close")
        assert passed is True

    def test_menu_action_word_passes(self):
        passed, _ = _check_1_1_1_button("menu")
        assert passed is True

    def test_japanese_action_word_passes(self):
        passed, _ = _check_1_1_1_button("検索")
        assert passed is True


# ── _check_4_1_2 ─────────────────────────────────────────────────────────────


class TestCheck412:
    def test_empty_name_fails(self):
        passed, msg = _check_4_1_2("", "buttons")
        assert passed is False
        assert "FAIL" in msg

    def test_none_name_fails(self):
        passed, _ = _check_4_1_2(None, "buttons")
        assert passed is False

    def test_generic_name_image_fails(self):
        passed, _ = _check_4_1_2("image", "icons")
        assert passed is False

    def test_logo_subtype_with_logo_word_passes(self):
        passed, msg = _check_4_1_2("Kao logo", "logos")
        assert passed is True
        assert "PASS" in msg

    def test_logo_subtype_with_home_word_passes(self):
        passed, _ = _check_4_1_2("Home", "logos")
        assert passed is True

    def test_logo_subtype_with_japanese_logo_word_passes(self):
        passed, _ = _check_4_1_2("サービスロゴ", "logos")
        assert passed is True

    def test_logo_subtype_without_logo_fails(self):
        passed, msg = _check_4_1_2("Brand Name", "logos")
        assert passed is False
        assert "logo" in msg.lower()

    def test_icon_subtype_social_brand_only_fails(self):
        passed, msg = _check_4_1_2("twitter", "icons")
        assert passed is False
        assert "icon" in msg.lower()

    def test_icon_subtype_with_icon_passes(self):
        passed, _ = _check_4_1_2("Twitter icon", "icons")
        assert passed is True

    def test_button_subtype_any_name_passes(self):
        passed, _ = _check_4_1_2("Submit form", "buttons")
        assert passed is True

    def test_button_subtype_generic_name_fails(self):
        passed, _ = _check_4_1_2("image", "buttons")
        assert passed is False


class TestCheck145:
    def test_complex_chart_is_exempt_even_when_text_is_detected(self):
        passed, msg = _check_1_4_5("complex", "charts", False, True)
        assert passed is True
        assert "essential presentation" in msg.lower()

    def test_non_logo_image_with_detected_text_fails(self):
        passed, msg = _check_1_4_5("informative", "images", False, True)
        assert passed is False
        assert "replace with real css-styled text" in msg.lower()


# ── AltTextAccessibilityAuditor.generate_audit_report ────────────────────────


class TestAltTextAuditorReport:
    def test_record_count_matches_images(self, tmp_output):
        images = [make_image(filename=f"img{i}.png", src=f"https://example.com/img{i}.png")
                  for i in range(4)]
        auditor = AltTextAccessibilityAuditor()
        records = auditor.generate_audit_report(
            images_data=images, ocr_results=[], output_dir=tmp_output
        )
        assert len(records) == 4

    def test_decorative_empty_alt_passes(self, tmp_output):
        img = make_image(
            classification="decorative", is_decorative=True,
            alt_text="", sub_type="decorative",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "PASSED"
        assert records[0]["overall_status"] == "PASSED"

    def test_decorative_with_alt_text_fails(self, tmp_output):
        img = make_image(
            classification="decorative", is_decorative=True,
            alt_text="Some description", sub_type="decorative",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"
        assert records[0]["overall_status"] == "FAILED"

    def test_missing_alt_fails(self, tmp_output):
        img = make_image(
            classification="decorative", is_decorative=True,
            alt_text="", sub_type="missing_alt",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"

    def test_informative_good_alt_passes(self, tmp_output):
        img = make_image(
            classification="informative",
            alt_text="A scenic mountain at sunset",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "PASSED"

    def test_informative_empty_alt_fails(self, tmp_output):
        img = make_image(classification="informative", alt_text="")
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"

    def test_informative_generic_alt_fails(self, tmp_output):
        img = make_image(classification="informative", alt_text="image")
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"

    def test_functional_logo_good_alt_passes(self, tmp_output):
        img = make_image(
            classification="functional", sub_type="logos",
            is_functional=True, is_logo=True,
            alt_text="Kao logo",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "PASSED"
        assert records[0]["wcag_4_1_2_status"] == "PASSED"
        assert records[0]["overall_status"] == "PASSED"

    def test_functional_logo_bad_alt_fails_both_rules(self, tmp_output):
        img = make_image(
            classification="functional", sub_type="logos",
            is_functional=True, is_logo=True,
            alt_text="Brand name",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"
        assert records[0]["wcag_4_1_2_status"] == "FAILED"
        assert records[0]["overall_status"] == "FAILED"

    def test_functional_icon_social_brand_only_fails(self, tmp_output):
        img = make_image(
            classification="functional", sub_type="icons",
            is_functional=True, is_icon=True,
            alt_text="twitter",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"

    def test_non_functional_image_has_na_for_4_1_2(self, tmp_output):
        img = make_image(
            classification="informative",
            alt_text="A scenic mountain",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_4_1_2_status"] == "N/A"

    def test_ui_component_without_ocr_marks_1_4_11_incomplete(self, tmp_output):
        img = make_image(
            classification="functional",
            sub_type="icons",
            is_functional=True,
            is_icon=True,
            alt_text="Search",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_4_11_status"] == "INCOMPLETE"
        assert records[0]["wcag_1_4_11_reason"].startswith("INCOMPLETE")

    def test_csv_created(self, tmp_output):
        AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[make_image()], ocr_results=[], output_dir=tmp_output
        )
        assert Path(tmp_output, "audit_report.csv").exists()

    def test_csv_has_correct_columns(self, tmp_output):
        AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[make_image()], ocr_results=[], output_dir=tmp_output
        )
        with open(Path(tmp_output, "audit_report.csv"), newline="") as fh:
            cols = csv.DictReader(fh).fieldnames
        expected = [
            "filename", "src", "url", "classification", "sub_type",
            "is_logo", "is_icon", "is_button", "is_functional", "is_decorative",
            "alt_text", "title", "has_ocr_text", "detected_text",
            "contrast_violations_count", "wcag_1_1_1_status", "wcag_4_1_2_status",
            "wcag_1_4_5_status", "wcag_1_4_11_status",
            "overall_status", "wcag_1_1_1_reason", "wcag_4_1_2_reason",
            "wcag_1_4_5_reason", "wcag_1_4_11_reason",
            "screenshot_path", "capture_status", "capture_error",
        ]
        assert cols == expected

    def test_ocr_result_matched_by_filename(self, tmp_output):
        img = make_image(
            classification="informative",
            filename="banner.png",
            alt_text="Buy now sale",
        )
        ocr = _MockOCRResult(filename="banner.png", has_text=True, texts=["Buy", "now", "sale"])
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[ocr], output_dir=tmp_output
        )
        assert records[0]["has_ocr_text"] is True
        assert "buy" in records[0]["detected_text"].lower() or "Buy" in records[0]["detected_text"]

    def test_ocr_not_matched_when_filename_differs(self, tmp_output):
        img = make_image(classification="informative", filename="image.png",
                         alt_text="Some image")
        ocr = _MockOCRResult(filename="other.png", has_text=True, texts=["text"])
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[ocr], output_dir=tmp_output
        )
        assert records[0]["has_ocr_text"] is False

    def test_empty_images_data_returns_empty(self, tmp_output):
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[], ocr_results=[], output_dir=tmp_output
        )
        assert records == []

    def test_complex_image_non_empty_alt_passes(self, tmp_output):
        img = make_image(
            classification="complex", is_complex=True,
            alt_text="Bar chart showing revenue by quarter",
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "PASSED"
        assert records[0]["wcag_1_4_5_status"] == "PASSED"

    def test_complex_image_empty_alt_fails(self, tmp_output):
        img = make_image(classification="complex", is_complex=True, alt_text="")
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["wcag_1_1_1_status"] == "FAILED"

    def test_complex_image_with_ocr_text_keeps_1_4_5_exemption(self, tmp_output):
        img = make_image(
            classification="complex",
            is_complex=True,
            sub_type="charts",
            filename="chart.png",
            alt_text="Quarterly revenue chart",
        )
        ocr = _MockOCRResult(filename="chart.png", has_text=True, texts=["Q1", "Revenue"])
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[ocr], output_dir=tmp_output
        )
        assert records[0]["has_ocr_text"] is True
        assert records[0]["wcag_1_4_5_status"] == "PASSED"
        assert "essential presentation" in records[0]["wcag_1_4_5_reason"].lower()

    def test_overall_status_failed_when_any_check_fails(self, tmp_output):
        img = make_image(
            classification="functional", sub_type="logos",
            is_functional=True, is_logo=True,
            alt_text="brand",  # missing 'logo' word — both checks fail
        )
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[], output_dir=tmp_output
        )
        assert records[0]["overall_status"] == "FAILED"

    def test_contrast_violations_count_from_ocr(self, tmp_output):
        img = make_image(filename="img.png", classification="informative",
                         alt_text="Some image")
        ocr = _MockOCRResult(filename="img.png", has_text=True,
                             texts=["text"], contrast_violations_count=3)
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=[img], ocr_results=[ocr], output_dir=tmp_output
        )
        assert records[0]["contrast_violations_count"] == 3

    def test_multiple_images_all_audited(self, tmp_output):
        images = [
            make_image(filename="a.png", classification="informative",
                       alt_text="Cat sleeping", src="https://x.com/a.png"),
            make_image(filename="b.png", classification="decorative",
                       is_decorative=True, alt_text="",
                       sub_type="decorative", src="https://x.com/b.png"),
            make_image(filename="c.png", classification="decorative",
                       is_decorative=True, alt_text="",
                       sub_type="missing_alt", src="https://x.com/c.png"),
        ]
        records = AltTextAccessibilityAuditor().generate_audit_report(
            images_data=images, ocr_results=[], output_dir=tmp_output
        )
        assert len(records) == 3
        statuses = {r["filename"]: r["wcag_1_1_1_status"] for r in records}
        assert statuses["a.png"] == "PASSED"
        assert statuses["b.png"] == "PASSED"
        assert statuses["c.png"] == "FAILED"
