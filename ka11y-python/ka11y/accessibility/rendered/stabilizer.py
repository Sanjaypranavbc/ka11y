"""
ka11y/accessibility/rendered/stabilizer.py
==========================================
Page stabiliser: waits for a Playwright page to be fully settled before
any layout snapshot is taken.
"""

from __future__ import annotations

import asyncio
from typing import List

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="stabilizer")

_SETTLE_LOOPS = 2
_SETTLE_DELAY_MS = 300


async def stabilize(page: Page, timeout_ms: int = 10_000) -> List[str]:
    """
    Wait for the page to be fully loaded and visually settled.

    Steps (all errors are tolerated so the audit can continue):
    1. domcontentloaded
    2. load
    3. document.readyState === "complete"
    4. document.fonts.ready
    5. Short settle loops to let deferred JS finish painting

    Returns a list of degradation warning strings (empty list = clean).
    Callers may propagate these into the job's warning set.
    """
    degradations: List[str] = []

    # 1 & 2 — handled by Playwright's goto() wait_until, but we also wait
    # explicitly here in case stabilize() is called after navigation.
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except PlaywrightTimeout:
        msg = "[stabilizer] domcontentloaded timeout — continuing"
        logger.warning(msg)
        degradations.append(msg)

    try:
        await page.wait_for_load_state("load", timeout=timeout_ms)
    except PlaywrightTimeout:
        msg = "[stabilizer] load timeout — continuing"
        logger.warning(msg)
        degradations.append(msg)

    # 3 — readyState
    try:
        await page.wait_for_function(
            "document.readyState === 'complete'", timeout=timeout_ms
        )
    except PlaywrightTimeout:
        msg = "[stabilizer] readyState timeout — continuing"
        logger.warning(msg)
        degradations.append(msg)

    # 4 — fonts
    try:
        await page.evaluate("document.fonts.ready")
    except Exception:
        pass  # some pages throw on this; non-fatal

    # 5 — brief settle
    for _ in range(_SETTLE_LOOPS):
        await asyncio.sleep(_SETTLE_DELAY_MS / 1000)

    return degradations
