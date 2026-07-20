"""
ka11y/api/v1/combined/stages.py
=================================
All per-stage coroutines and the Python pipeline orchestrator.

Each stage coroutine:
  - owns its crawler + auditor lifecycle
  - calls _stage_start / _stage_complete / _stage_error_and_warn
  - offloads CPU-bound auditor work via asyncio.to_thread()
  - returns a flat List[Dict] of findings
  - image_audit also returns contrast_report and image_audit_report

_run_python_stages() gathers all stages concurrently.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field


class PythonStagesResult(BaseModel):
    """Typed return value from :func:`_run_python_stages`.

    Replaces the prior ``(all_findings, contrast_report, image_audit_report)``
    positional tuple, which silently broke whenever a stage was added or
    reordered (the caller's positional unpack would point at the wrong
    object). Named fields make the contract explicit at the type level."""

    # Findings entries are deeply nested heterogeneous dicts; we do not want
    # Pydantic to deep-copy or revalidate them on every field assignment.
    model_config = ConfigDict(arbitrary_types_allowed=True)

    findings: List[Dict[str, Any]] = Field(default_factory=list)
    contrast_report: Optional[Dict[str, Any]] = None
    image_audit_report: Optional[Dict[str, Any]] = None

from ka11y.config.logger import setup_logger
from ka11y.utils.crawler_settings import (
    get_max_ocr_images_ceiling,
    get_max_ocr_images_per_page,
    get_max_ocr_images_per_run,
    get_max_warning_samples,
    select_ocr_candidate_paths,
)
from ka11y.accessibility.pipeline.pipeline_stage import (
    _run_pipeline_stage as _real_run_pipeline_stage,
)


from ka11y.utils.step_logger import ExecutionStepLogger
from ka11y.utils.crawler_timing import time_crawler

from .findings import (
    IMAGE_AUDIT_RECORD_CONVERTERS,
    OCR_RESULT_CONVERTERS,
    _build_contrast_report,
    _build_image_audit_report,
    _contrast_capture_failed_to_findings,
    _media_to_findings,
)
from .stage_events import (
    _record_crawler_time,
    _stage_complete,
    _stage_error_and_warn,
    _stage_start,
    emit_stage_progress,
)
from .store import _jobs
from ka11y.crawler.universal_page import UniversalPageLoader
from ka11y.utils import stage_timing


async def _run_pipeline_stage(
    url: str,
    job_id: str,
    run_image_audit: bool,
    run_contrast_audit: bool = True,
    lang: str = "en",
    snapshot: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Wrapper to record stage lifecycle and crawler time for the pipeline."""
    _stage_start(job_id, "pipeline")
    start_crawl: Optional[float] = None
    if snapshot:
        # Snapshot path: pipeline reuses the universal crawler's pass, so we
        # report that same duration here rather than re-timing CPU work.
        crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
        if crawl_dur:
            _record_crawler_time(job_id, "pipeline", crawl_dur)
    else:
        # Single-URL fallback: ``_real_run_pipeline_stage`` opens its own page
        # via ``_extract_contexts_for_url``. Time the call so the timing log
        # shows the real browser work instead of an empty cell.
        start_crawl = time.perf_counter()

    try:
        findings = await _real_run_pipeline_stage(
            url=url,
            job_id=job_id,
            run_image_audit=run_image_audit,
            run_contrast_audit=run_contrast_audit,
            lang=lang,
            snapshot=snapshot,
        )
        if start_crawl is not None:
            _record_crawler_time(job_id, "pipeline", time.perf_counter() - start_crawl)
        _stage_complete(job_id, "pipeline", len(findings))
        return findings
    except Exception as e:
        if start_crawl is not None:
            _record_crawler_time(job_id, "pipeline", time.perf_counter() - start_crawl)
        _stage_error_and_warn(job_id, "pipeline", e)
        return []

