"""
Tests for Sprint-2 #14 — the concurrent-job semaphore in
``ka11y.api.v1.combined.runner``.

Real ``_run_job`` would spawn Playwright + axe-core; here we just verify
that the gating semaphore is initialised, bound to the running loop, and
serialises body invocations correctly using a stub.
"""
from __future__ import annotations

import asyncio

import pytest

from ka11y.api.v1.combined import runner


@pytest.fixture(autouse=True)
def _reset_sema():
    runner._job_semaphore = None  # noqa: SLF001
    runner._job_semaphore_loop = None  # noqa: SLF001
    yield
    runner._job_semaphore = None  # noqa: SLF001
    runner._job_semaphore_loop = None  # noqa: SLF001


@pytest.mark.asyncio
async def test_semaphore_initialised_with_configured_cap():
    sem = runner._get_job_semaphore()
    # `_value` is the public-ish snapshot of remaining slots.
    assert sem._value == runner._MAX_CONCURRENT_JOBS  # noqa: SLF001


@pytest.mark.asyncio
async def test_second_call_returns_same_semaphore_in_same_loop():
    sem_a = runner._get_job_semaphore()
    sem_b = runner._get_job_semaphore()
    assert sem_a is sem_b


@pytest.mark.asyncio
async def test_semaphore_serialises_runs(monkeypatch):
    """Patch ``_MAX_CONCURRENT_JOBS`` to 1 and confirm two concurrent calls
    to the gated wrapper run one-at-a-time."""
    monkeypatch.setattr(runner, "_MAX_CONCURRENT_JOBS", 1)
    runner._job_semaphore = None  # noqa: SLF001 — force re-init at cap=1
    runner._job_semaphore_loop = None  # noqa: SLF001

    in_flight = 0
    max_in_flight = 0
    started = asyncio.Event()

    async def fake_body(job_id, payload, filter_rule=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        started.set()
        await asyncio.sleep(0.05)
        in_flight -= 1

    # Patch the body so we don't need a real payload/audit.
    monkeypatch.setattr(runner, "_run_job_body", fake_body)
    # _run_job touches _jobs[job_id]["status"]; pre-seed it.
    runner._jobs["job-a"] = {"status": "pending"}
    runner._jobs["job-b"] = {"status": "pending"}

    try:
        await asyncio.gather(
            runner._run_job("job-a", payload=None),
            runner._run_job("job-b", payload=None),
        )
    finally:
        runner._jobs.pop("job-a", None)
        runner._jobs.pop("job-b", None)

    assert max_in_flight == 1, (
        f"semaphore with cap=1 must serialise; saw {max_in_flight} concurrent runs"
    )
