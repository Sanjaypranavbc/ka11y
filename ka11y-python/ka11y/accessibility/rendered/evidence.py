"""
ka11y/accessibility/rendered/evidence.py
=========================================
Optional screenshot-based evidence capture.
Evidence is for internal debugging only — it does NOT affect the public API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Page

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="evidence")


async def capture_screenshot(
    page: Page,
    output_dir: Path,
    name: str,
    full_page: bool = True,
) -> Optional[Path]:
    """Save a full-page screenshot. Returns the path or None on error."""
    try:
        path = output_dir / f"{name}.png"
        await page.screenshot(path=str(path), full_page=full_page)
        return path
    except Exception as exc:
        logger.warning(f"[evidence] screenshot '{name}' failed: {exc}")
        return None


def save_raw_json(output_dir: Path, name: str, data: Any) -> Optional[Path]:
    """Save arbitrary data as JSON. Returns the path or None on error."""
    try:
        path = output_dir / f"{name}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        return path
    except Exception as exc:
        logger.warning(f"[evidence] save_raw_json '{name}' failed: {exc}")
        return None
