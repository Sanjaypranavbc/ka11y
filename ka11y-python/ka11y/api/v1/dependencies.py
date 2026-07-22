"""
ka11y/api/dependencies.py
=========================
FastAPI dependency providers for the ka11y pipeline.

Injection graph
───────────────
  get_config            → raw CONFIG dict from config_loader
  get_output_dir        → derives domain/timestamped output dir from URL + CONFIG
  get_image_crawler     → AsyncImageCrawler, bound to output_dir
  get_alt_text_auditor  → AltTextAccessibilityAuditor (stateless)
"""

from __future__ import annotations

import re
import time
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends

from ka11y.utils.config_loader import load_config

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # The optimized crawler is a drop-in for AsyncImageCrawler (same interface).
    from ka11y.crawler.optimized.optimized_crawler import OptimizedImageCrawler as AsyncImageCrawler
    from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor

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
        <base_out>/<domain>_<MMDD_HHMM>_<uid>/

    Security: hostname is validated against a strict allowlist pattern and
    the resolved path is checked to remain inside base_out (prevents traversal).
    A short UUID suffix prevents timestamp collisions for concurrent requests.
    """
    base_out = Path(config["input"]["output_dir"]).resolve()

    netloc = urlparse(url).netloc
    # Strip port if present (e.g. "example.com:8080" → "example.com")
    hostname = netloc.split(":")[0]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", hostname):
        raise ValueError(f"Invalid URL hostname for output directory: {hostname!r}")

    safe_domain = hostname.replace("www.", "").replace(".", "_")
    ts = time.strftime("%m%d_%H%M")
    uid = uuid.uuid4().hex[:8]
    path = (base_out / f"{safe_domain}_{ts}_{uid}").resolve()

    # Canonical path guard — must stay inside base_out
    if not str(path).startswith(str(base_out)):
        raise ValueError("Resolved output directory escapes the base output path.")

    path.mkdir(parents=True, exist_ok=True)
    return path


# ── 3. Crawlers ───────────────────────────────────────────────────────────────


def get_image_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> AsyncImageCrawler:
    """Provide an image crawler scoped to this request's output dir.
    Uses the optimized crawler engine (drop-in for AsyncImageCrawler)."""
    from ka11y.crawler.optimized.optimized_crawler import OptimizedImageCrawler

    crawler = OptimizedImageCrawler(base_url=url, max_depth=max_depth)
    crawler.output_dir = str(output_dir)
    Path(crawler.output_dir).mkdir(parents=True, exist_ok=True)
    return crawler


# ── 4. Auditors ───────────────────────────────────────────────────────────────


def get_alt_text_auditor() -> AltTextAccessibilityAuditor:
    """AltTextAccessibilityAuditor is stateless — new instance per request."""
    from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor

    return AltTextAccessibilityAuditor()
