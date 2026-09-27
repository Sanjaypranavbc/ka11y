"""
ka11y/api/v1/rule_evaluator.py
================================
Individual Rule Tester — evaluate a single WCAG rule against any URL.

Architecture notes:
  - Universal-snapshot rules reuse the last few snapshots (_SNAPSHOT_CACHE,
    bounded LRU) so switching rules on one URL skips the crawl.
  - Image rules run the universal loader with image capture (no cache: the
    image docs live in the request's temp dir).
  - Four Node-only rules proxy to the Node microservice.
  - Each request registers its own short-lived entry in the shared _jobs
    store (stage lifecycle helpers look the job up by id) and removes it on
    the way out, so concurrent testers never write into each other's
    stage list.
"""

import asyncio
import os
import tempfile
import uuid
from collections import OrderedDict
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
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="rule_evaluator")

router = APIRouter(tags=["testing"])

# ---------------------------------------------------------------------------
# Snapshot cache — the normalised UniversalSnapshot per URL so that switching
# rules in the Individual Rule Tester skips the ~10 s crawl. Bounded: it used
# to grow by one entry per distinct URL for the life of the process.
# ---------------------------------------------------------------------------
_SNAPSHOT_CACHE: "OrderedDict[str, Any]" = OrderedDict()
_SNAPSHOT_CACHE_MAX = 8


def _cache_get(url: str) -> Any:
    snapshot = _SNAPSHOT_CACHE.get(url)
    if snapshot is not None:
        _SNAPSHOT_CACHE.move_to_end(url)
    return snapshot


def _cache_put(url: str, snapshot: Any) -> None:
    _SNAPSHOT_CACHE[url] = snapshot
    _SNAPSHOT_CACHE.move_to_end(url)
    while len(_SNAPSHOT_CACHE) > _SNAPSHOT_CACHE_MAX:
        _SNAPSHOT_CACHE.popitem(last=False)


class TestRuleRequest(BaseModel):
    url: HttpUrl
    rule_id: str
    force_refresh: bool = False
    language: str = "en"


def _register_job(url: str) -> str:
    """Create this request's own entry in the shared _jobs store and return its id.

    Stage lifecycle helpers (_stage_start, _stage_complete, _stage_error)
    look up _jobs[job_id] and raise KeyError otherwise. One id per request —
    a shared constant made concurrent testers interleave their stage records
    and trip "stage not found in running state" warnings.
    """
    job_id = f"rule-eval-{uuid.uuid4().hex[:12]}"
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "url": url,
        "stages": [],
        "warnings": [],
        "current_stage": None,
    }
    return job_id


@router.post("/rule")
async def execute_rule_test(request: TestRuleRequest):
    url_str = str(request.url).rstrip("/")
    job_id = _register_job(url_str)
    try:
        return await _execute_rule_test(request, url_str, job_id)
    finally:
        _jobs.pop(job_id, None)


async def _execute_rule_test(request: TestRuleRequest, url_str: str, job_id: str) -> Dict[str, Any]:
    # ------------------------------------------------------------------
    # Snapshot helper — create once, reuse across rule switches
    # ------------------------------------------------------------------
    async def get_or_create_snapshot(tmp_dir: Path):
        cached = _cache_get(url_str)
        if request.force_refresh or cached is None:
            step_logger = ExecutionStepLogger(
                output_dir=tmp_dir,
                name="rule_evaluator",
                job_id=job_id,
            )
            snapshot = await _load_universal_snapshot(
                url=url_str,
                output_dir=tmp_dir,
                max_depth=0,
                job_id=job_id,
                step_logger=step_logger,
            )
            _cache_put(url_str, snapshot)
            return snapshot
        return cached

    # ------------------------------------------------------------------
    # Axe-Core logic has been removed as the node runner is no longer supported
    # ------------------------------------------------------------------

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
        except Exception:  # noqa: BLE001
            error_id = uuid.uuid4().hex
            logger.exception("Node proxy for rule %s failed (error_id=%s)", sc, error_id)
            raise HTTPException(
                status_code=502,
                detail={"message": f"The Node service could not evaluate rule {sc}.", "error_id": error_id},
            )
        return {"status": "success", "findings": findings}

    # ------------------------------------------------------------------
    # Python-based rules
    # ------------------------------------------------------------------
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
                        job_id=job_id,
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
                # Same single-pass path as the combined audit: the universal
                # loader navigates the page once with image capture on, and
                # the image stage only reads the resulting page docs. The
                # snapshot cache is not used here because the image docs live
                # in this request's temp dir.
                step_logger = ExecutionStepLogger(
                    output_dir=out_path, name="rule_evaluator", job_id=job_id,
                )
                image_raw_dir = out_path / "image_raw"
                await asyncio.wait_for(
                    _load_universal_snapshot(
                        url=url_str,
                        output_dir=out_path,
                        max_depth=0,
                        job_id=job_id,
                        step_logger=step_logger,
                        image_capture=True,
                        image_raw_dir=image_raw_dir,
                    ),
                    timeout=120.0,
                )
                # _stage_image_audit returns Tuple[List[Dict], Optional[Dict], Optional[Dict]]
                result = await asyncio.wait_for(
                    _stage_image_audit(
                        url=url_str,
                        output_dir=out_path,
                        max_depth=0,
                        run_ocr=request.rule_id in ("wcag_1_4_3", "wcag_1_4_6"),
                        run_image_audit=True,
                        job_id=job_id,
                        lang=request.language,
                        raw_dir=image_raw_dir,
                        image_output_dir=out_path / "images",
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
    except Exception:  # noqa: BLE001
        # Same contract as every other route: internals go to the log under an
        # opaque error_id, never into the response body.
        error_id = uuid.uuid4().hex
        logger.exception("Rule evaluation failed for %s (error_id=%s)", request.rule_id, error_id)
        raise HTTPException(
            status_code=500,
            detail={"message": "Rule evaluation failed due to an internal error.", "error_id": error_id},
        )

    return {"status": "success", "findings": findings}
