"""
ka11y/storage/jobstate.py
=========================
Job state in object storage — the run store while PostgreSQL is switched off.

One small JSON document per job, next to its artifacts (same key layout as
``storage/keys.py``)::

    anonymous/jobs/{job_id}/state.json     status, stages, progress, errors, params
    anonymous/jobs/{job_id}/cancel.json    present = cancellation requested
    anonymous/jobs/{job_id}/reviews.json   manual verdicts on needs_review items
    anonymous/jobs/{job_id}/reports/report.json   the full report (uploader.py)

Who writes what
    API (submit)   state.json  status=queued, with the request params
    API (cancel)   cancel.json, and state.json → cancelled while still queued
    API (review)   reviews.json (read-modify-write; one reviewer at a time)
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
REVIEWS_FILE = "reviews.json"

#: Where every job lives while there is no ownership store (PostgreSQL is
#: switched off): ``keys.job_prefix`` always answers under this root.
JOBS_ROOT = "anonymous/jobs/"

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


async def _reviews_key(job_id: str) -> str:
    return f"{await keys.job_prefix(job_id)}/{REVIEWS_FILE}"


async def _read_json(key: str, *, what: str, job_id: str) -> Optional[Any]:
    store = get_store()
    if store is None:
        return None
    try:
        raw = await store.get_bytes(key)
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: %s read failed", job_id, what, exc_info=True)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("[jobstate] job %s: %s is not valid JSON", job_id, what)
        return None


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
    doc = await _read_json(await _state_key(job_id), what="state.json", job_id=job_id)
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
    prefix = await keys.job_prefix(job_id)
    doc = await _read_json(keys.report_key(prefix, "report.json"), what="report.json", job_id=job_id)
    return doc if isinstance(doc, dict) else None


async def list_job_ids(limit: int = 200) -> List[str]:
    """Job ids that have a state.json, newest first by key listing order is
    not guaranteed, so callers sort by ``submitted_at`` after reading."""
    store = get_store()
    if store is None:
        return []
    try:
        found = await store.list_keys(JOBS_ROOT)
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] listing failed", exc_info=True)
        return []
    ids: List[str] = []
    for key in found:
        parts = key.split("/")
        if len(parts) == 4 and parts[3] == STATE_FILE:
            ids.append(parts[2])
    return ids[: max(0, limit)]


# ── history (the run store's list view) ──────────────────────────────────────

#: Parallel state.json reads while building the history list.
_LIST_CONCURRENCY = 16


def history_row(state: Dict[str, Any]) -> Dict[str, Any]:
    """The history/list shape the API layer has always served (the old
    ``repo._run_dict``), built from a state document."""
    params = state.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    job_id = state.get("job_id", "")
    return {
        "run_id": job_id,
        "job_id": job_id,
        "url": state.get("url", ""),
        "status": state.get("status", "unknown"),
        "lang_requested": state.get("lang"),
        "lang_resolved": state.get("lang_resolved"),
        "wcag_level": params.get("wcag_level"),
        "params": dict(params),
        "max_depth": params.get("max_depth"),
        "max_pages": params.get("max_pages"),
        "submitted_at": state.get("submitted_at"),
        "run_started_at": state.get("run_started_at"),
        "completed_at": state.get("completed_at"),
        "error_id": state.get("error_id"),
        "error_stage": state.get("error_stage"),
        "summary": state.get("result_summary"),
        "attempt": state.get("attempt", 0),
        "worker_pid": state.get("worker_pid"),
        "output_dir": state.get("output_dir"),
        "rerun_of": state.get("rerun_of"),
        "user_id": None,
        "organization_id": None,
    }


async def list_states(
    *,
    limit: int = 50,
    offset: int = 0,
    url: Optional[str] = None,
    status: Optional[str] = None,
    max_scan: int = 2000,
) -> List[Dict[str, Any]]:
    """History rows, newest first, from every state.json under the jobs root.

    One listing plus one GET per job (bounded by *max_scan*, read
    ``_LIST_CONCURRENCY`` at a time): fine for the few hundred jobs an
    S3-only deployment holds. Filters match the old ``repo.list_runs``:
    *url* is a case-insensitive substring, *status* an exact match."""
    import asyncio

    ids = await list_job_ids(limit=max_scan)
    if not ids:
        return []
    gate = asyncio.Semaphore(_LIST_CONCURRENCY)

    async def _one(job_id: str) -> Optional[Dict[str, Any]]:
        async with gate:
            return await get_state(job_id)

    states = [st for st in await asyncio.gather(*(_one(j) for j in ids)) if st]
    needle = (url or "").strip().lower()
    rows = []
    for st in states:
        if status and st.get("status") != status:
            continue
        if needle and needle not in str(st.get("url", "")).lower():
            continue
        rows.append(history_row(st))
    rows.sort(key=lambda r: r.get("submitted_at") or "", reverse=True)
    return rows[max(0, offset): max(0, offset) + max(0, limit)]


async def list_artifacts(job_id: str) -> List[str]:
    """Every object key stored for a job (reports, assets, raw, crash)."""
    store = get_store()
    if store is None:
        return []
    try:
        return await store.list_keys(f"{await keys.job_prefix(job_id)}/")
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: artifact listing failed", job_id, exc_info=True)
        return []


# ── manual verdicts (reviews.json) ───────────────────────────────────────────


async def get_reviews(job_id: str) -> Dict[str, Dict[str, Any]]:
    """``{finding_id: {finding_id, status, note, reviewer, updated_at, …}}``
    for a run — the shape ``report.apply_reviews`` consumes."""
    doc = await _read_json(await _reviews_key(job_id), what="reviews.json", job_id=job_id)
    if not isinstance(doc, dict):
        return {}
    return {k: v for k, v in doc.items() if isinstance(v, dict)}


async def set_review(
    job_id: str,
    finding_id: str,
    *,
    status: str,
    note: Optional[str] = None,
    reviewer: Optional[str] = None,
    wcag_sc: Optional[str] = None,
    page_url: Optional[str] = None,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Upsert a reviewer's decision (pass|violation) for one needs_review
    item; ``status='needs_review'`` clears it (re-opens the item). Returns the
    full review map after the write, or None when storage is off/failed.
    Read-modify-write on one small object: reviewers are people, so two
    verdicts on the same run never race in practice."""
    store = get_store()
    if store is None:
        logger.warning("[jobstate] job %s: storage is off; review not written", job_id)
        return None
    reviews = await get_reviews(job_id)
    if status == "needs_review":
        reviews.pop(finding_id, None)
    else:
        reviews[finding_id] = {
            "finding_id": finding_id,
            "status": status,
            "note": note,
            "reviewer": reviewer,
            "wcag_sc": wcag_sc,
            "page_url": page_url,
            "updated_at": _now(),
        }
    try:
        await store.put_bytes(await _reviews_key(job_id), _json(reviews), content_type="application/json")
    except Exception:  # noqa: BLE001
        logger.warning("[jobstate] job %s: reviews write failed", job_id, exc_info=True)
        return None
    return reviews


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
