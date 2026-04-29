"""
ka11y/api/v1/combined/report.py
=================================
_build_report() — merges all flat findings into the final combined report shape.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ka11y.i18n.loader import (
    get_level_labels,
    get_severity_labels,
    get_status_labels,
)


def _build_report(
    url: str,
    all_findings: List[Dict],
    lang: str = "en",
    contrast_report: Optional[Dict[str, Any]] = None,
    image_audit_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge axe + Python flat findings into the final combined report.

    The image-related report keys surface both OCR contrast analysis and the
    broader image-audit result set alongside the flat findings.
    """
    violations = [f for f in all_findings if f["status"] == "fail"]
    needs_review = [f for f in all_findings if f["status"] == "needs_review"]
    passes = [f for f in all_findings if f["status"] == "pass"]

    sev_count: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in violations + needs_review:
        sev = f.get("severity")
        if sev in sev_count:
            sev_count[sev] += 1

    level_count: Dict[str, Dict] = {}
    sc_count: Dict[str, Dict] = {}
    src_count: Dict[str, Dict] = {}

    for f in all_findings:
        for bucket, key in [
            (level_count, f.get("level") or "unknown"),
            (sc_count, f.get("wcag_sc") or "unknown"),
            (src_count, f.get("source", "unknown")),
        ]:
            if key not in bucket:
                bucket[key] = {"violations": 0, "needs_review": 0, "passes": 0}
            if f["status"] == "fail":
                bucket[key]["violations"] += 1
            elif f["status"] == "needs_review":
                bucket[key]["needs_review"] += 1
            else:
                bucket[key]["passes"] += 1

    return {
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lang": lang,
        "labels": {
            "severities": get_severity_labels(lang),
            "levels":     get_level_labels(lang),
            "statuses":   get_status_labels(lang),
        },
        "summary": {
            "total_findings": len(all_findings),
            "violations": len(violations),
            "needs_review": len(needs_review),
            "passes": len(passes),
            "by_severity": sev_count,
            "by_level": level_count,
            "by_wcag_sc": sc_count,
            "by_source": src_count,
        },
        "violations": violations,
        "needs_review": needs_review,
        "passes": passes,
        "contrast_report": contrast_report,
        "image_audit_report": image_audit_report,
    }
