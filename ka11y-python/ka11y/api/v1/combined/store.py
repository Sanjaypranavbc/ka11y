"""
ka11y/api/v1/combined/store.py
================================
In-memory job store and SSE subscriber bus.

_jobs            — dict of all live/recent audit jobs keyed by job_id
_subscribers     — per-job list of asyncio.Queue for SSE fan-out
_broadcast()     — push an event to every subscriber of a job
_close_subscribers() — drain and remove all subscriber queues for a job
_evict_old_jobs() — background TTL cleanup task (called from lifespan)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="combined")

# ── In-memory stores ──────────────────────────────────────────────────────────

_jobs: Dict[str, Dict[str, Any]] = {}

# SSE subscriber bus: job_id → list of per-client asyncio.Queue
_subscribers: Dict[str, List[asyncio.Queue]] = {}

# Bug 7 fix: do NOT create asyncio.Lock() at import time. Locks created at
# module-import time can be bound to the wrong event loop under pytest-asyncio,
# dev-server hot-reload, and alternative ASGI worker startup patterns.
# Use lazy initialisation via _get_subscribers_lock() instead.
_subscribers_lock: asyncio.Lock | None = None


def _get_subscribers_lock() -> asyncio.Lock:
    """Return the subscribers lock, creating it lazily inside the running loop."""
    global _subscribers_lock
    if _subscribers_lock is None:
        _subscribers_lock = asyncio.Lock()
    return _subscribers_lock


# TTL for completed/failed jobs (1 hour)
_JOB_TTL_SECONDS: int = 3600


# ── SSE subscriber bus ────────────────────────────────────────────────────────


async def _broadcast(job_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """Push an SSE event dict to every subscriber queue for this job.

    Acquires the subscribers lock before iterating so that a concurrent
    add-subscriber coroutine cannot slip between the snapshot and the
    put_nowait loop, which would cause a subscriber to miss the event.
    """
    msg = {"event": event_type, "data": data}
    async with _get_subscribers_lock():
        for q in list(_subscribers.get(job_id, [])):
            q.put_nowait(msg)


async def _close_subscribers(job_id: str) -> None:
    """Send sentinel None to all queues so their generators exit, then clean up.

    Also lock-protected so it is consistent with _broadcast.
    """
    async with _get_subscribers_lock():
        for q in list(_subscribers.get(job_id, [])):
            q.put_nowait(None)
        _subscribers.pop(job_id, None)


# ── TTL eviction ──────────────────────────────────────────────────────────────


async def _evict_old_jobs() -> None:
    """Background task: remove completed/failed jobs older than _JOB_TTL_SECONDS."""
    while True:
        await asyncio.sleep(300)  # run every 5 minutes
        cutoff = time.time() - _JOB_TTL_SECONDS
        expired = [
            jid
            for jid, job in list(_jobs.items())
            if job.get("status") in ("completed", "failed")
            and job.get("_created_at", 0) < cutoff
        ]
        for jid in expired:
            _jobs.pop(jid, None)
            _subscribers.pop(jid, None)
        if expired:
            logger.info(f"[combined] TTL eviction: removed {len(expired)} old jobs")
