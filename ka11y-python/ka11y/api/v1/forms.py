"""
ka11y/api/routes/forms.py
=========================
FastAPI route for the ka11y FORMS pipeline:

  STEP 1  Crawl  — AsyncFormCrawler   (extracts inputs, labels, error elements)
  STEP 2  Audit  — FormAccessibilityAuditor  (WCAG 3.3.1 / 3.3.2 → audit_form_report.csv)
"""

import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from ka11y.crawler.forms_crawler import AsyncFormCrawler
from ka11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from ka11y.config.logger import setup_logger

router = APIRouter(prefix="/forms", tags=["forms"])
logger = setup_logger(name="KAC", tag="forms")


# ── Request / Response models ─────────────────────────────────────────────────

class FormsRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_audit: bool = True


class FormsResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    total_fields: int
    audit_report: str | None = None    # path to audit_form_report.csv
    audit_summary: dict | None = None  # pass/fail counts


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/", response_model=FormsResponse)
async def run_forms_crawler(payload: FormsRequest):
    url       = str(payload.url)
    max_depth = payload.max_depth

    logger.info("=" * 60)
    logger.info("KA11Y FORMS PIPELINE START")
    logger.info(f"  URL       : {url}")
    logger.info(f"  max_depth : {max_depth}")
    logger.info(f"  run_audit : {payload.run_audit}")
    logger.info("=" * 60)

    audit_report  = None
    audit_summary = None

    try:
        # ── STEP 1 : Crawl forms ──────────────────────────────────────────────
        logger.info("\nSTEP 1: FORM CRAWL")
        logger.info("-" * 40)

        from ka11y.utils.config_loader import load_config
        from urllib.parse import urlparse
        import time

        CONFIG    = load_config()
        base_out  = CONFIG["input"]["output_dir"]
        domain    = urlparse(url).netloc.replace("www.", "").replace(".", "_")
        timestamp = time.strftime("%m%d_%H%M")
        output_dir = f"{base_out}/{domain}_{timestamp}"

        crawler = AsyncFormCrawler(
            base_url=url,
            output_dir=output_dir,
            max_depth=max_depth,
        )
        form_inputs = await crawler.crawl()
        crawler.save_raw_json()

        logger.info(f"Form crawl complete — {len(form_inputs)} input fields found")

        # ── STEP 2 : WCAG 3.3.1 / 3.3.2 Audit ───────────────────────────────
        if payload.run_audit:
            logger.info("\nSTEP 2: WCAG 3.3.1 / 3.3.2 FORM AUDIT")
            logger.info("-" * 40)

            auditor = FormAccessibilityAuditor(output_dir=output_dir)
            records = auditor.generate_audit_report(form_inputs=form_inputs)

            audit_report  = f"{output_dir}/audit_form_report.csv"
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
            output_dir=output_dir,
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