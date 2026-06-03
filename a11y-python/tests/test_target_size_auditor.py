"""
Tests for WCAG 2.5.8 — Target Size (Minimum)
Covers: _check_258 helper, TargetSizeAuditor.generate_audit_report, TargetSizeAuditor.summarize
"""

import csv
from pathlib import Path


from a11y.accessibility.rules.input_modalities.target_size_auditor import (
    TargetSizeAuditor,
    _check_258,
)
from a11y.crawler.target_size_crawler import TargetSizeData


# ── Factory ───────────────────────────────────────────────────────────────────


def make_item(**kwargs) -> TargetSizeData:
    defaults = dict(
        page_url="https://example.com",
        element_index=0,
        tag="BUTTON",
        role=None,
        element_id=None,
        input_type=None,
        accessible_name="Click me",
        rendered_width_px=32.0,
        rendered_height_px=32.0,
        padding_top_px=0.0,
        padding_bottom_px=0.0,
        padding_left_px=0.0,
        padding_right_px=0.0,
        is_inline_exception=False,
        is_ua_controlled_exception=False,
        is_offset_exception=False,
        required_offset_x_px=0.0,
        required_offset_y_px=0.0,
        nearest_target_gap_x_px=None,
        nearest_target_gap_y_px=None,
        passes_size=True,
        html_snippet="<button>Click me</button>",
    )
    defaults.update(kwargs)
    return TargetSizeData(**defaults)


# ── _check_258 ────────────────────────────────────────────────────────────────


class TestCheck258Exceptions:
    def test_inline_exception_returns_na(self):
        item = make_item(is_inline_exception=True, rendered_width_px=10, rendered_height_px=10)
        status, msg = _check_258(item)
        assert status == "N/A"
        assert "E1" in msg

    def test_ua_controlled_exception_returns_na(self):
        item = make_item(is_ua_controlled_exception=True, rendered_width_px=10, rendered_height_px=10)
        status, msg = _check_258(item)
        assert status == "N/A"
        assert "E4" in msg

    def test_inline_exception_takes_precedence_over_ua(self):
        item = make_item(is_inline_exception=True, is_ua_controlled_exception=True,
                         rendered_width_px=10, rendered_height_px=10)
        status, _ = _check_258(item)
        assert status == "N/A"

    def test_offset_exception_returns_na(self):
        item = make_item(
            rendered_width_px=14,
            rendered_height_px=14,
            is_offset_exception=True,
            required_offset_x_px=5.0,
            required_offset_y_px=5.0,
            nearest_target_gap_x_px=8.0,
            nearest_target_gap_y_px=6.0,
        )
        status, msg = _check_258(item)
        assert status == "N/A"
        assert "E5" in msg

    def test_no_exception_with_large_size_passes(self):
        item = make_item(rendered_width_px=48.0, rendered_height_px=48.0)
        status, _ = _check_258(item)
        assert status == "PASSED"


class TestCheck258SizeCheck:
    def test_exactly_24x24_passes(self):
        item = make_item(rendered_width_px=24.0, rendered_height_px=24.0)
        status, _ = _check_258(item)
        assert status == "PASSED"

    def test_above_threshold_passes(self):
        item = make_item(rendered_width_px=44.0, rendered_height_px=44.0)
        status, _ = _check_258(item)
        assert status == "PASSED"

    def test_width_below_threshold_fails(self):
        item = make_item(rendered_width_px=20.0, rendered_height_px=30.0)
        status, msg = _check_258(item)
        assert status == "FAILED"
        assert "width" in msg
        assert "20" in msg

    def test_height_below_threshold_fails(self):
        item = make_item(rendered_width_px=30.0, rendered_height_px=18.0)
        status, msg = _check_258(item)
        assert status == "FAILED"
        assert "height" in msg
        assert "18" in msg

    def test_both_below_threshold_mentions_both(self):
        item = make_item(rendered_width_px=16.0, rendered_height_px=12.0)
        status, msg = _check_258(item)
        assert status == "FAILED"
        assert "width" in msg
        assert "height" in msg

    def test_zero_size_fails(self):
        item = make_item(rendered_width_px=0.0, rendered_height_px=0.0)
        status, _ = _check_258(item)
        assert status == "FAILED"

    def test_just_below_threshold_fails(self):
        item = make_item(rendered_width_px=23.9, rendered_height_px=24.0)
        status, _ = _check_258(item)
        assert status == "FAILED"

    def test_violation_message_includes_wcag_reference(self):
        item = make_item(rendered_width_px=16.0, rendered_height_px=16.0)
        _, msg = _check_258(item)
        assert "2.5.8" in msg

    def test_violation_message_includes_dimensions(self):
        item = make_item(rendered_width_px=16.0, rendered_height_px=12.0)
        _, msg = _check_258(item)
        assert "16" in msg
        assert "12" in msg

    def test_passed_returns_empty_violation(self):
        item = make_item(rendered_width_px=44.0, rendered_height_px=44.0)
        _, msg = _check_258(item)
        assert msg == ""


