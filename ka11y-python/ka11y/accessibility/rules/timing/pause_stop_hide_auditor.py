"""
ka11y/accessibility/rules/timing/pause_stop_hide_auditor.py
=============================================================
WCAG 2.2.2 — Pause, Stop, Hide  (Level A)

Rule
────
For any moving, blinking, scrolling, or auto-updating content that:
  (1) starts automatically,
  (2) lasts more than 5 seconds, and
  (3) is presented in parallel with other content,
there must be a mechanism for the user to pause, stop, or hide it.

Why this goes beyond axe-core
──────────────────────────────
axe-core only flags deprecated <blink> and <marquee> HTML elements.
This auditor additionally detects:

  • <video autoplay>          — background / hero videos
  • Animated GIFs             — looping .gif images (no native pause)
  • CSS / WAAPI animations    — long-running keyframe animations (> 5 s or infinite)
  • JavaScript carousels      — Bootstrap, Swiper, Slick, Owl Carousel, Glide, Splide, generic
Pass conditions (WCAG 2.2.2 applicability gates — ALL must be met to require a mechanism)
──────────────────────────────────────────────────────────────────────────────────────────
  1. starts_automatically == True
  2. duration_seconds > 5  OR  duration_seconds == -1 (infinite)  OR  loops == True
  3. has_mechanism == False  →  FAILED

CSV output: audit_pause_stop_hide_report.csv

CSV columns
───────────
  page_url, element_index, content_type, content_type_label, tag, element_id, src,
  animation_name, animation_duration_seconds, animation_iteration_count,
  loops, duration_seconds, starts_automatically,
  has_video_controls, has_pause_button, has_mechanism,
  wcag_2_2_2_status, wcag_2_2_2_violation,
  overall_status, axe_would_catch,
  html_snippet
"""

import csv
from pathlib import Path
from typing import List, Dict, Any, Tuple

from ka11y.crawler.moving_content_crawler import MovingContentData

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_TYPE_LABELS: Dict[str, str] = {
    "video_autoplay": "Video with autoplay",
    "animated_gif": "Animated GIF (loops indefinitely)",
    "css_animation": "CSS / WAAPI animation",
    "carousel_autoplay": "Carousel / slider with autoplay",
    "marquee_element": "<marquee> element (deprecated)",
    "blink_element": "<blink> element (deprecated)",
}

