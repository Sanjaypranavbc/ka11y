"""
ka11y/crawler/sensory_crawler.py
=================================
Playwright-based crawler for WCAG 1.3.3 — Sensory Characteristics.

Extracts all instructional text-bearing elements from a page:
  <p>, <li>, <label>, <legend>, <button>, aria-label values,
  <span>, <div> with direct text, <a>, <td>, <th>, <caption>

Each record captures the element's text, tag, ARIA attributes,
and surrounding context so the auditor can detect instructions
that rely solely on shape, size, color, position, or sound.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel

from ka11y.crawler._ssrf_guard import install_ssrf_guard


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


class SensoryElementData(BaseModel):
    page_url: str

    # Element identity
    tag: str                          # p | li | label | legend | button | span | …
    element_id: Optional[str] = None
    element_class: Optional[str] = None

    # Text content
    text: str                         # visible inner text (trimmed)
    aria_label: Optional[str] = None  # aria-label on the element itself
    aria_labelledby: Optional[str] = None
    placeholder: Optional[str] = None # for input / textarea neighbours

    # Structural context
    role: Optional[str] = None        # ARIA role
    parent_tag: Optional[str] = None
    nearest_heading: Optional[str] = None  # closest h1-h6 ancestor text

    # Raw markup (truncated)
    html: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────


class AsyncSensoryCrawler:
    """
    Crawl one URL (depth=0 by default) and extract every text-bearing
    element needed for WCAG 1.3.3 sensory-characteristics auditing.
    """

    # Tags that typically carry user-facing instructional text
    TARGET_SELECTOR = (
        "p, li, label, legend, button, "
        "a, caption, th, td, "
        "span, div, h1, h2, h3, h4, h5, h6"
    )

    EXTRACT_JS = r"""() => {
        function outerHTML(el, max) {
            return (el && el.outerHTML) ? el.outerHTML.slice(0, max || 500) : '';
        }

        function nearestHeading(el) {
            // Walk up the DOM looking for an h1-h6 ancestor
            let cur = el.parentElement;
            while (cur && cur !== document.body) {
                if (/^H[1-6]$/.test(cur.tagName)) {
                    return (cur.innerText || '').trim().slice(0, 200);
                }
                cur = cur.parentElement;
            }
            // Fallback: previous sibling heading
            let prev = el.previousElementSibling;
            while (prev) {
                if (/^H[1-6]$/.test(prev.tagName)) {
                    return (prev.innerText || '').trim().slice(0, 200);
                }
                prev = prev.previousElementSibling;
            }
            return null;
        }

        const SELECTOR = "p, li, label, legend, button, a, caption, th, td, span, div, h1, h2, h3, h4, h5, h6";
        const elements = Array.from(document.querySelectorAll(SELECTOR));
        const results  = [];

        for (const el of elements) {
            // Only take elements with meaningful direct text OR an accessible name attribute
            const ariaLabel = (el.getAttribute('aria-label') || '').trim();
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            const rawText = (el.innerText || el.textContent || '').trim();
            
            if (!rawText && !ariaLabel && !placeholder) continue;
            if (rawText && rawText.length < 3 && !ariaLabel && !placeholder) continue;

            // For divs/spans: skip if they contain block-level children that will
            // be captured separately, to avoid massive duplication.
            if (el.tagName === 'DIV' || el.tagName === 'SPAN') {
                const hasBlockChild = Array.from(el.children).some(c =>
                    /^(P|LI|LABEL|LEGEND|BUTTON|H[1-6]|TABLE|UL|OL)$/.test(c.tagName)
                );
                if (hasBlockChild) continue;
            }

            // Skip hidden elements
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

            results.push({
                tag:               el.tagName.toLowerCase(),
                element_id:        el.id        || null,
                element_class:     el.className || null,
                text:              rawText.slice(0, 500),
                aria_label:        el.getAttribute('aria-label')       || null,
                aria_labelledby:   el.getAttribute('aria-labelledby')  || null,
                placeholder:       el.getAttribute('placeholder')      || null,
                role:              el.getAttribute('role')             || null,
                parent_tag:        el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                nearest_heading:   nearestHeading(el),
                html:              outerHTML(el, 500),
            });
        }

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url   = base_url
        self.output_dir = Path(output_dir)
        self.max_depth  = max_depth
        self.results: List[SensoryElementData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[SensoryElementData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await install_ssrf_guard(context)
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
            await page.wait_for_timeout(1500)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(SensoryElementData(page_url=url, **item))

            # Follow same-origin links for deeper crawls
            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                base_netloc = urlparse(self.base_url).netloc
                for href in links:
                    if (
                        urlparse(href).netloc == base_netloc
                        and href not in self.visited
                    ):
                        await self._crawl_page(context, href, depth + 1)

        except Exception as exc:
            print(f"[SensoryCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "sensory_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)