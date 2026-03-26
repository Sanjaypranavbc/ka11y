"""
ka11y/accessibility/rules/forms/wcag_331_auditor.py
====================================================
WCAG 3.3.1 / 3.3.2 Form Accessibility Auditor.

Rules checked
─────────────
  3.3.1 A  — Error Identification
      • Required field with no error-message container linked via aria-describedby
      • Error container exists but lacks role="alert" (screen readers won't auto-announce)
      • Error container exists but aria-live is not set (alternative to role="alert")

  3.3.2 A  — Labels or Instructions
      • Input has no accessible name (no label, aria-label, or aria-labelledby)
      • Required field not marked required / aria-required="true"
      • Password / email / tel field missing autocomplete attribute

Output
──────
  audit_form_report.csv  (written to output_dir)

CSV columns
───────────
  page_url, form_index, form_id, field_tag, field_type, field_id, field_name,
  label_text, has_any_label, required, aria_invalid,
  wcag_3_3_1_status, wcag_3_3_1_violations,
  wcag_3_3_2_status, wcag_3_3_2_violations,
  overall_status, total_violations,
  error_element_id, error_element_role, error_has_role_alert,
  error_has_aria_live, error_element_text,
  html_snippet
"""

import csv
from pathlib import Path
from typing import List, Dict, Any

from ka11y.crawler.forms_crawler import FormInputData

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _violations_331(f: FormInputData) -> List[str]:
    """
    WCAG 3.3.1 — Error Identification
    Checks that error messages are:
      (a) present (linked via aria-describedby)
      (b) programmatically associated (role="alert" OR aria-live)
    """
    viols = []

    # (a) Required field with no error container at all
    if f.required or (f.aria_required or "").strip().lower() == "true":
        if not f.aria_describedby:
            viols.append(
                "3.3.1: Required field has no aria-describedby — "
                "error messages cannot be associated programmatically."
            )
        elif not f.error_element_id:
            viols.append(
                "3.3.1: aria-describedby references an element that does not exist in the DOM."
            )

    # (b) Error container exists but missing role="alert" AND missing aria-live
    if f.error_element_id:
        has_live = f.error_has_role_alert or (
            f.error_has_aria_live in ("assertive", "polite")
        )
        if not has_live:
            viols.append(
                "3.3.1: Error container (#"
                + f.error_element_id
                + ') has neither role="alert" nor aria-live — '
                "screen readers will not announce validation errors automatically."
            )

    return viols


def _violations_332(f: FormInputData) -> List[str]:
    """
    WCAG 3.3.2 — Labels or Instructions
    Checks that every field has a visible / programmatic label,
    required state is communicated, and autocomplete is set for
    personal-data fields.
    """
    viols = []

    # (a) No accessible name
    if not f.has_any_label:
        viols.append(
            "3.3.2: Input has no accessible label — "
            "add <label for>, aria-label, or aria-labelledby."
        )

    # (b) Required but not marked in HTML/ARIA
    is_marked_required = f.required or (f.aria_required or "").strip().lower() == "true"
    if not is_marked_required and _field_appears_required(f):
        # heuristic: placeholder or label contains * but required attribute is absent
        viols.append(
            "3.3.2: Field appears required (label/placeholder contains '*') "
            "but is not marked with required or aria-required='true' — "
            "screen readers cannot programmatically determine it is mandatory."
        )

    # (c) Placeholder used as sole label (placeholder ≠ label)
    if not f.has_any_label and f.placeholder and f.placeholder.strip():
        viols.append(
            "3.3.2: Placeholder is the only label — "
            "placeholders disappear on input; use a persistent <label> instead."
        )

    # (d) Autocomplete missing for personal-data input types
    PERSONAL_TYPES = {"email", "tel", "url", "password", "name"}
    PERSONAL_NAMES = {
        "email",
        "phone",
        "tel",
        "password",
        "username",
        "first-name",
        "last-name",
        "firstname",
        "lastname",
        "address",
        "city",
        "zip",
        "postcode",
        "country",
    }
    field_type = (f.type or "").lower()
    field_name = (f.name or "").lower()
    if field_type in PERSONAL_TYPES or any(n in field_name for n in PERSONAL_NAMES):
        if not f.autocomplete:
            viols.append(
                "3.3.2: Personal-data field ("
                + field_type
                + ") is missing the autocomplete attribute (WCAG 1.3.5 / 3.3.2 best practice)."
            )

    return viols


