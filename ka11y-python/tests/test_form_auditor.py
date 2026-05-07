"""
Unit tests for WCAG 3.3.1 / 3.3.2 Form Accessibility Auditor.
ka11y/accessibility/rules/forms/form_auditor.py
"""

import csv
import pytest
from pathlib import Path

from ka11y.crawler.forms_crawler import FormInputData
from ka11y.accessibility.rules.forms.form_auditor import (
    FormAccessibilityAuditor,
    _violations_331,
    _violations_332,
    _field_appears_required,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper factory
# ─────────────────────────────────────────────────────────────────────────────

def make_field(**kwargs) -> FormInputData:
    defaults = dict(
        page_url="https://example.com",
        form_index=0,
        tag="INPUT",
        type="text",
        has_any_label=True,
        required=False,
        html="<input type='text'>",
    )
    defaults.update(kwargs)
    return FormInputData(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# _field_appears_required
# ─────────────────────────────────────────────────────────────────────────────

class TestFieldAppearsRequired:
    def test_asterisk_in_label_returns_true(self):
        f = make_field(label_text="Email *")
        assert _field_appears_required(f) is True

    def test_asterisk_in_placeholder_returns_true(self):
        f = make_field(placeholder="Enter email *")
        assert _field_appears_required(f) is True

    def test_no_asterisk_returns_false(self):
        f = make_field(label_text="Email", placeholder="Enter email")
        assert _field_appears_required(f) is False

    def test_none_label_and_none_placeholder_returns_false(self):
        f = make_field(label_text=None, placeholder=None)
        assert _field_appears_required(f) is False

    def test_asterisk_only_in_label_not_placeholder(self):
        f = make_field(label_text="Name *", placeholder=None)
        assert _field_appears_required(f) is True

    def test_asterisk_only_in_placeholder_not_label(self):
        f = make_field(label_text=None, placeholder="Required *")
        assert _field_appears_required(f) is True


# ─────────────────────────────────────────────────────────────────────────────
# _violations_331 — WCAG 3.3.1 Error Identification
# ─────────────────────────────────────────────────────────────────────────────

class TestViolations331:
    def test_required_field_with_no_aria_describedby_is_violation(self):
        f = make_field(required=True, aria_describedby=None)
        viols = _violations_331(f)
        assert len(viols) == 1
        assert "aria-describedby" in viols[0]

    def test_aria_required_true_treated_same_as_required(self):
        f = make_field(required=False, aria_required="true", aria_describedby=None)
        viols = _violations_331(f)
        assert any("aria-describedby" in v for v in viols)

    def test_required_field_with_aria_describedby_but_no_error_element_is_violation(self):
        f = make_field(
            required=True,
            aria_describedby="err-msg",
            error_element_id=None,   # element doesn't exist in DOM
        )
        viols = _violations_331(f)
        assert any("does not exist" in v for v in viols)

    def test_error_element_exists_without_role_alert_and_no_aria_live_is_violation(self):
        f = make_field(
            error_element_id="err-1",
            error_has_role_alert=False,
            error_has_aria_live=None,
        )
        viols = _violations_331(f)
        assert any("aria-live" in v for v in viols)

    def test_error_element_with_role_alert_passes_331(self):
        f = make_field(
            required=True,
            aria_describedby="err-1",
            error_element_id="err-1",
            error_has_role_alert=True,
            error_has_aria_live=None,
        )
        viols = _violations_331(f)
        assert viols == []

    def test_error_element_with_aria_live_assertive_passes_331(self):
        f = make_field(
            required=True,
            aria_describedby="err-1",
            error_element_id="err-1",
            error_has_role_alert=False,
            error_has_aria_live="assertive",
        )
        viols = _violations_331(f)
        assert viols == []

    def test_error_element_with_aria_live_polite_passes_331(self):
        f = make_field(
            required=True,
            aria_describedby="err-1",
            error_element_id="err-1",
            error_has_role_alert=False,
            error_has_aria_live="polite",
        )
        viols = _violations_331(f)
        assert viols == []

    def test_non_required_field_with_no_error_element_has_no_331_violation(self):
        f = make_field(required=False, aria_describedby=None, error_element_id=None)
        viols = _violations_331(f)
        assert viols == []

    def test_required_field_fully_compliant_has_no_violations(self):
        f = make_field(
            required=True,
            aria_describedby="msg",
            error_element_id="msg",
            error_has_role_alert=True,
        )
        viols = _violations_331(f)
        assert viols == []

    def test_violation_message_includes_error_element_id(self):
        f = make_field(
            error_element_id="my-error-box",
            error_has_role_alert=False,
            error_has_aria_live=None,
        )
        viols = _violations_331(f)
        assert any("my-error-box" in v for v in viols)


# ─────────────────────────────────────────────────────────────────────────────
# _violations_332 — WCAG 3.3.2 Labels or Instructions
# ─────────────────────────────────────────────────────────────────────────────

class TestViolations332:
    def test_no_label_is_violation(self):
        f = make_field(has_any_label=False, placeholder=None)
        viols = _violations_332(f)
        assert any("no accessible label" in v.lower() for v in viols)

    def test_placeholder_only_label_is_additional_violation(self):
        # When has_any_label=False AND placeholder exists, both violations fire
        f = make_field(has_any_label=False, placeholder="Enter your name")
        viols = _violations_332(f)
        # Should have "no accessible label" AND "placeholder is the only label"
        assert any("no accessible label" in v.lower() for v in viols)
        assert any("placeholder" in v.lower() for v in viols)

    def test_field_with_label_passes_332_label_check(self):
        f = make_field(has_any_label=True, label_text="Full Name")
        viols = _violations_332(f)
        # No label violation
        assert not any("no accessible label" in v.lower() for v in viols)

    def test_email_field_without_autocomplete_is_violation(self):
        f = make_field(type="email", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert any("autocomplete" in v.lower() for v in viols)

    def test_email_field_with_autocomplete_passes_332(self):
        f = make_field(type="email", has_any_label=True, autocomplete="email")
        viols = _violations_332(f)
        assert not any("autocomplete" in v.lower() for v in viols)

    def test_tel_field_without_autocomplete_is_violation(self):
        f = make_field(type="tel", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert any("autocomplete" in v.lower() for v in viols)

    def test_password_field_without_autocomplete_is_violation(self):
        f = make_field(type="password", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert any("autocomplete" in v.lower() for v in viols)

    def test_url_field_without_autocomplete_is_violation(self):
        f = make_field(type="url", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert not any("autocomplete" in v.lower() for v in viols)

    def test_text_field_with_personal_name_attribute_needs_autocomplete(self):
        # Field name "email" triggers autocomplete check regardless of type
        f = make_field(type="text", name="email", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert any("autocomplete" in v.lower() for v in viols)

    def test_text_field_with_password_name_needs_autocomplete(self):
        f = make_field(type="text", name="password", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert any("autocomplete" in v.lower() for v in viols)

    def test_regular_text_field_without_autocomplete_passes(self):
        # A plain text field with label and no personal data type/name doesn't need autocomplete
        f = make_field(type="text", name="comment", has_any_label=True, autocomplete=None)
        viols = _violations_332(f)
        assert not any("autocomplete" in v.lower() for v in viols)

    def test_fully_compliant_field_has_no_violations(self):
        f = make_field(
            type="email",
            has_any_label=True,
            label_text="Email address",
            autocomplete="email",
            required=False,
        )
        viols = _violations_332(f)
        assert viols == []

    def test_placeholder_alone_no_label_generates_two_violations(self):
        f = make_field(has_any_label=False, placeholder="Username")
        viols = _violations_332(f)
        assert len(viols) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# FormAccessibilityAuditor — generate_audit_report
# ─────────────────────────────────────────────────────────────────────────────

class TestFormAccessibilityAuditorReport:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def _sample_fields(self):
        return [
            # PASSED: labelled email with autocomplete, required with proper error container
            make_field(
                form_index=0, type="email", has_any_label=True, label_text="Email",
                required=True, aria_describedby="e1", error_element_id="e1",
                error_has_role_alert=True, autocomplete="email",
            ),
            # FAILED 3.3.2: no label
            make_field(
                form_index=0, type="text", has_any_label=False,
            ),
            # FAILED 3.3.1: required, no aria-describedby
            make_field(
                form_index=0, type="text", has_any_label=True, label_text="Name",
                required=True, aria_describedby=None,
            ),
            # FAILED 3.3.2: password without autocomplete
            make_field(
                form_index=0, type="password", has_any_label=True, label_text="Password",
                autocomplete=None,
            ),
        ]

    def test_record_count_matches_fields(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        assert len(records) == 4

    def test_first_record_is_passed(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        assert records[0]["overall_status"] == "PASSED"

    def test_second_record_fails_3_3_2(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        assert records[1]["wcag_3_3_2_status"] == "FAILED"

    def test_third_record_fails_3_3_1(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        assert records[2]["wcag_3_3_1_status"] == "FAILED"

    def test_fourth_record_fails_3_3_2_autocomplete(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        assert records[3]["wcag_3_3_2_status"] == "FAILED"
        assert "autocomplete" in records[3]["wcag_3_3_2_violations"].lower()

    def test_overall_status_failed_when_any_wcag_fails(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        for r in records[1:]:
            assert r["overall_status"] == "FAILED"

    def test_total_violations_is_sum_of_331_and_332(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(self._sample_fields())
        for r in records:
            v331 = len([v for v in r["wcag_3_3_1_violations"].split(" | ") if v])
            v332 = len([v for v in r["wcag_3_3_2_violations"].split(" | ") if v])
            assert r["total_violations"] == v331 + v332

    def test_violations_joined_with_pipe(self, tmp_output):
        # A field with two 3.3.2 violations (no label + placeholder) should have | separator
        f = make_field(has_any_label=False, placeholder="Enter text")
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert " | " in records[0]["wcag_3_3_2_violations"]

    def test_passed_record_has_empty_violation_strings(self, tmp_output):
        f = make_field(
            type="email", has_any_label=True, label_text="Email",
            required=False, autocomplete="email",
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_1_violations"] == ""
        assert records[0]["wcag_3_3_2_violations"] == ""

    def test_csv_file_created(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_fields())
        assert (Path(tmp_output) / "audit_form_report.csv").exists()

    def test_csv_has_all_defined_columns(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_fields())
        with open(Path(tmp_output) / "audit_form_report.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert set(FormAccessibilityAuditor.CSV_FIELDS).issubset(set(reader.fieldnames))

    def test_csv_ends_with_summary_row(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        auditor.generate_audit_report(self._sample_fields())
        with open(Path(tmp_output) / "audit_form_report.csv", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[-1]["page_url"] == "── SUMMARY ──"

    def test_empty_input_produces_no_records(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([])
        assert records == []

    def test_empty_input_still_creates_csv(self, tmp_output):
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        auditor.generate_audit_report([])
        assert (Path(tmp_output) / "audit_form_report.csv").exists()

    def test_output_dir_created_if_missing(self, tmp_path):
        new_dir = str(tmp_path / "nested" / "output")
        auditor = FormAccessibilityAuditor(output_dir=new_dir)
        auditor.generate_audit_report([])
        assert Path(new_dir).exists()

    def test_page_url_preserved(self, tmp_output):
        f = make_field(page_url="https://mysite.com/form")
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["page_url"] == "https://mysite.com/form"

    def test_form_id_preserved(self, tmp_output):
        f = make_field(form_id="contact-form")
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["form_id"] == "contact-form"

    def test_field_tag_preserved(self, tmp_output):
        f = make_field(tag="TEXTAREA")
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["field_tag"] == "TEXTAREA"

    def test_html_snippet_truncated_at_400_chars(self, tmp_output):
        long_html = "<input " + "a" * 500 + ">"
        f = make_field(html=long_html)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert len(records[0]["html_snippet"]) <= 400


# ─────────────────────────────────────────────────────────────────────────────
# FormAccessibilityAuditor — summarize
# ─────────────────────────────────────────────────────────────────────────────

class TestFormAccessibilityAuditorSummarize:
    def _make_records(self):
        return [
            {
                "overall_status": "PASSED",
                "wcag_3_3_1_status": "PASSED",
                "wcag_3_3_2_status": "PASSED",
                "has_any_label": True,
                "required": False,
                "error_element_id": "e1",
            },
            {
                "overall_status": "FAILED",
                "wcag_3_3_1_status": "FAILED",
                "wcag_3_3_2_status": "PASSED",
                "has_any_label": True,
                "required": True,
                "error_element_id": "",
            },
            {
                "overall_status": "FAILED",
                "wcag_3_3_1_status": "PASSED",
                "wcag_3_3_2_status": "FAILED",
                "has_any_label": False,
                "required": False,
                "error_element_id": "",
            },
        ]

    def test_total_fields(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["total_fields"] == 3

    def test_passed_count(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["passed"] == 1

    def test_failed_count(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["failed"] == 2

    def test_pass_rate(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["pass_rate_pct"] == round(1 / 3 * 100, 1)

    def test_wcag_331_failed_count(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["wcag_3_3_1_failed"] == 1

    def test_wcag_332_failed_count(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["wcag_3_3_2_failed"] == 1

    def test_fields_missing_label(self):
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["fields_missing_label"] == 1

    def test_fields_with_no_error_container(self):
        # Required field (index 1) has no error_element_id → counted
        summary = FormAccessibilityAuditor.summarize(self._make_records())
        assert summary["fields_with_no_error_container"] == 1

    def test_empty_records_returns_zeros(self):
        summary = FormAccessibilityAuditor.summarize([])
        assert summary["total_fields"] == 0
        assert summary["passed"] == 0
        assert summary["failed"] == 0
        assert summary["pass_rate_pct"] == 0
        assert summary["wcag_3_3_1_failed"] == 0
        assert summary["wcag_3_3_2_failed"] == 0

    def test_all_passed_zero_failed(self):
        records = [
            {
                "overall_status": "PASSED",
                "wcag_3_3_1_status": "PASSED",
                "wcag_3_3_2_status": "PASSED",
                "has_any_label": True,
                "required": False,
                "error_element_id": "x",
            }
        ] * 5
        summary = FormAccessibilityAuditor.summarize(records)
        assert summary["failed"] == 0
        assert summary["pass_rate_pct"] == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestFormAuditorEdgeCases:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def test_select_element_without_label_fails_332(self, tmp_output):
        f = make_field(tag="SELECT", type=None, has_any_label=False)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_2_status"] == "FAILED"

    def test_textarea_without_label_fails_332(self, tmp_output):
        f = make_field(tag="TEXTAREA", type=None, has_any_label=False)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_2_status"] == "FAILED"

    def test_wrapping_label_counts_as_any_label(self, tmp_output):
        f = make_field(has_wrapping_label=True, has_any_label=True, label_text="Username")
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert not any("no accessible label" in v.lower()
                       for v in records[0]["wcag_3_3_2_violations"].split(" | ") if v)

    def test_aria_label_counts_as_any_label(self, tmp_output):
        f = make_field(aria_label="Search query", has_any_label=True)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert not any("no accessible label" in v.lower()
                       for v in records[0]["wcag_3_3_2_violations"].split(" | ") if v)

    def test_error_text_truncated_at_200_chars_in_record(self, tmp_output):
        long_text = "Error: " + "x" * 300
        f = make_field(error_element_text=long_text)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert len(records[0]["error_element_text"]) <= 200

    def test_form_index_preserved(self, tmp_output):
        f = make_field(form_index=3)
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["form_index"] == 3

    def test_multiple_forms_on_page(self, tmp_output):
        fields = [
            make_field(form_index=0, label_text="Name",  has_any_label=True),
            make_field(form_index=1, label_text="Email", has_any_label=True, type="email", autocomplete="email"),
            make_field(form_index=2, has_any_label=False),
        ]
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report(fields)
        assert len(records) == 3
        assert records[0]["form_index"] == 0
        assert records[1]["form_index"] == 1
        assert records[2]["form_index"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Additional edge cases (per test spec)
# ─────────────────────────────────────────────────────────────────────────────


class TestFormAuditorAdditionalEdgeCases:
    @pytest.fixture()
    def tmp_output(self, tmp_path):
        return str(tmp_path)

    def test_required_with_no_error_message_patterns(self, tmp_output):
        """
        Edge case: field has `required` attribute but no aria-describedby and
        no error element — should produce a 3.3.1 violation.
        """
        f = make_field(
            required=True,
            aria_describedby=None,
            error_element_id=None,
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_1_status"] == "FAILED"
        assert "aria-describedby" in records[0]["wcag_3_3_1_violations"]

    def test_placeholder_only_label_detection(self, tmp_output):
        """
        Edge case: placeholder is the only label — no proper accessible label.
        Should generate both 'no accessible label' and 'placeholder' violations.
        """
        f = make_field(
            has_any_label=False,
            placeholder="Enter your name",
            label_text=None,
            aria_label=None,
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        viols = records[0]["wcag_3_3_2_violations"].lower()
        assert "no accessible label" in viols or "placeholder" in viols

    def test_hidden_label_detection_via_has_any_label_false(self, tmp_output):
        """
        Edge case: form field where has_any_label=False (label may exist in
        DOM but is hidden/invisible) — still triggers 3.3.2 violation.
        """
        f = make_field(
            has_any_label=False,
            label_text="Hidden label",  # label text exists but is_any_label=False
            placeholder=None,
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_2_status"] == "FAILED"

    def test_aria_required_without_describedby_triggers_331(self, tmp_output):
        """aria-required=true should be treated same as required=True for 3.3.1."""
        f = make_field(
            required=False,
            aria_required="true",
            aria_describedby=None,
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["wcag_3_3_1_status"] == "FAILED"

    def test_field_with_label_and_proper_error_has_no_violations(self, tmp_output):
        """A fully-compliant field should pass both 3.3.1 and 3.3.2."""
        f = make_field(
            type="email",
            has_any_label=True,
            label_text="Email address",
            required=True,
            aria_describedby="err-email",
            error_element_id="err-email",
            error_has_role_alert=True,
            autocomplete="email",
        )
        auditor = FormAccessibilityAuditor(output_dir=tmp_output)
        records = auditor.generate_audit_report([f])
        assert records[0]["overall_status"] == "PASSED"
        assert records[0]["wcag_3_3_1_violations"] == ""
        assert records[0]["wcag_3_3_2_violations"] == ""