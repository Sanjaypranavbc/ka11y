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
import functools
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
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
    _sensory_to_findings,
    _consistent_navigation_to_findings,
    _consistent_id_to_findings,
    _unusual_words_to_findings,
    _section_headings_to_findings,
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
    run_label_in_name_audit: bool,
    run_target_size_audit: bool = True,
    run_focus_audit: bool = True,
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
            run_label_in_name_audit=run_label_in_name_audit,
            run_target_size_audit=run_target_size_audit,
            run_focus_audit=run_focus_audit,
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

# How long Node (``_call_node_flat``) waits for the Python snapshot to publish
# its discovered-URL list before giving up. The Python snapshot task ALWAYS
# sets the coordination event in its ``finally`` (success or failure), so this
# wait normally resolves the instant the snapshot finishes — its only job is to
# outlast a legitimately slow snapshot. The old 90 s default was ~6× too short
# for heavy sites (a kao.com/jp snapshot took 561 s), so the wait expired, Node
# fell back to its independent BFS, hit the 255 s ``flatCrawlBudgetMs`` cliff,
# and audited only 7 of 50 pages — silently dropping axe coverage on 43 pages.
# Bounded by the snapshot stage's own budget; the outer ``_JOB_TIMEOUT_SECONDS``
# (1800 s) remains the real backstop against a hung Python task.
_SNAPSHOT_URLS_WAIT_SECONDS = float(
    os.environ.get("KA11Y_SNAPSHOT_URLS_WAIT_SECONDS", str(_STAGE_TIMEOUT_SECONDS))
)

# HTTP read-timeout sizing for the call to Node's ``/analyse-url-flat``.
#
# In snapshot-fed mode Node audits EVERY discovered URL with no internal
# time budget (unlike its legacy BFS, which self-caps at flatCrawlBudgetMs).
# A fixed 300 s client timeout therefore silently discarded *all* axe findings
# on any child crawl that took longer than 300 s end-to-end: the POST timed out
# mid-crawl, ``_call_node_flat`` raised, and ``node_findings`` came back empty —
# so deep pages lost their entire axe coverage even though the snapshot fix was
# feeding Node the right URLs. We now scale the timeout by the number of pages
# Node will actually audit (a fixed base for connection + the entry page, plus a
# per-page budget that matches Node's worst-case page cost: navigate + axe +
# custom checks), bounded by the outer job budget so a runaway crawl still
# terminates. The legacy single-page / BFS path keeps the 300 s floor.
_NODE_HTTP_BASE_TIMEOUT_SECONDS = float(
    os.environ.get("KA11Y_NODE_HTTP_BASE_TIMEOUT_SECONDS", "60")
)
_NODE_HTTP_PER_PAGE_TIMEOUT_SECONDS = float(
    os.environ.get("KA11Y_NODE_HTTP_PER_PAGE_TIMEOUT_SECONDS", "75")
)
# Hard ceiling — keep at/under the runner's KA11Y_JOB_TIMEOUT_SECONDS (1800 s)
# so the HTTP call fails with a clear axe-specific error before the outer job
# watchdog cancels the whole audit.
_NODE_HTTP_TIMEOUT_CAP_SECONDS = float(
    os.environ.get("KA11Y_JOB_TIMEOUT_SECONDS", "1800")
)


def _node_http_timeout(page_count: int) -> float:
    """Return the httpx timeout (seconds) for a Node flat call of ``page_count`` pages.

    Floors at 300 s (legacy single-page / BFS behaviour), grows linearly with the
    page count in snapshot-fed mode, and is capped at the job budget.
    """
    scaled = _NODE_HTTP_BASE_TIMEOUT_SECONDS + max(1, page_count) * _NODE_HTTP_PER_PAGE_TIMEOUT_SECONDS
    return min(_NODE_HTTP_TIMEOUT_CAP_SECONDS, max(300.0, scaled))

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


# ── Node / axe-core caller ────────────────────────────────────────────────────