# ── generate_audit_report ─────────────────────────────────────────────────────


class TestTargetSizeAuditorReport:
    def test_record_count_matches_input(self, tmp_output):
        items = [make_item(element_index=i) for i in range(5)]
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(items)
        assert len(records) == 5

    def test_passing_element_status(self, tmp_output):
        item = make_item(rendered_width_px=44.0, rendered_height_px=44.0)
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_5_8_status"] == "PASSED"
        assert records[0]["overall_status"] == "PASSED"

    def test_failing_element_status(self, tmp_output):
        item = make_item(rendered_width_px=16.0, rendered_height_px=16.0)
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_5_8_status"] == "FAILED"
        assert records[0]["overall_status"] == "FAILED"

    def test_na_element_status(self, tmp_output):
        item = make_item(is_inline_exception=True, rendered_width_px=10.0, rendered_height_px=10.0)
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_5_8_status"] == "N/A"
        assert records[0]["overall_status"] == "N/A"

    def test_offset_exception_status_is_na(self, tmp_output):
        item = make_item(
            rendered_width_px=12.0,
            rendered_height_px=16.0,
            is_offset_exception=True,
            required_offset_x_px=6.0,
            required_offset_y_px=4.0,
            nearest_target_gap_x_px=10.0,
            nearest_target_gap_y_px=8.0,
        )
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_5_8_status"] == "N/A"
        assert records[0]["overall_status"] == "N/A"

    def test_csv_created(self, tmp_output):
        items = [make_item()]
        TargetSizeAuditor(output_dir=tmp_output).generate_audit_report(items)
        assert Path(tmp_output, "audit_target_size_report.csv").exists()

    def test_csv_has_correct_columns(self, tmp_output):
        items = [make_item()]
        TargetSizeAuditor(output_dir=tmp_output).generate_audit_report(items)
        with open(Path(tmp_output, "audit_target_size_report.csv"), newline="") as fh:
            reader = csv.DictReader(fh)
            cols = reader.fieldnames
        expected = [
            "page_url", "element_index", "tag", "role", "element_id",
            "input_type", "accessible_name", "rendered_width_px",
            "rendered_height_px", "padding_top_px", "padding_bottom_px",
            "padding_left_px", "padding_right_px", "is_inline_exception",
            "is_ua_controlled_exception", "is_offset_exception",
            "required_offset_x_px", "required_offset_y_px",
            "nearest_target_gap_x_px", "nearest_target_gap_y_px",
            "passes_size", "wcag_2_5_8_status", "wcag_2_5_8_violation",
            "overall_status", "selector", "element_ref_id", "frame_path",
            "html_snippet",
        ]
        assert cols == expected

    def test_summary_row_present_in_csv(self, tmp_output):
        items = [make_item()]
        TargetSizeAuditor(output_dir=tmp_output).generate_audit_report(items)
        with open(Path(tmp_output, "audit_target_size_report.csv"), newline="") as fh:
            rows = list(csv.DictReader(fh))
        page_urls = [r["page_url"] for r in rows]
        assert "── SUMMARY ──" in page_urls

    def test_violation_populated_on_failure(self, tmp_output):
        item = make_item(rendered_width_px=16.0, rendered_height_px=16.0)
        auditor = TargetSizeAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_5_8_violation"] != ""
        assert "2.5.8" in records[0]["wcag_2_5_8_violation"]

    def test_no_violation_on_pass(self, tmp_output):
        item = make_item(rendered_width_px=44.0, rendered_height_px=44.0)
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert records[0]["wcag_2_5_8_violation"] == ""

    def test_empty_input_creates_csv(self, tmp_output):
        TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([])
        assert Path(tmp_output, "audit_target_size_report.csv").exists()

    def test_empty_input_returns_empty_records(self, tmp_output):
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([])
        data_rows = [r for r in records]
        assert len(data_rows) == 0

    def test_output_dir_created_if_missing(self, tmp_path):
        out = str(tmp_path / "new" / "nested" / "dir")
        TargetSizeAuditor(output_dir=out).generate_audit_report([])
        assert Path(out).exists()

    def test_html_snippet_truncated_to_400(self, tmp_output):
        long_html = "<button>" + "x" * 500 + "</button>"
        item = make_item(html_snippet=long_html)
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert len(records[0]["html_snippet"]) <= 400

    def test_page_url_preserved(self, tmp_output):
        item = make_item(page_url="https://test.example.com/page")
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert records[0]["page_url"] == "https://test.example.com/page"

    def test_element_index_preserved(self, tmp_output):
        item = make_item(element_index=42)
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert records[0]["element_index"] == 42

    def test_mixed_statuses(self, tmp_output):
        items = [
            make_item(element_index=0, rendered_width_px=44.0, rendered_height_px=44.0),
            make_item(element_index=1, rendered_width_px=16.0, rendered_height_px=16.0),
            make_item(element_index=2, is_inline_exception=True,
                      rendered_width_px=10.0, rendered_height_px=10.0),
        ]
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report(items)
        statuses = {r["element_index"]: r["wcag_2_5_8_status"] for r in records}
        assert statuses[0] == "PASSED"
        assert statuses[1] == "FAILED"
        assert statuses[2] == "N/A"

    def test_tag_preserved(self, tmp_output):
        item = make_item(tag="A")
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert records[0]["tag"] == "A"

    def test_role_preserved(self, tmp_output):
        item = make_item(role="button")
        records = TargetSizeAuditor(output_dir=tmp_output).generate_audit_report([item])
        assert records[0]["role"] == "button"


