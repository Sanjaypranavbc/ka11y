"""
ka11y/api/v1/combined/routes.py
=================================
FastAPI route handlers for accessibility audit endpoints.

  POST /python-audit/              202  Submit Python-only audit job (image, OCR contrast, media/captions)
  POST /combined-audit/            202  Submit combined audit job (Python + Node/axe-core — Node wired via runner)
  GET  /combined/{job_id}          200  Poll status / retrieve result
  GET  /combined/{job_id}/timings  200  Per-stage timing breakdown (JSON)
  GET  /combined/{job_id}/stream   200  SSE real-time stage events
  GET  /combined/{job_id}/image         Serve a job's image artifact
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from typing import Any, AsyncGenerator
from ka11y.utils.run_timing import compute_run_timing
from pydantic import BaseModel, Field, HttpUrl
from .dispatcher import enqueue
from .models import CombinedRequest, JobStatusResponse
from ka11y.observability import attributes as attrs
from ka11y.observability import current_span, set_span_attributes
from .report import apply_reviews, review_message
from ka11y.accessibility.technique_map import annotate_findings, strip_failure_techniques
from .store import _broadcast, _close_subscribers, _get_job_lock, _get_subscribers_lock, _jobs, _subscribers
from ka11y.store import repo
from ka11y.auth import ANONYMOUS, CurrentUser, require_user
from ka11y.api.v1.audits import _assert_can_view
from ka11y.config.logger import setup_logger
from ka11y.crawler._ssrf_guard import (
    _classify_blocked,
    _ip_is_blocked,
    _parse_literal_ip,
    _resolve_hostname,
)

logger = setup_logger(name="KAC", tag="combined")


class FindingReviewRequest(BaseModel):
    """A reviewer's adjudication of a 'Manual Review Required' (needs_review) item.

    ``status='needs_review'`` re-opens the item (clears a prior decision)."""

    status: str = Field(pattern=r"^(pass|violation|needs_review)$")
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=200)

# One sentence for every reason a target is refused, so the response cannot be
# used to tell an internal hostname from a non-existent one. Wording matches
# `url_not_allowed` in ka11y.errors.
_NOT_PUBLIC_DETAIL = (
    "The specified target is not permitted. "
    "Only publicly routable hosts may be audited."
)

router =APIRouter(prefix="/combined", tags=["combined audit"])


def _caller(user: Any) -> CurrentUser:
    """The signed-in user, or ANONYMOUS when a handler is called directly
    (tests) and the parameter is FastAPI's ``Depends`` sentinel, not a user."""
    return user if isinstance(user, CurrentUser) else ANONYMOUS


