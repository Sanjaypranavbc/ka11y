"""
ka11y/api/routes/pipeline.py
============================
Combined endpoint: runs the image crawl pipeline FIRST, then the forms
pipeline — both sharing the same output_dir via dependency injection.

  POST /pipeline/

  STEP 1  Image Crawl  →  AsyncImageCrawler
  STEP 2  OCR          →  OCRPreprocessing + TextClassification  (optional)
  STEP 3  Image Audit  →  AltTextAccessibilityAuditor            (optional)
  STEP 4  Form Crawl   →  AsyncFormCrawler
  STEP 5  Form Audit   →  FormAccessibilityAuditor               (optional)

Because get_output_dir is a plain Depends (not lru_cache), FastAPI resolves
it once per request and re-uses the same Path object for every dependency
that lists it — so all five steps share one directory.
"""

import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.crawler.forms_crawler import AsyncFormCrawler
from ka11y.crawler.interactive_crawler import InteractiveElementCrawler
from ka11y.crawler.moving_content_crawler import MovingContentCrawler
from ka11y.crawler.target_size_crawler import TargetSizeCrawler
from ka11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import LabelInNameAuditor
from ka11y.accessibility.rules.input_modalities.target_size_auditor import TargetSizeAuditor
from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import PauseStopHideAuditor
from ka11y.config.logger import setup_logger

