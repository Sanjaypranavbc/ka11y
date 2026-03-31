"""
ka11y/api/v1/combined/runner.py
=================================
_run_job() — the main background task that orchestrates the full audit.

Fires axe-core (Node) and all Python stages in parallel, resolves results,
builds the final report, and updates the job store.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from ka11y.config.logger import setup_logger
from ka11y.preprocessor.text_helper_models import _json_serializer
from ka11y.utils.config_loader import load_config

from .findings import _lang_ctx
from .models import CombinedRequest
from .report import _build_report
from .stage_events import _stage_complete, _stage_error_and_warn, _stage_start
from .stages import _allowed_levels, _call_node_flat, _run_python_stages
from .store import _broadcast, _close_subscribers, _jobs

logger = setup_logger(name="KAC", tag="combined")


def _merge_findings(
    node_findings: List[Dict], python_findings: List[Dict]
) -> List[Dict]:
    """
    Merge axe-core and Python findings with deduplication.

    Dedup key: (wcag_sc, status, element_signature)
      - element_signature is the first 120 chars of element.html (or element_id)
        normalised to lower-case so minor HTML differences don't create dupes.
      - Findings with no element info are never deduplicated (always kept).

    Override rule: when both axe-core and Python fire on the same key, the
    Python finding wins — it carries richer OCR-based contrast data for 1.4.3
    and more precise image-level diagnostics for other criteria.
    """
    # Index Python findings first so they take precedence in the merge table.
    merged: dict = {}  # key -> finding dict
    no_key: list = []  # findings with no dedup key (keep all)

    def _sig(f: Dict) -> tuple:
        el = f.get("element") or {}
        el_id = (el.get("element_id") or "").strip()
        el_html = (el.get("html") or "").strip()[:120].lower()
        ident = el_id or el_html
        return (f.get("wcag_sc", ""), f.get("status", ""), ident)

    for f in python_findings:
        key = _sig(f)
        if not key[2]:  # no element identifier
            no_key.append(f)
        else:
            merged[key] = f  # Python always wins

    for f in node_findings:
        key = _sig(f)
        if not key[2]:
            no_key.append(f)
        elif key not in merged:
            merged[key] = f  # axe only added when Python has no match

    return list(merged.values()) + no_key


async def _run_job(job_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None) -> None:
    """
    Background task: run axe-core (Node) and Python stages in parallel.

    If *filter_rule* is provided, the final report will only contain findings
    for that specific WCAG SC ID (e.g. "1.1.1").

    Graceful degradation:
    • Uses asyncio.gather(return_exceptions=True) so neither branch cancels the other.
    • If axe-core fails → Python-only report with a warning entry.
    • If a Python stage fails → other stages continue; warning entry added.
    • Job fails ONLY when both axe-core AND all Python stages return nothing.
    """
    _jobs[job_id]["status"] = "running"
    url = str(payload.url)
    _lang_ctx.set(payload.lang)  # Inherited by all child tasks via context copy

    config = load_config()
    node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts = time.strftime("%m%d_%H%M")
    output_dir = Path(
        f"{config['input']['output_dir']}/{domain}_{ts}_{job_id[:8]}_combined"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _jobs[job_id]["output_dir"] = str(output_dir)

    try:
        # Fire axe-core and all Python stages concurrently
        _stage_start(job_id, "axe_core")
        node_task = asyncio.create_task(
            _call_node_flat(url, node_base_url, payload.wcag_level, payload.lang)
        )
        python_task = asyncio.create_task(
            _run_python_stages(
                url=url,
                output_dir=output_dir,
                max_depth=payload.max_depth,
                run_ocr=payload.run_ocr,
                run_image_audit=payload.run_image_audit,
                run_form_audit=payload.run_form_audit,
                run_label_in_name_audit=payload.run_label_in_name_audit,
                run_pause_stop_hide_audit=payload.run_pause_stop_hide_audit,
                run_target_size_audit=payload.run_target_size_audit,
                run_resize_text_audit=payload.run_resize_text_audit,
                run_reflow_audit=payload.run_reflow_audit,
                run_text_spacing_audit=payload.run_text_spacing_audit,
                run_orientation_audit=payload.run_orientation_audit,
                run_hover_focus_content_audit=payload.run_hover_focus_content_audit,
                run_focus_not_obscured_min_audit=payload.run_focus_not_obscured_min_audit,
                run_focus_not_obscured_enh_audit=payload.run_focus_not_obscured_enh_audit,
                job_id=job_id,
                lang=payload.lang,
            )
        )

        node_result, python_result = await asyncio.gather(
            node_task, python_task, return_exceptions=True
        )

        # ── Resolve axe-core result ───────────────────────────────────────────
        if isinstance(node_result, Exception):
            _stage_error_and_warn(job_id, "axe_core", node_result)
            node_findings: List[Dict] = []
        else:
            node_findings = node_result
            _stage_complete(job_id, "axe_core", len(node_findings))

        # ── Resolve Python result ─────────────────────────────────────────────
        python_findings: List[Dict] = []
        contrast_report: Optional[Dict[str, Any]] = None

        if isinstance(python_result, Exception):
            pass  # all stages failed — warnings already recorded
        elif isinstance(python_result, tuple) and len(python_result) == 2:
            python_findings, contrast_report = python_result
        else:
            # Unexpected return type — degrade gracefully rather than raising
            logger.warning(
                f"[combined] job {job_id}: _run_python_stages() returned "
                f"unexpected type {type(python_result)!r}; ignoring python findings."
            )

        if not node_findings and not python_findings:
            raise RuntimeError(
                "All audit sources failed — no findings could be collected. "
                "Check warnings for details."
            )

        # Filter Python findings to the requested WCAG level
        allowed = _allowed_levels(payload.wcag_level)
        python_findings = [
            f
            for f in python_findings
            if f.get("level") in allowed or f.get("level") is None
        ]

        all_findings = _merge_findings(node_findings, python_findings)

        if filter_rule:
            all_findings = [f for f in all_findings if f.get("wcag_sc") == filter_rule]

        all_findings.sort(
            key=lambda f: {"fail": 0, "needs_review": 1, "pass": 2}.get(f["status"], 3)
        )

        report = _build_report(url, all_findings, contrast_report=contrast_report)
        report["warnings"] = _jobs[job_id].get("warnings", [])

        # Inject image_url into each contrast-report image for the frontend
        if report.get("contrast_report"):
            for img in report["contrast_report"].get("images", []):
                img["image_url"] = (
                    f"/api/v1/combined/{job_id}/image"
                    f"?path={quote(img['path'], safe='')}"
                )

        report_path = output_dir / "combined_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False, default=_json_serializer)

        _jobs[job_id].update(
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(report_path),
                "result": report,
                "current_stage": None,
            }
        )

        logger.info(
            f"[combined] job {job_id} completed — "
            f"{report['summary']['violations']} violations, "
            f"{report['summary']['needs_review']} needs_review, "
            f"{report['summary']['passes']} passes | "
            f"contrast regions: "
            f"{(contrast_report or {}).get('summary', {}).get('total_regions_analysed', 0)} | "
            f"report → {report_path}"
        )

        await _broadcast(
            job_id,
            "job_complete",
            {"job_id": job_id, "summary": report["summary"]},
        )

    except Exception as exc:
        logger.error(f"[combined] job {job_id} failed: {exc}")
        _jobs[job_id].update(
            {
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
                "current_stage": None,
            }
        )
        await _broadcast(job_id, "job_failed", {"job_id": job_id, "error": str(exc)})

    finally:
        # Bug 5 fix: stage-event broadcasts are scheduled via loop.create_task() and are
        # not awaited by their callers. If _close_subscribers() runs before those tasks
        # execute, subscriber queues are removed first and stage events are silently lost.
        # Yielding to the event loop here lets all pending broadcast tasks deliver their
        # events before the queues are closed. A single sleep(0) is sufficient because
        # _broadcast() only performs queue puts (no further I/O awaits), so each task
        # completes in one scheduling tick.
        await asyncio.sleep(0)
        await _close_subscribers(job_id)
