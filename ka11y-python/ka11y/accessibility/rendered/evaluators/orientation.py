"""
ka11y/accessibility/rendered/evaluators/orientation.py
========================================================
WCAG 1.3.4 — Orientation (Level AA)

Goal: Content is not restricted to a single display orientation unless
essential (e.g. a bank cheque, piano app).

We run portrait and landscape viewport scenarios and check for:
  - Rotate-device gatekeeper overlays
  - Missing main content in one orientation
  - Dramatically different interactive element counts

Because essential-orientation exceptions may legitimately exist, ambiguous
cases return NEEDS_REVIEW rather than automatic FAILED.
"""

from __future__ import annotations

from typing import List

from ..models import PageSnapshot, RuleAuditRecord
from ..heuristics import detect_missing_main_content, detect_rotate_overlay

_RULE_KEY = "wcag_1_3_4"


def evaluate(
    portrait: PageSnapshot,
    landscape: PageSnapshot,
) -> List[RuleAuditRecord]:
    """
    Evaluate WCAG 1.3.4 Orientation using portrait and landscape snapshots.
    """
    records: List[RuleAuditRecord] = []

    for label, snap in [("portrait", portrait), ("landscape", landscape)]:
        overlay_el = detect_rotate_overlay(snap)
        if overlay_el is not None:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"A rotate-device overlay was detected in {label} orientation. "
                        f'Overlay text: "{overlay_el.text[:120]}". '
                        "If content is truly blocked in this orientation, it violates "
                        "WCAG 1.3.4 unless an essential exception applies. Verify manually."
                    ),
                    html_snippet=overlay_el.html_snippet[:300],
                    element_id=overlay_el.element_id,
                    tag=overlay_el.tag,
                    page_url=snap.page_url,
                )
            )

        if detect_missing_main_content(snap):
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Very few visible text elements were found in {label} orientation. "
                        "Main content may be hidden. If this is intentional orientation "
                        "restriction it may violate WCAG 1.3.4. Verify manually."
                    ),
                    page_url=snap.page_url,
                )
            )

    # Compare interactive element counts between orientations
    portrait_interactive = [e for e in portrait.elements if e.focusable and e.visible]
    landscape_interactive = [e for e in landscape.elements if e.focusable and e.visible]
    p_count = len(portrait_interactive)
    l_count = len(landscape_interactive)

    if (p_count == 0) != (l_count == 0):
        # Exactly one orientation returned zero interactive elements while the
        # other has some — this is a meaningful asymmetry that could indicate a
        # collapsed hamburger menu or orientation-locked content.  Division
        # would be undefined (or trivially 0), so we flag NEEDS_REVIEW instead.
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="NEEDS_REVIEW",
                violation=(
                    f"One orientation has no interactive elements "
                    f"(portrait: {p_count}, landscape: {l_count}). "
                    "A collapsed navigation (e.g. hamburger menu) or orientation-locked "
                    "content may be hiding functionality. Verify manually."
                ),
                page_url=portrait.page_url,
            )
        )
    elif p_count > 0 and l_count > 0:
        ratio = min(p_count, l_count) / max(p_count, l_count)
        if ratio < 0.5:
            records.append(
                RuleAuditRecord(
                    rule_key=_RULE_KEY,
                    status="NEEDS_REVIEW",
                    violation=(
                        f"Dramatic difference in interactive elements between orientations "
                        f"(portrait: {p_count}, landscape: {l_count}). "
                        "Some functionality may be orientation-locked. Verify manually."
                    ),
                    page_url=portrait.page_url,
                )
            )

    if not records:
        records.append(
            RuleAuditRecord(
                rule_key=_RULE_KEY,
                status="PASSED",
                violation="",
                page_url=portrait.page_url,
            )
        )

    return records