# ── summarize ─────────────────────────────────────────────────────────────────


class TestTargetSizeAuditorSummarize:
    def _make_records(self, statuses_and_tags):
        return [
            {"wcag_2_5_8_status": s, "tag": t}
            for s, t in statuses_and_tags
        ]

    def test_total_elements(self):
        records = self._make_records([("PASSED", "BUTTON"), ("FAILED", "A"), ("N/A", "INPUT")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["total_elements"] == 3

    def test_passed_count(self):
        records = self._make_records([("PASSED", "A"), ("PASSED", "BUTTON"), ("FAILED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["passed"] == 2

    def test_failed_count(self):
        records = self._make_records([("PASSED", "A"), ("FAILED", "A"), ("FAILED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["failed"] == 2

    def test_na_count(self):
        records = self._make_records([("N/A", "INPUT"), ("N/A", "INPUT"), ("PASSED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["na"] == 2

    def test_checked_excludes_na(self):
        records = self._make_records([("PASSED", "A"), ("FAILED", "A"), ("N/A", "INPUT")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["checked"] == 2

    def test_pass_rate_pct(self):
        records = self._make_records([("PASSED", "A"), ("PASSED", "A"), ("FAILED", "A"), ("FAILED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["pass_rate_pct"] == 50.0

    def test_pass_rate_100_when_all_pass(self):
        records = self._make_records([("PASSED", "BUTTON"), ("PASSED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["pass_rate_pct"] == 100.0

    def test_pass_rate_zero_when_all_fail(self):
        records = self._make_records([("FAILED", "A"), ("FAILED", "BUTTON")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["pass_rate_pct"] == 0.0

    def test_zero_checked_no_division_error(self):
        records = self._make_records([("N/A", "INPUT"), ("N/A", "INPUT")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["pass_rate_pct"] == 0
        assert summary["checked"] == 0

    def test_empty_records(self):
        summary = TargetSizeAuditor.summarize([])
        assert summary["total_elements"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["checked"] == 0
        assert summary["pass_rate_pct"] == 0

    def test_wcag_258_failed_matches_failed_count(self):
        records = self._make_records([("FAILED", "A"), ("FAILED", "BUTTON"), ("PASSED", "A")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["wcag_2_5_8_failed"] == 2

    def test_failed_by_tag_counts(self):
        records = self._make_records([
            ("FAILED", "A"),
            ("FAILED", "A"),
            ("FAILED", "BUTTON"),
            ("PASSED", "A"),
        ])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["failed_by_tag"]["A"] == 2
        assert summary["failed_by_tag"]["BUTTON"] == 1

    def test_failed_by_tag_excludes_na(self):
        records = self._make_records([("N/A", "INPUT"), ("N/A", "INPUT")])
        summary = TargetSizeAuditor.summarize(records)
        assert summary["failed_by_tag"] == {}

    def test_all_keys_present(self):
        summary = TargetSizeAuditor.summarize([])
        expected_keys = {
            "total_elements", "checked", "passed", "failed",
            "na", "pass_rate_pct", "wcag_2_5_8_failed", "failed_by_tag",
        }
        assert expected_keys == set(summary.keys())
