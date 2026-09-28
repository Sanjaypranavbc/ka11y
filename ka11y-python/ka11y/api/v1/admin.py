"""
ka11y/api/v1/admin.py
=====================
Admin console API — every route requires an e-mail on KA11Y_ADMIN_EMAILS
(``require_admin``). Read-only: it aggregates what the audit engine already
records in PostgreSQL (users, organizations, audit_jobs, audit_summary,
audit_pages, audit_fails, reports, audit_logs, crash_reports, stage_timings,
user_sessions) into the shapes the console renders.

  GET /admin/overview             counters, status chart, pages audited per
                                  day (30 d), recent audits, activity,
                                  notifications
  GET /admin/audits               paged job list (?limit&offset&status&q)
  GET /admin/audits/{job_id}      one job with pages, fails, reports, log
  GET /admin/audits/{job_id}/export?format=csv|pdf|html
                                  the audit's report as a download, built
                                  from the stored report JSON on demand
  GET /admin/users                accounts with org, role, last login, audits
  GET /admin/fails                failing criteria across all runs (?days)
  GET /admin/reports              generated report files with download links
  GET /admin/system-events        job lifecycle events + crash reports
  GET /admin/settings             effective runtime configuration (read-only)
  GET /admin/metrics              run-store rollups: status counts, wall
                                  time by depth, slowest stages, failures
  GET /admin/events               Server-Sent Events: `refresh` whenever any
                                  of the tables above changes (2 s poll)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from sqlalchemy import case, func, select

from ka11y.auth.config import settings as auth_settings
from ka11y.auth.dependencies import CurrentUser, require_admin
from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured as pg_configured
from ka11y.db.engine import ping as pg_ping
from ka11y.db.engine import session_scope
from ka11y.db.models import (
    AuditFail,
    AuditJob,
    AuditLog,
    AuditPage,
    AuditSummary,
    CrashReport,
    OAuthIdentity,
    Organization,
    OrganizationMember,
    Report,
    StageTiming,
    User,
    UserSession,
    WcagRule,
)
from ka11y.store import repo as run_repo

logger = setup_logger(name="KAC", tag="admin")

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_SEVERITIES = ("critical", "serious", "moderate", "minor")
_SEVERITY_ALIAS = {
    "critical": "critical", "high": "serious", "serious": "serious",
    "medium": "moderate", "moderate": "moderate", "low": "minor", "minor": "minor",
}
_STATUS_ALIAS = {
    "queued": "queued", "pending": "queued", "running": "running",
    "completed": "completed", "failed": "failed", "cancelled": "cancelled", "canceled": "cancelled",
}


# ── small helpers ────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


def _status(value: Optional[str]) -> str:
    return _STATUS_ALIAS.get((value or "").lower(), "queued")


def _severity(value: Optional[str]) -> Optional[str]:
    return _SEVERITY_ALIAS.get((value or "").lower())


def _trend(current: int, previous: int, *, absolute: bool = False) -> Dict[str, str]:
    if absolute:
        return {"value": str(current), "direction": "up" if current > 0 else "flat"}
    if previous <= 0:
        return {"value": str(current), "direction": "up" if current > 0 else "flat"}
    pct = round((current - previous) * 100 / previous)
    return {"value": f"{abs(pct)}%", "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat")}


def _require_pg() -> None:
    if not pg_configured():
        raise HTTPException(status_code=503, detail="PostgreSQL is not configured.")


def _db_host() -> str:
    """host[:port]/db of DATABASE_URL, never the credentials."""
    try:
        parts = urlsplit(os.getenv("DATABASE_URL", ""))
        host = parts.hostname or "?"
        if parts.port:
            host += f":{parts.port}"
        return f"{host}{parts.path or ''}"
    except ValueError:
        return "?"


async def _node_healthy() -> bool:
    base = os.getenv("NODE_BASE_URL", "http://localhost:3000").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{base}/api/v1/health")
            return r.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def _rows(stmt) -> List[Any]:
    """A read that degrades to an empty list (the console must render even
    when the run store is unavailable)."""
    try:
        async with session_scope() as s:
            return list((await s.execute(stmt)).all())
    except Exception:  # noqa: BLE001
        logger.debug("[admin] store query failed", exc_info=True)
        return []


# ── jobs ─────────────────────────────────────────────────────────────────────


def _job_dict(job: AuditJob, summ: Optional[AuditSummary], email: Optional[str], org: Optional[str]) -> Dict[str, Any]:
    sev = {k: 0 for k in _SEVERITIES}
    if summ is not None:
        sev = {
            "critical": summ.critical_count or 0,
            "serious": summ.serious_count or 0,
            "moderate": summ.moderate_count or 0,
            "minor": summ.minor_count or 0,
        }
    jid = str(job.id)
    return {
        "id": jid,
        "targetHost": _host(job.target_url),
        "targetUrl": job.target_url,
        "pages": (summ.total_pages if summ and summ.total_pages else job.actual_pages) or 0,
        "fails": (summ.total_fails if summ else 0) or 0,
        "status": _status(job.status),
        "depth": job.crawl_depth or 0,
        "createdAt": _iso(job.created_at),
        "startedAt": _iso(job.started_at),
        "completedAt": _iso(job.completed_at),
        "user": email or "",
        "organization": org or "",
        "conformance": "WCAG 2.2 AA",
        "severity": sev,
        "passed": (summ.passed_count if summ else 0) or 0,
        "needsReview": (summ.needs_review_count if summ else 0) or 0,
        "durationMs": summ.duration_ms if summ else None,
        "pageList": [],
        "failList": [],
        "reports": [],
        "logs": [],
        "events": [],
        "s3Href": f"/api/v1/audits/{jid}/artifacts",
        "reportHref": "",
        "csvHref": "",
    }


def _report_dict(r: Report) -> Dict[str, Any]:
    fmt = (r.format or "json").lower()
    return {
        "id": str(r.id),
        "format": fmt if fmt in ("pdf", "csv", "json") else "json",
        "label": f"{(r.report_type or 'report').title()} ({fmt.upper()})",
        "sizeBytes": r.file_size_bytes or 0,
        "createdAt": _iso(r.created_at),
        "href": f"/api/v1/audits/{r.job_id}/reports/{r.id}/download",
    }


_EVENT_CODES = {"JOB_STARTED", "JOB_COMPLETED", "JOB_FAILED", "REPORT_GENERATED", "NEEDS_REVIEW"}


def _event_dict(log: AuditLog) -> Dict[str, Any]:
    code = log.event_type if log.event_type in _EVENT_CODES else (
        "JOB_FAILED" if "FAIL" in (log.event_type or "") else "JOB_STARTED"
    )
    msg = log.message or (log.event_type or "").replace("_", " ").title()
    return {"code": code, "at": _iso(log.created_at), "message": msg}


async def _list_jobs(
    *, limit: int, offset: int, status: Optional[str] = None, q: Optional[str] = None, job_id: Optional[uuid.UUID] = None
) -> List[Dict[str, Any]]:
    stmt = (
        select(AuditJob, AuditSummary, User.email, Organization.name)
        .outerjoin(AuditSummary, AuditSummary.job_id == AuditJob.id)
        .outerjoin(User, User.id == AuditJob.user_id)
        .outerjoin(Organization, Organization.id == AuditJob.organization_id)
        .order_by(AuditJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if job_id is not None:
        stmt = stmt.where(AuditJob.id == job_id)
    if status:
        stmt = stmt.where(AuditJob.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((AuditJob.target_url.ilike(like)) | (User.email.ilike(like)))

    async with session_scope() as s:
        rows = (await s.execute(stmt)).all()
        jobs = [_job_dict(job, summ, email, org) for job, summ, email, org in rows]
        ids = [job.id for job, *_ in rows]
        if ids:
            by_id = {j["id"]: j for j in jobs}
            reps = (
                await s.execute(select(Report).where(Report.job_id.in_(ids)).order_by(Report.created_at.desc()))
            ).scalars()
            for r in reps:
                j = by_id.get(str(r.job_id))
                if j is None:
                    continue
                d = _report_dict(r)
                j["reports"].append(d)
                if d["format"] == "csv" and not j["csvHref"]:
                    j["csvHref"] = d["href"]
                elif d["format"] in ("pdf", "json") and not j["reportHref"]:
                    j["reportHref"] = d["href"]
            logs = (
                await s.execute(select(AuditLog).where(AuditLog.job_id.in_(ids)).order_by(AuditLog.created_at))
            ).scalars()
            for log in logs:
                j = by_id.get(str(log.job_id))
                if j is not None:
                    j["events"].append(_event_dict(log))
    return jobs


async def _attach_detail(job: Dict[str, Any]) -> Dict[str, Any]:
    """Pages, per-criterion fails and the job log come from the run tables
    (same job_id); the report JSON supplies severities and rule names."""
    jid = uuid.UUID(job["id"])

    fails_by_page: Dict[str, int] = {}
    review_by_page: Dict[str, int] = {}
    for page_url, status, n in await _rows(
        select(AuditFail.page_url, AuditFail.status, func.count())
        .where(AuditFail.job_id == jid, AuditFail.status.in_(("fail", "needs_review")))
        .group_by(AuditFail.page_url, AuditFail.status)
    ):
        (fails_by_page if status == "fail" else review_by_page)[page_url or ""] = int(n)
    pages = await _rows(
        select(AuditPage.url, AuditPage.depth, AuditPage.status_code)
        .where(AuditPage.job_id == jid)
        .order_by(AuditPage.created_at, AuditPage.url)
    )
    page_list = []
    seen = set()
    for url, _depth, _status_code in pages:
        if url in seen:
            continue
        seen.add(url)
        n = fails_by_page.get(url, 0)
        page_list.append({
            "url": url,
            "fails": n,
            "status": "failed" if n else ("needsReview" if review_by_page.get(url) else "passed"),
        })
    for url in fails_by_page:  # pages the crawler table missed but findings know
        if url and url not in seen:
            page_list.append({"url": url, "fails": fails_by_page[url], "status": "failed"})
    job["pageList"] = page_list

    fail_list: Dict[str, Dict[str, Any]] = {}
    report = None
    try:
        report = await run_repo.get_report(str(jid))
    except Exception:  # noqa: BLE001
        report = None
    if report:
        for f in report.get("violations", []) or []:
            sc = str(f.get("wcag_sc") or "?")
            entry = fail_list.setdefault(sc, {
                "id": sc, "criterion": sc, "title": f.get("criterion_name") or sc,
                "severity": _severity(f.get("severity")) or "moderate", "occurrences": 0,
            })
            entry["occurrences"] += 1
    else:
        for wcag_sc, n in await _rows(
            select(AuditFail.wcag_sc, func.count())
            .where(AuditFail.job_id == jid, AuditFail.status == "fail")
            .group_by(AuditFail.wcag_sc)
            .order_by(func.count().desc())
        ):
            sc = str(wcag_sc or "?")
            fail_list[sc] = {"id": sc, "criterion": sc, "title": sc, "severity": "moderate", "occurrences": int(n)}
    if fail_list and pg_configured():
        async with session_scope() as s:
            rules = (await s.execute(select(WcagRule.rule_code, WcagRule.name))).all()
        names = {code: name for code, name in rules}
        for sc, entry in fail_list.items():
            if entry["title"] == sc and sc in names:
                entry["title"] = names[sc]
    job["failList"] = sorted(fail_list.values(), key=lambda e: -e["occurrences"])

    logs = []
    for (log,) in await _rows(select(AuditLog).where(AuditLog.job_id == jid).order_by(AuditLog.id)):
        ev = log.event_type or ""
        up = ev.upper()
        level = "error" if ("FAIL" in up or "ERROR" in up) else ("warn" if ("TIMEOUT" in up or "CANCEL" in up) else "info")
        detail = ""
        data = log.metadata_ or {}
        stage = data.get("stage") or data.get("name")
        if stage:
            detail = f" · {stage}"
        if data.get("error"):
            detail += f" · {str(data['error'])[:160]}"
        if log.message:
            detail += f" · {log.message[:160]}"
        logs.append({"at": _iso(log.created_at), "level": level, "message": f"{ev}{detail}"})
    job["logs"] = logs
    return job


# ── overview pieces ──────────────────────────────────────────────────────────


async def _stats() -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    now = _now()
    d30, d60 = now - timedelta(days=30), now - timedelta(days=60)
    async with session_scope() as s:
        async def count(stmt):
            return int((await s.execute(stmt)).scalar_one() or 0)

        users_total = await count(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
        users_30 = await count(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.created_at >= d30)
        )
        jobs_total = await count(select(func.count()).select_from(AuditJob))
        jobs_30 = await count(select(func.count()).select_from(AuditJob).where(AuditJob.created_at >= d30))
        jobs_prev = await count(
            select(func.count()).select_from(AuditJob).where(AuditJob.created_at >= d60, AuditJob.created_at < d30)
        )
        fails_stmt = select(func.coalesce(func.sum(AuditSummary.total_fails), 0)).select_from(AuditSummary)
        fails_total = await count(fails_stmt)
        joined = fails_stmt.join(AuditJob, AuditJob.id == AuditSummary.job_id)
        fails_30 = await count(joined.where(AuditJob.created_at >= d30))
        fails_prev = await count(joined.where(AuditJob.created_at >= d60, AuditJob.created_at < d30))

        status_rows = (await s.execute(select(AuditJob.status, func.count()).group_by(AuditJob.status))).all()

    status_counts = {"completed": 0, "running": 0, "failed": 0, "cancelled": 0}
    for raw, n in status_rows:
        key = _status(raw)
        status_counts["running" if key == "queued" else key] += int(n)
    stats = {
        "totalUsers": users_total,
        "totalUsersTrend": _trend(users_30, 0, absolute=True),
        "totalAudits": jobs_total,
        "totalAuditsTrend": _trend(jobs_30, jobs_prev),
        "totalFails": fails_total,
        "totalFailsTrend": _trend(fails_30, fails_prev),
    }
    slices = [{"status": k, "count": v} for k, v in status_counts.items()]
    return stats, slices


_PAGES_PER_DAY_DAYS = 30


async def _pages_per_day(days: int = _PAGES_PER_DAY_DAYS) -> List[Dict[str, Any]]:
    """One point per calendar day (UTC) for the last *days* days, oldest
    first, with the number of pages audited by jobs created that day. Days
    with no audits are present with 0 so the line has no gaps."""
    today = _now().date()
    start = today - timedelta(days=days - 1)
    buckets = {start + timedelta(days=i): 0 for i in range(days)}
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(AuditJob.created_at, AuditSummary.total_pages, AuditJob.actual_pages)
                .outerjoin(AuditSummary, AuditSummary.job_id == AuditJob.id)
                .where(AuditJob.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc))
            )
        ).all()
    for created, total_pages, actual_pages in rows:
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        day = created.astimezone(timezone.utc).date()
        if day in buckets:
            buckets[day] += int(total_pages or actual_pages or 0)
    return [{"date": d.isoformat(), "pages": n} for d, n in sorted(buckets.items())]


async def _activity(limit: int = 30) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    async with session_scope() as s:
        logs = (
            await s.execute(
                select(AuditLog, AuditJob.target_url, AuditSummary.total_pages, AuditSummary.total_fails, AuditSummary.needs_review_count)
                .join(AuditJob, AuditJob.id == AuditLog.job_id)
                .outerjoin(AuditSummary, AuditSummary.job_id == AuditJob.id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit * 2)
            )
        ).all()
        for log, url, pages, fails, review in logs:
            code = log.event_type or ""
            meta = log.metadata_ or {}
            jid = str(log.job_id)
            host = _host(url)
            if code == "JOB_COMPLETED":
                items.append({"id": f"log-{log.id}", "kind": "auditCompleted", "at": _iso(log.created_at), "jobId": jid,
                              "params": {"pages": pages or meta.get("pages") or 0, "fails": fails or 0, "host": host}, "important": True})
                if review:
                    items.append({"id": f"log-{log.id}-r", "kind": "needsReview", "at": _iso(log.created_at), "jobId": jid,
                                  "params": {"count": review, "host": host}, "important": False})
            elif code == "JOB_FAILED":
                items.append({"id": f"log-{log.id}", "kind": "auditFailed", "at": _iso(log.created_at), "jobId": jid,
                              "params": {"reason": (log.message or meta.get("error") or meta.get("stage") or host)[:160], "host": host}, "important": True})
            elif code in ("JOB_STARTED", "JOB_CREATED"):
                items.append({"id": f"log-{log.id}", "kind": "workerStarted", "at": _iso(log.created_at), "jobId": jid,
                              "params": {"job": host}, "important": False})
            elif code == "JOB_CANCELLED":
                items.append({"id": f"log-{log.id}", "kind": "failedJob", "at": _iso(log.created_at), "jobId": jid,
                              "params": {"host": host}, "important": False})
        reps = (
            await s.execute(select(Report).order_by(Report.created_at.desc()).limit(limit))
        ).scalars()
        for r in reps:
            items.append({"id": f"rep-{r.id}", "kind": "reportGenerated", "at": _iso(r.created_at), "jobId": str(r.job_id),
                          "params": {"format": (r.format or "").upper()}, "important": True})
        sessions = (
            await s.execute(
                select(UserSession.id, UserSession.started_at, User.email, User.id)
                .join(User, User.id == UserSession.user_id)
                .order_by(UserSession.started_at.desc())
                .limit(limit)
            )
        ).all()
        oidc_users = set(
            (await s.execute(select(OAuthIdentity.user_id).distinct())).scalars().all()
        )
        for sid, started, email, uid in sessions:
            items.append({"id": f"sess-{sid}", "kind": "userLogin", "at": _iso(started),
                          "params": {"email": email, "provider": "OIDC" if uid in oidc_users else "Password"}, "important": False})
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items[:limit]


async def _notifications(limit: int = 10) -> List[Dict[str, Any]]:
    since = _now() - timedelta(hours=24)
    out: List[Dict[str, Any]] = []
    async with session_scope() as s:
        failed = (
            await s.execute(
                select(AuditJob).where(AuditJob.status == "failed", AuditJob.updated_at >= since)
                .order_by(AuditJob.updated_at.desc()).limit(limit)
            )
        ).scalars()
        for job in failed:
            out.append({"id": f"job-{job.id}", "title": f"Audit failed: {_host(job.target_url)}",
                        "at": _iso(job.updated_at), "read": False, "href": "/admin/audits"})
        crashes = (
            await s.execute(select(CrashReport).where(CrashReport.created_at >= since)
                            .order_by(CrashReport.created_at.desc()).limit(limit))
        ).scalars()
        for c in crashes:
            out.append({"id": f"crash-{c.id}", "title": f"Crash in {c.stage or c.service or 'engine'}: {(c.error_type or 'error')}",
                        "at": _iso(c.created_at), "read": False, "href": "/admin/audits"})
    out.sort(key=lambda n: n["at"] or "", reverse=True)
    return out[:limit]


# ── routes ───────────────────────────────────────────────────────────────────


@router.get("/overview")
async def overview(user: CurrentUser = Depends(require_admin)) -> Dict[str, Any]:
    _require_pg()
    stats, slices = await _stats()
    node_ok, pg_ok = await asyncio.gather(_node_healthy(), pg_ping())
    stats["systemHealth"] = "healthy" if (node_ok and pg_ok) else "degraded"
    jobs, activity, notifications, pages_per_day = await asyncio.gather(
        _list_jobs(limit=25, offset=0), _activity(), _notifications(), _pages_per_day()
    )
    return {
        "generatedAt": _iso(_now()),
        "stats": stats,
        "auditStatus": slices,
        "pagesPerDay": pages_per_day,
        "recentAudits": jobs,
        "activity": activity,
        "notifications": notifications,
        "currentUser": {"name": user.name or (user.email or "").split("@")[0], "email": user.email or "", "role": "Admin"},
        "services": {"node": node_ok, "postgres": pg_ok},
    }


@router.get("/audits")
async def audits(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, max_length=20),
    q: Optional[str] = Query(None, max_length=200),
) -> Dict[str, Any]:
    _require_pg()
    return {"jobs": await _list_jobs(limit=limit, offset=offset, status=status, q=q)}


@router.get("/audits/{job_id}")
async def audit_detail(job_id: str) -> Dict[str, Any]:
    _require_pg()
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown job")
    jobs = await _list_jobs(limit=1, offset=0, job_id=jid)
    if not jobs:
        raise HTTPException(status_code=404, detail="Unknown job")
    return await _attach_detail(jobs[0])


_EXPORT_MEDIA = {"csv": "text/csv; charset=utf-8", "pdf": "application/pdf", "html": "text/html; charset=utf-8"}


@router.get("/audits/{job_id}/export")
async def audit_export(job_id: str, format: str = Query(..., pattern=r"^(csv|pdf|html)$")):
    """Download one audit's report in the requested format. A file the
    engine already stored for the job (CSV/PDF from the completion upload)
    is served as-is; otherwise the document is built from the report JSON
    in the run store. The filename uses the audited host, not the job id."""
    _require_pg()
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown job")
    async with session_scope() as s:
        job = await s.get(AuditJob, jid)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown job")
        target_url = job.target_url
        stored = (
            await s.execute(
                select(Report).where(Report.job_id == jid, func.lower(Report.format) == format)
                .order_by(Report.created_at.desc()).limit(1)
            )
        ).scalars().first()
    host = _host(target_url).replace(":", "_") or "audit"
    filename = f"{host}-accessibility-audit.{format}"

    if stored is not None:
        from ka11y.storage.backends import get_store

        store = get_store()
        if store is not None:
            url = await store.download_url(stored.s3_key, filename=filename)
            if url:
                return RedirectResponse(url, status_code=302)
            data = await store.get_bytes(stored.s3_key)
            if data is not None:
                return Response(content=data, media_type=_EXPORT_MEDIA[format],
                                headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    try:
        report = await run_repo.get_report(job_id)
    except Exception:  # noqa: BLE001
        report = None
    if not report:
        raise HTTPException(status_code=404, detail="No report is stored for this audit yet.")

    if format == "csv":
        from ka11y.utils.report_csv import build_findings_csv

        body: Any = build_findings_csv(report)
    elif format == "html":
        from ka11y.utils.report_pdf import _MAX_ROWS_PER_SECTION, _collect_images, build_report_html

        try:
            images = await _collect_images(report, _MAX_ROWS_PER_SECTION)
        except Exception:  # noqa: BLE001
            images = {}
        body = build_report_html(report, images)
    else:
        from ka11y.utils.report_pdf import build_report_pdf

        body = await build_report_pdf(report)
        if body is None:
            raise HTTPException(status_code=503, detail="PDF rendering is unavailable right now.")
    return Response(content=body, media_type=_EXPORT_MEDIA[format],
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/users")
async def users() -> Dict[str, Any]:
    _require_pg()
    cfg = auth_settings()
    async with session_scope() as s:
        audits_sub = (
            select(AuditJob.user_id, func.count().label("n")).group_by(AuditJob.user_id).subquery()
        )
        rows = (
            await s.execute(
                select(User, OrganizationMember.role, Organization.name, audits_sub.c.n)
                .outerjoin(OrganizationMember, OrganizationMember.user_id == User.id)
                .outerjoin(Organization, Organization.id == OrganizationMember.organization_id)
                .outerjoin(audits_sub, audits_sub.c.user_id == User.id)
                .where(User.deleted_at.is_(None))
                .order_by(User.created_at.desc())
            )
        ).all()
        providers: Dict[uuid.UUID, List[str]] = {}
        for uid, provider in (await s.execute(select(OAuthIdentity.user_id, OAuthIdentity.provider))).all():
            providers.setdefault(uid, []).append(provider)
    out = []
    seen = set()
    for u, role, org, n in rows:
        if u.id in seen:
            continue
        seen.add(u.id)
        methods = list(providers.get(u.id, []))
        if u.password_hash:
            methods.append("password")
        out.append({
            "id": str(u.id),
            "name": u.name or "",
            "email": u.email,
            "organization": org or "",
            "role": role or "member",
            "isAdmin": u.email.lower() in cfg.admin_emails,
            "status": u.status,
            "signInMethods": methods,
            "audits": int(n or 0),
            "createdAt": _iso(u.created_at),
            "lastLoginAt": _iso(u.last_login_at),
        })
    return {"users": out, "allowListed": sorted(cfg.allowed_emails), "adminEmails": sorted(cfg.admin_emails)}


@router.get("/fails")
async def fails(days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    since = _now() - timedelta(days=days)
    occurrences = func.sum(case((AuditFail.status == "fail", 1), else_=0)).label("occurrences")
    needs_review = func.sum(case((AuditFail.status == "needs_review", 1), else_=0)).label("needs_review")
    rows = await _rows(
        select(
            AuditFail.wcag_sc,
            func.max(AuditFail.level).label("level"),
            occurrences,
            needs_review,
            func.count(func.distinct(AuditFail.job_id)).label("runs"),
            func.count(func.distinct(AuditFail.page_url)).label("pages"),
        )
        .where(AuditFail.status.in_(("fail", "needs_review")), AuditFail.created_at >= since)
        .group_by(AuditFail.wcag_sc)
        .having(occurrences > 0)
        .order_by(occurrences.desc())
        .limit(150)
    )
    sev_rows = await _rows(
        select(AuditFail.wcag_sc, AuditFail.severity, func.count())
        .where(AuditFail.status == "fail", AuditFail.severity.is_not(None), AuditFail.created_at >= since)
        .group_by(AuditFail.wcag_sc, AuditFail.severity)
    )
    top_sev: Dict[str, Tuple[int, str]] = {}
    for sc, raw_sev, n in sev_rows:
        sev = _severity(raw_sev)
        if sev and (sc not in top_sev or n > top_sev[sc][0]):
            top_sev[sc] = (int(n), sev)
    names: Dict[str, Tuple[str, str]] = {}
    if pg_configured():
        async with session_scope() as s:
            for code, name, level in (await s.execute(select(WcagRule.rule_code, WcagRule.name, WcagRule.level))).all():
                names[code] = (name, level)
    out = []
    for wcag_sc, row_level, occ, review, runs, pages in rows:
        sc = wcag_sc or "?"
        name, level = names.get(sc, (sc, row_level or ""))
        out.append({
            "criterion": sc,
            "title": name,
            "level": row_level or level or "",
            "severity": top_sev.get(sc, (0, "unknown"))[1],
            "occurrences": int(occ or 0),
            "needsReview": int(review or 0),
            "runs": int(runs or 0),
            "pages": int(pages or 0),
        })
    return {"days": days, "fails": out}


@router.get("/reports")
async def reports(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    _require_pg()
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Report, AuditJob.target_url, User.email)
                .join(AuditJob, AuditJob.id == Report.job_id)
                .outerjoin(User, User.id == Report.user_id)
                .order_by(Report.created_at.desc())
                .limit(limit)
            )
        ).all()
    out = []
    for r, url, email in rows:
        d = _report_dict(r)
        d.update({"jobId": str(r.job_id), "targetUrl": url, "targetHost": _host(url), "user": email or "",
                  "type": r.report_type, "status": r.status, "bucket": r.s3_bucket or "", "key": r.s3_key})
        out.append(d)
    return {"reports": out}


@router.get("/system-events")
async def system_events(limit: int = Query(100, ge=1, le=500)) -> Dict[str, Any]:
    _require_pg()
    out: List[Dict[str, Any]] = []
    async with session_scope() as s:
        logs = (
            await s.execute(
                select(AuditLog, AuditJob.target_url, User.email)
                .join(AuditJob, AuditJob.id == AuditLog.job_id)
                .outerjoin(User, User.id == AuditLog.user_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).all()
        for log, url, email in logs:
            code = log.event_type or ""
            level = "error" if "FAIL" in code else ("warn" if "CANCEL" in code else "info")
            out.append({
                "id": f"log-{log.id}", "at": _iso(log.created_at), "source": "job", "level": level, "code": code,
                "message": log.message or code.replace("_", " ").title(), "jobId": str(log.job_id),
                "targetHost": _host(url), "user": email or "", "metadata": log.metadata_ or {},
            })
        crashes = (
            await s.execute(select(CrashReport).order_by(CrashReport.created_at.desc()).limit(limit))
        ).scalars()
        for c in crashes:
            out.append({
                "id": f"crash-{c.id}", "at": _iso(c.created_at), "source": "crash", "level": "error",
                "code": c.error_type or "CRASH",
                "message": f"{c.stage or c.service or 'engine'}: {(c.error_message or '')[:300]}",
                "jobId": str(c.job_id) if c.job_id else "", "targetHost": "", "user": "", "metadata": c.metadata_ or {},
            })
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return {"events": out[:limit]}


@router.get("/metrics")
async def admin_metrics():
    """Aggregate telemetry rollups for ops dashboards (audit_jobs + stage_timings).

    Lived on the assets router (user auth) until 2026-09-27; it exposes every
    failed run's URL, so it belongs behind require_admin like the rest of /admin.

    These answer the questions the old per-run timing logs could not without
    grepping: throughput, failure rate, slowest stages, wall-time by depth.
    """
    _require_pg()

    def _int(v: Any) -> Optional[int]:
        return int(v) if v is not None else None

    try:
        async with session_scope() as s:
            status_counts = (await s.execute(select(AuditJob.status, func.count()).group_by(AuditJob.status))).all()
            wall_by_depth = (
                await s.execute(
                    select(AuditJob.crawl_depth, func.count(), func.avg(AuditJob.wall_ms), func.max(AuditJob.wall_ms))
                    .where(AuditJob.wall_ms.is_not(None))
                    .group_by(AuditJob.crawl_depth)
                    .order_by(AuditJob.crawl_depth)
                )
            ).all()
            avg_ms = func.avg(StageTiming.duration_ms).label("avg_ms")
            slowest_stages = (
                await s.execute(
                    select(
                        StageTiming.stage,
                        func.count(),
                        avg_ms,
                        func.max(StageTiming.duration_ms),
                        func.sum(case((StageTiming.status == "error", 1), else_=0)),
                    )
                    .group_by(StageTiming.stage)
                    .order_by(avg_ms.desc())
                    .limit(25)
                )
            ).all()
            recent_failures = (
                await s.execute(
                    select(AuditJob.id, AuditJob.target_url, AuditJob.error_stage, AuditJob.completed_at)
                    .where(AuditJob.status == "failed")
                    .order_by(AuditJob.completed_at.desc().nulls_last())
                    .limit(20)
                )
            ).all()
            totals = (
                await s.execute(
                    select(
                        func.count(),
                        func.sum(case((AuditJob.status == "completed", 1), else_=0)),
                        func.sum(case((AuditJob.status == "failed", 1), else_=0)),
                        func.avg(AuditJob.wall_ms),
                        func.avg(AuditJob.queue_wait_ms),
                    )
                )
            ).one()
    except Exception:
        raise HTTPException(status_code=503, detail="Telemetry store unavailable.")

    return {
        "totals": {
            "total_runs": int(totals[0] or 0),
            "completed": int(totals[1] or 0),
            "failed": int(totals[2] or 0),
            "avg_wall_ms": _int(totals[3]),
            "avg_queue_wait_ms": _int(totals[4]),
        },
        "status_counts": {status: int(n) for status, n in status_counts},
        "wall_ms_by_depth": [
            {"depth": depth, "runs": int(n), "avg_wall_ms": _int(avg), "max_wall_ms": _int(mx)}
            for depth, n, avg, mx in wall_by_depth
        ],
        "slowest_stages": [
            {"stage": stage, "steps": int(n), "avg_ms": _int(avg), "max_ms": _int(mx), "errors": int(err or 0)}
            for stage, n, avg, mx, err in slowest_stages
        ],
        "recent_failures": [
            {"run_id": str(jid), "url": url, "error_stage": stage, "completed_at": _iso(done)}
            for jid, url, stage, done in recent_failures
        ],
    }


@router.get("/settings")
async def admin_settings() -> Dict[str, Any]:
    cfg = auth_settings()
    env = os.getenv
    node_ok, pg_ok = await asyncio.gather(_node_healthy(), pg_ping() if pg_configured() else asyncio.sleep(0, result=False))

    def flag(v: Any) -> str:
        return "on" if v else "off"

    sections = [
        {"key": "services", "items": [
            {"label": "PostgreSQL", "value": "connected" if pg_ok else "unavailable"},
            {"label": "axe-core engine (node)", "value": "healthy" if node_ok else "unreachable"},
            {"label": "NODE_BASE_URL", "value": env("NODE_BASE_URL", "http://localhost:3000")},
            {"label": "Run store", "value": f"PostgreSQL ({_db_host()})" if pg_configured() else "not configured"},
        ]},
        {"key": "auth", "items": [
            {"label": "Password sign-in", "value": flag(cfg.password_login)},
            {"label": "Self-service registration", "value": flag(cfg.password_registration)},
            {"label": "OIDC provider", "value": cfg.provider_name if cfg.oidc_configured else "not configured"},
            {"label": "Allow-listed e-mails", "value": ", ".join(sorted(cfg.allowed_emails)) or "(anyone)"},
            {"label": "Allow-listed domains", "value": ", ".join(sorted(cfg.allowed_domains)) or "—"},
            {"label": "Admin e-mails", "value": ", ".join(sorted(cfg.admin_emails)) or "—"},
            {"label": "Session idle / remember / max", "value": f"{cfg.session_idle_hours} h / {cfg.session_remember_days} d / {cfg.session_max_days} d"},
            {"label": "Secure cookie", "value": flag(cfg.cookie_secure)},
            {"label": "Cookie sealing", "value": "AES-256-GCM (HKDF-SHA256 key)"},
            {"label": "__Host- cookie prefix", "value": flag(cfg.cookie_host_prefix)},
            {"label": "Force HTTPS (308)", "value": flag(cfg.force_https)},
            {"label": "HSTS max-age", "value": f"{cfg.hsts_max_age} s" + (" + preload" if cfg.hsts_preload else "") if cfg.hsts_max_age else "off"},
        ]},
        {"key": "engine", "items": [
            {"label": "Concurrent audits", "value": env("KA11Y_MAX_CONCURRENT_JOBS", "4")},
            {"label": "Browser contexts", "value": env("KA11Y_MAX_BROWSER_CONTEXTS", env("KA11Y_MAX_BROWSERS", "2"))},
            {"label": "Job timeout (s)", "value": env("KA11Y_JOB_TIMEOUT_SECONDS", "1800")},
            {"label": "Run retention (days)", "value": env("KA11Y_RUN_RETENTION_DAYS", "30")},
            {"label": "Crash-requeue attempts", "value": env("KA11Y_MAX_ATTEMPTS", "2")},
            {"label": "Unified crawl", "value": flag(env("KA11Y_UNIFIED_CRAWL", "0") == "1")},
            {"label": "Auto-migrate on start", "value": flag(env("KA11Y_DB_AUTO_MIGRATE", "1") == "1")},
        ]},
        {"key": "storage", "items": [
            {"label": "Backend", "value": env("KA11Y_STORAGE_BACKEND", "auto")},
            {"label": "S3 bucket", "value": env("KA11Y_S3_BUCKET", "") or "(local directory)"},
            {"label": "S3 region", "value": env("KA11Y_S3_REGION", env("AWS_REGION", "")) or "—"},
            {"label": "Local artifact directory", "value": env("KA11Y_ARTIFACT_DIR", "ka11y-python/logs/artifacts")},
            {"label": "PDF report on completion", "value": flag(env("KA11Y_ARTIFACT_PDF", "1") != "0")},
        ]},
        {"key": "email", "items": [
            {"label": "SMTP server", "value": f"{env('SMTP_SERVER', 'smtp.gmail.com')}:{env('SMTP_PORT', '587')}"},
            {"label": "Sender", "value": env("SENDER_EMAIL", "") or "(not configured — completion e-mails skipped)"},
        ]},
        {"key": "ai", "items": [
            {"label": "Gemini enrichment", "value": "configured" if env("GEMINI_API_KEY") else "off (static reason/fix text)"},
            {"label": "Deepgram transcription", "value": "configured" if env("DEEPGRAM_API_KEY") else "off"},
        ]},
    ]
    return {"generatedAt": _iso(_now()), "sections": sections}


# ── live change feed ─────────────────────────────────────────────────────────


async def _change_cursor() -> Tuple[Any, ...]:
    log_max = sess_max = rep_max = crash_max = job_max = None
    if pg_configured():
        async with session_scope() as s:
            log_max = (await s.execute(select(func.max(AuditLog.id)))).scalar()
            sess_max = (await s.execute(select(func.max(UserSession.started_at)))).scalar()
            rep_max = (await s.execute(select(func.max(Report.created_at)))).scalar()
            crash_max = (await s.execute(select(func.max(CrashReport.created_at)))).scalar()
            job_max = (await s.execute(select(func.max(AuditJob.updated_at)))).scalar()
    return (log_max, str(sess_max), str(rep_max), str(crash_max), str(job_max))


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """`event: refresh` whenever the underlying tables change; a comment
    line every 20 s keeps proxies from closing the connection."""

    async def stream():
        last: Optional[Tuple[Any, ...]] = None
        last_ping = time.monotonic()
        yield "retry: 3000\n\n"
        while True:
            if await request.is_disconnected():
                return
            try:
                cur = await _change_cursor()
            except Exception:  # noqa: BLE001
                cur = None
            if cur is not None and last is not None and cur != last:
                yield f"event: refresh\ndata: {json.dumps({'at': _iso(_now())})}\n\n"
            if cur is not None:
                last = cur
            if time.monotonic() - last_ping > 20:
                yield ": ping\n\n"
                last_ping = time.monotonic()
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform: the Next.js server would otherwise gzip the proxied
        # stream for browsers (they send Accept-Encoding) and buffer it, so
        # events would only arrive in bulk. X-Accel-Buffering covers nginx.
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
