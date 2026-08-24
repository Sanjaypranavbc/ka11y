# text_detector.py

import os
import json
import shutil
import sys
import gc
import csv
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from ka11y.preprocessor import extract_color
from ka11y.accessibility.rules.non_text import contrast_analyser
from ka11y.preprocessor.text_helper_models import (
    TextDetectionResult,
    TextDetectionReport,
    DetailedDetection,
    _json_serializer,
)
from ka11y.utils.text_detector_helper import (
    estimate_boldness,
    bbox_height_rotated,
    load_image_with_alpha,
)
from ka11y.config.logger import setup_logger
from ka11y.utils.config_loader import load_config

config = load_config()

logger = setup_logger(name="KAC", tag="text_detector")
logger.info("Logger initialized")

# ---------------------------------------------------------------------------
# OCR worker pool — process-wide and persistent (created once, reused by
# every scan_directory() call), not a fresh pool per audit run. OCR
# inference (EasyOCR/PaddleOCR) is CPU-bound but releases the GIL during
# the actual numpy/torch/opencv compute, so running several images
# concurrently on a multi-core box cuts wall time substantially instead of
# pinning a single core for the whole scan. Each worker thread lazily loads
# its own OCR reader on first use (see ocrbase.get_ocr_reader) and keeps it
# for the life of the process — a fresh-pool-per-call design would instead
# pay that model-load cost again on every audit.
# Override the worker count with $KA11Y_OCR_WORKERS; default is a
# conservative slice of the box so OCR doesn't starve everything else
# running concurrently (Playwright, other audit jobs, uvicorn itself).
# ---------------------------------------------------------------------------
_OCR_MAX_WORKERS = max(1, int(os.environ.get("KA11Y_OCR_WORKERS", "4")))
_ocr_executor: Optional[ThreadPoolExecutor] = None
_ocr_executor_lock = threading.Lock()


def _get_ocr_executor() -> ThreadPoolExecutor:
    global _ocr_executor
    if _ocr_executor is None:
        with _ocr_executor_lock:
            if _ocr_executor is None:
                _ocr_executor = ThreadPoolExecutor(
                    max_workers=_OCR_MAX_WORKERS, thread_name_prefix="ocr-worker"
                )
    return _ocr_executor

# Engine selection is per-language, not a single global preference:
# PaddleOCR's recognition models handle Japanese/CJK text meaningfully
# better than EasyOCR's, so Japanese pages route to PaddleOCR; every other
# language routes to EasyOCR (lighter — a 2-model pipeline instead of
# PaddleOCR's, and the one this project has run in production the longest).
from ka11y.text_detector.ocrbase import OCRReader as EasyOCRReader

_PADDLEOCR_AVAILABLE = True
try:
    from ka11y.text_detector.paddleocrbase import OCRReader as PaddleOCRReader, PaddleOCR

    # Verify it can actually be initialized (detects missing paddleocr lib)
    if PaddleOCR is None:
        raise ImportError("PaddleOCR not functional")
except (ImportError, RuntimeError):
    _PADDLEOCR_AVAILABLE = False
    logger.info(
        "PaddleOCR not available — Japanese pages will use EasyOCR instead"
    )

_JAPANESE_LANGS = {"ja", "jp"}


def _select_ocr_reader_class(lang: str):
    if lang in _JAPANESE_LANGS:
        if _PADDLEOCR_AVAILABLE:
            return PaddleOCRReader
        logger.warning(
            f"lang={lang!r} requested PaddleOCR but it is not installed — "
            "using EasyOCR instead"
        )
    return EasyOCRReader


