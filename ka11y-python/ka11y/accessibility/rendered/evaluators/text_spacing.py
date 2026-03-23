"""
ka11y/accessibility/rendered/evaluators/text_spacing.py
=========================================================
WCAG 1.4.12 — Text Spacing (Level AA)

Goal: No loss of content or functionality when the following CSS overrides
are applied:
  • line-height: 1.5
  • letter-spacing: 0.12em
  • word-spacing: 0.16em
  • paragraph / list-item spacing: 2em bottom-margin

We compare a baseline snapshot (no overrides) with a modified snapshot
(overrides injected) and look for newly-clipped elements.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import ElementSnapshot, PageSnapshot, RuleAuditRecord
from ..heuristics import find_clipped_text_elements

_RULE_KEY = "wcag_1_4_12"

_TEXT_TAGS = {
    "p", "span", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "dt", "dd", "blockquote", "label", "td", "th",
    "a", "button",
}


def _selector_key(el: ElementSnapshot) -> str:
    """Stable cross-scenario identity key for an element."""
    return f"{el.tag}#{el.element_id}" if el.element_id else f"{el.tag}:{el.text[:40]}"


def evaluate(
    baseline: PageSnapshot,
    modified: PageSnapshot,
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.4.12 Text Spacing by diffing baseline vs spacing-override snapshot.
    """
    records: List[RuleAuditRecord] = []

    # Build index of baseline elements (not clipped)
    baseline_keys = {
        _selector_key(el)
        for el in baseline.elements
        if not el.text_clipped and el.tag in _TEXT_TAGS
    }

    # Find elements that became clipped after spacing override
    newly_clipped: List[ElementSnapshot] = []
    for el in modified.elements:
        if el.tag not in _TEXT_TAGS:
            continue
        if not el.text or len(el.text.strip()) < 3:
            continue
        if el.text_clipped and _selector_key(el) in baseline_keys:
            newly_clipped.append(el)

    if not newly_clipped:
        # Also check if page-level scroll changed dramatically
        if modified.has_horizontal_scroll and not baseline.has_horizontal_scroll:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        "Page gained horizontal scroll after text spacing overrides. "
                        "Content or functionality may be lost. Verify manually."
                    ),
                    page_url=baseline.page_url,
                )
            )
        else:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="PASSED",
                    violation="",
                    page_url=baseline.page_url,
                )
            )
        return records

    for el in newly_clipped[:10]:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="FAILED",
                violation=(
                    f"<{el.tag}> text is clipped after WCAG 1.4.12 spacing overrides "
                    f"(scrollW={el.scroll_width:.0f} > clientW={el.client_width:.0f}, "
                    f"overflow-{el.overflow_x}/{el.overflow_y}). "
                    f'Text: "{el.text[:80]}"'
                ),
                html_snippet=el.html_snippet[:300],
                element_id=el.element_id,
                tag=el.tag,
                page_url=baseline.page_url,
            )
        )

    return records