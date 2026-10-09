"""
The SQS audit worker against moto's in-process SQS, with job state on the
local object-storage backend. The audit itself is a stub that behaves like
``runner._run_job_body`` (settles the hot-cache entry); no Chromium, no Node.

Covers: publish → consume → completed; a crash leaves the message for
redelivery; a duplicate delivery is skipped; the cancel marker; concurrency
never exceeds the limiter; the visibility heartbeat; graceful stop.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from ka11y.api.v1.combined.models import CombinedRequest
from ka11y.api.v1.combined.store import _jobs
from ka11y.queue import AuditJobMessage
from ka11y.queue.sqs import get_client, reset_client
from ka11y.storage import jobstate, keys
from ka11y.storage.backends import get_store, reset_store
from ka11y.worker import ConcurrencyLimiter, Worker


@pytest.fixture
def queue_env(tmp_path, monkeypatch):
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("SQS_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("SQS_VISIBILITY_TIMEOUT", "30")
    monkeypatch.setenv("SQS_WAIT_TIME_SECONDS", "0")
    monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KA11Y_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("KA11Y_S3_BUCKET", raising=False)
    reset_store()
    reset_client()
    with moto.mock_aws():
        import boto3

        url = boto3.client("sqs", region_name="us-east-1").create_queue(QueueName="ka11y-jobs")["QueueUrl"]
        monkeypatch.setenv("SQS_QUEUE_URL", url)
        reset_client()
        yield get_client()
    reset_client()
    reset_store()
    _jobs.clear()


async def publish(job_id: str | None = None, *, state: bool = True) -> str:
    """What the submit route does: state.json 'queued', then the message."""
    job_id = job_id or str(uuid.uuid4())
    req = CombinedRequest(url="https://example.com", lang="en")
    if state:
        await jobstate.put_state(
            job_id, jobstate.new_state(job_id, url=str(req.url), lang=req.lang, params=req.model_dump(mode="json"))
        )
    await get_client().send_message(AuditJobMessage.for_request(job_id, req))
    return job_id


def completing_body(delay: float = 0.0, *, with_report: bool = True):
    """A stub runner: settles the hot entry as the real one does."""
    calls: list[str] = []

    async def body(job_id: str, request: CombinedRequest, filter_rule=None) -> None:
        calls.append(job_id)
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["current_stage"] = "image_audit"
        await asyncio.sleep(delay)
        report = {"url": str(request.url), "summary": {"violations": 1, "needs_review": 0, "passes": 3}}
        if with_report:
            prefix = await keys.job_prefix(job_id)
            await get_store().put_bytes(keys.report_key(prefix, "report.json"), b'{"summary": {"violations": 1}}')
        _jobs[job_id].update(
            status="completed", completed_at=datetime.now(timezone.utc).isoformat(),
            result=report, current_stage=None,
        )

    body.calls = calls  # type: ignore[attr-defined]
    return body


def failing_body(error_stage: str = "image_audit"):
    async def body(job_id: str, request: CombinedRequest, filter_rule=None) -> None:
        _jobs[job_id].update(
            status="failed", completed_at=datetime.now(timezone.utc).isoformat(),
            error="Audit failed due to an internal error.", error_id="e1", error_stage=error_stage,
        )

    return body


async def crashing_body(job_id: str, request: CombinedRequest, filter_rule=None) -> None:
    raise RuntimeError("runner escaped its handler")


async def run_until_idle(worker: Worker, timeout: float = 15.0) -> None:
    await asyncio.wait_for(worker.run(), timeout=timeout)


# ── the four behaviours the spec asks for ────────────────────────────────────


async def test_publish_consume_completed(queue_env):
    job_id = await publish()
    body = completing_body()
    worker = Worker(run_job=body, poll_wait=0, idle_exit=True)
    await run_until_idle(worker)

    assert body.calls == [job_id]
    state = await jobstate.get_state(job_id)
    assert state["status"] == "completed"
    assert state["attempt"] == 1 and state["worker_pid"]
    assert state["result_summary"] == {"violations": 1, "needs_review": 0, "passes": 3}
    assert state["has_report"] is True
    assert await jobstate.get_report(job_id) == {"summary": {"violations": 1}}
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}
    assert job_id not in _jobs, "worker must drop its hot-cache entry when done"


async def test_crash_keeps_message_for_redelivery(queue_env, monkeypatch):
    job_id = await publish()
    handles: list[str] = []
    real = queue_env.receive_messages

    async def spy(max_messages=1, wait_time=None):
        got = await real(max_messages=max_messages, wait_time=wait_time)
        handles.extend(m.receipt_handle for m in got)
        return got

    monkeypatch.setattr(queue_env, "receive_messages", spy)
    worker = Worker(run_job=crashing_body, poll_wait=0, idle_exit=True, max_attempts=3)
    await run_until_idle(worker)

    counts = await queue_env.approximate_counts()
    assert counts["in_flight"] == 1 and counts["visible"] == 0, "message must NOT be deleted"
    state = await jobstate.get_state(job_id)
    assert state["status"] == "queued" and state["attempt"] == 1 and state["error_stage"] == "worker"
    assert await real(wait_time=0) == [], "still hidden until the visibility timeout lapses"

    # Make SQS redeliver now (the visibility timeout would do this later) and
    # let a worker on its last permitted attempt fail the job for good.
    await queue_env.change_visibility(handles[-1], 0)
    worker2 = Worker(run_job=crashing_body, poll_wait=0, idle_exit=True, max_attempts=2)
    await run_until_idle(worker2)
    state = await jobstate.get_state(job_id)
    assert state["status"] == "failed" and state["attempt"] == 2 and state["error_stage"] == "worker"
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


async def test_duplicate_delivery_is_skipped(queue_env):
    job_id = str(uuid.uuid4())
    await jobstate.put_state(job_id, {**jobstate.new_state(job_id, url="u", lang="en", params={}), "status": "completed"})
    await publish(job_id, state=False)
    body = completing_body()
    worker = Worker(run_job=body, poll_wait=0, idle_exit=True)
    await run_until_idle(worker)

    assert body.calls == [], "a completed job must not run again"
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


async def test_concurrency_never_exceeds_limit(queue_env):
    for _ in range(6):
        await publish()
    in_flight = 0
    peak = 0

    async def body(job_id, request, filter_rule=None):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.1)
        in_flight -= 1
        _jobs[job_id].update(status="completed", completed_at="t", result={"summary": {}})

    limiter = ConcurrencyLimiter(2)
    worker = Worker(run_job=body, limiter=limiter, poll_wait=0, idle_exit=True)
    await run_until_idle(worker)

    assert peak == 2, f"two slots → at most two concurrent audits, saw {peak}"
    assert limiter.peak == 2 and limiter.active == 0
    assert worker.processed == 6
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


# ── the rest of the handler ──────────────────────────────────────────────────


async def test_slots_are_taken_before_receiving(queue_env, monkeypatch):
    """Never receive more messages than there are free slots."""
    for _ in range(5):
        await publish()
    asked: list[int] = []
    real = queue_env.receive_messages

    async def spy(max_messages=1, wait_time=None):
        asked.append(max_messages)
        return await real(max_messages=max_messages, wait_time=wait_time)

    monkeypatch.setattr(queue_env, "receive_messages", spy)
    worker = Worker(run_job=completing_body(0.05), limiter=ConcurrencyLimiter(2), poll_wait=0, idle_exit=True)
    await run_until_idle(worker)
    assert asked and max(asked) <= 2


async def test_runner_recorded_failure_is_terminal_by_default(queue_env):
    job_id = await publish()
    worker = Worker(run_job=failing_body(), poll_wait=0, idle_exit=True)
    await run_until_idle(worker)
    state = await jobstate.get_state(job_id)
    assert state["status"] == "failed" and state["error_stage"] == "image_audit"
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


async def test_runner_recorded_failure_can_be_retried(queue_env):
    job_id = await publish()
    worker = Worker(run_job=failing_body(), poll_wait=0, idle_exit=True, retry_failed_audits=True, max_attempts=3)
    await run_until_idle(worker)
    assert (await jobstate.get_state(job_id))["status"] == "queued"
    assert (await queue_env.approximate_counts())["in_flight"] == 1


async def test_cancel_marker_settles_without_running(queue_env):
    job_id = await publish()
    await jobstate.request_cancel(job_id)
    body = completing_body()
    worker = Worker(run_job=body, poll_wait=0, idle_exit=True)
    await run_until_idle(worker)
    assert body.calls == []
    assert (await jobstate.get_state(job_id))["status"] == "cancelled"
    assert (await queue_env.approximate_counts())["in_flight"] == 0


async def test_missing_state_is_rebuilt_from_message(queue_env):
    job_id = await publish(state=False)
    worker = Worker(run_job=completing_body(), poll_wait=0, idle_exit=True)
    await run_until_idle(worker)
    state = await jobstate.get_state(job_id)
    assert state["status"] == "completed" and state["url"] == "https://example.com/"


async def test_poison_message_is_deleted(queue_env):
    import boto3

    boto3.client("sqs", region_name="us-east-1").send_message(QueueUrl=queue_env.queue_url, MessageBody="{not json")
    body = completing_body()
    worker = Worker(run_job=body, poll_wait=0, idle_exit=True)
    await run_until_idle(worker)
    assert body.calls == []
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


async def test_heartbeat_extends_visibility_while_running(queue_env, monkeypatch):
    extended: list[int] = []
    real = queue_env.change_visibility

    async def spy(receipt_handle, seconds):
        extended.append(seconds)
        await real(receipt_handle, seconds)

    monkeypatch.setattr(queue_env, "change_visibility", spy)
    await publish()
    worker = Worker(run_job=completing_body(0.35), poll_wait=0, idle_exit=True, heartbeat_interval=0.1)
    await run_until_idle(worker)
    assert len(extended) >= 2 and set(extended) == {30}


async def test_graceful_stop_waits_for_in_flight_audit(queue_env):
    job_id = await publish()
    started = asyncio.Event()

    async def body(jid, request, filter_rule=None):
        started.set()
        await asyncio.sleep(0.3)
        _jobs[jid].update(status="completed", completed_at="t", result={"summary": {}})

    worker = Worker(run_job=body, poll_wait=0)
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), 5)
    worker.request_stop()
    await asyncio.wait_for(task, 5)
    assert (await jobstate.get_state(job_id))["status"] == "completed"
    assert await queue_env.approximate_counts() == {"visible": 0, "in_flight": 0, "delayed": 0}


async def test_stop_while_waiting_for_slot_returns_promptly(queue_env):
    worker = Worker(run_job=completing_body(), poll_wait=0)
    task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.request_stop()
    await asyncio.wait_for(task, 5)
    assert worker.limiter.active == 0


# ── limiter ──────────────────────────────────────────────────────────────────


class TestConcurrencyLimiter:
    def test_env_default_and_floor(self, monkeypatch):
        from ka11y.worker.concurrency import max_concurrency_from_env

        monkeypatch.delenv("WORKER_MAX_CONCURRENCY", raising=False)
        assert max_concurrency_from_env() == 2
        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "0")
        assert max_concurrency_from_env() == 1
        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "nope")
        assert max_concurrency_from_env() == 2

    async def test_acquire_available_never_blocks(self):
        lim = ConcurrencyLimiter(2)
        await lim.acquire()
        assert await lim.acquire_available(5) == 1
        assert lim.free_slots == 0
        assert await lim.acquire_available(5) == 0
        lim.release()
        lim.release()
        assert lim.active == 0 and await lim.wait_idle(0.1)

    async def test_release_without_acquire_is_an_error(self):
        with pytest.raises(RuntimeError):
            ConcurrencyLimiter(1).release()
