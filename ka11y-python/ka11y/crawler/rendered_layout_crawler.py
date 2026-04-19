"""
ka11y/crawler/rendered_layout_crawler.py
=========================================
Playwright-based rendered-layout crawler for WCAG rules that require
real browser rendering and scenario simulation.

Rules covered:
  • 1.4.4  Resize Text
  • 1.4.10 Reflow
  • 1.4.12 Text Spacing
  • 1.3.4  Orientation
  • 1.4.13 Content on Hover or Focus
  • 2.4.11 Focus Not Obscured (Minimum)
  • 2.4.12 Focus Not Obscured (Enhanced)

Usage
-----
    crawler = RenderedLayoutCrawler(base_url="https://example.com",
                                    output_dir="/tmp/out")
    results = await crawler.crawl()
    crawler.save_raw_json()
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

from ka11y.config.logger import setup_logger
from ka11y.crawler.context_factory import new_crawler_context
from ka11y.crawler.cookie_handler import handle_cookies
from ka11y.accessibility.rendered.geometry import rect_from_dict
from ka11y.accessibility.rendered.heuristics import compute_obscuration
from ka11y.accessibility.rendered.models import (
    FocusStep,
    HoverInteractionResult,
    PageSnapshot,
)
from ka11y.accessibility.rendered.snapshot_collector import collect_snapshot
from ka11y.accessibility.rendered.stabilizer import stabilize
from ka11y.utils.crawler_settings import (
    build_text_spacing_cjk_selector_css,
    get_max_focus_steps,
    get_max_hover_candidates,
)

logger = setup_logger(name="KAC", tag="rendered_layout")

# ── Viewport constants ────────────────────────────────────────────────────────

_DESKTOP_W, _DESKTOP_H = 1280, 720
_REFLOW_W, _REFLOW_H = 320, 640
_PORTRAIT_W, _PORTRAIT_H = 390, 844
_LANDSCAPE_W, _LANDSCAPE_H = 844, 390

_MAX_FOCUS_STEPS = get_max_focus_steps()
_MAX_HOVER_CANDIDATES = get_max_hover_candidates()
_PAGE_TIMEOUT_MS = 30_000

# ── CSS for text-spacing scenario (WCAG 1.4.12) ───────────────────────────────

_TEXT_SPACING_CSS = """
* {
    line-height: 1.5 !important;
    letter-spacing: 0.12em !important;
    word-spacing: 0.16em !important;
}
p, li, dt, dd, blockquote {
    margin-bottom: 2em !important;
}
""" + build_text_spacing_cjk_selector_css()

# ── CSS for text-resize scenario (WCAG 1.4.4) ─────────────────────────────────

_RESIZE_TEXT_JS = """
() => {
    document.documentElement.style.fontSize = '200%';
}
"""


# ── JS for overlay detection (focus scenarios) ────────────────────────────────

_OVERLAY_JS = """
() => {
    const overlays = [];
    const els = document.querySelectorAll('*');
    for (const el of els) {
        const cs = window.getComputedStyle(el);
        const pos = cs.position;
        if (pos !== 'fixed' && pos !== 'sticky') continue;
        const rect = el.getBoundingClientRect();
        if (rect.width < 10 || rect.height < 10) continue;
        overlays.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            x: rect.x, y: rect.y,
            width: rect.width, height: rect.height,
            top: rect.top, right: rect.right,
            bottom: rect.bottom, left: rect.left,
            z_index: parseInt(cs.zIndex) || 0,
            html: el.outerHTML.slice(0, 200),
        });
    }
    return overlays;
}
"""

# ── JS to find hover/focus candidate triggers ─────────────────────────────────

_HOVER_CANDIDATES_JS = """
() => {
    function safeSelector(el) {
        try {
            if (el.id) return `#${CSS.escape(el.id)}`;
            const parts = [];
            let cur = el;
            while (cur && cur.nodeType === 1 && parts.length < 6) {
                let part = cur.tagName.toLowerCase();
                if (cur.classList && cur.classList.length > 0) {
                    part += [...cur.classList]
                        .slice(0, 2)
                        .map(cls => `.${CSS.escape(cls)}`)
                        .join('');
                }
                const parent = cur.parentElement;
                if (parent) {
                    const sameTag = [...parent.children].filter(child => child.tagName === cur.tagName);
                    if (sameTag.length > 1) {
                        part += `:nth-of-type(${sameTag.indexOf(cur) + 1})`;
                    }
                }
                parts.unshift(part);
                const selector = parts.join(' > ');
                try {
                    if (document.querySelector(selector) === el) return selector;
                } catch (e) {}
                cur = parent;
            }
            return parts.join(' > ');
        } catch (e) {
            return '';
        }
    }

    const candidates = [];
    const triggers = document.querySelectorAll(
        '[aria-expanded], [data-tooltip], [title]:not(html):not(head), ' +
        '[aria-describedby], [aria-haspopup], .tooltip, .popover, .dropdown-toggle'
    );
    let idx = 0;
    for (const el of triggers) {
        try {
        if (idx >= 20) break;
        const rect = el.getBoundingClientRect();
        if (!rect || !Number.isFinite(rect.width) || !Number.isFinite(rect.height)) continue;
        if (rect.width === 0 || rect.height === 0) continue;
        const cs = window.getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        let html = '';
        try { html = el.outerHTML.slice(0, 200); } catch(e) {}
        candidates.push({
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            selector: safeSelector(el),
            html: html,
            rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                    top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left },
            index: idx,
        });
        idx++;
        } catch (e) {
            continue;
        }
    }
    return candidates;
}
"""

# ── JS for active element rect ────────────────────────────────────────────────

_ACTIVE_ELEMENT_JS = """
() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const rect = el.getBoundingClientRect();
    let html = '';
    try { html = el.outerHTML.slice(0, 200); } catch(e) {}
    return {
        tag: el.tagName.toLowerCase(),
        id: el.id || null,
        html: html,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
                top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left },
    };
}
"""


class RenderedLayoutCrawler:
    """
    Orchestrates scenario-based Playwright sessions and returns structured
    raw results for each WCAG rule's evaluator.
    """

    def __init__(
        self,
        base_url: str,
        output_dir: str,
        max_depth: int = 0,
    ) -> None:
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.max_focus_steps = _MAX_FOCUS_STEPS
        self.max_hover_candidates = _MAX_HOVER_CANDIDATES
        self._raw_results: Dict[str, Any] = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    async def crawl(self, discovered_urls: List[str] | None = None) -> List[Dict[str, Any]]:
        """
        Run all rendering scenarios and return a list of dicts (one per page),
        each containing the raw data consumed by evaluators.
        """
        urls = discovered_urls if discovered_urls else [self.base_url]
        all_results = []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                for url in urls:
                    logger.info(f"[rendered] starting scenarios for {url}")
                    # Temporarily override base_url for the scenario runners
                    original_base = self.base_url
                    self.base_url = url
                    try:
                        page_results = await self._run_all_scenarios(browser)
                        page_results["page_url"] = url
                        all_results.append(page_results)
                    finally:
                        self.base_url = original_base
            finally:
                await browser.close()

        self._raw_results_list = all_results
        return all_results

    def save_raw_json(self) -> None:
        """Save raw scenario results as JSON files for debugging."""
        path = self.output_dir / "rendered_layout_raw_all.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self._raw_results_list, fh, indent=2, ensure_ascii=False)
        logger.info(f"[rendered] saved raw results for {len(self._raw_results_list)} pages to {path}")

    # ── Internal scenario runner ───────────────────────────────────────────────

    async def _run_all_scenarios(self, browser: Browser) -> Dict[str, Any]:
        """Run all scenarios concurrently and collect results."""
        # Run layout scenarios concurrently
        (
            baseline_snap,
            snap_320,
            snap_text_spacing,
            snap_text_spacing_baseline,
            snap_resize,
            snap_portrait,
            snap_landscape,
        ) = await asyncio.gather(
            self._snapshot_at_viewport(_DESKTOP_W, _DESKTOP_H, "baseline", browser),
            self._snapshot_at_viewport(_REFLOW_W, _REFLOW_H, "reflow_320", browser),
            self._snapshot_with_css(
                _DESKTOP_W,
                _DESKTOP_H,
                "text_spacing_override",
                browser,
                css=_TEXT_SPACING_CSS,
            ),
            self._snapshot_at_viewport(
                _DESKTOP_W, _DESKTOP_H, "text_spacing_baseline", browser
            ),
            self._snapshot_with_js(
                _DESKTOP_W, _DESKTOP_H, "resize_text_200", browser, js=_RESIZE_TEXT_JS
            ),
            self._snapshot_at_viewport(
                _PORTRAIT_W, _PORTRAIT_H, "orientation_portrait", browser
            ),
            self._snapshot_at_viewport(
                _LANDSCAPE_W, _LANDSCAPE_H, "orientation_landscape", browser
            ),
            return_exceptions=True,
        )

        # Focus and hover scans run sequentially (they interact with the page)
        focus_steps = await self._focus_scan(browser)
        hover_results = await self._hover_scan(browser)

        def _safe(val: Any, fallback: Any) -> Any:
            return fallback if isinstance(val, Exception) else val

        empty_snap = PageSnapshot(
            scenario="empty",
            page_url=self.base_url,
            viewport_width=_DESKTOP_W,
            viewport_height=_DESKTOP_H,
        )

        return {
            "baseline": _safe(baseline_snap, empty_snap).model_dump(),
            "reflow_320": _safe(snap_320, empty_snap).model_dump(),
            "text_spacing_baseline": _safe(
                snap_text_spacing_baseline, empty_snap
            ).model_dump(),
            "text_spacing_override": _safe(snap_text_spacing, empty_snap).model_dump(),
            "resize_text_200": _safe(snap_resize, empty_snap).model_dump(),
            "orientation_portrait": _safe(snap_portrait, empty_snap).model_dump(),
            "orientation_landscape": _safe(snap_landscape, empty_snap).model_dump(),
            "focus_scan": [s.model_dump() for s in focus_steps],
            "hover_scan": [h.model_dump() for h in hover_results],
        }

    # ── Snapshot helpers ───────────────────────────────────────────────────────

    async def _make_context(
        self, browser: Browser, width: int, height: int
    ) -> BrowserContext:
        ctx = await new_crawler_context(
            browser,
            viewport={"width": width, "height": height},
        )
        return ctx

    async def _load_and_stabilize(self, page: Page) -> None:
        try:
            await page.goto(
                self.base_url,
                wait_until="domcontentloaded",
                timeout=_PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeout:
            logger.warning(f"[rendered] goto timeout for {self.base_url}")
            
        # ── Cookie Handling ──
        try:
            cookie_state = await handle_cookies(page)
            logger.debug(f"[rendered] Cookie handling state for {self.base_url}: {cookie_state}")
        except Exception as e:
            logger.debug(f"[rendered] Cookie handling exception for {self.base_url}: {e}")
            
        await stabilize(page)

    async def _snapshot_at_viewport(
        self,
        width: int,
        height: int,
        scenario: str,
        browser: Browser,
    ) -> PageSnapshot:
        ctx = await self._make_context(browser, width, height)
        try:
            page = await ctx.new_page()
            await self._load_and_stabilize(page)
            snap = await collect_snapshot(page, scenario, self.base_url)
            return snap
        except Exception as exc:
            logger.warning(f"[rendered] {scenario} snapshot failed: {exc}")
            return PageSnapshot(
                scenario=scenario,
                page_url=self.base_url,
                viewport_width=width,
                viewport_height=height,
                raw={"error": str(exc)},
            )
        finally:
            await ctx.close()

    async def _snapshot_with_css(
        self,
        width: int,
        height: int,
        scenario: str,
        browser: Browser,
        css: str,
    ) -> PageSnapshot:
        ctx = await self._make_context(browser, width, height)
        try:
            page = await ctx.new_page()
            await self._load_and_stabilize(page)
            await page.add_style_tag(content=css)
            await asyncio.sleep(0.3)  # let styles settle
            snap = await collect_snapshot(page, scenario, self.base_url)
            return snap
        except Exception as exc:
            logger.warning(f"[rendered] {scenario} css-snapshot failed: {exc}")
            return PageSnapshot(
                scenario=scenario,
                page_url=self.base_url,
                viewport_width=width,
                viewport_height=height,
                raw={"error": str(exc)},
            )
        finally:
            await ctx.close()

    async def _snapshot_with_js(
        self,
        width: int,
        height: int,
        scenario: str,
        browser: Browser,
        js: str,
    ) -> PageSnapshot:
        ctx = await self._make_context(browser, width, height)
        try:
            page = await ctx.new_page()
            await self._load_and_stabilize(page)
            await page.evaluate(js)
            await asyncio.sleep(0.3)
            snap = await collect_snapshot(page, scenario, self.base_url)
            return snap
        except Exception as exc:
            logger.warning(f"[rendered] {scenario} js-snapshot failed: {exc}")
            return PageSnapshot(
                scenario=scenario,
                page_url=self.base_url,
                viewport_width=width,
                viewport_height=height,
                raw={"error": str(exc)},
            )
        finally:
            await ctx.close()

    # ── Focus scan (2.4.11 / 2.4.12) ──────────────────────────────────────────

    async def _focus_scan(self, browser: Browser) -> List[FocusStep]:
        """
        Tab through focusable elements and detect obscuration by fixed overlays.
        """
        steps: List[FocusStep] = []
        ctx = await self._make_context(browser, _DESKTOP_W, _DESKTOP_H)
        try:
            page = await ctx.new_page()
            await self._load_and_stabilize(page)

            # Collect fixed/sticky overlays once
            overlays = await page.evaluate(_OVERLAY_JS)

            for step_idx in range(self.max_focus_steps):
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.05)

                el_data = await page.evaluate(_ACTIVE_ELEMENT_JS)
                if el_data is None:
                    continue  # focus on body — skip

                rect_d = el_data.get("rect", {})
                focus_rect = rect_from_dict(rect_d)

                # Skip zero-size / offscreen elements
                if focus_rect.width < 1 or focus_rect.height < 1:
                    continue

                # Compute obscuration ratio vs fixed overlays
                max_ratio, covering = compute_obscuration(focus_rect, overlays)

                steps.append(
                    FocusStep(
                        step_index=step_idx,
                        tag=el_data.get("tag", ""),
                        element_id=el_data.get("id"),
                        html_snippet=el_data.get("html", ""),
                        page_url=self.base_url,
                        rect=focus_rect,
                        covering_elements=covering,
                        fully_obscured=max_ratio >= 0.95,
                        partially_obscured=0.10 <= max_ratio < 0.95,
                        obscuration_ratio=round(max_ratio, 3),
                    )
                )

        except Exception as exc:
            logger.warning(f"[rendered] focus_scan failed: {exc}")
        finally:
            await ctx.close()

        return steps

    # ── Hover scan (1.4.13) ────────────────────────────────────────────────────

    async def _hover_scan(self, browser: Browser) -> List[HoverInteractionResult]:
        """
        Hover over candidate trigger elements and detect popup content behaviour.
        """
        results: List[HoverInteractionResult] = []
        ctx = await self._make_context(browser, _DESKTOP_W, _DESKTOP_H)
        try:
            page = await ctx.new_page()
            await self._load_and_stabilize(page)

            candidates = await page.evaluate(_HOVER_CANDIDATES_JS)

            for cand in candidates[: self.max_hover_candidates]:
                result = await self._test_hover_candidate(page, cand)
                if result is not None:
                    results.append(result)

        except Exception as exc:
            logger.warning(f"[rendered] hover_scan failed: {exc}")
        finally:
            await ctx.close()

        return results

    async def _test_hover_candidate(
        self,
        page: Page,
        cand: Dict[str, Any],
    ) -> Optional[HoverInteractionResult]:
        """Test one hover candidate for 1.4.13 behaviour."""
        tag = cand.get("tag", "")
        cand_id = cand.get("id")
        selector = cand.get("selector", "")
        html = cand.get("html", "")
        resolved_rect = await self._resolve_hover_candidate_box(page, cand)
        if not resolved_rect:
            logger.debug(f"[rendered] skipping hover candidate with no visible box: {selector or cand_id or tag}")
            return None

        cx = float(resolved_rect.get("x", 0)) + float(resolved_rect.get("width", 1)) / 2
        cy = float(resolved_rect.get("y", 0)) + float(resolved_rect.get("height", 1)) / 2

        try:
            # Collect baseline visible regions count
            baseline_count = await page.evaluate(
                '() => document.querySelectorAll(\'[aria-expanded="true"], '
                ".tooltip.show, .popover.show, [data-tooltip]:not([hidden])').length"
            )

            # Hover over the candidate
            await page.mouse.move(cx, cy)
            await asyncio.sleep(0.3)

            # Check if new content appeared
            after_count = await page.evaluate(
                '() => document.querySelectorAll(\'[aria-expanded="true"], '
                ".tooltip.show, .popover.show, [data-tooltip]:not([hidden])').length"
            )

            popup_appeared = int(after_count) > int(baseline_count)

            if not popup_appeared:
                # Try focus trigger
                try:
                    focus_selector = selector or (f"#{cand_id}" if cand_id else "")
                    if focus_selector:
                        await page.locator(focus_selector).first.focus()
                    await asyncio.sleep(0.2)
                    after_focus = await page.evaluate(
                        '() => document.querySelectorAll(\'[aria-expanded="true"], '
                        ".tooltip.show, .popover.show').length"
                    )
                    popup_appeared = int(after_focus) > int(baseline_count)
                except Exception:
                    pass

            if not popup_appeared:
                return None

            # Capture popup HTML
            popup_html = (
                await page.evaluate(
                    "() => {"
                    '  const el = document.querySelector(\'[aria-expanded="true"] + *, '
                    ".tooltip.show, .popover.show');"
                    "  return el ? el.outerHTML.slice(0, 300) : '';"
                    "}"
                )
                or ""
            )

            # Persistence: once shown, content should remain visible until the user
            # explicitly removes hover/focus (or dismisses it).
            await asyncio.sleep(0.35)
            stable_count = await page.evaluate(
                '() => document.querySelectorAll(\'[aria-expanded="true"], '
                ".tooltip.show, .popover.show').length"
            )
            persists = int(stable_count) > int(baseline_count)

            # Test: dismiss with Escape
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.15)
            after_esc = await page.evaluate(
                '() => document.querySelectorAll(\'[aria-expanded="true"], '
                ".tooltip.show, .popover.show').length"
            )
            dismissible = int(after_esc) < int(after_count)

            # Re-trigger to test hover-over
            await page.mouse.move(cx, cy)
            await asyncio.sleep(0.2)
            # Move toward where popup would be (above / below)
            await page.mouse.move(cx, cy - 60)
            await asyncio.sleep(0.2)
            after_move = await page.evaluate(
                '() => document.querySelectorAll(\'[aria-expanded="true"], '
                ".tooltip.show, .popover.show').length"
            )
            pointer_can_move = int(after_move) > 0

            # Move away to restore state
            await page.mouse.move(0, 0)
            await asyncio.sleep(0.2)

            # Treat the result as "certain" only when we can capture the popup node.
            # Count-only signals can be noisy on some component libraries.
            certain = bool(popup_html.strip())

            return HoverInteractionResult(
                trigger_tag=tag,
                trigger_id=cand_id,
                trigger_html=html,
                page_url=self.base_url,
                popup_appeared=True,
                popup_html=popup_html,
                dismissible_by_escape=dismissible,
                pointer_can_move_over=pointer_can_move,
                persists_until_removed=persists,
                certain=certain,
            )

        except Exception as exc:
            logger.debug(f"[rendered] hover test failed for {tag}: {exc}")
            return None

    async def _resolve_hover_candidate_box(
        self,
        page: Page,
        cand: Dict[str, Any],
    ) -> Optional[Dict[str, float]]:
        rect_d = cand.get("rect") or {}
        try:
            width = float(rect_d.get("width", 0))
            height = float(rect_d.get("height", 0))
            x = float(rect_d.get("x", 0))
            y = float(rect_d.get("y", 0))
            if width > 0 and height > 0:
                return {"x": x, "y": y, "width": width, "height": height}
        except (TypeError, ValueError):
            pass

        selector = str(cand.get("selector", "") or "").strip()
        if not selector:
            return None

        try:
            locator = page.locator(selector).first
            await locator.scroll_into_view_if_needed(timeout=2_000)
            box = await locator.bounding_box()
            if not box:
                return None
            width = float(box.get("width", 0))
            height = float(box.get("height", 0))
            if width <= 0 or height <= 0:
                return None
            return {
                "x": float(box.get("x", 0)),
                "y": float(box.get("y", 0)),
                "width": width,
                "height": height,
            }
        except Exception as exc:
            logger.debug(
                f"[rendered] failed to resolve hover candidate box for {selector}: {exc}"
            )
            return None


# ── Evaluator orchestration ───────────────────────────────────────────────────


def run_all_evaluators(
    raw_list: List[Dict[str, Any]],
    page_url: str,
    run_resize_text: bool = True,
    run_reflow: bool = True,
    run_text_spacing: bool = True,
    run_orientation: bool = True,
    run_hover_focus_content: bool = True,
    run_focus_not_obscured_min: bool = True,
    run_focus_not_obscured_enh: bool = True,
) -> List[Dict[str, Any]]:
    """
    Reconstruct PageSnapshot / FocusStep objects from raw dict and run all
    evaluators. Returns a flat list of RuleAuditRecord dicts (combined.py format).
    """
    from ka11y.accessibility.rendered.models import (
        PageSnapshot,
        FocusStep,
        HoverInteractionResult,
    )
    
    all_findings = []

    for raw in raw_list:
        current_url = raw.get("page_url", page_url)
        
        def _snap(key: str) -> PageSnapshot:
            d = raw.get(key, {})
            try:
                return PageSnapshot.model_validate(d)
            except Exception:
                return PageSnapshot(
                    scenario=key,
                    page_url=current_url,
                    viewport_width=1280,
                    viewport_height=720,
                )

        def _focus_steps() -> List[FocusStep]:
            steps = []
            for d in raw.get("focus_scan", []):
                try:
                    steps.append(FocusStep.model_validate(d))
                except Exception:
                    pass
            return steps

        def _hover_results() -> List[HoverInteractionResult]:
            results = []
            for d in raw.get("hover_scan", []):
                try:
                    results.append(HoverInteractionResult.model_validate(d))
                except Exception:
                    pass
            return results

        records = []
        if run_resize_text:
            from ka11y.accessibility.rendered.evaluators import evaluate_resize_text
            records.extend(evaluate_resize_text(_snap("baseline"), _snap("resize_text_200")))

        if run_reflow:
            from ka11y.accessibility.rendered.evaluators import evaluate_reflow
            records.extend(evaluate_reflow(_snap("reflow_320")))

        if run_text_spacing:
            from ka11y.accessibility.rendered.evaluators import evaluate_text_spacing
            records.extend(
                evaluate_text_spacing(
                    _snap("text_spacing_baseline"), _snap("text_spacing_override")
                )
            )

        if run_orientation:
            from ka11y.accessibility.rendered.evaluators import evaluate_orientation
            records.extend(
                evaluate_orientation(
                    _snap("orientation_portrait"), _snap("orientation_landscape")
                )
            )

        if run_hover_focus_content:
            from ka11y.accessibility.rendered.evaluators import evaluate_hover_focus_content
            records.extend(evaluate_hover_focus_content(_hover_results()))

        if run_focus_not_obscured_min:
            from ka11y.accessibility.rendered.evaluators import evaluate_focus_not_obscured_min
            records.extend(evaluate_focus_not_obscured_min(_focus_steps()))

        if run_focus_not_obscured_enh:
            from ka11y.accessibility.rendered.evaluators import evaluate_focus_not_obscured_enh
            records.extend(evaluate_focus_not_obscured_enh(_focus_steps()))
            
        all_findings.extend([r.model_dump() for r in records])

    return all_findings
