"""
ka11y/api/routes/crawl.py
=========================
FastAPI route for the full ka11y pipeline:

  STEP 1  Crawl   — AsyncImageCrawler
  STEP 2  OCR     — OCRPreprocessing + TextClassification  (optional)
  STEP 3  Audit   — AccessibilityAuditor  (explicit call, produces audit_report.csv)
"""

import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.config.logger import setup_logger

router = APIRouter(prefix="/crawl", tags=["crawl"])
logger = setup_logger(name="KAC", tag="crawl")


# ── Request / Response models ────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_ocr: bool = True
    run_audit: bool = True   # ← new flag; set False to skip WCAG audit


class CrawlResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    ocr_dir: str | None = None
    audit_report: str | None = None   # ← path to audit_report.csv
    audit_summary: dict | None = None  # ← pass/fail counts


# ── Route ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=CrawlResponse)
async def run_crawler(payload: CrawlRequest):
    url       = str(payload.url)
    max_depth = payload.max_depth

    logger.info("=" * 60)
    logger.info("KA11Y PIPELINE START")
    logger.info(f"  URL       : {url}")
    logger.info(f"  max_depth : {max_depth}")
    logger.info(f"  run_ocr   : {payload.run_ocr}")
    logger.info(f"  run_audit : {payload.run_audit}")
    logger.info("=" * 60)

    ocr_results   = []   # populated in STEP 2 if run_ocr=True
    ocr_dir       = None
    audit_report  = None
    audit_summary = None

    try:
        # ── STEP 1 : Crawl ───────────────────────────────────────────────
        logger.info("\nSTEP 1: CRAWL")
        logger.info("-" * 40)

        crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)
        await crawler.crawl_page()
        crawler.save_results()     # writes images_report.json + images_with_alt_text.csv

        logger.info(
            f"Crawl complete — {len(crawler.images_data)} images in "
            f"{len(crawler.visited_urls)} page(s)"
        )

        # ── STEP 2 : OCR (optional) ──────────────────────────────────────
        if payload.run_ocr:
            logger.info("\nSTEP 2: TEXT DETECTION & CONTRAST ANALYSIS")
            logger.info("-" * 40)

            detector = OCRPreprocessing(source_directory=crawler.output_dir)
            detector.scan_directory()          # populates detector.results

            save = TextClassification(source_directory=crawler.output_dir)
            save.results = detector.results
            save.save_reports()                # writes text_detection_report.json

            ocr_results = detector.results     # keep for audit step
            ocr_dir = str(detector.text_detected_dir)

            logger.info(
                f"OCR complete — {len(ocr_results)} images processed, "
                f"{sum(1 for r in ocr_results if r.has_text)} with text"
            )

        # ── STEP 3 : WCAG Accessibility Audit ────────────────────────────
        if payload.run_audit:
            logger.info("\nSTEP 3: WCAG ACCESSIBILITY AUDIT")
            logger.info("-" * 40)

            auditor = AltTextAccessibilityAuditor()
            records = auditor.generate_audit_report(
                images_data=crawler.images_data,
                ocr_results=ocr_results,       # empty list is safe if OCR skipped
                output_dir=crawler.output_dir,
            )

            audit_report = f"{crawler.output_dir}/audit_report.csv"

            # Build a lightweight summary dict to include in the API response
            total   = len(records)
            passed  = sum(1 for r in records if r["overall_status"] == "PASSED")
            failed  = sum(1 for r in records if r["overall_status"] == "FAILED")

            by_class: dict[str, dict] = {}
            for r in records:
                cls = r["classification"]
                if cls not in by_class:
                    by_class[cls] = {"passed": 0, "failed": 0}
                by_class[cls]["passed" if r["overall_status"] == "PASSED" else "failed"] += 1

            audit_summary = {
                "total":              total,
                "passed":             passed,
                "failed":             failed,
                "pass_rate_pct":      round(passed / total * 100, 1) if total else 0,
                "wcag_1_1_1_failed":  sum(1 for r in records if r["wcag_1_1_1_status"] == "FAILED"),
                "wcag_4_1_2_failed":  sum(1 for r in records if r["wcag_4_1_2_status"] == "FAILED"),
                "images_with_ocr":    sum(1 for r in records if r["has_ocr_text"]),
                "contrast_violations": sum(1 for r in records if r["contrast_violations_count"] > 0),
                "by_classification":  by_class,
            }

            logger.info(
                f"Audit complete — {total} images, "
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
            ocr_dir=ocr_dir,
            audit_report=audit_report,
            audit_summary=audit_summary,
        )

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))