async def _call_node_flat(
    url: str,
    node_base_url: str,
    wcag_level: str = "AAA",
    lang: str = "en",
    *,
    max_depth: int = 0,
    internal_links: bool = True,
    max_pages: int = 50,
    success_criteria_id: Optional[str] = None,
    job_id: Optional[str] = None,
    discovered_urls: Optional[List[str]] = None,
    snapshot_urls_event: Optional[asyncio.Event] = None,
    snapshot_urls_container: Optional[Dict[str, Any]] = None,
    snapshot_wait_timeout: float = _SNAPSHOT_URLS_WAIT_SECONDS,
) -> List[Dict]:
    """POST to Node's /api/v1/analyse-url-flat. Returns flat element-wise findings.

    ``max_depth`` / ``internal_links`` make Node run its own bounded BFS so it
    covers the same deeper pages Python does (previously Node only ever audited
    the root URL, so max_depth had no effect on the axe-core side).
    ``success_criteria_id`` lets Node run only the axe rules + custom checks for a
    single WCAG SC, so a per-rule audit doesn't pay for the full rule set.

    ``job_id`` (when supplied) is forwarded to Node which collects per-page
    timing rows and returns them in the response. Each row is then mirrored
    into the same ``logs/timings/<job_id>.jsonl`` file the Python stages write
    to, so the per-(page, stage) summary covers both engines.
    """
    endpoint = f"{node_base_url.rstrip('/')}/api/v1/analyse-url-flat"

    # R-1: prefer snapshot-fed mode. If the caller passed a coordination event,
    # the Python snapshot task fills ``snapshot_urls_container["urls"]`` and
    # signals the event when the snapshot finishes — and it ALWAYS signals, even
    # on snapshot failure, via a ``finally`` in ``_run_python_stages``. So this
    # wait normally resolves the moment the snapshot completes; the timeout only
    # guards against a Python task that never signals at all (hard crash). On
    # ``max_depth > 0`` the snapshot is the source of truth: falling back to
    # Node's independent BFS re-introduces the 255 s ``flatCrawlBudgetMs`` cliff
    # that silently drops axe coverage on every page past the budget, so we log
    # the degradation at ERROR rather than letting it pass quietly.
    if snapshot_urls_event is not None and snapshot_urls_container is not None and not discovered_urls:
        try:
            await asyncio.wait_for(
                snapshot_urls_event.wait(), timeout=snapshot_wait_timeout
            )
            urls = snapshot_urls_container.get("urls") or []
            # Drop the entry URL when it's the only thing the snapshot found
            # — that's the "no snapshot needed" sentinel and Node already
            # audits it through its own single-page path.
            if urls and not (len(urls) == 1 and urls[0] == url):
                discovered_urls = list(urls)
        except asyncio.TimeoutError:
            logger.error(
                f"[combined] axe_core: snapshot URL wait timed out after "
                f"{snapshot_wait_timeout}s at max_depth={max_depth} — Node will "
                f"fall back to independent BFS, which is capped by "
                f"flatCrawlBudgetMs and will likely UNDER-AUDIT deep pages. "
                f"Raise KA11Y_SNAPSHOT_URLS_WAIT_SECONDS if the snapshot is "
                f"legitimately slow on this site."
            )
    if max_depth > 0 and not discovered_urls:
        # Snapshot produced no usable URL list for a multi-page crawl. Node's
        # BFS would clip on heavy sites, so make the under-coverage explicit in
        # the logs (the run still proceeds — partial axe coverage beats none).
        logger.error(
            f"[combined] axe_core: no snapshot URLs available at "
            f"max_depth={max_depth} for {url}; Node falls back to its "
            f"budget-capped BFS and may under-audit deep pages."
        )

    payload_json: Dict[str, Any] = {
        "url": url,
        "level": wcag_level,
        "lang": lang,
        "maxDepth": max_depth,
        "internalLinks": internal_links,
        "maxPages": max_pages,
    }
    if success_criteria_id:
        payload_json["successCriteriaId"] = success_criteria_id
    if job_id:
        payload_json["jobId"] = job_id
    if discovered_urls:
        # R-1: when Python's snapshot has already enumerated the pages, send
        # the full list so Node skips its own BFS (which was capped by
        # flatCrawlBudgetMs=255s and was the source of the kao.com 3-page
        # truncation that left a2 unaudited by axe).
        payload_json["discoveredUrls"] = discovered_urls
    # Size the read timeout to the work Node will do. In snapshot-fed mode Node
    # audits every ``discovered_urls`` entry with no internal budget, so a flat
    # 300 s ceiling dropped all axe findings on large child crawls (see
    # _node_http_timeout). Fall back to the page count we asked Node to crawl
    # when the snapshot produced no explicit list.
    _page_count = len(discovered_urls) if discovered_urls else (max_pages if max_depth > 0 else 1)
    http_timeout = _node_http_timeout(_page_count)
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            resp = await client.post(endpoint, json=payload_json)
            resp.raise_for_status()
            body = resp.json()
            # Mirror Node-side per-page timing rows into our shared JSONL so
            # the run summary attributes time to both engines. Failure here
            # never breaks the audit — the findings already returned cleanly.
            if job_id:
                _mirror_node_timings(job_id, body.get("timings") or [])
            return body.get("findings", [])
    except httpx.ConnectError:
        raise RuntimeError(f"axe_core: Node engine unreachable at {node_base_url}")
    except httpx.TimeoutException:
        raise RuntimeError(
            f"axe_core: Node engine timed out after {http_timeout:.0f}s "
            f"({_page_count} page(s), {endpoint}) — raise "
            f"KA11Y_NODE_HTTP_PER_PAGE_TIMEOUT_SECONDS / KA11Y_JOB_TIMEOUT_SECONDS "
            f"if the crawl legitimately needs longer."
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 502:
            raise RuntimeError(f"axe_core: Node engine Bad Gateway ({endpoint})")
        raise RuntimeError(f"axe_core: Node engine returned {e.response.status_code}")
    except Exception as e:
        raise RuntimeError(f"axe_core: unexpected error calling Node: {e}")


def _mirror_node_timings(job_id: str, rows: List[Dict[str, Any]]) -> None:
    """Append Node-engine timing rows to the shared JSONL via stage_timing.

    Row shape from Node mirrors the Python schema (`stage`, `sub_stage`,
    `page_url`, `depth`, `rule`, `duration_ms`, `item_count`, `status`,
    `error`, `extra`). Anything malformed is skipped silently.
    """
    for row in rows:
        try:
            stage_timing.record(
                job_id,
                stage=str(row.get("stage") or "axe_core"),
                duration_ms=float(row.get("duration_ms") or 0.0),
                status=str(row.get("status") or "ok"),
                page_url=row.get("page_url"),
                depth=row.get("depth"),
                sub_stage=row.get("sub_stage"),
                rule=row.get("rule"),
                item_count=row.get("item_count"),
                error=row.get("error"),
                extra={**(row.get("extra") or {}), "source": "node"},
            )
        except Exception:  # noqa: BLE001 — never let mirroring break a run
            continue


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
        from ka11y.crawler.crawler import (
            AsyncImageCrawler,
            ImageCrawlerNavigationError,
        )
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


async def _stage_form_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_form_audit: bool,
    job_id: str,
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

        form_crawler = AsyncFormCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "form", url, pages_getter=lambda: len(form_inputs or [])
        ):
            form_inputs = await form_crawler.crawl()
        _record_crawler_time(job_id, "form_audit", time.perf_counter() - start_crawl)
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


