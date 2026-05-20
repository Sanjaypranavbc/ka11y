"""
ka11y/api/v1/combined/runner.py
=================================
_run_job() — the main background task that orchestrates the full audit.

Fires axe-core (Node) and all Python stages in parallel, resolves results,
builds the final report, and updates the job store.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

from ka11y.config.logger import setup_logger
from ka11y.preprocessor.text_helper_models import _json_serializer
from ka11y.utils.config_loader import load_config
from ka11y.utils.step_logger import ExecutionStepLogger

from .findings import _lang_ctx
from ka11y.utils.lang_detector import detect_page_language
from .models import CombinedRequest
from .report import _build_report
from .stage_events import (
    _stage_complete,
    _stage_error_and_warn,
    _stage_start,
    emit_job_plan,
)
from .stages import (
    PythonStagesResult,
    _allowed_levels,
    _call_node_flat,
    _run_python_stages,
)
from .store import _broadcast, _close_subscribers, _get_job_lock, _jobs

logger = setup_logger(name="KAC", tag="combined")


# Outer audit budget — bounds the top-level asyncio.gather of axe+python so
# a stuck inner branch cannot pin a worker forever. Each inner stage already
# has a tighter _STAGE_TIMEOUT_SECONDS budget in stages.py.
_JOB_TIMEOUT_SECONDS = int(os.environ.get("KA11Y_JOB_TIMEOUT_SECONDS", "1200"))

# Hard cap on concurrent _run_job() background tasks. Without this, every
# accepted POST spawns a Chromium + axe-core run; at the rate-limiter's
# 30 req/min ceiling that would launch ~150 browsers in 5 minutes. The
# semaphore is initialised lazily because asyncio primitives must be bound
# to a running event loop.
_MAX_CONCURRENT_JOBS = int(os.environ.get("KA11Y_MAX_CONCURRENT_JOBS", "4"))
_job_semaphore: asyncio.Semaphore | None = None
_job_semaphore_loop: Any = None


def _get_job_semaphore() -> asyncio.Semaphore:
    """Lazy per-event-loop semaphore so module import never touches the loop."""
    global _job_semaphore, _job_semaphore_loop
    current = asyncio.get_event_loop()
    if _job_semaphore is None or _job_semaphore_loop is not current:
        _job_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_JOBS)
        _job_semaphore_loop = current
    return _job_semaphore


def _merge_findings(
    node_findings: List[Dict], python_findings: List[Dict]
) -> List[Dict]:
    """
    Merge axe-core and Python findings with deduplication.

    Dedup key: (wcag_sc, status, element_signature)
      - element_signature prefers page-aware selectors/targets first so
        Python and node findings can still meet on the same live element.
      - fallback HTML signatures are hashed and namespaced by page/frame/tag
        to avoid merging unrelated repeated components by truncated markup.
      - Findings with no element info are never deduplicated (always kept).

    Override rule: when both axe-core and Python fire on the same key, the
    Python finding wins — it carries richer OCR-based contrast data for 1.4.3
    and more precise image-level diagnostics for other criteria.
    """
    # Index Python findings first so they take precedence in the merge table.
    merged: dict = {}  # key -> finding dict
    no_key: list = []  # findings with no dedup key (keep all)

    def _normalize_target_sig(target: Any) -> str:
        if isinstance(target, str):
            targets = [target]
        elif isinstance(target, list):
            targets = [item for item in target if isinstance(item, str)]
        else:
            targets = []
        cleaned = [
            " ".join(item.split()).strip().lower() for item in targets if item.strip()
        ]
        if not cleaned:
            return ""
        return "||".join(dict.fromkeys(cleaned))

    def _normalize_html_sig(html: str) -> str:
        collapsed = " ".join(html.split()).strip().lower()
        if not collapsed:
            return ""
        return hashlib.sha1(collapsed[:400].encode("utf-8")).hexdigest()[:16]

    def _sig(f: Dict) -> tuple:
        el = f.get("element") or {}
        page_url = (el.get("page_url") or "").strip().lower()
        frame_path = (el.get("frame_path") or "").strip().lower()
        selector = " ".join(str(el.get("selector") or "").split()).strip().lower()
        target_sig = _normalize_target_sig(el.get("target"))
        ref_id = (el.get("element_ref_id") or "").strip().lower()
        tag = (el.get("tag") or "").strip().lower()
        el_id = (el.get("element_id") or "").strip().lower()
        html_sig = _normalize_html_sig(str(el.get("html") or ""))
        # image_src: Python image findings use the src URL as element_id, but axe
        # findings for the same <img> use CSS selectors.  Provide a stable cross-service
        # dedup key by normalising the image src when present (§3.2 fix).
        image_src = (el.get("image_src") or "").strip().lower()
        # Strip the el_id if it looks like a URL — use image_src path instead so it
        # doesn't collide with a DOM element-id on a different element.
        el_id_is_url = el_id.startswith(("http://", "https://", "//", "/"))
        stable_el_id = el_id if not el_id_is_url else ""

        page_scope = "|".join(part for part in (page_url, frame_path) if part)
        ident = (
            (f"sel:{page_scope}|{selector}" if selector else "")
            or (f"target:{page_scope}|{target_sig}" if target_sig else "")
            or (f"ref:{page_scope}|{ref_id}" if ref_id else "")
            or (f"id:{page_scope}|{tag}|{stable_el_id}" if stable_el_id else "")
            or (f"img:{page_scope}|{image_src}" if image_src else "")
            or (f"html:{page_scope}|{tag}|{html_sig}" if html_sig else "")
        )
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


async def _run_job(
    job_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None
) -> None:
    """
    Background task: run axe-core (Node) and Python stages in parallel.

    If *filter_rule* is provided, the final report will only contain findings
    for that specific WCAG SC ID (e.g. "1.1.1").

    Graceful degradation:
    • Uses asyncio.gather(return_exceptions=True) so neither branch cancels the other.
    • If axe-core fails → Python-only report with a warning entry.
    • If a Python stage fails → other stages continue; warning entry added.
    • Job fails ONLY when both axe-core AND all Python stages return nothing.

    Concurrency:
    • Bounded by the module-level semaphore so the worker cannot launch more
      Chromium processes than _MAX_CONCURRENT_JOBS at once. Jobs over the cap
      wait in FIFO order; the job's status stays "pending" until the slot is
      acquired so clients polling /combined/{job_id} can observe the queue.
    """
    sem = _get_job_semaphore()
    if sem.locked() and sem._value <= 0:  # noqa: SLF001
        # Visible state when a job is admitted but is parked behind the cap.
        async with _get_job_lock(job_id):
            if _jobs.get(job_id, {}).get("status") == "pending":
                _jobs[job_id]["status"] = "queued"

    async with sem:
        await _run_job_body(job_id, payload, filter_rule)


async def _run_job_body(
    job_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None
) -> None:
    """Original body of :func:`_run_job`, gated by the concurrency semaphore."""
    _jobs[job_id]["status"] = "running"
    url = str(payload.url)
    # Auto-detect page language when user selects "auto"
    if payload.lang == "auto":
        resolved_lang = await detect_page_language(url)
        logger.info(
            f"[combined] job {job_id}: auto-detected language '{resolved_lang}' for {url}"
        )
    else:
        resolved_lang = payload.lang
    _lang_ctx.set(resolved_lang)

    config = load_config()
    node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
    domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts = time.strftime("%m%d_%H%M")
    output_dir = Path(
        f"{config['input']['output_dir']}/{domain}_{ts}_{job_id[:8]}_combined"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    _jobs[job_id]["output_dir"] = str(output_dir)
    step_logger = ExecutionStepLogger(
        output_dir=output_dir,
        name="combined_execution_steps",
        job_id=job_id,
    )
    _jobs[job_id]["step_log_path"] = str(step_logger.jsonl_path)
    _jobs[job_id]["step_summary_path"] = str(step_logger.summary_path)

    try:
        step_logger.record(
            step="combined_job",
            status="running",
            message="Combined audit job started",
            context={
                "url": url,
                "lang": resolved_lang,
                "wcag_level": payload.wcag_level,
            },
        )

        # Announce the stage plan to SSE subscribers so the progress bar can render.
        node_stage = "axe_core"
        if payload.run_accesslint and not payload.run_axe:
            node_stage = "accesslint"
        elif payload.run_accesslint and payload.run_axe:
            node_stage = "node_audit"
            
        active_stages: list[str] = [node_stage]
        if payload.run_ocr or payload.run_image_audit:
            active_stages.append("image_audit")
        # pipeline stage always runs; it handles 2.5.3 / 2.5.8 / 1.1.1 / focus / contrast
        active_stages.append("pipeline")
        if payload.run_form_audit:
            active_stages.append("form_audit")
        if payload.run_pause_stop_hide_audit:
            active_stages.append("pause_stop_hide")
        if payload.run_text_spacing_audit:
            active_stages.append("text_spacing")
        if any(
            (
                payload.run_resize_text_audit,
                payload.run_reflow_audit,
                payload.run_text_spacing_audit,
                payload.run_orientation_audit,
                payload.run_hover_focus_content_audit,
                payload.run_focus_not_obscured_min_audit,
                payload.run_focus_not_obscured_enh_audit,
            )
        ):
            active_stages.append("rendered_layout_audit")
        if payload.run_media_audit:
            active_stages.append("media_audit")
        if payload.run_sensory_audit:
            active_stages.append("sensory_audit")
        emit_job_plan(job_id, active_stages)

        # Fire axe-core and all Python stages concurrently
        _stage_start(job_id, node_stage)
        node_task = asyncio.create_task(
            _call_node_flat(url, node_base_url, payload.wcag_level, resolved_lang,
                            run_axe=payload.run_axe, run_accesslint=payload.run_accesslint)
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
                run_media_audit=payload.run_media_audit,
                run_captions_audit=payload.run_captions_audit,
                run_pause_stop_hide_audit=payload.run_pause_stop_hide_audit,
                run_target_size_audit=payload.run_target_size_audit,
                run_resize_text_audit=payload.run_resize_text_audit,
                run_reflow_audit=payload.run_reflow_audit,
                run_text_spacing_audit=payload.run_text_spacing_audit,
                run_orientation_audit=payload.run_orientation_audit,
                run_hover_focus_content_audit=payload.run_hover_focus_content_audit,
                run_focus_not_obscured_min_audit=payload.run_focus_not_obscured_min_audit,
                run_focus_not_obscured_enh_audit=payload.run_focus_not_obscured_enh_audit,
                run_sensory_audit=payload.run_sensory_audit,
                lang=resolved_lang,
                job_id=job_id,
                step_logger=step_logger,
            )
        )

        # Top-level audit cap: even if one branch hangs (e.g. a misbehaving
        # remote axe service or a Playwright deadlock), the job must terminate
        # rather than block the worker forever. The inner stage timeouts
        # (_timed in stages.py) bound individual auditors; this is the outer
        # safety net.
        try:
            node_result, python_result = await asyncio.wait_for(
                asyncio.gather(node_task, python_task, return_exceptions=True),
                timeout=_JOB_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            for t in (node_task, python_task):
                if not t.done():
                    t.cancel()
            # Surface as a structured failure; the outer except path will
            # scrub it before broadcasting.
            raise TimeoutError(
                f"audit exceeded {_JOB_TIMEOUT_SECONDS}s overall budget"
            )

        # ── Resolve axe-core result ───────────────────────────────────────────
        if isinstance(node_result, Exception):
            _stage_error_and_warn(job_id, node_stage, node_result)
            node_findings: List[Dict] = []
        else:
            node_findings = node_result
            _stage_complete(job_id, node_stage, len(node_findings))
            step_logger.record(
                step=f"{node_stage}_summary",
                status="completed",
                message=f"{node_stage.replace('_', '-')} results recorded",
                context={"finding_count": len(node_findings)},
            )

        # ── Resolve Python result ─────────────────────────────────────────────
        python_findings: List[Dict] = []
        contrast_report: Optional[Dict[str, Any]] = None
        image_audit_report: Optional[Dict[str, Any]] = None

        if isinstance(python_result, Exception):
            pass  # all stages failed — warnings already recorded
        elif isinstance(python_result, PythonStagesResult):
            python_findings = python_result.findings
            contrast_report = python_result.contrast_report
            image_audit_report = python_result.image_audit_report
        elif isinstance(python_result, tuple) and len(python_result) == 3:
            # Backwards-compat path: pre-dataclass callers / older test mocks.
            python_findings, contrast_report, image_audit_report = python_result
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

        report = _build_report(
            url,
            all_findings,
            lang=resolved_lang,
            contrast_report=contrast_report,
            image_audit_report=image_audit_report,
        )
        report["warnings"] = _jobs[job_id].get("warnings", [])
        report["warning_details"] = _jobs[job_id].get("warning_details", [])

        # Inject image_url into image-backed reports for frontend rendering.
        for report_key in ("contrast_report", "image_audit_report"):
            if report.get(report_key):
                for img in report[report_key].get("images", []):
                    if img.get("path"):
                        img["image_url"] = (
                            f"/api/v1/combined/{job_id}/image"
                            f"?path={quote(img['path'], safe='')}"
                        )

        for array_key in ("violations", "needs_review", "passes"):
            for finding in report.get(array_key, []):
                element = finding.get("element")
                if element and isinstance(element, dict):
                    src = element.get("image_src")
                    if (
                        src
                        and not src.startswith("/api/v1/")
                        and not src.startswith(("http://", "https://", "data:"))
                    ):
                        element["image_src"] = (
                            f"/api/v1/combined/{job_id}/image"
                            f"?path={quote(src, safe='')}"
                        )

        report_path = output_dir / "combined_report.json"
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(
                report, fh, indent=2, ensure_ascii=False, default=_json_serializer
            )

        # Slim down the "passes" array for the in-memory 'result' object used by the UI
        if len(report.get("passes", [])) > 100:
            logger.info(f"[combined] Slimming in-memory passes array from {len(report['passes'])} to 100 for job {job_id}")
            report["passes"] = report["passes"][:100]
            report["summary"]["passes_truncated"] = True

        async with _get_job_lock(job_id):
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
        step_logger.finalize(
            status="completed",
            message="Combined audit job completed",
            context={
                "report_path": str(report_path),
                "violations": report["summary"]["violations"],
                "needs_review": report["summary"]["needs_review"],
                "passes": report["summary"]["passes"],
                "warnings": len(report.get("warnings", [])),
            },
        )

        await _broadcast(
            job_id,
            "job_complete",
            {"job_id": job_id, "summary": report["summary"]},
        )

    except Exception as exc:
        tb = traceback.format_exc()
        origin = (
            traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
        )
        where = (
            f"{origin.filename}:{origin.lineno} in {origin.name}()"
            if origin
            else "unknown"
        )
        err_type = type(exc).__name__
        current_stage = _jobs[job_id].get("current_stage") or "post_processing"
        # Internal-only diagnostic detail (file paths, exception type, traceback)
        # is logged but never surfaced to API clients. Clients receive an opaque
        # error_id which support staff can correlate against these logs.
        error_id = uuid.uuid4().hex
        logger.error(
            f"[combined] job {job_id} (error_id={error_id}) failed during stage "
            f"'{current_stage}' ({err_type}: {exc}) at {where}\n{tb}"
        )
        async with _get_job_lock(job_id):
            _jobs[job_id].update(
                {
                    "status": "failed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error": "Audit failed due to an internal error.",
                    "error_id": error_id,
                    "error_stage": current_stage,
                    "current_stage": None,
                }
            )
        step_logger.finalize(
            status="error",
            message="Combined audit job failed",
            context={
                "error_type": err_type,
                "error": str(exc),
                "stage": current_stage,
                "location": where,
            },
        )
        # SSE broadcast: client gets opaque error_id + stage only. Exception
        # type, message, and source location are server-side log signals.
        await _broadcast(
            job_id,
            "job_failed",
            {
                "job_id": job_id,
                "error": "Audit failed due to an internal error.",
                "error_id": error_id,
                "stage": current_stage,
            },
        )

    finally:
        # Stage-event broadcasts are scheduled via loop.create_task() and are not
        # awaited by their callers. If _close_subscribers() runs before those tasks
        # execute, subscriber queues are removed first and stage events are silently
        # lost. Two yields are used: the first allows the broadcast tasks to be
        # scheduled; the second allows them to complete their queue puts, since each
        # broadcast task itself does a single non-blocking put_nowait with no further
        # awaits.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await _close_subscribers(job_id)
