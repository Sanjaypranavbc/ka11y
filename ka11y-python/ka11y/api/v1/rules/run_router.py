from __future__ import annotations

import uuid
import time
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter
from ka11y.api.v1.combined.models import CombinedRequest, JobStatusResponse
from ka11y.api.v1.combined.runner import _run_job
from ka11y.api.v1.combined.store import _jobs
from ka11y.api.v1.combined.routes import assert_public_url
from .models import RuleRunRequest, RuleUrlOnlyRequest

router = APIRouter(tags=["individual-rules"])

# Mapping from Rule ID to flags in CombinedRequest
RULE_FLAGS = {
    "1.1.1": {"run_image_audit": True},
    "1.2.1": {"run_media_audit": True},
    "1.2.2": {"run_captions_audit": True},
    "1.4.3": {"run_ocr": True},
    "1.4.6": {"run_ocr": True},
    "1.4.11": {"run_image_audit": True},
    "1.4.5": {"run_image_audit": True},
    "4.1.2": {"run_image_audit": True},
}


def create_rule_handler(rule_id: str):
    async def handler(payload: RuleRunRequest):
        return await _submit_rule_job(
            rule_id=rule_id,
            url=str(payload.url),
            max_depth=payload.max_depth,
            lang=payload.lang,
            internal_links=payload.internal_links,
            max_pages=payload.max_pages,
        )

    return handler


def create_rule_url_only_handler(rule_id: str):
    async def handler(payload: RuleUrlOnlyRequest):
        return await _submit_rule_job(
            rule_id=rule_id,
            url=str(payload.url),
            max_depth=0,
            lang=payload.lang,
        )

    return handler


async def _submit_rule_job(
    *,
    rule_id: str,
    url: str,
    max_depth: int,
    lang: str,
    internal_links: bool = True,
    max_pages: int = 50,
):
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    await assert_public_url(url)

    all_fields = (
        CombinedRequest.model_fields
        if hasattr(CombinedRequest, "model_fields")
        else CombinedRequest.__fields__
    )
    flags = {k: False for k in all_fields if k.startswith("run_")}
    flags.update(RULE_FLAGS.get(rule_id, {}))

    combined_payload = CombinedRequest(
        url=url,
        max_depth=max_depth,
        internal_links=internal_links,
        max_pages=max_pages,
        lang=lang,
        **flags,
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
    logger.info(
        f"[rules] job {job_id} submitted for {url} "
        f"(rule {rule_id}, max_depth={max_depth}, lang={lang})"
    )

    return _jobs[job_id]


# Programmatically add routes for each rule to show them in Swagger
for rule_id in RULE_FLAGS:
    router.add_api_route(
        f"/{rule_id}/run",
        create_rule_handler(rule_id),
        methods=["POST"],
        response_model=JobStatusResponse,
        summary=f"Run audit for rule {rule_id}",
        status_code=202,
    )
    router.add_api_route(
        f"/{rule_id}/analyse-url",
        create_rule_url_only_handler(rule_id),
        methods=["POST"],
        response_model=JobStatusResponse,
        summary=f"Run URL-only audit for rule {rule_id}",
        status_code=202,
    )