async def _stage_sensory_audit(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_sensory_audit: bool,
    job_id: str,
    lang: str = "en",
) -> List[Dict]:
    """
    Crawl text-bearing elements → 1.3.3 sensory-characteristics check.

    Pipeline:
      AsyncSensoryCrawler  →  SensoryCharacteristicsAuditor  →  findings
    """
    # Import stage helpers lazily so this file can be used standalone.
    from ka11y.api.v1.combined.stage_events import (
        _stage_complete,
        _stage_error_and_warn,
        _stage_start,
    )
    from ka11y.api.v1.combined.findings import _sensory_to_findings  # noqa: F401

    _stage_start(job_id, "sensory_audit")

    if not run_sensory_audit:
        _stage_complete(job_id, "sensory_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.non_text.sensory_auditor import (
            SensoryCharacteristicsAuditor,
        )
        from ka11y.crawler.sensory_crawler import AsyncSensoryCrawler

        # ── Crawl ──────────────────────────────────────────────────────────
        sensory_crawler = AsyncSensoryCrawler(
            base_url=url,
            output_dir=str(output_dir),
            max_depth=max_depth,
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "sensory", url, pages_getter=lambda: len(elements or [])
        ):
            elements = await sensory_crawler.crawl()
        _record_crawler_time(job_id, "sensory_audit", time.perf_counter() - start_crawl)
        await asyncio.to_thread(sensory_crawler.save_raw_json)

        # ── Audit ──────────────────────────────────────────────────────────
        auditor = SensoryCharacteristicsAuditor(
            output_dir=str(output_dir),
            lang=lang,
        )
        records: List[Dict] = await asyncio.to_thread(
            functools.partial(auditor.generate_audit_report, elements=elements)
        )

        # ── Convert to standard findings ───────────────────────────────────
        findings: List[Dict] = _sensory_to_findings(records, url)

        _stage_complete(job_id, "sensory_audit", len(findings))
        return findings

    except Exception as _exc:
        _stage_error_and_warn(job_id, "sensory_audit", _exc)
        return []


