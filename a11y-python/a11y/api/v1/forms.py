"""
a11y/api/routes/forms.py
=========================
FastAPI route for the a11y FORMS pipeline:

  STEP 1  Crawl  — AsyncFormCrawler            (injected)
  STEP 2  Audit  — FormAccessibilityAuditor    (injected)

The output_dir dependency is shared with the crawl route — if both are
called within the same request context (e.g. a combined endpoint), they
write to the same directory. When called standalone, forms creates its own
timestamped directory via the same get_output_dir dependency.

Dependencies are provided via FastAPI's DI system (see api/dependencies.py).
"""

import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from a11y.crawler.forms_crawler import AsyncFormCrawler
from a11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from a11y.config.logger import setup_logger

from a11y.api.v1.dependencies import (
    get_output_dir,
    get_form_crawler,
    get_form_auditor,
)
from a11y.api.v1.models.forms import FormsRequest, FormsResponse

router = APIRouter(prefix="/forms", tags=["forms"])
logger = setup_logger(name="AC", tag="forms")


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/", response_model=FormsResponse)
async def run_forms_crawler(
    payload: FormsRequest,
    output_dir: Path = Depends(get_output_dir),
    crawler: AsyncFormCrawler = Depends(get_form_crawler),
    auditor: FormAccessibilityAuditor = Depends(get_form_auditor),
):
    url = str(payload.url)
    max_depth = payload.max_depth

    logger.info("=" * 60)
    logger.info("A11Y FORMS PIPELINE START")
    logger.info(f"  URL        : {url}")
    logger.info(f"  max_depth  : {max_depth}")
    logger.info(f"  output_dir : {output_dir}")
    logger.info(f"  run_audit  : {payload.run_audit}")
    logger.info("=" * 60)

    audit_report = None
    audit_summary = None

    try:
        # ── STEP 1 : Crawl forms ──────────────────────────────────────────
        logger.info("\nSTEP 1: FORM CRAWL")
        logger.info("-" * 40)

        form_inputs = await crawler.crawl()
        crawler.save_raw_json()

        logger.info(f"Form crawl complete — {len(form_inputs)} input fields found")

        # ── STEP 2 : WCAG 3.3.1 / 3.3.2 Audit ───────────────────────────
        if payload.run_audit:
            logger.info("\nSTEP 2: WCAG 3.3.1 / 3.3.2 FORM AUDIT")
            logger.info("-" * 40)

            records = auditor.generate_audit_report(form_inputs=form_inputs)

            audit_report = f"{output_dir}/audit_form_report.csv"
            audit_summary = FormAccessibilityAuditor.summarize(records)

            logger.info(
                f"Form audit complete — {audit_summary['total_fields']} fields, "
                f"{audit_summary['passed']} passed ({audit_summary['pass_rate_pct']}%), "
                f"{audit_summary['failed']} failed"
            )

        logger.info("\nFORMS PIPELINE COMPLETE")
        logger.info("=" * 60)

        return FormsResponse(
            status="success",
            output_dir=str(output_dir),
            url=url,
            max_depth=max_depth,
            total_fields=len(form_inputs),
            audit_report=audit_report,
            audit_summary=audit_summary,
        )

    except Exception as e:
        logger.error(f"Forms pipeline failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
