"""
a11y/api/v1/combined/dispatcher.py
==================================
Durable, crash-safe job dispatcher (P4).

The POST handler no longer runs jobs directly. Instead it INSERTs a ``runs`` row
with ``status='queued'`` and a hot ``_jobs`` cache entry, then wakes this
dispatcher. The dispatcher is the single execution authority:

* On boot it requeues any run left ``running`` by a crash (``repo.requeue_running``)
  and rebuilds their hot cache entries, so an interrupted audit resumes.
* It drains ``queued`` rows in FIFO order, bounded by ``A11Y_MAX_CONCURRENT_JOBS``.
* Each launched job runs through :func:`runner._run_job_body` (the dispatcher,
  not the per-job semaphore, enforces the concurrency cap here).

If the store never initialised (DB down), :func:`enqueue` falls back to the
legacy in-process ``create_task(_run_job(...))`` path so audits still run.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from a11y.config.logger import setup_logger
from a11y.store import repo

from .models import CombinedRequest
from .store import _jobs

logger = setup_logger(name="AC", tag="combined.dispatcher")

_MAX_CONCURRENT_JOBS = int(os.environ.get("A11Y_MAX_CONCURRENT_JOBS", "4"))

_inflight: set[asyncio.Task] = set()
_dispatcher_running = False
_wakeup: Optional[asyncio.Event] = None
_wakeup_loop: Any = None


def _get_wakeup() -> asyncio.Event:
    global _wakeup, _wakeup_loop
    loop = asyncio.get_event_loop()
    if _wakeup is None or _wakeup_loop is not loop:
        _wakeup = asyncio.Event()
        _wakeup_loop = loop
    return _wakeup


def is_running() -> bool:
    return _dispatcher_running


def notify() -> None:
    """Wake the dispatcher to look for newly-queued work (best-effort)."""
    try:
        _get_wakeup().set()
    except Exception:  # noqa: BLE001
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload_from_row(row: Dict[str, Any]) -> Optional[CombinedRequest]:
    try:
        params = json.loads(row.get("params_json") or "{}")
        return CombinedRequest(**params)
    except Exception:  # noqa: BLE001
        logger.warning("[dispatcher] bad params for run %s", row.get("run_id"), exc_info=True)
        return None


def _ensure_hot_entry(run_id: str, row: Dict[str, Any], payload: CombinedRequest) -> None:
    """Make sure a hot cache entry exists (rebuilds it after a crash/restart)."""
    if run_id in _jobs:
        return
    _jobs[run_id] = {
        "job_id": run_id,
        "status": "queued",
        "url": row.get("url") or str(payload.url),
        "submitted_at": row.get("submitted_at") or _now(),
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


async def enqueue(run_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None) -> None:
    """Persist a queued run and wake the dispatcher.

    Fallback: if the dispatcher isn't running (store failed to init), launch the
    job directly so audits never silently stall.
    """
    await repo.create_run(
        run_id=run_id,
        url=str(payload.url),
        status="queued",
        lang_requested=payload.lang,
        wcag_level=payload.wcag_level,
        params=payload.model_dump(mode="json"),
        max_depth=payload.max_depth,
        max_pages=payload.max_pages,
        submitted_at=_jobs.get(run_id, {}).get("submitted_at") or _now(),
    )
    repo.insert_event(run_id, "queued", {"url": str(payload.url)})

    if not _dispatcher_running:
        # Legacy path — keep audits running even with the store unavailable.
        from .runner import _run_job

        asyncio.create_task(_run_job(run_id, payload, filter_rule))
        return
    notify()


async def _run_tracked(run_id: str, payload: CombinedRequest, filter_rule: Optional[str]) -> None:
    from .runner import _run_job_body

    try:
        await _run_job_body(run_id, payload, filter_rule)
    except Exception:  # noqa: BLE001
        logger.exception("[dispatcher] job %s crashed", run_id)


async def _drain() -> None:
    free = _MAX_CONCURRENT_JOBS - len(_inflight)
    if free <= 0:
        return
    rows = await repo.next_queued(free)
    for row in rows:
        run_id = row["run_id"]
        hot = _jobs.get(run_id)
        if hot and hot.get("status") == "running":
            continue
        payload = _payload_from_row(row)
        if payload is None:
            await repo.update_run(
                run_id, status="failed", error_stage="dispatch", error_id="bad_params",
                completed_at=_now(),
            )
            continue
        _ensure_hot_entry(run_id, row, payload)
        # Claim the row synchronously so the next tick won't re-pick it.
        await repo.update_run(run_id, status="running")
        if run_id in _jobs:
            _jobs[run_id]["status"] = "running"
        task = asyncio.create_task(_run_tracked(run_id, payload, None))
        _inflight.add(task)
        task.add_done_callback(_inflight.discard)


async def run_dispatcher() -> None:
    """Background task: crash-recover, then drain the queue forever."""
    global _dispatcher_running
    _dispatcher_running = True
    logger.info("[dispatcher] started (max_concurrent=%d)", _MAX_CONCURRENT_JOBS)
    try:
        try:
            requeued = await repo.requeue_running()
            if requeued:
                logger.info("[dispatcher] crash recovery requeued %d run(s)", len(requeued))
        except Exception:  # noqa: BLE001
            logger.warning("[dispatcher] crash recovery failed", exc_info=True)

        while True:
            try:
                await _drain()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.warning("[dispatcher] drain failed", exc_info=True)
            try:
                await asyncio.wait_for(_get_wakeup().wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            finally:
                _get_wakeup().clear()
    except asyncio.CancelledError:
        raise
    finally:
        _dispatcher_running = False
        logger.info("[dispatcher] stopped")