class OCRPreprocessing:
    def __init__(
        self,
        source_directory: str,
        output_directory: Optional[str] = None,
        lang: str = "en",
        include_paths: Optional[List[str]] = None,
    ):
        self.source_directory = source_directory
        self.include_paths = [
            str(Path(path).resolve()) for path in (include_paths or []) if path
        ]

        if output_directory is None:
            self.base_output_dir = source_directory
        else:
            self.base_output_dir = output_directory

        ocr_config = config["ocr"]

        base_folder = config["ocr"]["base_folder"] or ""
        contrast_folder = config["ocr"]["contrast_folder"]
        category_config = ocr_config["categories"]

        self.text_detected_dir = os.path.join(self.base_output_dir, base_folder)

        self.contrast_dir = os.path.join(self.text_detected_dir, contrast_folder)
        logger.info(f"base output dir :{self.base_output_dir}")
        logger.info(f"text detected dir :{self.text_detected_dir}")

        self.categories = {
            key: os.path.join(self.text_detected_dir, value)
            for key, value in category_config.items()
        }
        # Create folders
        for path in self.categories.values():
            Path(path).mkdir(parents=True, exist_ok=True)

        Path(self.contrast_dir).mkdir(parents=True, exist_ok=True)

        reader_cls = _select_ocr_reader_class(lang)
        logger.info(
            f"Initializing OCR Reader for lang={lang} (engine={reader_cls.__module__})..."
        )
        self.reader = reader_cls(source_directory, lang=lang)
        logger.info("OCR Reader initialized")

        self.results: List[TextDetectionResult] = []
        # Images that could not be processed (corrupt, missing, OCR backend failure).
        # Populated by detect_text_in_image(); callers can check this to emit warnings.
        self.skipped_images: List[str] = []

    def _determine_category(self, original_path: str) -> str:
        """Heuristic to determine category based on source path."""
        path_str = str(original_path).lower()
        if "button" in path_str:
            return "button_text"
        elif "logo" in path_str:
            return "logo_text"
        elif "informative" in path_str or "informational" in path_str:
            return "informational_text"
        return "with_text"

    # def detect_text_in_image(self, image_path: str) -> TextDetectionResult:
    #     """Use EasyOCR to detect text and run contrast analysis"""
    #     logger.info(f"Processing: {image_path}")
    #
    #     filename = Path(image_path).name
    #     category = self._determine_category(image_path)
    #
    #     result = TextDetectionResult(
    #         filename=filename,
    #         original_path=image_path,
    #         category=category
    #     )
    #
    #     try:
    #         detections = self.reader.readtext(image_path)
    #
    #         if len(detections) > 0:
    #             result.has_text = True
    #             img = cv2.imread(image_path)
    #
    #             for bbox, text, conf in detections:
    #                 clean_bbox = [(int(p[0]), int(p[1])) for p in bbox]
    #
    #                 try:
    #                     contrast_info = contrast_analyser.analyze_text_region(img, clean_bbox)
    #                 except Exception as e:
    #                     logger.warning(f"Contrast analysis failed: {e}")
    #                     contrast_info = None
    #
    #                 violations = []
    #
    #                 color_info = None
    #                 if 'utils.color_picker' in sys.modules:
    #                     try:
    #                         fg_color = extract_color.extract_text_color(img, clean_bbox)
    #                         bg_pixels = extract_color.extract_adjacent_text_pixels(img, clean_bbox)
    #                         bg_colors = extract_color.cluster_colors(bg_pixels, k=3)
    #
    #                         color_info = {
    #                             "foreground": fg_color,
    #                             "background_palette": bg_colors,
    #                             "contrast_checks": []
    #                         }
    #
    #                         fg_lum = fg_color['luminance']
    #                         for bg in bg_colors:
    #                             bg_lum = bg['luminance']
    #                             l1 = max(fg_lum, bg_lum)
    #                             l2 = min(fg_lum, bg_lum)
    #                             ratio = (l1 + 0.05) / (l2 + 0.05)
    #                             compliance = contrast_analyser.check_wcag_compliance(ratio)
    #                             color_info["contrast_checks"].append({
    #                                 "bg_color": bg,
    #                                 "ratio": round(ratio, 2),
    #                                 "compliance": compliance
    #                             })
    #                             if not compliance['AA_normal']:
    #                                 violations.append(f"Fails AA Normal vs BG {bg['hex']}")
    #
    #                     except Exception as cp_err:
    #                         logger.warning(f"Color picker failed for region: {cp_err}")
    #
    #                 if contrast_info and not contrast_info.get('error'):
    #                     if 'compliance' in contrast_info:
    #                         compliance = contrast_info['compliance']
    #                         if not compliance.get('AA_normal', False):
    #                             violations.append("Fails AA Normal")
    #
    #                 if violations:
    #                     result.contrast_violations_count += 1
    #
    #                 result.detections.append(DetailedDetection(
    #                     text=text,
    #                     confidence=float(conf),
    #                     bbox=clean_bbox,
    #                     contrast_info=contrast_info,
    #                     color_info=color_info,
    #                     wcag_violations=violations
    #                 ))
    #
    #             # Copy image to appropriate text category folder
    #             dest_folder = self.categories.get(category, self.categories["with_text"])
    #             dest_path = os.path.join(dest_folder, filename)
    #             shutil.copy2(image_path, dest_path)
    #
    #             result.new_path = dest_path
    #
    #             logger.info(
    #                 f"✓ Detected {len(detections)} text regions. Category: {category}. Violations: {result.contrast_violations_count}")
    #         else:
    #             logger.debug(f"No text detected in {filename}")
    #
    #     except Exception as e:
    #         logger.error(f"Error processing {filename}: {str(e)}")
    #         import traceback
    #         traceback.print_exc()
    #
    #     return result

    def is_valid_text(self, bbox, text, conf):
        if conf < 0.6:
            return False
        if len(text.strip()) <= 1:
            return False
        if not any(c.isalnum() for c in text):
            return False

        tl, tr, br, bl = bbox
        width = tr[0] - tl[0]
        height = bl[1] - tl[1]

        if width * height < 500:
            return False

        return True

    def detect_text_in_image(self, image_path: str) -> TextDetectionResult:
        """Use EasyOCR to detect text and run contrast analysis"""
        logger.info(f"Processing: {image_path}")

        filename = Path(image_path).name
        category = self._determine_category(image_path)
        # Always store as absolute so the API can serve images regardless of CWD
        abs_path = str(Path(image_path).resolve())

        result = TextDetectionResult(
            filename=filename, original_path=abs_path, category=category
        )

        if not Path(image_path).exists():
            logger.error(f"[text_detector] image not found, skipping: {image_path}")
            self.skipped_images.append(image_path)
            return result

        try:
            detections = self.reader.readtext(image_path)

            if len(detections) > 0:
                result.has_text = True
                img = load_image_with_alpha(image_path)

                if img is None:
                    logger.error(f"Failed to load image: {image_path}")
                    return result

                device_pixel_ratio = config.get("device_pixel_ratio", 1.0)

                for bbox, text, conf in detections:
                    if not self.is_valid_text(bbox, text, conf):
                        continue

                    clean_bbox = [(int(p[0]), int(p[1])) for p in bbox]

                    # ✅ NEW: clamp bbox to image bounds
                    h, w = img.shape[:2]
                    clean_bbox = [
                        (max(0, min(x, w - 1)), max(0, min(y, h - 1)))
                        for x, y in clean_bbox
                    ]

                    # ✅ F10: correct rotated bbox height
                    bbox_height = bbox_height_rotated(clean_bbox)

                    # ✅ F6: DPR-aware normalization
                    font_size_px = max(bbox_height / device_pixel_ratio, 8)

                    # ✅ F5: detect bold text
                    is_bold = estimate_boldness(img, clean_bbox)

                    # NOTE on UI components (buttons/icons): this OCR
                    # detection is *text* baked into an image, so it is
                    # always scored against the WCAG 1.4.3/1.4.6 text-size
                    # thresholds below (via `is_bold`/`font_size_px`) — never
                    # the 3:1 `is_ui_component` shortcut in
                    # check_wcag_compliance. That shortcut is for the
                    # component's own boundary/fill contrast (WCAG 1.4.11),
                    # a different visual feature computed separately by
                    # `contrast_analyser.analyze_ui_component()` (real page
                    # context, in alttext.py's `_check_1_4_11`) or, as a
                    # fallback approximation, by comparing this same
                    # detection's raw `contrast_ratio` against 3:1 directly —
                    # not by relaxing this text's own compliance dict.
                    try:
                        contrast_info = contrast_analyser.analyze_text_region(
                            img, clean_bbox, font_size_px=font_size_px, is_bold=is_bold
                        )
                    except Exception as e:
                        logger.warning(f"Contrast analysis failed: {e}")
                        contrast_info = None

                    violations = []

                    color_info = None
                    if contrast_info and not contrast_info.get("error"):
                        try:
                            # analyze_ui_component does not return "region"/"mask"
                            # keys — only analyze_text_region does.  Skip colour
                            # extraction when the keys are absent to avoid KeyError.
                            if (
                                "region" not in contrast_info
                                or "mask" not in contrast_info
                            ):
                                raise ValueError(
                                    "No region/mask available for colour extraction"
                                )

                            extracted = extract_color.extract_colors_from_mask(
                                contrast_info["region"], contrast_info["mask"], k_bg=3
                            )

                            if "error" not in extracted:
                                fg_color = extracted["foreground"]
                                bg_colors = extracted["background_palette"]

                                dominant_bg = max(bg_colors, key=lambda c: c["percent"])

                                fg_lum = fg_color["luminance"]

                                # Build contrast_checks for all clusters (for reporting).
                                contrast_checks = []
                                for bg in bg_colors:
                                    bg_lum = bg["luminance"]
                                    l1 = max(fg_lum, bg_lum)
                                    l2 = min(fg_lum, bg_lum)
                                    ratio = (l1 + 0.05) / (l2 + 0.05)
                                    compliance = (
                                        contrast_analyser.check_wcag_compliance(
                                            ratio,
                                            font_size_px=font_size_px,
                                            is_bold=is_bold,
                                        )
                                    )
                                    contrast_checks.append(
                                        {
                                            "bg_color": bg,
                                            "ratio": round(ratio, 2),
                                            "compliance": compliance,
                                        }
                                    )

                                dom_bg_lum = dominant_bg["luminance"]
                                l1 = max(fg_lum, dom_bg_lum)
                                l2 = min(fg_lum, dom_bg_lum)
                                dominant_ratio = round((l1 + 0.05) / (l2 + 0.05), 2)
                                dominant_compliance = (
                                    contrast_analyser.check_wcag_compliance(
                                        dominant_ratio,
                                        font_size_px=font_size_px,
                                        is_bold=is_bold,
                                    )
                                )

                                color_info = {
                                    "foreground": fg_color,
                                    "background_palette": bg_colors,
                                    "contrast_checks": contrast_checks,
                                    # Single authoritative pair used for violation + UI display.
                                    "dominant_contrast": {
                                        "bg_color": dominant_bg,
                                        "ratio": dominant_ratio,
                                        "compliance": dominant_compliance,
                                    },
                                }

                                if not dominant_compliance["AA_passes"]:
                                    violations.append(
                                        f"Fails AA Normal vs BG {dominant_bg['hex']}"
                                    )
                            else:
                                logger.warning(
                                    f"Color extraction failed: {extracted['error']}"
                                )

                        except Exception as cp_err:
                            logger.warning(f"Color picker failed for region: {cp_err}")

                    if (
                        color_info is None
                        and contrast_info
                        and not contrast_info.get("error")
                        and not contrast_info.get("needs_review")
                    ):
                        ratio_fb = contrast_info.get("contrast_ratio", 0)

                        compliance_fb = contrast_analyser.check_wcag_compliance(
                            ratio_fb,
                            font_size_px=font_size_px,
                            is_bold=is_bold,
                        )
                        if not compliance_fb.get("AA_passes", False):
                            bg_rgb = contrast_info.get(
                                "background_color", (255, 255, 255)
                            )
                            bg_hex = "#{:02x}{:02x}{:02x}".format(*bg_rgb)
                            violations.append(f"Fails AA Normal vs BG {bg_hex}")
                    if violations:
                        result.contrast_violations_count += 1

                    # Contrast genuinely couldn't be determined (analysis
                    # raised, or segmentation/colour extraction reported an
                    # error/needs_review) — distinct from "determined and
                    # passed". Both previously left `violations == []` with
                    # no way to tell them apart, silently deflating violation
                    # counts on exactly the low-contrast images most likely
                    # to make segmentation fail.
                    contrast_undetermined = (
                        color_info is None
                        and not violations
                        and (
                            contrast_info is None
                            or contrast_info.get("error")
                            or contrast_info.get("needs_review")
                        )
                    )
                    if contrast_undetermined:
                        result.contrast_needs_review_count += 1

                    result.detections.append(
                        DetailedDetection(
                            text=text,
                            confidence=float(conf),
                            bbox=clean_bbox,
                            needs_review=contrast_undetermined,
                            contrast_info=contrast_info,
                            color_info=color_info,
                            wcag_violations=violations,
                        )
                    )

                # Copy image to appropriate text category folder
                dest_folder = self.categories.get(
                    category, self.categories["with_text"]
                )
                dest_path = os.path.join(dest_folder, filename)
                shutil.copy2(image_path, dest_path)

                result.new_path = dest_path

                logger.info(
                    f"✓ Detected {len(detections)} text regions. Category: {category}. Violations: {result.contrast_violations_count}"
                )
            else:
                logger.debug(f"No text detected in {filename}")

        except Exception as e:
            logger.error(f"[text_detector] Error processing {filename}: {str(e)}")
            self.skipped_images.append(image_path)
            import traceback
            traceback.print_exc()

        return result

    def scan_directory(self):
        """Scan source directory for images"""
        logger.info(f"Scanning directory: {self.source_directory}")

        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        if self.include_paths:
            image_files = [
                path
                for path in self.include_paths
                if Path(path).suffix.lower() in image_extensions and Path(path).exists()
            ]
            logger.info(f"OCR candidate allowlist active: {len(image_files)} file(s)")
        else:
            image_files = []
            for root, dirs, files in os.walk(self.source_directory):
                # Avoid scanning our own output directories if they are inside source
                if "text_detected" in root or "contrast" in root:
                    continue

                for file in files:
                    if Path(file).suffix.lower() in image_extensions:
                        image_files.append(os.path.join(root, file))

        # OCR for each image is independent (own file, own result object), so
        # run the batch through a persistent worker pool instead of one image
        # at a time. executor.map preserves input order in the results it
        # yields even though the underlying work completes out of order, so
        # this is a drop-in replacement for the old sequential loop.
        executor = _get_ocr_executor()
        for result in executor.map(self.detect_text_in_image, image_files):
            self.results.append(result)

            if result.has_text:
                print(
                    f"  ✓ Found {len(result.detections)} text regions ({result.category})"
                )
                if result.contrast_violations_count > 0:
                    print(
                        f"  ⚠ {result.contrast_violations_count} contrast violations detected!"
                    )
            else:
                print("  . No text")

        # One GC pass for the whole batch instead of one per image — the old
        # per-image gc.collect() was a blanket OOM guard that cost real time
        # on every single iteration; a single end-of-batch pass gives most of
        # the same memory-pressure relief without paying that cost N times.
        gc.collect()

        if self.skipped_images:
            logger.warning(
                f"[text_detector] {len(self.skipped_images)} image(s) could not be "
                f"processed and were skipped: {self.skipped_images}"
            )


