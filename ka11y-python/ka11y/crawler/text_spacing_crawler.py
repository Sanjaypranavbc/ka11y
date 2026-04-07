"""
ka11y/crawler/text_spacing_crawler.py
=====================================

Extract DOM elements relevant for WCAG 1.4.12 (Text Spacing)

Focus:
  • Fixed height containers
  • Overflow restrictions
  • Text-heavy elements
"""

import asyncio
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel

from ka11y.crawler._ssrf_guard import install_ssrf_guard
from ka11y.crawler.universal_page import navigate_with_retry

# ─────────────────────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────────────────────


class TextSpacingData(BaseModel):
    page_url: str
    element_index: int

    tag: str
    element_id: Optional[str]
    class_name: Optional[str]

    text_length: int
    text_preview: Optional[str]

    height: Optional[str]
    min_height: Optional[str]
    overflow: Optional[str]

    has_fixed_height: bool
    has_overflow_hidden: bool

    html_snippet: str
    is_clipped: bool


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────


class AsyncTextSpacingCrawler:
    # This crawler performs STATIC structural analysis only (fixed-height + overflow
    # detection without applying spacing overrides).  The rendered spacing-override
    # test (applying WCAG 1.4.12 CSS and diffing snapshots) is handled by
    # RenderedLayoutCrawler + evaluators/text_spacing.py.

    EXTRACT_JS = r"""() => {
    const results = [];
    let index = 0;

    const ignoredTags = ["html","head","body","script","style","img","svg","canvas"];

    const all = document.querySelectorAll("*");

    for (const el of all) {

        const tag = el.tagName.toLowerCase();
        if (ignoredTags.includes(tag)) continue;

        const style = window.getComputedStyle(el);

        // ✅ Only consider block-like elements (important)
        const display = style.display;
        const isBlockLike = ["block", "inline-block", "flex", "grid"].includes(display);
        if (!isBlockLike) continue;

        const text = (el.innerText || "").trim();
        const textLength = text.length;

        // ✅ Ignore low-text elements
        if (textLength < 20) continue;

        const height = style.height;
        const minHeight = style.minHeight;
        const overflow = style.overflow;

        const hasFixedHeight =
            height &&
            height !== "auto" &&
            /^\d+(\.\d+)?px$/.test(height);

        const hasOverflowHidden =
            overflow === "hidden" || overflow === "clip";

        // ✅ Only treat clipping as relevant if overflow is restricted
        const isClipped =
            (hasOverflowHidden && el.scrollHeight > el.clientHeight) ||
            (hasOverflowHidden && el.scrollWidth > el.clientWidth);

        results.push({
            element_index: index++,
            tag,
            element_id: el.id || null,
            class_name: el.className || null,

            text_length: textLength,
            text_preview: text.slice(0, 150),

            height,
            min_height: minHeight,
            overflow,

            has_fixed_height: hasFixedHeight,
            has_overflow_hidden: hasOverflowHidden,
            is_clipped: isClipped,

            html_snippet: el.outerHTML.slice(0, 400)
        });
    }

    return results;
}"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[TextSpacingData] = []
        self.visited = set()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[TextSpacingData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            await install_ssrf_guard(context)  # Bug 1 fix

            try:
                await self._crawl_page(context, self.base_url, 0)
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
            await navigate_with_retry(page, url)
            await page.wait_for_timeout(1_000)  # let JS populate text nodes

            raw = await page.evaluate(self.EXTRACT_JS)

            for item in raw:
                self.results.append(TextSpacingData(page_url=url, **item))

            # Depth crawl
            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )

                base_netloc = urlparse(self.base_url).netloc

                for href in links:
                    if urlparse(href).netloc == base_netloc:
                        await self._crawl_page(context, href, depth + 1)

        except Exception as e:
            print(f"[TextSpacingCrawler] Error: {e}")

        finally:
            await page.close()

    @classmethod
    def from_snapshot(cls, snapshot_text_spacing: list, page_url: str, output_dir: str) -> "AsyncTextSpacingCrawler":
        """Populate from a pre-crawled PageSnapshot instead of launching a browser."""
        instance = cls.__new__(cls)
        instance.base_url = page_url
        instance.output_dir = Path(output_dir)
        instance.max_depth = 0
        instance.visited = {page_url}
        instance.output_dir.mkdir(parents=True, exist_ok=True)
        from ka11y.crawler.text_spacing_crawler import TextSpacingData
        instance.results = [TextSpacingData(page_url=page_url, **item) for item in snapshot_text_spacing]
        return instance

    def save_json(self):
        import json

        path = self.output_dir / "text_spacing_raw.json"
        with open(path, "w") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)

        print(f"[TextSpacingCrawler] Saved → {path}")
        return str(path)
