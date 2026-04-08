"""
Unit tests for WCAG 1.3.3 Sensory Characteristics auditor.
ka11y/accessibility/rules/non_text/sensory_auditor.py
"""

import csv
from pathlib import Path

import pytest

from ka11y.accessibility.rules.non_text import sensory_auditor as sensory_module
from ka11y.accessibility.rules.non_text.sensory_auditor import (
    SensoryCharacteristicsAuditor,
    _violations_133_regex,
)
from ka11y.crawler.sensory_crawler import SensoryElementData


def make_element(**kwargs) -> SensoryElementData:
    defaults = dict(
        page_url="https://example.com",
        tag="p",
        text="Click the round button.",
        html="<p>Click the round button.</p>",
    )
    defaults.update(kwargs)
    return SensoryElementData(**defaults)


class TestViolations133Regex:
    def test_round_button_instruction_fails(self):
        element = make_element(text="Click the round button to continue.")

        viols = _violations_133_regex(element)

        assert len(viols) == 1
        assert viols[0][3] == "FAILED"
        assert "shape" in viols[0][2]

    def test_submit_label_with_sensory_hint_passes(self):
        element = make_element(text="Click the blue Submit button.")

        viols = _violations_133_regex(element)

        assert len(viols) == 1
        assert viols[0][3] == "PASSED"
        assert "color" in viols[0][2]

    def test_required_fields_marked_in_red_fails(self):
        element = make_element(text="Required fields are marked in red.")

        viols = _violations_133_regex(element)

        assert len(viols) == 1
        assert viols[0][3] == "FAILED"
        assert viols[0][2] == ["color"]

    def test_generic_arrow_on_right_still_fails(self):
        element = make_element(text="Press the arrow on the right to continue.")

        viols = _violations_133_regex(element)

        assert len(viols) == 1
        assert viols[0][3] == "FAILED"
        assert "position" in viols[0][2]

    def test_placeholder_text_is_checked_when_visible_text_is_empty(self):
        element = make_element(
            tag="input",
            text="",
            placeholder="Use the field on the left.",
            html="<input placeholder='Use the field on the left.'>",
        )

        viols = _violations_133_regex(element)

        assert len(viols) == 1
        assert viols[0][3] == "FAILED"
        assert "position" in viols[0][2]

    def test_non_instructional_sensory_sentence_is_skipped(self):
        element = make_element(text="The round button is disabled.")

        assert _violations_133_regex(element) == []


class TestSensoryCharacteristicsAuditorReport:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def test_generate_audit_report_uses_regex_fallback_and_writes_csv(
        self, tmp_output, monkeypatch
    ):
        monkeypatch.setattr(sensory_module, "_get_nlp", lambda lang="en": None)
        auditor = SensoryCharacteristicsAuditor(output_dir=tmp_output)
        elements = [
            make_element(text="Click the round button to continue."),
            make_element(text='Click the "Submit" button on the right.'),
            make_element(text="The round button is disabled."),
        ]

        records = auditor.generate_audit_report(elements)

        assert [r["wcag_1_3_3_status"] for r in records] == ["FAILED", "PASSED"]

        csv_path = Path(tmp_output) / "audit_sensory_report.csv"
        assert csv_path.exists()

        with open(csv_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

        assert rows[0]["wcag_1_3_3_status"] == "FAILED"
        assert rows[1]["wcag_1_3_3_status"] == "PASSED"
        assert rows[-1]["page_url"] == "── SUMMARY ──"

    def test_summarize_counts_failed_categories(self):
        summary = SensoryCharacteristicsAuditor.summarize(
            [
                {
                    "overall_status": "FAILED",
                    "page_url": "https://example.com/a",
                    "sensory_categories": "shape, position",
                },
                {
                    "overall_status": "FAILED",
                    "page_url": "https://example.com/b",
                    "sensory_categories": "position",
                },
                {
                    "overall_status": "PASSED",
                    "page_url": "https://example.com/c",
                    "sensory_categories": "color",
                },
            ]
        )

        assert summary == {
            "total_violations": 2,
            "affected_pages": 2,
            "by_sensory_category": {"shape": 1, "position": 2},
        }
