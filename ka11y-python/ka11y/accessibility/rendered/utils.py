"""
ka11y/accessibility/rendered/utils.py
======================================
Shared utilities for the rendered-layout audit engine.
"""

from __future__ import annotations

from typing import List

from .models import RuleAuditRecord


def deduplicate_records(
    records: List[RuleAuditRecord],
    max_per_status: int = 50,
) -> List[RuleAuditRecord]:
    """
    Limit the number of records per status to avoid flooding the report.
    Preserves the first `max_per_status` FAILED, then NEEDS_REVIEW, then PASSED.
    """
    counts = {"FAILED": 0, "NEEDS_REVIEW": 0, "PASSED": 0, "N/A": 0}
    out: List[RuleAuditRecord] = []
    for rec in records:
        s = rec.status
        if counts.get(s, 0) < max_per_status:
            out.append(rec)
            counts[s] = counts.get(s, 0) + 1
    return out


def truncate_html(html: str, max_len: int = 300) -> str:
    """Safely truncate an HTML snippet."""
    return html[:max_len] if html else ""