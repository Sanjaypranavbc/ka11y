"""
ka11y/crawler/browser_pool.py
=============================
Shared Playwright Chromium pool for ka11y crawlers.

Background
----------
Sprint 2 (#9): each of the ten ka11y crawlers — image, media, sensory,
forms, target-size, text-spacing, rendered-layout, interactive,
moving-content, universal — historically opened its own
``async_playwright()`` block and launched its own Chromium process. For
a single audit URL that is **five-to-ten** Chromium processes
(~300 MB each) running serially or in parallel depending on the stage.

This module provides a single, bounded Chromium pool plus a
:func:`leased_context` helper so crawlers can request a fresh
``BrowserContext`` without owning the Playwright lifecycle. The pool:

* lazy-initialises a single Playwright instance per event loop;
* caps concurrent browsers via an :class:`asyncio.Semaphore`;
* reuses a single warm browser across leases by default — every
  ``leased_context`` call yields a brand-new ``BrowserContext`` for
  isolation, but they share one Chromium process;
* shuts down cleanly on :func:`shutdown`.

Migration is incremental: a crawler can opt in by replacing its
``async with async_playwright() ...`` block with::

    from ka11y.crawler.browser_pool import leased_context

    async with leased_context(viewport={...}, user_agent=...) as ctx:
        page = await ctx.new_page()
        ...

Crawlers not yet migrated keep their per-call browser launch; both
patterns coexist.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any, AsyncIterator, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from ka11y.crawler.context_factory import new_crawler_context

logger = logging.getLogger(__name__)


# Bound on concurrent Chromium processes (not contexts). Contexts are
# cheap; processes are not. Tune via env.
_MAX_BROWSERS = int(os.environ.get("KA11Y_MAX_BROWSERS", "2"))


class BrowserPool:
    """
    Process-level Chromium pool.

    Not a class designed for inheritance — use the module-level
    :func:`get_pool` / :func:`leased_context` helpers.
    """

    def __init__(self, max_browsers: int = _MAX_BROWSERS) -> None:
        self._max_browsers = max(1, max_browsers)
        self._sema = asyncio.Semaphore(self._max_browsers)
        self._pw: Optional[Playwright] = None
        self._browsers: List[Browser] = []
        self._init_lock = asyncio.Lock()
        # Stamp the loop the pool is bound to. Re-creating the pool when the
        # loop changes (e.g. between pytest tests) is the caller's job.
        self._loop = asyncio.get_event_loop()

    async def _ensure_started(self) -> None:
        if self._pw is not None:
            return
        async with self._init_lock:
            if self._pw is not None:
                return
            self._pw = await async_playwright().start()

    async def _acquire_browser(self) -> Browser:
        await self._ensure_started()
        assert self._pw is not None
        # Reuse a warm browser if one exists; otherwise launch.
        if self._browsers:
            return self._browsers[0]
        browser = await self._pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._browsers.append(browser)
        return browser

    @contextlib.asynccontextmanager
    async def lease_browser(self) -> AsyncIterator[Browser]:
        """
        Acquire the pool's warm ``Browser`` directly. Use this only when the
        caller needs to spawn many contexts off one browser (e.g. the
        rendered-layout crawler fans out 7 viewport contexts in parallel).

        The browser is **not** closed on exit — it stays warm for subsequent
        leases. Concurrency is bounded by the same semaphore as
        :meth:`lease_context`.
        """
        async with self._sema:
            browser = await self._acquire_browser()
            yield browser

    @contextlib.asynccontextmanager
    async def lease_context(self, **context_kwargs: Any) -> AsyncIterator[BrowserContext]:
        """
        Acquire a new ``BrowserContext`` from the pool. Context is closed
        on exit. The underlying browser is **not** closed — it is reused
        for subsequent leases.

        The semaphore caps the number of contexts open at one time, so
        even cheap-context callers cannot starve the host.
        """
        async with self._sema:
            browser = await self._acquire_browser()
            context = await new_crawler_context(browser, **context_kwargs)
            try:
                yield context
            finally:
                try:
                    await context.close()
                except Exception:  # noqa: BLE001
                    # A context can be torn down externally (target closed
                    # mid-eval). Don't mask the original exception path.
                    logger.debug("context close raised on lease exit", exc_info=True)

    async def shutdown(self) -> None:
        """Close all browsers and stop Playwright. Idempotent."""
        for b in self._browsers:
            try:
                await b.close()
            except Exception:  # noqa: BLE001
                logger.debug("browser close raised", exc_info=True)
        self._browsers.clear()
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:  # noqa: BLE001
                logger.debug("playwright stop raised", exc_info=True)
            self._pw = None


# ── Module-level lazy singleton, per event loop ──────────────────────────────

_pool: Optional[BrowserPool] = None
_pool_loop: Any = None


def get_pool() -> BrowserPool:
    """Return the per-event-loop ``BrowserPool`` singleton, lazily creating it.

    asyncio primitives are bound to the loop they were created in. Tests that
    create a fresh event loop per case (and any future server that re-creates
    the loop) get a fresh pool automatically.
    """
    global _pool, _pool_loop
    current = asyncio.get_event_loop()
    if _pool is None or _pool_loop is not current:
        _pool = BrowserPool()
        _pool_loop = current
    return _pool


@contextlib.asynccontextmanager
async def leased_context(**context_kwargs: Any) -> AsyncIterator[BrowserContext]:
    """Shortcut: ``async with leased_context(...) as ctx:``"""
    async with get_pool().lease_context(**context_kwargs) as ctx:
        yield ctx


@contextlib.asynccontextmanager
async def leased_browser() -> AsyncIterator[Browser]:
    """Shortcut: ``async with leased_browser() as browser:``"""
    async with get_pool().lease_browser() as browser:
        yield browser


async def shutdown_pool() -> None:
    """Shutdown the module singleton. Call from FastAPI lifespan teardown."""
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
        _pool_loop = None
