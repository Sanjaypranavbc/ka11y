"""
Tests for the shared :class:`BrowserPool` (Sprint 2 #9).

The pool must:
  * lease working ``BrowserContext`` instances from a single Chromium;
  * cap concurrent leases via the semaphore;
  * survive sequential leases without launching a new browser each time;
  * shut down cleanly.
"""
from __future__ import annotations

import asyncio

import pytest

from ka11y.crawler import browser_pool as bp


@pytest.fixture(autouse=True)
async def _reset_pool():
    """Each test gets a clean pool singleton to avoid loop-bound leaks."""
    await bp.shutdown_pool()
    yield
    await bp.shutdown_pool()


@pytest.mark.asyncio
async def test_lease_yields_usable_context():
    async with bp.leased_context() as ctx:
        page = await ctx.new_page()
        await page.set_content("<!doctype html><title>hi</title><h1>x</h1>")
        assert (await page.title()) == "hi"
        await page.close()


@pytest.mark.asyncio
async def test_sequential_leases_share_one_browser():
    pool = bp.get_pool()

    async with pool.lease_context():
        n_after_first = len(pool._browsers)  # noqa: SLF001

    async with pool.lease_context():
        n_after_second = len(pool._browsers)  # noqa: SLF001

    assert n_after_first == 1
    assert n_after_second == 1, "second lease must reuse the warm browser"


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent_leases():
    """With max_browsers=1, two concurrent leases must serialise."""
    pool = bp.BrowserPool(max_browsers=1)

    started = asyncio.Event()
    release = asyncio.Event()
    second_acquired = asyncio.Event()

    async def hold():
        async with pool.lease_context():
            started.set()
            await release.wait()

    async def second():
        await started.wait()
        async with pool.lease_context():
            second_acquired.set()

    holder = asyncio.create_task(hold())
    follower = asyncio.create_task(second())

    await started.wait()
    # The follower must NOT have acquired yet because the holder still holds.
    await asyncio.sleep(0.05)
    assert not second_acquired.is_set()

    release.set()
    await asyncio.wait_for(follower, timeout=10)
    assert second_acquired.is_set()

    await asyncio.wait_for(holder, timeout=10)
    await pool.shutdown()


@pytest.mark.asyncio
async def test_shutdown_is_idempotent():
    async with bp.leased_context():
        pass
    await bp.shutdown_pool()
    # Second shutdown must not raise.
    await bp.shutdown_pool()
