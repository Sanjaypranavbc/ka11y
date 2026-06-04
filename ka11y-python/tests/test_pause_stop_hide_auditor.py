"""
Unit tests for WCAG 2.2.2 Pause, Stop, Hide auditor.
ka11y/accessibility/rules/timing/pause_stop_hide_auditor.py
"""

import csv
import pytest
from pathlib import Path

from ka11y.crawler.moving_content_crawler import MovingContentData
from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import (
    PauseStopHideAuditor,
    _check_222,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper factory
# ─────────────────────────────────────────────────────────────────────────────

def make_item(**kwargs) -> MovingContentData:
    defaults = dict(
        page_url="https://example.com",
        element_index=0,
        content_type="video_autoplay",
        tag="VIDEO",
        starts_automatically=True,
        loops=False,
        duration_seconds=10.0,
        has_mechanism=False,
        has_video_controls=False,
        has_pause_button=False,
        axe_would_catch=False,
        html_snippet="<video autoplay></video>",
    )
    defaults.update(kwargs)
    return MovingContentData(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 — starts_automatically
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck222Gate1StartsAutomatically:
    def test_not_starting_automatically_passes(self):
        item = make_item(starts_automatically=False, has_mechanism=False)
        status, msg = _check_222(item)
        assert status == "PASSED"
        assert msg == ""

    def test_not_starting_automatically_ignores_mechanism_flag(self):
        # Even if has_mechanism is False, the rule doesn't apply
        item = make_item(starts_automatically=False, duration_seconds=60.0, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "PASSED"

    def test_starting_automatically_proceeds_to_further_gates(self):
        item = make_item(starts_automatically=True, duration_seconds=60.0, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 2 — duration threshold (> 5 seconds)
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck222Gate2Duration:
    def test_duration_under_5s_passes(self):
        item = make_item(duration_seconds=3.0, loops=False, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "PASSED"

    def test_duration_exactly_5s_passes(self):
        item = make_item(duration_seconds=5.0, loops=False, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "PASSED"

    def test_duration_just_over_5s_requires_mechanism(self):
        item = make_item(duration_seconds=5.01, loops=False, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"

    def test_duration_minus_one_is_infinite_requires_mechanism(self):
        # -1 means infinite
        item = make_item(duration_seconds=-1, loops=False, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"

    def test_iteration_count_infinite_requires_mechanism(self):
        item = make_item(
            duration_seconds=2.0,
            animation_iteration_count="infinite",
            loops=False,
            has_mechanism=False,
        )
        status, _ = _check_222(item)
        assert status == "FAILED"

    def test_loops_true_requires_mechanism_regardless_of_duration(self):
        # loops=True means total duration is effectively infinite
        item = make_item(duration_seconds=3.0, loops=True, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"

    def test_duration_none_is_treated_as_applicable(self):
        # Unknown duration — treat conservatively as applicable
        item = make_item(duration_seconds=None, loops=False, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"

    def test_short_looping_video_fails(self):
        # 2s per loop but loops=True → infinite total → rule applies
        item = make_item(
            content_type="video_autoplay",
            duration_seconds=2.0,
            loops=True,
            has_mechanism=False,
        )
        status, _ = _check_222(item)
        assert status == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 3 — mechanism check
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck222Gate3Mechanism:
    def test_has_mechanism_passes(self):
        item = make_item(duration_seconds=30.0, has_mechanism=True)
        status, msg = _check_222(item)
        assert status == "PASSED"
        assert msg == ""

    def test_video_controls_constitutes_mechanism(self):
        item = make_item(
            content_type="video_autoplay",
            duration_seconds=30.0,
            has_video_controls=True,
            has_mechanism=True,
        )
        status, _ = _check_222(item)
        assert status == "PASSED"

    def test_pause_button_constitutes_mechanism(self):
        item = make_item(
            content_type="carousel_autoplay",
            duration_seconds=-1,
            has_pause_button=True,
            has_mechanism=True,
        )
        status, _ = _check_222(item)
        assert status == "PASSED"

    def test_no_mechanism_fails(self):
        item = make_item(duration_seconds=30.0, has_mechanism=False)
        status, _ = _check_222(item)
        assert status == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# Violation message content
# ─────────────────────────────────────────────────────────────────────────────

class TestCheck222ViolationMessage:
    def test_message_starts_with_wcag_number(self):
        item = make_item(duration_seconds=30.0, has_mechanism=False)
        _, msg = _check_222(item)
        assert msg.startswith("2.2.2:")

    def test_message_contains_content_type_label_for_video(self):
        item = make_item(content_type="video_autoplay", duration_seconds=30.0)
        _, msg = _check_222(item)
        assert "Video with autoplay" in msg

    def test_message_contains_content_type_label_for_carousel(self):
        item = make_item(content_type="carousel_autoplay", duration_seconds=-1)
        _, msg = _check_222(item)
        assert "Carousel" in msg

    def test_message_contains_content_type_label_for_gif(self):
        item = make_item(content_type="animated_gif", duration_seconds=-1, loops=True)
        _, msg = _check_222(item)
        assert "GIF" in msg

    def test_message_contains_content_type_label_for_css_animation(self):
        item = make_item(content_type="css_animation", duration_seconds=10.0)
        _, msg = _check_222(item)
        assert "CSS" in msg or "animation" in msg.lower()

    def test_message_shows_loops_indefinitely_for_infinite_duration(self):
        item = make_item(duration_seconds=-1, has_mechanism=False)
        _, msg = _check_222(item)
        assert "loops indefinitely" in msg

    def test_message_shows_loops_indefinitely_when_loops_true(self):
        item = make_item(duration_seconds=3.0, loops=True, has_mechanism=False)
        _, msg = _check_222(item)
        assert "loops indefinitely" in msg

    def test_message_shows_loops_indefinitely_for_infinite_iteration_count(self):
        item = make_item(
            duration_seconds=2.0,
            animation_iteration_count="infinite",
            loops=False,
            has_mechanism=False,
        )
        _, msg = _check_222(item)
        assert "loops indefinitely" in msg

    def test_message_shows_duration_in_seconds_for_finite_duration(self):
        item = make_item(duration_seconds=12.5, loops=False, has_mechanism=False)
        _, msg = _check_222(item)
        assert "12.5 s" in msg

    def test_message_shows_unknown_duration_when_none(self):
        item = make_item(duration_seconds=None, loops=False, has_mechanism=False)
        _, msg = _check_222(item)
        assert "unknown duration" in msg

    def test_message_contains_starts_automatically_phrase(self):
        item = make_item(duration_seconds=30.0, has_mechanism=False)
        _, msg = _check_222(item)
        assert "starts automatically" in msg

    def test_message_contains_remediation_hint_for_video(self):
        item = make_item(content_type="video_autoplay", duration_seconds=30.0)
        _, msg = _check_222(item)
        assert "controls" in msg.lower() or "pause" in msg.lower()

    def test_message_contains_remediation_hint_for_carousel(self):
        item = make_item(content_type="carousel_autoplay", duration_seconds=-1)
        _, msg = _check_222(item)
        assert "Pause" in msg or "pause" in msg

    def test_message_contains_remediation_hint_for_marquee(self):
        item = make_item(content_type="marquee_element", duration_seconds=-1)
        _, msg = _check_222(item)
        assert "marquee" in msg.lower() or "deprecated" in msg.lower()

    def test_unknown_content_type_uses_fallback_label_and_hint(self):
        item = make_item(content_type="custom_widget", duration_seconds=30.0)
        _, msg = _check_222(item)
        # Falls back to content_type string as label and generic hint
        assert "custom_widget" in msg or "mechanism" in msg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# PauseStopHideAuditor — generate_audit_report
# ─────────────────────────────────────────────────────────────────────────────

class TestPauseStopHideAuditorReport:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def _sample_items(self):
        return [
            # PASSED: has mechanism
            make_item(element_index=0, content_type="video_autoplay",
                      duration_seconds=30.0, has_mechanism=True, has_video_controls=True),
            # FAILED: carousel, no mechanism, infinite
            make_item(element_index=1, content_type="carousel_autoplay",
                      duration_seconds=-1, loops=True, has_mechanism=False,
                      axe_would_catch=False),
            # PASSED: doesn't start automatically
            make_item(element_index=2, content_type="css_animation",
                      starts_automatically=False, duration_seconds=60.0, has_mechanism=False),
            # PASSED: duration ≤ 5s
            make_item(element_index=3, content_type="css_animation",
                      duration_seconds=4.0, loops=False, has_mechanism=False),
            # FAILED: marquee, caught by axe
            make_item(element_index=4, content_type="marquee_element",
                      duration_seconds=-1, loops=True, has_mechanism=False,
                      axe_would_catch=True),
        ]

    def test_record_count_matches_input(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert len(records) == 5

    def test_correct_statuses(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        statuses = [r["wcag_2_2_2_status"] for r in records]
        assert statuses == ["PASSED", "FAILED", "PASSED", "PASSED", "FAILED"]

    def test_overall_status_mirrors_wcag_status(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        for r in records:
            assert r["overall_status"] == r["wcag_2_2_2_status"]

    def test_passed_record_has_empty_violation_message(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[0]["wcag_2_2_2_violation"] == ""

    def test_failed_record_has_non_empty_violation_message(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[1]["wcag_2_2_2_violation"] != ""

    def test_content_type_label_populated(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[0]["content_type_label"] == "Video with autoplay"
        assert records[1]["content_type_label"] == "Carousel / slider with autoplay"

    def test_axe_would_catch_preserved(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_items())
        assert records[1]["axe_would_catch"] is False   # carousel
        assert records[4]["axe_would_catch"] is True    # marquee

    def test_csv_file_created(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_items())
        csv_path = Path(tmp_output) / "audit_pause_stop_hide_report.csv"
        assert csv_path.exists()

    def test_csv_has_correct_columns(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_items())
        csv_path = Path(tmp_output) / "audit_pause_stop_hide_report.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert set(PauseStopHideAuditor.CSV_FIELDS).issubset(set(reader.fieldnames))

    def test_csv_ends_with_summary_row(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_items())
        csv_path = Path(tmp_output) / "audit_pause_stop_hide_report.csv"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[-1]["page_url"] == "── SUMMARY ──"

    def test_empty_input_produces_no_records(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([])
        assert records == []

    def test_empty_input_still_creates_csv(self, tmp_output):
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        auditor.generate_audit_report([])
        csv_path = Path(tmp_output) / "audit_pause_stop_hide_report.csv"
        assert csv_path.exists()

    def test_all_passed_items_produce_only_passing_records(self, tmp_output):
        items = [
            make_item(element_index=i, duration_seconds=30.0, has_mechanism=True)
            for i in range(3)
        ]
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(items)
        assert all(r["wcag_2_2_2_status"] == "PASSED" for r in records)

    def test_page_url_preserved_in_records(self, tmp_output):
        item = make_item(page_url="https://test.example.org/page", duration_seconds=10.0)
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["page_url"] == "https://test.example.org/page"

    def test_element_index_preserved(self, tmp_output):
        item = make_item(element_index=7, duration_seconds=10.0)
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["element_index"] == 7

    def test_output_dir_created_if_not_exists(self, tmp_path):
        new_dir = str(tmp_path / "new_subdir" / "nested")
        auditor = PauseStopHideAuditor(output_dir=new_dir)
        auditor.generate_audit_report([])
        assert Path(new_dir).exists()

    def test_html_snippet_preserved(self, tmp_output):
        item = make_item(html_snippet="<video autoplay loop></video>", duration_seconds=30.0)
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["html_snippet"] == "<video autoplay loop></video>"

    def test_gif_with_no_mechanism_fails(self, tmp_output):
        item = make_item(
            content_type="animated_gif",
            tag="IMG",
            duration_seconds=-1,
            loops=True,
            has_mechanism=False,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_2_2_status"] == "FAILED"

    def test_marquee_always_fails(self, tmp_output):
        item = make_item(
            content_type="marquee_element",
            tag="MARQUEE",
            duration_seconds=-1,
            loops=True,
            has_mechanism=False,
            axe_would_catch=True,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_2_2_status"] == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# PauseStopHideAuditor — summarize
# ─────────────────────────────────────────────────────────────────────────────

class TestPauseStopHideAuditorSummarize:
    def _make_records(self):
        return [
            {"wcag_2_2_2_status": "PASSED", "content_type": "video_autoplay",    "axe_would_catch": False},
            {"wcag_2_2_2_status": "FAILED", "content_type": "carousel_autoplay",  "axe_would_catch": False},
            {"wcag_2_2_2_status": "FAILED", "content_type": "animated_gif",       "axe_would_catch": False},
            {"wcag_2_2_2_status": "FAILED", "content_type": "marquee_element",    "axe_would_catch": True},
            {"wcag_2_2_2_status": "PASSED", "content_type": "css_animation",      "axe_would_catch": False},
        ]

    def test_total_items(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["total_items"] == 5

    def test_passed_count(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["passed"] == 2

    def test_failed_count(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["failed"] == 3

    def test_wcag_2_2_2_failed_matches_failed(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["wcag_2_2_2_failed"] == summary["failed"]

    def test_pass_rate_correct(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["pass_rate_pct"] == round(2 / 5 * 100, 1)

    def test_axe_would_miss_count(self):
        # 4 items have axe_would_catch=False → axe misses them
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["axe_would_miss"] == 4

    def test_failed_by_type_breakdown(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["failed_by_type"]["carousel_autoplay"] == 1
        assert summary["failed_by_type"]["animated_gif"] == 1
        assert summary["failed_by_type"]["marquee_element"] == 1

    def test_passed_by_type_breakdown(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert summary["passed_by_type"]["video_autoplay"] == 1
        assert summary["passed_by_type"]["css_animation"] == 1

    def test_failed_by_type_excludes_passing_content_types(self):
        summary = PauseStopHideAuditor.summarize(self._make_records())
        assert "video_autoplay" not in summary["failed_by_type"]
        assert "css_animation" not in summary["failed_by_type"]

    def test_empty_records_returns_zero_counts(self):
        summary = PauseStopHideAuditor.summarize([])
        assert summary["total_items"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["pass_rate_pct"] == 0
        assert summary["axe_would_miss"] == 0
        assert summary["failed_by_type"] == {}
        assert summary["passed_by_type"] == {}

    def test_all_passed_zero_failed(self):
        records = [
            {"wcag_2_2_2_status": "PASSED", "content_type": "video_autoplay", "axe_would_catch": False}
        ] * 3
        summary = PauseStopHideAuditor.summarize(records)
        assert summary["failed"] == 0
        assert summary["pass_rate_pct"] == 100.0

    def test_all_failed_zero_passed(self):
        records = [
            {"wcag_2_2_2_status": "FAILED", "content_type": "carousel_autoplay", "axe_would_catch": False}
        ] * 2
        summary = PauseStopHideAuditor.summarize(records)
        assert summary["passed"] == 0
        assert summary["pass_rate_pct"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Content-type specific edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestContentTypeSpecificBehavior:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def test_blink_element_fails_with_no_mechanism(self, tmp_output):
        item = make_item(
            content_type="blink_element",
            tag="BLINK",
            duration_seconds=-1,
            loops=True,
            has_mechanism=False,
            axe_would_catch=True,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_2_2_status"] == "FAILED"

    def test_css_animation_with_pause_button_passes(self, tmp_output):
        item = make_item(
            content_type="css_animation",
            tag="DIV",
            animation_name="slide",
            animation_duration_seconds=8.0,
            animation_iteration_count="infinite",
            duration_seconds=-1,
            loops=True,
            has_mechanism=True,
            has_pause_button=True,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_2_2_status"] == "PASSED"

    def test_video_with_controls_attribute_passes(self, tmp_output):
        item = make_item(
            content_type="video_autoplay",
            duration_seconds=60.0,
            has_video_controls=True,
            has_mechanism=True,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["wcag_2_2_2_status"] == "PASSED"

    def test_animation_fields_preserved_in_record(self, tmp_output):
        item = make_item(
            content_type="css_animation",
            animation_name="bounce",
            animation_duration_seconds=3.0,
            animation_iteration_count="infinite",
            duration_seconds=-1,
        )
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([item])
        assert records[0]["animation_name"] == "bounce"
        assert records[0]["animation_duration_seconds"] == 3.0
        assert records[0]["animation_iteration_count"] == "infinite"

    def test_multiple_items_from_same_page(self, tmp_output):
        url = "https://example.com/page"
        items = [
            make_item(element_index=i, page_url=url, duration_seconds=10.0, has_mechanism=False)
            for i in range(4)
        ]
        auditor = PauseStopHideAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(items)
        assert len(records) == 4
        assert all(r["page_url"] == url for r in records)
