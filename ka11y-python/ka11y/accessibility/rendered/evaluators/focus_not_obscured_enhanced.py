"""
ka11y/accessibility/rendered/evaluators/focus_not_obscured_enhanced.py
========================================================================
WCAG 2.4.12 — Focus Not Obscured (Enhanced) (Level AA)

Goal: When a UI component receives keyboard focus, it is not obscured *at all*
by author-created content.

This is stricter than 2.4.11: even partial obscuration counts.

Logic (using the same focus_steps as 2.4.11):
  - FAILED when overlap >= 10% (any non-trivial obscuration)
  - NEEDS_REVIEW when overlap 2–10% (tiny possible overlap — uncertain)
  - PASSED when overlap < 2%
"""

from __future__ import annotations

from typing import List

from ..models import FocusStep, RuleAuditRecord

_RULE_KEY = "wcag_2_4_12"

_FAIL_THRESHOLD = 0.10      # >= 10% → fail
_REVIEW_THRESHOLD = 0.02    # 2–10% → needs_review


def evaluate(focus_steps: List[FocusStep]) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 2.4.12 Focus Not Obscured (Enhanced) from focus traversal results.
    """
    records: List[RuleAuditRecord] = []

    for step in focus_steps:
        ratio = step.obscuration_ratio

        if ratio >= _FAIL_THRESHOLD:
            overlay_tags = ", ".join(
                f"<{ov.get('tag', '?')}>" for ov in step.covering_elements[:3]
            )
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="FAILED",
                    violation=(
                        f"Focused <{step.tag}>"
                        + (f" #{step.element_id}" if step.element_id else "")
                        + f" (step {step.step_index}) is obscured "
                        f"({ratio * 100:.0f}% covered) by author-created overlay(s): "
                        + (overlay_tags or "unknown")
                        + ". WCAG 2.4.12 (Enhanced) requires no obscuration of the focused element."
                    ),
                    html_snippet=step.html_snippet[:300],
                    element_id=step.element_id,
                    tag=step.tag,
                    page_url=step.page_url,
                )
            )
        elif ratio >= _REVIEW_THRESHOLD:
            overlay_tags = ", ".join(
                f"<{ov.get('tag', '?')}>" for ov in step.covering_elements[:3]
            )
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Focused <{step.tag}>"
                        + (f" #{step.element_id}" if step.element_id else "")
                        + f" (step {step.step_index}) has minor overlap "
                        f"({ratio * 100:.0f}%) with overlay(s): "
                        + (overlay_tags or "unknown")
                        + ". WCAG 2.4.12 requires *no* obscuration. Verify manually."
                    ),
                    html_snippet=step.html_snippet[:300],
                    element_id=step.element_id,
                    tag=step.tag,
                    page_url=step.page_url,
                )
            )

    if not records:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation=(
                    "No focused element was obscured by author-created content."
                ),
                page_url=focus_steps[0].page_url if focus_steps else "",
            )
        )

    return records