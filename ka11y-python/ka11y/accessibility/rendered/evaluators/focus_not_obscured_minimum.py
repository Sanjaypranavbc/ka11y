"""
ka11y/accessibility/rendered/evaluators/focus_not_obscured_minimum.py
=======================================================================
WCAG 2.4.11 — Focus Not Obscured (Minimum) (Level AA)

Goal: When a UI component receives keyboard focus, it is not entirely hidden
by author-created content (sticky headers, cookie banners, chat widgets, etc.).

Logic:
  - FAILED when the focused element is fully obscured (overlap >= 95%)
  - NEEDS_REVIEW when partially obscured (overlap 10–95%) — uncertain
  - PASSED when overlap < 10%
"""

from __future__ import annotations

from typing import List

from ..models import FocusStep, RuleAuditRecord

_RULE_KEY = "wcag_2_4_11"

# WCAG 2.4.11 — Focus Not Obscured (Minimum):
# "Any focus indicator obscured = FAIL; we use 95% to allow 1-2px scroll bars"
# Reference: https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum
OBSCURATION_FAIL_THRESHOLD = 0.95   # >= this ratio → FAIL
OBSCURATION_REVIEW_THRESHOLD = 0.10  # >= this ratio → NEEDS_REVIEW

# Keep legacy private names as aliases so existing callers are not broken.
_FULLY_OBSCURED_THRESHOLD = OBSCURATION_FAIL_THRESHOLD
_PARTIAL_THRESHOLD = OBSCURATION_REVIEW_THRESHOLD


def evaluate(focus_steps: List[FocusStep]) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 2.4.11 from keyboard focus traversal results.
    """
    records: List[RuleAuditRecord] = []

    for step in focus_steps:
        ratio = step.obscuration_ratio

        if ratio >= _FULLY_OBSCURED_THRESHOLD:
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
                        + f" (step {step.step_index}) is fully obscured "
                        f"({ratio * 100:.0f}% covered) by author-created overlay(s): "
                        + (overlay_tags or "unknown")
                        + ". Violates WCAG 2.4.11 Focus Not Obscured (Minimum)."
                    ),
                    html_snippet=step.html_snippet[:300],
                    element_id=step.element_id,
                    tag=step.tag,
                    page_url=step.page_url,
                )
            )
        elif ratio >= _PARTIAL_THRESHOLD:
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
                        + f" (step {step.step_index}) is partially obscured "
                        f"({ratio * 100:.0f}% covered) by overlay(s): "
                        + (overlay_tags or "unknown")
                        + ". 2.4.11 requires the element is not *entirely* hidden; "
                        "partial coverage may be acceptable but should be verified."
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
                    "No focused element was found to be fully obscured by "
                    "author-created content."
                ),
                page_url=focus_steps[0].page_url if focus_steps else "",
            )
        )

    return records
