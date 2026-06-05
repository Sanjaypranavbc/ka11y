"""
ka11y/accessibility/rendered/evaluators/hover_focus_content.py
================================================================
WCAG 1.4.13 — Content on Hover or Focus (Level AA)

Goal: Supplemental content that appears on hover/focus must be:
  1. Dismissible (Escape removes it without moving focus)
  2. Hoverable (pointer can move over the content without it vanishing)
  3. Persistent (stays visible until hover/focus removed, or dismissed)

Full automation is not possible. We use heuristics to detect popup content and
apply deterministic checks where possible; unknowns are flagged as NEEDS_REVIEW.
"""

from __future__ import annotations

from typing import List

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

        failed_issues: List[str] = []
        unknown_checks: List[str] = []

        if result.dismissible_by_escape is False:
            failed_issues.append(
                "Popup cannot be dismissed by pressing Escape without moving focus."
            )
        elif result.dismissible_by_escape is None:
            unknown_checks.append("dismissible")

        if result.pointer_can_move_over is False:
            failed_issues.append(
                "Popup disappears when the pointer moves towards it "
                "(content is not hoverable)."
            )
        elif result.pointer_can_move_over is None:
            unknown_checks.append("hoverable")

        if result.persists_until_removed is False:
            failed_issues.append(
                "Popup did not persist until focus/hover was explicitly removed."
            )
        elif result.persists_until_removed is None:
            unknown_checks.append("persistent")

        if failed_issues:
            status = (
                "FAILED"
                if result.certain
                or (
                    result.dismissible_by_escape is not None
                    and result.pointer_can_move_over is not None
                    and result.persists_until_removed is not None
                )
                else "NEEDS_REVIEW"
            )
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status=status,
                    violation=(
                        f"Hover/focus popup on <{result.trigger_tag}> "
                        + (f"#{result.trigger_id} " if result.trigger_id else "")
                        + "may violate WCAG 1.4.13: "
                        + " | ".join(failed_issues)
                    ),
                    html_snippet=result.trigger_html[:300],
                    element_id=result.trigger_id,
                    tag=result.trigger_tag,
                    page_url=result.page_url,
                )
            )
        elif unknown_checks:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Hover/focus popup detected on <{result.trigger_tag}> "
                        + (f"#{result.trigger_id} " if result.trigger_id else "")
                        + "— partial checks passed but "
                        + ", ".join(unknown_checks)
                        + " behaviour could not be verified automatically."
                    ),
                    html_snippet=result.trigger_html[:300],
                    element_id=result.trigger_id,
                    tag=result.trigger_tag,
                    page_url=result.page_url,
                )
            )
        else:
            # All three measurable checks passed.
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="PASSED",
                    violation=(
                        f"Hover/focus popup detected on <{result.trigger_tag}> "
                        + (f"#{result.trigger_id} " if result.trigger_id else "")
                        + "meets automated dismissible, hoverable, and persistent checks."
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
