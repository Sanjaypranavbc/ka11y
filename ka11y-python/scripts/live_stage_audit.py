from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ka11y.api.v1.combined.models import CombinedRequest
from ka11y.api.v1.combined.runner import _run_job
from ka11y.api.v1.combined.store import _jobs
from ka11y.config.logger import setup_logger
from ka11y.utils.step_logger import ExecutionStepLogger

logger = setup_logger(name="KAC", tag="live_stage_runner")


def _load_plan(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh) or {}
    runs = payload.get("runs") or []
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"No runs found in {path}")
    return runs


def _new_job_record(job_id: str, url: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": job_id,
        "status": "pending",
        "url": url,
        "submitted_at": now,
        "_created_at": time.time(),
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
    }


def _build_request(run: Dict[str, Any]) -> CombinedRequest:
    payload = {
        "url": run["url"],
        "lang": run.get("lang", "en"),
        "wcag_level": run.get("wcag_level", "AAA"),
        "max_depth": run.get("max_depth", 0),
    }
    for key in (
        "run_ocr",
        "run_image_audit",
        "run_form_audit",
        "run_label_in_name_audit",
        "run_media_audit",
        "run_pause_stop_hide_audit",
        "run_target_size_audit",
        "run_resize_text_audit",
        "run_reflow_audit",
        "run_text_spacing_audit",
        "run_orientation_audit",
        "run_hover_focus_content_audit",
        "run_focus_not_obscured_min_audit",
        "run_focus_not_obscured_enh_audit",
        "run_sensory_audit",
    ):
        if key in run:
            payload[key] = run[key]
    return CombinedRequest(**payload)


def _write_summary(output_dir: Path, rows: List[Dict[str, Any]]) -> None:
    json_path = output_dir / "live_stage_summary.json"
    md_path = output_dir / "live_stage_summary.md"

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)

    lines = [
        "# Live Stage Audit Summary",
        "",
        "| Run | URL | Lang | Status | Violations | Needs Review | Passes | Warnings | Report |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {run_id} | {url} | {lang} | {status} | {violations} | {needs_review} | {passes} | {warnings} | {report_path} |".format(
                run_id=row["run_id"],
                url=row["url"],
                lang=row["lang"],
                status=row["status"],
                violations=row["violations"],
                needs_review=row["needs_review"],
                passes=row["passes"],
                warnings=row["warnings"],
                report_path=row["report_path"] or "",
            )
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _run_plan(plan_path: Path, output_dir: Path, node_base_url: str | None) -> int:
    runs = _load_plan(plan_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if node_base_url:
        os.environ["NODE_BASE_URL"] = node_base_url

    step_logger = ExecutionStepLogger(
        output_dir=output_dir,
        name="live_stage_runner_steps",
    )
    step_logger.record(
        step="live_stage_runner",
        status="running",
        message="Starting live staged URL audit plan",
        context={"plan": str(plan_path), "runs": len(runs), "node_base_url": node_base_url},
    )

    summary_rows: List[Dict[str, Any]] = []

    for run in runs:
        if run.get("enabled", True) is False:
            continue

        run_id = run.get("id") or str(uuid.uuid4())[:8]
        payload = _build_request(run)
        job_id = str(uuid.uuid4())
        _jobs[job_id] = _new_job_record(job_id, str(payload.url))

        step_logger.record(
            step="live_run",
            status="running",
            message="Running live audit",
            context={
                "run_id": run_id,
                "url": str(payload.url),
                "lang": payload.lang,
                "max_depth": payload.max_depth,
                "notes": run.get("notes"),
                "expected_features": run.get("expected_features", []),
            },
        )

        await _run_job(job_id, payload)
        job = _jobs[job_id]
        result = job.get("result") or {}
        report = result.get("summary") or {}

        row = {
            "run_id": run_id,
            "url": str(payload.url),
            "lang": payload.lang,
            "status": job.get("status"),
            "violations": report.get("violations", 0),
            "needs_review": report.get("needs_review", 0),
            "passes": report.get("passes", 0),
            "warnings": len(job.get("warnings", [])),
            "report_path": job.get("report_path"),
            "step_log_path": job.get("step_log_path"),
            "error": job.get("error"),
        }
        summary_rows.append(row)

        step_logger.record(
            step="live_run",
            status="completed" if job.get("status") == "completed" else "error",
            message="Finished live audit",
            context=row,
        )

    _write_summary(output_dir, summary_rows)
    failures = sum(1 for row in summary_rows if row["status"] != "completed")
    step_logger.finalize(
        status="completed" if failures == 0 else "warning",
        message="Finished live staged audit plan",
        context={
            "runs": len(summary_rows),
            "failures": failures,
            "summary_json": str(output_dir / "live_stage_summary.json"),
            "summary_md": str(output_dir / "live_stage_summary.md"),
        },
    )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real combined audits against staged/live URLs from a YAML plan."
    )
    parser.add_argument(
        "--plan",
        required=True,
        help="Path to the YAML run plan.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "live_stage_runs" / datetime.now().strftime("%Y%m%d_%H%M%S")),
        help="Directory for plan-level summaries and step logs.",
    )
    parser.add_argument(
        "--node-base-url",
        default=os.getenv("NODE_BASE_URL"),
        help="Optional override for the ka11y-node service base URL.",
    )
    args = parser.parse_args()

    logger.info(f"[live_stage_runner] plan={args.plan} output_dir={args.output_dir}")
    return asyncio.run(
        _run_plan(
            plan_path=Path(args.plan).resolve(),
            output_dir=Path(args.output_dir).resolve(),
            node_base_url=args.node_base_url,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
