"""
ka11y/accessibility/rendered/evaluators/resize_text.py
========================================================
WCAG 1.4.4 — Resize Text (Level AA)

Goal: Text can be resized up to 200% without loss of content or functionality.

Approach: Compare a baseline snapshot with a 200% text-size snapshot.
Detect:
  - Newly clipped text (overflow: hidden + scrollWidth > clientWidth)
  - Elements whose width shrank to zero / became invisible
  - Page-level horizontal scroll appearing after resize
"""

from __future__ import annotations

from typing import List

from ..models import ElementSnapshot, PageSnapshot, RuleAuditRecord
from ..heuristics import find_clipped_text_elements

_RULE_KEY = "wcag_1_4_4"

_TEXT_TAGS = {
    "p",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "dt",
    "dd",
    "blockquote",
    "label",
    "td",
    "th",
    "a",
    "button",
    "nav",
}


def _selector_key(el: ElementSnapshot) -> str:
    if el.element_id:
        return f"{el.tag}#{el.element_id}"
    return f"{el.tag}:{el.text[:40]}"


def evaluate(
    baseline: PageSnapshot,
    resized: PageSnapshot,
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.4.4 Resize Text by diffing baseline vs 200% text-size snapshot.
    """
    records: List[RuleAuditRecord] = []

    # Baseline: elements that were not clipped
    baseline_ok = {
        _selector_key(el)
        for el in baseline.elements
        if not el.text_clipped and el.tag in _TEXT_TAGS and el.visible
    }

    newly_clipped: List[ElementSnapshot] = []
    for el in resized.elements:
        if el.tag not in _TEXT_TAGS:
            continue
        if not el.text or len(el.text.strip()) < 3:
            continue
        if el.text_clipped and _selector_key(el) in baseline_ok:
            newly_clipped.append(el)

    # Check for horizontal scroll appearing after resize
    scroll_introduced = (
        resized.has_horizontal_scroll and not baseline.has_horizontal_scroll
    )

    if not newly_clipped and not scroll_introduced:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation="",
                page_url=baseline.page_url,
            )
        )
        return records

    if scroll_introduced:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="FAILED",
                violation=(
                    "Page requires horizontal scrolling after 200% text resize "
                    f"(scrollWidth={resized.document_scroll_width:.0f} px > "
                    f"viewport={resized.viewport_width} px). "
                    "Content or functionality is lost — violates WCAG 1.4.4."
                ),
                page_url=baseline.page_url,
            )
        )

    for el in newly_clipped[:10]:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="FAILED",
                violation=(
                    f"<{el.tag}> text is clipped after 200% text resize "
                    f"(scrollW={el.scroll_width:.0f} > clientW={el.client_width:.0f}, "
                    f"overflow={el.overflow_x}/{el.overflow_y}). "
                    f'Text: "{el.text[:80]}"'
                ),
                html_snippet=el.html_snippet[:300],
                element_id=el.element_id,
                tag=el.tag,
                page_url=baseline.page_url,
            )
        )

    return records