async def _stage_label_in_name(
    url: str,
    output_dir: Path,
    max_depth: int,
    run_label_in_name_audit: bool,
    job_id: str,
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

        interactive_crawler = InteractiveElementCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "interactive", url,
            pages_getter=lambda: len(interactive_elements or []),
        ):
            interactive_elements = await interactive_crawler.crawl()
        _record_crawler_time(job_id, "label_in_name", time.perf_counter() - start_crawl)
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

        moving_crawler = MovingContentCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "pause_stop_hide", url,
            pages_getter=lambda: len(moving_items or []),
        ):
            moving_items = await moving_crawler.crawl()
        _record_crawler_time(job_id, "pause_stop_hide", time.perf_counter() - start_crawl)
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

        ts_crawler = TargetSizeCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "target_size", url, pages_getter=lambda: len(ts_items or [])
        ):
            ts_items = await ts_crawler.crawl()
        _record_crawler_time(job_id, "target_size", time.perf_counter() - start_crawl)
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

        ts_crawler = AsyncTextSpacingCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "text_spacing", url, pages_getter=lambda: len(items or [])
        ):
            items = await ts_crawler.crawl()
        _record_crawler_time(job_id, "text_spacing", time.perf_counter() - start_crawl)
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
    step_logger: ExecutionStepLogger | None = None,
    discovered_urls: List[str] | None = None,
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

        crawler = RenderedLayoutCrawler(base_url=url, output_dir=str(output_dir))
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "rendered_layout", url,
            pages_getter=lambda: len(discovered_urls or []),
        ):
            raw = await crawler.crawl(discovered_urls=discovered_urls)
        _record_crawler_time(job_id, "rendered_layout_audit", time.perf_counter() - start_crawl)
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

        _record_stage_metrics(
            step_logger,
            stage="rendered_layout_audit",
            crawler_items=len(raw) if hasattr(raw, "__len__") else 0,
            auditor_records=len(records),
            findings=len(findings),
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
) -> List[Dict]:
    """Crawl media elements → 1.2.1 audio-only / video-only check."""
    _stage_start(job_id, "media_audit")
    if not run_media_audit:
        _stage_complete(job_id, "media_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.media.media_auditor import MediaAuditor
        from ka11y.crawler.media_crawler import AsyncMediaCrawler

        media_crawler = AsyncMediaCrawler(
            base_url=url, output_dir=str(output_dir), max_depth=max_depth
        )
        start_crawl = time.perf_counter()
        async with time_crawler(
            output_dir, "media", url, pages_getter=lambda: len(media_items or [])
        ):
            media_items = await media_crawler.crawl()
        _record_crawler_time(job_id, "media_audit", time.perf_counter() - start_crawl)
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


async def _stage_form_audit_universal(
    url: str,
    output_dir: Path,
    run_form_audit: bool,
    job_id: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "form_audit")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "form_audit", crawl_dur)

    if not run_form_audit:
        _stage_complete(job_id, "form_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.forms.form_auditor import (
            FormAccessibilityAuditor,
        )

        snapshot = await snapshot_task
        form_auditor = FormAccessibilityAuditor(output_dir=str(output_dir))
        records = await asyncio.to_thread(
            functools.partial(
                form_auditor.generate_audit_report, form_inputs=snapshot.forms
            )
        )
        findings = _form_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="form_audit",
            crawler_items=len(snapshot.forms),
            auditor_records=len(records),
            findings=len(findings),
        )
        _stage_complete(job_id, "form_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "form_audit", _exc)
        return []


async def _stage_label_in_name_universal(
    url: str,
    output_dir: Path,
    run_label_in_name_audit: bool,
    job_id: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "label_in_name")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "label_in_name", crawl_dur)

    if not run_label_in_name_audit:
        _stage_complete(job_id, "label_in_name", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import (
            LabelInNameAuditor,
        )

        snapshot = await snapshot_task
        auditor = LabelInNameAuditor(output_dir=str(output_dir))
        records = await asyncio.to_thread(
            auditor.generate_audit_report, snapshot.interactive
        )
        findings = _lin_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="label_in_name",
            crawler_items=len(snapshot.interactive),
            auditor_records=len(records),
            findings=len(findings),
        )
        _stage_complete(job_id, "label_in_name", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "label_in_name", _exc)
        return []


