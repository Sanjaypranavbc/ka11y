"""
ka11y/api/v1/rule_evaluator.py
================================
Individual Rule Tester — evaluate a single WCAG rule against any URL.

Architecture notes:
  - Universal-snapshot rules use an in-memory _SNAPSHOT_CACHE to skip re-crawl.
  - Image rules spin up their own crawlers (no cache).
  - A dummy job entry is registered in _jobs so stage lifecycle helpers
    (_stage_start / _stage_complete) don't crash with KeyError.
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.api.v1.combined.stages import (
    _load_universal_snapshot,
    _stage_media_audit_universal,
    _stage_image_audit,
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
    # Python-based rules
    # ------------------------------------------------------------------
    _ensure_job_registered()
    findings = []

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)

            # ── Universal-snapshot rules ──────────────────────────────
            if request.rule_id in ("wcag_1_2_1", "wcag_1_2_2"):
                snapshot = await get_or_create_snapshot(out_path)
                future: asyncio.Future = asyncio.Future()
                future.set_result(snapshot)

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
