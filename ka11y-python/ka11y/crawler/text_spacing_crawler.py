"""
ka11y/crawler/text_spacing_crawler.py
=====================================

Extract DOM elements relevant for WCAG 1.4.12 (Text Spacing)

Focus:
  • Fixed height containers
  • Overflow restrictions
  • Text-heavy elements
"""

from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel


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

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None

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
        from ka11y.crawler.browser_pool import leased_context
        from ka11y.crawler.bfs import bounded_bfs
        from ka11y.crawler.policy import CrawlPolicy

        policy = CrawlPolicy(max_depth=self.max_depth)

        async with leased_context(
            viewport={"width": 1440, "height": 900},
        ) as context:
            await bounded_bfs(
                context=context,
                base_url=self.base_url,
                policy=policy,
                visit=self._visit_page,
                log_prefix="text_spacing_crawler",
            )

        return self.results

    async def _visit_page(self, page, url: str, depth: int) -> list:
        """Extract text-spacing data from one page; return hrefs found.

        :func:`bounded_bfs` owns traversal, the visited set, the global page
        budget, and the exact-hostname filter (the prior recursion had no page
        budget and re-followed links it had already queued)."""
        await page.goto(url, wait_until="domcontentloaded")

        raw = await page.evaluate(self.EXTRACT_JS)
        for item in raw:
            self.results.append(TextSpacingData(page_url=url, **item))

        return await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href)"
        )

    def save_json(self):
        import json

        path = self.output_dir / "text_spacing_raw.json"
        with open(path, "w") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)

        print(f"[TextSpacingCrawler] Saved → {path}")
        return str(path)
