"""
ka11y/api/v1/combined/stage_events.py
=======================================
Stage lifecycle helpers — record stage status and broadcast SSE events.

Every audit stage calls _stage_start() on entry and either
_stage_complete() or _stage_error_and_warn() on exit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ka11y.config.logger import setup_logger

from .store import _broadcast, _jobs

logger = setup_logger(name="KAC", tag="combined")


def _stage_start(job_id: str, name: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    rec = {"name": name, "status": "running", "started_at": now}
    job = _jobs[job_id]
    job["current_stage"] = name
    job.setdefault("stages", []).append(rec)
    _broadcast(job_id, "stage_start", {"stage_name": name, "started_at": now})


def _stage_complete(job_id: str, name: str, findings_count: int = 0) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(
                status="completed", completed_at=now, findings_count=findings_count
            )
            break
    _broadcast(
        job_id,
        "stage_complete",
        {"stage_name": name, "completed_at": now, "findings_count": findings_count},
    )


def _stage_error(job_id: str, name: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for s in _jobs[job_id].get("stages", []):
        if s["name"] == name and s["status"] == "running":
            s.update(status="error", completed_at=now, error=error)
            break
    _broadcast(job_id, "stage_error", {"stage_name": name, "error": error})


def _stage_error_and_warn(job_id: str, name: str, exc: Exception | None) -> None:
    """Record a non-fatal stage failure: update stages, broadcast, log a warning."""
    msg = str(exc) if exc is not None else "unknown error"
    logger.warning(f"[combined] {name} stage error: {msg}")
    _stage_error(job_id, name, msg)
    _jobs[job_id].setdefault("warnings", []).append(f"{name}: {msg}")