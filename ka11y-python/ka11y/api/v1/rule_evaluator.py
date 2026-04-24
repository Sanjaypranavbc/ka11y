import asyncio
import tempfile
import os
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
    _call_node_flat
)
from ka11y.utils.step_logger import ExecutionStepLogger

router = APIRouter(tags=["testing"])

_SNAPSHOT_CACHE: Dict[str, Any] = {}

class TestRuleRequest(BaseModel):
    url: HttpUrl
    rule_id: str
    force_refresh: bool = False
    language: str = "en"

@router.post("/rule")
async def execute_rule_test(request: TestRuleRequest):
    url_str = str(request.url).rstrip("/")
    if url_str.endswith("/"):
        url_str = url_str[:-1]
    
    snapshot = _SNAPSHOT_CACHE.get(url_str)
    
    async def get_or_create_snapshot(tmp_dir: Path):
        nonlocal snapshot
        if request.force_refresh or snapshot is None:
            logger = ExecutionStepLogger(
                output_dir=tmp_dir,
                name="test_runner",
                job_id="test_runner"
            )
            snapshot = await _load_universal_snapshot(
                url=url_str,
                output_dir=tmp_dir,
                max_depth=0,
                job_id="test_runner",
                step_logger=logger
            )
            _SNAPSHOT_CACHE[url_str] = snapshot
        return snapshot

    findings = []
    
    if request.rule_id == "axe_core":
        node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
        try:
            findings = await _call_node_flat(url_str, node_base_url, "AA", request.language)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"status": "success", "findings": findings}
        
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            snapshot = await get_or_create_snapshot(out_path)
            future = asyncio.Future()
            future.set_result(snapshot)

            if request.rule_id in ("wcag_1_2_1", "wcag_1_2_2"):
                findings = await asyncio.wait_for(_stage_media_audit_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_media_audit=request.rule_id == "wcag_1_2_1",
                    run_captions_audit=request.rule_id == "wcag_1_2_2",
                    job_id="test_runner",
                    snapshot_task=future,
                    lang=request.language
                ), timeout=30.0)
            elif request.rule_id in ("wcag_3_3_1", "wcag_3_3_2", "wcag_1_3_1_form"):
                findings = await asyncio.wait_for(_stage_form_audit_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_form_audit=True,
                    job_id="test_runner",
                    snapshot_task=future
                ), timeout=60.0)
                findings = [f for f in findings if f.get("rule_id") == request.rule_id]
            elif request.rule_id == "wcag_2_5_3":
                findings = await asyncio.wait_for(_stage_label_in_name_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_label_in_name_audit=True,
                    job_id="test_runner",
                    snapshot_task=future
                ), timeout=60.0)
            elif request.rule_id == "wcag_2_2_2":
                findings = await asyncio.wait_for(_stage_pause_stop_hide_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_pause_stop_hide_audit=True,
                    job_id="test_runner",
                    snapshot_task=future
                ), timeout=60.0)
            elif request.rule_id == "wcag_2_5_8":
                findings = await asyncio.wait_for(_stage_target_size_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_target_size_audit=True,
                    job_id="test_runner",
                    snapshot_task=future
                ), timeout=60.0)
            elif request.rule_id == "wcag_1_4_12":
                findings = await asyncio.wait_for(_stage_text_spacing_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_text_spacing_audit=True,
                    job_id="test_runner",
                    snapshot_task=future
                ), timeout=60.0)
            elif request.rule_id == "wcag_1_3_3":
                findings = await asyncio.wait_for(_stage_sensory_audit_universal(
                    url=url_str,
                    output_dir=out_path,
                    run_sensory_audit=True,
                    job_id="test_runner",
                    lang=request.language,
                    snapshot_task=future
                ), timeout=60.0)
            else:
                raise HTTPException(status_code=400, detail=f"Rule ID {request.rule_id} is not supported in the evaluator.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"status": "success", "findings": findings}
