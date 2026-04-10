"""
ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py
====================================================================
WCAG 2.5.3 — Label in Name  (Level A, WCAG 2.1+)/


Rule
────
The accessible name of a UI component must *contain* the visible label text
(case-insensitive substring match after whitespace normalisation).
──────
Allows speech-input users (e.g. Dragon NaturallySpeaking) to activate
controls by speaking the visible text. When aria-label or aria-labelledby
override the accessible name without including the visible text, voice-
control commands fail.

What is checked
───────────────
  • <button>, <a href>, <input type="submit|button|reset|image">
  • Elements with interactive ARIA roles (role="button|link|menuitem|…")

Failure condition
─────────────────
  visible_label is non-empty (contains ≥1 word character)
  AND accessible_name does NOT contain visible_label (case-insensitive)

CSV output: audit_label_in_name_report.csv

CSV columns
───────────
  page_url, element_index, tag, role, element_id, input_type,
  visible_label,
  aria_label, aria_labelledby, aria_labelledby_text, title_attr,
  value_attr, alt_attr, accessible_name,
  wcag_2_5_3_status, wcag_2_5_3_violation,
  overall_status,
  html_snippet
"""

import csv
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional

from ka11y.crawler.interactive_crawler import InteractiveElementData

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _normalize(text: Optional[str]) -> str:
    """NFC-normalise, casefold, and collapse whitespace for comparison.

    Using NFC + casefold catches Unicode equivalences (e.g. "Café" vs "Cafe\u0301")
    that a plain .lower() would miss.
    """
    if not text:
        return ""
    nfc = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", nfc.strip()).casefold()


def _has_word_chars(text: str) -> bool:
    """True if text contains at least one Unicode letter or digit (not just symbols)."""
    return bool(re.search(r"[^\W_]", text, re.UNICODE))


def _strip_punctuation(text: str) -> str:
    """Remove leading/trailing punctuation so word-boundary checks work correctly.

    Without this, a visible label like "Go!" would have its word boundary fall
    between "o" and "!" (both non-word characters), making ``\\bGo\\b`` fail to
    match even though the text clearly contains the word "Go".
    """
    return re.sub(r"[^\w\s]", "", text).strip()


def _contains_cjk(text: str) -> bool:
    """True when text includes Hiragana, Katakana, or Han characters."""
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _label_in_name(visible: str, acc_name: str) -> bool:
    """Return True if *visible* appears as a whole word within *acc_name*.

    Uses a word-boundary regex so that visible="Go" does not match "Gorilla".
    Both inputs should already be normalised via _normalize().

    Punctuation is stripped from *visible* before applying the word-boundary
    check so that labels like "Go!" still match an accessible name of "Go to
    the next page".
    """
    if not visible:
        return True
    stripped = _strip_punctuation(visible)
    # Fall back to plain substring match if stripping removes everything.
    if not stripped:
        return visible in acc_name
    # CJK labels are not reliably tokenized by \b boundaries.
    if _contains_cjk(stripped):
        return stripped in acc_name
    pattern = r"\b" + re.escape(stripped) + r"\b"
    return bool(re.search(pattern, acc_name))


