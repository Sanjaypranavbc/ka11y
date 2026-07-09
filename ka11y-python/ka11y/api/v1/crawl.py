"""
ka11y/api/routes/crawl.py
=========================
FastAPI route for the full ka11y pipeline:

  STEP 1  Crawl        — AsyncImageCrawler              (injected)
  STEP 2  OCR          — OCRPreprocessing + TextClassification  (optional)
  STEP 3  Image Audit  — AltTextAccessibilityAuditor            (injected, optional)

All steps share the same output_dir so every artefact lands in one directory.
Dependencies are provided via FastAPI's DI system (see api/dependencies.py).
"""

import traceback
import uuid

from fastapi import APIRouter, HTTPException

from ka11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from ka11y.config.logger import setup_logger

from ka11y.api.v1.dependencies import (
    get_config,
    get_output_dir,
    get_image_crawler,
    get_alt_text_auditor,
)
from ka11y.api.v1.models.crawl import CrawlRequest, CrawlResponse

router = APIRouter(prefix="/crawl", tags=["crawl"])
logger = setup_logger(name="KAC", tag="crawl")


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

    logger.info("=" * 60)
    logger.info("KA11Y PIPELINE START")
    logger.info(f"  URL            : {url}")
    logger.info(f"  max_depth      : {max_depth}")
    logger.info(f"  output_dir     : {output_dir}")
    logger.info(f"  run_ocr        : {payload.run_ocr}")
    logger.info(f"  run_audit      : {payload.run_audit}")
    logger.info("=" * 60)

    ocr_results = []
    ocr_dir = None
    audit_report = None
    audit_summary = None

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
