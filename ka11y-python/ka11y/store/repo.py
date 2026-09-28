"""
ka11y/store/repo.py
===================
The one persistence API for audit runs, on PostgreSQL.

Until 2026-09-28 every run was written twice: a ``runs`` row (+ report,
findings, events, timings, assets, verdicts) in a SQLite file, and an
``audit_jobs`` ownership row (+ summary, logs, crash report, report files)
in PostgreSQL, through two modules with overlapping ``mark_*`` functions.
This module is the merge: ``audit_jobs`` is the queue row and the run
record, and each lifecycle transition writes the job, its summary and its
event-log row in a single transaction.

Three flavours of call:

* **Hot-path writes** (``mark_*``, ``save_*``, ``add_report``,
  ``insert_event``) are wrapped: a DB error is logged and swallowed so an
  audit never fails because persistence hiccuped.
* **``create_run`` is the one write that raises.** The ``audit_jobs`` row
  *is* the queue: if it is not written the dispatcher never sees the job, so
  the caller (``dispatcher.enqueue`` → ``routes._admit_run``) must know and
  answer 503 instead of returning a job id that will sit 'queued' forever.
* **Reads** (``get_run``, ``list_runs``, ``get_report`` …) propagate errors
  to the API layer, which turns them into a normal HTTP error. A job id
  that is not a UUID is simply unknown.

Job ids are the ``uuid4`` strings the API hands out; ``run_id`` and
``job_id`` name the same value (the older callers say ``run_id``).
"""

from __future__ import annotations

import json
import os
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured, session_scope
from ka11y.db.models import (
    AuditAsset,
    AuditFail,
    AuditJob,
    AuditLog,
    AuditPage,
    AuditResult,
    AuditSummary,
    CrashReport,
    FindingReview,
    Report,
    StageTiming,
)
from ka11y.store import writer

logger = setup_logger(name="KAC", tag="store.repo")

# Event codes (audit_logs.event_type). The admin console keys on these.
JOB_CREATED = "JOB_CREATED"
JOB_STARTED = "JOB_STARTED"
JOB_COMPLETED = "JOB_COMPLETED"
JOB_FAILED = "JOB_FAILED"
JOB_CANCELLED = "JOB_CANCELLED"
REPORT_GENERATED = "REPORT_GENERATED"
FINDING_REVIEWED = "FINDING_REVIEWED"

# rules.yml severities → spec severities
_SEVERITY_ALIAS = {
    "critical": "critical",
    "serious": "serious",
    "high": "serious",
    "moderate": "moderate",
    "medium": "moderate",
    "minor": "minor",
    "low": "minor",
}

_TERMINAL = ("completed", "failed", "cancelled")

_not_configured_warned = False


# ── helpers ──────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(job_id: Any) -> Optional[uuid.UUID]:
    if isinstance(job_id, uuid.UUID):
        return job_id
    try:
        return uuid.UUID(str(job_id))
    except (ValueError, TypeError, AttributeError):
        return None


def _require_uuid(job_id: Any) -> uuid.UUID:
    jid = _uuid(job_id)
    if jid is None:
        raise ValueError(f"job id {job_id!r} is not a UUID")
    return jid


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _ms_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[int]:
    if a is None or b is None:
        return None
    return int((b - a).total_seconds() * 1000)


def _ready(what: str) -> bool:
    """False (with one warning) when DATABASE_URL is unset."""
    global _not_configured_warned
    if is_configured():
        return True
    if not _not_configured_warned:
        _not_configured_warned = True
        logger.warning("[store] DATABASE_URL is not set; %s and every other run write is a no-op", what)
    return False


