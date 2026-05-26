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
        queue_wait = _delta_s(submitted_at, run_started_at)
        run_dur = _delta_s(run_started_at, completed_at)
        wall = _delta_s(submitted_at, completed_at)

        summary = summary or {}
        score = summary.get("score")
        score_s = "—" if score is None else f"{score}"

        lines: list[str] = []
        lines.append("=" * 78)
        head = (
            f"RUN {completed_at or datetime.utcnow().isoformat()}  "
            f"job={job_id[:8]}  status={status}  lang={lang or '—'}"
        )
        lines.append(head)
        lines.append(f"  url={url}")
        if summary:
            lines.append(
                f"  score={score_s}  findings={summary.get('total_findings', '—')} "
                f"(V={summary.get('violations', '—')} "
                f"NR={summary.get('needs_review', '—')} "
                f"P={summary.get('passes', '—')})  "
                f"pages={summary.get('page_count', '—')}"
            )
        if error_stage:
            lines.append(f"  failed_stage={error_stage}")

        # Per-stage table
        lines.append(
            f"  {'Stage':<{_W_STAGE}}{'Status':<{_W_STATUS}}"
            f"{'Duration':>{_W_DUR}}{'Findings':>{_W_FIND}}"
        )
        lines.append(f"  {'-' * (_W_STAGE + _W_STATUS + _W_DUR + _W_FIND)}")
        for s in stages or []:
            name = str(s.get("name", "?"))[:_W_STAGE - 1]
            st = str(s.get("status", "?"))[:_W_STATUS - 1]
            dur = _delta_s(s.get("started_at"), s.get("completed_at"))
            fc = s.get("findings_count")
            fc_s = "—" if fc is None else str(fc)
            lines.append(
                f"  {name:<{_W_STAGE}}{st:<{_W_STATUS}}"
                f"{_fmt_dur(dur):>{_W_DUR}}{fc_s:>{_W_FIND}}"
            )

        lines.append(f"  {'-' * (_W_STAGE + _W_STATUS + _W_DUR + _W_FIND)}")
        lines.append(f"  queue_wait (submitted→start) : {_fmt_dur(queue_wait)}")
        lines.append(f"  RUN        (start→completed) : {_fmt_dur(run_dur)}")
        lines.append(f"  WALL       (submitted→done)  : {_fmt_dur(wall)}")
        lines.append("")

        block = "\n".join(lines) + "\n"
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
