"""
ka11y/utils/stage_timing.py
===========================
Low-level per-(page, stage, sub_stage, rule) timing logger.

Where the existing :mod:`ka11y.utils.run_timing` writes one **aggregate** block
per run and :mod:`ka11y.utils.crawler_timing` writes one row per crawler
invocation, this module writes **one row per fine-grained step** so you can
answer questions like:

    * "On which page did rule 1.4.3 spend most of its time?"
    * "Why did this depth=1 run take 3× longer than the depth=0 run?"
    * "Was OCR the bottleneck on page X or was it the contrast converter?"

Two files per run, both under ``ka11y-python/logs/timings/``:

    <run_id>.jsonl           — one JSON object per step (machine-parseable)
    <run_id>.summary.log     — human-readable per-page → per-stage breakdown
                                emitted at the end of the run

Override the directory with ``$KA11Y_STAGE_TIMING_DIR``. Disable entirely with
``KA11Y_STAGE_TIMING_DISABLE=1``.

JSONL row schema
----------------
::

    {
      "ts":          "2026-05-29T10:42:18.731+00:00",
      "run_id":      "ka11y-abc123",
      "page_url":    "https://example.com/child" | null,
      "depth":       1 | null,
      "stage":       "image_audit",
      "sub_stage":   "ocr_scan" | "page_capture" | null,
      "rule":        "1.4.3" | null,
      "duration_ms": 123.4,
      "item_count":  42 | null,
      "status":      "ok" | "error" | "timeout",
      "error":       null | "msg",
      "extra":       {...}      # free-form per-stage extras
    }

Safety guarantees
-----------------
*   Every write is wrapped in try/except. A logging failure must never break
    an audit. Errors are logged via the standard ka11y logger.
*   Per-file ``threading.Lock`` so concurrent stages cannot interleave rows.
*   No mutation of the audit result. The module is purely observational.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="stage_timing")

_DISABLE_ENV = "KA11Y_STAGE_TIMING_DISABLE"
_DIR_ENV = "KA11Y_STAGE_TIMING_DIR"

# Per-file write locks. Concurrent stages may finish at the same instant.
_locks: Dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _is_disabled() -> bool:
    return os.getenv(_DISABLE_ENV, "").strip() in {"1", "true", "yes", "on"}


def _timings_dir() -> Path:
    override = os.getenv(_DIR_ENV)
    if override:
        return Path(override)
    # Sibling of run_timings.log / KAC_*.log for consistency.
    return Path(__file__).resolve().parent.parent.parent / "logs" / "timings"


def _lock_for(path: str) -> threading.Lock:
    with _registry_lock:
        lock = _locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _locks[path] = lock
        return lock


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _jsonl_path(run_id: str) -> Path:
    return _timings_dir() / f"{_safe_run_id(run_id)}.jsonl"


def _summary_path(run_id: str) -> Path:
    return _timings_dir() / f"{_safe_run_id(run_id)}.summary.log"


def _safe_run_id(run_id: str) -> str:
    # Strip path separators / control characters so a malicious run_id cannot
    # escape the timings dir.
    return "".join(c for c in (run_id or "unknown") if c.isalnum() or c in "-_.") or "unknown"


def _files_enabled() -> bool:
    """JSONL/summary files are opt-out (P3). Set KA11Y_TELEMETRY_FILES=0 in prod
    to keep telemetry in SQLite only and avoid unbounded log-file growth."""
    return os.environ.get("KA11Y_TELEMETRY_FILES", "1") != "0"


def _write_row(run_id: str, row: Dict[str, Any]) -> None:
    if _is_disabled():
        return
    # P3: mirror every fine-grained step into the durable stage_timings table
    # (fire-and-forget; never blocks or raises). This is the queryable sink that
    # /admin/metrics and /{run_id}/timings read from.
    try:
        from ka11y.store import repo

        repo.insert_timing(row)
    except Exception:  # noqa: BLE001
        pass

    if not _files_enabled():
        return
    try:
        path = _jsonl_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = _lock_for(str(path))
        with lock, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str))
            fh.write("\n")
    except Exception as exc:  # noqa: BLE001 - logging failure must never raise
        logger.warning("stage_timing: failed to write row: %s", exc)


def record(
    run_id: str,
    *,
    stage: str,
    duration_ms: float,
    status: str = "ok",
    page_url: Optional[str] = None,
    depth: Optional[int] = None,
    sub_stage: Optional[str] = None,
    rule: Optional[str] = None,
    item_count: Optional[int] = None,
    error: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a single timing row. Safe to call from any thread or coroutine."""
    row = {
        "ts": _now_iso(),
        "run_id": run_id,
        "page_url": page_url,
        "depth": depth,
        "stage": stage,
        "sub_stage": sub_stage,
        "rule": rule,
        "duration_ms": round(duration_ms, 3),
        "item_count": item_count,
        "status": status,
        "error": error,
        "extra": extra or {},
    }
    _write_row(run_id, row)