_HINTS: Dict[str, str] = {
    "video_autoplay": (
        "Add the controls attribute to the <video> element, or provide "
        "a visible Pause/Stop button that controls playback."
    ),
    "animated_gif": (
        "Replace the GIF with a <video controls> or a static image. "
        "Alternatively, provide a JavaScript-based pause/stop mechanism."
    ),
    "css_animation": (
        "Provide a Pause/Stop button, or honour prefers-reduced-motion "
        "by pausing/removing the animation for users who request it."
    ),
    "carousel_autoplay": (
        "Add a visible Pause button (not just Prev/Next) that stops "
        "the auto-advance behaviour."
    ),
    "marquee_element": (
        "Remove the deprecated <marquee> element entirely. "
        "If scrolling text is needed, use CSS with a user-controllable animation."
    ),
    "blink_element": (
        "Remove the deprecated <blink> element entirely. "
        "Blinking content is also covered by WCAG 2.3.1 (Three Flashes)."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Check function
# ─────────────────────────────────────────────────────────────────────────────


def _check_222(item: MovingContentData) -> Tuple[str, str]:
    """
    Returns (status, violation_message) for WCAG 2.2.2.
    status: "PASSED" | "FAILED" | "NEEDS_REVIEW"

    WCAG 2.2.2 only applies when ALL three applicability gates are met:
      1. Content starts automatically
      2. Content lasts more than 5 seconds (or loops indefinitely)
      3. No pause/stop/hide mechanism exists  →  FAILED
    """
    if item.applicability_exception == "loading_indicator":
        return (
            "N/A",
            "Loading or status indicator treated as an essential exception for WCAG 2.2.2.",
        )

    # Gate 1: content must start automatically
    if not item.starts_automatically:
        return "PASSED", ""

    # Gate 2: content must last more than 5 seconds.
    # duration_seconds == -1 means infinite. Unknown finite duration is ambiguous.
    is_infinite = (
        item.duration_seconds == -1 or item.animation_iteration_count == "infinite"
    )
    if (
        not is_infinite
        and not item.loops
        and item.duration_seconds is None
        and not item.duration_known
    ):
        if item.has_mechanism:
            return "PASSED", ""
        label = _TYPE_LABELS.get(item.content_type, item.content_type)
        return (
            "NEEDS_REVIEW",
            f"2.2.2: {label} starts automatically but its duration could not be "
            "determined. Verify whether it runs longer than 5 seconds and provide "
            "a pause, stop, or hide mechanism if it does.",
        )

    if (
        not is_infinite
        and not item.loops
        and item.duration_seconds is not None
        and item.duration_seconds <= 5.0
    ):
        return "PASSED", ""

    # Gate 3: a mechanism must be absent to be a violation
    if item.has_mechanism:
        return "PASSED", ""

    label = _TYPE_LABELS.get(item.content_type, item.content_type)
    hint = _HINTS.get(item.content_type, "Provide a mechanism to pause, stop, or hide.")

    if is_infinite or item.loops:
        duration_str = "loops indefinitely"
    elif item.duration_seconds is not None:
        duration_str = f"{item.duration_seconds:.1f} s"
    else:
        duration_str = "unknown duration"

    msg = (
        f"2.2.2: {label} ({duration_str}) starts automatically "
        f"and provides no mechanism to pause, stop, or hide it. {hint}"
    )
    return "FAILED", msg


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class PauseStopHideAuditor:
    """
    Audits WCAG 2.2.2 (Pause, Stop, Hide) against a list of MovingContentData
    records and writes audit_pause_stop_hide_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "element_index",
        "content_type",
        "content_type_label",
        "tag",
        "element_id",
        "src",
        # Animation details
        "animation_name",
        "animation_duration_seconds",
        "animation_iteration_count",
        "loops",
        "duration_seconds",
        "starts_automatically",
        "applicability_exception",
        # Mechanism
        "has_video_controls",
        "has_pause_button",
        "has_mechanism",
        "selector",
        "element_ref_id",
        "frame_path",
        # WCAG result
        "wcag_2_2_2_status",
        "wcag_2_2_2_violation",
        "overall_status",
        # Axe-core comparison
        "axe_would_catch",
        # Raw element
        "html_snippet",
    ]

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_audit_report(
        self,
        items: List[MovingContentData],
    ) -> List[Dict[str, Any]]:
        """Audit all items, write CSV, return list of record dicts."""
        records = []

        for item in items:
            status, violation = _check_222(item)
            record = {
                "page_url": item.page_url,
                "element_index": item.element_index,
                "content_type": item.content_type,
                "content_type_label": _TYPE_LABELS.get(
                    item.content_type, item.content_type
                ),
                "tag": item.tag,
                "element_id": item.element_id or "",
                "src": item.src or "",
                "animation_name": item.animation_name or "",
                "animation_duration_seconds": (
                    item.animation_duration_seconds
                    if item.animation_duration_seconds is not None
                    else ""
                ),
                "animation_iteration_count": item.animation_iteration_count or "",
                "loops": item.loops,
                "duration_seconds": (
                    item.duration_seconds if item.duration_seconds is not None else ""
                ),
                "starts_automatically": item.starts_automatically,
                "applicability_exception": item.applicability_exception or "",
                "has_video_controls": item.has_video_controls,
                "has_pause_button": item.has_pause_button,
                "has_mechanism": item.has_mechanism,
                "selector": item.selector or "",
                "element_ref_id": item.element_ref_id or "",
                "frame_path": item.frame_path or "",
                "wcag_2_2_2_status": status,
                "wcag_2_2_2_violation": violation,
                "overall_status": status,
                "axe_would_catch": item.axe_would_catch,
                "html_snippet": item.html_snippet,
            }
            records.append(record)

        # ── Summary counts ─────────────────────────────────────────────────
        total = len(records)
        passed = sum(1 for r in records if r["wcag_2_2_2_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_2_2_status"] == "FAILED")
        needs_review = sum(
            1 for r in records if r["wcag_2_2_2_status"] == "NEEDS_REVIEW"
        )
        na = sum(1 for r in records if r["wcag_2_2_2_status"] == "N/A")
        checked = passed + failed + needs_review
        rate = round(passed / checked * 100, 1) if checked else 0

        by_type: Dict[str, Dict[str, int]] = {}
        for r in records:
            ct = r["content_type"]
            if ct not in by_type:
                by_type[ct] = {"passed": 0, "failed": 0, "needs_review": 0, "na": 0}
            bucket = (
                "passed"
                if r["wcag_2_2_2_status"] == "PASSED"
                else (
                    "failed"
                    if r["wcag_2_2_2_status"] == "FAILED"
                    else ("needs_review" if r["wcag_2_2_2_status"] == "NEEDS_REVIEW" else "na")
                )
            )
            by_type[ct][bucket] += 1

        axe_would_miss = sum(1 for r in records if not r["axe_would_catch"])

        # ── Summary row ────────────────────────────────────────────────────
        summary = {field: "" for field in self.CSV_FIELDS}
        summary.update(
            {
                "page_url": "── SUMMARY ──",
                "content_type": f"Total items      : {total}",
                "tag": f"PASSED           : {passed}",
                "element_id": f"FAILED           : {failed}",
                "src": f"NEEDS_REVIEW     : {needs_review}",
                "animation_name": f"N/A              : {na}",
                "animation_duration_seconds": f"Pass rate        : {rate}%",
                "animation_iteration_count": f"Axe-core misses  : {axe_would_miss}",
                "wcag_2_2_2_status": "PASSED" if failed == 0 and needs_review == 0 else ("FAILED" if failed else "NEEDS_REVIEW"),
                "overall_status": "PASSED" if failed == 0 and needs_review == 0 else ("FAILED" if failed else "NEEDS_REVIEW"),
            }
        )

        # ── Write CSV ──────────────────────────────────────────────────────
        csv_path = self.output_dir / "audit_pause_stop_hide_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({field: "" for field in self.CSV_FIELDS})
            writer.writerow(summary)

        by_type_summary = "  |  ".join(
            f"{ct}: {counts['passed']}P/{counts['failed']}F/{counts['needs_review']}R/{counts['na']}N"
            for ct, counts in by_type.items()
        )
        print(
            f"[PauseStopHideAuditor] audit_pause_stop_hide_report.csv → {csv_path}  "
            f"({total} items | {passed} PASSED / {failed} FAILED / {needs_review} NEEDS_REVIEW / {na} N/A | pass rate {rate}%) "
            f"| axe-core would miss {axe_would_miss}"
            + (f"\n  by type: {by_type_summary}" if by_type_summary else "")
        )
        return records

    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(records)
        passed = sum(1 for r in records if r["wcag_2_2_2_status"] == "PASSED")
        failed = sum(1 for r in records if r["wcag_2_2_2_status"] == "FAILED")
        needs_review = sum(1 for r in records if r["wcag_2_2_2_status"] == "NEEDS_REVIEW")
        na = sum(1 for r in records if r["wcag_2_2_2_status"] == "N/A")

        failed_by_type: Dict[str, int] = {}
        passed_by_type: Dict[str, int] = {}
        review_by_type: Dict[str, int] = {}
        na_by_type: Dict[str, int] = {}
        for r in records:
            ct = r["content_type"]
            if r["wcag_2_2_2_status"] == "FAILED":
                failed_by_type[ct] = failed_by_type.get(ct, 0) + 1
            elif r["wcag_2_2_2_status"] == "PASSED":
                passed_by_type[ct] = passed_by_type.get(ct, 0) + 1
            elif r["wcag_2_2_2_status"] == "NEEDS_REVIEW":
                review_by_type[ct] = review_by_type.get(ct, 0) + 1
            else:
                na_by_type[ct] = na_by_type.get(ct, 0) + 1

        return {
            "total_items": total,
            "passed": passed,
            "failed": failed,
            "needs_review": needs_review,
            "na": na,
            "pass_rate_pct": round(passed / (passed + failed + needs_review) * 100, 1) if (passed + failed + needs_review) else 0,
            "wcag_2_2_2_failed": failed,
            "axe_would_miss": sum(1 for r in records if not r["axe_would_catch"]),
            "failed_by_type": failed_by_type,
            "passed_by_type": passed_by_type,
            "needs_review_by_type": review_by_type,
            "na_by_type": na_by_type,
        }
