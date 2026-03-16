"""
ka11y/api/dependencies.py
=========================
FastAPI dependency providers for the ka11y pipeline.

Injection graph
───────────────
  get_config            → raw CONFIG dict from config_loader
  get_output_dir        → derives domain/timestamped output dir from URL + CONFIG
  get_image_crawler     → AsyncImageCrawler, bound to output_dir
  get_form_crawler      → AsyncFormCrawler,  bound to output_dir
  get_alt_text_auditor  → AltTextAccessibilityAuditor (stateless)
  get_form_auditor      → FormAccessibilityAuditor,   bound to output_dir
"""

import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends
from pydantic import HttpUrl

from ka11y.utils.config_loader import load_config
from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.crawler.forms_crawler import AsyncFormCrawler
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor


# ── 1. Config ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_config() -> dict:
    """Load and cache the YAML/JSON config once per process."""
    return load_config()


# ── 2. Output directory ───────────────────────────────────────────────────────

def get_output_dir(
    url: str,
    config: dict = Depends(get_config),
) -> Path:
    """
    Build a per-run output directory:
        <base_out>/<domain>_<MMDD_HHMM>/

    Both crawl and forms routes call this with the same `url`, so they
    share the exact same directory when composed in a single request.
    """
    base_out = config["input"]["output_dir"]
    domain   = urlparse(url).netloc.replace("www.", "").replace(".", "_")
    ts       = time.strftime("%m%d_%H%M")
    path     = Path(f"{base_out}/{domain}_{ts}")
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── 3. Crawlers ───────────────────────────────────────────────────────────────

def get_image_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> AsyncImageCrawler:
    """Provide an AsyncImageCrawler scoped to this request's output dir."""
    return AsyncImageCrawler(base_url=url, max_depth=max_depth)


def get_form_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> AsyncFormCrawler:
    """Provide an AsyncFormCrawler scoped to this request's output dir."""
    return AsyncFormCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )


# ── 4. Auditors ───────────────────────────────────────────────────────────────

def get_alt_text_auditor() -> AltTextAccessibilityAuditor:
    """AltTextAccessibilityAuditor is stateless — new instance per request."""
    return AltTextAccessibilityAuditor()


def get_form_auditor(
    output_dir: Path = Depends(get_output_dir),
) -> FormAccessibilityAuditor:
    """FormAccessibilityAuditor needs the output dir to write its CSV."""
    return FormAccessibilityAuditor(output_dir=str(output_dir))