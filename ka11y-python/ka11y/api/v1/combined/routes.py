"""
ka11y/api/v1/combined/routes.py
=================================
FastAPI route handlers for the combined audit endpoint.

  POST /combined/                  202  Submit audit job
  GET  /combined/{job_id}          200  Poll status / retrieve result
  GET  /combined/{job_id}/timings  200  Per-stage timing breakdown (JSON)
  GET  /combined/{job_id}/stream   200  SSE real-time stage events
  GET  /combined/{job_id}/image         Serve a job's image artifact
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import mimetypes
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from typing import AsyncGenerator
from ka11y.utils.run_timing import compute_run_timing
from pydantic import BaseModel, Field
from .dispatcher import enqueue
from .models import CombinedRequest, JobStatusResponse
from .report import apply_reviews
from .store import _get_job_lock, _get_subscribers_lock, _jobs, _subscribers
from ka11y.store import repo
from ka11y.store.assets import get_asset


class FindingReviewRequest(BaseModel):
    """A reviewer's adjudication of a 'Manual Review Required' (needs_review) item.

    ``status='needs_review'`` re-opens the item (clears a prior decision)."""

    status: str = Field(pattern=r"^(pass|violation|needs_review)$")
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=200)

# Private/reserved IP ranges that must never be fetched (SSRF guard for redirects).
# These CIDR networks cover: loopback, RFC-1918 private, link-local, unique-local
# (IPv6), documentation ranges, and the IPv4-mapped IPv6 loopback.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),  # RFC-1918 class A private
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 class B private
    ipaddress.ip_network("192.168.0.0/16"),  # RFC-1918 class C private
    ipaddress.ip_network("169.254.0.0/16"),  # IPv4 link-local
    ipaddress.ip_network("100.64.0.0/10"),  # Shared address space (RFC 6598)
    ipaddress.ip_network("192.0.0.0/24"),  # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("0.0.0.0/8"),  # "This" network
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local (fc00 + fd00)
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ipaddress.ip_network("::ffff:127.0.0.1/128"),  # IPv4-mapped IPv6 loopback
]


def _ip_is_blocked(ip_str: str) -> bool:
    """Return True if *ip_str* falls within any blocked private/reserved network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _BLOCKED_NETWORKS)


router = APIRouter(prefix="/combined", tags=["combined"])


def _is_non_public_ip(ip: str) -> bool:
    """
    Return True for IP addresses that should never be fetched by audit workers:
    private, loopback, link-local, multicast, reserved, or unspecified.
    """
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return False

    return any(
        (
            parsed.is_private,
            parsed.is_loopback,
            parsed.is_link_local,
            parsed.is_multicast,
            parsed.is_reserved,
            parsed.is_unspecified,
            _ip_is_blocked(ip),
        )
    )


def build_ssrf_route_handler(page):
    """
    Return a Playwright ``page.route()`` handler that blocks requests to
    private/reserved IP addresses during a crawl.

    This prevents SSRF via HTTP redirects: even if attacker.com responds with
    a 301 to http://192.168.1.1, Playwright will call this handler before
    following the redirect and the request will be aborted.

    Usage::

        handler = build_ssrf_route_handler(page)
        await page.route("**/*", handler)
    """
    import re

    # Regex to quickly detect literal IP hostnames in URLs (avoids DNS lookup
    # inside the hot-path handler).
    _IP_HOST_RE = re.compile(r"https?://(\[?[0-9a-fA-F:.]+\]?)(?:[:/]|$)")

    async def _handler(route, request):
        url = request.url
        m = _IP_HOST_RE.match(url)
        if m:
            host = m.group(1).strip("[]")
            if _ip_is_blocked(host):
                await route.abort("addressunreachable")
                return
        await route.continue_()

    return _handler


async def _resolve_all_ips(hostname: str) -> list[str]:
    infos = await asyncio.to_thread(
        socket.getaddrinfo,
        hostname,
        None,
        0,
        socket.SOCK_STREAM,
    )
    addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip = sockaddr[0]
        if ip not in addrs:
            addrs.append(ip)
    return addrs


