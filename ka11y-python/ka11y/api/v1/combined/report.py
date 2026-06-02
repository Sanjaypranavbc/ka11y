"""
ka11y/api/v1/combined/report.py
=================================
_build_report() — merges all flat findings into the final combined report shape.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ka11y.crawler.policy import CrawlPolicy
from ka11y.i18n.loader import (
    get_level_labels,
    get_severity_labels,
    get_status_labels,
)
from ka11y.utils.url_canonical import canonicalize_url as _canonicalize_url

# Single shared policy used purely for URL canonicalization in the report.
# Mirrors the BFS defaults so the page table groups variants of the same page
# (http vs https, trailing-slash, tracker params) into one row.
_REPORT_URL_POLICY = CrawlPolicy()


def _finding_signature(f: Dict) -> str:
    """Element-identity signature for a finding, independent of its status.

    Used to build a stable ``finding_id`` so a client can attach a manual-review
    decision to a specific item and have it survive restart / re-read."""
    el = f.get("element") or {}
    parts = [
        str(f.get("wcag_sc") or ""),
        str(f.get("rule_id") or ""),
        str(el.get("page_url") or ""),
        str(el.get("frame_path") or ""),
        str(el.get("selector") or el.get("target") or ""),
        str(el.get("element_ref_id") or ""),
        str(el.get("element_id") or ""),
        str(el.get("tag") or ""),
        str(el.get("image_src") or ""),
        (" ".join(str(el.get("html") or "").split())[:200]),
    ]
    return "|".join(parts)


def _stamp_finding_ids(findings: List[Dict]) -> None:
    """Stamp each finding with a deterministic ``finding_id`` (+ disambiguate
    exact duplicates) and a ``manual_review`` flag for needs_review items."""
    seen: Dict[str, int] = {}
    for f in findings:
        sig = _finding_signature(f)
        n = seen.get(sig, 0)
        seen[sig] = n + 1
        raw = sig if n == 0 else f"{sig}#{n}"
        f["finding_id"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        # needs_review items are the ones a human must adjudicate. Surface that
        # explicitly so the UI can label them "Manual Review Required".
        f["manual_review"] = f.get("status") == "needs_review"


def apply_reviews(report: Dict[str, Any], reviews: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Overlay manual-review decisions onto a built report and recompute the
    *effective* score so it reflects human adjudication.

    ``reviews`` maps ``finding_id`` → ``{"status": "pass"|"violation", "note": ...}``.
    A reviewed needs_review item counts toward passes/violations for the headline
    counts and the pass-rate; the original automated counts are preserved under
    ``summary.automated``. Mutates and returns *report*. Safe with empty reviews
    (then effective == automated, so nothing visibly changes)."""
    summary = report.get("summary") or {}
    # Idempotent: source the automated baseline from a prior overlay if present,
    # so applying reviews twice to the same (hot-cache) report object doesn't
    # compound the counts.
    automated = summary.get("automated") or {
        "violations": summary.get("violations", 0),
        "needs_review": summary.get("needs_review", 0),
        "passes": summary.get("passes", 0),
        "score": summary.get("score"),
    }

    reviewed = as_pass = as_violation = 0
    # Stamp every needs_review finding (flat list + per-page copies share refs).
    for f in report.get("needs_review", []) or []:
        rev = reviews.get(f.get("finding_id")) if reviews else None
        if rev and rev.get("status") in ("pass", "violation"):
            f["review_status"] = rev["status"]
            f["review_note"] = rev.get("note")
            f["reviewed"] = True
            reviewed += 1
            if rev["status"] == "pass":
                as_pass += 1
            else:
                as_violation += 1
        else:
            f.pop("review_status", None)
            f.pop("reviewed", None)

    eff_violations = automated["violations"] + as_violation
    eff_passes = automated["passes"] + as_pass
    eff_needs_review = automated["needs_review"] - reviewed
    denom = eff_passes + eff_violations
    eff_score = round(100.0 * eff_passes / denom, 1) if denom else None

    summary["automated"] = automated
    summary["violations"] = eff_violations
    summary["needs_review"] = eff_needs_review
    summary["passes"] = eff_passes
    summary["score"] = eff_score
    summary["manual_review_required"] = eff_needs_review
    summary["reviews"] = {
        "reviewed": reviewed,
        "pending": eff_needs_review,
        "as_pass": as_pass,
        "as_violation": as_violation,
    }
    report["summary"] = summary

    # Per-page effective recompute. pages[].needs_review holds the SAME finding
    # objects just stamped above, so each page's score reflects its own reviews.
    for page in report.get("pages", []) or []:
        ps = page.get("summary") or {}
        if "automated" not in ps:
            ps["automated"] = {
                "violations": ps.get("violations", 0),
                "needs_review": ps.get("needs_review", 0),
                "passes": ps.get("passes", 0),
                "score": ps.get("score"),
            }
        p_pass = sum(1 for f in page.get("needs_review", []) if f.get("review_status") == "pass")
        p_viol = sum(1 for f in page.get("needs_review", []) if f.get("review_status") == "violation")
        ev = ps["automated"]["violations"] + p_viol
        ep = ps["automated"]["passes"] + p_pass
        enr = ps["automated"]["needs_review"] - p_pass - p_viol
        d = ep + ev
        ps["violations"] = ev
        ps["passes"] = ep
        ps["needs_review"] = enr
        ps["manual_review_required"] = enr
        ps["score"] = round(100.0 * ep / d, 1) if d else None
        page["summary"] = ps
    return report


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
    # Stamp stable ids + manual_review flags before bucketing so every copy of a
    # finding (flat lists + per-page arrays) carries the same id.
    _stamp_finding_ids(all_findings)

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
    # R-2: canonicalise the root URL once up front so the element-less
    # fallback path produces the same key as element-stamped findings (which
    # were canonicalised in _make_finding). Without this, `https://x.com` and
    # `https://x.com/` end up as separate page rows in the by_page table.
    canonical_root = _canonicalize_url(url) if url else url

    def _page_of(f: Dict) -> str:
        element = f.get("element")
        raw = (
            element["page_url"]
            if isinstance(element, dict) and element.get("page_url")
            else canonical_root
        )
        # Apply both layers of normalisation: the CrawlPolicy step keeps the
        # report grouping bug-compatible with older runs (strips tracker
        # params etc.), and the canonicalise step keeps Python + Node + the
        # snapshot all in agreement.
        normalized = _REPORT_URL_POLICY.normalize_url(raw)
        return _canonicalize_url(normalized) if normalized else (normalized or raw)

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
    # a confirmed failure). A page/crawl with NO pass-or-fail findings (only
    # needs_review, or nothing) returns ``None`` — "not scored" — rather than a
    # misleading 100.0. The old 100.0 made pages that were barely audited (e.g.
    # axe never ran on them, only image needs_review findings landed) advertise
    # perfect compliance; ``None`` lets the UI render "—" so an un-scored page is
    # never confused with a passing one. Both the overall crawl and each page
    # expose it so the UI can show one headline score plus a per-page column.
    def _score(passes_n: int, violations_n: int) -> Optional[float]:
        denom = passes_n + violations_n
        if denom == 0:
            return None
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
            # needs_review items are surfaced to the UI as "Manual Review
            # Required"; this mirrors the count until a reviewer adjudicates them
            # (apply_reviews then decrements it as items move to pass/violation).
            "manual_review_required": len(needs_review),
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
