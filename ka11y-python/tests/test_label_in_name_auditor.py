"""
Unit tests for WCAG 2.5.3 Label in Name auditor.
ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py
"""

import csv
import pytest
from pathlib import Path

from ka11y.crawler.interactive_crawler import InteractiveElementData
from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import (
    LabelInNameAuditor,
    _normalize,
    _has_word_chars,
    _label_in_name,
    _contains_cjk,
    _strip_punctuation,
    _check_253,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper factory
# ─────────────────────────────────────────────────────────────────────────────

def make_element(**kwargs) -> InteractiveElementData:
    defaults = dict(
        page_url="https://example.com",
        element_index=0,
        tag="BUTTON",
        html_snippet="<button>Click</button>",
    )
    defaults.update(kwargs)
    return InteractiveElementData(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# _normalize
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalize:
    def test_lowercases_text(self):
        assert _normalize("Hello World") == "hello world"

    def test_strips_leading_trailing_spaces(self):
        assert _normalize("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self):
        assert _normalize("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines(self):
        assert _normalize("hello\t\nworld") == "hello world"

    def test_none_returns_empty(self):
        assert _normalize(None) == ""

    def test_empty_string_returns_empty(self):
        assert _normalize("") == ""

    def test_preserves_unicode(self):
        assert _normalize("Ñoño") == "ñoño"


# ─────────────────────────────────────────────────────────────────────────────
# _has_word_chars
# ─────────────────────────────────────────────────────────────────────────────

class TestHasWordChars:
    def test_regular_text_is_true(self):
        assert _has_word_chars("Submit")

    def test_symbol_only_is_false(self):
        assert not _has_word_chars("✕")

    def test_empty_string_is_false(self):
        assert not _has_word_chars("")

    def test_arrow_symbol_is_false(self):
        assert not _has_word_chars("→")

    def test_digit_counts_as_word_char(self):
        assert _has_word_chars("42")

    def test_mixed_text_and_symbols_is_true(self):
        assert _has_word_chars("Go →")


# ─────────────────────────────────────────────────────────────────────────────
# _check_253 — N/A cases
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck253NA:
    def test_no_visible_label_is_na(self):
        el = make_element(visible_label=None, accessible_name="Close dialog")
        status, _ = _check_253(el)
        assert status == "N/A"

    def test_empty_visible_label_is_na(self):
        el = make_element(visible_label="", accessible_name="Close dialog")
        status, _ = _check_253(el)
        assert status == "N/A"

    def test_symbol_only_label_is_na(self):
        el = make_element(visible_label="✕", accessible_name="Close dialog")
        status, _ = _check_253(el)
        assert status == "N/A"

    def test_arrow_only_label_is_na(self):
        el = make_element(visible_label="→", accessible_name="Next")
        status, _ = _check_253(el)
        assert status == "N/A"


# ─────────────────────────────────────────────────────────────────────────────
# _check_253 — FAILED cases
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck253Failed:
    def test_no_accessible_name_is_failed(self):
        el = make_element(visible_label="Submit", accessible_name=None)
        status, msg = _check_253(el)
        assert status == "FAILED"
        assert "No accessible name" in msg

    def test_empty_accessible_name_is_failed(self):
        el = make_element(visible_label="Submit", accessible_name="")
        status, msg = _check_253(el)
        assert status == "FAILED"

    def test_name_not_containing_visible_label_is_failed(self):
        # "Learn more about accessibility" does not contain "Read more"
        el = make_element(
            visible_label="Read more",
            accessible_name="Learn more about accessibility",
        )
        status, msg = _check_253(el)
        assert status == "FAILED"
        assert "Read more" in msg

    def test_completely_different_name_is_failed(self):
        el = make_element(visible_label="Home", accessible_name="Go to start page")
        status, msg = _check_253(el)
        assert status == "FAILED"

    def test_violation_message_mentions_both_label_and_name(self):
        el = make_element(
            visible_label="Buy now",
            accessible_name="Purchase this item immediately",
        )
        _, msg = _check_253(el)
        assert "Buy now" in msg
        assert "Purchase this item immediately" in msg


# ─────────────────────────────────────────────────────────────────────────────
# _check_253 — PASSED cases
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck253Passed:
    def test_exact_match_passes(self):
        el = make_element(visible_label="Submit", accessible_name="Submit")
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_accessible_name_contains_visible_label_passes(self):
        el = make_element(
            visible_label="Search",
            accessible_name="Search this website",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_case_insensitive_match_passes(self):
        # "navigate to home page" contains "Home" (lowercased)
        el = make_element(visible_label="Home", accessible_name="Navigate to home page")
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_extra_text_before_visible_label_passes(self):
        el = make_element(visible_label="Submit", accessible_name="Please Submit the form")
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_whitespace_normalised_match_passes(self):
        el = make_element(
            visible_label="  Next  page  ",
            accessible_name="Go to next page",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_cjk_visible_label_substring_match_passes(self):
        el = make_element(
            visible_label="検索",
            accessible_name="サイト内検索を開く",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_cjk_visible_label_missing_fails(self):
        el = make_element(
            visible_label="検索",
            accessible_name="メニューを開く",
        )
        status, _ = _check_253(el)
        assert status == "FAILED"


class TestCJKHelpers:
    def test_contains_cjk_true_for_hiragana(self):
        assert _contains_cjk("お知らせ")

    def test_contains_cjk_false_for_ascii(self):
        assert not _contains_cjk("search")


# ─────────────────────────────────────────────────────────────────────────────
# LabelInNameAuditor — generate_audit_report
# ─────────────────────────────────────────────────────────────────────────────

class TestLabelInNameAuditor:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def _make_elements(self):
        return [
            make_element(element_index=0, visible_label="Submit", accessible_name="Submit form"),           # PASSED
            make_element(element_index=1, visible_label="Home",   accessible_name="Go to start page"),     # FAILED
            make_element(element_index=2, visible_label="✕",      accessible_name="Close dialog"),         # N/A
            make_element(element_index=3, visible_label="Search",  accessible_name=None),                  # FAILED
        ]

    def test_records_count_matches_elements(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._make_elements())
        assert len(records) == 4

    def test_correct_statuses(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._make_elements())
        statuses = [r["wcag_2_5_3_status"] for r in records]
        assert statuses == ["PASSED", "FAILED", "N/A", "FAILED"]

    def test_overall_status_mirrors_wcag_status(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._make_elements())
        for r in records:
            assert r["overall_status"] == r["wcag_2_5_3_status"]

    def test_csv_file_is_created(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._make_elements())
        csv_path = Path(tmp_output) / "audit_label_in_name_report.csv"
        assert csv_path.exists()

    def test_csv_has_correct_columns(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._make_elements())
        csv_path = Path(tmp_output) / "audit_label_in_name_report.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert set(LabelInNameAuditor.CSV_FIELDS).issubset(set(reader.fieldnames))

    def test_csv_ends_with_summary_row(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._make_elements())
        csv_path = Path(tmp_output) / "audit_label_in_name_report.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # Last row is the summary
        assert rows[-1]["page_url"] == "── SUMMARY ──"

    def test_empty_input_produces_empty_report(self, tmp_output):
        auditor = LabelInNameAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([])
        assert records == []


# ─────────────────────────────────────────────────────────────────────────────
# LabelInNameAuditor — summarize
# ─────────────────────────────────────────────────────────────────────────────

class TestLabelInNameSummarize:
    def _make_records(self):
        return [
            {"wcag_2_5_3_status": "PASSED"},
            {"wcag_2_5_3_status": "FAILED"},
            {"wcag_2_5_3_status": "N/A"},
            {"wcag_2_5_3_status": "FAILED"},
        ]

    def test_total_elements(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["total_elements"] == 4

    def test_passed_count(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["passed"] == 1

    def test_failed_count(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["failed"] == 2

    def test_na_count(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["na"] == 1

    def test_checked_is_passed_plus_failed(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["checked"] == 3

    def test_pass_rate_correct(self):
        summary = LabelInNameAuditor.summarize(self._make_records())
        assert summary["pass_rate_pct"] == round(1 / 3 * 100, 1)

    def test_zero_checked_does_not_divide_by_zero(self):
        summary = LabelInNameAuditor.summarize([{"wcag_2_5_3_status": "N/A"}])
        assert summary["pass_rate_pct"] == 0

    def test_all_passed(self):
        records = [{"wcag_2_5_3_status": "PASSED"}] * 5
        summary = LabelInNameAuditor.summarize(records)
        assert summary["pass_rate_pct"] == 100.0
        assert summary["failed"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# P11: Punctuation stripping — _strip_punctuation and _label_in_name
# ─────────────────────────────────────────────────────────────────────────────


class TestStripPunctuation:
    def test_trailing_exclamation_stripped(self):
        assert _strip_punctuation("Go!") == "Go"

    def test_leading_punctuation_stripped(self):
        assert _strip_punctuation("!Go") == "Go"

    def test_multiple_punctuation_stripped(self):
        assert _strip_punctuation("Go!!!") == "Go"

    def test_text_with_no_punctuation_unchanged(self):
        assert _strip_punctuation("Submit") == "Submit"

    def test_empty_string_stays_empty(self):
        assert _strip_punctuation("") == ""

    def test_punctuation_only_becomes_empty(self):
        assert _strip_punctuation("!!!") == ""


class TestLabelInNamePunctuation:
    def test_label_ending_exclamation_matches_name(self):
        """P11: 'Go!' should match accessible name 'Go to next page'."""
        assert _label_in_name("go!", "go to next page") is True

    def test_label_with_multiple_punctuation_matches(self):
        assert _label_in_name("go!!!", "go to next page") is True

    def test_plain_label_still_works(self):
        assert _label_in_name("submit", "submit the form") is True

    def test_hyphenated_label_matches_hyphenated_name(self):
        assert _label_in_name("css-tricks", "css-tricks") is True

    def test_dotted_label_matches_dotted_name(self):
        assert _label_in_name("the govt.nz app", "download the govt.nz app") is True

    def test_non_matching_label_still_fails(self):
        assert _label_in_name("read more!", "learn more about accessibility") is False

    def test_empty_label_always_matches(self):
        assert _label_in_name("", "anything") is True


# ─────────────────────────────────────────────────────────────────────────────
# P11: _check_253 — punctuation-in-label integration tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCheck253Punctuation:
    def test_label_ending_exclamation_matches_accessible_name(self):
        """P11: visible label 'Go!' must match accessible name 'Go to next page'."""
        el = make_element(
            visible_label="Go!",
            accessible_name="Go to next page",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_label_with_multiple_punctuation_matches(self):
        el = make_element(
            visible_label="Submit!!",
            accessible_name="Submit the registration form",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_label_submit_exclamation_matches_submit_form(self):
        """'Submit!' should match accessible name 'Submit form'."""
        el = make_element(
            visible_label="Submit!",
            accessible_name="Submit form",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_punctuation_does_not_cause_false_positive(self):
        """'Buy!' should NOT match 'Purchase this item'."""
        el = make_element(
            visible_label="Buy!",
            accessible_name="Purchase this item",
        )
        status, _ = _check_253(el)
        assert status == "FAILED"

    def test_empty_label_after_punctuation_strip_is_na(self):
        """A label that is purely punctuation has no word chars → N/A."""
        el = make_element(
            visible_label="!!!",
            accessible_name="Click here",
        )
        status, _ = _check_253(el)
        # "!!!" has no word characters → N/A (no visible text rule)
        assert status == "N/A"

    def test_hyphenated_visible_label_matches_identical_accessible_name(self):
        el = make_element(
            visible_label="CSS-Tricks",
            accessible_name="CSS-Tricks",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"

    def test_dotted_visible_label_matches_identical_accessible_name(self):
        el = make_element(
            visible_label="The Govt.nz app",
            accessible_name="The Govt.nz app",
        )
        status, _ = _check_253(el)
        assert status == "PASSED"
