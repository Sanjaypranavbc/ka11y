"""
a11y/accessibility/rules/forms/wcag_331_auditor.py
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
import re
from pathlib import Path
from typing import List, Dict, Any

from a11y.crawler.forms_crawler import FormInputData

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _violations_331(f: FormInputData) -> List[str]:
    """
    WCAG 3.3.1 — Error Identification.

    Fires only when there is signal that an error is actually being communicated:
      • aria-errormessage is set (unambiguously an error association), or
      • aria-invalid="true" is set on the field.

    aria-describedby alone is treated as help/instructional text and is NOT
    flagged for missing live-region semantics — that is the largest historical
    false-positive source.
    """
    viols = []
    aria_invalid_true = (f.aria_invalid or "").strip().lower() == "true"

    # aria-errormessage is unambiguously an error reference: target must exist
    # and be announceable.
    if f.aria_errormessage:
        if not f.errormessage_element_id:
            viols.append(
                "3.3.1: aria-errormessage references an element that does not exist in the DOM."
            )
        elif not f.errormessage_is_live:
            viols.append(
                "3.3.1: aria-errormessage target (#"
                + f.errormessage_element_id
                + ') has no live-region semantics — add role="alert", role="status", '
                'or aria-live="polite"/"assertive" so screen readers announce it.'
            )

    # If the field reports an error state, it must be tied to an announceable message.
    if aria_invalid_true:
        linked_id = f.errormessage_element_id or f.error_element_id
        if not linked_id:
            viols.append(
                '3.3.1: aria-invalid="true" but no aria-errormessage or aria-describedby '
                "points to an error message — the error is not programmatically associated."
            )
        else:
            has_live_error = f.errormessage_is_live or f.error_is_live
            if not has_live_error:
                viols.append(
                    '3.3.1: aria-invalid="true" but the associated error message (#'
                    + linked_id
                    + ") is not a live region — screen readers will not announce it."
                )

    return viols


def _violations_332(f: FormInputData) -> List[str]:
    """
    WCAG 3.3.2 — Labels or Instructions.

    Checks that every field has a visible / programmatic label,
    required state is communicated, and autocomplete is set (and not
    suppressed) for personal-data fields.
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
        viols.append(
            "3.3.2: Field appears required (label/placeholder contains a required indicator "
            "such as '*', '(required)', or '必須') "
            "but is not marked with required or aria-required='true' — "
            "screen readers cannot programmatically determine it is mandatory."
        )

    # (c) Placeholder used as sole label (placeholder ≠ label)
    if not f.has_any_label and f.placeholder and f.placeholder.strip():
        viols.append(
            "3.3.2: Placeholder is the only label — "
            "placeholders disappear on input; use a persistent <label> instead."
        )

    # (d) Autocomplete checks for personal-data fields (only on applicable types).
    field_type = (f.type or "").lower()
    field_name = (f.name or "")
    field_id = (f.id or "")

    if _autocomplete_applies(f.tag, field_type) and (
        field_type in _PERSONAL_INPUT_TYPES
        or _looks_like_personal_data(field_name)
        or _looks_like_personal_data(field_id)
    ):
        ac_value = (f.autocomplete or "").strip().lower()
        if not ac_value:
            viols.append(
                "3.3.2: Personal-data field ("
                + (field_type or "name/id-based heuristic")
                + ") is missing the autocomplete attribute (WCAG 1.3.5 / 3.3.2 best practice)."
            )
        elif ac_value == "off":
            viols.append(
                '3.3.2: Personal-data field has autocomplete="off" — this disables '
                "browser autofill on a field WCAG 1.3.5 expects to expose an input purpose."
            )

    return viols


# ─────────────────────────────────────────────────────────────────────────────
# Required-field heuristic patterns
# ─────────────────────────────────────────────────────────────────────────────