def _log(session, job: AuditJob, event_type: str, status: Optional[str], *,
         message: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
    session.add(
        AuditLog(
            job_id=job.id,
            user_id=job.user_id,
            event_type=event_type,
            event_status=status,
            message=(message or "")[:1000] or None,
            metadata_=metadata or None,
        )
    )


def _pid() -> int:
    return os.getpid()


def _run_dict(job: AuditJob) -> Dict[str, Any]:
    """The run row in the shape the API layer has always consumed."""
    return {
        "run_id": str(job.id),
        "url": job.target_url,
        "status": job.status,
        "lang_requested": job.lang_requested,
        "lang_resolved": job.lang_resolved,
        "wcag_level": job.wcag_level,
        "params": dict(job.params or {}),
        "max_depth": job.crawl_depth,
        "max_pages": job.requested_pages,
        "submitted_at": _iso(job.created_at),
        "run_started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "queue_wait_ms": job.queue_wait_ms,
        "wall_ms": job.wall_ms,
        "error_id": job.error_id,
        "error_stage": job.error_stage,
        "summary": dict(job.summary) if job.summary else None,
        "attempt": job.attempt or 0,
        "worker_pid": job.worker_pid,
        "output_dir": job.output_dir,
        "user_id": str(job.user_id) if job.user_id else None,
        "organization_id": str(job.organization_id) if job.organization_id else None,
    }


# ── run lifecycle ────────────────────────────────────────────────────────────


async def create_run(
    *,
    run_id: str,
    url: str,
    status: str,
    lang_requested: Optional[str],
    wcag_level: Optional[str],
    params: Dict[str, Any],
    max_depth: Optional[int],
    max_pages: Optional[int],
    submitted_at: Optional[str],
    user_id: Optional[uuid.UUID] = None,
    organization_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
) -> None:
    """Insert the queue row (ownership included). Raises on failure — see the
    module docstring. Re-submitting an existing id replaces the row."""
    jid = _require_uuid(run_id)
    submitted = _parse_ts(submitted_at) or _now()
    async with session_scope() as s:
        job = await s.get(AuditJob, jid)
        if job is None:
            job = AuditJob(id=jid, created_at=submitted)
            s.add(job)
        job.user_id = user_id
        job.organization_id = organization_id
        job.session_id = session_id
        job.target_url = url
        job.status = status
        job.crawl_depth = int(max_depth or 0)
        job.requested_pages = max_pages
        job.lang_requested = lang_requested
        job.wcag_level = wcag_level
        job.params = json.loads(json.dumps(params or {}, default=str))
        job.attempt = 0
        job.error_id = None
        job.error_stage = None
        _log(s, job, JOB_CREATED, status, metadata={"url": url})


_FIELD_ALIASES = {
    "run_started_at": "started_at",
    "summary_json": "summary",
    "url": "target_url",
    "max_depth": "crawl_depth",
    "max_pages": "requested_pages",
}
_DATETIME_FIELDS = {"started_at", "completed_at"}


async def update_run(run_id: str, **fields: Any) -> None:
    """Set columns on the run row (SQLite-era field names accepted). Swallows errors."""
    if not fields or not _ready("update_run"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            for key, value in fields.items():
                col = _FIELD_ALIASES.get(key, key)
                if col in _DATETIME_FIELDS:
                    value = _parse_ts(value)
                elif col == "summary" and isinstance(value, str):
                    value = json.loads(value)
                setattr(job, col, value)
    except Exception:  # noqa: BLE001
        logger.warning("[store] update_run(%s) failed", run_id, exc_info=True)


async def mark_queued(run_id: str) -> None:
    await update_run(run_id, status="queued")


async def mark_running(run_id: str, run_started_at: Optional[str] = None, submitted_at: Optional[str] = None) -> None:
    if not _ready("mark_running"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    started = _parse_ts(run_started_at) or _now()
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            job.status = "running"
            job.started_at = started
            job.worker_pid = _pid()
            job.queue_wait_ms = _ms_between(_parse_ts(submitted_at) or job.created_at, started)
            _log(s, job, JOB_STARTED, "running")
    except Exception:  # noqa: BLE001
        logger.warning("[store] mark_running(%s) failed", run_id, exc_info=True)


async def mark_completed(
    run_id: str,
    *,
    completed_at: Optional[str] = None,
    run_started_at: Optional[str] = None,
    summary: Optional[Dict[str, Any]],
    output_dir: Optional[str] = None,
) -> None:
    """Terminal 'completed': job row, typed counts in audit_summary, event."""
    if not _ready("mark_completed"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    summary = dict(summary or {})
    done = _parse_ts(completed_at) or _now()
    pages = int(summary.get("page_count") or 0)
    sev = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for key, n in (summary.get("by_severity") or {}).items():
        mapped = _SEVERITY_ALIAS.get(str(key).lower())
        if mapped:
            sev[mapped] += int(n or 0)
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            started = _parse_ts(run_started_at) or job.started_at
            job.status = "completed"
            job.completed_at = done
            job.wall_ms = _ms_between(started, done)
            job.summary = json.loads(json.dumps(summary, default=str))
            job.output_dir = output_dir
            job.actual_pages = pages or job.actual_pages
            row = (
                await s.execute(select(AuditSummary).where(AuditSummary.job_id == jid))
            ).scalar_one_or_none()
            if row is None:
                row = AuditSummary(job_id=jid)
                s.add(row)
            row.total_pages = pages
            row.total_fails = int(summary.get("violations") or 0)
            row.failed_count = int(summary.get("violations") or 0)
            row.passed_count = int(summary.get("passes") or 0)
            row.needs_review_count = int(summary.get("needs_review") or 0)
            row.critical_count = sev["critical"]
            row.serious_count = sev["serious"]
            row.moderate_count = sev["moderate"]
            row.minor_count = sev["minor"]
            row.duration_ms = job.wall_ms
            _log(s, job, JOB_COMPLETED, "completed",
                 metadata={"score": summary.get("score"), "pages": pages,
                           "violations": row.total_fails, "needs_review": row.needs_review_count})
    except Exception:  # noqa: BLE001
        logger.warning("[store] mark_completed(%s) failed", run_id, exc_info=True)


async def mark_failed(
    run_id: str,
    *,
    completed_at: Optional[str] = None,
    run_started_at: Optional[str] = None,
    error_id: Optional[str] = None,
    error_stage: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    stack_trace: Optional[str] = None,
    object_key: Optional[str] = None,
) -> None:
    """Terminal 'failed': job row, event, and a crash_reports row when the
    caller knows what went wrong (error_type / message / trace)."""
    if not _ready("mark_failed"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    done = _parse_ts(completed_at) or _now()
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            started = _parse_ts(run_started_at) or job.started_at
            job.status = "failed"
            job.completed_at = done
            job.wall_ms = _ms_between(started, done)
            job.error_id = error_id
            job.error_stage = error_stage
            _log(s, job, JOB_FAILED, "failed", message=error_message,
                 metadata={"error_id": error_id, "stage": error_stage})
            if error_type or error_message or stack_trace:
                s.add(
                    CrashReport(
                        job_id=jid,
                        user_id=job.user_id,
                        service="ka11y-python",
                        stage=(error_stage or "")[:100] or None,
                        error_type=(error_type or "")[:255] or None,
                        error_message=error_message,
                        stack_trace=stack_trace,
                        metadata_={"error_id": error_id, "s3_key": object_key}
                        if (error_id or object_key)
                        else None,
                    )
                )
    except Exception:  # noqa: BLE001
        logger.warning("[store] mark_failed(%s) failed", run_id, exc_info=True)


async def mark_cancelled(run_id: str, completed_at: Optional[str] = None) -> None:
    if not _ready("mark_cancelled"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            job.status = "cancelled"
            job.completed_at = _parse_ts(completed_at) or _now()
            _log(s, job, JOB_CANCELLED, "cancelled")
    except Exception:  # noqa: BLE001
        logger.warning("[store] mark_cancelled(%s) failed", run_id, exc_info=True)


# ── report + findings + pages ────────────────────────────────────────────────


def _compress_report(report: Dict[str, Any]) -> tuple:
    """Pure CPU: serialize + zlib a report. Top-level + picklable so it can run
    in the shared ProcessPoolExecutor for large multi-page reports without
    blocking the event loop."""
    raw = json.dumps(report, default=str, ensure_ascii=False).encode("utf-8")
    return zlib.compress(raw, level=6), len(raw)


async def save_report(run_id: str, report: Dict[str, Any]) -> None:
    if not _ready("save_report"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        from ka11y.store.cpu_pool import run_cpu

        comp, raw_len = await run_cpu(_compress_report, report)
        async with session_scope() as s:
            stmt = pg_insert(AuditResult).values(
                job_id=jid, report_zlib=comp, bytes_raw=raw_len, bytes_stored=len(comp), created_at=_now()
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[AuditResult.job_id],
                set_={
                    "report_zlib": stmt.excluded.report_zlib,
                    "bytes_raw": stmt.excluded.bytes_raw,
                    "bytes_stored": stmt.excluded.bytes_stored,
                    "created_at": stmt.excluded.created_at,
                },
            )
            await s.execute(stmt)
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_report(%s) failed", run_id, exc_info=True)


def _finding_rows(jid: uuid.UUID, report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten violations + needs_review for the admin console. Passes stay
    in the report JSON: they are the bulk of every run and nothing queries them."""
    rows: List[Dict[str, Any]] = []
    for key, default_status in (("violations", "fail"), ("needs_review", "needs_review")):
        for f in report.get(key, []) or []:
            el = f.get("element") or {}
            selector = el.get("selector") or el.get("target")
            if isinstance(selector, list):
                selector = json.dumps(selector)
            status = f.get("status") or default_status
            rows.append(
                {
                    "job_id": jid,
                    "page_url": el.get("page_url") or f.get("page_url"),
                    "wcag_sc": (f.get("wcag_sc") or None),
                    "level": (f.get("level") or None),
                    "status": status,
                    "needs_review": status == "needs_review",
                    "source": f.get("source") or ("axe" if f.get("axe_rule_id") else "python"),
                    "reason_code": (f.get("reason_code") or None),
                    "severity": (f.get("severity") or None),
                    "selector": selector,
                    "description": (f.get("reason") or f.get("description") or None),
                    "recommendation": (f.get("fix") or f.get("recommendation") or None),
                    "element": json.loads(json.dumps(el, default=str)) if el else None,
                }
            )
    return rows


async def save_findings(run_id: str, report: Dict[str, Any]) -> None:
    if not _ready("save_findings"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        rows = _finding_rows(jid, report)
        async with session_scope() as s:
            await s.execute(delete(AuditFail).where(AuditFail.job_id == jid))
            if rows:
                await s.execute(pg_insert(AuditFail), rows)
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_findings(%s) failed", run_id, exc_info=True)


async def save_pages(run_id: str, pages: List[Dict[str, Any]]) -> None:
    if not pages or not _ready("save_pages"):
        return
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        rows = [
            {
                "job_id": jid,
                "url": p.get("page_url") or p.get("url"),
                "depth": p.get("depth"),
                "status_code": p.get("http_status"),
                "crawl_ms": p.get("crawl_ms"),
                "snapshot_ref": p.get("snapshot_ref"),
                "scan_status": "completed",
            }
            for p in pages
            if (p.get("page_url") or p.get("url"))
        ]
        if not rows:
            return
        async with session_scope() as s:
            await s.execute(delete(AuditPage).where(AuditPage.job_id == jid))
            await s.execute(pg_insert(AuditPage), rows)
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_pages(%s) failed", run_id, exc_info=True)


# ── events / telemetry (fire-and-forget) ─────────────────────────────────────


def insert_event(run_id: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Durable lifecycle/SSE event. Fire-and-forget — safe from any thread."""
    jid = _uuid(run_id)
    if jid is None:
        return
    try:
        writer.enqueue(
            AuditLog,
            {
                "job_id": jid,
                "event_type": str(event)[:100],
                "event_status": None,
                "metadata_": json.loads(json.dumps(data or {}, default=str)) or None,
                "created_at": _now(),
            },
        )
    except Exception:  # noqa: BLE001
        pass


def insert_timing(row: Dict[str, Any]) -> None:
    """Insert one stage_timings row. Fire-and-forget; never raises."""
    jid = _uuid(row.get("run_id") or row.get("job_id"))
    if jid is None or not row.get("stage"):
        return
    try:
        extra = row.get("extra")
        writer.enqueue(
            StageTiming,
            {
                "job_id": jid,
                "page_url": row.get("page_url"),
                "depth": row.get("depth"),
                "stage": str(row.get("stage"))[:100],
                "sub_stage": (str(row["sub_stage"])[:100] if row.get("sub_stage") else None),
                "rule": (str(row["rule"])[:100] if row.get("rule") else None),
                "duration_ms": row.get("duration_ms"),
                "item_count": row.get("item_count"),
                "status": (str(row["status"])[:20] if row.get("status") else None),
                "error": row.get("error"),
                "extra": json.loads(json.dumps(extra, default=str)) if extra else None,
                "ts": _parse_ts(row.get("ts")) or _now(),
            },
        )
    except Exception:  # noqa: BLE001
        pass


# ── reads (propagate errors to the API layer) ────────────────────────────────


async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return None
    async with session_scope() as s:
        job = await s.get(AuditJob, jid)
        return _run_dict(job) if job else None


async def list_runs(
    *,
    limit: int = 50,
    offset: int = 0,
    url: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not is_configured():
        return []
    stmt = select(AuditJob).order_by(AuditJob.created_at.desc()).limit(limit).offset(offset)
    if url:
        stmt = stmt.where(AuditJob.target_url.ilike(f"%{url}%"))
    if status:
        stmt = stmt.where(AuditJob.status == status)
    async with session_scope() as s:
        return [_run_dict(j) for j in (await s.execute(stmt)).scalars().all()]


async def get_report(run_id: str) -> Optional[Dict[str, Any]]:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return None
    async with session_scope() as s:
        blob = (await s.execute(select(AuditResult.report_zlib).where(AuditResult.job_id == jid))).scalar()
    if blob is None:
        return None
    try:
        return json.loads(zlib.decompress(blob).decode("utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("[store] get_report(%s) decompress failed", run_id, exc_info=True)
        return None


async def get_events(run_id: str) -> List[Dict[str, Any]]:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return []
    async with session_scope() as s:
        logs = (
            await s.execute(select(AuditLog).where(AuditLog.job_id == jid).order_by(AuditLog.id))
        ).scalars().all()
        return [
            {"event": lg.event_type, "status": lg.event_status, "message": lg.message,
             "data": dict(lg.metadata_ or {}), "ts": _iso(lg.created_at)}
            for lg in logs
        ]


async def get_timings(run_id: str) -> List[Dict[str, Any]]:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return []
    async with session_scope() as s:
        rows = (
            await s.execute(select(StageTiming).where(StageTiming.job_id == jid).order_by(StageTiming.id))
        ).scalars().all()
        return [
            {"page_url": t.page_url, "depth": t.depth, "stage": t.stage, "sub_stage": t.sub_stage,
             "rule": t.rule, "duration_ms": t.duration_ms, "item_count": t.item_count,
             "status": t.status, "error": t.error, "ts": _iso(t.ts)}
            for t in rows
        ]


# ── queue / crash recovery ───────────────────────────────────────────────────


async def requeue_running() -> List[Dict[str, Any]]:
    """On boot, move orphaned ``running`` rows back to ``queued`` (or fail them
    if they've exhausted their attempt budget). Returns the rows requeued."""
    if not is_configured():
        return []
    max_attempts = int(os.getenv("KA11Y_MAX_ATTEMPTS", "2"))
    requeued: List[Dict[str, Any]] = []
    async with session_scope() as s:
        orphans = (
            await s.execute(select(AuditJob).where(AuditJob.status.in_(("running", "queued"))))
        ).scalars().all()
        for job in orphans:
            attempt = (job.attempt or 0) + 1
            if attempt > max_attempts:
                job.status = "failed"
                job.error_stage = "crash_recovery"
                job.error_id = "max_attempts_exceeded"
                job.completed_at = _now()
                _log(s, job, JOB_FAILED, "failed", metadata={"stage": "crash_recovery", "attempt": attempt})
            else:
                job.status = "queued"
                job.attempt = attempt
                requeued.append({"run_id": str(job.id), "attempt": attempt})
    return requeued


async def next_queued(limit: int) -> List[Dict[str, Any]]:
    if limit <= 0 or not is_configured():
        return []
    async with session_scope() as s:
        jobs = (
            await s.execute(
                select(AuditJob).where(AuditJob.status == "queued").order_by(AuditJob.created_at).limit(limit)
            )
        ).scalars().all()
        return [_run_dict(j) for j in jobs]


async def count_running() -> int:
    if not is_configured():
        return 0
    async with session_scope() as s:
        n = (await s.execute(select(func.count()).select_from(AuditJob).where(AuditJob.status == "running"))).scalar()
        return int(n or 0)


async def is_cancelled(run_id: str) -> bool:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return False
    async with session_scope() as s:
        status = (await s.execute(select(AuditJob.status).where(AuditJob.id == jid))).scalar()
        return status == "cancelled"


# ── retention ────────────────────────────────────────────────────────────────


async def retention_sweep(retention_days: int) -> List[str]:
    """Delete finished runs older than *retention_days*. ON DELETE CASCADE
    clears the children. Returns the job ids removed so the caller can prune
    asset files."""
    if not is_configured():
        return []
    cutoff = _now() - timedelta(days=retention_days)
    async with session_scope() as s:
        ids = [
            str(i)
            for i in (
                await s.execute(
                    select(AuditJob.id).where(AuditJob.created_at < cutoff, AuditJob.status.in_(_TERMINAL))
                )
            ).scalars().all()
        ]
        if ids:
            await s.execute(delete(AuditJob).where(AuditJob.id.in_([uuid.UUID(i) for i in ids])))
    if ids:
        logger.info("[store] retention sweep removed %d runs", len(ids))
    return ids


# ── manual-review decisions ──────────────────────────────────────────────────


async def set_finding_review(
    *,
    run_id: str,
    finding_id: str,
    status: str,
    note: Optional[str] = None,
    reviewer: Optional[str] = None,
    wcag_sc: Optional[str] = None,
    page_url: Optional[str] = None,
) -> None:
    """Upsert a reviewer's decision (pass|violation) for one needs_review item.

    ``status='needs_review'`` clears the decision (re-opens the item)."""
    jid = _require_uuid(run_id)
    async with session_scope() as s:
        if status == "needs_review":
            await s.execute(
                delete(FindingReview).where(FindingReview.job_id == jid, FindingReview.finding_id == finding_id)
            )
        else:
            stmt = pg_insert(FindingReview).values(
                job_id=jid, finding_id=finding_id, status=status, note=note, reviewer=reviewer,
                wcag_sc=wcag_sc, page_url=page_url, updated_at=_now(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[FindingReview.job_id, FindingReview.finding_id],
                set_={"status": stmt.excluded.status, "note": stmt.excluded.note,
                      "reviewer": stmt.excluded.reviewer, "updated_at": stmt.excluded.updated_at},
            )
            await s.execute(stmt)
        job = await s.get(AuditJob, jid)
        if job is not None:
            _log(s, job, FINDING_REVIEWED, status,
                 metadata={"finding_id": finding_id, "status": status, "wcag_sc": wcag_sc, "reviewer": reviewer})


async def get_reviews(run_id: str) -> Dict[str, Dict[str, Any]]:
    """Return ``{finding_id: {status, note, reviewer, updated_at}}`` for a run."""
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return {}
    async with session_scope() as s:
        rows = (await s.execute(select(FindingReview).where(FindingReview.job_id == jid))).scalars().all()
        return {
            r.finding_id: {"finding_id": r.finding_id, "status": r.status, "note": r.note,
                           "reviewer": r.reviewer, "updated_at": _iso(r.updated_at)}
            for r in rows
        }


# ── assets ───────────────────────────────────────────────────────────────────


def _asset_dict(a: AuditAsset, *, with_keys: bool) -> Dict[str, Any]:
    d = {"id": a.id, "page_url": a.page_url, "kind": a.kind, "rel_path": a.rel_path, "sha256": a.sha256,
         "mime": a.mime, "width": a.width, "height": a.height, "bytes": a.bytes}
    if with_keys:
        d["object_key"] = a.object_key
        d["object_bucket"] = a.object_bucket
    return d


async def _assets(run_id: str, *, with_keys: bool) -> List[Dict[str, Any]]:
    jid = _uuid(run_id)
    if jid is None or not is_configured():
        return []
    async with session_scope() as s:
        rows = (
            await s.execute(select(AuditAsset).where(AuditAsset.job_id == jid).order_by(AuditAsset.id))
        ).scalars().all()
        return [_asset_dict(a, with_keys=with_keys) for a in rows]


async def query_assets_with_keys(run_id: str) -> List[Dict[str, Any]]:
    """Assets of a run including where their bytes live in object storage."""
    return await _assets(run_id, with_keys=True)


async def list_run_assets(run_id: str) -> List[Dict[str, Any]]:
    return await _assets(run_id, with_keys=False)


# ── ownership / history (spec §27) ───────────────────────────────────────────


async def get_owner(job_id: str) -> Optional[Dict[str, Any]]:
    """{user_id, organization_id, session_id} of an *owned* job. ``None`` when
    the job is unknown or was submitted anonymously — such a job is visible
    to anyone signed in, as before."""
    jid = _uuid(job_id)
    if jid is None or not is_configured():
        return None
    async with session_scope() as s:
        job = await s.get(AuditJob, jid)
        if job is None or job.user_id is None:
            return None
        return {"user_id": job.user_id, "organization_id": job.organization_id, "session_id": job.session_id}


async def list_history(
    *,
    user_id: Optional[uuid.UUID],
    organization_id: Optional[uuid.UUID],
    scope: str,
    limit: int,
    offset: int,
    status: Optional[str] = None,
    url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """audit_jobs LEFT JOIN audit_summary, newest first, for one user or org."""
    if not is_configured():
        return []
    stmt = (
        select(AuditJob, AuditSummary)
        .outerjoin(AuditSummary, AuditSummary.job_id == AuditJob.id)
        .order_by(AuditJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if scope == "org" and organization_id is not None:
        stmt = stmt.where(AuditJob.organization_id == organization_id)
    else:
        stmt = stmt.where(AuditJob.user_id == user_id)
    if status:
        stmt = stmt.where(AuditJob.status == status)
    if url:
        stmt = stmt.where(AuditJob.target_url.ilike(f"%{url}%"))

    out: List[Dict[str, Any]] = []
    async with session_scope() as s:
        for job, summ in (await s.execute(stmt)).all():
            out.append(
                {
                    "job_id": str(job.id),
                    "target_url": job.target_url,
                    "status": job.status,
                    "depth": job.crawl_depth,
                    "pages": summ.total_pages if summ else job.actual_pages,
                    "fails": summ.total_fails if summ else None,
                    "passes": summ.passed_count if summ else None,
                    "needs_review": summ.needs_review_count if summ else None,
                    "severity": {
                        "critical": summ.critical_count,
                        "serious": summ.serious_count,
                        "moderate": summ.moderate_count,
                        "minor": summ.minor_count,
                    }
                    if summ
                    else None,
                    "duration_ms": summ.duration_ms if summ else job.wall_ms,
                    "score": (job.summary or {}).get("score") if job.summary else None,
                    "user_id": str(job.user_id) if job.user_id else None,
                    "started_at": _iso(job.started_at),
                    "completed_at": _iso(job.completed_at),
                    "created_at": _iso(job.created_at),
                    "updated_at": _iso(job.updated_at),
                }
            )
    return out


# ── generated report files (spec §13) ────────────────────────────────────────


async def add_report(
    job_id: str,
    *,
    report_type: str,
    fmt: str,
    bucket: Optional[str],
    key: str,
    size: Optional[int],
    status: str = "completed",
) -> None:
    """One ``reports`` row per generated file. Upserts on (job, type, format)
    so a re-upload replaces the pointer. Swallows errors."""
    if not _ready("add_report"):
        return
    jid = _uuid(job_id)
    if jid is None:
        return
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            row = (
                await s.execute(
                    select(Report).where(Report.job_id == jid, Report.report_type == report_type, Report.format == fmt)
                )
            ).scalar_one_or_none()
            if row is None:
                row = Report(job_id=jid, user_id=job.user_id, organization_id=job.organization_id,
                             report_type=report_type, format=fmt, s3_key=key)
                s.add(row)
            row.s3_bucket = bucket
            row.s3_key = key
            row.file_size_bytes = size
            row.status = status
            _log(s, job, REPORT_GENERATED, status, metadata={"format": fmt, "type": report_type, "key": key})
    except Exception:  # noqa: BLE001
        logger.warning("[store] add_report(%s, %s) failed", job_id, fmt, exc_info=True)


async def list_reports(job_id: str) -> List[Dict[str, Any]]:
    jid = _uuid(job_id)
    if jid is None or not is_configured():
        return []
    async with session_scope() as s:
        rows = (await s.execute(select(Report).where(Report.job_id == jid).order_by(Report.created_at))).scalars().all()
        return [
            {"report_id": str(r.id), "type": r.report_type, "format": r.format, "status": r.status,
             "bucket": r.s3_bucket, "key": r.s3_key, "size_bytes": r.file_size_bytes,
             "created_at": _iso(r.created_at)}
            for r in rows
        ]


async def get_report_file(report_id: str) -> Optional[Dict[str, Any]]:
    """One ``reports`` row (a generated file's pointer) by its own id."""
    rid = _uuid(report_id)
    if rid is None or not is_configured():
        return None
    async with session_scope() as s:
        r = await s.get(Report, rid)
        if r is None:
            return None
        return {"report_id": str(r.id), "job_id": str(r.job_id), "user_id": r.user_id,
                "organization_id": r.organization_id, "type": r.report_type, "format": r.format,
                "bucket": r.s3_bucket, "key": r.s3_key}

