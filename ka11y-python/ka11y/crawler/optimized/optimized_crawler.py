"""
ka11y/crawler/optimized/optimized_crawler.py
============================================
Drop-in replacement for ``AsyncImageCrawler`` backed by the hardened
"optimized" crawler engine (one browser + context pool, crash-recovery, cookie
rejection, SSRF guard, classification, overlay-screenshot-vs-download asset
capture, 1.2.1 transcript context).

It exposes the exact surface the existing pipeline uses — ``crawl_page()``,
``save_results()``, ``images_data``, ``images_metadata``, ``visited_urls``,
``page_langs``, ``output_dir`` — so the OCR / audit / report stages are used
unchanged. Internally it runs the engine into a private ``_raw`` sub-directory
of raw per-page JSON, then the adapter converts those facts into ``ImageData``
and copies each captured pixel file into ``output_dir`` for OCR correlation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import urlparse

from ka11y.utils.config_loader import load_config
from ka11y.crawler.models import ImageData, ImageMetadata
from ka11y.crawler.optimized.engine import Crawler as _Engine
from ka11y.crawler.optimized.adapter import build_image_data

CONFIG = load_config()


class OptimizedImageCrawler:
    def __init__(
        self,
        base_url: str,
        max_depth: int,
        max_pages: int | None = None,
        internal_links: bool = True,
        job_id: str | None = None,
    ) -> None:
        self.base_url = base_url
        self.max_depth = max_depth
        self.max_pages = (
            max_pages if max_pages is not None
            else CONFIG.get("crawler", {}).get("max_pages", 50)
        )
        self.internal_links = internal_links
        self.job_id = job_id

        self.images_data: List[ImageData] = []
        self.images_metadata: List[ImageMetadata] = []
        self.visited_urls: Set[str] = set()
        self.page_langs: Dict[str, str] = {}

        base_out = CONFIG["input"]["output_dir"]
        domain = urlparse(base_url).netloc.replace("www.", "").replace(".", "_")
        timestamp = time.strftime("%m%d_%H%M")
        self.output_dir = f"{base_out}/{domain}_{timestamp}"

    async def crawl_page(self, discovered_urls: List[str] | None = None) -> None:
        out = Path(self.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        raw = out / "_raw"

        crawler_cfg = CONFIG.get("crawler", {})
        if discovered_urls:
            # Honor the pipeline's shared page list: crawl exactly those pages.
            depth, seeds = 0, list(discovered_urls)
            max_pages = max(self.max_pages, len(seeds))
        else:
            depth, seeds = self.max_depth, None
            max_pages = self.max_pages

        engine = _Engine(
            seed_url=self.base_url,
            max_depth=depth,
            max_pages=max_pages,
            out_dir=raw,
            concurrency=crawler_cfg.get("concurrency", 4),
            delay=crawler_cfg.get("delay", 1.0),
            seed_urls=seeds,
        )
        await engine.run()

        self.images_data, self.page_langs, self.visited_urls = build_image_data(
            raw, out
        )

    def save_results(self) -> None:
        """Persist images_data as a metadata sidecar. The OCR/audit stages work
        off the in-memory images_data + the copied files, so this is best-effort
        provenance, not a pipeline dependency."""
        meta = Path(self.output_dir) / "metadata"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "images_data.json").write_text(
            json.dumps([i.model_dump() for i in self.images_data], indent=2),
            encoding="utf-8",
        )
