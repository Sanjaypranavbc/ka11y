"""
ka11y/accessibility/rules/input_modalities/target_size_auditor.py
==================================================================
WCAG 2.5.8 — Target Size (Minimum)  (Level AA, WCAG 2.2)

Rule
────
The size of the target for pointer inputs must be at least 24×24 CSS pixels,
EXCEPT where:
  1. Inline  — the target is in a sentence or its size is constrained by
               the line-height of non-target text.
  2. Equivalent — a different control on the same page performs the same
                  function and meets the criterion (not automatable).
  3. Essential — the target size is essential or required by law (not automatable).
  4. User agent — the target size is determined by the user agent and not
                  modified by CSS (e.g. native checkbox/radio).
  5. Offset — the target offset (spacing from other targets) is at least
              (24 − target_width) / 2 or (24 − target_height) / 2 CSS px.

This auditor checks exceptions 1 (inline), 4 (UA-controlled), and 5 (offset)
automatically. Elements failing these exceptions with rendered size < 24×24 are
flagged as FAILED.

CSV output: audit_target_size_report.csv

CSV columns
───────────
  page_url, element_index, tag, role, element_id, input_type, accessible_name,
  rendered_width_px, rendered_height_px,
  padding_top_px, padding_bottom_px, padding_left_px, padding_right_px,
  is_inline_exception, is_ua_controlled_exception, is_offset_exception,
  required_offset_x_px, required_offset_y_px,
  nearest_target_gap_x_px, nearest_target_gap_y_px,
  passes_size,
  wcag_2_5_8_status, wcag_2_5_8_violation,
  overall_status,
  html_snippet
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ka11y.crawler.target_size_crawler import TargetSizeData

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MIN_PX = 24.0  # WCAG 2.5.8 minimum


def _fmt_gap(v: float | None) -> str:
    """Format nearest-gap values for human-readable violation text."""
    return "n/a" if v is None else f"{v:.2f}px"


# ─────────────────────────────────────────────────────────────────────────────
# Check function
# ─────────────────────────────────────────────────────────────────────────────


def _check_258(item: TargetSizeData) -> Tuple[str, str]:
    """
    Returns (status, violation_message) for WCAG 2.5.8.

    status values
    ─────────────
      "N/A"    — exception applies; rule does not require a minimum size
      "PASSED" — rendered width ≥ 24 AND height ≥ 24 CSS px
      "FAILED" — below 24×24 with no applicable exception
    """
    # ── Exceptions: rule does not apply ────────────────────────────────────
    if item.is_inline_exception:
        return (
            "N/A",
            "Inline link exception — target size not required (WCAG 2.5.8 E1).",
        )

    if item.is_ua_controlled_exception:
        return "N/A", (
            "User-agent-controlled exception — native control size not modified "
            "by CSS (WCAG 2.5.8 E4)."
        )

    if item.is_offset_exception:
        return (
            "N/A",
            (
                "Offset exception — undersized target has sufficient spacing "
                f"from nearby targets (required: x≥{item.required_offset_x_px:.2f}px, "
                f"y≥{item.required_offset_y_px:.2f}px; nearest gaps: "
                f"x={_fmt_gap(item.nearest_target_gap_x_px)}, "
                f"y={_fmt_gap(item.nearest_target_gap_y_px)}). "
                "(WCAG 2.5.8 E5)."
            ),
        )

    # ── Size check ──────────────────────────────────────────────────────────
    w = item.rendered_width_px
    h = item.rendered_height_px

    if w >= MIN_PX and h >= MIN_PX:
        return "PASSED", ""

    dims = f"{w:.0f}×{h:.0f} px"
    short_axes = []
    if w < MIN_PX:
        short_axes.append(f"width {w:.0f} px (need ≥ {MIN_PX:.0f})")
    if h < MIN_PX:
        short_axes.append(f"height {h:.0f} px (need ≥ {MIN_PX:.0f})")

    msg = (
        f"2.5.8: Interactive target is {dims} — {' and '.join(short_axes)}. "
        "Increase the element size or add sufficient padding so the total "
        f"clickable area is at least {MIN_PX:.0f}×{MIN_PX:.0f} CSS px."
    )
    return "FAILED", msg


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class TargetSizeAuditor:
    """
    Audits WCAG 2.5.8 (Target Size Minimum) against a list of TargetSizeData
    records and writes audit_target_size_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "element_index",
        "tag",
        "role",
        "element_id",
        "input_type",
        "accessible_name",
        # Rendered dimensions
        "rendered_width_px",
        "rendered_height_px",
        # Padding
        "padding_top_px",
        "padding_bottom_px",
        "padding_left_px",
        "padding_right_px",
        # Exceptions
        "is_inline_exception",
        "is_ua_controlled_exception",
        "is_offset_exception",
        "required_offset_x_px",
        "required_offset_y_px",
        "nearest_target_gap_x_px",
        "nearest_target_gap_y_px",
        # Pre-computed
        "passes_size",
        # WCAG result
        "wcag_2_5_8_status",
        "wcag_2_5_8_violation",
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
        items: List[TargetSizeData],
    ) -> List[Dict[str, Any]]:
        """Audit all items, write CSV, return list of record dicts."""
        records = []

        for item in items:
            status, violation = _check_258(item)
            record = {
                "page_url": item.page_url,
                "element_index": item.element_index,
                "tag": item.tag,
                "role": item.role or "",
                "element_id": item.element_id or "",
                "input_type": item.input_type or "",
                "accessible_name": item.accessible_name or "",
                "rendered_width_px": item.rendered_width_px,
                "rendered_height_px": item.rendered_height_px,
                "padding_top_px": item.padding_top_px,
                "padding_bottom_px": item.padding_bottom_px,
                "padding_left_px": item.padding_left_px,
                "padding_right_px": item.padding_right_px,
                "is_inline_exception": item.is_inline_exception,
                "is_ua_controlled_exception": item.is_ua_controlled_exception,
                "is_offset_exception": item.is_offset_exception,
                "required_offset_x_px": item.required_offset_x_px,
                "required_offset_y_px": item.required_offset_y_px,
                "nearest_target_gap_x_px": item.nearest_target_gap_x_px,
                "nearest_target_gap_y_px": item.nearest_target_gap_y_px,
                "passes_size": item.passes_size,
                "wcag_2_5_8_status": status,
                "wcag_2_5_8_violation": violation,
                "overall_status": (
                    "FAILED"
                    if status == "FAILED"
                    else ("PASSED" if status == "PASSED" else "N/A")
                ),
                "selector": item.selector or "",
                "element_ref_id": item.element_ref_id or "",
                "frame_path": item.frame_path or "",
                "html_snippet": item.html_snippet[:400],
            }
            records.append(record)

        # ── Summary counts ──────────────────────────────────────────────────
        total = len(records)
        passed = sum(1 for r in records if r["wcag_2_5_8_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_5_8_status"] == "FAILED")
        na = sum(1 for r in records if r["wcag_2_5_8_status"] == "N/A")
        checked = passed + failed
        rate = round(passed / checked * 100, 1) if checked else 0

        by_tag: Dict[str, Dict[str, int]] = {}
        for r in records:
            if r["wcag_2_5_8_status"] == "N/A":
                continue
            t = r["tag"]
            if t not in by_tag:
                by_tag[t] = {"passed": 0, "failed": 0}
            by_tag[t]["passed" if r["wcag_2_5_8_status"] == "PASSED" else "failed"] += 1

        # ── Summary row ─────────────────────────────────────────────────────
        summary = {field: "" for field in self.CSV_FIELDS}
        summary.update(
            {
                "page_url": "── SUMMARY ──",
                "tag": f"Total elements          : {total}",
                "role": f"Checked (N/A excluded)  : {checked}",
                "element_id": f"PASSED (≥ 24×24 px)     : {passed}",
                "input_type": f"FAILED (< 24×24 px)     : {failed}",
                "accessible_name": f"N/A (exception)         : {na}",
                "rendered_width_px": f"Pass rate               : {rate}%",
                "wcag_2_5_8_status": "PASSED" if failed == 0 else "FAILED",
                "overall_status": "PASSED" if failed == 0 else "FAILED",
            }
        )

        # ── Write CSV ────────────────────────────────────────────────────────
        csv_path = self.output_dir / "audit_target_size_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({field: "" for field in self.CSV_FIELDS})
            writer.writerow(summary)

        by_tag_str = "  |  ".join(
            f"{tag}: {c['passed']}P/{c['failed']}F" for tag, c in by_tag.items()
        )
        print(
            f"[TargetSizeAuditor] audit_target_size_report.csv → {csv_path}  "
            f"({total} elements | {checked} checked | "
            f"{passed} PASSED / {failed} FAILED | pass rate {rate}%)"
            + (f"\n  by tag: {by_tag_str}" if by_tag_str else "")
        )
        return records

    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        passed = sum(1 for r in records if r["wcag_2_5_8_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_5_8_status"] == "FAILED")
        na = sum(1 for r in records if r["wcag_2_5_8_status"] == "N/A")
        checked = passed + failed

        failed_by_tag: Dict[str, int] = {}
        for r in records:
            if r["wcag_2_5_8_status"] == "FAILED":
                t = r["tag"]
                failed_by_tag[t] = failed_by_tag.get(t, 0) + 1

        return {
            "total_elements": len(records),
            "checked": checked,
            "passed": passed,
            "failed": failed,
            "na": na,
            "pass_rate_pct": round(passed / checked * 100, 1) if checked else 0,
            "wcag_2_5_8_failed": failed,
            "failed_by_tag": failed_by_tag,
        }
