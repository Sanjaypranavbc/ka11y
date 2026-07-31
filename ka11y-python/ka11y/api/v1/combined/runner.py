"""
ka11y/api/v1/combined/runner.py
=================================
_run_job() — the main background task that orchestrates the full audit.

Runs Python audit stages (image, media, contrast) and the Node/axe-core
audit in parallel, then merges and deduplicates their findings into a
single unified report.

Graceful degradation: if Node is unavailable the job still completes with
Python-only findings and a warning entry.
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
from ka11y.utils.run_timing import log_run_timing
from ka11y.utils.stage_timing import emit_summary as emit_stage_timing_summary
from .models import CombinedRequest
from .report import _build_report
from .stage_events import emit_job_plan
from .stages import (
    PythonStagesResult,
    _allowed_levels,
    _run_python_stages,
)
from .store import _broadcast, _close_subscribers, _get_job_lock, _jobs
from ka11y.store import repo

logger = setup_logger(name="KAC", tag="combined")

_JOB_TIMEOUT_SECONDS = int(os.environ.get("KA11Y_JOB_TIMEOUT_SECONDS", "1800"))
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

    merged: dict = {}
    no_key: list = []

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
        image_src = (el.get("image_src") or "").strip().lower()
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
        if not key[2]:
            no_key.append(f)
        else:
            merged[key] = f
    for f in node_findings:
        key = _sig(f)
        if not key[2]:
            no_key.append(f)
        elif key not in merged:
            merged[key] = f

    return list(merged.values()) + no_key


# ---------------------------------------------------------------------------
# Node/axe-core integration
# ---------------------------------------------------------------------------

_NODE_BASE_URL = os.environ.get("NODE_BASE_URL", "http://localhost:3000")
_NODE_TIMEOUT_SECONDS = int(os.environ.get("KA11Y_NODE_TIMEOUT_SECONDS", "120"))


async def _fetch_node_findings(
    url: str,
    job_id: str,
    lang: str,
    payload: CombinedRequest,
) -> List[Dict]:
    """
    Call the Node/axe-core microservice (POST /api/v1/analyse-url-flat) and
    return its findings in the same schema expected by _merge_findings.

    Returns an empty list (+ logs a warning) on any failure so the job
    degrades gracefully to Python-only results.
    """
    import httpx

    node_url = f"{_NODE_BASE_URL.rstrip('/')}/api/v1/analyse-url-flat"
    body = {
        "url": url,
        "lang": lang,
        "level": payload.wcag_level,
        "maxDepth": payload.max_depth,
        "maxPages": payload.max_pages,
        "internalLinks": payload.internal_links,
        "jobId": job_id,
    }
    if payload.success_criteria_id:
        body["successCriteriaId"] = payload.success_criteria_id

    try:
        async with httpx.AsyncClient(timeout=_NODE_TIMEOUT_SECONDS) as client:
            resp = await client.post(node_url, json=body)
            resp.raise_for_status()
            data = resp.json()

        raw_findings: List[Dict] = data.get("findings") or []

        # Normalise field names: Node uses camelCase in some fields; _merge_findings
        # expects snake_case.  The axeResultMapper already outputs snake_case keys
        # (wcag_sc, status, level, element.page_url, element.selector …) so most
        # fields pass through untouched.  We only need to handle the pageUrl alias.
        for f in raw_findings:
            el = f.get("element")
            if isinstance(el, dict):
                # Normalise pageUrl -> page_url inside element
                if "pageUrl" in el and "page_url" not in el:
                    el["page_url"] = el.pop("pageUrl")
            # Top-level pageUrl alias (set by analyseUrlFlat loop)
            if "pageUrl" in f and "element" not in f:
                f.setdefault("element", {})["page_url"] = f.pop("pageUrl")

        logger.info(
            "[combined] job %s: Node audit returned %d findings",
            job_id, len(raw_findings),
        )
        return raw_findings

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[combined] job %s: Node audit failed (%s: %s) — continuing with Python-only results",
            job_id, type(exc).__name__, exc,
        )
        return []


async def _run_job(
    job_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None
) -> None:
    """
    Background task: run the combined Python + Node/axe-core audit.

    Python stages (image, media, contrast, form, label-in-name) and the
    Node/axe-core stage are launched in parallel. Their findings are merged
    and deduplicated by _merge_findings (Python wins on duplicate keys).

    If *filter_rule* is provided, the final report will only contain findings
    for that specific WCAG SC ID (e.g. "1.1.1").

    Graceful degradation:
    • Node failure → warning appended; job completes with Python-only findings.
    • Python failure → job fails (Python is the primary source of truth).

    Concurrency:
    • Bounded by the module-level semaphore so the worker cannot launch more
      Chromium processes than _MAX_CONCURRENT_JOBS at once.
    """
    sem = _get_job_semaphore()
    if sem.locked() and sem._value <= 0:
        async with _get_job_lock(job_id):
            if _jobs.get(job_id, {}).get("status") == "pending":
                _jobs[job_id]["status"] = "queued"

    async with sem:
        await _run_job_body(job_id, payload, filter_rule)


async def _run_job_body(
    job_id: str, payload: CombinedRequest, filter_rule: Optional[str] = None
) -> None:
    """Orchestrates one combined audit job: image audit and media/captions
    audit — no axe-core, no pipeline."""
    _jobs[job_id]["status"] = "running"
    run_started_at = datetime.now(timezone.utc).isoformat()
    _jobs[job_id]["run_started_at"] = run_started_at
    await repo.mark_running(job_id, run_started_at, _jobs[job_id].get("submitted_at"))
    repo.insert_event(job_id, "running", {})

    try:
        if await repo.is_cancelled(job_id):
            _jobs[job_id]["status"] = "cancelled"
            logger.info("[combined] job %s cancelled before start", job_id)
            return
    except Exception:
        pass

    url = str(payload.url)

    if payload.lang == "auto":
        resolved_lang = await detect_page_language(url)
        logger.info(f"[combined] job {job_id}: detected page language: {resolved_lang}")
    else:
        resolved_lang = payload.lang

    _lang_ctx.set(resolved_lang)
    try:
        from ka11y.utils import crawler_timing
        crawler_timing.set_run_id(job_id)
    except Exception:
        pass

    config = load_config()
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

        active_stages: list[str] = []
        if payload.run_ocr or payload.run_image_audit:
            active_stages.append("image_audit")
        if payload.run_media_audit or payload.run_captions_audit:
            active_stages.append("media_audit")
        emit_job_plan(job_id, active_stages)
        logger.info(f"[combined] job {job_id}: active stages = {active_stages}")

        # ── Launch Python and Node tasks in parallel ──────────────────────
        python_task = asyncio.create_task(
            _run_python_stages(
                url=url,
                output_dir=output_dir,
                max_depth=payload.max_depth,
                run_ocr=payload.run_ocr,
                run_image_audit=payload.run_image_audit,
                run_media_audit=payload.run_media_audit,
                run_captions_audit=payload.run_captions_audit,
                lang=resolved_lang,
                job_id=job_id,
                step_logger=step_logger,
                internal_links=payload.internal_links,
                max_pages=payload.max_pages,
                success_criteria_id=payload.success_criteria_id,
            )
        )

        node_task = asyncio.create_task(
            _fetch_node_findings(url, job_id, resolved_lang, payload)
        )

        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(python_task, node_task, return_exceptions=True),
                timeout=_JOB_TIMEOUT_SECONDS,
            )
            python_result = gathered[0]
            node_result_raw = gathered[1]
        except asyncio.TimeoutError:
            for t in (python_task, node_task):
                if t and not t.done():
                    t.cancel()
            raise TimeoutError(
                f"audit exceeded {_JOB_TIMEOUT_SECONDS}s overall budget"
            )

        # ── Resolve Python result ────────────────────────────────────────
        python_findings: List[Dict] = []
        contrast_report: Optional[Dict[str, Any]] = None
        image_audit_report: Optional[Dict[str, Any]] = None

        if isinstance(python_result, Exception):
            logger.error(f"[combined] job {job_id}: python stages failed: {python_result}")
        else:
            python_findings = python_result.findings
            contrast_report = python_result.contrast_report
            image_audit_report = python_result.image_audit_report

        if not python_findings:
            raise RuntimeError(
                "All audit sources failed — no findings could be collected. "
                "Check warnings for details."
            )

        # ── Resolve Node result ──────────────────────────────────────────
        node_findings: List[Dict] = []
        if isinstance(node_result_raw, Exception):
            # _fetch_node_findings already logged; treat as empty with warning
            logger.warning(
                "[combined] job %s: node task raised unexpectedly: %s",
                job_id, node_result_raw,
            )
            _jobs[job_id].setdefault("warnings", []).append(
                "Node/axe-core audit failed — report contains Python-only findings."
            )
        elif node_result_raw:
            node_findings = node_result_raw  # list[dict] from _fetch_node_findings
            if not node_findings:
                _jobs[job_id].setdefault("warnings", []).append(
                    "Node/axe-core audit returned no findings (service may be unavailable)."
                )

        logger.info(
            "[combined] job %s: python=%d findings, node=%d findings before merge",
            job_id, len(python_findings), len(node_findings),
        )

        allowed = _allowed_levels(payload.wcag_level)
        python_findings = [
            f
            for f in python_findings
            if f.get("level") in allowed or f.get("level") is None
        ]
        node_findings = [
            f
            for f in node_findings
            if f.get("level") in allowed or f.get("level") is None
        ]

        from ka11y.store.cpu_pool import run_cpu
        all_findings = await run_cpu(_merge_findings, node_findings, python_findings)

        # FIX: this was referenced below but never assigned — restored.
        effective_filter = filter_rule or payload.success_criteria_id
        if effective_filter:
            all_findings = [
                f for f in all_findings if f.get("wcag_sc") == effective_filter
            ]

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

        try:
            from ka11y.store.assets import register_report_assets
            await register_report_assets(job_id, report)
        except Exception:
            logger.debug("asset registration failed for %s", job_id, exc_info=True)

        for report_key in ("contrast_report", "image_audit_report"):
            if report.get(report_key):
                for img in report[report_key].get("images", []):
                    if img.get("path") and not img.get("image_url"):
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

        # Trigger automated Gemini report enrichment (enriched_report.json + token_usage.json)
        try:
            import sys
            import pathlib
            
            # Dynamically find the parent folder of the ka11y package
            curr = pathlib.Path(__file__).resolve().parent
            python_root = None
            for parent in [curr] + list(curr.parents):
                if parent.name == "ka11y" and (parent / "api").is_dir():
                    python_root = str(parent.parent)
                    break
                    
            if python_root:
                if python_root not in sys.path:
                    sys.path.insert(0, python_root)
            from enrich_audit import enrich_report_in_pipeline
            
            logger.info(f"[combined] Starting automated Gemini enrichment for job {job_id} into {output_dir} (language={resolved_lang})")
            enrich_report_in_pipeline(report, output_dir, language=resolved_lang)
        except Exception as e:
            import os
            import sys
            import pathlib
            diag_root = python_root if 'python_root' in locals() else 'not_set'
            file_loc = str(pathlib.Path(__file__).resolve())
            app_exists = os.path.exists('/app')
            app_contents = os.listdir('/app') if app_exists else 'no /app directory'
            logger.error(
                f"[combined] Automated enrichment failed (skipping): {e}\n"
                f"  __file__ location: {file_loc}\n"
                f"  Resolved python_root: {diag_root}\n"
                f"  sys.path: {sys.path}\n"
                f"  Contents of /app: {app_contents}",
                exc_info=True
            )

        if len(report.get("passes", [])) > 100:
            logger.info(f"[combined] Slimming in-memory passes array from {len(report['passes'])} to 100 for job {job_id}")
            report["passes"] = report["passes"][:100]
            report["summary"]["passes_truncated"] = True

        completed_at = datetime.now(timezone.utc).isoformat()
        async with _get_job_lock(job_id):
            _jobs[job_id].update(
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "report_path": str(report_path),
                    "result": report,
                    "current_stage": None,
                }
            )

        await repo.save_report(job_id, report)
        await repo.save_findings(job_id, report)
        await repo.save_pages(
            job_id, (report.get("pages") or []) if isinstance(report.get("pages"), list) else []
        )
        await repo.mark_completed(
            job_id,
            completed_at=completed_at,
            run_started_at=_jobs[job_id].get("run_started_at"),
            summary=report.get("summary"),
            output_dir=str(output_dir),
        )
        repo.insert_event(job_id, "job_complete", {"summary": report.get("summary")})

        job_rec = _jobs.get(job_id, {})
        log_run_timing(
            job_id=job_id,
            url=url,
            status="completed",
            stages=job_rec.get("stages", []),
            submitted_at=job_rec.get("submitted_at"),
            run_started_at=job_rec.get("run_started_at"),
            completed_at=job_rec.get("completed_at"),
            lang=resolved_lang,
            summary=report.get("summary"),
        )

        emit_stage_timing_summary(job_id)

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
        running_stages = [
            s["name"]
            for s in _jobs[job_id].get("stages", [])
            if s.get("status") == "running"
        ]
        current_stage = (
            ", ".join(running_stages)
            if running_stages
            else (_jobs[job_id].get("current_stage") or "post_processing")
        )

        error_id = uuid.uuid4().hex
        logger.error(
            f"[combined] job {job_id} (error_id={error_id}) failed during stage "
            f"'{current_stage}' ({err_type}: {exc}) at {where}\n{tb}"
        )
        failed_at = datetime.now(timezone.utc).isoformat()
        async with _get_job_lock(job_id):
            _jobs[job_id].update(
                {
                    "status": "failed",
                    "completed_at": failed_at,
                    "error": "Audit failed due to an internal error.",
                    "error_id": error_id,
                    "error_stage": current_stage,
                    "current_stage": None,
                }
            )
        await repo.mark_failed(
            job_id,
            completed_at=failed_at,
            run_started_at=_jobs[job_id].get("run_started_at"),
            error_id=error_id,
            error_stage=current_stage,
        )
        repo.insert_event(job_id, "job_failed", {"error_id": error_id, "stage": current_stage})

        job_rec = _jobs.get(job_id, {})
        log_run_timing(
            job_id=job_id,
            url=url,
            status="failed",
            stages=job_rec.get("stages", []),
            submitted_at=job_rec.get("submitted_at"),
            run_started_at=job_rec.get("run_started_at"),
            completed_at=job_rec.get("completed_at"),
            lang=_jobs.get(job_id, {}).get("lang"),
            error_stage=current_stage,
        )
        emit_stage_timing_summary(job_id)
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
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await _close_subscribers(job_id)