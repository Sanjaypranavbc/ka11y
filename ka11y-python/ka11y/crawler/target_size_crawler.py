"""
ka11y/crawler/target_size_crawler.py
=====================================
Playwright-based crawler that measures the rendered CSS pixel dimensions
of every interactive element — used by TargetSizeAuditor (WCAG 2.5.8).

What is measured
────────────────
  • <button>
  • <a href="…">
  • <input type="submit|button|reset|image|checkbox|radio">
  • Elements with interactive ARIA roles (role="button|link|menuitem|tab|…")

For each element the crawler records:
  • Rendered bounding-box width / height (getBoundingClientRect)
  • Computed CSS padding on each side
  • Whether the element is an inline link exception (WCAG 2.5.8 exception 1)
  • Whether it appears to be a user-agent-controlled widget (exception 4)
  • Whether it qualifies for offset spacing exception (WCAG 2.5.8 exception 5)

WCAG 2.5.8 exceptions that are detected
─────────────────────────────────────────
  inline_exception      — <a> displayed as CSS inline inside a paragraph of text
  ua_controlled_exception — native checkbox / radio whose appearance has not been
                            overridden with CSS `appearance: none`
  offset_exception      — undersized targets that still have enough spacing to
                          adjacent targets based on the required offset formula
"""

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel



class TargetSizeData(BaseModel):
    """One interactive element record, consumed by TargetSizeAuditor."""

    page_url: str
    element_index: int
    tag: str  # BUTTON | A | INPUT | DIV …
    role: Optional[str] = None
    element_id: Optional[str] = None
    input_type: Optional[str] = None
    accessible_name: Optional[str] = None

    # Rendered dimensions (CSS px)
    rendered_width_px: float
    rendered_height_px: float

    # Computed CSS padding (CSS px)
    padding_top_px: float = 0.0
    padding_bottom_px: float = 0.0
    padding_left_px: float = 0.0
    padding_right_px: float = 0.0

    # WCAG 2.5.8 applicability exceptions (True = rule does not apply)
    is_inline_exception: bool = False
    is_ua_controlled_exception: bool = False
    is_offset_exception: bool = False

    # Offset exception metrics (CSS px)
    required_offset_x_px: float = 0.0
    required_offset_y_px: float = 0.0
    nearest_target_gap_x_px: Optional[float] = None
    nearest_target_gap_y_px: Optional[float] = None

    # Pre-computed pass/fail for size (width ≥ 24 AND height ≥ 24)
    passes_size: bool = True

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None

    html_snippet: str = ""


