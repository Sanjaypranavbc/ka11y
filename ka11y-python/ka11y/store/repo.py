"""
ka11y/store/repo.py
===================
High-level persistence operations for the combined audit.

Two flavours of call:

* **Hot-path writes** (``create_run``, ``mark_*``, ``save_report``,
  ``save_findings``, ``insert_event``) are wrapped: a DB error is logged and
  swallowed so an audit never fails because persistence hiccuped.
* **Reads** (``get_run``, ``list_runs``, ``get_report`` …) propagate errors to
  the API layer, which turns them into a normal HTTP error.

All SQL lives here so a future Postgres swap is mechanical.
"""

from __future__ import annotations

import json
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.store.db import get_db

logger = setup_logger(name="KAC", tag="store.repo")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def _ms_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    da, db_ = _parse_iso(a), _parse_iso(b)
    if not da or not db_:
        return None
    return int((db_ - da).total_seconds() * 1000)


# ── run lifecycle (hot-path writes; swallow errors) ──────────────────────────


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
    submitted_at: str,
) -> None:
    try:
        await get_db().execute(
            "INSERT OR REPLACE INTO runs "
            "(run_id, url, status, lang_requested, wcag_level, params_json, "
            " max_depth, max_pages, submitted_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                url,
                status,
                lang_requested,
                wcag_level,
                json.dumps(params, default=str),
                max_depth,
                max_pages,
                submitted_at,
                _now(),
            ),
        )
    except Exception:  # noqa: BLE001
        logger.warning("[store] create_run(%s) failed", run_id, exc_info=True)


