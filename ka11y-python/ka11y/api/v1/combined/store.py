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

class _LazyAsyncLock:
    """Loop-aware proxy around asyncio.Lock for safe module-level reuse."""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock = asyncio.Lock()
            self._loop = loop
        return self._lock

    async def acquire(self) -> bool:
        return await self._ensure_lock().acquire()

    def release(self) -> None:
        lock = self._ensure_lock()
        if lock.locked():
            lock.release()

    def locked(self) -> bool:
        return self._ensure_lock().locked()

    async def __aenter__(self) -> "_LazyAsyncLock":
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


_subscribers_lock = _LazyAsyncLock()


def _get_subscribers_lock() -> asyncio.Lock:
    """Return the current loop's underlying subscribers lock."""
    return _subscribers_lock._ensure_lock()


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
