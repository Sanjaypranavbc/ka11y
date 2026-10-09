"""
ka11y/worker/concurrency.py
===========================
Bounded concurrency for the worker, on ``asyncio.Semaphore``.

The rule that matters: **take the slot first, then ask SQS for a message.**
A message received without a slot to run it sits in memory while its
visibility timeout counts down; when the timeout lapses SQS hands the same
message to another consumer and the audit runs twice. So the poll loop
acquires one slot (blocking until an audit finishes), grabs whatever other
slots are free without blocking, and receives at most that many messages.

  WORKER_MAX_CONCURRENCY   slots (default 2; one Chromium-heavy audit each)
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="worker.concurrency")

DEFAULT_MAX_CONCURRENCY = 2


def max_concurrency_from_env() -> int:
    raw = os.getenv("WORKER_MAX_CONCURRENCY", "").strip()
    if not raw:
        return DEFAULT_MAX_CONCURRENCY
    try:
        value = int(raw)
    except ValueError:
        logger.warning("[worker] WORKER_MAX_CONCURRENCY=%r is not an integer; using %d", raw, DEFAULT_MAX_CONCURRENCY)
        return DEFAULT_MAX_CONCURRENCY
    if value < 1:
        logger.warning("[worker] WORKER_MAX_CONCURRENCY=%d is below 1; using 1", value)
        return 1
    return value


class ConcurrencyLimiter:
    """``asyncio.Semaphore`` plus an active-slot counter and an idle condition.

    Use from a single event loop. ``acquire`` blocks until a slot is free;
    ``acquire_available`` takes up to *n* more slots without ever blocking;
    ``release`` must be called exactly once per acquired slot (the worker does
    so in a ``finally``)."""

    def __init__(self, max_concurrency: Optional[int] = None) -> None:
        self.max_concurrency = int(max_concurrency or max_concurrency_from_env())
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        self._sem = asyncio.Semaphore(self.max_concurrency)
        self._active = 0
        self._peak = 0
        self._idle = asyncio.Condition()

    # ── introspection ───────────────────────────────────────────────────────

    @property
    def active(self) -> int:
        """Slots currently held."""
        return self._active

    @property
    def free_slots(self) -> int:
        return self.max_concurrency - self._active

    @property
    def peak(self) -> int:
        """Highest number of slots held at once since construction (tests)."""
        return self._peak

    # ── acquire / release ───────────────────────────────────────────────────

    async def acquire(self) -> None:
        """Wait for one slot."""
        await self._sem.acquire()
        self._took()

    async def acquire_available(self, limit: int) -> int:
        """Take up to *limit* slots that are free right now. Never blocks.
        Returns how many were taken."""
        taken = 0
        while taken < limit and self.free_slots > 0:
            # free_slots > 0 ⇒ the semaphore has a permit, so this returns at once.
            await self._sem.acquire()
            self._took()
            taken += 1
        return taken

    def _took(self) -> None:
        self._active += 1
        self._peak = max(self._peak, self._active)

    def release(self) -> None:
        if self._active <= 0:
            raise RuntimeError("release() without a matching acquire()")
        self._active -= 1
        self._sem.release()
        if self._active == 0:
            # Wake wait_idle(); schedule rather than await — release() is sync.
            asyncio.get_running_loop().create_task(self._notify_idle())

    async def _notify_idle(self) -> None:
        async with self._idle:
            self._idle.notify_all()

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        await self.acquire()
        try:
            yield
        finally:
            self.release()

    # ── shutdown support ────────────────────────────────────────────────────

    async def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until no slot is held. Returns False on timeout."""
        if self._active == 0:
            return True

        async def _wait() -> None:
            async with self._idle:
                await self._idle.wait_for(lambda: self._active == 0)

        try:
            await asyncio.wait_for(_wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