class TargetSizeCrawler:
    """
    Launches headless Chromium, navigates to base_url, and measures
    interactive element sizes at a 1440-wide viewport.
    """

    MIN_PX = 24  # WCAG 2.5.8 minimum target size

    EXTRACT_JS = r"""() => {
        const MIN_PX = 24;

        const INTERACTIVE_ROLES = new Set([
            'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
            'option', 'tab', 'treeitem', 'switch', 'checkbox', 'radio',
            'combobox', 'listbox',
        ]);

        /* ── Inline exception: <a> rendered as CSS inline inside a text block ── */
        function isInlineLink(el) {
            if (el.tagName !== 'A') return false;
            const display = window.getComputedStyle(el).display;
            if (display !== 'inline') return false;
            const parent = el.parentElement;
            if (!parent) return false;
            // Parent must have text content beyond this link itself
            const parentText = (parent.textContent || '')
                .replace(el.textContent || '', '').trim();
            return parentText.length > 0;
        }

        /* ── UA-controlled exception: native checkbox/radio without custom styling ── */
        function isUAControlled(el) {
            const tag  = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase();
            if (tag !== 'INPUT' || !['checkbox', 'radio'].includes(type)) return false;
            const style = window.getComputedStyle(el);
            // UA-controlled when appearance has NOT been overridden to 'none'.
            const app = (style.appearance || style.webkitAppearance || '').toLowerCase();
            return app !== 'none' && app !== '';
        }

        function getAccessibleName(el) {
            const tag  = el.tagName.toUpperCase();
            const type = (el.type  || '').toLowerCase();

            const lbId = el.getAttribute('aria-labelledby');
            if (lbId) {
                const parts = lbId.trim().split(/\s+/).map(id => {
                    const ref = document.getElementById(id);
                    return ref ? (ref.innerText || ref.textContent || '').trim() : '';
                }).filter(Boolean);
                if (parts.length) return parts.join(' ');
            }

            const aria = el.getAttribute('aria-label');
            if (aria && aria.trim()) return aria.trim();

            if (tag === 'INPUT' && ['submit', 'button', 'reset'].includes(type)) {
                return (el.value || '').trim();
            }
            if (tag === 'INPUT' && type === 'image') {
                return (el.getAttribute('alt') || '').trim();
            }

            const title = el.getAttribute('title');
            if (title && title.trim()) return title.trim();

            return ((el.innerText || el.textContent || '')).trim().slice(0, 100);
        }

        const seen    = new WeakSet();
        const results = [];

        function addElement(el) {
            if (seen.has(el)) return;
            seen.add(el);

            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;

            const w = rect.width;
            const h = rect.height;

            results.push({
                element_index:              results.length,
                tag:                        el.tagName.toUpperCase(),
                role:                       el.getAttribute('role') || null,
                element_id:                 el.id                   || null,
                input_type:                 el.type                 || null,
                accessible_name:            getAccessibleName(el)   || null,
                rendered_width_px:          Math.round(w  * 100) / 100,
                rendered_height_px:         Math.round(h  * 100) / 100,
                padding_top_px:             parseFloat(style.paddingTop)    || 0,
                padding_bottom_px:          parseFloat(style.paddingBottom) || 0,
                padding_left_px:            parseFloat(style.paddingLeft)   || 0,
                padding_right_px:           parseFloat(style.paddingRight)  || 0,
                is_inline_exception:        isInlineLink(el),
                is_ua_controlled_exception: isUAControlled(el),
                is_offset_exception:        false,
                required_offset_x_px:       0,
                required_offset_y_px:       0,
                nearest_target_gap_x_px:    null,
                nearest_target_gap_y_px:    null,
                passes_size:                w >= MIN_PX && h >= MIN_PX,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
                left:                       Math.round(rect.left * 100) / 100,
                top:                        Math.round(rect.top * 100) / 100,
                right:                      Math.round(rect.right * 100) / 100,
                bottom:                     Math.round(rect.bottom * 100) / 100,
            });
        }

        // Native interactive elements
        document.querySelectorAll(
            'button, a[href],' +
            ' input[type="submit"], input[type="button"],' +
            ' input[type="reset"], input[type="image"],' +
            ' input[type="checkbox"], input[type="radio"]'
        ).forEach(addElement);

        // ARIA-role elements on non-native tags
        document.querySelectorAll('[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            const tag = el.tagName.toUpperCase();
            if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(tag)) return;
            addElement(el);
        });

        // Offset exception (WCAG 2.5.8 E5):
        // For undersized targets, if there is enough clear spacing around the
        // target (inflated by required offsets), the size requirement can be
        // treated as not applicable.
        for (let i = 0; i < results.length; i++) {
            const cur = results[i];
            const reqX = Math.max(0, (MIN_PX - cur.rendered_width_px) / 2);
            const reqY = Math.max(0, (MIN_PX - cur.rendered_height_px) / 2);
            let minGapX = Number.POSITIVE_INFINITY;
            let minGapY = Number.POSITIVE_INFINITY;
            let intersectsInflated = false;

            const inflated = {
                left: cur.left - reqX,
                right: cur.right + reqX,
                top: cur.top - reqY,
                bottom: cur.bottom + reqY,
            };

            for (let j = 0; j < results.length; j++) {
                if (i === j) continue;
                const other = results[j];

                const hGap = other.left >= cur.right
                    ? other.left - cur.right
                    : (cur.left >= other.right ? cur.left - other.right : 0);
                const vGap = other.top >= cur.bottom
                    ? other.top - cur.bottom
                    : (cur.top >= other.bottom ? cur.top - other.bottom : 0);

                if (hGap < minGapX) minGapX = hGap;
                if (vGap < minGapY) minGapY = vGap;

                if (reqX > 0 || reqY > 0) {
                    const intersects = !(
                        other.right <= inflated.left ||
                        other.left >= inflated.right ||
                        other.bottom <= inflated.top ||
                        other.top >= inflated.bottom
                    );
                    if (intersects) intersectsInflated = true;
                }
            }

            cur.required_offset_x_px = Math.round(reqX * 100) / 100;
            cur.required_offset_y_px = Math.round(reqY * 100) / 100;
            cur.nearest_target_gap_x_px = Number.isFinite(minGapX)
                ? Math.round(minGapX * 100) / 100
                : null;
            cur.nearest_target_gap_y_px = Number.isFinite(minGapY)
                ? Math.round(minGapY * 100) / 100
                : null;
            cur.is_offset_exception = (reqX > 0 || reqY > 0) && !intersectsInflated;
        }

        return results.map(({ left, top, right, bottom, ...rest }) => rest);
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[TargetSizeData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[TargetSizeData]:
        from ka11y.crawler.browser_pool import leased_context
        from ka11y.crawler.bfs import bounded_bfs
        from ka11y.crawler.policy import CrawlPolicy

        policy = CrawlPolicy(max_depth=self.max_depth)

        async with leased_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        ) as context:
            await bounded_bfs(
                context=context,
                base_url=self.base_url,
                policy=policy,
                visit=self._visit_page,
                log_prefix="target_size_crawler",
            )
        return self.results

    async def _visit_page(self, page, url: str, depth: int) -> list:
        """Extract target-size data from one page; return hrefs found.

        Traversal, visited set, global page budget, and exact-hostname filter
        are owned by :func:`bounded_bfs`."""
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            await page.goto(url, wait_until="commit", timeout=15_000)
        await page.wait_for_timeout(2000)

        raw: list = await page.evaluate(self.EXTRACT_JS)
        for item in raw:
            self.results.append(TargetSizeData(page_url=url, **item))

        return await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href)"
        )

    def save_raw_json(self) -> str:
        path = self.output_dir / "target_size_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
