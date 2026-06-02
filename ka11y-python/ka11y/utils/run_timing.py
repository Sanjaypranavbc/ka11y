"""
ka11y/utils/run_timing.py
=========================
Per-run timing log. After each combined audit finishes (success *or* failure),
:func:`log_run_timing` computes the queue wait, the per-stage durations, and the
total wall time from the timestamps already captured in the job store, and
appends one human-readable block to a persistent log file:

    ka11y-python/logs/run_timings.log      (override with $KA11Y_RUN_TIMING_LOG)

Unlike ``crawler_timings.log`` (written into the per-job ``output_dir``, which is
TTL-swept by the store), this file lives in the durable ``logs/`` directory so
the timing history survives job eviction — you can just tail it:

    tail -f logs/run_timings.log

Nothing here can fail an audit: every path is wrapped so a logging error is
swallowed and logged, never raised.

Note on durations: the axe-core and Python branches run **concurrently**
(``asyncio.gather``), and several Python stages overlap too, so the per-stage
durations do **not** sum to the wall time. ``WALL`` is the real elapsed time;
the per-stage rows show where each stage spent its own time.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="run_timing")

# Single append lock — concurrent jobs (up to KA11Y_MAX_CONCURRENT_JOBS) may
# finish at the same moment and must not interleave their blocks.
_write_lock = threading.Lock()

_W_STAGE = 26
_W_STATUS = 11
_W_DUR = 10
_W_CRAWL = 10
_W_FIND = 9


def _log_path() -> Path:
    override = os.getenv("KA11Y_RUN_TIMING_LOG")
    if override:
        return Path(override)
    # Same logs/ dir the rotating app logger uses (ka11y-python/logs/).
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    return log_dir / "run_timings.log"


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Accept both "+00:00" and a trailing "Z".
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _delta_s(a: Optional[str], b: Optional[str]) -> Optional[float]:
    """Seconds between ISO timestamps *a*→*b* (None if either is missing)."""
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    return (db - da).total_seconds()


def _fmt_dur(seconds: Optional[float]) -> str:
    return "—" if seconds is None else f"{seconds:.2f}s"


def _round(seconds: Optional[float]) -> Optional[float]:
    return None if seconds is None else round(seconds, 2)


def compute_run_timing(
    *,
    job_id: str,
    url: str,
    status: str,
    stages: list[dict[str, Any]],
    submitted_at: Optional[str],
    run_started_at: Optional[str],
    completed_at: Optional[str],
    lang: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
    error_stage: Optional[str] = None,
) -> dict[str, Any]:
    """Build the structured timing for a run from already-recorded timestamps.

    This is the single source of truth shared by :func:`log_run_timing` (which
    formats it into the text log) and the ``GET /combined/{job_id}/timings``
    API endpoint (which returns it as JSON), so the file and the API never drift.

    Measures nothing itself — it only derives durations from the timestamps the
    runner/stage-events already captured, so it is safe to call at any time
    (including mid-run, where unfinished stages report ``duration_s: null``).
    """
    stage_rows: list[dict[str, Any]] = []
    for s in stages or []:
        stage_rows.append(
            {
                "name": s.get("name"),
                "status": s.get("status"),
                "started_at": s.get("started_at"),
                "completed_at": s.get("completed_at"),
                "duration_s": _round(_delta_s(s.get("started_at"), s.get("completed_at"))),
                "crawler_duration_s": s.get("crawler_duration_s"),
                "findings_count": s.get("findings_count"),
            }
        )

    return {
        "job_id": job_id,
        "url": url,
        "status": status,
        "lang": lang,
        "error_stage": error_stage,
        "submitted_at": submitted_at,
        "run_started_at": run_started_at,
        "completed_at": completed_at,
        "queue_wait_s": _round(_delta_s(submitted_at, run_started_at)),
        "run_s": _round(_delta_s(run_started_at, completed_at)),
        "wall_s": _round(_delta_s(submitted_at, completed_at)),
        "stages": stage_rows,
        "summary": summary or None,
    }


def _format_run_timing_block(data: dict[str, Any]) -> str:
    """Render a :func:`compute_run_timing` dict into one human-readable block."""
    summary = data.get("summary") or {}
    score = summary.get("score")
    score_s = "—" if score is None else f"{score}"

    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(
        f"RUN {data.get('completed_at') or datetime.utcnow().isoformat()}  "
        f"job={str(data.get('job_id', ''))[:8]}  status={data.get('status')}  "
        f"lang={data.get('lang') or '—'}"
    )
    lines.append(f"  url={data.get('url')}")
    if summary:
        lines.append(
            f"  score={score_s}  findings={summary.get('total_findings', '—')} "
            f"(V={summary.get('violations', '—')} "
            f"NR={summary.get('needs_review', '—')} "
            f"P={summary.get('passes', '—')})  "
            f"pages={summary.get('page_count', '—')}"
        )
    if data.get("error_stage"):
        lines.append(f"  failed_stage={data['error_stage']}")

    # Per-stage table
    lines.append(
        f"  {'Stage':<{_W_STAGE}}{'Status':<{_W_STATUS}}"
        f"{'Duration':>{_W_DUR}}{'Crawl':>{_W_CRAWL}}{'Findings':>{_W_FIND}}"
    )
    lines.append(f"  {'-' * (_W_STAGE + _W_STATUS + _W_DUR + _W_CRAWL + _W_FIND)}")
    for s in data.get("stages") or []:
        name = str(s.get("name", "?"))[: _W_STAGE - 1]
        st = str(s.get("status", "?"))[: _W_STATUS - 1]
        fc = s.get("findings_count")
        fc_s = "—" if fc is None else str(fc)
        crawl = s.get("crawler_duration_s")
        crawl_s = _fmt_dur(crawl) if crawl is not None else "—"
        lines.append(
            f"  {name:<{_W_STAGE}}{st:<{_W_STATUS}}"
            f"{_fmt_dur(s.get('duration_s')):>{_W_DUR}}{crawl_s:>{_W_CRAWL}}{fc_s:>{_W_FIND}}"
        )

    lines.append(f"  {'-' * (_W_STAGE + _W_STATUS + _W_DUR + _W_CRAWL + _W_FIND)}")
    lines.append(f"  queue_wait (submitted→start) : {_fmt_dur(data.get('queue_wait_s'))}")
    lines.append(f"  RUN        (start→completed) : {_fmt_dur(data.get('run_s'))}")
    lines.append(f"  WALL       (submitted→done)  : {_fmt_dur(data.get('wall_s'))}")
    lines.append("")
    return "\n".join(lines) + "\n"


def log_run_timing(
    *,
    job_id: str,
    url: str,
    status: str,
    stages: list[dict[str, Any]],
    submitted_at: Optional[str],
    run_started_at: Optional[str],
    completed_at: Optional[str],
    lang: Optional[str] = None,
    summary: Optional[dict[str, Any]] = None,
    error_stage: Optional[str] = None,
) -> None:
    """Append one timing block for a finished run to the run-timings log.

    Reads the timestamps the runner/stage-events already recorded — it does not
    measure anything itself, so it adds no overhead to the audit path.
    """
    try:
        data = compute_run_timing(
            job_id=job_id,
            url=url,
            status=status,
            stages=stages,
            submitted_at=submitted_at,
            run_started_at=run_started_at,
            completed_at=completed_at,
            lang=lang,
            summary=summary,
            error_stage=error_stage,
        )
        wall = data["wall_s"]
        run_dur = data["run_s"]
        queue_wait = data["queue_wait_s"]

        # P3: mirror the computed aggregate into the durable run_events table so
        # the per-run timing summary is queryable (and survives TTL/restart),
        # not only tailable from run_timings.log. Fire-and-forget; never raises.
        try:
            from ka11y.store import repo

            repo.insert_event(job_id, "run_timing", data)
        except Exception:  # noqa: BLE001
            pass

        if os.environ.get("KA11Y_TELEMETRY_FILES", "1") != "0":
            block = _format_run_timing_block(data)
            path = _log_path()
            with _write_lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(block)

        # Also emit a one-line summary to the app log for quick grepping.
        logger.info(
            "[run_timing] job=%s status=%s wall=%s run=%s queue=%s → %s",
            job_id[:8],
            status,
            _fmt_dur(wall),
            _fmt_dur(run_dur),
            _fmt_dur(queue_wait),
            path,
        )
    except Exception as exc:  # never let timing logging break a run
        logger.warning("[run_timing] failed to write timing log: %s", exc)
