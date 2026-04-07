"""
ka11y/api/v1/combined/stages.py
=================================
All per-stage coroutines and the Python pipeline orchestrator.

Each stage coroutine:
  - owns its crawler + auditor lifecycle
  - calls _stage_start / _stage_complete / _stage_error_and_warn
  - offloads CPU-bound auditor work via asyncio.to_thread()
  - returns a flat List[Dict] of findings (image_audit also returns contrast_report)

_run_python_stages() gathers all stages concurrently.
"""

from __future__ import annotations

import asyncio
import functools
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ka11y.crawler.universal_page import PageSnapshot, UniversalPageLoader

# Maximum wall-clock seconds for the full image-audit stage (crawl + OCR).
_STAGE_TIMEOUT_SECONDS = 600
# Maximum seconds for the universal snapshot (single page load for all crawlers).
_SNAPSHOT_TIMEOUT_SECONDS = 60
# Maximum seconds for the crawler pass only.  OCR always runs on whatever
# images were saved before this deadline, so a slow/stuck target never
# prevents contrast analysis from completing.
# Button/icon screenshots are now capped at 5 s each (crawler.py), so 300 s
# handles up to ~60 stuck elements before we cut over to OCR on partial images.
_CRAWL_TIMEOUT_SECONDS = 300

import httpx

from ka11y.config.logger import setup_logger

from .findings import (
    IMAGE_AUDIT_RECORD_CONVERTERS,
    OCR_RESULT_CONVERTERS,
    _build_contrast_report,
    _crawler_text_spacing_to_findings,
    _focus_not_obscured_enh_to_findings,
    _focus_not_obscured_min_to_findings,
    _form_to_findings,
    _hover_focus_content_to_findings,
    _lin_to_findings,
    _media_to_findings,
    _orientation_to_findings,
    _psh_to_findings,
    _reflow_to_findings,
    _rendered_text_spacing_to_findings,
    _resize_text_to_findings,
    _ts_to_findings,
)
from .stage_events import _stage_complete, _stage_error_and_warn, _stage_start, _stage_warn

logger = setup_logger(name="KAC", tag="combined")


# ── WCAG level filter ─────────────────────────────────────────────────────────


def _allowed_levels(wcag_level: str) -> set:
    levels = {"A"}
    if wcag_level in ("AA", "AAA"):
        levels.add("AA")
    if wcag_level == "AAA":
        levels.add("AAA")
    return levels


# ── Node / axe-core caller ────────────────────────────────────────────────────


async def _call_node_flat(
    url: str, node_base_url: str, wcag_level: str = "AAA", lang: str = "en"
) -> List[Dict]:
    """POST to Node's /api/v1/analyse-url-flat. Returns flat element-wise findings."""
    endpoint = f"{node_base_url.rstrip('/')}/api/v1/analyse-url-flat"
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(endpoint, json={"url": url, "level": wcag_level, "lang": lang})
        resp.raise_for_status()
        return resp.json().get("findings", [])


# ── Individual stage coroutines ───────────────────────────────────────────────