class TextClassification:

    def __init__(self, source_directory: str, output_directory: Optional[str] = None):
        self.source_directory = source_directory

        # Main output directory inside the crawl directory
        if output_directory is None:
            self.base_output_dir = source_directory
        else:
            self.base_output_dir = output_directory

        self.text_detected_dir = os.path.join(self.base_output_dir, "text_detected")
        self.contrast_dir = os.path.join(self.text_detected_dir, "contrast")

        self.results: List[TextDetectionResult] = []

        # Create output directory structure
        self._create_directories()

    def _create_directories(self):
        """Create necessary output directories"""
        self.categories = {
            "button_text": os.path.join(self.text_detected_dir, "button_text"),
            "informational_text": os.path.join(
                self.text_detected_dir, "informational_text"
            ),
            "logo_text": os.path.join(self.text_detected_dir, "logo_text"),
            "with_text": os.path.join(self.text_detected_dir, "with_text"),
        }

        # Create text detection folders
        for path in self.categories.values():
            Path(path).mkdir(parents=True, exist_ok=True)

        # Create contrast folder
        Path(self.contrast_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directories in {self.base_output_dir}")

    def save_reports(self):
        """Save JSON, CSV and Contrast Markdown reports"""
        total_detections = sum(len(r.detections) for r in self.results)
        detections_with_color = sum(
            1 for r in self.results for d in r.detections if d.color_info
        )
        logger.info(
            f"save_reports: {len(self.results)} results | "
            f"{total_detections} detections | "
            f"{detections_with_color} with color_info"
        )

        # JSON Report (Full Report)
        json_file = os.path.join(self.text_detected_dir, "text_detection_report.json")

        images_with_text = sum(1 for r in self.results if r.has_text)
        images_with_violations = sum(
            1 for r in self.results if r.contrast_violations_count > 0
        )
        images_with_needs_review = sum(
            1 for r in self.results if r.contrast_needs_review_count > 0
        )

        report = TextDetectionReport(
            scan_date=datetime.utcnow().isoformat(),
            source_directory=self.source_directory,
            total_images_scanned=len(self.results),
            images_with_text=images_with_text,
            images_with_contrast_violations=images_with_violations,
            images_with_contrast_needs_review=images_with_needs_review,
            results=self.results,
        )

        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(
                report.model_dump(),
                f,
                indent=2,
                ensure_ascii=False,
                default=_json_serializer,
            )

        # CSV Report
        csv_file = os.path.join(self.contrast_dir, "contrast_report.csv")
        self._generate_contrast_csv(csv_file)

        # Contrast JSON Report
        contrast_json = os.path.join(self.contrast_dir, "contrast_report.json")
        self._generate_contrast_json(contrast_json)

        # Markdown Report
        md_file = os.path.join(self.contrast_dir, "contrast_report.md")
        self._generate_contrast_markdown(md_file, images_with_violations)

        print(f"\n{'=' * 60}")
        print("SCAN COMPLETE")
        print(f"Total images: {len(self.results)}")
        print(f"With text: {images_with_text}")
        print(f"Contrast violations: {images_with_violations}")
        print(f"Contrast needs review (could not be determined): {images_with_needs_review}")
        print("Reports saved to:")
        print(f"  - {json_file}")
        print(f"  - {csv_file}")
        print(f"  - {contrast_json}")
        print(f"  - {md_file}")
        print(f"{'=' * 60}")

    def _generate_contrast_markdown(self, output_path: str, violation_count: int):
        """Generate a user-friendly Markdown report for contrast analysis"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# WCAG Contrast Analysis Report\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Total Violations Found:** {violation_count}\n\n")

            f.write("## Color Palette Analysis\n\n")
            for result in self.results:
                # Check if this image has any detections with color info
                if result.has_text and any(d.color_info for d in result.detections):
                    f.write(f"### Image: `{result.filename}`\n")
                    f.write(f"**Path**: `{result.original_path}`\n\n")

                    for i, det in enumerate(result.detections, 1):
                        if det.color_info:
                            text_snippet = det.text.replace("\n", " ")[:30]
                            # Clean up snippet
                            if len(det.text) > 30:
                                text_snippet += "..."

                            f.write(f'#### {i}. Text: "{text_snippet}"\n')

                            fg = det.color_info.get("foreground") or {}
                            f.write(
                                f"- **Detected Text Color**: {fg.get('hex', 'N/A')} (Lum: {fg.get('luminance', 'N/A')})\n\n"
                            )

                            f.write(
                                "| Background | Ratio | AA Normal | AA Large | AAA Normal | AAA Large |\n"
                            )
                            f.write("|---|---|---|---|---|---|\n")

                            for check in det.color_info.get("contrast_checks", []):
                                bg = check["bg_color"]
                                ratio = check["ratio"]
                                comp = check["compliance"]

                                aa = "✅" if comp.get("AA_passes") else "❌"
                                aa_lg = (
                                    "✅" if comp.get("AA_passes") else "❌"
                                )  # no separate large key anymore
                                aaa = "✅" if comp.get("AAA_passes") else "❌"
                                aaa_lg = "✅" if comp.get("AAA_passes") else "❌"

                                f.write(
                                    f"| {bg['hex']} | {ratio}:1 | {aa} | {aa_lg} | {aaa} | {aaa_lg} |\n"
                                )
                            f.write("\n")
                    f.write("---\n\n")

    def _generate_contrast_csv(self, output_path):
        """Generate CSV report for contrast results"""

        with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)

            writer.writerow(
                [
                    "Image",
                    "Image Path",
                    "Text",
                    "Foreground Color",
                    "Background Color",
                    "Contrast Ratio",
                    "AA Normal",
                    "AA Large",
                    "AAA Normal",
                    "AAA Large",
                ]
            )

            for result in self.results:
                for det in result.detections:
                    if det.color_info:
                        fg = (det.color_info.get("foreground") or {}).get("hex", "N/A")

                        for check in det.color_info.get("contrast_checks", []):
                            bg = check["bg_color"]["hex"]
                            ratio = check["ratio"]
                            comp = check["compliance"]

                            writer.writerow(
                                [
                                    result.filename,
                                    result.original_path,  # ← added
                                    det.text,
                                    fg,
                                    bg,
                                    ratio,
                                    comp.get("AA_passes"),
                                    comp.get("AA_passes"),
                                    comp.get("AAA_passes"),
                                    comp.get("AAA_passes"),
                                ]
                            )
                    elif det.needs_review:
                        # Contrast could not be determined — surface it as a
                        # NEEDS_REVIEW row instead of silently omitting the
                        # detection, which previously made this report look
                        # identical to "checked and passed".
                        writer.writerow(
                            [
                                result.filename,
                                result.original_path,
                                det.text,
                                "N/A",
                                "N/A",
                                "NEEDS_REVIEW",
                                "NEEDS_REVIEW",
                                "NEEDS_REVIEW",
                                "NEEDS_REVIEW",
                                "NEEDS_REVIEW",
                            ]
                        )

    def _generate_contrast_json(self, output_path):
        """Generate JSON report only for contrast analysis"""

        contrast_data = []

        for result in self.results:
            for det in result.detections:
                if det.color_info:
                    contrast_data.append(
                        {
                            "image": result.filename,
                            "image_path": result.original_path,  # ← added
                            "text": det.text,
                            "foreground": det.color_info.get("foreground"),
                            "background_palette": det.color_info.get(
                                "background_palette"
                            ),
                            "contrast_checks": det.color_info.get("contrast_checks"),
                            "wcag_violations": det.wcag_violations,
                            "needs_review": False,
                        }
                    )
                elif det.needs_review:
                    # Surface undetermined-contrast detections instead of
                    # silently omitting them (see DetailedDetection.needs_review).
                    contrast_data.append(
                        {
                            "image": result.filename,
                            "image_path": result.original_path,
                            "text": det.text,
                            "foreground": None,
                            "background_palette": None,
                            "contrast_checks": None,
                            "wcag_violations": det.wcag_violations,
                            "needs_review": True,
                        }
                    )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(contrast_data, f, indent=2)


def main():
    if len(sys.argv) > 1:
        source_directory = sys.argv[1]
    else:
        source_directory = "crawled_images"
        if os.path.exists(source_directory):
            crawl_dirs = [
                d
                for d in os.listdir(source_directory)
                if os.path.isdir(os.path.join(source_directory, d))
            ]
            if crawl_dirs:
                crawl_dirs.sort(
                    key=lambda x: os.path.getmtime(os.path.join(source_directory, x)),
                    reverse=True,
                )
                source_directory = os.path.join(source_directory, crawl_dirs[0])

    if not os.path.exists(source_directory):
        print(f"Error: Directory {source_directory} not found.")
        return

    detector = OCRPreprocessing(source_directory)
    detector.scan_directory()

    save = TextClassification(source_directory)
    save.results = detector.results
    save.save_reports()


# if __name__ == "__main__":
#     main()
