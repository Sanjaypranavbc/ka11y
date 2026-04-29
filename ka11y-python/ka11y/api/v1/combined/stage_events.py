"""
ka11y/api/v1/combined/stage_events.py
=======================================
Stage lifecycle helpers — record stage status and broadcast SSE events.

Every audit stage calls _stage_start() on entry and either
_stage_complete() or _stage_error_and_warn() on exit.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ka11y.config.logger import setup_logger
from ka11y.utils.step_logger import append_step_log

from .constants import STAGE_WEIGHTS
from .store import _broadcast, _jobs

logger = setup_logger(name="KAC", tag="combined")

# Throttle stage_progress events to at most one per (job_id, stage, phase)
# every _PROGRESS_MIN_INTERVAL_S seconds to prevent SSE flooding on fast
# inner loops (e.g. OCR scanning 200+ images).
_PROGRESS_MIN_INTERVAL_S = 0.2
_progress_last_emit: dict[tuple[str, str, str], float] = {}


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


def _plan_index(job_id: str, name: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Return (index, total, weight) for `name` given the job's plan.

    index is 1-based. Returns (None, None, None) when no plan was stored
    (e.g. unit tests that never call emit_job_plan()), so older callers
    still function without the new fields.
    """
    plan = _jobs.get(job_id, {}).get("plan")
    if not plan:
        return (None, None, None)
    stages = plan.get("stages", []) or []
    total = len(stages) or None
    for i, s in enumerate(stages, 1):
        if s.get("key") == name:
            return (i, total, int(s.get("weight", 0)) or None)
    return (None, total, STAGE_WEIGHTS.get(name))


def emit_job_plan(job_id: str, active_stage_keys: list[str]) -> None:
    """Emit the stage plan for the whole job — frontend uses this to draw the bar.

    `active_stage_keys` should be the list of stage keys that will actually run,
    in execution order, derived from the audit request flags.
    """
    stages = [
        {"key": k, "weight": STAGE_WEIGHTS.get(k, 1)}
        for k in active_stage_keys
    ]
    plan = {
        "stages": stages,
        "total": len(stages),
        "weight_total": sum(s["weight"] for s in stages) or 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _jobs.setdefault(job_id, {})["plan"] = plan
    _fire_broadcast(job_id, "job_plan", {"job_id": job_id, **plan})


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
    idx, total, weight = _plan_index(job_id, name)
    payload: dict[str, Any] = {"stage_name": name, "started_at": now}
    if idx is not None:
        payload.update(index=idx, total=total, weight=weight)
    _fire_broadcast(job_id, "stage_start", payload)


def emit_stage_progress(
    job_id: str,
    name: str,
    current: int,
    total: int,
    *,
    phase: Optional[str] = None,
) -> None:
    """Sub-progress inside a stage. Throttled to _PROGRESS_MIN_INTERVAL_S per
    (job_id, stage, phase) to avoid flooding the SSE stream.

    - `current` and `total` define the inner progress bar (e.g. 17 of 38 images).
    - `phase` is an optional sub-label ("crawl", "ocr", "transcribe"…) that the
       UI displays alongside the stage name.

    Always emits on the terminal boundary (current >= total) so the UI can
    transition cleanly even when the last iteration is sub-throttle.
    """
    key = (job_id, name, phase or "")
    now_s = time.monotonic()
    last = _progress_last_emit.get(key, 0.0)
    at_end = total > 0 and current >= total
    if not at_end and (now_s - last) < _PROGRESS_MIN_INTERVAL_S:
        return
    _progress_last_emit[key] = now_s
    payload = {
        "stage_name": name,
        "current": int(current),
        "total": int(total),
    }
    if phase:
        payload["phase"] = phase
    _fire_broadcast(job_id, "stage_progress", payload)


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
    idx, total, weight = _plan_index(job_id, name)
    payload: dict[str, Any] = {
        "stage_name": name,
        "completed_at": now,
        "findings_count": findings_count,
    }
    if idx is not None:
        payload.update(index=idx, total=total, weight=weight)
    _fire_broadcast(job_id, "stage_complete", payload)
    # drop per-(job,stage,phase) throttle entries for this stage to cap memory
    _progress_last_emit.pop((job_id, name, ""), None)
    for phase in ("crawl", "ocr", "transcribe"):
        _progress_last_emit.pop((job_id, name, phase), None)


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
    idx, total, weight = _plan_index(job_id, name)
    payload: dict[str, Any] = {"stage_name": name, "error": error}
    if idx is not None:
        payload.update(index=idx, total=total, weight=weight)
    _fire_broadcast(job_id, "stage_error", payload)


def _stage_error_and_warn(job_id: str, name: str, exc: Exception | None) -> None:
    """Record a non-fatal stage failure: update stages, broadcast, log a warning."""
    msg = str(exc) if exc is not None else "unknown error"
    logger.warning(f"[combined] {name} stage error: {msg}")
    _stage_error(job_id, name, msg)
    _jobs[job_id].setdefault("warnings", []).append(f"{name}: {msg}")


def _stage_warn(job_id: str, message: str) -> None:
    """Append a degradation warning to the job without changing stage status.

    Use this for partial-success conditions (e.g. partial image set, challenge
    page detected) where the stage continues but coverage is reduced.
    """
    logger.warning(f"[combined] {message}")
    _jobs[job_id].setdefault("warnings", []).append(message)
