"""
Unit tests for WCAG 1.4.12 Text Spacing auditor.
a11y/accessibility/rules/input_modalities/text_spacing_auditor.py
"""

import pytest
from pathlib import Path

from a11y.crawler.text_spacing_crawler import TextSpacingData
from a11y.accessibility.rules.input_modalities.text_spacing_auditor import (
    TextSpacingAuditor,
    _check_1412,
    _is_text_relevant,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper factory
# ─────────────────────────────────────────────────────────────────────────────


def make_item(**kwargs) -> TextSpacingData:
    defaults = dict(
        page_url="https://example.com",
        element_index=0,
        tag="p",
        element_id=None,
        class_name=None,
        text_length=50,
        text_preview="Some sample text content here.",
        height="auto",
        min_height=None,
        overflow="visible",
        has_fixed_height=False,
        has_overflow_hidden=False,
        html_snippet="<p>Some sample text content here.</p>",
        is_clipped=False,
    )
    defaults.update(kwargs)
    return TextSpacingData(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# _is_text_relevant
# ─────────────────────────────────────────────────────────────────────────────


class TestIsTextRelevant:
    def test_long_paragraph_is_relevant(self):
        item = make_item(tag="p", text_length=50)
        assert _is_text_relevant(item) is True

    def test_short_text_under_20_chars_is_not_relevant(self):
        item = make_item(tag="p", text_length=10)
        assert _is_text_relevant(item) is False

    def test_exactly_20_chars_is_not_relevant(self):
        # text_length < 20 is the boundary; 20 itself is NOT less than 20
        item = make_item(tag="p", text_length=20)
        assert _is_text_relevant(item) is True

    def test_19_chars_is_not_relevant(self):
        item = make_item(tag="p", text_length=19)
        assert _is_text_relevant(item) is False

    def test_html_tag_not_relevant(self):
        item = make_item(tag="html", text_length=100)
        assert _is_text_relevant(item) is False

    def test_body_tag_not_relevant(self):
        item = make_item(tag="body", text_length=100)
        assert _is_text_relevant(item) is False

    def test_img_tag_not_relevant(self):
        item = make_item(tag="img", text_length=100)
        assert _is_text_relevant(item) is False

    def test_svg_tag_not_relevant(self):
        item = make_item(tag="svg", text_length=100)
        assert _is_text_relevant(item) is False

    def test_canvas_tag_not_relevant(self):
        item = make_item(tag="canvas", text_length=100)
        assert _is_text_relevant(item) is False

    def test_div_with_long_text_is_relevant(self):
        item = make_item(tag="div", text_length=200)
        assert _is_text_relevant(item) is True


# ─────────────────────────────────────────────────────────────────────────────
# _check_1412 — N/A cases (P8 fix: was incorrectly returning PASSED)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheck1412NA:
    def test_short_text_returns_na_not_passed(self):
        """P8: non-relevant items must return N/A, not PASSED."""
        item = make_item(tag="p", text_length=5)
        status, _ = _check_1412(item)
        assert status == "N/A"

    def test_empty_text_returns_na(self):
        item = make_item(tag="p", text_length=0)
        status, _ = _check_1412(item)
        assert status == "N/A"

    def test_img_tag_returns_na(self):
        item = make_item(tag="img", text_length=100)
        status, _ = _check_1412(item)
        assert status == "N/A"

    def test_body_tag_returns_na(self):
        item = make_item(tag="body", text_length=500)
        status, _ = _check_1412(item)
        assert status == "N/A"

    def test_na_violation_message_is_non_empty(self):
        """N/A result should carry an explanatory message."""
        item = make_item(tag="p", text_length=3)
        status, msg = _check_1412(item)
        assert status == "N/A"
        assert len(msg) > 0


# ─────────────────────────────────────────────────────────────────────────────
# _check_1412 — PASSED cases (genuinely checked items)
# ─────────────────────────────────────────────────────────────────────────────


class TestCheck1412Passed:
    def test_relevant_no_fixed_height_passes(self):
        """Relevant text element with no height/overflow issue → PASSED."""
        item = make_item(tag="p", text_length=50, has_fixed_height=False, has_overflow_hidden=False)
        status, _ = _check_1412(item)
        assert status == "PASSED"

    def test_text_length_exactly_at_boundary_passes(self):
        """text_length == 20 is relevant (>= 20) and should pass when no issues."""
        item = make_item(tag="p", text_length=20, has_fixed_height=False)
        status, _ = _check_1412(item)
        assert status == "PASSED"


# ─────────────────────────────────────────────────────────────────────────────
# _check_1412 — WARNING cases
# ─────────────────────────────────────────────────────────────────────────────


class TestCheck1412Warning:
    def test_fixed_height_with_overflow_hidden_returns_warning(self):
        item = make_item(
            tag="div",
            text_length=100,
            has_fixed_height=True,
            has_overflow_hidden=True,
        )
        status, msg = _check_1412(item)
        assert status == "WARNING"
        assert "1.4.12" in msg

    def test_fixed_height_only_returns_info(self):
        item = make_item(
            tag="section",
            text_length=80,
            has_fixed_height=True,
            has_overflow_hidden=False,
        )
        status, msg = _check_1412(item)
        assert status == "INFO"
        assert "1.4.12" in msg


# ─────────────────────────────────────────────────────────────────────────────
# TextSpacingAuditor — generate_audit_report
# ─────────────────────────────────────────────────────────────────────────────


class TestTextSpacingAuditor:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def _sample_items(self):
        return [
            # Relevant, no issues → PASSED
            make_item(element_index=0, tag="p", text_length=60),
            # Relevant, fixed height + overflow:hidden → WARNING
            make_item(
                element_index=1,
                tag="div",
                text_length=100,
                has_fixed_height=True,
                has_overflow_hidden=True,
            ),
            # Not relevant (short text) → N/A
            make_item(element_index=2, tag="p", text_length=8),
            # Not relevant (img tag) → N/A
            make_item(element_index=3, tag="img", text_length=200),
        ]

    def test_record_count_matches_items(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert len(records) == 4

    def test_relevant_no_issue_is_passed(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[0]["wcag_1_4_12_status"] == "PASSED"
        assert records[0]["overall_status"] == "PASSED"

    def test_warning_element_has_warning_overall_status(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[1]["wcag_1_4_12_status"] == "WARNING"
        assert records[1]["overall_status"] == "WARNING"

    def test_non_relevant_short_text_returns_na_not_passed(self, tmp_output):
        """P8: non-relevant items must not count as PASSED in overall_status."""
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[2]["wcag_1_4_12_status"] == "N/A"
        assert records[2]["overall_status"] == "N/A"

    def test_img_tag_returns_na_not_passed(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[3]["wcag_1_4_12_status"] == "N/A"
        assert records[3]["overall_status"] == "N/A"

    def test_csv_file_is_created(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_items())
        csv_path = Path(tmp_output) / "audit_text_spacing_report.csv"
        assert csv_path.exists()

    def test_html_snippet_truncated_at_400_chars(self, tmp_output):
        long_html = "<p>" + "x" * 500 + "</p>"
        item = make_item(text_length=50, html_snippet=long_html)
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert len(records[0]["html_snippet"]) <= 400

    def test_empty_items_produces_empty_report(self, tmp_output):
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([])
        assert records == []

    def test_output_dir_created_if_missing(self, tmp_path):
        new_dir = str(tmp_path / "nested" / "output")
        auditor = TextSpacingAuditor(output_dir=new_dir)
        auditor.generate_audit_report([])
        assert Path(new_dir).exists()

    def test_fixed_height_overflow_hidden_element_triggers_warning(self, tmp_output):
        """Direct test for the element type described in the bug spec."""
        item = make_item(
            tag="div",
            text_length=100,
            has_fixed_height=True,
            has_overflow_hidden=True,
            height="100px",
            overflow="hidden",
        )
        auditor = TextSpacingAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_1_4_12_status"] == "WARNING"
        assert "clipping" in records[0]["wcag_1_4_12_violation"].lower() or \
               "overflow" in records[0]["wcag_1_4_12_violation"].lower()