async def _stage_pause_stop_hide_universal(
    url: str,
    output_dir: Path,
    run_pause_stop_hide_audit: bool,
    job_id: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "pause_stop_hide")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "pause_stop_hide", crawl_dur)

    if not run_pause_stop_hide_audit:
        _stage_complete(job_id, "pause_stop_hide", 0)
        return []

    try:
        from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import (
            PauseStopHideAuditor,
        )

        snapshot = await snapshot_task
        auditor = PauseStopHideAuditor(output_dir=str(output_dir))
        records = await asyncio.to_thread(
            auditor.generate_audit_report, snapshot.moving_content
        )
        findings = _psh_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="pause_stop_hide",
            crawler_items=len(snapshot.moving_content),
            auditor_records=len(records),
            findings=len(findings),
            extra={
                "na_records": sum(
                    1 for record in records if record.get("wcag_2_2_2_status") == "N/A"
                ),
            },
        )
        _stage_complete(job_id, "pause_stop_hide", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "pause_stop_hide", _exc)
        return []


async def _stage_target_size_universal(
    url: str,
    output_dir: Path,
    run_target_size_audit: bool,
    job_id: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "target_size")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "target_size", crawl_dur)

    if not run_target_size_audit:
        _stage_complete(job_id, "target_size", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.target_size_auditor import (
            TargetSizeAuditor,
        )

        snapshot = await snapshot_task
        auditor = TargetSizeAuditor(output_dir=str(output_dir))
        records = await asyncio.to_thread(
            auditor.generate_audit_report, snapshot.target_sizes
        )
        findings = _ts_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="target_size",
            crawler_items=len(snapshot.target_sizes),
            auditor_records=len(records),
            findings=len(findings),
        )
        _stage_complete(job_id, "target_size", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "target_size", _exc)
        return []


async def _stage_text_spacing_universal(
    url: str,
    output_dir: Path,
    run_text_spacing_audit: bool,
    job_id: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "text_spacing")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "text_spacing", crawl_dur)

    if not run_text_spacing_audit:
        _stage_complete(job_id, "text_spacing", 0)
        return []

    try:
        from ka11y.accessibility.rules.input_modalities.text_spacing_auditor import (
            TextSpacingAuditor,
        )

        snapshot = await snapshot_task
        auditor = TextSpacingAuditor(output_dir=str(output_dir))
        records = await asyncio.to_thread(
            auditor.generate_audit_report, snapshot.text_spacing
        )
        findings = _crawler_text_spacing_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="text_spacing",
            crawler_items=len(snapshot.text_spacing),
            auditor_records=len(records),
            findings=len(findings),
        )
        _stage_complete(job_id, "text_spacing", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "text_spacing", _exc)
        return []


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


async def _stage_sensory_audit_universal(
    url: str,
    output_dir: Path,
    run_sensory_audit: bool,
    job_id: str,
    lang: str,
    snapshot_task,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "sensory_audit")
    crawl_dur = _jobs.get(job_id, {}).get("universal_crawler_duration_s")
    if crawl_dur:
        _record_crawler_time(job_id, "sensory_audit", crawl_dur)

    if not run_sensory_audit:
        _stage_complete(job_id, "sensory_audit", 0)
        return []

    try:
        from ka11y.accessibility.rules.non_text.sensory_auditor import (
            SensoryCharacteristicsAuditor,
        )

        snapshot = await snapshot_task
        auditor = SensoryCharacteristicsAuditor(output_dir=str(output_dir), lang=lang)
        records = await asyncio.to_thread(
            functools.partial(auditor.generate_audit_report, elements=snapshot.sensory)
        )
        findings = _sensory_to_findings(records, url)
        _record_stage_metrics(
            step_logger,
            stage="sensory_audit",
            crawler_items=len(snapshot.sensory),
            auditor_records=len(records),
            findings=len(findings),
        )
        _stage_complete(job_id, "sensory_audit", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "sensory_audit", _exc)
        return []


