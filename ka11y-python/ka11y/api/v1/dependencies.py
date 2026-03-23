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

import re
import time
import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends
from pydantic import HttpUrl

from ka11y.utils.config_loader import load_config
from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.crawler.forms_crawler import AsyncFormCrawler
from ka11y.crawler.interactive_crawler import InteractiveElementCrawler
from ka11y.crawler.moving_content_crawler import MovingContentCrawler
from ka11y.crawler.target_size_crawler import TargetSizeCrawler
from ka11y.accessibility.rules.non_text.alttext import AltTextAccessibilityAuditor
from ka11y.accessibility.rules.forms.form_auditor import FormAccessibilityAuditor
from ka11y.accessibility.rules.input_modalities.label_in_name_auditor import (
    LabelInNameAuditor,
)
from ka11y.accessibility.rules.input_modalities.target_size_auditor import (
    TargetSizeAuditor,
)
from ka11y.accessibility.rules.timing.pause_stop_hide_auditor import (
    PauseStopHideAuditor,
)
from ka11y.crawler.text_spacing_crawler import AsyncTextSpacingCrawler
from ka11y.accessibility.rules.input_modalities.text_spacing_auditor import TextSpacingAuditor
from ka11y.api.v1.models.pipeline import PipelineRequest


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


def get_interactive_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> InteractiveElementCrawler:
    """Provide an InteractiveElementCrawler for WCAG 2.5.3 auditing."""
    return InteractiveElementCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )


def get_moving_content_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> MovingContentCrawler:
    """Provide a MovingContentCrawler for WCAG 2.2.2 auditing."""
    return MovingContentCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )


def get_label_in_name_auditor(
    output_dir: Path = Depends(get_output_dir),
) -> LabelInNameAuditor:
    """LabelInNameAuditor needs the output dir to write its CSV."""
    return LabelInNameAuditor(output_dir=str(output_dir))


def get_pause_stop_hide_auditor(
    output_dir: Path = Depends(get_output_dir),
) -> PauseStopHideAuditor:
    """PauseStopHideAuditor needs the output dir to write its CSV."""
    return PauseStopHideAuditor(output_dir=str(output_dir))


def get_target_size_crawler(
    url: str,
    max_depth: int,
    output_dir: Path = Depends(get_output_dir),
) -> TargetSizeCrawler:
    """Provide a TargetSizeCrawler for WCAG 2.5.8 auditing."""
    return TargetSizeCrawler(
        base_url=url,
        output_dir=str(output_dir),
        max_depth=max_depth,
    )


def get_target_size_auditor(
    output_dir: Path = Depends(get_output_dir),
) -> TargetSizeAuditor:
    """TargetSizeAuditor needs the output dir to write its CSV."""
    return TargetSizeAuditor(output_dir=str(output_dir))

def get_text_spacing_crawler(
    payload: PipelineRequest,
    output_dir: Path = Depends(get_output_dir),
) -> AsyncTextSpacingCrawler:
    return AsyncTextSpacingCrawler(
        base_url=str(payload.url),
        output_dir=str(output_dir),
        max_depth=payload.max_depth,
    )

def get_text_spacing_auditor(
    output_dir: Path = Depends(get_output_dir),
) -> TextSpacingAuditor:
    return TextSpacingAuditor(output_dir=str(output_dir))