@asynccontextmanager
async def time_stage_async(
    run_id: str,
    stage: str,
    *,
    page_url: Optional[str] = None,
    depth: Optional[int] = None,
    sub_stage: Optional[str] = None,
    rule: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    """Async context manager: records duration on exit (even on exception)."""
    start = time.perf_counter()
    status = "ok"
    err: Optional[str] = None
    try:
        yield
    except Exception as exc:
        status = "error"
        err = repr(exc)[:200]
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        record(
            run_id,
            stage=stage,
            duration_ms=duration_ms,
            status=status,
            page_url=page_url,
            depth=depth,
            sub_stage=sub_stage,
            rule=rule,
            error=err,
            extra=extra,
        )


@contextmanager
def time_stage(
    run_id: str,
    stage: str,
    *,
    page_url: Optional[str] = None,
    depth: Optional[int] = None,
    sub_stage: Optional[str] = None,
    rule: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Iterator[None]:
    """Sync context manager analogue of :func:`time_stage_async`."""
    start = time.perf_counter()
    status = "ok"
    err: Optional[str] = None
    try:
        yield
    except Exception as exc:
        status = "error"
        err = repr(exc)[:200]
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        record(
            run_id,
            stage=stage,
            duration_ms=duration_ms,
            status=status,
            page_url=page_url,
            depth=depth,
            sub_stage=sub_stage,
            rule=rule,
            error=err,
            extra=extra,
        )


# ── Summary emission ────────────────────────────────────────────────────────


def _load_rows(run_id: str) -> List[Dict[str, Any]]:
    path = _jsonl_path(run_id)
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("stage_timing: failed to load rows: %s", exc)
    return rows


def emit_summary(run_id: str) -> Optional[Path]:
    """
    Render a human-readable per-page → per-stage summary log alongside the
    JSONL. Safe to call multiple times — overwrites the summary file.
    Returns the summary path on success, or None on failure / disabled.
    """
    if _is_disabled():
        return None
    try:
        rows = _load_rows(run_id)
        if not rows:
            return None

        # Aggregate: stage → total ms, count
        # Aggregate: (page_url, stage) → total ms, count
        # Aggregate: (page_url, stage, rule) → total ms, count
        stage_totals: Dict[str, List[float]] = defaultdict(list)
        page_stage: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        page_stage_rule: Dict[str, Dict[str, Dict[str, List[float]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )

        total_ms = 0.0
        for r in rows:
            dur = float(r.get("duration_ms") or 0.0)
            stage = r.get("stage") or "?"
            page = r.get("page_url") or "—"
            rule = r.get("rule") or "—"
            stage_totals[stage].append(dur)
            page_stage[page][stage].append(dur)
            page_stage_rule[page][stage][rule].append(dur)
            total_ms += dur

        out = _summary_path(run_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append(f"# ka11y stage timing summary — run_id={run_id}")
        lines.append(f"# generated: {_now_iso()}")
        lines.append(f"# rows: {len(rows)}    summed duration: {total_ms / 1000.0:.2f}s")
        lines.append(
            "# note: summed != wall time (stages run concurrently via asyncio.gather)"
        )
        lines.append("")
        lines.append("## Stage totals (sum across all pages)")
        lines.append(
            f"{'stage':<32} {'total_s':>10} {'count':>8} {'mean_ms':>10} {'max_ms':>10}"
        )
        lines.append("-" * 72)
        for stage in sorted(stage_totals, key=lambda s: -sum(stage_totals[s])):
            durs = stage_totals[stage]
            total = sum(durs)
            mean = total / len(durs) if durs else 0.0
            mx = max(durs) if durs else 0.0
            lines.append(
                f"{stage:<32} {total / 1000.0:>10.2f} {len(durs):>8} "
                f"{mean:>10.1f} {mx:>10.1f}"
            )
        lines.append("")

        lines.append("## Per-page breakdown")
        for page in sorted(page_stage):
            page_total = sum(sum(v) for v in page_stage[page].values())
            lines.append("")
            lines.append(f"### {page}    (total {page_total / 1000.0:.2f}s)")
            lines.append(
                f"  {'stage':<30} {'total_s':>10} {'count':>8} {'top_rule':>20} {'rule_s':>10}"
            )
            lines.append("  " + "-" * 80)
            for stage in sorted(
                page_stage[page], key=lambda s: -sum(page_stage[page][s])
            ):
                durs = page_stage[page][stage]
                total = sum(durs)
                # Find the heaviest rule for this (page, stage)
                rules = page_stage_rule[page][stage]
                if rules:
                    top_rule = max(rules, key=lambda k: sum(rules[k]))
                    top_dur = sum(rules[top_rule])
                else:
                    top_rule = "—"
                    top_dur = 0.0
                lines.append(
                    f"  {stage:<30} {total / 1000.0:>10.2f} {len(durs):>8} "
                    f"{top_rule:>20} {top_dur / 1000.0:>10.2f}"
                )
        lines.append("")

        path = str(out)
        lock = _lock_for(path)
        with lock, out.open("w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("stage_timing: failed to emit summary: %s", exc)
        return None


__all__ = [
    "record",
    "time_stage",
    "time_stage_async",
    "emit_summary",
]
