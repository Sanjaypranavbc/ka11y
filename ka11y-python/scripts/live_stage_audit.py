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


def _resolve_artifact_path(path: str | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if candidate.exists():
        return candidate.resolve()
    workspace_candidate = REPO_ROOT.parent / candidate
    if workspace_candidate.exists():
        return workspace_candidate.resolve()
    repo_candidate = REPO_ROOT / candidate
    if repo_candidate.exists():
        return repo_candidate.resolve()
    return None


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


def _load_json(path: Path | None) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _collect_metrics(report_path: str | None) -> Dict[str, Any]:
    report_abs = _resolve_artifact_path(report_path)
    snapshot_abs = (
        report_abs.parent / "universal_snapshot_normalized.json"
        if report_abs and report_abs.exists()
        else None
    )

    report = _load_json(report_abs)
    snapshot = _load_json(snapshot_abs)

    counts_by_bucket = {
        key: len(snapshot.get(key, []))
        for key in (
            "forms",
            "interactive",
            "target_sizes",
            "moving_content",
            "media",
            "text_spacing",
            "sensory",
        )
    }

    selector_records = []
    non_main_frame_records = 0
    loading_indicator_exceptions = 0
    for key in counts_by_bucket:
        for item in snapshot.get(key, []):
            selector = item.get("selector") or ""
            if selector:
                selector_records.append(selector)
            frame_path = item.get("frame_path") or "main"
            if frame_path != "main":
                non_main_frame_records += 1
            if item.get("applicability_exception") == "loading_indicator":
                loading_indicator_exceptions += 1

    warning_counts: Dict[str, int] = {}
    for warning in snapshot.get("warnings", []):
        code = warning.get("code") or "unknown"
        warning_counts[code] = warning_counts.get(code, 0) + 1

    by_wcag_sc = report.get("summary", {}).get("by_wcag_sc", {})

    return {
        "report_exists": bool(report_abs and report_abs.exists()),
        "snapshot_exists": bool(snapshot_abs and snapshot_abs.exists()),
        "report_path_abs": str(report_abs) if report_abs else None,
        "snapshot_path_abs": str(snapshot_abs) if snapshot_abs and snapshot_abs.exists() else None,
        "passes": len(report.get("passes", [])),
        "violations": len(report.get("violations", [])),
        "needs_review": len(report.get("needs_review", [])),
        "report_warning_count": len(report.get("warnings", [])),
        "snapshot_warning_count": len(snapshot.get("warnings", [])),
        "warning_counts": warning_counts,
        "by_wcag_sc": by_wcag_sc,
        "counts_by_bucket": counts_by_bucket,
        "pages_crawled": snapshot.get("pages_crawled", 0),
        "partial": bool(snapshot.get("partial", False)),
        "shadow_selector_count": sum(1 for selector in selector_records if " >>> " in selector),
        "non_main_frame_record_count": non_main_frame_records,
        "loading_indicator_exceptions": loading_indicator_exceptions,
    }


def _evaluate_expectations(run: Dict[str, Any], metrics: Dict[str, Any]) -> Dict[str, Any]:
    expectations = run.get("expectations") or {}
    failures: List[str] = []
    checks: List[str] = []

    if expectations.get("require_report", True):
        if metrics["report_exists"]:
            checks.append("report_exists")
        else:
            failures.append("missing combined_report.json")

    if expectations.get("require_snapshot", True):
        if metrics["snapshot_exists"]:
            checks.append("snapshot_exists")
        else:
            failures.append("missing universal_snapshot_normalized.json")

    for bucket, min_count in (expectations.get("min_counts") or {}).items():
        actual = metrics["counts_by_bucket"].get(bucket, 0)
        if actual >= min_count:
            checks.append(f"{bucket}>={min_count}")
        else:
            failures.append(f"{bucket} expected >= {min_count}, got {actual}")

    min_shadow = expectations.get("min_shadow_selectors")
    if min_shadow is not None:
        actual = metrics["shadow_selector_count"]
        if actual >= min_shadow:
            checks.append(f"shadow_selector_count>={min_shadow}")
        else:
            failures.append(
                f"shadow selector count expected >= {min_shadow}, got {actual}"
            )

    min_frames = expectations.get("min_non_main_frame_records")
    if min_frames is not None:
        actual = metrics["non_main_frame_record_count"]
        if actual >= min_frames:
            checks.append(f"non_main_frame_record_count>={min_frames}")
        else:
            failures.append(
                f"non-main frame record count expected >= {min_frames}, got {actual}"
            )

    min_loading = expectations.get("min_loading_indicator_exceptions")
    if min_loading is not None:
        actual = metrics["loading_indicator_exceptions"]
        if actual >= min_loading:
            checks.append(f"loading_indicator_exceptions>={min_loading}")
        else:
            failures.append(
                f"loading indicator exceptions expected >= {min_loading}, got {actual}"
            )

    for code in expectations.get("required_warning_codes", []):
        actual = metrics["warning_counts"].get(code, 0)
        if actual > 0:
            checks.append(f"warning:{code}")
        else:
            failures.append(f"expected warning code {code}, got 0")

    for wcag_sc in expectations.get("expect_zero_wcag_sc", []):
        bucket = metrics["by_wcag_sc"].get(wcag_sc, {})
        actual = int(bucket.get("violations", 0))
        if actual == 0:
            checks.append(f"{wcag_sc}.violations==0")
        else:
            failures.append(f"{wcag_sc} violations expected 0, got {actual}")

    max_snapshot_warnings = expectations.get("max_snapshot_warnings")
    if max_snapshot_warnings is not None:
        actual = metrics["snapshot_warning_count"]
        if actual <= max_snapshot_warnings:
            checks.append(f"snapshot_warning_count<={max_snapshot_warnings}")
        else:
            failures.append(
                f"snapshot warning count expected <= {max_snapshot_warnings}, got {actual}"
            )

    return {
        "passed": not failures,
        "checks": checks,
        "failures": failures,
    }


def _write_summary(output_dir: Path, rows: List[Dict[str, Any]]) -> None:
    json_path = output_dir / "live_stage_summary.json"
    md_path = output_dir / "live_stage_summary.md"

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)

    lines = [
        "# Live Stage Audit Summary",
        "",
        "| Run | URL | Lang | Status | Expectation Status | Violations | Needs Review | Passes | Snapshot Warnings | Report |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            "| {run_id} | {url} | {lang} | {status} | {expectation_status} | {violations} | {needs_review} | {passes} | {snapshot_warning_count} | {report_path} |".format(
                run_id=row["run_id"],
                url=row["url"],
                lang=row["lang"],
                status=row["status"],
                expectation_status=row["expectation_status"],
                violations=row["violations"],
                needs_review=row["needs_review"],
                passes=row["passes"],
                snapshot_warning_count=row["snapshot_warning_count"],
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
        metrics = _collect_metrics(job.get("report_path"))
        expectation_result = _evaluate_expectations(run, metrics)

        row = {
            "run_id": run_id,
            "url": str(payload.url),
            "lang": payload.lang,
            "status": job.get("status"),
            "violations": metrics["violations"] or report.get("violations", 0),
            "needs_review": metrics["needs_review"] or report.get("needs_review", 0),
            "passes": metrics["passes"] or report.get("passes", 0),
            "warnings": len(job.get("warnings", [])),
            "snapshot_warning_count": metrics["snapshot_warning_count"],
            "report_path": job.get("report_path"),
            "step_log_path": job.get("step_log_path"),
            "error": job.get("error"),
            "report_path_abs": metrics["report_path_abs"],
            "snapshot_path_abs": metrics["snapshot_path_abs"],
            "metrics": metrics,
            "expectation_status": "PASS" if expectation_result["passed"] else "FAIL",
            "expectation_checks": expectation_result["checks"],
            "expectation_failures": expectation_result["failures"],
            "expected_features": run.get("expected_features", []),
            "notes": run.get("notes"),
        }
        summary_rows.append(row)

        step_logger.record(
            step="live_expectations",
            status=(
                "completed"
                if job.get("status") == "completed" and expectation_result["passed"]
                else "warning"
            ),
            message="Validated live audit expectations",
            context=row,
        )

        step_logger.record(
            step="live_run",
            status="completed" if job.get("status") == "completed" else "error",
            message="Finished live audit",
            context=row,
        )

    _write_summary(output_dir, summary_rows)
    failures = sum(1 for row in summary_rows if row["status"] != "completed")
    expectation_failures = sum(
        1 for row in summary_rows if row["expectation_status"] != "PASS"
    )
    step_logger.finalize(
        status="completed" if failures == 0 and expectation_failures == 0 else "warning",
        message="Finished live staged audit plan",
        context={
            "runs": len(summary_rows),
            "failures": failures,
            "expectation_failures": expectation_failures,
            "summary_json": str(output_dir / "live_stage_summary.json"),
            "summary_md": str(output_dir / "live_stage_summary.md"),
        },
    )
    return 1 if failures or expectation_failures else 0


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
