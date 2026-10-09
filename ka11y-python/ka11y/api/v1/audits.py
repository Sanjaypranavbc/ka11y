"""
ka11y/api/v1/audits.py
======================
Audit history and artifacts, served from object storage.

PostgreSQL (ownership-aware history over ``audit_jobs LEFT JOIN
audit_summary``, spec §27) is switched off for now: every ``run_repo`` call is
commented out, not removed. Until it is back there is no owner on a job, so
``_assert_can_view`` lets any signed-in (or anonymous, with auth disabled)
caller see any job, and the history is the list of state.json documents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response

from ka11y.auth import CurrentUser, require_user
from ka11y.storage import jobstate, keys
from ka11y.storage.backends import get_store, guess_type
from ka11y.storage.uploader import download_url_for
# from ka11y.store import repo as run_repo  # PostgreSQL: switched off

router = APIRouter(prefix="/audits", tags=["audits"])

_REPORT_MEDIA = {"json": "application/json", "csv": "text/csv", "pdf": "application/pdf", "html": "text/html"}


@router.get("/history")
async def audit_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    scope: str = Query("me", pattern=r"^(me|org)$"),
    status: Optional[str] = Query(None, pattern=r"^(queued|running|completed|failed|cancelled)$"),
    url: Optional[str] = Query(None, max_length=512),
    user: CurrentUser = Depends(require_user),
) -> Dict[str, Any]:
    # PostgreSQL (per-user / per-organization history) — switched off:
    # if user.is_anonymous:
    #     return {"items": [], "limit": limit, "offset": offset, "scope": scope}
    # if scope == "org" and user.organization_id is None:
    #     raise HTTPException(status_code=400, detail="You are not a member of an organization.")
    # items = await run_repo.list_history(user_id=user.user_id, organization_id=user.organization_id,
    #                                     scope=scope, limit=limit, offset=offset, status=status, url=url)
    items: List[Dict[str, Any]] = await jobstate.list_states(limit=limit, offset=offset, url=url, status=status)
    return {"items": items, "limit": limit, "offset": offset, "scope": scope}


async def _assert_can_view(job_id: str, user: CurrentUser) -> None:
    """A job is visible to its owner and to members of the owning organization.
    Unknown or anonymous jobs are visible to anyone signed in.

    With the ownership store (PostgreSQL) switched off every job is anonymous,
    so this always passes. The original check is kept for when it returns."""
    return
    # try:
    #     owner = await run_repo.get_owner(job_id)
    # except Exception:  # noqa: BLE001 — PG down: fail closed, but as a clean 503
    #     raise HTTPException(status_code=503, detail="Ownership store unavailable.")
    # if owner is None or user.is_anonymous or user.is_admin:
    #     return
    # if owner["user_id"] == user.user_id:
    #     return
    # if owner.get("organization_id") and owner["organization_id"] == user.organization_id:
    #     return
    # raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")


def _split_artifacts(job_id: str, prefix: str, found: List[str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Object keys under a job → (reports, assets) in the shape the old
    ``reports`` / ``audit_assets`` rows had, minus the ids."""
    reports: List[Dict[str, Any]] = []
    assets: List[Dict[str, Any]] = []
    for key in found:
        rel = key[len(prefix) + 1:] if key.startswith(prefix + "/") else key
        name = rel.rsplit("/", 1)[-1]
        if rel in (jobstate.STATE_FILE, jobstate.CANCEL_FILE, jobstate.REVIEWS_FILE):
            continue
        if rel.startswith("reports/"):
            fmt = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
            reports.append({
                "report_id": name, "job_id": job_id,
                "type": "summary" if fmt == "pdf" else "findings" if fmt == "csv" else "full",
                "format": fmt, "key": key, "bucket": None,
            })
        else:
            folder = rel.split("/", 1)[0]
            assets.append({
                "id": None, "job_id": job_id, "kind": folder, "rel_path": rel, "key": key,
                "mime": guess_type(name), "page_url": None,
            })
    return reports, assets


@router.get("/{job_id}/artifacts")
async def audit_artifacts(job_id: str, user: CurrentUser = Depends(require_user)) -> Dict[str, Any]:
    """Everything stored for one audit: report files (JSON/CSV/PDF) with
    download links, and every uploaded asset (screenshots, crops, HTML
    snapshots, OCR reports, step logs) with its serving URL."""
    await _assert_can_view(job_id, user)
    if await jobstate.get_state(job_id) is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    # reports = await run_repo.list_reports(job_id)                 # PostgreSQL: off
    # assets = await run_repo.query_assets_with_keys(job_id)        # PostgreSQL: off
    prefix = await keys.job_prefix(job_id)
    reports, assets = _split_artifacts(job_id, prefix, await jobstate.list_artifacts(job_id))
    for r in reports:
        r["download_url"] = (
            await download_url_for(r["key"], filename=f"{job_id}-{r['type']}.{r['format']}")
            or f"/api/v1/audits/{job_id}/reports/{r['report_id']}/download"
        )
    for a in assets:
        a["url"] = f"/api/v1/assets/by-key/{a['key']}"
    store = get_store()
    return {
        "job_id": job_id,
        "storage": store.backend if store else "off",
        "reports": reports,
        "assets": assets,
    }


@router.get("/{job_id}/reports/{report_id}/download")
async def download_report(job_id: str, report_id: str, user: CurrentUser = Depends(require_user)):
    """``report_id`` is the file name under the job's ``reports/`` folder
    (report.json, findings.csv, report.pdf) — there are no report rows
    while PostgreSQL is switched off."""
    await _assert_can_view(job_id, user)
    # rep = await run_repo.get_report_file(report_id)   # PostgreSQL: off
    store = get_store()
    if store is None:
        raise HTTPException(status_code=404, detail="Object storage is not configured")
    filename = keys._clean(report_id)
    if not filename or "." not in filename:
        raise HTTPException(status_code=404, detail="Report not found")
    key = keys.report_key(await keys.job_prefix(job_id), filename)
    fmt = filename.rsplit(".", 1)[-1].lower()
    download_name = f"{job_id}-{filename}"
    url = await store.download_url(key, filename=download_name)
    if url:
        return RedirectResponse(url, status_code=302)
    data = await store.get_bytes(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Report file not found")
    return Response(
        content=data,
        media_type=_REPORT_MEDIA.get(fmt, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