# Maximum wall-clock seconds for the full image-audit stage (crawl + OCR).
_STAGE_TIMEOUT_SECONDS = 1200
# Maximum seconds for the crawler pass only.  OCR always runs on whatever
# images were saved before this deadline, so a slow/stuck target never
# prevents contrast analysis from completing.
# Button/icon screenshots are now capped at 5 s each (crawler.py), so 300 s
# handles up to ~60 stuck elements before we cut over to OCR on partial images.
# This is the FLOOR (single-page / small-crawl) budget; for multi-page crawls
# the effective budget scales with the page count (see below) so a page visited
# late in the BFS still gets reached and screenshotted instead of being silently
# dropped — the bug where the same page yielded fewer image/contrast findings as
# a crawled child than as a directly-audited root.
_CRAWL_TIMEOUT_SECONDS = 300
# Per-discovered-page crawl budget. The effective crawl deadline is
# ``max(_CRAWL_TIMEOUT_SECONDS, per_page * pages)`` capped by
# ``_CRAWL_TIMEOUT_CEILING`` so deep crawls reach every page while still leaving
# the rest of the stage budget (``_STAGE_TIMEOUT_SECONDS``) for OCR/contrast.
_CRAWL_PER_PAGE_SECONDS = float(os.environ.get("KA11Y_IMAGE_CRAWL_PER_PAGE_SECONDS", "20"))
# Hard ceiling on the (scaled) crawl deadline. Kept well under the 1200 s stage
# budget so OCR/contrast always has time to run on the images that were captured.
_CRAWL_TIMEOUT_CEILING = float(os.environ.get("KA11Y_IMAGE_CRAWL_TIMEOUT_CEILING", "600"))

# Process-wide queue for browser-heavy crawler stages. ``image_audit`` and
# ``rendered_layout_audit`` each open their own Playwright contexts + image
# buffers; with _MAX_CONCURRENT_JOBS=4 an unguarded depth>0 audit can spawn
# 8 simultaneous BFS crawls and OOM-kill the container. The semaphore is
# global (not per-job) so the surplus parks until a slot frees, regardless
# of which job they belong to. Queue wait does NOT count against the stage
# timeout — ``_heavy`` arms ``asyncio.wait_for`` only after acquiring the
# slot, so a parked stage isn't killed for waiting its turn.
_HEAVY_STAGE_CONCURRENCY = int(os.environ.get("KA11Y_HEAVY_STAGE_CONCURRENCY", "2"))
_heavy_stage_sem: asyncio.Semaphore | None = None
_heavy_stage_sem_loop: Any = None


def _get_heavy_stage_sem() -> asyncio.Semaphore:
    """Lazy per-event-loop semaphore so module import never touches the loop."""
    global _heavy_stage_sem, _heavy_stage_sem_loop
    current = asyncio.get_event_loop()
    if _heavy_stage_sem is None or _heavy_stage_sem_loop is not current:
        _heavy_stage_sem = asyncio.Semaphore(_HEAVY_STAGE_CONCURRENCY)
        _heavy_stage_sem_loop = current
    return _heavy_stage_sem


async def _heavy(coro, *, timeout: float = _STAGE_TIMEOUT_SECONDS):
    """Run ``coro`` while holding the global heavy-stage slot.

    Replaces ``_timed`` for browser-heavy stages: the per-stage deadline is
    armed *after* the semaphore is acquired so a stage queued behind another
    heavy stage isn't penalised for the wait.
    """
    async with _get_heavy_stage_sem():
        return await asyncio.wait_for(coro, timeout=timeout)


logger = setup_logger(name="KAC", tag="combined")


