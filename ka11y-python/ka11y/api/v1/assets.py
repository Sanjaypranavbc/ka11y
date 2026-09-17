"""
ka11y/api/v1/assets.py
=====================
Content-addressed asset serving + admin telemetry rollups.

  GET /api/v1/assets/{asset_id}     Serve a stored asset (screenshot/crop/HAR)
  GET /api/v1/admin/metrics         Ops rollups derived from the telemetry tables

The asset endpoint replaces the per-job ``?path=`` scheme: an asset is served by
its DB id, the row is the authority for the on-disk location, and a containment
check in :func:`store.assets.get_asset` blocks path traversal.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from ka11y.store import repo
from ka11y.store.assets import get_asset_record
from ka11y.store.db import get_db
from ka11y.storage.backends import LocalObjectStore, get_store

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}")
async def serve_asset(asset_id: int):
    """Serve from local disk when the file is there; otherwise from object
    storage (302 to a presigned S3 URL, or the local artifact copy)."""
    row = await get_asset_record(asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = row.get("mime") or mimetypes.guess_type(row["rel_path"])[0] or "application/octet-stream"
    if row.get("abs_path"):
        return FileResponse(row["abs_path"], media_type=media_type)

    key = row.get("object_key")
    store = get_store() if key else None
    if store is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if isinstance(store, LocalObjectStore):
        local = store.local_path(key)
        if local is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(str(local), media_type=media_type)
    url = await store.download_url(key)
    if url:
        return RedirectResponse(url, status_code=302)
    data = await store.get_bytes(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(content=data, media_type=media_type)


@router.get("/admin/metrics")
async def admin_metrics():
    """Aggregate telemetry rollups for ops dashboards. All from SQLite.

    These answer the questions the old per-run timing logs could not without
    grepping: throughput, failure rate, slowest stages, wall-time by depth.
    """
    db = get_db()
    try:
        status_counts = await db.query(
            "SELECT status, COUNT(*) AS n FROM runs GROUP BY status"
        )
        wall_by_depth = await db.query(
            "SELECT max_depth AS depth, COUNT(*) AS runs, "
            "       CAST(AVG(wall_ms) AS INTEGER) AS avg_wall_ms, "
            "       MAX(wall_ms) AS max_wall_ms "
            "FROM runs WHERE wall_ms IS NOT NULL GROUP BY max_depth ORDER BY max_depth"
        )
        slowest_stages = await db.query(
            "SELECT stage, COUNT(*) AS steps, "
            "       CAST(AVG(duration_ms) AS INTEGER) AS avg_ms, "
            "       CAST(MAX(duration_ms) AS INTEGER) AS max_ms, "
            "       SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) AS errors "
            "FROM stage_timings GROUP BY stage ORDER BY avg_ms DESC LIMIT 25"
        )
        recent_failures = await db.query(
            "SELECT run_id, url, error_stage, completed_at FROM runs "
            "WHERE status='failed' ORDER BY completed_at DESC LIMIT 20"
        )
        totals = await db.query_one(
            "SELECT COUNT(*) AS total_runs, "
            "       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed, "
            "       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed, "
            "       CAST(AVG(wall_ms) AS INTEGER) AS avg_wall_ms, "
            "       CAST(AVG(queue_wait_ms) AS INTEGER) AS avg_queue_wait_ms FROM runs"
        )
    except Exception:
        raise HTTPException(status_code=503, detail="Telemetry store unavailable.")

    return {
        "totals": totals,
        "status_counts": {r["status"]: r["n"] for r in status_counts},
        "wall_ms_by_depth": wall_by_depth,
        "slowest_stages": slowest_stages,
        "recent_failures": recent_failures,
    }