async def update_run(run_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    try:
        await get_db().execute(
            f"UPDATE runs SET {cols} WHERE run_id=?",
            (*fields.values(), run_id),
        )
    except Exception:  # noqa: BLE001
        logger.warning("[store] update_run(%s) failed", run_id, exc_info=True)


async def mark_running(run_id: str, run_started_at: str, submitted_at: Optional[str]) -> None:
    await update_run(
        run_id,
        status="running",
        run_started_at=run_started_at,
        worker_pid=_pid(),
        queue_wait_ms=_ms_between(submitted_at, run_started_at),
    )


async def mark_queued(run_id: str) -> None:
    await update_run(run_id, status="queued")


async def mark_completed(
    run_id: str,
    *,
    completed_at: str,
    run_started_at: Optional[str],
    summary: Optional[Dict[str, Any]],
    output_dir: Optional[str],
) -> None:
    await update_run(
        run_id,
        status="completed",
        completed_at=completed_at,
        wall_ms=_ms_between(run_started_at, completed_at),
        summary_json=json.dumps(summary or {}, default=str),
        output_dir=output_dir,
    )


async def mark_failed(
    run_id: str,
    *,
    completed_at: str,
    run_started_at: Optional[str],
    error_id: Optional[str],
    error_stage: Optional[str],
) -> None:
    await update_run(
        run_id,
        status="failed",
        completed_at=completed_at,
        wall_ms=_ms_between(run_started_at, completed_at),
        error_id=error_id,
        error_stage=error_stage,
    )


def _pid() -> int:
    import os

    return os.getpid()


# ── report + findings ────────────────────────────────────────────────────────


def _compress_report(report: Dict[str, Any]) -> tuple:
    """Pure CPU: serialize + zlib a report. Top-level + picklable so it can run
    in the shared ProcessPoolExecutor (P5) for large multi-page reports without
    blocking the event loop."""
    raw = json.dumps(report, default=str, ensure_ascii=False).encode("utf-8")
    return zlib.compress(raw, level=6), len(raw)


async def save_report(run_id: str, report: Dict[str, Any]) -> None:
    try:
        from ka11y.store.cpu_pool import run_cpu

        comp, raw_len = await run_cpu(_compress_report, report)
        await get_db().execute(
            "INSERT OR REPLACE INTO run_reports "
            "(run_id, report_zlib, bytes_raw, bytes_stored, created_at) "
            "VALUES (?,?,?,?,?)",
            (run_id, comp, raw_len, len(comp), _now()),
        )
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_report(%s) failed", run_id, exc_info=True)


async def save_findings(run_id: str, report: Dict[str, Any]) -> None:
    """Flatten violations/needs_review/passes into the findings table."""
    rows: List[tuple] = []
    now = _now()
    buckets = (
        ("violations", "fail"),
        ("needs_review", "needs_review"),
        ("passes", "pass"),
    )
    try:
        for key, default_status in buckets:
            for f in report.get(key, []) or []:
                el = f.get("element") or {}
                rows.append(
                    (
                        run_id,
                        el.get("page_url") or f.get("page_url"),
                        f.get("wcag_sc"),
                        f.get("level"),
                        f.get("status") or default_status,
                        f.get("source") or ("axe" if f.get("axe_rule_id") else "python"),
                        f.get("reason_code"),
                        el.get("selector") or el.get("target"),
                        json.dumps(el, default=str)[:4000] if el else None,
                        now,
                    )
                )
        if not rows:
            return
        await get_db().executemany(
            "INSERT INTO findings "
            "(run_id, page_url, wcag_sc, level, status, source, reason_code, "
            " selector, element_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_findings(%s) failed", run_id, exc_info=True)


async def save_pages(run_id: str, pages: List[Dict[str, Any]]) -> None:
    if not pages:
        return
    try:
        rows = [
            (
                run_id,
                p.get("page_url") or p.get("url"),
                p.get("depth"),
                p.get("http_status"),
                p.get("crawl_ms"),
                p.get("snapshot_ref"),
            )
            for p in pages
            if (p.get("page_url") or p.get("url"))
        ]
        if rows:
            await get_db().executemany(
                "INSERT INTO run_pages "
                "(run_id, page_url, depth, http_status, crawl_ms, snapshot_ref) "
                "VALUES (?,?,?,?,?,?)",
                rows,
            )
    except Exception:  # noqa: BLE001
        logger.warning("[store] save_pages(%s) failed", run_id, exc_info=True)


# ── events / telemetry (fire-and-forget) ─────────────────────────────────────


def insert_event(run_id: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
    """Durable lifecycle/SSE event. Fire-and-forget — safe from any thread."""
    try:
        get_db().enqueue(
            "INSERT INTO run_events (run_id, event, data_json, ts) VALUES (?,?,?,?)",
            (run_id, event, json.dumps(data or {}, default=str), _now()),
        )
    except Exception:  # noqa: BLE001
        pass


def insert_timing(row: Dict[str, Any]) -> None:
    """Insert one stage_timings row. Fire-and-forget; never raises."""
    try:
        get_db().enqueue(
            "INSERT INTO stage_timings "
            "(run_id, page_url, depth, stage, sub_stage, rule, duration_ms, "
            " item_count, status, error, extra_json, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                row.get("run_id"),
                row.get("page_url"),
                row.get("depth"),
                row.get("stage"),
                row.get("sub_stage"),
                row.get("rule"),
                row.get("duration_ms"),
                row.get("item_count"),
                row.get("status"),
                row.get("error"),
                json.dumps(row.get("extra"), default=str) if row.get("extra") else None,
                row.get("ts") or _now(),
            ),
        )
    except Exception:  # noqa: BLE001
        pass


# ── reads (propagate errors to API layer) ────────────────────────────────────


async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    return await get_db().query_one("SELECT * FROM runs WHERE run_id=?", (run_id,))


async def list_runs(
    *,
    limit: int = 50,
    offset: int = 0,
    url: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    where = []
    params: List[Any] = []
    if url:
        where.append("url LIKE ?")
        params.append(f"%{url}%")
    if status:
        where.append("status=?")
        params.append(status)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])
    rows = await get_db().query(
        f"SELECT run_id, url, status, lang_resolved, wcag_level, max_depth, "
        f"max_pages, submitted_at, run_started_at, completed_at, queue_wait_ms, "
        f"wall_ms, summary_json, error_stage FROM runs{clause} "
        f"ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
        params,
    )
    for r in rows:
        if r.get("summary_json"):
            try:
                r["summary"] = json.loads(r.pop("summary_json"))
            except Exception:  # noqa: BLE001
                r["summary"] = None
    return rows


