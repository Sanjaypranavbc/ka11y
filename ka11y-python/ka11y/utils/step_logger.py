from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="step_logger")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_step_log(
    path: str | Path | None,
    *,
    step: str,
    status: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    if not path:
        return None

    log_path = Path(path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp": _utc_now(),
        "step": step,
        "status": status,
        "message": message,
        "context": context or {},
    }

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return str(log_path)


class ExecutionStepLogger:
    def __init__(
        self,
        *,
        output_dir: Path,
        name: str,
        job_id: str | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.name = name
        self.job_id = job_id
        self.steps_dir = self.output_dir / "step_logs"
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.steps_dir / f"{name}.jsonl"
        self.summary_path = self.steps_dir / f"{name}_summary.json"
        self._counts = {"running": 0, "completed": 0, "warning": 0, "error": 0}

    def record(
        self,
        *,
        step: str,
        status: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        ctx = dict(context or {})
        if self.job_id:
            ctx.setdefault("job_id", self.job_id)
        append_step_log(
            self.jsonl_path,
            step=step,
            status=status,
            message=message,
            context=ctx,
        )
        self._counts[status] = self._counts.get(status, 0) + 1

        if status == "error":
            logger.error(f"{step}: {message}")
        elif status == "warning":
            logger.warning(f"{step}: {message}")
        elif status == "completed":
            logger.success(f"{step}: {message}")
        else:
            logger.processing(f"{step}: {message}")

    def finalize(
        self, *, status: str, message: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        self.record(step=self.name, status=status, message=message, context=context)
        summary = {
            "name": self.name,
            "job_id": self.job_id,
            "status": status,
            "message": message,
            "counts": self._counts,
            "jsonl_path": str(self.jsonl_path),
            "completed_at": _utc_now(),
            "context": context or {},
        }
        with self.summary_path.open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