async def _stage_image_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    job_id: str,
    lang: str = "en",
) -> Tuple[List[Dict], Optional[Dict[str, Any]]]:
    """Crawl images → OCR → 1.1.1 alt-text + 1.4.3 contrast."""
    _stage_start(job_id, "image_audit")
    if not run_ocr and not run_image_audit:
        _stage_complete(job_id, "image_audit", 0)
        return [], None

    try:
        from ka11y.accessibility.rules.non_text.alttext import (
            AltTextAccessibilityAuditor,
        )
        from ka11y.crawler.crawler import AsyncImageCrawler
        from ka11y.text_detector.text_detector import (
            OCRPreprocessing,
            TextClassification,
        )

        image_crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)

        async def _crawl_and_save() -> None:
            await image_crawler.crawl_page()
            await asyncio.to_thread(image_crawler.save_results)

        try:
            await asyncio.wait_for(_crawl_and_save(), timeout=_CRAWL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            _stage_warn(
                job_id,
                f"image_audit: crawler exceeded {_CRAWL_TIMEOUT_SECONDS}s "
                f"— partial image set from {image_crawler.output_dir}",
            )

        ocr_results: list = []
        contrast_report: Optional[Dict[str, Any]] = None
        findings: List[Dict] = []

        if run_ocr:
            detector = OCRPreprocessing(source_directory=image_crawler.output_dir, lang=lang)
            await asyncio.to_thread(detector.scan_directory)

            saver = TextClassification(source_directory=image_crawler.output_dir)
            saver.results = detector.results
            await asyncio.to_thread(saver.save_reports)

            ocr_results = detector.results
            contrast_report = _build_contrast_report(ocr_results)
            for _, converter in OCR_RESULT_CONVERTERS:
                findings.extend(converter(ocr_results, url, job_id=job_id))

        if run_image_audit:
            auditor = AltTextAccessibilityAuditor()
            records = await asyncio.to_thread(
                auditor.generate_audit_report,
                images_data=image_crawler.images_data,
                ocr_results=ocr_results,
                output_dir=image_crawler.output_dir,
            )
            for _, converter in IMAGE_AUDIT_RECORD_CONVERTERS:
                findings.extend(converter(records, url))

        _stage_complete(job_id, "image_audit", len(findings))
        return findings, contrast_report
    except Exception as _exc:
        _stage_error_and_warn(job_id, "image_audit", _exc)
        return [], None


async def _stage_form_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_form_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl forms → 3.3.1 / 3.3.2 label + error checks."""
    _stage_start(job_id, "form_audit")
    if not run_form_audit:
        _stage_complete(job_id, "form_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.forms.form_auditor import (
            FormAccessibilityAuditor,
        )
        from ka11y.crawler.forms_crawler import AsyncFormCrawler

        if snapshot is not None:
            form_crawler = AsyncFormCrawler.from_snapshot(snapshot.forms, url, str(output_dir))
        else:
            form_crawler = AsyncFormCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await form_crawler.crawl()
        form_inputs = form_crawler.results
        await asyncio.to_thread(form_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_form_audit:
            form_auditor = FormAccessibilityAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                functools.partial(
                    form_auditor.generate_audit_report, form_inputs=form_inputs
                )
            )
            findings = _form_to_findings(records, url)

        _stage_complete(job_id, "form_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "form_audit", _exc)
        return []


async def _stage_label_in_name(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_label_in_name_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl interactive elements → 2.5.3 label-in-name check."""
    _stage_start(job_id, "label_in_name")
    if not run_label_in_name_audit:
        _stage_complete(job_id, "label_in_name", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import (
            LabelInNameAuditor,
        )
        from ka11y.crawler.interactive_crawler import InteractiveElementCrawler

        if snapshot is not None:
            interactive_crawler = InteractiveElementCrawler.from_snapshot(snapshot.interactive, url, str(output_dir))
        else:
            interactive_crawler = InteractiveElementCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await interactive_crawler.crawl()
        interactive_elements = interactive_crawler.results
        await asyncio.to_thread(interactive_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_label_in_name_audit:
            lin_auditor = LabelInNameAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                lin_auditor.generate_audit_report, interactive_elements
            )
            findings = _lin_to_findings(records, url)

        _stage_complete(job_id, "label_in_name", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "label_in_name", _exc)
        return []


async def _stage_pause_stop_hide(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_pause_stop_hide_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl moving content → 2.2.2 pause/stop/hide check."""
    _stage_start(job_id, "pause_stop_hide")
    if not run_pause_stop_hide_audit:
        _stage_complete(job_id, "pause_stop_hide", 0)
        return []

    try:
        from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import (
            PauseStopHideAuditor,
        )
        from ka11y.crawler.moving_content_crawler import MovingContentCrawler

        if snapshot is not None:
            moving_crawler = MovingContentCrawler.from_snapshot(snapshot.moving_content, url, str(output_dir))
        else:
            moving_crawler = MovingContentCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await moving_crawler.crawl()
        moving_items = moving_crawler.results
        await asyncio.to_thread(moving_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_pause_stop_hide_audit:
            psh_auditor = PauseStopHideAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                psh_auditor.generate_audit_report, moving_items
            )
            findings = _psh_to_findings(records, url)

        _stage_complete(job_id, "pause_stop_hide", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "pause_stop_hide", _exc)
        return []


async def _stage_target_size(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_target_size_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl touch targets → 2.5.8 target-size check."""
    _stage_start(job_id, "target_size")
    if not run_target_size_audit:
        _stage_complete(job_id, "target_size", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.target_size_auditor import (
            TargetSizeAuditor,
        )
        from ka11y.crawler.target_size_crawler import TargetSizeCrawler

        if snapshot is not None:
            ts_crawler = TargetSizeCrawler.from_snapshot(snapshot.target_sizes, url, str(output_dir))
        else:
            ts_crawler = TargetSizeCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await ts_crawler.crawl()
        ts_items = ts_crawler.results
        await asyncio.to_thread(ts_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_target_size_audit:
            ts_auditor = TargetSizeAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                ts_auditor.generate_audit_report, ts_items
            )
            findings = _ts_to_findings(records, url)

        _stage_complete(job_id, "target_size", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "target_size", _exc)
        return []


async def _stage_text_spacing(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_text_spacing_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl fixed-height/overflow elements → 1.4.12 text-spacing check."""
    _stage_start(job_id, "text_spacing")
    if not run_text_spacing_audit:
        _stage_complete(job_id, "text_spacing", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.text_spacing_auditor import (
            TextSpacingAuditor,
        )
        from ka11y.crawler.text_spacing_crawler import AsyncTextSpacingCrawler

        if snapshot is not None:
            ts_crawler = AsyncTextSpacingCrawler.from_snapshot(snapshot.text_spacing, url, str(output_dir))
        else:
            ts_crawler = AsyncTextSpacingCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await ts_crawler.crawl()
        items = ts_crawler.results
        await asyncio.to_thread(ts_crawler.save_json)

        findings: List[Dict] = []
        if run_text_spacing_audit:
            auditor = TextSpacingAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(auditor.generate_audit_report, items)
            findings = _crawler_text_spacing_to_findings(records, url)

        _stage_complete(job_id, "text_spacing", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "text_spacing", _exc)
        return []


async def _stage_rendered_layout_audit(
    url: str,
    output_dir: Path,
    run_resize_text_audit: bool,
    run_reflow_audit: bool,
    run_text_spacing_audit: bool,
    run_orientation_audit: bool,
    run_hover_focus_content_audit: bool,
    run_focus_not_obscured_min_audit: bool,
    run_focus_not_obscured_enh_audit: bool,
    job_id: str,
    har_path: Optional[str] = None,
) -> List[Dict]:
    """
    Rendered-layout audit stage: Playwright scenarios for
    WCAG 1.4.4 / 1.4.10 / 1.4.12 / 1.3.4 / 1.4.13 / 2.4.11 / 2.4.12.
    """
    _stage_start(job_id, "rendered_layout_audit")
    if not any(
        (
            run_resize_text_audit,
            run_reflow_audit,
            run_text_spacing_audit,
            run_orientation_audit,
            run_hover_focus_content_audit,
            run_focus_not_obscured_min_audit,
            run_focus_not_obscured_enh_audit,
        )
    ):
        _stage_complete(job_id, "rendered_layout_audit", 0)
        return []

    try:
        from ka11y.crawler.rendered_layout_crawler import (
            RenderedLayoutCrawler,
            run_all_evaluators,
        )

        crawler = RenderedLayoutCrawler(base_url=url, output_dir=str(output_dir), har_path=har_path)
        raw = await crawler.crawl()
        await asyncio.to_thread(crawler.save_raw_json)

        records = await asyncio.to_thread(
            run_all_evaluators,
            raw,
            url,
            run_resize_text_audit,
            run_reflow_audit,
            run_text_spacing_audit,
            run_orientation_audit,
            run_hover_focus_content_audit,
            run_focus_not_obscured_min_audit,
            run_focus_not_obscured_enh_audit,
        )

        findings: List[Dict] = []
        findings.extend(
            _resize_text_to_findings(
                [r for r in records if "wcag_1_4_4_status" in r], url
            )
        )
        findings.extend(
            _reflow_to_findings([r for r in records if "wcag_1_4_10_status" in r], url)
        )
        findings.extend(
            _rendered_text_spacing_to_findings(
                [r for r in records if "wcag_1_4_12_status" in r], url
            )
        )
        findings.extend(
            _orientation_to_findings(
                [r for r in records if "wcag_1_3_4_status" in r], url
            )
        )
        findings.extend(
            _hover_focus_content_to_findings(
                [r for r in records if "wcag_1_4_13_status" in r], url
            )
        )
        findings.extend(
            _focus_not_obscured_min_to_findings(
                [r for r in records if "wcag_2_4_11_status" in r], url
            )
        )
        findings.extend(
            _focus_not_obscured_enh_to_findings(
                [r for r in records if "wcag_2_4_12_status" in r], url
            )
        )

        _stage_complete(job_id, "rendered_layout_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "rendered_layout_audit", _exc)
        return []


async def _stage_media_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_media_audit: bool,
    job_id: str,
    snapshot: Optional[PageSnapshot] = None,
) -> List[Dict]:
    """Crawl media elements → 1.2.1 audio-only / video-only check."""
    _stage_start(job_id, "media_audit")
    if not run_media_audit:
        _stage_complete(job_id, "media_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.media.media_auditor import MediaAuditor
        from ka11y.crawler.media_crawler import AsyncMediaCrawler

        if snapshot is not None:
            media_crawler = AsyncMediaCrawler.from_snapshot(snapshot.media, url, str(output_dir))
        else:
            media_crawler = AsyncMediaCrawler(
                base_url=url, output_dir=str(output_dir), max_depth=max_depth
            )
            await media_crawler.crawl()
        media_items = media_crawler.results
        await asyncio.to_thread(media_crawler.save_raw_json)

        findings: List[Dict] = []
        if run_media_audit:
            media_auditor = MediaAuditor(output_dir=str(output_dir))
            records = await asyncio.to_thread(
                media_auditor.generate_audit_report,
                [item.model_dump() for item in media_items],
            )
            findings = _media_to_findings(records, url)

        _stage_complete(job_id, "media_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "media_audit", _exc)
        return []


# ── Python pipeline orchestrator ──────────────────────────────────────────────


async def _run_python_stages(
    *,
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    run_form_audit: bool,
    run_label_in_name_audit: bool,
    run_media_audit: bool,
    run_pause_stop_hide_audit: bool,
    run_target_size_audit: bool,
    run_resize_text_audit: bool,
    run_reflow_audit: bool,
    run_text_spacing_audit: bool,
    run_orientation_audit: bool,
    run_hover_focus_content_audit: bool,
    run_focus_not_obscured_min_audit: bool,
    run_focus_not_obscured_enh_audit: bool,
    job_id: str,
    lang: str = "en",
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Run all Python audit stages concurrently.

    Phase 1: Universal snapshot — ONE page load feeds all static crawlers.
    Phase 2: All audit stages run concurrently; snapshot-backed stages skip
             their own browser launch; rendered_layout_audit replays from HAR.

    Returns (all_findings, contrast_report).
    """

    # Phase 1: Universal snapshot (single page load)
    snapshot: Optional[PageSnapshot] = None
    har_path: Optional[str] = None
    try:
        snapshot = await asyncio.wait_for(
            UniversalPageLoader.load(url=url, output_dir=Path(output_dir), record_har=True),
            timeout=_SNAPSHOT_TIMEOUT_SECONDS,
        )
        har_path = snapshot.har_path
        logger.info(f"[stages] universal snapshot complete for {url}")
        # Propagate any challenge/interstitial warnings from the snapshot loader
        for w in snapshot.warnings:
            _stage_warn(job_id, f"universal_snapshot: {w}")
    except Exception as exc:
        logger.warning(f"[stages] universal snapshot failed ({exc}); falling back to individual crawlers")
        _stage_warn(job_id, f"universal_snapshot: failed — {exc}")

    # Each stage is wrapped with asyncio.wait_for so that a slow/unresponsive
    # target cannot hold a Playwright browser instance indefinitely (D2).
    def _timed(coro):
        return asyncio.wait_for(coro, timeout=_STAGE_TIMEOUT_SECONDS)

    # Phase 2: All stages concurrently
    results = await asyncio.gather(
        _timed(
            _stage_image_audit(
                url, output_dir, max_depth, run_ocr, run_image_audit, job_id, lang
            )
        ),
        _timed(_stage_form_audit(url, output_dir, max_depth, run_form_audit, job_id, snapshot=snapshot)),
        _timed(
            _stage_label_in_name(
                url, output_dir, max_depth, run_label_in_name_audit, job_id, snapshot=snapshot
            )
        ),
        _timed(
            _stage_pause_stop_hide(
                url, output_dir, max_depth, run_pause_stop_hide_audit, job_id, snapshot=snapshot
            )
        ),
        _timed(
            _stage_target_size(
                url, output_dir, max_depth, run_target_size_audit, job_id, snapshot=snapshot
            )
        ),
        _timed(
            _stage_text_spacing(
                url, output_dir, max_depth, run_text_spacing_audit, job_id, snapshot=snapshot
            )
        ),
        _timed(
            _stage_rendered_layout_audit(
                url,
                output_dir,
                run_resize_text_audit,
                run_reflow_audit,
                run_text_spacing_audit,
                run_orientation_audit,
                run_hover_focus_content_audit,
                run_focus_not_obscured_min_audit,
                run_focus_not_obscured_enh_audit,
                job_id,
                har_path=har_path,
            )
        ),
        _timed(
            _stage_media_audit(
                url, output_dir, max_depth, run_media_audit, job_id, snapshot=snapshot
            )
        ),
        return_exceptions=True,
    )

    all_findings: List[Dict] = []
    contrast_report: Optional[Dict[str, Any]] = None

    # Image audit returns (findings, contrast_report)
    img_result = results[0]
    if not isinstance(img_result, Exception):
        img_findings, contrast_report = img_result
        all_findings.extend(img_findings)

    # All other stages return a plain findings list
    for r in results[1:]:
        if not isinstance(r, Exception):
            all_findings.extend(r)

    return all_findings, contrast_report
