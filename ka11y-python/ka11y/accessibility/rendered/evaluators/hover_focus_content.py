"""
ka11y/accessibility/rendered/evaluators/hover_focus_content.py
================================================================
WCAG 1.4.13 — Content on Hover or Focus (Level AA)

Goal: Supplemental content that appears on hover/focus must be:
  1. Dismissible (Escape removes it without moving focus)
  2. Hoverable (pointer can move over the content without it vanishing)
  3. Persistent (stays visible until hover/focus removed, or dismissed)

Full automation is not possible. We use heuristics to detect popup content
and check what we can; the rest is flagged as NEEDS_REVIEW.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import HoverInteractionResult, RuleAuditRecord

_RULE_KEY = "wcag_1_4_13"


def evaluate(
    interactions: List[HoverInteractionResult],
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.4.13 from a list of hover/focus interaction results.
    """
    records: List[RuleAuditRecord] = []

    if not interactions:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation="No hover/focus-triggered popup content detected on this page.",
                page_url="",
            )
        )
        return records

    for result in interactions:
        if not result.popup_appeared:
            continue

        issues: List[str] = []

        # Check dismissibility
        if result.dismissible_by_escape is False:
            issues.append(
                "Popup cannot be dismissed by pressing Escape without moving focus."
            )

        # Check hoverability
        if result.pointer_can_move_over is False:
            issues.append(
                "Popup disappears when the pointer moves towards it "
                "(content is not hoverable)."
            )

        # Persistence is hard to test reliably; flag as needs_review if uncertain
        if result.persists_until_removed is False:
            issues.append(
                "Popup did not persist until focus/hover was explicitly removed."
            )

        if issues:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="FAILED" if result.certain else "NEEDS_REVIEW",
                    violation=(
                        f"Hover/focus popup on <{result.trigger_tag}> "
                        + (f"#{result.trigger_id} " if result.trigger_id else "")
                        + "may violate WCAG 1.4.13: "
                        + " | ".join(issues)
                    ),
                    html_snippet=result.trigger_html[:300],
                    element_id=result.trigger_id,
                    tag=result.trigger_tag,
                    page_url=result.page_url,
                )
            )
        else:
            # Popup appeared but all detectable checks passed → needs_review
            # because we cannot fully automate the complete set of checks.
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Hover/focus popup detected on <{result.trigger_tag}> "
                        + (f"#{result.trigger_id} " if result.trigger_id else "")
                        + "— automated checks passed but manual verification "
                        "of dismissible/hoverable/persistent behaviour is required."
                    ),
                    html_snippet=result.trigger_html[:300],
                    element_id=result.trigger_id,
                    tag=result.trigger_tag,
                    page_url=result.page_url,
                )
            )

    if not records:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation=(
                    "No hover/focus-triggered popups detected, or no issues found "
                    "in automated checks."
                ),
                page_url=interactions[0].page_url if interactions else "",
            )
        )

    return records