async def assert_public_url(url: str) -> None:
    """Reject a submission whose host is private, loopback, link-local or
    otherwise non-public (SSRF). Uses the same classifier as the browser-context
    guard in crawler/_ssrf_guard.py, which stays in force during the crawl
    for redirects and sub-resources; this check just fails fast with a 400."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme '{parsed.scheme}' is not supported; use http or https.",
        )
    if not host:
        raise HTTPException(status_code=400, detail="URL hostname is missing.")
    if host.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
        raise HTTPException(
            status_code=400,
            detail=f"URL hostname '{host}' is not allowed (private/loopback address).",
        )

    literal = _parse_literal_ip(host)
    if literal is not None:
        if _classify_blocked(literal):
            raise HTTPException(
                status_code=400,
                detail=f"URL hostname '{host}' is not allowed (private/loopback address).",
            )
        return

    # Every rejection below answers with the same sentence and never names a
    # resolved address. Reporting the address, or distinguishing "does not
    # resolve" from "resolves internally", would let anyone who can submit an
    # audit use this endpoint to map internal DNS. The specific reason is
    # logged instead. _resolve_hostname returns an empty tuple on failure.
    resolved = await asyncio.to_thread(_resolve_hostname, host)
    if not resolved:
        logger.info("[ssrf] refused %s: hostname does not resolve", host)
        raise HTTPException(status_code=400, detail=_NOT_PUBLIC_DETAIL)

    blocked = [ip for ip in resolved if _ip_is_blocked(ip)]
    if blocked:
        logger.warning(
            "[ssrf] refused %s: resolves to non-public address(es) %s",
            host,
            ", ".join(blocked[:3]),
        )
        raise HTTPException(status_code=400, detail=_NOT_PUBLIC_DETAIL)


@router.post("/python-audit", response_model=JobStatusResponse, status_code=202)
async def submit_python_audit(
    payload: CombinedRequest, user: CurrentUser = Depends(require_user)
):
    """
    Submit a **Python-only** accessibility audit.

    Runs the Python stages only: image audit (1.1.1 / 1.4.5 / 1.4.11 / 4.1.2),
    OCR contrast (1.4.3 / 1.4.6) and the media/captions audit (1.2.1 / 1.2.2),
    plus the cross-page and linked-PDF checks on multi-page crawls.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report, or connect to
    **GET /api/v1/combined/{job_id}/stream** for real-time SSE stage events.
    """
    return await _admit_run(payload, user=user)


@router.post("/combined-audit", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(
    # HttpUrl, not str: as a plain str the CombinedRequest below is built
    # inside the handler, so a bad URL raised pydantic.ValidationError rather
    # than a request-validation error and the caller got 500 for a typo.
    url: HttpUrl = Query(...),
    max_depth: int = Query(0, ge=0, le=5),
    max_pages: int = Query(20, ge=1, le=200),
    wcag_level: str = Query("AAA", pattern=r"^(A|AA|AAA)$"),
    # Same pattern as CombinedRequest.email. Checked here too: the request
    # below is built inside the handler, so a bad address raised
    # pydantic.ValidationError there and the caller got 500, not 422.
    email: str | None = Query(None, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    lang: str = Query("auto", max_length=20, pattern=r"^(auto|[A-Za-z][A-Za-z0-9_-]*)$"),
    user: CurrentUser = Depends(require_user),
):
    """
    Submit a **combined Python + Node/axe-core** accessibility audit.

    Convenience endpoint — accepts plain `url`/`max_depth` query parameters instead
    of a full JSON request body. All active Python audit stages are enabled by
    default (image audit, OCR/contrast, media, captions).

    `max_depth` (0-5): extra pages to crawl beyond `url` itself. 0 = single page.
    `max_pages` (default 20): page budget for the whole crawl; values above the
    20-page policy ceiling are silently capped rather than rejected (see
    ``CombinedRequest._cap_max_pages``).
    `wcag_level` (A | AA | AAA): conformance level to report against. The filter
    is cumulative — "AA" returns A + AA findings and suppresses AAA.
    `lang`: language every reason/criterion string is rendered in. Defaults to
    "auto", which detects the audited page's own language — pass an explicit
    locale ("en", "ja") when the caller has a user-chosen language, otherwise an
    English site always reports in English regardless of that choice.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report.
    """
    payload = CombinedRequest(
        url=str(url),
        max_depth=max_depth,
        max_pages=max_pages,
        wcag_level=wcag_level,
        email=email,
        lang=lang,
        run_ocr=True,
        run_image_audit=True,
        run_media_audit=True,
        run_captions_audit=True,
    )
    return await _admit_run(payload, user=user)



async def _admit_run(
    payload: CombinedRequest,
    *,
    rerun_of: str | None = None,
    user: CurrentUser | None = None,
) -> dict:
    """Create the hot-cache entry and enqueue a run through the durable queue.

    Shared by fresh submissions and re-audits so both go through the exact same
    SSRF guard, queue, and dispatcher path."""
    job_id = str(uuid.uuid4())
    url = str(payload.url)
    now = datetime.now(timezone.utc).isoformat()

    # SSRF guard: reject private / loopback / link-local endpoints.
    await assert_public_url(url)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "url": url,
        "submitted_at": now,
        "lang": payload.lang,
        "_created_at": time.time(),
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
    }

    # One row: the audit_jobs record carries the owner (when the caller is
    # signed in) and is the queue entry the dispatcher drains. isinstance,
    # not a None check: when a test calls the route function directly the
    # parameter is FastAPI's Depends() sentinel, not a user.
    owner = user if isinstance(user, CurrentUser) else None
    try:
        await enqueue(job_id, payload, user=owner)
    except Exception:  # noqa: BLE001
        # The queue row is the job. Without it nothing will ever run, so the
        # caller must not receive a job id: drop the hot entry and answer 503.
        logger.exception("[combined] job %s could not be queued", job_id)
        _jobs.pop(job_id, None)
        raise HTTPException(status_code=503, detail="Audit queue is unavailable. Please try again.")

    logger.info("[combined] job %s submitted for %s", job_id, url)
    # Stamp the job id on the HTTP span (the middleware's, still current here).
    # The audit runs as its own trace, so this attribute is the thread that
    # leads from "this request was slow / errored" to the audit it started.
    set_span_attributes(
        current_span(),
        {
            attrs.JOB_ID: job_id,
            attrs.JOB_URL: url,
            attrs.JOB_LANG: payload.lang,
            attrs.JOB_WCAG_LEVEL: payload.wcag_level,
            attrs.JOB_RERUN_OF: rerun_of,
        },
    )
    return _jobs[job_id]


@router.post("/{job_id}/rerun", status_code=202)
async def rerun_combined_audit(job_id: str, user: CurrentUser = Depends(require_user)):
    """Re-audit a past run with its exact stored parameters.

    Returns a NEW ``job_id`` (the original run is preserved for comparison). Use
    this to refresh a result after an engine improvement — e.g. the per-page OCR
    budget change that recovers image findings on deep-crawl child pages — without
    re-entering the URL and toggles. The new run flows through the normal durable
    queue + dispatcher.
    """
    await _assert_can_view(job_id, _caller(user))
    run = await repo.get_run(job_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id!r} not found in the durable store; cannot re-run.",
        )
    try:
        params = run.get("params") or {}
        if isinstance(params, str):
            params = json.loads(params or "{}")
        payload = CombinedRequest(**params)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Stored audit parameters could not be reconstructed for re-run.",
        )
    new_job = await _admit_run(payload, rerun_of=job_id, user=user)
    return {**new_job, "rerun_of": job_id}


def _inject_image_urls(job: dict, job_id: str) -> None:
    """Rewrite on-disk image paths to job-scoped serving URLs for the frontend.

    Shared by the hot-cache and durable (DB) read paths so both return the same
    shape regardless of whether the run is still in memory.
    """
    from urllib.parse import quote

    result = job.get("result") or {}
    for report_key in ("contrast_report", "image_audit_report"):
        report = result.get(report_key) or {}
        for img in report.get("images", []):
            if not img.get("image_url") and img.get("path"):
                img["image_url"] = (
                    f"/api/v1/combined/{job_id}/image?path={quote(img['path'], safe='')}"
                )

    for array_key in ("violations", "needs_review", "passes"):
        for finding in result.get(array_key) or []:
            element = finding.get("element")
            if element and isinstance(element, dict):
                src = element.get("image_src")
                if (
                    src
                    and not src.startswith("/api/v1/")
                    and not src.startswith(("http://", "https://", "data:"))
                ):
                    element["image_src"] = (
                        f"/api/v1/combined/{job_id}/image?path={quote(src, safe='')}"
                    )


async def _apply_reviews_to_job(job: dict, job_id: str) -> None:
    """Overlay any stored manual-review decisions onto the job's report so the
    effective score (violations / needs_review / passes counts) reflects them."""
    result = job.get("result")
    if not result or not isinstance(result, dict):
        return
    # Not gated on a non-empty needs_review list: on the hot-cache object the
    # overlay has already moved reviewed items into violations/passes, and a
    # verdict that was since cleared must still be re-partitioned back.
    if not any(result.get(k) for k in ("violations", "needs_review", "passes")):
        return
    try:
        reviews = await repo.get_reviews(job_id)
    except Exception:  # noqa: BLE001
        return
    apply_reviews(result, reviews)


def _refresh_techniques(result: dict | None) -> None:
    """Re-tag every finding with the *current* technique map. Reports store the
    tags they were built with; re-annotating on read means a mapping fix (or a
    regenerated map) applies to existing audits too. Idempotent and cheap —
    a few dict lookups per finding — and the per-page arrays share the same
    finding objects, so the flat lists are enough."""
    if not isinstance(result, dict):
        return
    findings = []
    for key in ("violations", "needs_review", "passes"):
        findings.extend(f for f in (result.get(key) or []) if isinstance(f, dict))
    if findings:
        annotate_findings(findings)


async def _finalize_job_view(job: dict, job_id: str) -> None:
    """Shape a job record for the frontend.

    This is the *only* place the UI reads findings from, so it is also the
    boundary where failing / needs_review findings lose their WCAG
    situation/technique tags (passing findings keep them). The strip works on
    a copy: the hot-cache entry, the run store, the exports and the email all
    keep the full report. Runs after the review overlay so a reviewed item is
    judged on its final status."""
    _inject_image_urls(job, job_id)
    await _apply_reviews_to_job(job, job_id)
    if job.get("result"):
        _refresh_techniques(job["result"])
        job["result"] = strip_failure_techniques(job["result"])


@router.get("/history")
async def list_combined_history(
    limit: int = 50,
    offset: int = 0,
    url: str | None = None,
    status: str | None = None,
    user: CurrentUser = Depends(require_user),
):
    """Paginated history of *every* audit run in the durable store.

    The ``runs`` table has no owner column, so this is an operator view:
    admins only (``KA11Y_ADMIN_EMAILS``), or anyone when auth is disabled.
    Signed-in users get their own history from ``GET /audits/history``.
    """
    caller = _caller(user)
    if not caller.is_anonymous and not caller.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required.")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    try:
        runs = await repo.list_runs(limit=limit, offset=offset, url=url, status=status)
    except Exception:
        raise HTTPException(status_code=503, detail="History store unavailable.")
    return {"runs": runs, "limit": limit, "offset": offset, "count": len(runs)}


async def _job_from_db(job_id: str) -> dict | None:
    """Reconstruct a JobStatusResponse-shaped dict from the durable store for a
    run no longer in the in-memory hot cache (restart / TTL eviction)."""
    run = await repo.get_run(job_id)
    if not run:
        return None
    result = None
    if run.get("status") == "completed":
        result = await repo.get_report(job_id)
    job = {
        "job_id": job_id,
        "status": run.get("status", "unknown"),
        "url": run.get("url", ""),
        "submitted_at": run.get("submitted_at") or "",
        "lang": run.get("lang_resolved") or run.get("lang_requested") or "auto",
        "completed_at": run.get("completed_at"),
        "report_path": run.get("output_dir"),
        "result": result,
        "error": None if run.get("status") != "failed" else "Audit failed due to an internal error.",
        # Reconstructed from the durable store, which has no error_code column
        # until the Postgres migration. The UI falls back to `error` above.
        "error_code": run.get("error_code"),
        "error_id": run.get("error_id"),
        "error_stage": run.get("error_stage"),
        "current_stage": None,
        "stages": [],
        "warnings": (result or {}).get("warnings", []) if result else [],
    }
    return job


_EXPORT_MEDIA = {
    "json": "application/json; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
}


async def _full_report(job_id: str) -> dict | None:
    """The complete report for a finished job — every finding, pass and fail,
    with its technique/situation tags — with manual-review decisions applied.
    Deep-copied so rendering never touches the cached object. ``None`` when
    the job is unknown or has no stored report."""
    result = None
    if job_id in _jobs:
        async with _get_job_lock(job_id):
            snapshot = _jobs.get(job_id) or {}
            if snapshot.get("status") == "completed":
                result = snapshot.get("result")
    if result is None:
        run = await repo.get_run(job_id)
        if not run:
            return None
        if run.get("status") == "completed":
            result = await repo.get_report(job_id)
    if not result:
        return None
    report = json.loads(json.dumps(result, ensure_ascii=False, default=str))
    holder = {"result": report}
    await _apply_reviews_to_job(holder, job_id)
    _refresh_techniques(holder["result"])
    return holder["result"]


@router.get("/{job_id}/export")
async def export_combined_audit(
    job_id: str,
    format: str = Query(..., pattern=r"^(json|csv|html|pdf)$"),
    user: CurrentUser = Depends(require_user),
):
    """Download the full audit report as JSON, CSV, HTML or PDF.

    Unlike ``GET /{job_id}`` (the dashboard's view), every finding here —
    pass, fail and needs_review — carries its WCAG ``situations`` and
    ``techniques``. The CSV is flat, one row per (finding, technique). Files
    are built on demand from the stored report; the filename uses the audited
    host, never the job id.
    """
    await _assert_can_view(job_id, _caller(user))
    report = await _full_report(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report is stored for this audit yet.")

    host = (urlparse(str(report.get("url") or "")).hostname or "audit").replace(":", "_")
    filename = f"{host}-accessibility-audit.{format}"

    body: bytes | str
    if format == "json":
        body = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    elif format == "csv":
        from ka11y.utils.report_csv import build_export_csv

        body = build_export_csv(report)
    elif format == "html":
        from ka11y.utils.report_pdf import _MAX_ROWS_PER_SECTION, _collect_images, build_report_html

        try:
            images = await _collect_images(report, _MAX_ROWS_PER_SECTION)
        except Exception:  # noqa: BLE001
            images = {}
        body = build_report_html(report, images, max_rows=None)
    else:
        from ka11y.utils.report_pdf import build_report_pdf

        pdf = await build_report_pdf(report)
        if pdf is None:
            raise HTTPException(status_code=503, detail="PDF rendering is unavailable right now.")
        body = pdf
    return Response(
        content=body,
        media_type=_EXPORT_MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{job_id}/cancel")
async def cancel_combined_audit(job_id: str, user: CurrentUser = Depends(require_user)):
    """Cooperatively cancel a queued/running audit.

    Queued: settled immediately (hot cache + ``job_cancelled`` SSE event).
    Running: the runner re-reads the stored status before it starts and again
    once the crawl/OCR/Node engines finish, and stops there — an in-flight
    browser pass is not interrupted."""
    await _assert_can_view(job_id, _caller(user))
    run = await repo.get_run(job_id)
    in_hot = job_id in _jobs
    if not run and not in_hot:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    current = (run or {}).get("status") or _jobs.get(job_id, {}).get("status")
    if current in ("completed", "failed", "cancelled"):
        return {"job_id": job_id, "status": current, "cancelled": False}
    completed_at = datetime.now(timezone.utc).isoformat()
    await repo.mark_cancelled(job_id, completed_at)
    if in_hot:
        # A queued job has no runner to notice the flag: settle it here. A
        # running one is left 'running' for the runner, which checks the flag
        # at its next checkpoint and emits job_cancelled itself.
        if current == "running":
            async with _get_job_lock(job_id):
                _jobs[job_id]["cancel_requested"] = True
        else:
            async with _get_job_lock(job_id):
                _jobs[job_id].update(status="cancelled", completed_at=completed_at, current_stage=None)
            await _broadcast(job_id, "job_cancelled", {"job_id": job_id, "when": "while queued"})
            await _close_subscribers(job_id)
    return {"job_id": job_id, "status": "cancelled", "cancelled": True}


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_combined_audit(job_id: str, user: CurrentUser = Depends(require_user)):
    """Poll the status or retrieve the result of a combined audit job."""
    await _assert_can_view(job_id, _caller(user))
    if job_id not in _jobs:
        # Durable fallback: the run may have been evicted from the hot cache or
        # the process may have restarted — reconstruct it from the run store.
        db_job = await _job_from_db(job_id)
        if db_job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        await _finalize_job_view(db_job, job_id)
        return db_job
    # Snapshot under the per-job lock so a concurrent runner._run_job() update
    # cannot publish a half-applied state to a polling client. Shallow copy is
    # sufficient because we only read top-level fields below.
    async with _get_job_lock(job_id):
        snapshot = _jobs.get(job_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        job = dict(snapshot)
        # `stages` is a list mutated by sync stage_events; snapshot it too.
        if "stages" in job:
            job["stages"] = list(job["stages"])

    await _finalize_job_view(job, job_id)
    return job


@router.get("/{job_id}/reviews")
async def get_finding_reviews(job_id: str, user: CurrentUser = Depends(require_user)):
    """List the manual-review decisions recorded for a run's needs_review items."""
    await _assert_can_view(job_id, _caller(user))
    run = await repo.get_run(job_id)
    if not run and job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    reviews = await repo.get_reviews(job_id)
    return {"job_id": job_id, "reviews": reviews, "count": len(reviews)}


def _find_reviewable(result: dict, finding_id: str) -> dict | None:
    """The finding with *finding_id* whose automated status is needs_review.

    Searched across every bucket (and the per-page arrays reference the same
    objects): after a verdict the overlay moves the item into violations or
    passes, and a second verdict / re-open must still find it."""
    for bucket in ("needs_review", "violations", "passes"):
        for f in result.get(bucket) or []:
            if f.get("finding_id") == finding_id:
                return f if f.get("status") == "needs_review" else None
    return None


@router.post("/{job_id}/findings/{finding_id}/review")
async def review_finding(
    job_id: str,
    finding_id: str,
    body: FindingReviewRequest,
    user: CurrentUser = Depends(require_user),
):
    """Record or clear a manual verdict on a 'Manual Review Required' item.

    Only findings the engine marked ``needs_review`` can be adjudicated; an
    engine pass/fail is authoritative and returns 409. ``status`` is ``pass``
    or ``violation`` (a fail), or ``needs_review`` to re-open. The verdict is a
    stored overlay: the next GET /combined/{job_id} (and every export) shows
    the item under its new bucket with ``review_status``, ``reviewed_by``,
    ``reviewed_at``, ``verdict_source: "manual"`` and the audit-trail
    ``review_message`` ("Reviewed by user and manually changed to Pass.").
    """
    user = _caller(user)
    await _assert_can_view(job_id, user)
    run = await repo.get_run(job_id)
    in_hot = job_id in _jobs
    if not run and not in_hot:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    result = (_jobs.get(job_id, {}).get("result")) or (await repo.get_report(job_id)) or {}
    target = _find_reviewable(result, finding_id)
    if target is None:
        known = any(
            f.get("finding_id") == finding_id
            for b in ("violations", "needs_review", "passes")
            for f in result.get(b) or []
        )
        if known:
            raise HTTPException(
                status_code=409,
                detail="Only findings the engine marked needs_review can be given a manual verdict.",
            )
        raise HTTPException(status_code=404, detail=f"Finding {finding_id!r} is not part of this run.")

    # The reviewer is the signed-in user; the request body can only name one
    # when there is no identity (auth disabled / anonymous).
    reviewer = user.email or user.name or body.reviewer or "user"
    await repo.set_finding_review(
        run_id=job_id,
        finding_id=finding_id,
        status=body.status,
        note=body.note,
        reviewer=reviewer,
        wcag_sc=target.get("wcag_sc"),
        page_url=(target.get("element") or {}).get("page_url"),
    )
    reviews = await repo.get_reviews(job_id)
    rev = reviews.get(finding_id)
    lang = result.get("lang") or (run or {}).get("lang_resolved") or "en"
    return {
        "job_id": job_id,
        "finding_id": finding_id,
        "status": body.status,
        "wcag_sc": target.get("wcag_sc"),
        "reviewed": rev is not None,
        "verdict_source": "manual" if rev else "engine",
        "review_status": rev["status"] if rev else None,
        "review_note": rev.get("note") if rev else None,
        "reviewed_by": rev.get("reviewer") if rev else None,
        "reviewed_at": rev.get("updated_at") if rev else None,
        "review_message": review_message(rev["status"], lang) if rev else None,
    }


@router.get("/{job_id}/timings")
async def get_combined_audit_timings(job_id: str, user: CurrentUser = Depends(require_user)):
    """
    Return the per-stage timing breakdown for a combined audit job as JSON.

    This is the same data appended to ``logs/run_timings.log`` when the job
    finishes (queue wait, per-stage durations, run/wall totals), derived from
    the timestamps the runner/stage-events already recorded — so the API and
    the log file never drift. Safe to poll mid-run: unfinished stages report
    ``duration_s: null`` and the run/wall totals fill in once the job completes.
    """
    await _assert_can_view(job_id, _caller(user))
    async with _get_job_lock(job_id):
        snapshot = _jobs.get(job_id)
        if snapshot:
            job = dict(snapshot)
            if "stages" in job:
                job["stages"] = [dict(s) for s in job["stages"]]
        else:
            job = None

    if job is None:
        # Durable fallback: rebuild the per-(page,stage,rule) breakdown from the
        # stage_timings table for runs no longer in the hot cache.
        run = await repo.get_run(job_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        rows = await repo.get_timings(job_id)
        # The stored error is repr(exc) of the failed step: internal paths,
        # hosts and library text. It stays in the table and the logs; the
        # client gets the step's status only.
        for row in rows:
            row["error"] = None
        return {
            "job_id": job_id,
            "url": run.get("url"),
            "status": run.get("status"),
            "queue_wait_ms": run.get("queue_wait_ms"),
            "wall_ms": run.get("wall_ms"),
            "steps": rows,
        }

    result = job.get("result") or {}
    return compute_run_timing(
        job_id=job_id,
        url=job.get("url", ""),
        status=job.get("status", "unknown"),
        stages=job.get("stages", []),
        submitted_at=job.get("submitted_at"),
        run_started_at=job.get("run_started_at"),
        completed_at=job.get("completed_at"),
        lang=job.get("lang"),
        summary=result.get("summary"),
        error_stage=job.get("error_stage"),
    )


@router.get("/{job_id}/image")
async def get_job_image(job_id: str, path: str, user: CurrentUser = Depends(require_user)):
    """
    DEPRECATED legacy image serving (``?path=``). Superseded by the
    content-addressed ``GET /api/v1/assets/{id}`` route: as of P2 the runner
    registers every report-referenced image in the ``assets`` table and points
    ``image_url`` / ``element.image_src`` at ``/api/v1/assets/{id}``. This
    endpoint remains only as a fallback for images that were never
    content-addressed (e.g. a run produced before the asset store existed).

    The ``path`` query parameter must exactly match one of the image paths
    recorded in ``result.contrast_report.images`` for the given job.
    """
    await _assert_can_view(job_id, _caller(user))
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    result = job.get("result") or {}
    valid_paths = set()
    for report_key in ("contrast_report", "image_audit_report"):
        report = result.get(report_key) or {}
        valid_paths.update(
            img["path"] for img in report.get("images", []) if img.get("path")
        )

    # Canonicalize the requested path to prevent path-traversal attacks.
    # valid_paths are already canonical absolute paths stored by the auditor.
    try:
        canonical_path = Path(path).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image path.")

    canonical_valid = {str(Path(p).resolve()) for p in valid_paths}
    if str(canonical_path) not in canonical_valid:
        raise HTTPException(
            status_code=403,
            detail="Image path is not associated with this job.",
        )

    # Defence-in-depth: even if a (poisoned) auditor record stored a symlink
    # pointing outside the configured output tree, refuse to serve content
    # that escapes it. Combined-audit images now live under the job's own
    # directory (``<job_dir>/images/…``), but runs produced before the
    # crawler consolidation wrote them to a SIBLING ``{output_root}/{domain}_{ts}``
    # folder, so the configured output root (and the job dir's parent) stay
    # accepted as containment roots. The original symlink-attack guard from
    # the security review still holds: paths outside the configured root are
    # refused.
    from ka11y.utils.config_loader import load_config

    try:
        config = load_config()
        configured_root = config.get("input", {}).get("output_dir")
    except Exception:
        configured_root = None

    candidate_roots = []
    if configured_root:
        candidate_roots.append(Path(configured_root).resolve())
    job_output_dir = job.get("output_dir")
    if job_output_dir:
        # Also accept the job's own dir (e.g. report.json) and its parent —
        # gives us coverage for sibling crawler dirs without depending on
        # the config being consistent with the runner's path.
        candidate_roots.append(Path(job_output_dir).resolve())
        candidate_roots.append(Path(job_output_dir).resolve().parent)

    if candidate_roots:
        contained = False
        for root in candidate_roots:
            try:
                canonical_path.relative_to(root)
                contained = True
                break
            except ValueError:
                continue
        if not contained:
            raise HTTPException(
                status_code=403,
                detail="Image path escapes the configured output directory.",
            )

    if not canonical_path.exists() or not canonical_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found on server.")

    media_type, _ = mimetypes.guess_type(str(canonical_path))
    return FileResponse(str(canonical_path), media_type=media_type or "image/png")


@router.get("/{job_id}/stream")
async def stream_combined_audit(job_id: str, user: CurrentUser = Depends(require_user)):
    """
    Server-Sent Events stream for a combined audit job.

    Connect immediately after submitting to receive real-time stage progress.
    Events: stage_start | stage_complete | stage_error | job_state |
            job_complete | job_failed | job_cancelled
    Heartbeat: ': keepalive' comment lines every 25 s.
    """
    await _assert_can_view(job_id, _caller(user))
    job = _jobs.get(job_id)
    if not job:
        # Durable fallback: the run may have completed before this client
        # connected (or the process restarted). Emit its terminal state from the
        # store and close, rather than 404-ing a finished run.
        run = await repo.get_run(job_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

        async def _terminal() -> AsyncGenerator[str, None]:
            status = run.get("status")
            if status == "completed":
                rep = await repo.get_report(job_id) or {}
                yield (
                    f"event: job_complete\n"
                    f"data: {json.dumps({'job_id': job_id, 'summary': rep.get('summary', {})})}\n\n"
                )
            elif status == "failed":
                failure = {
                    "job_id": job_id,
                    "error": "Audit failed due to an internal error.",
                    "error_code": _jobs.get(job_id, {}).get("error_code"),
                }
                yield f"event: job_failed\ndata: {json.dumps(failure)}\n\n"
            elif status == "cancelled":
                yield f"event: job_cancelled\ndata: {json.dumps({'job_id': job_id})}\n\n"
            else:
                yield f"event: job_state\ndata: {json.dumps({'status': status})}\n\n"

        return StreamingResponse(
            _terminal(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    q: asyncio.Queue = asyncio.Queue()
    async with _get_subscribers_lock():
        _subscribers.setdefault(job_id, []).append(q)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            current = _jobs.get(job_id, {})

            if current.get("status") == "completed":
                result = current.get("result", {})
                yield (
                    f"event: job_complete\n"
                    f"data: {json.dumps({'job_id': job_id, 'summary': result.get('summary', {})})}\n\n"
                )
                return
            if current.get("status") == "failed":
                yield (
                    f"event: job_failed\n"
                    f"data: {json.dumps({'job_id': job_id, 'error': current.get('error', '')})}\n\n"
                )
                return
            if current.get("status") == "cancelled":
                yield f"event: job_cancelled\ndata: {json.dumps({'job_id': job_id})}\n\n"
                return

            if current.get("current_stage") or current.get("stages"):
                yield (
                    f"event: job_state\n"
                    f"data: {json.dumps({'current_stage': current.get('current_stage'), 'stages': current.get('stages', [])})}\n\n"
                )

            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    if msg is None:
                        break
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                    if msg["event"] in ("job_complete", "job_failed", "job_cancelled"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            async with _get_subscribers_lock():
                subs = _subscribers.get(job_id, [])
                if q in subs:
                    subs.remove(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
