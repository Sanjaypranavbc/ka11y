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
from fastapi.responses import FileResponse

from ka11y.store import repo
from ka11y.store.assets import get_asset
from ka11y.store.db import get_db

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}")
async def serve_asset(asset_id: int):
    row = await get_asset(asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = row.get("mime")
    if not media_type:
        media_type, _ = mimetypes.guess_type(row["abs_path"])
    return FileResponse(row["abs_path"], media_type=media_type or "application/octet-stream")


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
