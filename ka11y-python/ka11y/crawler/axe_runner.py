"""
ka11y/crawler/axe_runner.py
==========================
Unified crawl (P6): run axe-core inside the same Playwright/Chromium the Python
crawlers already use, instead of a second Puppeteer crawl in the Node service.

axe-core is browser-agnostic JS — injecting ``axe.min.js`` into a Playwright
page and calling ``axe.run`` produces the same results Puppeteer would. This
eliminates the double page-load (Playwright snapshot + Puppeteer axe) that
dominates deep-crawl cost.

Default OFF. Enabled with ``KA11Y_UNIFIED_CRAWL=1``; the runner then swaps the
HTTP call to Node for :func:`run_axe_unified`, which is a drop-in for
``stages._call_node_flat`` (same snapshot-URL synchronisation, same flat
findings shape consumed by ``runner._merge_findings``).

axe.min.js resolution order:
  1. ``$KA11Y_AXE_MIN_JS``
  2. vendored ``ka11y/crawler/vendor/axe.min.js``
  3. dev fallback ``../ka11y-node/node_modules/axe-core/axe.min.js``
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.crawler.browser_pool import leased_context
from ka11y.utils import stage_timing

logger = setup_logger(name="KAC", tag="axe_runner")

_WCAG_TAG_RE = re.compile(r"^wcag(\d)(\d)(\d+)$")
_LEVEL_TAGS = {"wcag2a": "A", "wcag21a": "A", "wcag2aa": "AA", "wcag21aa": "AA", "wcag2aaa": "AAA"}

_LEVEL_RUN_TAGS = {
    "A": ["wcag2a", "wcag21a", "wcag22a"],
    "AA": ["wcag2a", "wcag21a", "wcag22a", "wcag2aa", "wcag21aa", "wcag22aa"],
    "AAA": [
        "wcag2a", "wcag21a", "wcag22a", "wcag2aa", "wcag21aa", "wcag22aa",
        "wcag2aaa", "wcag21aaa",
    ],
}

_AXE_RUN_JS = """
(opts) => new Promise((resolve) => {
  try {
    axe.run(document, opts).then(resolve).catch((e) => resolve({ error: String(e) }));
  } catch (e) { resolve({ error: String(e) }); }
})
"""


def is_unified_enabled() -> bool:
    return os.environ.get("KA11Y_UNIFIED_CRAWL", "0") == "1"


def resolve_axe_js() -> Optional[Path]:
    override = os.environ.get("KA11Y_AXE_MIN_JS")
    candidates = [
        Path(override) if override else None,
        Path(__file__).resolve().parent / "vendor" / "axe.min.js",
        Path(__file__).resolve().parents[3] / "ka11y-node" / "node_modules" / "axe-core" / "axe.min.js",
    ]
    for c in candidates:
        if c and c.is_file():
            return c
    return None


def _wcag_sc_from_tags(tags: List[str]) -> Optional[str]:
    for t in tags or []:
        m = _WCAG_TAG_RE.match(t)
        if m:
            return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return None


def _level_from_tags(tags: List[str]) -> Optional[str]:
    best = None
    order = {"A": 1, "AA": 2, "AAA": 3}
    for t in tags or []:
        lvl = _LEVEL_TAGS.get(t)
        if lvl and (best is None or order[lvl] > order[best]):
            best = lvl
    return best


_IMPACT_TO_SEVERITY = {
    "critical": "critical",
    "serious": "high",
    "moderate": "medium",
    "minor": "low",
}


def _build_element(node: Dict[str, Any], page_url: Optional[str]) -> Optional[Dict[str, Any]]:
    html = (node.get("html") or "")[:600]
    target = node.get("target") if isinstance(node.get("target"), list) else []
    selector = target[0] if target and isinstance(target[0], str) else None
    tag = None
    if html:
        m = re.match(r"^<(\w+)", html)
        if m:
            tag = m.group(1).upper()
    element_id = None
    if selector:
        m = re.search(r"#([\w-]+)", selector)
        if m:
            element_id = m.group(1)
    if not html and not element_id and not target and not tag and not selector:
        return None
    return {
        "html": html,
        "element_id": element_id,
        "tag": tag,
        "target": target,
        "selector": selector,
        "page_url": page_url,
    }


def map_axe_results(
    raw: Dict[str, Any], page_url: Optional[str], criteria_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Map a raw ``axe.run`` result to the flat finding shape used across ka11y.

    Mirrors ``ka11y-node/src/utils/axeResultMapper.js`` (the fields
    ``runner._merge_findings`` and ``report._build_report`` consume): one
    finding per failing/incomplete node, one per passing rule.
    """
    if not raw or raw.get("error"):
        if raw and raw.get("error"):
            logger.warning("[axe] page %s: axe.run error: %s", page_url, raw["error"])
        return []

    findings: List[Dict[str, Any]] = []

    def _emit(rule: Dict[str, Any], status: str, per_node: bool) -> None:
        tags = rule.get("tags") or []
        sc = _wcag_sc_from_tags(tags)
        if criteria_filter and sc != criteria_filter:
            return
        level = _level_from_tags(tags)
        severity = _IMPACT_TO_SEVERITY.get(rule.get("impact") or "")
        base = {
            "source": "axe",
            "rule_id": rule.get("id"),
            "wcag_sc": sc,
            "level": level,
            "severity": severity,
            "status": status,
            "reason": rule.get("help") or rule.get("description"),
            "help_url": rule.get("helpUrl"),
        }
        nodes = rule.get("nodes") or []
        if per_node and nodes:
            for node in nodes:
                el = _build_element(node, page_url)
                f = dict(base)
                f["element"] = el
                findings.append(f)
        else:
            f = dict(base)
            f["element"] = _build_element(nodes[0], page_url) if nodes else None
            findings.append(f)

    for rule in raw.get("violations", []) or []:
        _emit(rule, "fail", per_node=True)
    for rule in raw.get("incomplete", []) or []:
        _emit(rule, "needs_review", per_node=True)
    for rule in raw.get("passes", []) or []:
        _emit(rule, "pass", per_node=False)

    return findings


