"""
ka11y/storage/jobstate.py
=========================
Job state in object storage — the run store while PostgreSQL is switched off.

One small JSON document per job, next to its artifacts (same key layout as
``storage/keys.py``)::

    anonymous/jobs/{job_id}/state.json     status, stages, progress, errors, params
    anonymous/jobs/{job_id}/cancel.json    present = cancellation requested
    anonymous/jobs/{job_id}/reports/report.json   the full report (uploader.py)

Who writes what
    API (submit)   state.json  status=queued, with the request params
    API (cancel)   cancel.json, and state.json → cancelled while still queued
    worker         state.json on every stage event (throttled) and at the end
    runner         reports/report.json via ``uploader.upload_job_artifacts``

Reads are plain GETs: the API's status poll and SSE stream read state.json;
the worker reads it once per delivery for idempotency and the cancel flag at
its checkpoints. Last writer wins — the only concurrent writers are the API's
cancel (which uses its own object) and the worker.

Backend: S3 when ``KA11Y_S3_BUCKET`` is set, otherwise the local artifact
directory (``KA11Y_ARTIFACT_DIR``), which docker-compose bind-mounts into
both the API and the worker container. Every function degrades: a storage
error is logged and returns ``False``/``None``; only the submit path turns
that into a 503, because without state.json there is no job.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.storage import keys
from ka11y.storage.backends import get_store

logger = setup_logger(name="KAC", tag="storage.jobstate")

STATE_FILE = "state.json"
CANCEL_FILE = "cancel.json"

#: Statuses after which a job never runs again.
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

#: Hot-cache (``store._jobs``) fields copied into state.json, in this order.
#: ``result`` is deliberately absent: the full report is its own object.
_STATE_FIELDS = (
    "job_id",
    "status",
    "url",
    "submitted_at",
    "lang",
    "completed_at",
    "run_started_at",
    "error",
    "error_id",
    "error_code",
    "error_stage",
    "current_stage",
    "stages",
    "warnings",
    "plan",
    "output_dir",
    "params",
    "attempt",
    "worker_pid",
    "rerun_of",
    "artifacts",
)

#: Hot-cache fields that are in-process only and must never leave the worker.
_PRIVATE_PREFIX = "_"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


async def _state_key(job_id: str) -> str:
    return f"{await keys.job_prefix(job_id)}/{STATE_FILE}"


async def _cancel_key(job_id: str) -> str:
    return f"{await keys.job_prefix(job_id)}/{CANCEL_FILE}"


def storage_available() -> bool:
    """False when KA11Y_STORAGE_BACKEND=off (then nothing can be queued)."""
    return get_store() is not None


# ── snapshots ────────────────────────────────────────────────────────────────


def snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """The public, JSON-safe view of a hot-cache entry: the fields the status
    endpoint serves, plus the report summary (never the report itself)."""
    out: Dict[str, Any] = {}
    for field in _STATE_FIELDS:
        if field.startswith(_PRIVATE_PREFIX):
            continue
        value = job.get(field)
        if value is None:
            continue
        if field in ("stages", "warnings"):
            value = [dict(s) if isinstance(s, dict) else s for s in value]
        out[field] = value
    result = job.get("result")
    if isinstance(result, dict) and isinstance(result.get("summary"), dict):
        out["result_summary"] = dict(result["summary"])
        out["has_report"] = True
    out.setdefault("stages", [])
    out.setdefault("warnings", [])
    out["updated_at"] = _now()
    return out


def new_state(
    job_id: str,
    *,
    url: str,
    lang: str,
    params: Dict[str, Any],
    submitted_at: Optional[str] = None,
    rerun_of: Optional[str] = None,
) -> Dict[str, Any]:
    """The state.json a freshly submitted job starts with."""
    state: Dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "url": url,
        "submitted_at": submitted_at or _now(),
        "lang": lang,
        "completed_at": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
        "params": params,
        "attempt": 0,
    }
    if rerun_of:
        state["rerun_of"] = rerun_of
    return state


def to_hot_entry(state: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild the in-memory entry the runner expects from a state document."""
    return {
        "job_id": state["job_id"],
        "status": state.get("status", "queued"),
        "url": state.get("url", ""),
        "submitted_at": state.get("submitted_at") or _now(),
        "lang": state.get("lang", "auto"),
        "_created_at": time.time(),
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
        "params": state.get("params") or {},
        "attempt": state.get("attempt", 0),
        "rerun_of": state.get("rerun_of"),
    }


# ── writes ───────────────────────────────────────────────────────────────────


