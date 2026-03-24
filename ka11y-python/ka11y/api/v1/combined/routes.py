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

from .models import CombinedRequest, JobStatusResponse
from .runner import _run_job
from .store import _jobs, _subscribers, _subscribers_lock

router = APIRouter(prefix="/combined", tags=["combined"])

_PRIVATE_PREFIXES = ("localhost", "127.", "10.", "192.168.", "169.254.")


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

    # SSRF guard: reject private / loopback / link-local URLs
    _parsed = urlparse(url)
    _host = _parsed.hostname or ""
    if _host == "localhost" or any(_host.startswith(p) for p in _PRIVATE_PREFIXES):
        raise HTTPException(
            status_code=400,
            detail=f"URL hostname '{_host}' is not allowed (private/loopback address).",
        )

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "url": url,
        "submitted_at": now,
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
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
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
    contrast_report = result.get("contrast_report") or {}
    valid_paths = {img["path"] for img in contrast_report.get("images", [])}

    if path not in valid_paths:
        raise HTTPException(
            status_code=403,
            detail="Image path is not associated with this job.",
        )

    img_path = Path(path)
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found on server.")

    media_type, _ = mimetypes.guess_type(str(img_path))
    return FileResponse(str(img_path), media_type=media_type or "image/png")


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
    async with _subscribers_lock:
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
            async with _subscribers_lock:
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
