"""
ka11y/accessibility/rules/input_modalities/text_spacing_auditor.py
==================================================================

WCAG 1.4.12 — Text Spacing (Level AA)

Rule:
Text must not be clipped when spacing is increased.
"""

import csv
from pathlib import Path
from typing import List, Dict, Any

from ka11y.crawler.text_spacing_crawler import TextSpacingData


def _is_text_relevant(item: TextSpacingData):
    if item.text_length < 20:
        return False

    if item.tag in ["html", "body", "img", "svg", "canvas"]:
        return False

    return True


# ─────────────────────────────────────────────────────────────────────────────


def _check_1412(item: TextSpacingData):

    if not _is_text_relevant(item):
        # Return N/A so the downstream converter does not count this as a genuine
        # pass, which would artificially inflate pass rates.
        return "N/A", "Element is not relevant for 1.4.12 text-spacing check."

    if item.has_fixed_height and item.has_overflow_hidden:
        return "WARNING", (
            "1.4.12: Potential clipping risk — fixed height with overflow hidden. "
            "Needs visual verification with increased spacing."
        )

    if item.has_fixed_height:
        return "INFO", (
            "1.4.12: Fixed height detected. Verify text does not clip when spacing increases."
        )

    return "PASSED", ""


# ─────────────────────────────────────────────────────────────────────────────


class TextSpacingAuditor:

    CSV_FIELDS = [
        "page_url",
        "element_index",
        "tag",
        "element_id",
        "class_name",
        "text_length",
        "height",
        "min_height",
        "overflow",
        "has_fixed_height",
        "has_overflow_hidden",
        "wcag_1_4_12_status",
        "wcag_1_4_12_violation",
        "overall_status",
        "html_snippet",
    ]

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_audit_report(
        self, items: List[TextSpacingData]
    ) -> List[Dict[str, Any]]:

        records = []

        for item in items:
            status, violation = _check_1412(item)

            record = {
                "page_url": item.page_url,
                "element_index": item.element_index,
                "tag": item.tag,
                "element_id": item.element_id or "",
                "class_name": item.class_name or "",
                "text_length": item.text_length,
                "height": item.height,
                "min_height": item.min_height,
                "overflow": item.overflow,
                "has_fixed_height": item.has_fixed_height,
                "has_overflow_hidden": item.has_overflow_hidden,
                "wcag_1_4_12_status": status,
                "wcag_1_4_12_violation": violation,
                "overall_status": (
                    "FAILED"
                    if status == "FAILED"
                    else (
                        "WARNING"
                        if status == "WARNING"
                        else ("N/A" if status == "N/A" else "PASSED")
                    )
                ),
                "html_snippet": item.html_snippet[:400],
            }

            records.append(record)

        # Save CSV
        csv_path = self.output_dir / "audit_text_spacing_report.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)

        print(f"[TextSpacingAuditor] CSV → {csv_path}")

        return records