async def put_state(job_id: str, state: Dict[str, Any]) -> bool:
    """Write state.json. Returns False (logged) when storage is off or failed."""
    store = get_store()
    if store is None:
        logger.warning("[jobstate] job %s: storage is off; state not written", job_id)
        return False
    try:
        doc = dict(state)
        doc.setdefault("job_id", job_id)
        doc["updated_at"] = _now()
        await store.put_bytes(await _state_key(job_id), _json(doc), content_type="application/json")
        return True
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: state write failed", job_id, exc_info=True)
        return False


async def update_state(job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    """Read-modify-write a few fields. Returns the new document, or None when
    the job is unknown or storage failed."""
    current = await get_state(job_id)
    if current is None:
        return None
    current.update(fields)
    ok = await put_state(job_id, current)
    return current if ok else None


async def request_cancel(job_id: str) -> bool:
    """Leave the cancel marker the runner checks at its checkpoints."""
    store = get_store()
    if store is None:
        return False
    try:
        await store.put_bytes(
            await _cancel_key(job_id), _json({"job_id": job_id, "requested_at": _now()}),
            content_type="application/json",
        )
        return True
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: cancel marker write failed", job_id, exc_info=True)
        return False


# ── reads ────────────────────────────────────────────────────────────────────


async def get_state(job_id: str) -> Optional[Dict[str, Any]]:
    store = get_store()
    if store is None:
        return None
    try:
        raw = await store.get_bytes(await _state_key(job_id))
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: state read failed", job_id, exc_info=True)
        return None
    if not raw:
        return None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("[jobstate] job %s: state.json is not valid JSON", job_id)
        return None
    return doc if isinstance(doc, dict) else None


async def get_status(job_id: str) -> Optional[str]:
    state = await get_state(job_id)
    return state.get("status") if state else None


async def is_cancel_requested(job_id: str) -> bool:
    store = get_store()
    if store is None:
        return False
    try:
        return await store.exists(await _cancel_key(job_id))
    except Exception:  # noqa: BLE001
        logger.debug("[jobstate] job %s: cancel check failed", job_id, exc_info=True)
        return False


async def get_report(job_id: str) -> Optional[Dict[str, Any]]:
    """The full report the runner uploaded on completion (reports/report.json)."""
    store = get_store()
    if store is None:
        return None
    try:
        prefix = await keys.job_prefix(job_id)
        raw = await store.get_bytes(keys.report_key(prefix, "report.json"))
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: report read failed", job_id, exc_info=True)
        return None
    if not raw:
        return None
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("[jobstate] job %s: report.json is not valid JSON", job_id)
        return None
    return doc if isinstance(doc, dict) else None


async def list_job_ids(limit: int = 200) -> List[str]:
    """Job ids that have a state.json, newest first by key listing order is
    not guaranteed, so callers sort by ``submitted_at`` after reading."""
    store = get_store()
    if store is None:
        return []
    try:
        found = await store.list_keys("anonymous/jobs/")
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] listing failed", exc_info=True)
        return []
    ids: List[str] = []
    for key in found:
        parts = key.split("/")
        if len(parts) == 4 and parts[3] == STATE_FILE:
            ids.append(parts[2])
    return ids[: max(0, limit)]


# ── progress sink (worker side) ──────────────────────────────────────────────

#: Seconds between two state writes for the same job on noisy events
#: (per-image ``stage_progress``). Stage boundaries and terminal events
#: always write.
PROGRESS_MIN_INTERVAL_S = 2.0
_ALWAYS_WRITE = frozenset(
    {"job_plan", "stage_start", "stage_complete", "stage_error", "job_state",
     "job_complete", "job_failed", "job_cancelled"}
)
_last_write: Dict[str, float] = {}


async def progress_sink(job_id: str, event_type: str, data: Dict[str, Any]) -> None:
    """``store.add_broadcast_sink`` callback: mirror the hot-cache entry to
    state.json whenever the runner broadcasts an SSE event, so an API in
    another process can serve live progress."""
    from ka11y.api.v1.combined.store import _jobs

    job = _jobs.get(job_id)
    if job is None:
        return
    now = time.monotonic()
    if event_type not in _ALWAYS_WRITE and now - _last_write.get(job_id, 0.0) < PROGRESS_MIN_INTERVAL_S:
        return
    _last_write[job_id] = now
    if event_type in ("job_complete", "job_failed", "job_cancelled"):
        _last_write.pop(job_id, None)
    await put_state(job_id, snapshot(job))
