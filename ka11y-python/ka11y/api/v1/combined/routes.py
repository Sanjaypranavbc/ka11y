"""
ka11y/api/v1/combined/routes.py
=================================
FastAPI route handlers for the combined audit endpoint.

  POST /combined/                  202  Submit audit job
  GET  /combined/{job_id}          200  Poll status / retrieve result
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

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from typing import AsyncGenerator

from ka11y.crawler._ssrf_guard import (
    _host_is_blocked,
    _parse_literal_ip,
    _resolve_hostname,
)

from .models import CombinedRequest, JobStatusResponse
from .runner import _run_job
from .store import _get_job_lock, _get_subscribers_lock, _jobs, _subscribers

router = APIRouter(prefix="/combined", tags=["combined"])

# Localhost aliases that resolve to loopback but aren't literal IPs.
_LOCALHOST_ALIASES = {"localhost", "ip6-localhost", "ip6-loopback"}


async def assert_public_url(url: str) -> None:
    """Reject URLs whose host is private/loopback/reserved before a crawl starts.

    The actual SSRF classification — encoded IP literals (decimal/hex/octal),
    IPv4-mapped IPv6, hostname resolution, localhost aliases — lives in the
    single canonical guard :mod:`ka11y.crawler._ssrf_guard`. This entry-point
    check shares that logic so the request-level guard and the per-request
    Playwright route guard can never disagree. The same guard is re-applied to
    every request (including redirect targets) via ``install_ssrf_guard``.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"URL scheme '{parsed.scheme}' is not supported; use http or https.",
        )

    if not host:
        raise HTTPException(status_code=400, detail="URL hostname is missing.")

    # For real hostnames (not literal IPs / localhost aliases), surface a
    # friendly 400 when DNS fails outright — otherwise the crawl proceeds and
    # dies later with an opaque NavigationError. _resolve_hostname is
    # lru_cached, so _host_is_blocked below reuses this lookup for free.
    if (
        _parse_literal_ip(host) is None
        and host.lower() not in _LOCALHOST_ALIASES
    ):
        resolved = await asyncio.to_thread(_resolve_hostname, host)
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail=f"URL hostname '{host}' could not be resolved.",
            )

    if _host_is_blocked(host):
        raise HTTPException(
            status_code=400,
            detail=(
                f"URL hostname '{host}' is not allowed "
                "(private/loopback/reserved address)."
            ),
        )


@router.post("/", response_model=JobStatusResponse, status_code=202)
async def submit_combined_audit(payload: CombinedRequest):
    """
    Submit a combined Python + Node axe-core accessibility audit.

    Returns `job_id` immediately (HTTP 202). Poll **GET /api/v1/combined/{job_id}**
    for status and the full report, or connect to
    **GET /api/v1/combined/{job_id}/stream** for real-time SSE stage events.

    **Graceful degradation**: if Node/axe-core is unavailable the job still
    completes using Python-only findings; a `warnings` list notes the failure.
    """
    job_id = str(uuid.uuid4())
    url = str(payload.url)
    now = datetime.now(timezone.utc).isoformat()

    # SSRF guard: reject private / loopback / link-local endpoints.
    await assert_public_url(url)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
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

    asyncio.create_task(_run_job(job_id, payload))
    from ka11y.config.logger import setup_logger

    logger = setup_logger(name="KAC", tag="combined")
    logger.info(f"[combined] job {job_id} submitted for {url}")
    return _jobs[job_id]


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_combined_audit(job_id: str):
    """Poll the status or retrieve the result of a combined audit job."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
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

    # Inject image_url into image-backed reports so the frontend can load them.
    result = job.get("result") or {}
    from urllib.parse import quote

    for report_key in ("contrast_report", "image_audit_report"):
        report = result.get(report_key) or {}
        for img in report.get("images", []):
            if not img.get("image_url") and img.get("path"):
                img["image_url"] = (
                    f"/api/v1/combined/{job_id}/image?path={quote(img['path'], safe='')}"
                )

    for array_key in ("violations", "needs_review", "passes"):
        arr = result.get(array_key) or []
        for finding in arr:
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

    return job


@router.get("/{job_id}/image")
async def get_job_image(job_id: str, path: str):
    """
    Serve an image file belonging to a completed audit job.

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
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

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
