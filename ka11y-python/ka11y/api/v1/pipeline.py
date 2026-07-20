"""
ka11y/api/routes/pipeline.py
============================
Image crawl + audit endpoint.

  POST /pipeline/

  STEP 1  Image Crawl  →  AsyncImageCrawler
  STEP 2  OCR          →  OCRPreprocessing + TextClassification  (optional)
  STEP 3  Image Audit  →  AltTextAccessibilityAuditor            (optional)

Because get_output_dir is a plain Depends (not lru_cache), FastAPI resolves
it once per request and re-uses the same Path object for every dependency
that lists it.
"""

from __future__ import annotations

import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException


from ka11y.config.logger import setup_logger

from ka11y.api.v1.dependencies import (
    get_output_dir,
    get_image_crawler,
    get_alt_text_auditor,
)
from ka11y.api.v1.models.pipeline import PipelineRequest, PipelineResponse
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # The optimized crawler is a drop-in for AsyncImageCrawler (same interface).
    from ka11y.crawler.optimized import OptimizedImageCrawler as AsyncImageCrawler

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
logger = setup_logger(name="KAC", tag="pipeline")


# ── Contrast extraction helper ────────────────────────────────────────────────


def extract_contrast_report(ocr_results: list) -> Dict[str, Any]:
    """
    Walk OCR results and build a structured contrast report that is safe to
    serialise as JSON.

    Returns
    -------
    {
        "summary": {
            "total_regions_analysed": int,
            "total_violations":       int,
            "images_with_violations": int,
            "pass_rate_pct":          float,
        },
        "table": [          # one row per text-detection region
            {
                "image":            str,
                "image_path":       str,
                "text":             str,
                "confidence":       float,
                "foreground_hex":   str | None,
                "foreground_lum":   float | None,
                "background_hex":   str | None,   # dominant bg
                "background_lum":   float | None,
                "contrast_ratio":   float | None,
                "AA_normal":        bool | None,
                "AA_large":         bool | None,
                "AAA_normal":       bool | None,
                "AAA_large":        bool | None,
                "violations":       list[str],
            },
            ...
        ],
        "images": [         # one entry per image that has detections
            {
                "filename":                  str,
                "path":                      str,
                "contrast_violations_count": int,
                "detections": [
                    {
                        "text":           str,
                        "confidence":     float,
                        "bbox":           list,
                        "foreground":     dict | None,
                        "background_palette": list[dict],
                        "contrast_checks":    list[dict],
                        "wcag_violations":    list[str],
                        "ratio":          float | None,
                        "AA_normal":      bool | None,
                        "AA_large":       bool | None,
                        "AAA_normal":     bool | None,
                        "AAA_large":      bool | None,
                    },
                    ...
                ],
            },
            ...
        ],
    }
    """
    table_rows: List[Dict[str, Any]] = []
    images_detail: List[Dict[str, Any]] = []
    total_violations = 0
    images_with_violations = 0

    for result in ocr_results:
        if not result.has_text:
            continue

        image_detections: List[Dict[str, Any]] = []
        image_has_violation = False

        for det in result.detections:
            # ── pull contrast_info (from contrast_analyser.analyze_text_region) ──
            ci = det.contrast_info or {}
            col = det.color_info or {}

            ratio: Optional[float] = None
            aa_n = aaa_n = None

            compliance = ci.get("compliance") or {}
            if compliance:
                ratio = compliance.get("contrast_ratio")
                aa_n = compliance.get("AA_passes")
                aaa_n = compliance.get("AAA_passes")

            # ── foreground / background from color_info (cluster-based) ──────────
            fg = col.get("foreground") or {}
            bg_pal = col.get("background_palette") or []
            checks = col.get("contrast_checks") or []

            # dominant background = first cluster with the highest contrast check
            dominant_bg: Dict[str, Any] = {}
            if bg_pal:
                dominant_bg = bg_pal[0]

            # flat table row (one per detection)
            table_rows.append(
                {
                    "image": result.filename,
                    "image_path": result.original_path,
                    "text": det.text,
                    "confidence": round(float(det.confidence), 3),
                    "foreground_hex": fg.get("hex"),
                    "foreground_lum": fg.get("luminance"),
                    "background_hex": dominant_bg.get("hex"),
                    "background_lum": dominant_bg.get("luminance"),
                    "contrast_ratio": ratio,
                    "AA_normal": aa_n,
                    "AAA_normal": aaa_n,
                    "violations": list(det.wcag_violations or []),
                }
            )

            if det.wcag_violations:
                total_violations += len(det.wcag_violations)
                image_has_violation = True

            # full detection record (nested under its image)
            image_detections.append(
                {
                    "text": det.text,
                    "confidence": round(float(det.confidence), 3),
                    "bbox": det.bbox,
                    "foreground": fg or None,
                    "background_palette": bg_pal,
                    "contrast_checks": checks,
                    "wcag_violations": list(det.wcag_violations or []),
                    "ratio": ratio,
                    "AA_normal": aa_n,
                    "AAA_normal": aaa_n,
                }
            )

        if image_has_violation:
            images_with_violations += 1

        if image_detections:
            images_detail.append(
                {
                    "filename": result.filename,
                    "path": result.original_path,
                    "contrast_violations_count": result.contrast_violations_count,
                    "detections": image_detections,
                }
            )

    total_regions = len(table_rows)
    # Bug 6 fix: total_violations counts per-criterion failures (a single region can
    # fail both 1.4.3 and 1.4.6), so subtracting it from total_regions can produce a
    # negative result. Count failing REGIONS instead (each region contributes at most 1).
    failing_regions = sum(1 for row in table_rows if row.get("violations"))
    pass_rate = (
        round((total_regions - failing_regions) / total_regions * 100, 1)
        if total_regions
        else 0.0
    )

    return {
        "summary": {
            "total_regions_analysed": total_regions,
            "total_violations": total_violations,
            "images_with_violations": images_with_violations,
            "pass_rate_pct": pass_rate,
        },
        "table": table_rows,
        "images": images_detail,
    }


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/", response_model=PipelineResponse)
async def run_full_pipeline(
    payload: PipelineRequest,
    # ── shared output directory (resolved once, reused by all deps) ────────
    output_dir: Path = Depends(get_output_dir),
    # ── crawlers ──────────────────────────────────────────────────────────
    image_crawler: AsyncImageCrawler = Depends(get_image_crawler),
    # ── auditors ──────────────────────────────────────────────────────────
    image_auditor: AltTextAccessibilityAuditor = Depends(get_alt_text_auditor),
):
    url = str(payload.url)
    max_depth = payload.max_depth

    logger.info("=" * 60)
    logger.info("KA11Y FULL PIPELINE START")
    logger.info(f"  URL        : {url}")
    logger.info(f"  max_depth  : {max_depth}")
    logger.info(f"  output_dir : {output_dir}")
    logger.info("=" * 60)

    ocr_results = []
    ocr_dir = None
    contrast_report = None
    image_audit_report = None
    image_audit_summary = None

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

            from ka11y.text_detector.text_detector import (
                OCRPreprocessing,
                TextClassification,
            )

            detector = OCRPreprocessing(source_directory=image_crawler.output_dir)
            detector.scan_directory()

            save = TextClassification(source_directory=image_crawler.output_dir)
            save.results = detector.results
            save.save_reports()

            ocr_results = detector.results
            ocr_dir = str(detector.text_detected_dir)

            # ── Build structured contrast report from OCR results ─────────
            contrast_report = extract_contrast_report(ocr_results)

            logger.info(
                f"OCR complete — {len(ocr_results)} images processed, "
                f"{sum(1 for r in ocr_results if r.has_text)} with text | "
                f"contrast violations: {contrast_report['summary']['total_violations']}"
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

            total = len(img_records)
            passed = sum(1 for r in img_records if r["overall_status"] == "PASSED")
            failed = total - passed

            by_class: Dict[str, Dict[str, int]] = {}
            for r in img_records:
                cls = r["classification"]
                if cls not in by_class:
                    by_class[cls] = {"passed": 0, "failed": 0}
                by_class[cls][
                    "passed" if r["overall_status"] == "PASSED" else "failed"
                ] += 1

            image_audit_summary = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
                "wcag_1_1_1_failed": sum(
                    1 for r in img_records if r["wcag_1_1_1_status"] == "FAILED"
                ),
                "wcag_4_1_2_failed": sum(
                    1 for r in img_records if r["wcag_4_1_2_status"] == "FAILED"
                ),
                "images_with_ocr": sum(1 for r in img_records if r["has_ocr_text"]),
                "contrast_violations": sum(
                    1 for r in img_records if r["contrast_violations_count"] > 0
                ),
                "by_classification": by_class,
            }

            logger.info(
                f"Image audit complete — {total} images, "
                f"{passed} passed ({image_audit_summary['pass_rate_pct']}%), {failed} failed"
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
            contrast_report=contrast_report,  # ← NEW
        )

    except Exception as e:
        # Internal error context (exception type, message, traceback) is logged
        # but NEVER returned to the client. The opaque error_id allows support
        # staff to correlate a 500 response with the corresponding log entry.
        error_id = uuid.uuid4().hex
        logger.error(f"Full pipeline failed (error_id={error_id}): {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Pipeline failed due to an internal error.",
                "error_id": error_id,
            },
        )
