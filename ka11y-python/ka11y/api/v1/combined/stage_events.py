"""
ka11y/api/v1/combined/stage_events.py
=======================================
Stage lifecycle helpers — record stage status and broadcast SSE events.

Every audit stage calls _stage_start() on entry and either
_stage_complete() or _stage_error_and_warn() on exit.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from ka11y.config.logger import setup_logger
from ka11y.utils.step_logger import append_step_log

from .store import _broadcast, _jobs

logger = setup_logger(name="KAC", tag="combined")


def _fire_broadcast(job_id: str, event_type: str, data: dict) -> None:
    """Schedule an async _broadcast() call from synchronous stage-event helpers.

    Stage-event helpers (_stage_start, _stage_complete, _stage_error) are
    called from async context but are themselves synchronous so they can be
    used without await boilerplate.  We use asyncio.ensure_future() to enqueue
    the coroutine onto the running event loop without blocking.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_broadcast(job_id, event_type, data))
    except RuntimeError:
        # No running event loop (e.g. called from a thread) — best-effort only.
        logger.warning(
            f"[combined] _fire_broadcast: no running event loop; "
            f"SSE event '{event_type}' for job {job_id} will not be delivered."
        )


def _stage_start(job_id: str, name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rec = {"name": name, "status": "running", "started_at": now}
    job = _jobs[job_id]
    job["current_stage"] = name
    job.setdefault("stages", []).append(rec)
    append_step_log(
        job.get("step_log_path"),
        step=f"stage:{name}",
        status="running",
        message="Stage started",
        context={"job_id": job_id, "stage_name": name, "started_at": now},
    )
    _fire_broadcast(job_id, "stage_start", {"stage_name": name, "started_at": now})


def _stage_complete(job_id: str, name: str, findings_count: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    matched = False
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(
                status="completed", completed_at=now, findings_count=findings_count
            )
            matched = True
            break
    if not matched:
        logger.warning(
            f"[combined] _stage_complete: stage '{name}' not found in running state "
            f"for job {job_id} — SSE progress may appear stale"
        )
    append_step_log(
        _jobs[job_id].get("step_log_path"),
        step=f"stage:{name}",
        status="completed",
        message="Stage completed",
        context={
            "job_id": job_id,
            "stage_name": name,
            "completed_at": now,
            "findings_count": findings_count,
        },
    )
    _fire_broadcast(
        job_id,
        "stage_complete",
        {"stage_name": name, "completed_at": now, "findings_count": findings_count},
    )


def _stage_error(job_id: str, name: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    matched = False
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(status="error", completed_at=now, error=error)
            matched = True
            break
    if not matched:
        logger.warning(
            f"[combined] _stage_error: stage '{name}' not found in running state "
            f"for job {job_id} — stage record will not be updated"
        )
    append_step_log(
        _jobs[job_id].get("step_log_path"),
        step=f"stage:{name}",
        status="error",
        message="Stage failed",
        context={"job_id": job_id, "stage_name": name, "error": error, "completed_at": now},
    )
    _fire_broadcast(job_id, "stage_error", {"stage_name": name, "error": error})


def _stage_error_and_warn(job_id: str, name: str, exc: Exception | None) -> None:
    """Record a non-fatal stage failure: update stages, broadcast, log a warning."""
    msg = str(exc) if exc is not None else "unknown error"
    logger.warning(f"[combined] {name} stage error: {msg}")
    _stage_error(job_id, name, msg)
    _jobs[job_id].setdefault("warnings", []).append(f"{name}: {msg}")
