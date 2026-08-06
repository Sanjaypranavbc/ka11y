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


import csv
from datetime import datetime
from pydantic import BaseModel, Field


class CrawlSummary(BaseModel):
    total_images: int = 0
    informative: int = 0
    decorative: int = 0
    functional: int = 0
    complex: int = 0
    text_images: int = 0
    functional_buttons: int = 0
    functional_icons: int = 0
    functional_logos: int = 0
    functional_images: int = 0
    pages_crawled: int = 0


class CrawlReport(BaseModel):
    base_url: str
    crawl_date: str
    summary: CrawlSummary
    sub_type_breakdown: dict[str, int] = Field(default_factory=dict)
    images: List[ImageData] = Field(default_factory=list)


class OptimizedImageCrawler:
    def __init__(
        self,
        base_url: str,
        max_depth: int,
        max_pages: int | None = None,
        internal_links: bool = True,
        job_id: str | None = None,
        output_dir: str | Path | None = None,
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

        if output_dir is not None:
            # Caller (e.g. the combined-audit pipeline) already owns a
            # per-job output directory — write into it directly instead of
            # inventing a second, disconnected one. Without this, every
            # audit split its artifacts across two sibling directories: this
            # crawler's own `<domain>_<timestamp>` (images, OCR, metadata)
            # and the job's real `<domain>_<timestamp>_<job_id>_combined`
            # (reports) — and since the self-generated name has no job_id,
            # concurrent same-domain jobs within the same minute could even
            # collide.
            self.output_dir = str(output_dir)
        else:
            base_out = CONFIG["input"]["output_dir"]
            domain = urlparse(base_url).netloc.replace("www.", "").replace(".", "_")
            timestamp = time.strftime("%m%d_%H%M")
            self.output_dir = f"{base_out}/{domain}_{timestamp}"
        self._create_directories()

    def _create_directories(self) -> None:
        base = Path(self.output_dir)
        dirs = [base] + [base / sub for sub in CONFIG.get("directories", [])]
        dirs.append(base / "metadata")
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    async def crawl_page(self, discovered_urls: List[str] | None = None) -> None:
        out = Path(self.output_dir)
        self._create_directories()
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

        if not self.visited_urls:
            raise ImageCrawlerNavigationError(
                code="zero_pages_crawled",
                url=self.base_url,
                host=urlparse(self.base_url).hostname,
                original_message="Crawl budget or navigation failures resulted in 0 pages being reached.",
                attempts=1,
            )

    def save_results(self) -> None:
        """Persist images_data, images_report.json, and images_with_alt_text.csv matching pranav-v2."""
        meta = Path(self.output_dir) / "metadata"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "images_data.json").write_text(
            json.dumps([i.model_dump() for i in self.images_data], indent=2),
            encoding="utf-8",
        )

        summary = CrawlSummary(pages_crawled=len(self.visited_urls))
        sub_breakdown: dict[str, int] = {}

        for img in self.images_data:
            summary.total_images += 1
            cls = img.classification
            if cls == "informative":
                summary.informative += 1
            elif cls == "decorative":
                summary.decorative += 1
            elif cls == "functional":
                summary.functional += 1
                if img.sub_type == "buttons":
                    summary.functional_buttons += 1
                elif img.sub_type == "icons":
                    summary.functional_icons += 1
                elif img.sub_type == "logos":
                    summary.functional_logos += 1
                else:
                    summary.functional_images += 1
            elif cls == "complex":
                summary.complex += 1
            if img.is_text_image:
                summary.text_images += 1
            key = f"{cls}/{img.sub_type}" if img.sub_type else cls
            sub_breakdown[key] = sub_breakdown.get(key, 0) + 1

        report = CrawlReport(
            base_url=self.base_url,
            crawl_date=datetime.now().isoformat(),
            summary=summary,
            sub_type_breakdown=sub_breakdown,
            images=self.images_data,
        )

        report_path = Path(self.output_dir) / "images_report.json"
        report_path.write_text(
            json.dumps(report.model_dump(), indent=2),
            encoding="utf-8",
        )

        self._export_csv()

    def _export_csv(self) -> None:
        if not self.images_data:
            return
        csv_path = Path(self.output_dir) / "images_with_alt_text.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "src",
                    "alt_text",
                    "title",
                    "classification",
                    "sub_type",
                    "is_functional",
                    "is_decorative",
                    "is_complex",
                    "is_logo",
                    "is_icon",
                    "is_button",
                    "screenshot_path",
                ],
            )
            w.writeheader()
            for img in self.images_data:
                w.writerow(
                    {
                        "src": img.src,
                        "alt_text": img.alt_text if img.alt_text is not None else "",
                        "title": img.title,
                        "classification": img.classification,
                        "sub_type": img.sub_type,
                        "is_functional": img.is_functional,
                        "is_decorative": img.is_decorative,
                        "is_complex": img.is_complex,
                        "is_logo": img.is_logo,
                        "is_icon": img.is_icon,
                        "is_button": img.is_button,
                        "screenshot_path": img.screenshot_path,
                    }
                )

class ImageCrawlerNavigationError(RuntimeError):
    """Raised when the image crawler cannot resolve or load the target page."""

    def __init__(
        self,
        *,
        code: str,
        url: str,
        host: str | None,
        original_message: str,
        attempts: int,
    ) -> None:
        self.code = code
        self.url = url
        self.host = host
        self.original_message = original_message
        self.attempts = attempts
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        host_part = f" host={self.host}" if self.host else ""
        if self.code == "dns_resolution_failed":
            return (
                f"dns_resolution_failed{host_part} url={self.url}; image crawl could not "
                f"resolve the hostname after {self.attempts} attempt(s), so OCR and "
                f"image-audit checks were skipped. Original error: {self.original_message}"
            )
        return (
            f"page_navigation_failed{host_part} url={self.url}; image crawl could not load "
            f"the page after {self.attempts} attempt(s), so OCR and image-audit checks were "
            f"skipped. Original error: {self.original_message}"
        )
