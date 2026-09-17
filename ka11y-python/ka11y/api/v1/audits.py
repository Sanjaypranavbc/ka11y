"""
ka11y/api/v1/audits.py
======================
Ownership-aware audit history (spec §27): ``audit_jobs LEFT JOIN audit_summary``
for the signed-in user, or for their whole organization with ``?scope=org``.

The older ``GET /combined/history`` reads the SQLite run store and has no
notion of who ran what; this endpoint is the one the History page should use.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from ka11y.auth import CurrentUser, require_user
from ka11y.db import audit_repo
from ka11y.storage.backends import get_store
from ka11y.storage.uploader import download_url_for
from ka11y.store import repo as run_repo

router = APIRouter(prefix="/audits", tags=["audits"])


@router.get("/history")
async def audit_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scope: str = Query("me", pattern=r"^(me|org)$"),
    status: Optional[str] = Query(None, pattern=r"^(queued|running|completed|failed|cancelled)$"),
    url: Optional[str] = Query(None, max_length=512),
    user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    if user.is_anonymous:
        return {"items": [], "limit": limit, "offset": offset, "scope": scope}
    if scope == "org" and user.organization_id is None:
        raise HTTPException(status_code=400, detail="You are not a member of an organization.")
    items: List[Dict[str, Any]] = await audit_repo.list_history(
        user_id=user.user_id,
        organization_id=user.organization_id,
        scope=scope,
        limit=limit,
        offset=offset,
        status=status,
        url=url,
    )
    return {"items": items, "limit": limit, "offset": offset, "scope": scope}


async def _assert_can_view(job_id: str, user: CurrentUser) -> None:
    """A job is visible to its owner and to members of the owning organization.
    Jobs PostgreSQL does not know (anonymous) are visible to anyone signed in."""
    owner = await audit_repo.get_owner(job_id)
    if owner is None or user.is_anonymous:
        return
    if owner["user_id"] == user.user_id:
        return
    if owner.get("organization_id") and owner["organization_id"] == user.organization_id:
        return
    raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")


@router.get("/{job_id}/artifacts")
async def audit_artifacts(job_id: str, user: CurrentUser = Depends(require_user)) -> Dict[str, Any]:
    """Everything stored for one audit: report files (JSON/CSV/PDF) with
    download links, and every registered asset (screenshots, crops, HTML
    snapshots, OCR reports, step logs) with its serving URL."""
    await _assert_can_view(job_id, user)
    reports = await audit_repo.list_reports(job_id)
    for r in reports:
        r["download_url"] = (
            await download_url_for(r["key"], filename=f"{job_id}-{r['type']}.{r['format']}")
            or f"/api/v1/audits/{job_id}/reports/{r['report_id']}/download"
        )
    try:
        assets = await run_repo.query_assets_with_keys(job_id)
    except Exception:  # noqa: BLE001
        assets = []
    for a in assets:
        a["url"] = f"/api/v1/assets/{a['id']}"
    store = get_store()
    return {
        "job_id": job_id,
        "storage": store.backend if store else "off",
        "reports": reports,
        "assets": assets,
    }


@router.get("/{job_id}/reports/{report_id}/download")
async def download_report(job_id: str, report_id: str, user: CurrentUser = Depends(require_user)):
    await _assert_can_view(job_id, user)
    rep = await audit_repo.get_report(report_id)
    if rep is None or rep["job_id"] != job_id:
        raise HTTPException(status_code=404, detail="Report not found")
    store = get_store()
    if store is None:
        raise HTTPException(status_code=404, detail="Object storage is not configured")
    filename = f"{job_id}-{rep['type']}.{rep['format']}"
    url = await store.download_url(rep["key"], filename=filename)
    if url:
        return RedirectResponse(url, status_code=302)
    data = await store.get_bytes(rep["key"])
    if data is None:
        raise HTTPException(status_code=404, detail="Report file not found")
    media = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf", "html": "text/html"}
    return Response(
        content=data,
        media_type=media.get(rep["format"], "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
