"""
ka11y/api/v1/combined/report.py
=================================
_build_report() — merges all flat findings into the final combined report shape.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ka11y.crawler.policy import CrawlPolicy
from ka11y.i18n.loader import (
    get_level_labels,
    get_severity_labels,
    get_status_labels,
)

# Single shared policy used purely for URL canonicalization in the report.
# Mirrors the BFS defaults so the page table groups variants of the same page
# (http vs https, trailing-slash, tracker params) into one row.
_REPORT_URL_POLICY = CrawlPolicy()


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

    # ── Page-wise breakdown ──────────────────────────────────────────────────
    # Multi-page crawls (max_depth > 0) attribute each finding to its source page
    # via element.page_url. Element-less findings (page-level checks) fall back to
    # the audited root URL. We expose both a `summary.by_page` count map (mirroring
    # by_wcag_sc) and a `pages` array that groups the findings per page with its own
    # summary, so clients can render a per-page view without re-scanning the flat
    # lists. The page entries reference the same finding objects as the flat lists.
    def _page_of(f: Dict) -> str:
        element = f.get("element")
        raw = (
            element["page_url"]
            if isinstance(element, dict) and element.get("page_url")
            else url
        )
        # Canonicalize the URL the same way the BFS does so http://x/ and
        # https://x and https://x/ all bucket into the same page row instead
        # of appearing as separate rows in the page table.
        normalized = _REPORT_URL_POLICY.normalize_url(raw)
        return normalized or raw

    by_page: Dict[str, Dict[str, int]] = {}
    page_buckets: Dict[str, Dict[str, List[Dict]]] = {}
    page_order: List[str] = []
    for f in all_findings:
        page_url = _page_of(f)
        if page_url not in by_page:
            by_page[page_url] = {"violations": 0, "needs_review": 0, "passes": 0}
            page_buckets[page_url] = {
                "violations": [],
                "needs_review": [],
                "passes": [],
            }
            page_order.append(page_url)
        status = f["status"]
        bucket_key = (
            "violations"
            if status == "fail"
            else "needs_review"
            if status == "needs_review"
            else "passes"
        )
        by_page[page_url][bucket_key] += 1
        page_buckets[page_url][bucket_key].append(f)

    # Compliance score: pass-rate = passes / (passes + violations), as a 0–100
    # percentage. needs_review is deliberately excluded (it is neither a pass nor
    # a confirmed failure). A page/crawl with no pass-or-fail findings scores 100
    # (nothing failed). Both the overall crawl and each individual page expose it
    # so the UI can show one headline score plus a per-page column.
    def _score(passes_n: int, violations_n: int) -> float:
        denom = passes_n + violations_n
        if denom == 0:
            return 100.0
        return round(100.0 * passes_n / denom, 1)

    pages: List[Dict[str, Any]] = []
    for page_url in page_order:
        buckets = page_buckets[page_url]
        page_sev: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in buckets["violations"] + buckets["needs_review"]:
            sev = f.get("severity")
            if sev in page_sev:
                page_sev[sev] += 1
        pages.append(
            {
                "page_url": page_url,
                "summary": {
                    "total_findings": (
                        len(buckets["violations"])
                        + len(buckets["needs_review"])
                        + len(buckets["passes"])
                    ),
                    "violations": len(buckets["violations"]),
                    "needs_review": len(buckets["needs_review"]),
                    "passes": len(buckets["passes"]),
                    "score": _score(
                        len(buckets["passes"]), len(buckets["violations"])
                    ),
                    "by_severity": page_sev,
                },
                "violations": buckets["violations"],
                "needs_review": buckets["needs_review"],
                "passes": buckets["passes"],
            }
        )

    # Worst pages first (most violations, then most needs_review), URL as tiebreak.
    pages.sort(
        key=lambda p: (
            -p["summary"]["violations"],
            -p["summary"]["needs_review"],
            p["page_url"],
        )
    )

    return {
        "url": url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lang": lang,
        "labels": {
            "severities": get_severity_labels(lang),
            "levels": get_level_labels(lang),
            "statuses": get_status_labels(lang),
        },
        "summary": {
            "total_findings": len(all_findings),
            "violations": len(violations),
            "needs_review": len(needs_review),
            "passes": len(passes),
            "score": _score(len(passes), len(violations)),
            "by_severity": sev_count,
            "by_level": level_count,
            "by_wcag_sc": sc_count,
            "by_source": src_count,
            "by_page": by_page,
            "page_count": len(pages),
        },
        "violations": violations,
        "needs_review": needs_review,
        "passes": passes,
        "pages": pages,
        "contrast_report": contrast_report,
        "image_audit_report": image_audit_report,
    }
