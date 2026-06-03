"""
a11y/api/routes/crawl.py
=========================
FastAPI route for the full a11y pipeline:

  STEP 1  Crawl        — AsyncImageCrawler              (injected)
  STEP 2  OCR          — OCRPreprocessing + TextClassification  (optional)
  STEP 3  Image Audit  — AltTextAccessibilityAuditor            (injected, optional)
  STEP 4  Form Crawl   — AsyncFormCrawler                       (injected)
  STEP 5  Form Audit   — FormAccessibilityAuditor               (injected, optional)

All steps share the same output_dir so every artefact lands in one directory.
Dependencies are provided via FastAPI's DI system (see api/dependencies.py).
"""

import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from a11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from a11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from a11y.config.logger import setup_logger

from a11y.api.v1.dependencies import (
    get_config,
    get_output_dir,
    get_image_crawler,
    get_alt_text_auditor,
    get_form_crawler,
    get_form_auditor,
)
from a11y.api.v1.models.crawl import CrawlRequest, CrawlResponse

router = APIRouter(prefix="/crawl", tags=["crawl"])
logger = setup_logger(name="AC", tag="crawl")


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/", response_model=CrawlResponse)
async def run_crawler(
    payload: CrawlRequest,
):
    url = str(payload.url)
    max_depth = payload.max_depth
    config = get_config()
    output_dir = get_output_dir(url, config)
    crawler = get_image_crawler(url, max_depth, output_dir)
    auditor = get_alt_text_auditor()
    form_crawler = get_form_crawler(url, max_depth, output_dir)
    form_auditor = get_form_auditor(output_dir)

    logger.info("=" * 60)
    logger.info("A11Y PIPELINE START")
    logger.info(f"  URL            : {url}")
    logger.info(f"  max_depth      : {max_depth}")
    logger.info(f"  output_dir     : {output_dir}")
    logger.info(f"  run_ocr        : {payload.run_ocr}")
    logger.info(f"  run_audit      : {payload.run_audit}")
    logger.info(f"  run_form_audit : {payload.run_form_audit}")
    logger.info("=" * 60)

    ocr_results = []
    ocr_dir = None
    audit_report = None
    audit_summary = None
    form_inputs = []
    form_audit_report = None
    form_audit_summary = None

    try:
        # ── STEP 1 : Image Crawl ─────────────────────────────────────────
        logger.info("\nSTEP 1: IMAGE CRAWL")
        logger.info("-" * 40)

        await crawler.crawl_page()
        crawler.save_results()

        logger.info(
            f"Crawl complete — {len(crawler.images_data)} images in "
            f"{len(crawler.visited_urls)} page(s)"
        )

        # ── STEP 2 : OCR (optional) ───────────────────────────────────────
        if payload.run_ocr:
            logger.info("\nSTEP 2: TEXT DETECTION & CONTRAST ANALYSIS")
            logger.info("-" * 40)

            detector = OCRPreprocessing(source_directory=crawler.output_dir)
            detector.scan_directory()

            save = TextClassification(source_directory=crawler.output_dir)
            save.results = detector.results
            save.save_reports()

            ocr_results = detector.results
            ocr_dir = str(detector.text_detected_dir)

            logger.info(
                f"OCR complete — {len(ocr_results)} images processed, "
                f"{sum(1 for r in ocr_results if r.has_text)} with text"
            )

        # ── STEP 3 : Image Accessibility Audit (optional) ─────────────────
        if payload.run_audit:
            logger.info("\nSTEP 3: WCAG IMAGE ACCESSIBILITY AUDIT")
            logger.info("-" * 40)

            records = auditor.generate_audit_report(
                images_data=crawler.images_data,
                ocr_results=ocr_results,
                output_dir=crawler.output_dir,
            )

            audit_report = f"{crawler.output_dir}/audit_report.csv"

            total = len(records)
            passed = sum(1 for r in records if r["overall_status"] == "PASSED")
            failed = total - passed

            by_class: dict[str, dict] = {}
            for r in records:
                cls = r["classification"]
                if cls not in by_class:
                    by_class[cls] = {"passed": 0, "failed": 0}
                by_class[cls][
                    "passed" if r["overall_status"] == "PASSED" else "failed"
                ] += 1

            audit_summary = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
                "wcag_1_1_1_failed": sum(
                    1 for r in records if r["wcag_1_1_1_status"] == "FAILED"
                ),
                "wcag_4_1_2_failed": sum(
                    1 for r in records if r["wcag_4_1_2_status"] == "FAILED"
                ),
                "images_with_ocr": sum(1 for r in records if r["has_ocr_text"]),
                "contrast_violations": sum(
                    1 for r in records if r["contrast_violations_count"] > 0
                ),
                "by_classification": by_class,
            }

            logger.info(
                f"Image audit complete — {total} images, "
                f"{passed} passed ({audit_summary['pass_rate_pct']}%), "
                f"{failed} failed"
            )

        # ── STEP 4 : Form Crawl ───────────────────────────────────────────
        logger.info("\nSTEP 4: FORM CRAWL")
        logger.info("-" * 40)

        # Sync the form crawler's output dir to the image crawler's actual dir
        # so both pipelines write artefacts to the same folder.
        form_crawler.output_dir = Path(crawler.output_dir)
        form_crawler.output_dir.mkdir(parents=True, exist_ok=True)

        form_inputs = await form_crawler.crawl()
        form_crawler.save_raw_json()

        logger.info(f"Form crawl complete — {len(form_inputs)} input fields found")

        # ── STEP 5 : Form Accessibility Audit (optional) ─────────────────
        if payload.run_form_audit:
            logger.info("\nSTEP 5: WCAG 3.3.1 / 3.3.2 FORM AUDIT")
            logger.info("-" * 40)

            # Keep the form auditor's output path in sync with the shared dir
            form_auditor.output_dir = Path(crawler.output_dir)
            form_auditor.output_dir.mkdir(parents=True, exist_ok=True)

            form_records = form_auditor.generate_audit_report(form_inputs=form_inputs)
            form_audit_report = f"{crawler.output_dir}/audit_form_report.csv"
            form_audit_summary = FormAccessibilityAuditor.summarize(form_records)

            logger.info(
                f"Form audit complete — {form_audit_summary['total_fields']} fields, "
                f"{form_audit_summary['passed']} passed "
                f"({form_audit_summary['pass_rate_pct']}%), "
                f"{form_audit_summary['failed']} failed"
            )

        logger.info("\nPIPELINE COMPLETE")
        logger.info("=" * 60)

        return CrawlResponse(
            status="success",
            output_dir=str(crawler.output_dir),
            url=url,
            max_depth=max_depth,
            total_images=len(crawler.images_data),
            ocr_dir=ocr_dir,
            audit_report=audit_report,
            audit_summary=audit_summary,
            total_fields=len(form_inputs),
            form_audit_report=form_audit_report,
            form_audit_summary=form_audit_summary,
        )

    except Exception as e:
        # Internal error context (exception type, message, traceback) is logged
        # but NEVER returned to the client. The opaque error_id allows support
        # staff to correlate a 500 response with the corresponding log entry.
        error_id = uuid.uuid4().hex
        logger.error(f"Crawl pipeline failed (error_id={error_id}): {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Crawl pipeline failed due to an internal error.",
                "error_id": error_id,
            },
        )
