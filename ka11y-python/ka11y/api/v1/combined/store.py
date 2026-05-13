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
import os
import shutil
import time
from pathlib import Path
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
    """Return the subscribers lock, creating it lazily inside the running loop.

    Each asyncio.Lock is bound to the event loop that creates it. We recreate
    the lock whenever the running loop changes (e.g. after a hot-reload or a
    new pytest-asyncio session spawns a fresh loop), so the lock is always
    compatible with the current loop's scheduler.
    """
    global _subscribers_lock
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if _subscribers_lock is None or (
        running_loop is not None
        and getattr(_subscribers_lock, "_loop", None) is not running_loop
    ):
        _subscribers_lock = asyncio.Lock()
    return _subscribers_lock


# Per-job locks. Multi-field _jobs[job_id].update({...}) calls and list-mutate
# operations like stages.append() are not atomic in CPython (each kwarg is a
# separate dict[k]=v). Without a lock, a polling reader can observe a
# partially-applied update or iterate a stages list that's being appended to.
# Same lazy-init-bound-to-running-loop pattern as _subscribers_lock above.
_job_locks: Dict[str, asyncio.Lock] = {}
_job_locks_loop: Any = None


def _get_job_lock(job_id: str) -> asyncio.Lock:
    """Return a per-job asyncio.Lock, creating it lazily and rebinding the
    whole registry if the running event loop has changed (test runs, hot
    reload). Holding this lock makes a multi-field update atomic from the
    perspective of any other reader that also holds it."""
    global _job_locks, _job_locks_loop
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None and _job_locks_loop is not running_loop:
        _job_locks = {}
        _job_locks_loop = running_loop

    lock = _job_locks.get(job_id)
    if lock is None:
        lock = asyncio.Lock()
        _job_locks[job_id] = lock
    return lock


def _drop_job_lock(job_id: str) -> None:
    """Release the lock entry for a job that's been removed from _jobs."""
    _job_locks.pop(job_id, None)


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


def _safe_rmtree(path: str | os.PathLike[str]) -> bool:
    """Best-effort recursive delete. Returns True if anything was removed.

    Refuses to touch a path outside the configured output root — otherwise
    a poisoned job dict could trick eviction into deleting arbitrary trees.
    Errors are swallowed (TTL is best-effort) but logged.
    """
    try:
        from ka11y.utils.config_loader import load_config

        config = load_config()
        configured_root = config.get("input", {}).get("output_dir")
    except Exception:
        configured_root = None

    target = Path(path).resolve()
    if not target.is_dir():
        return False

    if configured_root:
        try:
            target.relative_to(Path(configured_root).resolve())
        except ValueError:
            logger.warning(
                "[combined] TTL eviction refused to delete %s "
                "(outside configured output root)",
                target,
            )
            return False

    try:
        shutil.rmtree(target, ignore_errors=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[combined] TTL eviction failed to remove %s: %s", target, exc
        )
        return False


def _evict_orphan_output_dirs(cutoff: float) -> int:
    """Sweep the configured output root for sub-directories older than
    ``cutoff`` (mtime) that are not referenced by any live job's
    ``output_dir`` field. Catches the sibling AsyncImageCrawler dirs
    that are not part of any single job's ``_combined`` tree."""
    try:
        from ka11y.utils.config_loader import load_config

        config = load_config()
        configured_root = config.get("input", {}).get("output_dir")
    except Exception:
        configured_root = None
    if not configured_root:
        return 0

    root = Path(configured_root)
    if not root.is_dir():
        return 0

    live_paths = {
        Path(j["output_dir"]).resolve()
        for j in _jobs.values()
        if j.get("output_dir")
    }

    removed = 0
    for child in root.iterdir():
        try:
            if not child.is_dir():
                continue
            if child.resolve() in live_paths:
                continue
            if child.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        if _safe_rmtree(child):
            removed += 1
    return removed


async def _evict_old_jobs() -> None:
    """Background task: remove completed/failed jobs older than
    ``_JOB_TTL_SECONDS`` and reclaim their on-disk output_dir, plus any
    orphan sibling crawler dirs older than the same cutoff (Sprint 4 /
    step 29)."""
    while True:
        await asyncio.sleep(300)  # run every 5 minutes
        cutoff = time.time() - _JOB_TTL_SECONDS
        expired = [
            jid
            for jid, job in list(_jobs.items())
            if job.get("status") in ("completed", "failed")
            and job.get("_created_at", 0) < cutoff
        ]
        dirs_removed = 0
        for jid in expired:
            job = _jobs.pop(jid, None) or {}
            _subscribers.pop(jid, None)
            _drop_job_lock(jid)
            # Reclaim disk for the per-job _combined dir. Best-effort.
            out_dir = job.get("output_dir")
            if out_dir and _safe_rmtree(out_dir):
                dirs_removed += 1

        # Also sweep orphan sibling crawler dirs (AsyncImageCrawler writes
        # outside the _combined tree). Cheap when output/ has few entries.
        dirs_removed += _evict_orphan_output_dirs(cutoff)

        if expired or dirs_removed:
            logger.info(
                "[combined] TTL eviction: removed %d job(s), %d on-disk dir(s)",
                len(expired),
                dirs_removed,
            )
