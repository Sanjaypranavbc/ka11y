"""
ka11y/api/v1/rule_evaluator.py
================================
Individual Rule Tester — evaluate a single WCAG rule against any URL.

Architecture notes:
  - Universal-snapshot rules use an in-memory _SNAPSHOT_CACHE to skip re-crawl.
  - Image and Layout rules spin up their own crawlers (no cache).
  - Axe-Core rules proxy to the Node microservice.
  - A dummy job entry is registered in _jobs so stage lifecycle helpers
    (_stage_start / _stage_complete) don't crash with KeyError.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.api.v1.combined.stages import (
    _load_universal_snapshot,
    _stage_media_audit_universal,
    _stage_form_audit_universal,
    _stage_label_in_name_universal,
    _stage_pause_stop_hide_universal,
    _stage_target_size_universal,
    _stage_text_spacing_universal,
    _stage_sensory_audit_universal,
    _stage_image_audit,
    _stage_rendered_layout_audit,
    _call_node_flat,
)
from ka11y.api.v1.combined.store import _jobs
from ka11y.utils.step_logger import ExecutionStepLogger

logger = logging.getLogger(__name__)

router = APIRouter(tags=["testing"])

# ---------------------------------------------------------------------------
# Snapshot cache — stores the full UniversalSnapshot per URL so that
# switching rules in the Individual Rule Tester skips the 10s crawl.
# ---------------------------------------------------------------------------
_SNAPSHOT_CACHE: Dict[str, Any] = {}

JOB_ID = "rule_evaluator"


class TestRuleRequest(BaseModel):
    url: HttpUrl
    rule_id: str
    force_refresh: bool = False
    language: str = "en"


def _ensure_job_registered() -> None:
    """Ensure a minimal job entry exists in the shared _jobs store.

    Stage lifecycle helpers (_stage_start, _stage_complete, _stage_error)
    look up _jobs[job_id]. If the entry doesn't exist they raise KeyError.
    The main Dashboard creates this entry in runner.py; the Individual Rule
    Tester must create its own.
    """
    _jobs.setdefault(JOB_ID, {
        "status": "running",
        "stages": [],
        "warnings": [],
        "current_stage": None,
    })


@router.post("/rule")
async def execute_rule_test(request: TestRuleRequest):
    url_str = str(request.url).rstrip("/")

    # ------------------------------------------------------------------
    # Snapshot helper — create once, reuse across rule switches
    # ------------------------------------------------------------------
    async def get_or_create_snapshot(tmp_dir: Path):
        cached = _SNAPSHOT_CACHE.get(url_str)
        if request.force_refresh or cached is None:
            step_logger = ExecutionStepLogger(
                output_dir=tmp_dir,
                name="rule_evaluator",
                job_id=JOB_ID,
            )
            snapshot = await _load_universal_snapshot(
                url=url_str,
                output_dir=tmp_dir,
                max_depth=0,
                job_id=JOB_ID,
                step_logger=step_logger,
            )
            _SNAPSHOT_CACHE[url_str] = snapshot
            return snapshot
        return cached

    # ------------------------------------------------------------------
    # Axe-Core — proxies to the Node JS microservice (no snapshot needed)
    # ------------------------------------------------------------------
    if request.rule_id == "axe_core":
        node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
        try:
            findings = await _call_node_flat(url_str, node_base_url, "AA", request.language)
        except Exception as exc:
            logger.exception("Axe-Core proxy failed")
            raise HTTPException(status_code=500, detail=f"Axe-Core error: {exc}")
        return {"status": "success", "findings": findings}

    if request.rule_id in ("wcag_3_2_3", "wcag_3_2_4", "wcag_3_1_3", "wcag_2_4_10"):
        node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
        sc = request.rule_id.replace("wcag_", "").replace("_", ".")
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{node_base_url}/api/v1/rules/{sc}/analyse-url",
                    json={"url": url_str, "lang": request.language},
                    timeout=120.0,
                )
                resp.raise_for_status()
                data = resp.json()
                findings = data.get("results") or []
        except Exception as exc:
            logger.exception(f"Node proxy for rule {sc} failed")
            raise HTTPException(status_code=500, detail=f"Node service error for rule {sc}: {exc}")
        return {"status": "success", "findings": findings}

    # ------------------------------------------------------------------
    # Python-based rules
    # ------------------------------------------------------------------
    _ensure_job_registered()
    findings = []

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)

            # ── Universal-snapshot rules ──────────────────────────────
            if request.rule_id in (
                "wcag_1_2_1", "wcag_1_2_2",
                "wcag_3_3_1", "wcag_3_3_2", "wcag_1_3_1_form",
                "wcag_2_5_3", "wcag_2_2_2", "wcag_2_5_8",
                "wcag_1_4_12", "wcag_1_3_3",
            ):
                snapshot = await get_or_create_snapshot(out_path)
                future: asyncio.Future = asyncio.Future()
                future.set_result(snapshot)

                if request.rule_id in ("wcag_1_2_1", "wcag_1_2_2"):
                    findings = await asyncio.wait_for(
                        _stage_media_audit_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_media_audit=request.rule_id == "wcag_1_2_1",
                            run_captions_audit=request.rule_id == "wcag_1_2_2",
                            job_id=JOB_ID,
                            snapshot_task=future,
                            lang=request.language,
                        ),
                        timeout=60.0,
                    )
                    # Filter output to match the individually requested rule (e.g. '1.2.1')
                    target_wcag_num = request.rule_id.replace("wcag_", "").replace("_", ".")
                    findings = [f for f in findings if target_wcag_num in f.get("wcag_sc", "")]

                elif request.rule_id in ("wcag_3_3_1", "wcag_3_3_2", "wcag_1_3_1_form"):
                    findings = await asyncio.wait_for(
                        _stage_form_audit_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_form_audit=True,
                            job_id=JOB_ID,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )
                    findings = [f for f in findings if f.get("rule_id") == request.rule_id]

                elif request.rule_id == "wcag_2_5_3":
                    findings = await asyncio.wait_for(
                        _stage_label_in_name_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_label_in_name_audit=True,
                            job_id=JOB_ID,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )

                elif request.rule_id == "wcag_2_2_2":
                    findings = await asyncio.wait_for(
                        _stage_pause_stop_hide_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_pause_stop_hide_audit=True,
                            job_id=JOB_ID,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )

                elif request.rule_id == "wcag_2_5_8":
                    findings = await asyncio.wait_for(
                        _stage_target_size_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_target_size_audit=True,
                            job_id=JOB_ID,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )

                elif request.rule_id == "wcag_1_4_12":
                    findings = await asyncio.wait_for(
                        _stage_text_spacing_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_text_spacing_audit=True,
                            job_id=JOB_ID,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )

                elif request.rule_id == "wcag_1_3_3":
                    findings = await asyncio.wait_for(
                        _stage_sensory_audit_universal(
                            url=url_str,
                            output_dir=out_path,
                            run_sensory_audit=True,
                            job_id=JOB_ID,
                            lang=request.language,
                            snapshot_task=future,
                        ),
                        timeout=60.0,
                    )

            # ── Image-crawler rules (1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2) ──
            elif request.rule_id in ("wcag_1_1_1", "wcag_1_4_5", "wcag_1_4_11", "wcag_4_1_2", "wcag_1_4_3", "wcag_1_4_6"):
                # _stage_image_audit returns Tuple[List[Dict], Optional[Dict]]
                result = await asyncio.wait_for(
                    _stage_image_audit(
                        url=url_str,
                        output_dir=out_path,
                        max_depth=0,
                        run_ocr=request.rule_id in ("wcag_1_4_3", "wcag_1_4_6"),
                        run_image_audit=True,
                        job_id=JOB_ID,
                        lang=request.language,
                    ),
                    timeout=120.0,
                )
                # Unpack tuple: (findings_list, contrast_report_or_none)
                all_findings = result[0] if isinstance(result, tuple) else result
                # Filter to only the requested rule's findings
                target_sc = request.rule_id.replace("wcag_", "").replace("_", ".")
                findings = [f for f in all_findings if f.get("wcag_sc") == target_sc]

            # ── Layout-crawler rules (1.4.4, 1.4.10, 1.3.4, 1.4.13, 2.4.11, 2.4.12) ──
            elif request.rule_id in ("wcag_1_4_4", "wcag_1_4_10", "wcag_1_3_4", "wcag_1_4_13", "wcag_2_4_11", "wcag_2_4_12"):
                findings = await asyncio.wait_for(
                    _stage_rendered_layout_audit(
                        url=url_str,
                        output_dir=out_path,
                        run_resize_text_audit=request.rule_id == "wcag_1_4_4",
                        run_reflow_audit=request.rule_id == "wcag_1_4_10",
                        run_text_spacing_audit=False,
                        run_orientation_audit=request.rule_id == "wcag_1_3_4",
                        run_hover_focus_content_audit=request.rule_id == "wcag_1_4_13",
                        run_focus_not_obscured_min_audit=request.rule_id == "wcag_2_4_11",
                        run_focus_not_obscured_enh_audit=request.rule_id == "wcag_2_4_12",
                        job_id=JOB_ID,
                    ),
                    timeout=120.0,
                )

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule '{request.rule_id}' is not supported.",
                )

    except HTTPException:
        raise  # Let 400s pass through untouched
    except Exception as exc:
        logger.exception(f"Rule evaluation failed for {request.rule_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Rule evaluation failed: {type(exc).__name__}: {exc}",
        )

    return {"status": "success", "findings": findings}