# ─────────────────────────────────────────────────────────────────────────────
# Monkey-patch: static helper used inside _violations_332
# ─────────────────────────────────────────────────────────────────────────────
# (kept as a plain function to avoid modifying FormInputData)
def _field_appears_required(f: FormInputData) -> bool:
    """Heuristic: label or placeholder contains '*'."""
    label = (f.label_text or "").strip()
    ph = (f.placeholder or "").strip()
    return "*" in label or "*" in ph


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class FormAccessibilityAuditor:
    """
    Runs WCAG 3.3.1 / 3.3.2 rules against a list of FormInputData records
    and writes audit_form_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "form_index",
        "form_id",
        "field_tag",
        "field_type",
        "field_id",
        "field_name",
        "label_text",
        "has_any_label",
        "required",
        "aria_invalid",
        # WCAG columns
        "wcag_3_3_1_status",
        "wcag_3_3_1_violations",
        "wcag_3_3_2_status",
        "wcag_3_3_2_violations",
        "overall_status",
        "total_violations",
        # Error message details
        "error_element_id",
        "error_element_role",
        "error_has_role_alert",
        "error_has_aria_live",
        "error_element_text",
        # Raw element
        "html_snippet",
    ]

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_audit_report(
        self,
        form_inputs: List[FormInputData],
    ) -> List[Dict[str, Any]]:
        """
        Audit all inputs, write CSV, return list of record dicts.
        """
        records = []

        for f in form_inputs:
            viols_331 = _violations_331(f)
            viols_332 = _violations_332(f)
            total = len(viols_331) + len(viols_332)

            record = {
                "page_url": f.page_url,
                "form_index": f.form_index,
                "form_id": f.form_id or "",
                "field_tag": f.tag,
                "field_type": f.type or "",
                "field_id": f.id or "",
                "field_name": f.name or "",
                "label_text": f.label_text or "",
                "has_any_label": f.has_any_label,
                "required": f.required,
                "aria_invalid": f.aria_invalid or "",
                # WCAG 3.3.1
                "wcag_3_3_1_status": "FAILED" if viols_331 else "PASSED",
                "wcag_3_3_1_violations": " | ".join(viols_331),
                # WCAG 3.3.2
                "wcag_3_3_2_status": "FAILED" if viols_332 else "PASSED",
                "wcag_3_3_2_violations": " | ".join(viols_332),
                # Overall
                "overall_status": "FAILED" if total > 0 else "PASSED",
                "total_violations": total,
                # Error message metadata
                "error_element_id": f.error_element_id or "",
                "error_element_role": f.error_element_role or "",
                "error_has_role_alert": f.error_has_role_alert,
                "error_has_aria_live": f.error_has_aria_live or "",
                "error_element_text": (f.error_element_text or "")[:200],
                # HTML
                "html_snippet": f.html[:400],
            }
            records.append(record)

        # ── Build summary counts ──────────────────────────────────────────────
        total_fields = len(records)
        total_passed = sum(1 for r in records if r["overall_status"] == "PASSED")
        total_failed = total_fields - total_passed
        pass_rate = round(total_passed / total_fields * 100, 1) if total_fields else 0
        fail_331 = sum(1 for r in records if r["wcag_3_3_1_status"] == "FAILED")
        fail_332 = sum(1 for r in records if r["wcag_3_3_2_status"] == "FAILED")

        # ── Summary row appended after all field rows ─────────────────────────
        summary_row = {field: "" for field in self.CSV_FIELDS}
        summary_row.update(
            {
                "page_url": "── SUMMARY ──",
                "field_tag": f"Total fields : {total_fields}",
                "field_type": f"PASSED : {total_passed}",
                "field_id": f"FAILED : {total_failed}",
                "field_name": f"Pass rate : {pass_rate}%",
                "wcag_3_3_1_status": f"3.3.1 failed : {fail_331}",
                "wcag_3_3_2_status": f"3.3.2 failed : {fail_332}",
                "overall_status": "PASSED" if total_failed == 0 else "FAILED",
                "total_violations": sum(r["total_violations"] for r in records),
            }
        )

        # ── Write CSV ─────────────────────────────────────────────────────────
        csv_path = self.output_dir / "audit_form_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({field: "" for field in self.CSV_FIELDS})  # blank spacer
            writer.writerow(summary_row)

        print(
            f"[FormAuditor] audit_form_report.csv → {csv_path}  "
            f"({total_fields} fields | {total_passed} PASSED / {total_failed} FAILED | "
            f"pass rate {pass_rate}%)"
        )
        return records

    # ── Convenience summary ───────────────────────────────────────────────────
    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(records)
        passed = sum(1 for r in records if r["overall_status"] == "PASSED")
        failed = total - passed
        return {
            "total_fields": total,
            "passed": passed,
            "failed": failed,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
            "wcag_3_3_1_failed": sum(
                1 for r in records if r["wcag_3_3_1_status"] == "FAILED"
            ),
            "wcag_3_3_2_failed": sum(
                1 for r in records if r["wcag_3_3_2_status"] == "FAILED"
            ),
            "fields_missing_label": sum(1 for r in records if not r["has_any_label"]),
            "fields_with_no_error_container": sum(
                1 for r in records if r["required"] and not r["error_element_id"]
            ),
        }
