from __future__ import annotations

import uuid
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from ka11y.api.v1.combined.models import CombinedRequest, JobStatusResponse
from ka11y.api.v1.combined.runner import _run_job
from ka11y.api.v1.combined.store import _jobs
from ka11y.api.v1.combined.routes import assert_public_url
from .models import RuleRunRequest

router = APIRouter(tags=["individual-rules"])

# Mapping from Rule ID to flags in CombinedRequest
RULE_FLAGS = {
    "1.1.1": {"run_image_audit": True},
    "1.4.3": {"run_ocr": True},
    "1.4.6": {"run_ocr": True},
    "1.4.11": {"run_image_audit": True},
    "1.4.5": {"run_image_audit": True},
    "3.3.1": {"run_form_audit": True},
    "3.3.2": {"run_form_audit": True},
    "2.5.3": {"run_label_in_name_audit": True},
    "2.2.2": {"run_pause_stop_hide_audit": True},
    "2.5.8": {"run_target_size_audit": True},
    "1.4.12": {"run_text_spacing_audit": True},
    "1.4.4": {"run_resize_text_audit": True},
    "1.4.10": {"run_reflow_audit": True},
    "1.3.4": {"run_orientation_audit": True},
    "1.4.13": {"run_hover_focus_content_audit": True},
    "2.4.11": {"run_focus_not_obscured_min_audit": True},
    "2.4.12": {"run_focus_not_obscured_enh_audit": True},
}

def create_rule_handler(rule_id: str):
    async def handler(payload: RuleRunRequest):
        job_id = str(uuid.uuid4())
        url = str(payload.url)
        now = datetime.now(timezone.utc).isoformat()

        await assert_public_url(url)

        # Build CombinedRequest with all flags False except the ones for this rule
        # We use a dict comprehension to set all run_* flags to False
        all_fields = CombinedRequest.model_fields if hasattr(CombinedRequest, "model_fields") else CombinedRequest.__fields__
        flags = {k: False for k in all_fields if k.startswith("run_")}
        flags.update(RULE_FLAGS.get(rule_id, {}))
        
        combined_payload = CombinedRequest(
            url=payload.url,
            max_depth=payload.max_depth,
            lang=payload.lang,
            **flags
        )

        _jobs[job_id] = {
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

        asyncio.create_task(_run_job(job_id, combined_payload, filter_rule=rule_id))
        
        from ka11y.config.logger import setup_logger
        logger = setup_logger(name="KAC", tag="rules")
        logger.info(f"[rules] job {job_id} submitted for {url} (rule {rule_id})")
        
        return _jobs[job_id]
    
    return handler

# Programmatically add routes for each rule to show them in Swagger
for rule_id in RULE_FLAGS:
    router.add_api_route(
        f"/{rule_id}/run",
        create_rule_handler(rule_id),
        methods=["POST"],
        response_model=JobStatusResponse,
        summary=f"Run audit for rule {rule_id}",
        status_code=202
    )
