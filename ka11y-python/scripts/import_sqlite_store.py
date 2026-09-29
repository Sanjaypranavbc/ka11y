#!/usr/bin/env python3
"""
scripts/import_sqlite_store.py
==============================
One-off: copy the history from the retired SQLite run store into PostgreSQL.

Until 2026-09-28 every audit was written to two places — ``runs`` (+ report,
findings, pages, assets, verdicts, events, timings) in ``ka11y.db`` and an
``audit_jobs`` ownership row in PostgreSQL. The SQLite side is gone; this
script moves what only it had (report JSON, findings, pages, asset index,
manual verdicts, telemetry, run parameters/timings) onto the ``audit_jobs``
rows that already exist, and creates jobs (anonymous) for runs PostgreSQL
never saw. Idempotent: rows that are already there are left alone.

Run it from the host, once, after the stack has started at least once on the
new schema (so migration 0004 has been applied to the ``ka11y`` database):

    cd ka11y-python
    DATABASE_URL=postgresql://ka11y:<password>@127.0.0.1:5432/ka11y \\
        python scripts/import_sqlite_store.py ../output/db/ka11y.db --dry-run
    # same command without --dry-run to write

The old file lives at ./output/db/ka11y.db on the host (the compose bind
mount of the retired store). Once imported the directory can be removed.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("KA11Y_LOAD_DOTENV", "0")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ka11y.db.engine import database_url  # noqa: E402
from ka11y.db.models import (  # noqa: E402
    AuditAsset,
    AuditFail,
    AuditJob,
    AuditLog,
    AuditPage,
    AuditResult,
    AuditSummary,
    FindingReview,
    StageTiming,
)

_SEVERITY_ALIAS = {
    "critical": "critical", "serious": "serious", "high": "serious",
    "moderate": "moderate", "medium": "moderate", "minor": "minor", "low": "minor",
}


def _uuid(value: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _json(value: Any) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        out = json.loads(value)
        return out if isinstance(out, dict) else None
    except (TypeError, ValueError):
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def import_store(sqlite_path: Path, *, dry_run: bool = False) -> Dict[str, int]:
    url = database_url()
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    engine = create_engine(url)
    counts = {k: 0 for k in ("jobs_created", "jobs_updated", "skipped_non_uuid", "results", "findings",
                             "pages", "assets", "reviews", "events", "timings")}

    with Session(engine) as s:
        have_results = {row[0] for row in s.execute(select(AuditResult.job_id)).all()}
        have_fails = {row[0] for row in s.execute(select(AuditFail.job_id).distinct()).all()}
        have_pages = {row[0] for row in s.execute(select(AuditPage.job_id).distinct()).all()}
        have_timings = {row[0] for row in s.execute(select(StageTiming.job_id).distinct()).all()}
        have_assets = {(row[0], row[1]) for row in s.execute(select(AuditAsset.job_id, AuditAsset.rel_path)).all()}

        # ── runs → audit_jobs ─────────────────────────────────────────────
        run_ids: Dict[str, uuid.UUID] = {}
        for r in src.execute("SELECT * FROM runs"):
            jid = _uuid(r["run_id"])
            if jid is None:
                counts["skipped_non_uuid"] += 1
                continue
            run_ids[r["run_id"]] = jid
            summary = _json(r["summary_json"])
            params = _json(r["params_json"]) or {}
            job = s.get(AuditJob, jid)
            if job is None:
                job = AuditJob(
                    id=jid, user_id=None, target_url=r["url"], status=r["status"],
                    crawl_depth=int(r["max_depth"] or 0), requested_pages=r["max_pages"],
                    created_at=_ts(r["submitted_at"]) or _ts(r["created_at"]) or datetime.now(timezone.utc),
                )
                s.add(job)
                counts["jobs_created"] += 1
            else:
                counts["jobs_updated"] += 1
            # Only fill what PostgreSQL never had; never override a newer status.
            if job.status in (None, "queued", "running") and r["status"]:
                job.status = r["status"]
            job.lang_requested = job.lang_requested or r["lang_requested"]
            job.lang_resolved = job.lang_resolved or r["lang_resolved"]
            job.wcag_level = job.wcag_level or r["wcag_level"]
            if not job.params:
                job.params = params
            job.started_at = job.started_at or _ts(r["run_started_at"])
            job.completed_at = job.completed_at or _ts(r["completed_at"])
            job.queue_wait_ms = job.queue_wait_ms if job.queue_wait_ms is not None else r["queue_wait_ms"]
            job.wall_ms = job.wall_ms if job.wall_ms is not None else r["wall_ms"]
            job.error_id = job.error_id or r["error_id"]
            job.error_stage = job.error_stage or r["error_stage"]
            job.attempt = job.attempt or int(r["attempt"] or 0)
            job.worker_pid = job.worker_pid or r["worker_pid"]
            job.output_dir = job.output_dir or r["output_dir"]
            if summary and not job.summary:
                job.summary = summary
                if s.execute(select(AuditSummary.id).where(AuditSummary.job_id == jid)).first() is None:
                    sev = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
                    for key, n in (summary.get("by_severity") or {}).items():
                        mapped = _SEVERITY_ALIAS.get(str(key).lower())
                        if mapped:
                            sev[mapped] += int(n or 0)
                    s.add(AuditSummary(
                        job_id=jid, total_pages=int(summary.get("page_count") or 0),
                        total_fails=int(summary.get("violations") or 0),
                        failed_count=int(summary.get("violations") or 0),
                        passed_count=int(summary.get("passes") or 0),
                        needs_review_count=int(summary.get("needs_review") or 0),
                        critical_count=sev["critical"], serious_count=sev["serious"],
                        moderate_count=sev["moderate"], minor_count=sev["minor"],
                        duration_ms=r["wall_ms"],
                    ))
        s.flush()

        # ── run_reports → audit_results ───────────────────────────────────
        for r in src.execute("SELECT run_id, report_zlib, bytes_raw, bytes_stored, created_at FROM run_reports"):
            jid = run_ids.get(r["run_id"])
            if jid is None or jid in have_results:
                continue
            s.add(AuditResult(job_id=jid, report_zlib=r["report_zlib"], bytes_raw=r["bytes_raw"],
                              bytes_stored=r["bytes_stored"], created_at=_ts(r["created_at"]) or datetime.now(timezone.utc)))
            counts["results"] += 1

        # ── findings → audit_fails (fail + needs_review only) ─────────────
        cols = _columns(src, "findings")
        sev_col = "severity" if "severity" in cols else "NULL AS severity"
        for r in src.execute(
            f"SELECT run_id, page_url, wcag_sc, level, status, source, reason_code, selector, element_json, "
            f"created_at, {sev_col} FROM findings WHERE status IN ('fail','needs_review')"
        ):
            jid = run_ids.get(r["run_id"])
            if jid is None or jid in have_fails:
                continue
            s.add(AuditFail(
                job_id=jid, page_url=r["page_url"], wcag_sc=r["wcag_sc"], level=r["level"], status=r["status"],
                needs_review=r["status"] == "needs_review", source=r["source"], reason_code=r["reason_code"],
                severity=r["severity"], selector=r["selector"], element=_json(r["element_json"]),
                created_at=_ts(r["created_at"]) or datetime.now(timezone.utc),
            ))
            counts["findings"] += 1

        # ── run_pages → audit_pages ───────────────────────────────────────
        for r in src.execute("SELECT run_id, page_url, depth, http_status, crawl_ms, snapshot_ref FROM run_pages"):
            jid = run_ids.get(r["run_id"])
            if jid is None or jid in have_pages or not r["page_url"]:
                continue
            s.add(AuditPage(job_id=jid, url=r["page_url"], depth=r["depth"], status_code=r["http_status"],
                            crawl_ms=r["crawl_ms"], snapshot_ref=r["snapshot_ref"], scan_status="completed"))
            counts["pages"] += 1

        # ── assets → audit_assets ─────────────────────────────────────────
        acols = _columns(src, "assets")
        key_cols = "object_key, object_bucket" if "object_key" in acols else "NULL AS object_key, NULL AS object_bucket"
        for r in src.execute(
            f"SELECT run_id, page_url, kind, rel_path, sha256, mime, width, height, bytes, created_at, {key_cols} "
            f"FROM assets ORDER BY id"
        ):
            jid = run_ids.get(r["run_id"])
            if jid is None or (jid, r["rel_path"]) in have_assets:
                continue
            s.add(AuditAsset(job_id=jid, page_url=r["page_url"], kind=r["kind"], rel_path=r["rel_path"],
                             sha256=r["sha256"], mime=r["mime"], width=r["width"], height=r["height"],
                             bytes=r["bytes"], object_key=r["object_key"], object_bucket=r["object_bucket"],
                             created_at=_ts(r["created_at"]) or datetime.now(timezone.utc)))
            counts["assets"] += 1

        # ── finding_reviews ───────────────────────────────────────────────
        if _table_exists(src, "finding_reviews"):
            for r in src.execute("SELECT * FROM finding_reviews"):
                jid = run_ids.get(r["run_id"])
                if jid is None:
                    continue
                stmt = pg_insert(FindingReview).values(
                    job_id=jid, finding_id=r["finding_id"], status=r["status"], note=r["note"],
                    reviewer=r["reviewer"], wcag_sc=r["wcag_sc"], page_url=r["page_url"],
                    updated_at=_ts(r["updated_at"]) or datetime.now(timezone.utc),
                ).on_conflict_do_nothing(index_elements=[FindingReview.job_id, FindingReview.finding_id])
                counts["reviews"] += s.execute(stmt).rowcount or 0

        # ── run_events → audit_logs (only for jobs PostgreSQL never logged) ─
        logged = {row[0] for row in s.execute(select(AuditLog.job_id).distinct()).all()}
        for r in src.execute("SELECT run_id, event, data_json, ts FROM run_events ORDER BY id"):
            jid = run_ids.get(r["run_id"])
            if jid is None or jid in logged:
                continue
            s.add(AuditLog(job_id=jid, event_type=str(r["event"])[:100], metadata_=_json(r["data_json"]),
                           created_at=_ts(r["ts"]) or datetime.now(timezone.utc)))
            counts["events"] += 1

        # ── stage_timings ─────────────────────────────────────────────────
        for r in src.execute("SELECT * FROM stage_timings ORDER BY id"):
            jid = run_ids.get(r["run_id"])
            if jid is None or jid in have_timings or not r["stage"]:
                continue
            s.add(StageTiming(job_id=jid, page_url=r["page_url"], depth=r["depth"], stage=str(r["stage"])[:100],
                              sub_stage=r["sub_stage"], rule=r["rule"], duration_ms=r["duration_ms"],
                              item_count=r["item_count"], status=r["status"], error=r["error"],
                              extra=_json(r["extra_json"]), ts=_ts(r["ts"]) or datetime.now(timezone.utc)))
            counts["timings"] += 1

        if dry_run:
            s.rollback()
        else:
            s.commit()
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sqlite_path", type=Path, help="path to the old ka11y.db")
    ap.add_argument("--dry-run", action="store_true", help="count what would be imported, write nothing")
    args = ap.parse_args()
    if not args.sqlite_path.is_file():
        print(f"not a file: {args.sqlite_path}", file=sys.stderr)
        return 2
    counts = import_store(args.sqlite_path, dry_run=args.dry_run)
    label = "would import" if args.dry_run else "imported"
    print(f"{label}: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