from ka11y.api.v1.dependencies import (
    get_output_dir,
    get_image_crawler,
    get_form_crawler,
    get_alt_text_auditor,
    get_form_auditor,
    get_interactive_crawler,
    get_moving_content_crawler,
    get_label_in_name_auditor,
    get_pause_stop_hide_auditor,
    get_target_size_crawler,
    get_target_size_auditor,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = setup_logger(name="KAC", tag="pipeline")


# ── Request / Response models ─────────────────────────────────────────────────

class PipelineRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_ocr: bool = True
    run_image_audit: bool = True
    run_form_audit: bool = True
    run_label_in_name_audit: bool = True
    run_pause_stop_hide_audit: bool = True
    run_target_size_audit: bool = True


class PipelineResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    # Image crawl
    total_images: int
    ocr_dir: str | None = None
    image_audit_report: str | None = None
    image_audit_summary: dict | None = None
    # Form crawl
    total_fields: int
    form_audit_report: str | None = None
    form_audit_summary: dict | None = None
    # WCAG 2.5.3 — Label in Name
    total_interactive_elements: int = 0
    label_in_name_report: str | None = None
    label_in_name_summary: dict | None = None
    # WCAG 2.2.2 — Pause, Stop, Hide
    total_moving_content_items: int = 0
    pause_stop_hide_report: str | None = None
    pause_stop_hide_summary: dict | None = None
    # WCAG 2.5.8 — Target Size (Minimum)
    total_target_size_elements: int = 0
    target_size_report: str | None = None
    target_size_summary: dict | None = None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/", response_model=PipelineResponse)
async def run_full_pipeline(
    payload: PipelineRequest,
    # ── shared output directory (resolved once, reused by all deps) ────────
    output_dir: Path                     = Depends(get_output_dir),
    # ── crawlers ──────────────────────────────────────────────────────────
    image_crawler: AsyncImageCrawler               = Depends(get_image_crawler),
    form_crawler: AsyncFormCrawler                 = Depends(get_form_crawler),
    interactive_crawler: InteractiveElementCrawler = Depends(get_interactive_crawler),
    moving_content_crawler: MovingContentCrawler   = Depends(get_moving_content_crawler),
    target_size_crawler: TargetSizeCrawler         = Depends(get_target_size_crawler),
    # ── auditors ──────────────────────────────────────────────────────────
    image_auditor: AltTextAccessibilityAuditor     = Depends(get_alt_text_auditor),
    form_auditor: FormAccessibilityAuditor         = Depends(get_form_auditor),
    label_in_name_auditor: LabelInNameAuditor      = Depends(get_label_in_name_auditor),
    pause_stop_hide_auditor: PauseStopHideAuditor  = Depends(get_pause_stop_hide_auditor),
    target_size_auditor: TargetSizeAuditor         = Depends(get_target_size_auditor),
):
    url       = str(payload.url)
    max_depth = payload.max_depth

    logger.info("=" * 60)
    logger.info("KA11Y FULL PIPELINE START")
    logger.info(f"  URL        : {url}")
    logger.info(f"  max_depth  : {max_depth}")
    logger.info(f"  output_dir : {output_dir}")
    logger.info("=" * 60)

    ocr_results              = []
    ocr_dir                  = None
    image_audit_report       = None
    image_audit_summary      = None
    form_audit_report        = None
    form_audit_summary       = None
    label_in_name_report     = None
    label_in_name_summary    = None
    pause_stop_hide_report   = None
    pause_stop_hide_summary  = None
    target_size_report       = None
    target_size_summary      = None

    try:
        # ── STEP 1 : Image Crawl ──────────────────────────────────────────
        logger.info("\nSTEP 1: IMAGE CRAWL")
        logger.info("-" * 40)

        await image_crawler.crawl_page()
        image_crawler.save_results()

        logger.info(
            f"Image crawl complete — {len(image_crawler.images_data)} images "
            f"in {len(image_crawler.visited_urls)} page(s)"
        )

        # ── STEP 2 : OCR (optional) ───────────────────────────────────────
        if payload.run_ocr:
            logger.info("\nSTEP 2: TEXT DETECTION & CONTRAST ANALYSIS")
            logger.info("-" * 40)

            detector = OCRPreprocessing(source_directory=image_crawler.output_dir)
            detector.scan_directory()

            save = TextClassification(source_directory=image_crawler.output_dir)
            save.results = detector.results
            save.save_reports()

            ocr_results = detector.results
            ocr_dir     = str(detector.text_detected_dir)

            logger.info(
                f"OCR complete — {len(ocr_results)} images processed, "
                f"{sum(1 for r in ocr_results if r.has_text)} with text"
            )

        # ── STEP 3 : Image Accessibility Audit (optional) ─────────────────
        if payload.run_image_audit:
            logger.info("\nSTEP 3: WCAG IMAGE ACCESSIBILITY AUDIT")
            logger.info("-" * 40)

            img_records = image_auditor.generate_audit_report(
                images_data=image_crawler.images_data,
                ocr_results=ocr_results,
                output_dir=image_crawler.output_dir,
            )

            image_audit_report = f"{image_crawler.output_dir}/audit_report.csv"

            total  = len(img_records)
            passed = sum(1 for r in img_records if r["overall_status"] == "PASSED")
            failed = total - passed

            by_class: dict[str, dict] = {}
            for r in img_records:
                cls = r["classification"]
                if cls not in by_class:
                    by_class[cls] = {"passed": 0, "failed": 0}
                by_class[cls]["passed" if r["overall_status"] == "PASSED" else "failed"] += 1

            image_audit_summary = {
                "total":               total,
                "passed":              passed,
                "failed":              failed,
                "pass_rate_pct":       round(passed / total * 100, 1) if total else 0,
                "wcag_1_1_1_failed":   sum(1 for r in img_records if r["wcag_1_1_1_status"] == "FAILED"),
                "wcag_4_1_2_failed":   sum(1 for r in img_records if r["wcag_4_1_2_status"] == "FAILED"),
                "images_with_ocr":     sum(1 for r in img_records if r["has_ocr_text"]),
                "contrast_violations": sum(1 for r in img_records if r["contrast_violations_count"] > 0),
                "by_classification":   by_class,
            }

            logger.info(
                f"Image audit complete — {total} images, "
                f"{passed} passed ({image_audit_summary['pass_rate_pct']}%), {failed} failed"
            )

        # ── STEP 4 : Form Crawl ───────────────────────────────────────────
        logger.info("\nSTEP 4: FORM CRAWL")
        logger.info("-" * 40)

        form_inputs = await form_crawler.crawl()
        form_crawler.save_raw_json()

        logger.info(f"Form crawl complete — {len(form_inputs)} input fields found")

        # ── STEP 5 : Form Accessibility Audit (optional) ──────────────────
        if payload.run_form_audit:
            logger.info("\nSTEP 5: WCAG 3.3.1 / 3.3.2 FORM AUDIT")
            logger.info("-" * 40)

            form_records   = form_auditor.generate_audit_report(form_inputs=form_inputs)
            form_audit_report  = f"{output_dir}/audit_form_report.csv"
            form_audit_summary = FormAccessibilityAuditor.summarize(form_records)

            logger.info(
                f"Form audit complete — {form_audit_summary['total_fields']} fields, "
                f"{form_audit_summary['passed']} passed "
                f"({form_audit_summary['pass_rate_pct']}%), "
                f"{form_audit_summary['failed']} failed"
            )

        # ── STEP 6 : Interactive Element Crawl (2.5.3) ───────────────
        logger.info("\nSTEP 6: INTERACTIVE ELEMENT CRAWL (WCAG 2.5.3)")
        logger.info("-" * 40)

        interactive_elements = await interactive_crawler.crawl()
        interactive_crawler.save_raw_json()

        logger.info(f"Interactive crawl complete — {len(interactive_elements)} elements found")

        # ── STEP 7 : WCAG 2.5.3 Label in Name Audit (optional) ───────
        if payload.run_label_in_name_audit:
            logger.info("\nSTEP 7: WCAG 2.5.3 LABEL IN NAME AUDIT")
            logger.info("-" * 40)

            lin_records       = label_in_name_auditor.generate_audit_report(interactive_elements)
            label_in_name_report   = str(output_dir / "audit_label_in_name_report.csv")
            label_in_name_summary  = LabelInNameAuditor.summarize(lin_records)

            logger.info(
                f"Label in Name audit complete — "
                f"{label_in_name_summary['checked']} checked, "
                f"{label_in_name_summary['passed']} passed "
                f"({label_in_name_summary['pass_rate_pct']}%), "
                f"{label_in_name_summary['failed']} failed"
            )

        # ── STEP 8 : Moving Content Crawl (2.2.2) ────────────────────
        logger.info("\nSTEP 8: MOVING CONTENT CRAWL (WCAG 2.2.2)")
        logger.info("-" * 40)

        moving_items = await moving_content_crawler.crawl()
        moving_content_crawler.save_raw_json()

        logger.info(f"Moving content crawl complete — {len(moving_items)} items found")

        # ── STEP 9 : WCAG 2.2.2 Pause Stop Hide Audit (optional) ─────
        if payload.run_pause_stop_hide_audit:
            logger.info("\nSTEP 9: WCAG 2.2.2 PAUSE / STOP / HIDE AUDIT")
            logger.info("-" * 40)

            psh_records          = pause_stop_hide_auditor.generate_audit_report(moving_items)
            pause_stop_hide_report   = str(output_dir / "audit_pause_stop_hide_report.csv")
            pause_stop_hide_summary  = PauseStopHideAuditor.summarize(psh_records)

            logger.info(
                f"Pause/Stop/Hide audit complete — "
                f"{pause_stop_hide_summary['total_items']} items, "
                f"{pause_stop_hide_summary['passed']} passed "
                f"({pause_stop_hide_summary['pass_rate_pct']}%), "
                f"{pause_stop_hide_summary['failed']} failed | "
                f"axe-core would miss {pause_stop_hide_summary['axe_would_miss']}"
            )

        # ── STEP 10 : Target Size Crawl (2.5.8) ──────────────────────
        logger.info("\nSTEP 10: TARGET SIZE CRAWL (WCAG 2.5.8)")
        logger.info("-" * 40)

        target_size_items = await target_size_crawler.crawl()
        target_size_crawler.save_raw_json()

        logger.info(f"Target size crawl complete — {len(target_size_items)} elements found")

        # ── STEP 11 : WCAG 2.5.8 Target Size Audit (optional) ────────
        if payload.run_target_size_audit:
            logger.info("\nSTEP 11: WCAG 2.5.8 TARGET SIZE AUDIT")
            logger.info("-" * 40)

            ts_records         = target_size_auditor.generate_audit_report(target_size_items)
            target_size_report = str(output_dir / "audit_target_size_report.csv")
            target_size_summary = TargetSizeAuditor.summarize(ts_records)

            logger.info(
                f"Target size audit complete — "
                f"{target_size_summary['checked']} checked, "
                f"{target_size_summary['passed']} passed "
                f"({target_size_summary['pass_rate_pct']}%), "
                f"{target_size_summary['failed']} failed"
            )

        logger.info("\nFULL PIPELINE COMPLETE")
        logger.info("=" * 60)

        return PipelineResponse(
            status="success",
            output_dir=str(output_dir),
            url=url,
            max_depth=max_depth,
            total_images=len(image_crawler.images_data),
            ocr_dir=ocr_dir,
            image_audit_report=image_audit_report,
            image_audit_summary=image_audit_summary,
            total_fields=len(form_inputs),
            form_audit_report=form_audit_report,
            form_audit_summary=form_audit_summary,
            total_interactive_elements=len(interactive_elements),
            label_in_name_report=label_in_name_report,
            label_in_name_summary=label_in_name_summary,
            total_moving_content_items=len(moving_items),
            pause_stop_hide_report=pause_stop_hide_report,
            pause_stop_hide_summary=pause_stop_hide_summary,
            total_target_size_elements=len(target_size_items),
            target_size_report=target_size_report,
            target_size_summary=target_size_summary,
        )

    except Exception as e:
        logger.error(f"Full pipeline failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))