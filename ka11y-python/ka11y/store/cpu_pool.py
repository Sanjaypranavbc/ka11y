"""
ka11y/store/cpu_pool.py
======================
Shared ProcessPoolExecutor for CPU-bound auditor work (P5).

Why
---
The CPU-heavy auditors (cosine similarity, text parsing, parts of contrast math
that aren't NumPy) run today via ``asyncio.to_thread``. Threads don't give true
parallelism for pure-Python code because of the GIL, so "concurrent" stages
serialize on one core. A process pool sidesteps the GIL: each worker is its own
interpreter.

Contract for callables submitted here
--------------------------------------
* Must be a **top-level**, importable function (picklable) — not a lambda or a
  closure, not a bound method on an object holding a browser handle.
* Args and return value must be picklable — pass plain dicts/lists, never
  Playwright pages or open file handles.

Use ``run_cpu(fn, *args)`` from async code. If the pool can't be used (e.g.
inside a worker that is itself a pool child, or pickling fails) it transparently
falls back to ``asyncio.to_thread`` so callers never have to branch.
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="store.cpu_pool")


def _default_workers() -> int:
    override = os.getenv("KA11Y_CPU_WORKERS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    return max(1, (os.cpu_count() or 2) - 1)


_pool: Optional[ProcessPoolExecutor] = None


def get_pool() -> Optional[ProcessPoolExecutor]:
    """Lazily create the shared process pool.

    Opt-in: the pool is only created when ``KA11Y_CPU_WORKERS`` is set to a
    value > 0. Unset (or ``0``) keeps the default thread path — identical to
    today's behaviour, and avoids forking under pytest. Ops enables true
    multi-core parallelism on the box by exporting e.g. ``KA11Y_CPU_WORKERS=6``.
    """
    global _pool
    raw = os.getenv("KA11Y_CPU_WORKERS")
    if not raw or raw == "0":
        return None
    if _pool is None:
        try:
            _pool = ProcessPoolExecutor(max_workers=_default_workers())
            logger.info("[cpu_pool] started with %d workers", _default_workers())
        except Exception:  # noqa: BLE001
            logger.warning("[cpu_pool] could not start; using threads", exc_info=True)
            return None
    return _pool


async def run_cpu(fn: Callable[..., Any], *args: Any) -> Any:
    """Run *fn* in the process pool (true parallelism), falling back to a thread."""
    pool = get_pool()
    if pool is None:
        return await asyncio.to_thread(fn, *args)
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(pool, fn, *args)
    except Exception as exc:  # noqa: BLE001
        # Pickling / pool-broken errors → degrade to a thread rather than fail.
        logger.warning("[cpu_pool] run_in_executor failed (%s); using thread", exc)
        return await asyncio.to_thread(fn, *args)


def shutdown_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