def _warning_samples(
    warnings: List[Dict[str, Any]],
    *,
    sample_limit: int,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for warning in warnings:
        code = str(warning.get("code") or "unknown_warning")
        group = grouped.setdefault(code, {"code": code, "count": 0, "samples": []})
        group["count"] += 1
        if len(group["samples"]) >= sample_limit:
            continue

        sample = {
            key: value
            for key, value in warning.items()
            if key != "code" and value not in (None, "", [], {})
        }
        message = sample.get("message")
        if isinstance(message, str) and len(message) > 320:
            sample["message"] = message[:317] + "..."
        group["samples"].append(sample)

    return [grouped[key] for key in sorted(grouped)]


def _record_stage_metrics(
    step_logger: ExecutionStepLogger | None,
    *,
    stage: str,
    crawler_items: int,
    auditor_records: int,
    findings: int,
    extra: Dict[str, Any] | None = None,
) -> None:
    if not step_logger:
        return
    context = {
        "crawler_items": crawler_items,
        "auditor_records": auditor_records,
        "finding_count": findings,
    }
    if extra:
        context.update(extra)
    step_logger.record(
        step=f"{stage}_summary",
        status="completed",
        message=f"{stage} crawler and auditor results recorded",
        context=context,
    )


# ── WCAG level filter ─────────────────────────────────────────────────────────


def _allowed_levels(wcag_level: str) -> set:
    levels = {"A"}
    if wcag_level in ("AA", "AAA"):
        levels.add("AA")
    if wcag_level == "AAA":
        levels.add("AAA")
    return levels


# ── Individual stage coroutines ───────────────────────────────────────────────


def _ocr_lang_for_page(page_lang: Optional[str], run_lang: str) -> str:
    """Pick the OCR language for one page's screenshots.

    The OCR backends only meaningfully distinguish Japanese (``ja`` → PaddleOCR
    ``japan`` / EasyOCR ``["en","ja"]``) from the Latin family. We therefore only
    ever split a run into a ``ja`` group and a non-``ja`` group, which keeps the
    grouping safe (never passes an unsupported code to a backend) while fixing
    the real cross-language bug:

    * Japanese page (root or child) → ``ja``.
    * Non-Japanese page under a Japanese run → the page is Latin, so OCR it as
      ``en`` instead of mis-reading it with the Japanese model.
    * Non-Japanese page under a non-Japanese run → keep the run language
      (unchanged from previous behaviour).
    * Unknown page language → fall back to the run language (unchanged).
    """

    def _base(value: Optional[str]) -> str:
        return (value or "").split("-")[0].split("_")[0].strip().lower()

    page_base = _base(page_lang)
    run_base = _base(run_lang)
    if page_base in ("ja", "jp"):
        return "ja"
    if page_base:
        # Known non-Japanese (Latin) page: if the run language is Japanese the
        # page would otherwise be mis-OCR'd, so force English; else keep the run
        # language so a configured Latin language (fr/de/…) is preserved.
        return "en" if run_base in ("ja", "jp") else run_lang
    return run_lang


async def _stage_image_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_ocr: bool,
    run_image_audit: bool,
    job_id: str,
    lang: str = "en",
    step_logger: ExecutionStepLogger | None = None,
    discovered_urls: List[str] | None = None,
    max_pages: int = 50,
    internal_links: bool = True,
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
        # Optimized crawler is a drop-in for AsyncImageCrawler (same interface);
        # the navigation-error type still comes from the original module.
        from ka11y.crawler.optimized import OptimizedImageCrawler as AsyncImageCrawler
        from ka11y.crawler.crawler import ImageCrawlerNavigationError
        from ka11y.text_detector.text_detector import (
            OCRPreprocessing,
            TextClassification,
        )

        image_crawler = AsyncImageCrawler(
            base_url=url,
            max_depth=max_depth,
            max_pages=max_pages,
            internal_links=internal_links,
            job_id=job_id,
        )

        async def _crawl_and_save() -> None:
            start_crawl = time.perf_counter()
            async with time_crawler(
                output_dir, "image", url,
                pages_getter=lambda: len(image_crawler.images_data),
            ):
                await image_crawler.crawl_page(discovered_urls=discovered_urls)
            _record_crawler_time(job_id, "image_audit", time.perf_counter() - start_crawl)
            await asyncio.to_thread(image_crawler.save_results)

        # Scale the crawl deadline with the number of pages to visit so a deep
        # crawl reaches every discovered page (each gets ~_CRAWL_PER_PAGE_SECONDS)
        # instead of all pages sharing one fixed 300 s budget — which let pages
        # visited late get no screenshots and silently contribute zero findings.
        # A single page / small crawl keeps the original 300 s floor; the ceiling
        # keeps the crawl from eating the OCR portion of the stage budget.
        _crawl_page_count = len(discovered_urls) if discovered_urls else 1
        effective_crawl_timeout = max(
            _CRAWL_TIMEOUT_SECONDS,
            min(_CRAWL_PER_PAGE_SECONDS * _crawl_page_count, _CRAWL_TIMEOUT_CEILING),
        )

        try:
            await asyncio.wait_for(_crawl_and_save(), timeout=effective_crawl_timeout)
        except asyncio.TimeoutError:
            # The crawl was clipped by the wall-clock cap, so pages visited late
            # in the BFS (often the very child page the user cares about) may have
            # NO screenshots and therefore silently contribute zero image/contrast
            # findings. Surface this on the report instead of hiding it in the log
            # so a low child finding-count is explainable, not mysterious.
            covered_pages = sorted(
                {getattr(i, "url", "") for i in image_crawler.images_data if getattr(i, "url", "")}
            )
            requested = len(discovered_urls) if discovered_urls else None
            clipped = (
                max(0, requested - len(covered_pages)) if requested is not None else None
            )
            logger.warning(
                f"[combined] image_audit: crawler exceeded {effective_crawl_timeout:.0f}s "
                f"— proceeding with partial image set ({len(covered_pages)} page(s) "
                f"covered{f', {clipped} clipped' if clipped else ''}) "
                f"from {image_crawler.output_dir}"
            )
            try:
                _jobs[job_id].setdefault("warnings", []).append(
                    f"image_audit: image crawl timed out after "
                    f"{effective_crawl_timeout:.0f}s; {len(covered_pages)} page(s) covered"
                    + (f", {clipped} page(s) not screenshotted" if clipped else "")
                    + " — some pages may show fewer image/contrast findings"
                )
            except Exception:  # noqa: BLE001 — a warning must never fail the audit
                pass

        ocr_results: list = []
        contrast_report: Optional[Dict[str, Any]] = None
        image_audit_report: Optional[Dict[str, Any]] = None
        findings: List[Dict] = []
        ocr_paths: List[str] = []

        # Emit a crawl-phase completion marker so the bar settles before OCR begins.
        emit_stage_progress(
            job_id,
            "image_audit",
            current=len(image_crawler.images_data),
            total=len(image_crawler.images_data),
            phase="crawl",
        )

        if run_ocr:
            # OCR budget scales with the number of crawled pages so a child page
            # gets the same per-page image coverage it would as the root. The
            # budget is per_page * pages (capped by a global memory ceiling) and
            # distributed fairly round-robin across pages, so a page's images
            # never compete with every sibling for one shared cap — the cross-page
            # starvation that made the same page yield fewer image findings
            # (1.1.1, 1.4.3, 1.4.5, 1.4.6) as a child than audited alone. With the
            # default per_page (60) and max_pages (50) every page gets its full
            # ~60 either way; only crawls past the ceiling degrade, and they do so
            # evenly across pages rather than starving the ones visited last.
            distinct_pages = len(
                {getattr(i, "url", "") for i in image_crawler.images_data if getattr(i, "url", "")}
            ) or 1
            if distinct_pages > 1:
                max_ocr_images = min(
                    get_max_ocr_images_per_page() * distinct_pages,
                    get_max_ocr_images_ceiling(),
                )
            else:
                # Single page: preserve the exact legacy budget/behaviour.
                max_ocr_images = get_max_ocr_images_per_run()
            ocr_paths, skipped_ocr_paths = select_ocr_candidate_paths(
                image_crawler.images_data,
                limit=max_ocr_images,
                fair_per_page=distinct_pages > 1,
            )
            if skipped_ocr_paths:
                message = (
                    f"image_audit: OCR limited to {len(ocr_paths)} image(s); "
                    f"skipped {len(skipped_ocr_paths)} lower-priority screenshot(s)"
                )
                logger.info(message)
                if step_logger:
                    step_logger.record(
                        step="image_audit",
                        status="info",
                        message="OCR budget applied",
                        context={
                            "selected_images": len(ocr_paths),
                            "skipped_images": len(skipped_ocr_paths),
                            "budget": max_ocr_images,
                        },
                    )

            # Per-page OCR language. The default OCR backend (PaddleOCR) is
            # mono-lingual: forcing the root URL's language on every page made an
            # English child of a Japanese root (e.g. /jp → /global/en/...) get
            # OCR'd with the Japanese model, detecting almost no text and so
            # losing nearly all its 1.1.1/1.4.3/1.4.6 image+contrast findings.
            # Group the selected screenshots by the language of the page they
            # came from and OCR each group with the right model. When every page
            # resolves to the same language this is a single group — identical to
            # the previous single-detector behaviour.
            path_to_page: Dict[str, str] = {}
            for _img in image_crawler.images_data:
                _sp = getattr(_img, "screenshot_path", None)
                _pg = getattr(_img, "url", None)
                if _sp and _pg:
                    try:
                        path_to_page[str(Path(_sp).resolve())] = _pg
                    except Exception:
                        path_to_page[str(_sp)] = _pg
            page_lang_map = getattr(image_crawler, "page_langs", {}) or {}

            ocr_groups: Dict[str, List[str]] = {}
            for _p in ocr_paths:
                try:
                    _rp = str(Path(_p).resolve())
                except Exception:
                    _rp = str(_p)
                _page_url = path_to_page.get(_rp)
                _glang = _ocr_lang_for_page(page_lang_map.get(_page_url), lang)
                ocr_groups.setdefault(_glang, []).append(_p)

            ocr_results = []
            total_ocr = len(ocr_paths)
            done_ocr = 0
            emit_stage_progress(
                job_id, "image_audit", current=0, total=total_ocr, phase="ocr"
            )
            for _glang, _gpaths in ocr_groups.items():
                detector = OCRPreprocessing(
                    source_directory=image_crawler.output_dir,
                    lang=_glang,
                    include_paths=_gpaths,
                )
                async with stage_timing.time_stage_async(
                    job_id,
                    "image_audit",
                    sub_stage="ocr_scan",
                    extra={"image_count": len(_gpaths), "ocr_lang": _glang},
                ):
                    await asyncio.to_thread(detector.scan_directory)
                ocr_results.extend(detector.results)
                done_ocr += len(_gpaths)
                emit_stage_progress(
                    job_id,
                    "image_audit",
                    current=done_ocr,
                    total=total_ocr,
                    phase="ocr",
                )

            saver = TextClassification(source_directory=image_crawler.output_dir)
            saver.results = ocr_results
            async with stage_timing.time_stage_async(
                job_id,
                "image_audit",
                sub_stage="ocr_save_reports",
            ):
                await asyncio.to_thread(saver.save_reports)
            # filename → source page URL, so the contrast report can be grouped
            # per page in the image visualiser on multi-page crawls.
            page_by_filename: Dict[str, str] = {}
            for _img in image_crawler.images_data:
                _fn = getattr(_img, "filename", None)
                _pg = getattr(_img, "url", None)
                if _fn and _pg:
                    page_by_filename[_fn] = _pg
            contrast_report = _build_contrast_report(ocr_results, page_by_filename)
            # D-1 fix: thread page_by_filename through so contrast findings (1.4.3,
            # 1.4.6) are stamped with the page the image actually came from, not
            # the root URL. Without this, every contrast finding on a multi-page
            # crawl collapses to the root URL and child pages silently lose them.
            for rule_sc, converter in OCR_RESULT_CONVERTERS:
                with stage_timing.time_stage(
                    job_id,
                    "image_audit",
                    sub_stage="ocr_converter",
                    rule=rule_sc,
                    extra={"input_count": len(ocr_results)},
                ):
                    findings.extend(
                        converter(ocr_results, url, page_by_filename=page_by_filename)
                    )
            # 1.4.3/1.4.6 needs_review for images that failed screenshot capture
            findings.extend(
                _contrast_capture_failed_to_findings(image_crawler.images_data, url)
            )

        if run_image_audit:
            auditor = AltTextAccessibilityAuditor()
            emit_stage_progress(
                job_id,
                "image_audit",
                current=0,
                total=len(image_crawler.images_data),
                phase="alt_audit",
            )
            records = await asyncio.to_thread(
                auditor.generate_audit_report,
                images_data=image_crawler.images_data,
                ocr_results=ocr_results,
                output_dir=image_crawler.output_dir,
            )
            emit_stage_progress(
                job_id,
                "image_audit",
                current=len(image_crawler.images_data),
                total=len(image_crawler.images_data),
                phase="alt_audit",
            )
            image_audit_report = _build_image_audit_report(records)
            for status_key, converter in IMAGE_AUDIT_RECORD_CONVERTERS:
                # Strip the wcag_X_Y_Z_status prefix → "X.Y.Z" for the rule field.
                _rule = (
                    status_key.replace("wcag_", "")
                    .replace("_status", "")
                    .replace("_", ".")
                )
                with stage_timing.time_stage(
                    job_id,
                    "image_audit",
                    sub_stage="image_audit_converter",
                    rule=_rule,
                    extra={"input_count": len(records)},
                ):
                    findings.extend(converter(records, url))
        else:
            records = []

        _record_stage_metrics(
            step_logger,
            stage="image_audit",
            crawler_items=len(image_crawler.images_data),
            auditor_records=len(records),
            findings=len(findings),
            extra={
                "ocr_results": len(ocr_results),
                "ocr_images_scanned": len(ocr_paths) if run_ocr else 0,
                "contrast_regions": (contrast_report or {})
                .get("summary", {})
                .get("total_regions_analysed", 0),
            },
        )

        _stage_complete(job_id, "image_audit", len(findings))
        return findings, contrast_report, image_audit_report
    except ImageCrawlerNavigationError as _exc:
        if step_logger:
            step_logger.record(
                step="image_audit",
                status="warning",
                message="Image crawl could not resolve or load the target page",
                context={
                    "code": getattr(_exc, "code", None),
                    "url": getattr(_exc, "url", url),
                    "host": getattr(_exc, "host", None),
                    "attempts": getattr(_exc, "attempts", None),
                },
            )
        _stage_error_and_warn(job_id, "image_audit", _exc)
        return [], None, None
    except Exception as _exc:
        _stage_error_and_warn(job_id, "image_audit", _exc)
        return [], None, None


async def _load_universal_snapshot(
    *,
    url: str,
    output_dir: Path,
    max_depth: int,
    job_id: str,
    step_logger: ExecutionStepLogger | None,
    internal_links: bool = True,
    max_pages: int = 50,
):
    from ka11y.crawler.snapshot_normalizer import SnapshotNormalizer
    from ka11y.crawler.policy import CrawlPolicy

    # Build the crawl policy explicitly so the request's internal_links /
    # max_pages controls reach the universal BFS: same_origin == internal-only
    # (exact hostname), max_pages is the hard RAM/time budget.
    #
    # max_links_per_page must scale with max_pages: it was defaulting to 50, so a
    # crawl with max_pages>50 could never actually reach that many pages — each
    # page only enqueued its first 50 links, starving deep BFS of child URLs.
    policy = CrawlPolicy(
        max_depth=max_depth,
        max_pages=max_pages,
        max_links_per_page=max(50, max_pages),
        same_origin=internal_links,
    )

    # UniversalPageLoader is imported at module level so tests can patch
    # `stages.UniversalPageLoader`; the call site below resolves it from the
    # module namespace.
    start_crawl = time.perf_counter()
    async with time_crawler(
        output_dir, "universal_snapshot", url,
        pages_getter=lambda: len(getattr(raw_snapshot, "page_summaries", []) or []),
    ):
        raw_snapshot = await UniversalPageLoader.load(
            url=url,
            output_dir=output_dir,
            max_depth=max_depth,
            record_har=False,
            step_logger=step_logger,
            policy=policy,
        )
    crawl_dur = time.perf_counter() - start_crawl
    _jobs[job_id]["universal_crawler_duration_s"] = round(crawl_dur, 2)
    await asyncio.to_thread(UniversalPageLoader.save_snapshot, raw_snapshot, output_dir)
    normalized = await asyncio.to_thread(
        SnapshotNormalizer.normalize,
        raw_snapshot,
        output_dir=output_dir,
        step_logger=step_logger,
    )
    if normalized.warnings:
        warning_path = output_dir / "universal_snapshot_warnings.json"
        await asyncio.to_thread(
            warning_path.write_text,
            json.dumps(normalized.warnings, indent=2, ensure_ascii=False),
            "utf-8",
        )
        warning_details = _warning_samples(
            normalized.warnings,
            sample_limit=get_max_warning_samples(),
        )
        counts: Dict[str, int] = {}
        for warning in normalized.warnings:
            code = warning.get("code", "unknown_warning")
            counts[code] = counts.get(code, 0) + 1
        for code, count in sorted(counts.items()):
            _jobs[job_id].setdefault("warnings", []).append(
                f"universal_static:{code}: {count} occurrence(s)"
            )
        if warning_details:
            _jobs[job_id]["warning_details"] = warning_details
        _jobs[job_id]["universal_warning_path"] = str(warning_path)
        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="warning",
                message="Universal crawl completed with extraction limitations",
                context={
                    "warning_counts": counts,
                    "warning_samples": warning_details,
                    "warning_path": str(warning_path),
                },
            )
    if normalized.pages_crawled == 0:
        raise Exception("Universal crawl failed: 0 pages extracted")
    return normalized


