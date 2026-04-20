"""
ka11y/accessibility/rendered/evaluators/reflow.py
===================================================
WCAG 1.4.10 — Reflow (Level AA)

Goal: At 320 CSS px viewport width, content must not require two-dimensional
scrolling (horizontal + vertical) to read or operate it.

Exemptions: data tables, SVG charts/maps, code editors → NEEDS_REVIEW.
"""

from __future__ import annotations

from typing import List

from ..models import PageSnapshot, RuleAuditRecord
from ..heuristics import (
    detect_page_horizontal_scroll,
    elements_with_horizontal_overflow,
)

_RULE_KEY = "wcag_1_4_10"
_EXEMPT_TAGS = {"table", "svg", "canvas", "iframe", "pre", "code"}
_EXEMPT_ROLES = {"grid", "treegrid", "spreadsheet"}


def _is_likely_exempt(tag: str, html: str) -> bool:
    tag = (tag or "").lower()
    html = (html or "").lower()

    if tag in {"table", "svg", "canvas", "pre", "code"}:
        return True

    if any(k in html for k in ["chart", "graph", "map", "datatable"]):
        return True

    return False

def evaluate(
    snapshot_320: PageSnapshot,
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.4.10 Reflow using the 320 px viewport snapshot.

    Returns one record per issue found (plus supporting element records if applicable).
    """
    records: List[RuleAuditRecord] = []

    # 1. Page-level horizontal scroll check
    page_scrolls = detect_page_horizontal_scroll(snapshot_320)

    # Get all overflowing elements
    overflow_els = elements_with_horizontal_overflow(snapshot_320)

    # ── Helper: valid overflow (allowed cases) ────────────────────────────────
    def _is_valid_overflow(el) -> bool:
        return (
            _is_likely_exempt(el.tag, el.html_snippet)
            or getattr(el, "has_overflow_x_scroll", False)
        )

    # Filter only REAL violations
    valid_overflows = [
        el for el in overflow_els if not _is_valid_overflow(el)
    ]

    # ── Case 1: Page has horizontal scroll ────────────────────────────────────
    if page_scrolls:
        if not valid_overflows:
            # Only exempt content caused scroll
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Page requires horizontal scrolling at "
                        f"{snapshot_320.viewport_width} px viewport, "
                        "but the overflowing elements appear to be exempt content "
                        "(table/SVG/canvas/code or scrollable containers). "
                        "Verify manually."
                    ),
                    html_snippet="",
                    page_url=snapshot_320.page_url,
                )
            )
        else:
            # True WCAG failure
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="FAILED",
                    violation=(
                        f"At {snapshot_320.viewport_width} px viewport width the page has horizontal scroll "
                        f"(document scrollWidth={snapshot_320.document_scroll_width:.0f} px > "
                        f"viewport={snapshot_320.viewport_width} px). "
                        "Content requires two-dimensional scrolling — violates WCAG 1.4.10."
                    ),
                    html_snippet="",
                    page_url=snapshot_320.page_url,
                )
            )

        # ── Add supporting element findings (NOT failures) ────────────────────
        for el in valid_overflows[:3]:  # limit noise
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"<{el.tag}> element extends to {el.rect.right:.0f} px, "
                        f"overflowing the {snapshot_320.viewport_width} px viewport width."
                    ),
                    html_snippet=el.html_snippet[:300],
                    element_id=el.element_id,
                    tag=el.tag,
                    page_url=snapshot_320.page_url,
                )
            )

    # ── Case 2: No horizontal scroll ──────────────────────────────────────────
    else:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation="",
                page_url=snapshot_320.page_url,
            )
        )

    return records