async def _stage_consistent_navigation(
    url: str,
    output_dir: Path,
    run_consistent_navigation_audit: bool,
    job_id: str,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "consistent_navigation")
    if not run_consistent_navigation_audit:
        _stage_complete(job_id, "consistent_navigation", 0)
        return []

    try:
        from ka11y.accessibility.rules.navigation.consistent_nav import analyze_wcag_323
        
        report = await analyze_wcag_323(url)
        findings = _consistent_navigation_to_findings(report, url)
        _stage_complete(job_id, "consistent_navigation", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "consistent_navigation", _exc)
        return []


async def _stage_consistent_identification(
    url: str,
    output_dir: Path,
    run_consistent_id_audit: bool,
    job_id: str,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "consistent_identification")
    if not run_consistent_id_audit:
        _stage_complete(job_id, "consistent_identification", 0)
        return []

    try:
        from ka11y.accessibility.rules.navigation.consistent_id import analyze_wcag_324
        
        report = await analyze_wcag_324(url)
        findings = _consistent_id_to_findings(report, url)
        _stage_complete(job_id, "consistent_identification", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "consistent_identification", _exc)
        return []


async def _stage_unusual_words(
    url: str,
    output_dir: Path,
    run_unusual_words_audit: bool,
    job_id: str,
    lang: str,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "unusual_words")
    if not run_unusual_words_audit:
        _stage_complete(job_id, "unusual_words", 0)
        return []

    try:
        from ka11y.accessibility.rules.language.unusual_words import analyze_wcag_313
        
        report = await analyze_wcag_313(url)
        findings = _unusual_words_to_findings(report, url)
        _stage_complete(job_id, "unusual_words", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "unusual_words", _exc)
        return []


async def _stage_section_headings(
    url: str,
    output_dir: Path,
    run_section_headings_audit: bool,
    job_id: str,
    step_logger: ExecutionStepLogger | None = None,
) -> List[Dict]:
    _stage_start(job_id, "section_headings")
    if not run_section_headings_audit:
        _stage_complete(job_id, "section_headings", 0)
        return []

    try:
        from ka11y.accessibility.rules.rendered.section_headings import analyze_wcag_2410
        
        report = await analyze_wcag_2410(url)
        findings = _section_headings_to_findings(report, url)
        _stage_complete(job_id, "section_headings", len(findings))
        return findings
    except Exception as _exc:
        _stage_error_and_warn(job_id, "section_headings", _exc)
        return []


# ── Python pipeline orchestrator ──────────────────────────────────────────────


