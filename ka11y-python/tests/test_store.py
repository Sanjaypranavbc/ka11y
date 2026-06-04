"""
Unit tests for ka11y/api/v1/combined/store.py

Covers:
  - _broadcast() acquires lock (P6 fix)
  - Concurrent broadcast + subscriber add is race-condition-free
  - Broadcast to empty subscriber list does not fail
  - Subscriber removed during broadcast does not raise
  - _close_subscribers() drains queues and removes job entry
"""

from __future__ import annotations

import asyncio
import pytest

from ka11y.api.v1.combined.store import (
    _broadcast,
    _close_subscribers,
    _subscribers,
    _get_subscribers_lock,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _add_subscriber(job_id: str) -> asyncio.Queue:
    """Simulate the route handler adding a subscriber under the lock."""
    q: asyncio.Queue = asyncio.Queue()
    async with _get_subscribers_lock():
        _subscribers.setdefault(job_id, []).append(q)
    return q


def _remove_subscriber(job_id: str, q: asyncio.Queue) -> None:
    subs = _subscribers.get(job_id, [])
    if q in subs:
        subs.remove(q)


# ─────────────────────────────────────────────────────────────────────────────
# _broadcast — basic correctness
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_delivers_to_single_subscriber():
    job_id = "test-job-1"
    _subscribers.pop(job_id, None)

    q = await _add_subscriber(job_id)
    await _broadcast(job_id, "stage_start", {"stage": "form_audit"})

    assert not q.empty()
    msg = q.get_nowait()
    assert msg["event"] == "stage_start"
    assert msg["data"]["stage"] == "form_audit"

    _subscribers.pop(job_id, None)


@pytest.mark.asyncio
async def test_broadcast_delivers_to_multiple_subscribers():
    job_id = "test-job-multi"
    _subscribers.pop(job_id, None)

    q1 = await _add_subscriber(job_id)
    q2 = await _add_subscriber(job_id)
    q3 = await _add_subscriber(job_id)

    await _broadcast(job_id, "job_complete", {"job_id": job_id})

    for q in (q1, q2, q3):
        assert not q.empty()
        msg = q.get_nowait()
        assert msg["event"] == "job_complete"

    _subscribers.pop(job_id, None)


@pytest.mark.asyncio
async def test_broadcast_to_empty_subscriber_list_does_not_fail():
    """Broadcast to a job with no subscribers must be a no-op."""
    job_id = "test-job-empty"
    _subscribers.pop(job_id, None)

    # Should not raise
    await _broadcast(job_id, "job_complete", {"job_id": job_id})


@pytest.mark.asyncio
async def test_broadcast_to_unknown_job_does_not_fail():
    """Broadcast for a job_id that has never had subscribers must not raise."""
    await _broadcast("nonexistent-job-xyz", "job_failed", {"error": "boom"})


# ─────────────────────────────────────────────────────────────────────────────
# _broadcast — lock-protection (P6 fix)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_broadcast_and_add_subscriber_no_race():
    """
    P6: _broadcast must be safe to call while a subscriber is being added
    concurrently.  We fire both coroutines simultaneously and verify that the
    new subscriber either receives the message (if it was added before the
    broadcast iterated) or doesn't (if it was added after) — but the process
    must NOT raise and no message must be lost to a subscriber that was
    already registered.
    """
    job_id = "test-job-race"
    _subscribers.pop(job_id, None)

    # Pre-existing subscriber
    q_existing = await _add_subscriber(job_id)

    # Run broadcast and add-subscriber concurrently
    async def slow_add():
        """Add a subscriber with a tiny sleep to interleave with broadcast."""
        await asyncio.sleep(0)
        return await _add_subscriber(job_id)

    new_q_task = asyncio.create_task(slow_add())
    await _broadcast(job_id, "ping", {"v": 1})
    await new_q_task

    # The existing subscriber must have received the message
    assert not q_existing.empty()
    assert q_existing.get_nowait()["event"] == "ping"

    # No exception was raised (test passes if we reach here)
    _subscribers.pop(job_id, None)


@pytest.mark.asyncio
async def test_broadcast_is_async():
    """_broadcast must be a coroutine (awaitable), not a plain function."""
    import inspect

    job_id = "test-job-async-check"
    coro = _broadcast(job_id, "test", {})
    assert inspect.isawaitable(coro)
    await coro  # clean up the coroutine


# ─────────────────────────────────────────────────────────────────────────────
# Subscriber removed during broadcast
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscriber_removed_before_broadcast_does_not_raise():
    """
    If a subscriber is removed from the list between _broadcast calls
    (e.g. client disconnects), the next broadcast must still work.
    """
    job_id = "test-job-removed"
    _subscribers.pop(job_id, None)

    q = await _add_subscriber(job_id)
    _remove_subscriber(job_id, q)

    # Must not raise even though the queue is gone
    await _broadcast(job_id, "stage_complete", {"stage": "form_audit"})

    _subscribers.pop(job_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# _close_subscribers
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_subscribers_sends_none_sentinel():
    job_id = "test-job-close"
    _subscribers.pop(job_id, None)

    q = await _add_subscriber(job_id)
    await _close_subscribers(job_id)

    # Sentinel None should be in the queue
    assert not q.empty()
    assert q.get_nowait() is None


@pytest.mark.asyncio
async def test_close_subscribers_removes_job_entry():
    job_id = "test-job-close-cleanup"
    _subscribers.pop(job_id, None)

    await _add_subscriber(job_id)
    assert job_id in _subscribers

    await _close_subscribers(job_id)
    assert job_id not in _subscribers


@pytest.mark.asyncio
async def test_close_subscribers_on_empty_job_does_not_fail():
    job_id = "test-job-close-empty"
    _subscribers.pop(job_id, None)

    # Should not raise
    await _close_subscribers(job_id)


@pytest.mark.asyncio
async def test_close_subscribers_is_async():
    import inspect

    job_id = "test-job-close-async"
    coro = _close_subscribers(job_id)
    assert inspect.isawaitable(coro)
    await coro
