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
  • Whether it appears to be a user-agent-controlled widget (exception 3)

WCAG 2.5.8 exceptions that are detected
─────────────────────────────────────────
  inline_exception      — <a> displayed as CSS inline inside a paragraph of text
  ua_controlled_exception — native checkbox / radio whose appearance has not been
                            overridden with CSS `appearance: none`
"""

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel


class TargetSizeData(BaseModel):
    """One interactive element record, consumed by TargetSizeAuditor."""
    page_url:    str
    element_index: int
    tag:         str                      # BUTTON | A | INPUT | DIV …
    role:        Optional[str] = None
    element_id:  Optional[str] = None
    input_type:  Optional[str] = None
    accessible_name: Optional[str] = None

    # Rendered dimensions (CSS px)
    rendered_width_px:  float
    rendered_height_px: float

    # Computed CSS padding (CSS px)
    padding_top_px:    float = 0.0
    padding_bottom_px: float = 0.0
    padding_left_px:   float = 0.0
    padding_right_px:  float = 0.0

    # WCAG 2.5.8 applicability exceptions (True = rule does not apply)
    is_inline_exception:        bool = False
    is_ua_controlled_exception: bool = False

    # Pre-computed pass/fail for size (width ≥ 24 AND height ≥ 24)
    passes_size: bool = True

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
            // If appearance is still 'auto'/'checkbox'/'radio', size is UA-controlled
            const app = style.appearance || style.webkitAppearance || '';
            return !['none', 'auto'].includes(app) || app === 'auto';
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
                passes_size:                w >= MIN_PX && h >= MIN_PX,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
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

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url   = base_url
        self.output_dir = Path(output_dir)
        self.max_depth  = max_depth
        self.results: List[TargetSizeData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[TargetSizeData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            try:
                await self._crawl_page(context, self.base_url, depth=0)
            finally:
                await context.close()
                await browser.close()
        return self.results

    async def _crawl_page(self, context, url: str, depth: int):
        if url in self.visited:
            return
        self.visited.add(url)

        page = await context.new_page()
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                await page.goto(url, wait_until="commit", timeout=15_000)
            await page.wait_for_timeout(2000)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(TargetSizeData(page_url=url, **item))

            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                base_netloc = urlparse(self.base_url).netloc
                for href in links:
                    if urlparse(href).netloc == base_netloc and href not in self.visited:
                        await self._crawl_page(context, href, depth + 1)

        except Exception as exc:
            print(f"[TargetSizeCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "target_size_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)