async def _run_axe_on_url(
    url: str, axe_js: Path, run_opts: Dict[str, Any], criteria_filter: Optional[str]
) -> List[Dict[str, Any]]:
    """Open *url* in a leased context, inject axe, run it, map results."""
    try:
        from ka11y.api.v1.combined.routes import build_ssrf_route_handler
    except Exception:  # noqa: BLE001
        build_ssrf_route_handler = None  # type: ignore

    async with leased_context(
        viewport={"width": 1440, "height": 900},
    ) as context:
        page = await context.new_page()
        try:
            if build_ssrf_route_handler is not None:
                await page.route("**/*", build_ssrf_route_handler(page))
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.add_script_tag(path=str(axe_js))
            raw = await page.evaluate(_AXE_RUN_JS, run_opts)
            resolved = page.url or url
            return map_axe_results(raw, resolved, criteria_filter)
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                pass


async def run_axe_unified(
    url: str,
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
    snapshot_wait_timeout: float = 1200.0,
) -> List[Dict[str, Any]]:
    """Drop-in replacement for ``stages._call_node_flat`` that runs axe-core in
    Playwright. Same snapshot-URL synchronisation: waits for the Python snapshot
    to publish the discovered URL set, then audits exactly those pages — no
    second BFS, no flatCrawlBudgetMs cliff.
    """
    axe_js = resolve_axe_js()
    if axe_js is None:
        raise RuntimeError(
            "KA11Y_UNIFIED_CRAWL is on but axe.min.js was not found. Set "
            "KA11Y_AXE_MIN_JS or vendor ka11y/crawler/vendor/axe.min.js."
        )

    # Reuse the exact snapshot handshake Node used (see _call_node_flat).
    if (
        snapshot_urls_event is not None
        and snapshot_urls_container is not None
        and not discovered_urls
    ):
        try:
            await asyncio.wait_for(snapshot_urls_event.wait(), timeout=snapshot_wait_timeout)
            urls = snapshot_urls_container.get("urls") or []
            if urls and not (len(urls) == 1 and urls[0] == url):
                discovered_urls = list(urls)
        except asyncio.TimeoutError:
            logger.error("[axe] unified: snapshot URL wait timed out; auditing entry URL only")

    targets = discovered_urls or [url]
    targets = targets[: max(1, max_pages)]

    run_opts: Dict[str, Any] = {
        "runOnly": {"type": "tag", "values": _LEVEL_RUN_TAGS.get(wcag_level, _LEVEL_RUN_TAGS["AAA"])},
        "resultTypes": ["violations", "incomplete", "passes"],
    }
    criteria_filter = success_criteria_id

    all_findings: List[Dict[str, Any]] = []
    for target in targets:
        try:
            async with stage_timing.time_stage_async(
                job_id or "unified",
                "axe_core",
                sub_stage="axe_run",
                page_url=target,
            ):
                page_findings = await _run_axe_on_url(target, axe_js, run_opts, criteria_filter)
            all_findings.extend(page_findings)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[axe] unified: %s failed: %s", target, exc)
            stage_timing.record(
                job_id or "unified",
                stage="axe_core",
                sub_stage="axe_run",
                page_url=target,
                duration_ms=0.0,
                status="error",
                error=str(exc),
            )

    logger.info("[axe] unified: %d findings across %d page(s)", len(all_findings), len(targets))
    return all_findings
