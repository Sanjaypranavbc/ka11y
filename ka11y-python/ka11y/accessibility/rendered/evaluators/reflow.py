"""
ka11y/accessibility/rendered/evaluators/reflow.py
===================================================
WCAG 1.4.10 — Reflow (Level AA)

Goal: At 320 CSS px viewport width, content must not require two-dimensional
scrolling (horizontal + vertical) to read or operate it.

Exemptions: data tables, SVG charts/maps, code editors → NEEDS_REVIEW.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import PageSnapshot, RuleAuditRecord
from ..heuristics import (
    detect_page_horizontal_scroll,
    elements_with_horizontal_overflow,
    find_fixed_sticky_overlays,
)

_RULE_KEY = "wcag_1_4_10"
_EXEMPT_TAGS = {"table", "svg", "canvas", "iframe", "pre", "code"}
_EXEMPT_ROLES = {"grid", "treegrid", "spreadsheet"}


def _is_likely_exempt(el_tag: str, el_html: str) -> bool:
    """Heuristic: is this element one of the WCAG 1.4.10 exempt categories?"""
    if el_tag in _EXEMPT_TAGS:
        return True
    html_lower = el_html.lower()
    for marker in ("data-chart", 'role="grid"', "role='grid'", "codemirror", "monaco"):
        if marker in html_lower:
            return True
    return False


def evaluate(
    snapshot_320: PageSnapshot,
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.4.10 Reflow using the 320 px viewport snapshot.

    Returns one record per issue found (or a single PASSED record if clean).
    """
    records: List[RuleAuditRecord] = []

    # 1. Page-level horizontal scroll check
    page_scrolls = detect_page_horizontal_scroll(snapshot_320)

    if page_scrolls:
        # Check if the scroll is only due to exempt elements
        overflow_els = elements_with_horizontal_overflow(snapshot_320)
        exempt_only = (
            all(_is_likely_exempt(el.tag, el.html_snippet) for el in overflow_els)
            if overflow_els
            else False
        )

        if exempt_only:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        "Page requires horizontal scrolling at 320 px viewport, "
                        "but the overflowing elements appear to be exempt content "
                        "(table/SVG/canvas/code). Verify manually."
                    ),
                    html_snippet="",
                    page_url=snapshot_320.page_url,
                )
            )
        else:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="FAILED",
                    violation=(
                        f"At 320 px viewport width the page has horizontal scroll "
                        f"(document scrollWidth={snapshot_320.document_scroll_width:.0f} px > "
                        f"viewport={snapshot_320.viewport_width} px). "
                        "Content requires two-dimensional scrolling — violates WCAG 1.4.10."
                    ),
                    html_snippet="",
                    page_url=snapshot_320.page_url,
                )
            )

        # Report the specific overflowing elements (up to 5)
        for el in overflow_els[:5]:
            if _is_likely_exempt(el.tag, el.html_snippet):
                status = "NEEDS_REVIEW"
                msg = (
                    f"<{el.tag}> element extends to {el.rect.right:.0f} px (viewport 320 px). "
                    "May be exempt (table/SVG/chart). Verify manually."
                )
            else:
                status = "FAILED"
                msg = (
                    f"<{el.tag}> element extends to {el.rect.right:.0f} px, "
                    "overflowing the 320 px viewport width."
                )
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status=status,
                    violation=msg,
                    html_snippet=el.html_snippet[:300],
                    element_id=el.element_id,
                    tag=el.tag,
                    page_url=snapshot_320.page_url,
                )
            )
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