async def assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme '{parsed.scheme}' is not supported; use http or https.",
        )

    if not host:
        raise HTTPException(status_code=400, detail="URL hostname is missing.")

    if host.lower() == "localhost":
        raise HTTPException(
            status_code=400,
            detail="URL hostname 'localhost' is not allowed (private/loopback address).",
        )

    # Literal IP host
    try:
        if _is_non_public_ip(host):
            raise HTTPException(
                status_code=400,
                detail=f"URL hostname '{host}' is not allowed (private/loopback address).",
            )
        return
    except ValueError:
        # Not a literal IP, continue with DNS resolution.
        pass

    try:
        resolved = await _resolve_all_ips(host)
    except socket.gaierror:
        raise HTTPException(
            status_code=400,
            detail=f"URL hostname '{host}' could not be resolved.",
        )

    if not resolved:
        raise HTTPException(
            status_code=400,
            detail=f"URL hostname '{host}' resolved to no addresses.",
        )

    blocked = [ip for ip in resolved if _is_non_public_ip(ip)]
    if blocked:
        sample = ", ".join(blocked[:3])
        raise HTTPException(
            status_code=400,
            detail=(
                f"URL hostname '{host}' resolves to private/loopback address(es): {sample}."
            ),
        )


@router.post("/", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(payload: CombinedRequest):
    """
    Submit a combined Python + Node axe-core accessibility audit.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report, or connect to
    **GET /api/v1/
    /{job_id}/stream** for real-time SSE stage events.

    **Graceful degradation**: if Node/axe-core is unavailable the job still
    completes using Python-only findings; a `warnings` list notes the failure.
    """
    return await _admit_run(payload)


async def _admit_run(payload: CombinedRequest, *, rerun_of: str | None = None) -> dict:
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


    await enqueue(job_id, payload)
    from ka11y.config.logger import setup_logger
    logger = setup_logger(name="KAC", tag="combined")

    logger.info(f"[combined] Job {job_id} submitted for {url}")
    return _jobs[job_id]


@router.post("/{job_id}/rerun", status_code=202)
async def rerun_combined_audit(job_id: str):
    """Re-audit a past run with its exact stored parameters.

    Returns a NEW ``job_id`` (the original run is preserved for comparison). Use
    this to refresh a result after an engine improvement — e.g. the per-page OCR
    budget change that recovers image findings on deep-crawl child pages — without
    re-entering the URL and toggles. The new run flows through the normal durable
    queue + dispatcher.
    """
    run = await repo.get_run(job_id)
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id!r} not found in the durable store; cannot re-run.",
        )
    try:
        params = json.loads(run.get("params_json") or "{}")
        payload = CombinedRequest(**params)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Stored audit parameters could not be reconstructed for re-run.",
        )
    new_job = await _admit_run(payload, rerun_of=job_id)
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
    if not result or not result.get("needs_review"):
        return
    try:
        reviews = await repo.get_reviews(job_id)
    except Exception:  # noqa: BLE001
        return
    apply_reviews(result, reviews)


async def _finalize_job_view(job: dict, job_id: str) -> None:
    _inject_image_urls(job, job_id)
    await _apply_reviews_to_job(job, job_id)


@router.get("/history")
async def list_combined_history(
    limit: int = 50, offset: int = 0, url: str | None = None, status: str | None = None
):
    """Paginated history of past audit runs (durable; survives restart/TTL).

    Reads straight from the ``runs`` table so the list is available even after
    a run has been evicted from the in-memory hot cache.
    """
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
        "error_id": run.get("error_id"),
        "error_stage": run.get("error_stage"),
        "current_stage": None,
        "stages": [],
        "warnings": (result or {}).get("warnings", []) if result else [],
    }
    return job