def _check_253(el: InteractiveElementData):
    """
    Returns (status, violation_message) for WCAG 2.5.3.

    status values
    ─────────────
      "N/A"    — no visible text label; rule does not apply
      "PASSED" — accessible name contains visible label
      "FAILED" — accessible name is missing or does not contain visible label
    """
    visible = _normalize(el.visible_label)
    name = _normalize(el.accessible_name)

    # N/A: no visible text (icon-only button, image with no alt, etc.)
    if not visible or not _has_word_chars(visible):
        return "N/A", "No visible text label — rule does not apply."

    # FAILED: no accessible name at all
    if not name:
        return "FAILED", (
            "2.5.3: No accessible name found. "
            f'Visible label is "{el.visible_label}" but the element has no '
            "aria-label, aria-labelledby, title, or computed text name."
        )

    # FAILED: accessible name does not contain visible label (word-boundary check)
    if not _label_in_name(visible, name):
        return "FAILED", (
            f'2.5.3: Accessible name "{el.accessible_name}" does not contain '
            f'visible label "{el.visible_label}". '
            "Speech-input users cannot activate this control by speaking the visible label."
        )

    return "PASSED", ""


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class LabelInNameAuditor:
    """
    Audits WCAG 2.5.3 (Label in Name) against a list of InteractiveElementData
    records and writes audit_label_in_name_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "element_index",
        "tag",
        "role",
        "element_id",
        "input_type",
        # Visible text
        "visible_label",
        # Accessible-name breakdown
        "aria_label",
        "aria_labelledby",
        "aria_labelledby_text",
        "title_attr",
        "value_attr",
        "alt_attr",
        "accessible_name",
        # WCAG result
        "wcag_2_5_3_status",
        "wcag_2_5_3_violation",
        "overall_status",
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
        elements: List[InteractiveElementData],
    ) -> List[Dict[str, Any]]:
        """Audit all elements, write CSV, return list of record dicts."""
        records = []

        for el in elements:
            status, violation = _check_253(el)
            record = {
                "page_url": el.page_url,
                "element_index": el.element_index,
                "tag": el.tag,
                "role": el.role or "",
                "element_id": el.element_id or "",
                "input_type": el.input_type or "",
                "visible_label": el.visible_label or "",
                "aria_label": el.aria_label or "",
                "aria_labelledby": el.aria_labelledby or "",
                "aria_labelledby_text": el.aria_labelledby_text or "",
                "title_attr": el.title_attr or "",
                "value_attr": el.value_attr or "",
                "alt_attr": el.alt_attr or "",
                "accessible_name": el.accessible_name or "",
                "wcag_2_5_3_status": status,
                "wcag_2_5_3_violation": violation,
                "overall_status": (
                    "FAILED"
                    if status == "FAILED"
                    else ("PASSED" if status == "PASSED" else "N/A")
                ),
                "selector": el.selector or "",
                "element_ref_id": el.element_ref_id or "",
                "frame_path": el.frame_path or "",
                "html_snippet": el.html_snippet[:400],
            }
            records.append(record)

        # ── Summary counts ─────────────────────────────────────────────────
        total = len(records)
        passed = sum(1 for r in records if r["wcag_2_5_3_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_5_3_status"] == "FAILED")
        na = sum(1 for r in records if r["wcag_2_5_3_status"] == "N/A")
        checked = passed + failed
        rate = round(passed / checked * 100, 1) if checked else 0

        # ── Summary row ────────────────────────────────────────────────────
        summary = {field: "" for field in self.CSV_FIELDS}
        summary.update(
            {
                "page_url": "── SUMMARY ──",
                "tag": f"Total elements          : {total}",
                "role": f"Checked (N/A excluded)  : {checked}",
                "element_id": f"PASSED                  : {passed}",
                "input_type": f"FAILED                  : {failed}",
                "visible_label": f"N/A (no visible text)   : {na}",
                "accessible_name": f"Pass rate               : {rate}%",
                "wcag_2_5_3_status": "PASSED" if failed == 0 else "FAILED",
                "overall_status": "PASSED" if failed == 0 else "FAILED",
            }
        )

        # ── Write CSV ──────────────────────────────────────────────────────
        csv_path = self.output_dir / "audit_label_in_name_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({field: "" for field in self.CSV_FIELDS})
            writer.writerow(summary)

        print(
            f"[LabelInNameAuditor] audit_label_in_name_report.csv → {csv_path}  "
            f"({total} elements | {checked} checked | "
            f"{passed} PASSED / {failed} FAILED | pass rate {rate}%)"
        )
        return records

    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        passed = sum(1 for r in records if r["wcag_2_5_3_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_5_3_status"] == "FAILED")
        na = sum(1 for r in records if r["wcag_2_5_3_status"] == "N/A")
        checked = passed + failed
        return {
            "total_elements": len(records),
            "checked": checked,
            "passed": passed,
            "failed": failed,
            "na": na,
            "pass_rate_pct": round(passed / checked * 100, 1) if checked else 0,
            "wcag_2_5_3_failed": failed,
        }
