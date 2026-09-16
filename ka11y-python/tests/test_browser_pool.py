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


@pytest.mark.asyncio
async def test_crashed_browser_is_relaunched_on_next_lease():
    """Crash recovery: if Chromium dies between leases the pool must relaunch
    instead of handing out a dead handle forever."""
    pool = bp.get_pool()
    async with pool.lease_context() as ctx:
        await (await ctx.new_page()).set_content("<p>one</p>")
    gen_before = pool.generation
    assert gen_before == 1

    # Kill the warm browser out from under the pool.
    await pool._browsers[0].close()  # noqa: SLF001
    assert not pool._browsers[0].is_connected()  # noqa: SLF001

    async with pool.lease_context() as ctx:
        page = await ctx.new_page()
        await page.set_content("<!doctype html><title>back</title>")
        assert (await page.title()) == "back"
    assert pool.generation == gen_before + 1
    assert len(pool._browsers) == 1  # noqa: SLF001


@pytest.mark.asyncio
async def test_reserve_lets_inner_lease_skip_semaphore():
    """``reserve()`` + a lease inside must use ONE slot, not two — with a
    single-slot pool that would otherwise deadlock."""
    pool = bp.BrowserPool(max_browsers=1)

    async def stage():
        async with pool.reserve():
            async with pool.lease_context() as ctx:
                page = await ctx.new_page()
                await page.set_content("<p>x</p>")
                return "ok"

    assert await asyncio.wait_for(stage(), timeout=30) == "ok"
    await pool.shutdown()


@pytest.mark.asyncio
async def test_recycle_only_when_idle(monkeypatch):
    """A memory/lifetime threshold must not retire a browser that has a live
    lease; it is applied on the next idle acquire."""
    pool = bp.BrowserPool(max_browsers=2, max_lifetime_s=0.01)

    async with pool.lease_context() as ctx:
        gen_in_lease = pool.generation
        await asyncio.sleep(0.05)  # lifetime now exceeded
        # A second lease while the first is still active must NOT recycle.
        async with pool.lease_context():
            assert pool.generation == gen_in_lease
        await (await ctx.new_page()).set_content("<p>still alive</p>")

    # Idle now → the stale browser is replaced on the next acquire.
    async with pool.lease_context():
        assert pool.generation == gen_in_lease + 1
    await pool.shutdown()