# ... [code stays the same up to _run_python_stages]


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
    run_captions_audit: bool,
    run_pause_stop_hide_audit: bool,
    run_target_size_audit: bool,
    run_resize_text_audit: bool,
    run_reflow_audit: bool,
    run_text_spacing_audit: bool,
    run_orientation_audit: bool,
    run_hover_focus_content_audit: bool,
    run_focus_not_obscured_min_audit: bool,
    run_focus_not_obscured_enh_audit: bool,
    run_sensory_audit: bool,
    job_id: str,
    lang: str = "en",
    step_logger: ExecutionStepLogger | None = None,
    internal_links: bool = True,
    max_pages: int = 50,
    success_criteria_id: Optional[str] = None,
    run_consistent_navigation_audit: bool = False,
    run_consistent_id_audit: bool = False,
    run_unusual_words_audit: bool = False,
    run_section_headings_audit: bool = False,
    snapshot_urls_event: Optional[asyncio.Event] = None,
    snapshot_urls_container: Optional[Dict[str, Any]] = None,
) -> PythonStagesResult:
    """
    Run all Python audit stages concurrently.

    Returns a :class:`PythonStagesResult` with named ``findings``,
    ``contrast_report``, and ``image_audit_report`` fields.

    ``snapshot_urls_event`` / ``snapshot_urls_container`` (R-1) let a sibling
    Node task wait for the universal snapshot's discovered URL list before
    starting its own crawl. We always signal the event before returning so a
    crash here cannot strand Node — see the ``finally`` block at the bottom
    of this function.
    """

    def _timed(coro):
        return asyncio.wait_for(coro, timeout=_STAGE_TIMEOUT_SECONDS)

    static_rules_enabled = any(
        (
            run_form_audit,
            # run_label_in_name_audit, # Handled by pipeline
            run_media_audit,
            run_captions_audit,
            run_pause_stop_hide_audit,
            run_target_size_audit,
            run_text_spacing_audit,
            run_sensory_audit,
        )
    )

    # The rendered-layout stage does not crawl on its own — it audits exactly the
    # pages in ``discovered_urls``, which come from the snapshot's bounded BFS. So
    # at depth>0 it needs the snapshot to reach deeper pages. (The image stage has
    # its own BFS, so an image-only deep audit does not need the snapshot.)
    rendered_layout_enabled = any(
        (
            run_resize_text_audit,
            run_reflow_audit,
            run_text_spacing_audit,
            run_orientation_audit,
            run_hover_focus_content_audit,
            run_focus_not_obscured_min_audit,
            run_focus_not_obscured_enh_audit,
        )
    )

    # 1. Run universal snapshot first.
    #
    # The snapshot now ALSO carries per-page pipeline contexts, so building it
    # at ``max_depth > 0`` is the only way the unified pipeline (1.1.1, 1.4.3,
    # 1.4.5, 1.4.6, 1.4.11, 2.4.7, 2.4.13, 2.5.3, 2.5.8) covers more than the
    # entry URL. Without that, deep pages were silently losing every pipeline
    # finding even though the BFS visited them. The image-only ``max_depth=0``
    # path remains snapshot-free (the pipeline falls back to its single-URL
    # navigation, which preserves the previous behaviour for that case).
    snapshot = None
    discovered_urls = [url]
    try:
        if (
            static_rules_enabled
            or (rendered_layout_enabled and max_depth > 0)
            or max_depth > 0
        ):
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
            # page_summary key. Dedupe (order-preserving) before feeding Node so
            # it doesn't re-audit an identical resolved page.
            seen_pages: set[str] = set()
            discovered_urls = []
            for s in snapshot.page_summaries:
                pu = s["page_url"]
                if pu not in seen_pages:
                    seen_pages.add(pu)
                    discovered_urls.append(pu)
            if not discovered_urls:
                discovered_urls = [url]
    finally:
        # R-1: always release the sibling Node task waiting on the snapshot,
        # even if the snapshot load raised. Without this `finally` an
        # exception here would leave Node blocked on `Event.wait()` until the
        # _SNAPSHOT_URLS_WAIT_SECONDS fallback timeout, doubling failure latency.
        if snapshot_urls_container is not None:
            snapshot_urls_container["urls"] = list(discovered_urls)
        if snapshot_urls_event is not None and not snapshot_urls_event.is_set():
            snapshot_urls_event.set()

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
        _timed(
            _stage_form_audit_universal(
                url, output_dir, run_form_audit, job_id, snapshot_task, step_logger
            )
        ),
        # MUTED: _stage_label_in_name_universal is replaced by Pipeline 2.5.3.
        # Snapshot is passed so the pipeline evaluates every BFS-discovered page,
        # not just the entry URL; with no snapshot it falls back to single-URL mode.
        _timed(
            _run_pipeline_stage(
                url,
                job_id,
                run_image_audit=run_image_audit,
                run_label_in_name_audit=run_label_in_name_audit,
                run_target_size_audit=run_target_size_audit,
                lang=lang,
                snapshot=snapshot,
            )
        ),
        _timed(
            _stage_pause_stop_hide_universal(
                url,
                output_dir,
                run_pause_stop_hide_audit,
                job_id,
                snapshot_task,
                step_logger,
            )
        ),
        # MUTED: _stage_target_size_universal is replaced by Pipeline 2.5.8
        # _timed(
        #    _stage_target_size_universal(
        #        url, output_dir, run_target_size_audit, job_id, snapshot_task, step_logger
        #    )
        # ),
        _timed(
            _stage_text_spacing_universal(
                url,
                output_dir,
                run_text_spacing_audit,
                job_id,
                snapshot_task,
                step_logger,
            )
        ),
        _heavy(
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
                step_logger,
                discovered_urls=discovered_urls,
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
        _timed(
            _stage_sensory_audit_universal(
                url,
                output_dir,
                run_sensory_audit,
                job_id,
                lang,
                snapshot_task,
                step_logger,
            )
        ),
        _timed(
            _stage_consistent_navigation(
                url, output_dir, run_consistent_navigation_audit, job_id, step_logger
            )
        ),
        _timed(
            _stage_consistent_identification(
                url, output_dir, run_consistent_id_audit, job_id, step_logger
            )
        ),
        _timed(
            _stage_unusual_words(
                url, output_dir, run_unusual_words_audit, job_id, lang, step_logger
            )
        ),
        _timed(
            _stage_section_headings(
                url, output_dir, run_section_headings_audit, job_id, step_logger
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