async def _stage_media_audit_universal(
    url: str,
    output_dir: Path,
    run_media_audit: bool,
    run_captions_audit: bool,
    job_id: str,
    snapshot_task,
    lang: str = "en",
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "media_audit")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "media_audit", crawl_dur)

    if not run_media_audit and not run_captions_audit:
        _stage_complete(job_id, "media_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.media.media_auditor import MediaAuditor

        snapshot = await snapshot_task
        auditor = MediaAuditor(output_dir=str(output_dir), lang=lang)
        records = await asyncio.to_thread(
            auditor.generate_audit_report,
            [item.model_dump() for item in snapshot.media],
            run_1_2_1=run_media_audit,
            run_1_2_2=run_captions_audit,
        )
        findings = _media_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="media_audit",
            crawler_items=len(snapshot.media),
            auditor_records=len(records),
            findings=len(findings),
        )
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
    run_media_audit: bool,
    run_captions_audit: bool,
    job_id: str,
    lang: str = "en",
    step_logger: ExecutionStepLogger | None = None,
    internal_links: bool = True,
    max_pages: int = 50,
    success_criteria_id: Optional[str] = None,
) -> PythonStagesResult:
    """
    Run all Python audit stages concurrently.

    Returns a :class:`PythonStagesResult` with named ``findings``,
    ``contrast_report``, and ``image_audit_report`` fields.
    """

    def _timed(coro):
        return asyncio.wait_for(coro, timeout=_STAGE_TIMEOUT_SECONDS)

    static_rules_enabled = any((run_media_audit, run_captions_audit))

    # 1. Run universal snapshot first.
    #
    # The snapshot now ALSO carries per-page pipeline contexts, so building it
    # at ``max_depth > 0`` is the only way the unified pipeline (1.1.1, 1.4.3,
    # 1.4.5, 1.4.6, 1.4.11) covers more than the entry URL. Without that, deep
    # pages were silently losing every pipeline finding even though the BFS
    # visited them. The image-only ``max_depth=0`` path remains snapshot-free
    # (the pipeline falls back to its single-URL navigation, which preserves
    # the previous behaviour for that case).
    snapshot = None
    discovered_urls = [url]
    if static_rules_enabled or max_depth > 0:
        snapshot = await _load_universal_snapshot(
            url=url,
            output_dir=output_dir,
            max_depth=max_depth,
            job_id=job_id,
            step_logger=step_logger,
            internal_links=internal_links,
            max_pages=max_pages,
        )
        # page_url is now the resolved URL (see universal_page._crawl_one_url),
        # so two queued links that 301 to the same page collapse to one
        # page_summary key.
        seen_pages: set[str] = set()
        discovered_urls = []
        for s in snapshot.page_summaries:
            pu = s["page_url"]
            if pu not in seen_pages:
                seen_pages.add(pu)
                discovered_urls.append(pu)
        if not discovered_urls:
            discovered_urls = [url]

    snapshot_task = asyncio.Future()
    if snapshot:
        snapshot_task.set_result(snapshot)
    else:
        snapshot_task.set_result(None)

    results = await asyncio.gather(
        _heavy(
            _stage_image_audit(
                url,
                output_dir,
                max_depth,
                run_ocr,
                run_image_audit,
                job_id,
                lang,
                step_logger,
                discovered_urls=discovered_urls,
                max_pages=max_pages,
                internal_links=internal_links,
            )
        ),
        # Snapshot is passed so the pipeline evaluates every BFS-discovered page,
        # not just the entry URL; with no snapshot it falls back to single-URL mode.
        _timed(
            _run_pipeline_stage(
                url,
                job_id,
                run_image_audit=run_image_audit,
                lang=lang,
                snapshot=snapshot,
            )
        ),
        _timed(
            _stage_media_audit_universal(
                url,
                output_dir,
                run_media_audit,
                run_captions_audit,
                job_id,
                snapshot_task,
                lang,
                step_logger,
            )
        ),
        return_exceptions=True,
    )

    all_findings: List[Dict] = []
    contrast_report: Optional[Dict[str, Any]] = None
    image_audit_report: Optional[Dict[str, Any]] = None

    # Image audit returns (findings, contrast_report, image_audit_report)
    img_result = results[0]
    if not isinstance(img_result, Exception):
        img_findings, contrast_report, image_audit_report = img_result
        all_findings.extend(img_findings)

    # All other stages return a plain findings list
    for r in results[1:]:
        if not isinstance(r, Exception):
            all_findings.extend(r)

    return PythonStagesResult(
        findings=all_findings,
        contrast_report=contrast_report,
        image_audit_report=image_audit_report,
    )
