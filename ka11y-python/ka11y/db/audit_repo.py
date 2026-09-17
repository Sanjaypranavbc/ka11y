"""
ka11y/db/audit_repo.py
======================
The bridge from the audit pipeline to ``audit_jobs`` / ``audit_summary`` /
``audit_logs`` / ``crash_reports`` in PostgreSQL.

Every write here is best-effort, exactly like ``ka11y/store/repo.py``: a DB
error is logged and swallowed so persistence can never fail an audit. With
DATABASE_URL unset, or an anonymous caller (KA11Y_AUTH_DISABLED), every call
is a no-op — the SQLite run store remains the operational source of truth
for the job queue; this layer is the *ownership and history* record.

``job_id`` is the same UUID string the API hands out and SQLite uses as
``run_id``, so one id correlates both stores.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured, session_scope
from ka11y.db.models import AuditJob, AuditLog, AuditSummary, CrashReport, Report

logger = setup_logger(name="KAC", tag="db.audit")

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(job_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(job_id))
    except (ValueError, TypeError):
        return None


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def create_job(
    job_id: str,
    *,
    user_id: Optional[uuid.UUID],
    organization_id: Optional[uuid.UUID],
    session_id: Optional[uuid.UUID],
    target_url: str,
    crawl_depth: int,
    requested_pages: Optional[int],
) -> None:
    jid = _uuid(job_id)
    if not is_configured() or user_id is None or jid is None:
        return
    try:
        async with session_scope() as s:
            s.add(
                AuditJob(
                    id=jid,
                    user_id=user_id,
                    organization_id=organization_id,
                    session_id=session_id,
                    target_url=target_url,
                    status="queued",
                    crawl_depth=crawl_depth,
                    requested_pages=requested_pages,
                )
            )
            s.add(AuditLog(job_id=jid, user_id=user_id, event_type="JOB_CREATED", event_status="ok"))
    except Exception:  # noqa: BLE001
        logger.warning("[db.audit] create_job(%s) failed", job_id, exc_info=True)


async def _set_status(job_id: str, status: str, event: str, **fields: Any) -> Optional[AuditJob]:
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return None
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return None  # submitted anonymously / before PG existed
            job.status = status
            for k, v in fields.items():
                setattr(job, k, v)
            s.add(AuditLog(job_id=jid, user_id=job.user_id, event_type=event, event_status=status))
            return job
    except Exception:  # noqa: BLE001
        logger.warning("[db.audit] %s(%s) failed", event, job_id, exc_info=True)
        return None


async def mark_running(job_id: str, started_at: Optional[str] = None) -> None:
    await _set_status(job_id, "running", "JOB_STARTED", started_at=_parse_ts(started_at) or _now())


async def mark_cancelled(job_id: str) -> None:
    await _set_status(job_id, "cancelled", "JOB_CANCELLED", completed_at=_now())


async def mark_completed(
    job_id: str,
    *,
    summary: Optional[Dict[str, Any]],
    completed_at: Optional[str] = None,
    run_started_at: Optional[str] = None,
) -> None:
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return
    summary = summary or {}
    done = _parse_ts(completed_at) or _now()
    started = _parse_ts(run_started_at)
    duration_ms = int((done - started).total_seconds() * 1000) if started else None
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
            job.status = "completed"
            job.completed_at = done
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
            row.duration_ms = duration_ms
            s.add(
                AuditLog(
                    job_id=jid,
                    user_id=job.user_id,
                    event_type="JOB_COMPLETED",
                    event_status="completed",
                    metadata_={"score": summary.get("score"), "pages": pages},
                )
            )
    except Exception:  # noqa: BLE001
        logger.warning("[db.audit] mark_completed(%s) failed", job_id, exc_info=True)


async def mark_failed(
    job_id: str,
    *,
    stage: Optional[str],
    error_type: Optional[str],
    error_message: Optional[str],
    stack_trace: Optional[str] = None,
    error_id: Optional[str] = None,
    completed_at: Optional[str] = None,
    object_key: Optional[str] = None,
) -> None:
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            job.status = "failed"
            job.completed_at = _parse_ts(completed_at) or _now()
            s.add(
                AuditLog(
                    job_id=jid,
                    user_id=job.user_id,
                    event_type="JOB_FAILED",
                    event_status="failed",
                    message=(error_message or "")[:1000] or None,
                    metadata_={"error_id": error_id, "stage": stage},
                )
            )
            s.add(
                CrashReport(
                    job_id=jid,
                    user_id=job.user_id,
                    service="ka11y-python",
                    stage=(stage or "")[:100] or None,
                    error_type=(error_type or "")[:255] or None,
                    error_message=error_message,
                    stack_trace=stack_trace,
                    metadata_={"error_id": error_id, "s3_key": object_key}
                    if (error_id or object_key)
                    else None,
                )
            )
    except Exception:  # noqa: BLE001
        logger.warning("[db.audit] mark_failed(%s) failed", job_id, exc_info=True)


async def get_owner(job_id: str) -> Optional[Dict[str, Any]]:
    """{user_id, organization_id} of a job, or None if unknown to PG."""
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return None
    async with session_scope() as s:
        job = await s.get(AuditJob, jid)
        if job is None:
            return None
        return {
            "user_id": job.user_id,
            "organization_id": job.organization_id,
            "session_id": job.session_id,
        }


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
    """One ``reports`` row per generated file (spec §13). Upserts on
    (job, type, format) so a re-upload replaces the pointer."""
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return
    try:
        async with session_scope() as s:
            job = await s.get(AuditJob, jid)
            if job is None:
                return
            row = (
                await s.execute(
                    select(Report).where(
                        Report.job_id == jid, Report.report_type == report_type, Report.format == fmt
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = Report(
                    job_id=jid,
                    user_id=job.user_id,
                    organization_id=job.organization_id,
                    report_type=report_type,
                    format=fmt,
                    s3_key=key,
                )
                s.add(row)
            row.s3_bucket = bucket
            row.s3_key = key
            row.file_size_bytes = size
            row.status = status
            s.add(
                AuditLog(
                    job_id=jid,
                    user_id=job.user_id,
                    event_type="REPORT_GENERATED",
                    event_status=status,
                    metadata_={"format": fmt, "type": report_type, "key": key},
                )
            )
    except Exception:  # noqa: BLE001
        logger.warning("[db.audit] add_report(%s, %s) failed", job_id, fmt, exc_info=True)


async def list_reports(job_id: str) -> List[Dict[str, Any]]:
    jid = _uuid(job_id)
    if not is_configured() or jid is None:
        return []
    async with session_scope() as s:
        rows = (
            await s.execute(select(Report).where(Report.job_id == jid).order_by(Report.created_at))
        ).scalars().all()
        return [
            {
                "report_id": str(r.id),
                "type": r.report_type,
                "format": r.format,
                "status": r.status,
                "bucket": r.s3_bucket,
                "key": r.s3_key,
                "size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


async def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    rid = _uuid(report_id)
    if not is_configured() or rid is None:
        return None
    async with session_scope() as s:
        r = await s.get(Report, rid)
        if r is None:
            return None
        return {
            "report_id": str(r.id),
            "job_id": str(r.job_id),
            "user_id": r.user_id,
            "organization_id": r.organization_id,
            "type": r.report_type,
            "format": r.format,
            "bucket": r.s3_bucket,
            "key": r.s3_key,
        }


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
    """Spec §27: audit_jobs LEFT JOIN audit_summary, newest first."""
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
                    "duration_ms": summ.duration_ms if summ else None,
                    "user_id": str(job.user_id),
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                    "created_at": job.created_at.isoformat(),
                    "updated_at": job.updated_at.isoformat(),
                }
            )
    return out
