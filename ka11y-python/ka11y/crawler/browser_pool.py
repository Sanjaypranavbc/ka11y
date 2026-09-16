"""
ka11y/crawler/browser_pool.py
=============================
Shared Playwright Chromium pool for ka11y crawlers.

Background
----------
Historically every crawler in ka11y opened its own ``async_playwright()``
block and launched its own Chromium process (~300 MB each). Only two crawlers
remain in this tree — the universal page loader (``universal_page.py``) and
the optimized image engine (``optimized/engine.py``, CLI only) — and the
combined audit path runs entirely on this pool.

This module provides a single, bounded Chromium pool plus a
:func:`leased_context` helper so crawlers can request a fresh
``BrowserContext`` without owning the Playwright lifecycle. The pool:

* lazy-initialises a single Playwright instance per event loop;
* caps concurrent context leases via an :class:`asyncio.Semaphore` — this is
  the **one** concurrency knob for browser work (``KA11Y_MAX_BROWSER_CONTEXTS``;
  the older ``KA11Y_MAX_BROWSERS`` name is still honoured);
* reuses a single warm browser across leases — every ``leased_context`` call
  yields a brand-new ``BrowserContext`` for isolation, but they share one
  Chromium process;
* **recovers from a crashed browser**: a disconnected Chromium is dropped and
  relaunched on the next lease instead of failing every crawl until restart;
* optionally **recycles** the browser between leases when it has outgrown a
  memory cap or a lifetime cap (``KA11Y_BROWSER_MAX_MEMORY_MB`` /
  ``KA11Y_BROWSER_MAX_LIFETIME_S``; both off by default). Recycling only
  happens when no lease is active, so an in-flight crawl is never cut off;
* shuts down cleanly on :func:`shutdown`.

Usage::

    from ka11y.crawler.browser_pool import leased_context

    async with leased_context(viewport={...}, user_agent=...) as ctx:
        page = await ctx.new_page()
        ...

Reserving a slot ahead of time
------------------------------
A stage that wants "queue for a browser slot, and only *then* start its
timeout" wraps itself in :func:`reserve`::

    async with reserve():
        await asyncio.wait_for(crawl(), timeout=...)   # crawl() leases normally

Inside a reservation ``leased_context`` does not acquire the semaphore a second
time (a ``ContextVar`` marks the task, and tasks spawned inside inherit it),
so one stage holds exactly one slot no matter how it structures its leases.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import os
import time
from typing import Any, AsyncIterator, List, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Playwright,
    async_playwright,
)

from ka11y.crawler.context_factory import STEALTH_LAUNCH_ARGS, new_crawler_context

try:  # optional: memory watchdog
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

logger = logging.getLogger(__name__)


def _env_int(*names: str, default: int) -> int:
    for name in names:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            try:
                return int(raw)
            except ValueError:
                logger.warning("ignoring non-integer %s=%r", name, raw)
    return default


# Bound on concurrent context leases (one Chromium process, N contexts).
# ``KA11Y_MAX_BROWSER_CONTEXTS`` is the honest name; ``KA11Y_MAX_BROWSERS`` is
# what deployments have set historically and means the same thing;
# ``KA11Y_HEAVY_STAGE_CONCURRENCY`` used to gate a *second* semaphore in
# stages.py around the same resource and is accepted as a last fallback so
# an existing .env keeps its effective limit.
_MAX_CONTEXTS = _env_int(
    "KA11Y_MAX_BROWSER_CONTEXTS", "KA11Y_MAX_BROWSERS", "KA11Y_HEAVY_STAGE_CONCURRENCY",
    default=2,
)
# Recycle thresholds (0 = disabled). Checked only between leases.
_MAX_MEMORY_MB = _env_int("KA11Y_BROWSER_MAX_MEMORY_MB", default=0)
_MAX_LIFETIME_S = _env_int("KA11Y_BROWSER_MAX_LIFETIME_S", default=0)

# Set inside :func:`reserve` so nested leases skip the semaphore.
_reserved: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ka11y_browser_slot_reserved", default=False
)


def _chromium_rss_mb() -> float:
    """Resident memory of every Chromium child of this process, in MB.
    0.0 when psutil is unavailable."""
    if psutil is None:
        return 0.0
    try:
        me = psutil.Process(os.getpid())
        children = me.children(recursive=True)
    except Exception:  # noqa: BLE001
        return 0.0
    total = 0
    for child in children:
        try:
            name = child.name().lower()
            if "chrome" in name or "chromium" in name or "headless_shell" in name:
                total += child.memory_info().rss
        except Exception:  # noqa: BLE001
            continue
    return total / (1024 * 1024)


class BrowserPool:
    """
    Process-level Chromium pool.

    Not a class designed for inheritance — use the module-level
    :func:`get_pool` / :func:`leased_context` helpers.
    """

    def __init__(
        self,
        max_browsers: int = _MAX_CONTEXTS,
        *,
        max_memory_mb: int = _MAX_MEMORY_MB,
        max_lifetime_s: float = _MAX_LIFETIME_S,
    ) -> None:
        # ``max_browsers`` keeps its historical name for callers/tests; it is
        # the number of concurrent context leases.
        self._max_browsers = max(1, max_browsers)
        self._sema = asyncio.Semaphore(self._max_browsers)
        self._max_memory_mb = max(0, int(max_memory_mb))
        self._max_lifetime_s = max(0.0, float(max_lifetime_s))
        self._pw: Optional[Playwright] = None
        self._browsers: List[Browser] = []
        self._launched_at = 0.0
        self._generation = 0
        self._active_leases = 0
        self._init_lock = asyncio.Lock()
        # Stamp the loop the pool is bound to. Re-creating the pool when the
        # loop changes (e.g. between pytest tests) is the caller's job.
        self._loop = asyncio.get_event_loop()

    # ── introspection ─────────────────────────────────────────────────────

    @property
    def generation(self) -> int:
        """Incremented on every (re)launch; lets callers detect a restart."""
        return self._generation

    @property
    def active_leases(self) -> int:
        return self._active_leases

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def _ensure_started(self) -> None:
        if self._pw is not None:
            return
        async with self._init_lock:
            if self._pw is not None:
                return
            self._pw = await async_playwright().start()

    async def _launch(self) -> Browser:
        assert self._pw is not None
        # Stealth launch flags (AutomationControlled off, etc.) plus the
        # container-friendly ones; dedup keeps the list stable if both name
        # the same switch.
        args = list(dict.fromkeys(["--no-sandbox", *STEALTH_LAUNCH_ARGS]))
        browser = await self._pw.chromium.launch(headless=True, args=args)
        self._browsers = [browser]
        self._launched_at = time.monotonic()
        self._generation += 1
        logger.info(
            "browser pool: launched chromium %s (generation %d)",
            browser.version, self._generation,
        )
        return browser

    async def _retire(self, browser: Browser, reason: str) -> None:
        logger.warning("browser pool: retiring chromium (%s)", reason)
        self._browsers = []
        try:
            await asyncio.wait_for(browser.close(), timeout=5)
        except Exception:  # noqa: BLE001
            logger.debug("browser close raised during retire", exc_info=True)

    def _recycle_reason(self) -> Optional[str]:
        """Why the warm browser should be replaced *now*, or None. Only
        consulted when no lease is active so a running crawl is never cut."""
        if self._active_leases:
            return None
        if self._max_lifetime_s and (time.monotonic() - self._launched_at) > self._max_lifetime_s:
            return f"lifetime > {self._max_lifetime_s:.0f}s"
        if self._max_memory_mb:
            rss = _chromium_rss_mb()
            if rss > self._max_memory_mb:
                return f"rss {rss:.0f} MB > {self._max_memory_mb} MB"
        return None

    async def _acquire_browser(self) -> Browser:
        await self._ensure_started()
        assert self._pw is not None
        async with self._init_lock:
            if self._browsers:
                browser = self._browsers[0]
                if not browser.is_connected():
                    # Crash recovery: Chromium died (OOM-kill, sandbox crash,
                    # renderer wedge that took the browser process down).
                    # Drop it and relaunch instead of handing out a dead
                    # handle to every crawl until the service restarts.
                    await self._retire(browser, "disconnected")
                else:
                    reason = self._recycle_reason()
                    if reason is None:
                        return browser
                    await self._retire(browser, reason)
            return await self._launch()

    # ── leasing ───────────────────────────────────────────────────────────

    @contextlib.asynccontextmanager
    async def _slot(self) -> AsyncIterator[None]:
        """Hold one semaphore slot unless the task already reserved one."""
        if _reserved.get():
            yield
            return
        async with self._sema:
            yield

    @contextlib.asynccontextmanager
    async def reserve(self) -> AsyncIterator[None]:
        """Acquire a slot up front; leases taken inside do not acquire again.

        Lets a stage separate "waiting for a browser slot" from its own
        timeout: ``async with pool.reserve(): await wait_for(work, t)``.
        """
        if _reserved.get():
            yield
            return
        async with self._sema:
            token = _reserved.set(True)
            try:
                yield
            finally:
                _reserved.reset(token)

    @contextlib.asynccontextmanager
    async def lease_browser(self) -> AsyncIterator[Browser]:
        """
        Acquire the pool's warm ``Browser`` directly. Use this only when the
        caller needs to spawn many contexts off one browser.

        The browser is **not** closed on exit — it stays warm for subsequent
        leases. Concurrency is bounded by the same semaphore as
        :meth:`lease_context`.
        """
        async with self._slot():
            browser = await self._acquire_browser()
            self._active_leases += 1
            try:
                yield browser
            finally:
                self._active_leases -= 1

    @contextlib.asynccontextmanager
    async def lease_context(self, **context_kwargs: Any) -> AsyncIterator[BrowserContext]:
        """
        Acquire a new ``BrowserContext`` from the pool. Context is closed
        on exit. The underlying browser is **not** closed — it is reused
        for subsequent leases.

        The semaphore caps the number of contexts open at one time, so
        even cheap-context callers cannot starve the host.
        """
        async with self._slot():
            browser = await self._acquire_browser()
            context = await new_crawler_context(browser, **context_kwargs)
            self._active_leases += 1
            try:
                yield context
            finally:
                self._active_leases -= 1
                try:
                    await context.close()
                except Exception:  # noqa: BLE001
                    # A context can be torn down externally (target closed
                    # mid-eval, browser crashed). Don't mask the original
                    # exception path.
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


@contextlib.asynccontextmanager
async def reserve() -> AsyncIterator[None]:
    """Shortcut: ``async with reserve(): ...`` — see :meth:`BrowserPool.reserve`."""
    async with get_pool().reserve():
        yield


async def shutdown_pool() -> None:
    """Shutdown the module singleton. Call from FastAPI lifespan teardown."""
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.shutdown()
        _pool = None
        _pool_loop = None