async def get_report(run_id: str) -> Optional[Dict[str, Any]]:
    row = await get_db().query_one(
        "SELECT report_zlib FROM run_reports WHERE run_id=?", (run_id,)
    )
    if not row or row.get("report_zlib") is None:
        return None
    try:
        return json.loads(zlib.decompress(row["report_zlib"]).decode("utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("[store] get_report(%s) decompress failed", run_id, exc_info=True)
        return None


async def get_events(run_id: str) -> List[Dict[str, Any]]:
    rows = await get_db().query(
        "SELECT event, data_json, ts FROM run_events WHERE run_id=? ORDER BY id",
        (run_id,),
    )
    for r in rows:
        if r.get("data_json"):
            try:
                r["data"] = json.loads(r.pop("data_json"))
            except Exception:  # noqa: BLE001
                r["data"] = {}
    return rows


async def get_timings(run_id: str) -> List[Dict[str, Any]]:
    return await get_db().query(
        "SELECT page_url, depth, stage, sub_stage, rule, duration_ms, item_count, "
        "status, error, ts FROM stage_timings WHERE run_id=? ORDER BY id",
        (run_id,),
    )


# ── queue / crash recovery ───────────────────────────────────────────────────


async def requeue_running() -> List[Dict[str, Any]]:
    """On boot, move orphaned ``running`` rows back to ``queued`` (or fail them
    if they've exhausted their attempt budget). Returns the rows requeued."""
    import os

    max_attempts = int(os.getenv("KA11Y_MAX_ATTEMPTS", "2"))
    orphans = await get_db().query(
        "SELECT run_id, attempt FROM runs WHERE status IN ('running','queued')"
    )
    requeued: List[Dict[str, Any]] = []
    for o in orphans:
        attempt = (o.get("attempt") or 0) + 1
        if attempt > max_attempts:
            await update_run(
                o["run_id"],
                status="failed",
                error_stage="crash_recovery",
                error_id="max_attempts_exceeded",
                completed_at=_now(),
            )
        else:
            await update_run(o["run_id"], status="queued", attempt=attempt)
            requeued.append(o)
    return requeued


async def next_queued(limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    return await get_db().query(
        "SELECT run_id, url, params_json, lang_requested, wcag_level "
        "FROM runs WHERE status='queued' ORDER BY submitted_at LIMIT ?",
        (limit,),
    )


async def count_running() -> int:
    row = await get_db().query_one(
        "SELECT COUNT(*) AS n FROM runs WHERE status='running'"
    )
    return int(row["n"]) if row else 0


async def is_cancelled(run_id: str) -> bool:
    row = await get_db().query_one("SELECT status FROM runs WHERE run_id=?", (run_id,))
    return bool(row and row.get("status") == "cancelled")


# ── retention ────────────────────────────────────────────────────────────────


async def retention_sweep(retention_days: int) -> List[str]:
    """Delete runs older than *retention_days*. ON DELETE CASCADE clears child
    rows. Returns the run_ids removed so the caller can prune asset files."""
    cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
    cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
    victims = await get_db().query(
        "SELECT run_id FROM runs WHERE submitted_at < ? "
        "AND status IN ('completed','failed','cancelled')",
        (cutoff_iso,),
    )
    ids = [v["run_id"] for v in victims]
    for rid in ids:
        await get_db().execute("DELETE FROM runs WHERE run_id=?", (rid,))
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
    if status == "needs_review":
        await get_db().execute(
            "DELETE FROM finding_reviews WHERE run_id=? AND finding_id=?",
            (run_id, finding_id),
        )
        return
    await get_db().execute(
        "INSERT INTO finding_reviews "
        "(run_id, finding_id, status, note, reviewer, wcag_sc, page_url, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT(run_id, finding_id) DO UPDATE SET "
        "  status=excluded.status, note=excluded.note, reviewer=excluded.reviewer, "
        "  updated_at=excluded.updated_at",
        (run_id, finding_id, status, note, reviewer, wcag_sc, page_url, _now()),
    )


async def get_reviews(run_id: str) -> Dict[str, Dict[str, Any]]:
    """Return ``{finding_id: {status, note, reviewer, updated_at}}`` for a run."""
    rows = await get_db().query(
        "SELECT finding_id, status, note, reviewer, updated_at "
        "FROM finding_reviews WHERE run_id=?",
        (run_id,),
    )
    return {r["finding_id"]: r for r in rows}


async def list_run_assets(run_id: str) -> List[Dict[str, Any]]:
    return await get_db().query(
        "SELECT id, page_url, kind, rel_path, sha256, mime, width, height, bytes "
        "FROM assets WHERE run_id=? ORDER BY id",
        (run_id,),
    )