# Tightened to avoid matching bare "required" inside unrelated phrases like
# "Required reading list" — only fires when the required-indicator appears in
# a marker-like position (e.g. at a boundary, followed by punctuation, or
# wrapped in parentheses).
_REQUIRED_PATTERN = re.compile(
    r"""
    (?:^|\s)\*+(?:\s|$)                       # ✱ surrounded by whitespace / edges
    | \(\s*required\s*\)                       # "(required)"
    | \(\s*req\.?\s*\)                         # "(req)" / "(req.)"
    | (?:^|\s)required\s*(?::|\.|,|$)          # "Required:" / "...required."
    | (?:^|\s)mandatory\s*(?::|\.|,|$)
    | 必須(?:項目)?                             # Japanese
    | (?:^|\s)obligatoire(?:\s|:|\.|,|$)       # French
    | (?:^|\s)obrigatório(?:\s|:|\.|,|$)       # Portuguese
    | pflichtfeld                              # German (compound, no boundary issues)
    | (?:^|\s)erforderlich(?:\s|:|\.|,|$)      # German
    | (?:^|\s)requerido(?:\s|:|\.|,|$)         # Spanish
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _field_appears_required(f: FormInputData) -> bool:
    """
    Heuristic: label or placeholder text contains a required-field indicator.

    Covers asterisk (✱), "(required)", "required" keyword, Japanese 必須/必要,
    and several other language variants used in practice.
    """
    label = (f.label_text or "").strip()
    ph = (f.placeholder or "").strip()
    return bool(_REQUIRED_PATTERN.search(label) or _REQUIRED_PATTERN.search(ph))


# ─────────────────────────────────────────────────────────────────────────────
# Autocomplete / personal-data heuristics
# ─────────────────────────────────────────────────────────────────────────────

# Input types where autocomplete is meaningful (HTML spec).
_AUTOCOMPLETE_INPUT_TYPES = {
    "", "text", "search", "url", "tel", "email", "password",
    "number", "month", "date", "week", "time", "datetime-local",
}

# Input types whose data is inherently personal — even if `name` is opaque.
_PERSONAL_INPUT_TYPES = {"email", "tel", "password"}

# Personal-data tokens for matching field name / id. Matched either as the
# full normalized name (after stripping trailing digits and lowercasing) or
# as the trailing segment of a hyphen/underscore/camelCase-split name.
_PERSONAL_FULL_NAMES = {
    "email", "e-mail", "emailaddress", "email-address",
    "phone", "telephone", "tel", "phonenumber", "phone-number", "mobile",
    "password", "passwd", "pwd",
    "new-password", "newpassword", "current-password", "currentpassword",
    "username", "user-name", "userid", "user-id", "user", "login",
    "fname", "lname", "firstname", "lastname",
    "first-name", "last-name", "middle-name",
    "given-name", "family-name", "additional-name",
    "fullname", "full-name", "name",
    "address", "street-address", "streetaddress",
    "address-line1", "address-line2", "address-line3",
    "address1", "address2", "address3",
    "city", "town", "state", "province", "region", "country", "country-name",
    "zip", "zipcode", "zip-code", "postcode", "postal-code", "postalcode",
    "organization", "company", "company-name",
    "birthday", "bday", "dob", "birth-date", "birthdate", "date-of-birth",
    "cc-number", "cc-name", "cc-exp", "cc-csc", "cc-cvc", "cc-cvv",
    "creditcard", "credit-card", "card-number", "cardnumber",
    "cvc", "cvv", "csc",
    "ssn", "social-security",
}

# Trailing-segment tokens. We only flag if the last segment of a normalized
# name is one of these — so `email_marketing_opt_in` (last="in") doesn't
# match but `user_email` (last="email") does.
_PERSONAL_TRAILING_TOKENS = {
    "email", "mail", "phone", "telephone", "mobile", "password", "passwd",
    "username", "userid",
    "firstname", "lastname", "fname", "lname", "name",
    "address", "street", "city", "state", "country",
    "zip", "zipcode", "postcode", "postalcode",
    "organization", "company",
    "birthday", "bday", "dob", "birthdate",
    "cvc", "cvv", "csc", "ssn",
}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TRAILING_DIGITS = re.compile(r"\d+$")


def _autocomplete_applies(tag: str, input_type: str) -> bool:
    """Autocomplete is only meaningful on a subset of form controls."""
    tag_up = (tag or "").upper()
    if tag_up in ("SELECT", "TEXTAREA"):
        return True
    if tag_up == "INPUT":
        return (input_type or "").lower() in _AUTOCOMPLETE_INPUT_TYPES
    return False


def _looks_like_personal_data(raw: str) -> bool:
    """
    Tokenized check: does this field name/id read like a personal-data field?

    Avoids the old false-positive on names like `email_marketing_opt_in` by
    requiring the personal token to be the *final* segment of the normalized
    name (or for the full normalized name itself to be a known token).
    """
    if not raw:
        return False

    # Normalize: insert hyphens at camelCase boundaries, lowercase, then drop
    # trailing digits (so `email2` / `address1` map to `email` / `address`).
    s = _CAMEL_BOUNDARY.sub("-", raw).lower().strip()
    s_no_digits = _TRAILING_DIGITS.sub("", s)

    if s in _PERSONAL_FULL_NAMES or s_no_digits in _PERSONAL_FULL_NAMES:
        return True

    parts = re.split(r"[-_]+", s_no_digits)
    if parts and parts[-1] in _PERSONAL_TRAILING_TOKENS:
        return True

    return False


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
        "selector",
        "element_ref_id",
        "frame_path",
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
                "selector": f.selector or "",
                "element_ref_id": f.element_ref_id or "",
                "frame_path": f.frame_path or "",
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