@router.post("/{job_id}/cancel")
async def cancel_combined_audit(job_id: str):
    """Cooperatively cancel a queued/running audit. The worker checks the DB
    status between stages and aborts if it sees ``cancelled``."""
    run = await repo.get_run(job_id)
    in_hot = job_id in _jobs
    if not run and not in_hot:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    current = (run or {}).get("status") or _jobs.get(job_id, {}).get("status")
    if current in ("completed", "failed", "cancelled"):
        return {"job_id": job_id, "status": current, "cancelled": False}
    await repo.update_run(
        job_id, status="cancelled", completed_at=datetime.now(timezone.utc).isoformat()
    )
    if in_hot:
        _jobs[job_id]["status"] = "cancelled"
    repo.insert_event(job_id, "cancelled", {})
    return {"job_id": job_id, "status": "cancelled", "cancelled": True}


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_combined_audit(job_id: str):
    """Poll the status or retrieve the result of a combined audit job."""
    if job_id not in _jobs:
        # Durable fallback: the run may have been evicted from the hot cache or
        # the process may have restarted — reconstruct it from SQLite.
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
async def get_finding_reviews(job_id: str):
    """List the manual-review decisions recorded for a run's needs_review items."""
    run = await repo.get_run(job_id)
    if not run and job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    reviews = await repo.get_reviews(job_id)
    return {"job_id": job_id, "reviews": reviews, "count": len(reviews)}


@router.post("/{job_id}/findings/{finding_id}/review")
async def review_finding(job_id: str, finding_id: str, body: FindingReviewRequest):
    """Record/clear a reviewer's adjudication of a 'Manual Review Required' item.

    The next GET /combined/{job_id} returns the report with the effective score
    (violations / needs_review / passes) updated to reflect this decision.
    """
    run = await repo.get_run(job_id)
    in_hot = job_id in _jobs
    if not run and not in_hot:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    # Locate the finding in the report to capture its SC/page for the audit row
    # and to reject ids that don't correspond to a needs_review item.
    result = (_jobs.get(job_id, {}).get("result")) or (await repo.get_report(job_id)) or {}
    target = next(
        (f for f in result.get("needs_review", []) if f.get("finding_id") == finding_id),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"Finding {finding_id!r} is not a reviewable (needs_review) item of this run.",
        )

    await repo.set_finding_review(
        run_id=job_id,
        finding_id=finding_id,
        status=body.status,
        note=body.note,
        reviewer=body.reviewer,
        wcag_sc=target.get("wcag_sc"),
        page_url=(target.get("element") or {}).get("page_url"),
    )
    repo.insert_event(
        job_id,
        "finding_reviewed",
        {"finding_id": finding_id, "status": body.status, "wcag_sc": target.get("wcag_sc")},
    )
    return {
        "job_id": job_id,
        "finding_id": finding_id,
        "status": body.status,
        "wcag_sc": target.get("wcag_sc"),
    }


@router.get("/{job_id}/timings")
async def get_combined_audit_timings(job_id: str):
    """
    Return the per-stage timing breakdown for a combined audit job as JSON.

    This is the same data appended to ``logs/run_timings.log`` when the job
    finishes (queue wait, per-stage durations, run/wall totals), derived from
    the timestamps the runner/stage-events already recorded — so the API and
    the log file never drift. Safe to poll mid-run: unfinished stages report
    ``duration_s: null`` and the run/wall totals fill in once the job completes.
    """
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
async def get_job_image(job_id: str, path: str):
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
    # that escapes it. Bounding to the *configured* output root (rather than
    # the per-job dir) is the right granularity here — the image crawler
    # writes to ``{output_root}/{domain}_{ts}`` which is a SIBLING of the
    # combined job's ``{output_root}/{domain}_{ts}_{job_id}_combined`` dir,
    # so a per-job containment check rejects every legitimate image path
    # ("image unavailable" everywhere in the UI). The original symlink-
    # attack guard from the security review still holds: paths outside the
    # configured root are refused.
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
async def stream_combined_audit(job_id: str):
    """
    Server-Sent Events stream for a combined audit job.

    Connect immediately after submitting to receive real-time stage progress.
    Events: stage_start | stage_complete | stage_error | job_state |
            job_complete | job_failed
    Heartbeat: ': keepalive' comment lines every 25 s.
    """
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
                yield (
                    f"event: job_failed\n"
                    f"data: {json.dumps({'job_id': job_id, 'error': 'Audit failed due to an internal error.'})}\n\n"
                )
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
                    if msg["event"] in ("job_complete", "job_failed"):
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
