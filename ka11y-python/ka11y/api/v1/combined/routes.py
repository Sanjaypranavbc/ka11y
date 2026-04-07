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

from .models import CombinedRequest, JobStatusResponse
from .runner import _run_job
from .store import _get_subscribers_lock, _jobs, _subscribers

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

    # Inject image_url into contrast_report images so the frontend can load them.
    # _build_contrast_report stores only the filesystem `path`; the serving URL
    # is constructed here at response time to keep the image endpoint URL in one place.
    result = job.get("result") or {}
    contrast_report = result.get("contrast_report") or {}
    for img in contrast_report.get("images", []):
        if not img.get("image_url") and img.get("path"):
            from urllib.parse import quote

            img["image_url"] = (
                f"/api/v1/combined/{job_id}/image?path={quote(img['path'], safe='')}"
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
