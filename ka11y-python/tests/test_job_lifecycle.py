"""
Regression tests for job-lifecycle reliability fixes (CODE_REVIEW_2026-09-27 §5).

B2  a failure before the runner's try-block used to leave the job 'running'
    forever; the dispatcher's last-resort handler did not mark it failed.
B5  a failed queue INSERT was swallowed and the caller got a job id for a
    run nothing would ever execute.
"""

from __future__ import annotations

import uuid as _uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from ka11y.api.v1.combined import dispatcher, routes, runner, store
from ka11y.auth.dependencies import CurrentUser
from ka11y.api.v1.combined.models import CombinedRequest
from ka11y.store import repo
from tests.test_durable_store import isolated_db  # noqa: F401 — fixture


def _hot_entry(job_id: str, status: str = "queued") -> dict:
    return {
        "job_id": job_id,
        "status": status,
        "url": "https://example.com",
        "submitted_at": "2026-01-01T00:00:00+00:00",
        "_created_at": 0,
        "completed_at": None,
        "report_path": None,
        "result": None,
        "error": None,
        "current_stage": None,
        "stages": [],
        "warnings": [],
    }


# ── B2 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failure_before_output_dir_marks_job_failed(tmp_path):
    """Language detection blowing up (anything before the old try-block) must
    end in status='failed' with an error_id, not a job stuck 'running'."""
    job_id = "lifecycle-pre-try-crash"
    store._jobs[job_id] = _hot_entry(job_id)
    payload = CombinedRequest(url="https://example.com", lang="auto")

    with patch.object(runner, "detect_page_language", AsyncMock(side_effect=RuntimeError("dns down"))), patch.object(
        runner, "load_config", return_value={"input": {"output_dir": str(tmp_path)}}
    ):
        await runner._run_job_body(job_id, payload)

    job = store._jobs.pop(job_id)
    assert job["status"] == "failed"
    assert job["error_id"]
    assert job["error"] == "Audit failed due to an internal error."


@pytest.mark.asyncio
async def test_dispatcher_marks_run_failed_when_runner_escapes(isolated_db):  # noqa: F811
    """If the runner body raises past its own handler the dispatcher must still
    close the run out: run row 'failed', hot entry 'failed', SSE closed."""
    run_id = str(_uuid.uuid4())
    await repo.create_run(
        run_id=run_id, url="https://example.com", status="running", lang_requested="en",
        wcag_level="AA", params={"url": "https://example.com"}, max_depth=0, max_pages=1,
        submitted_at="2026-01-01T00:00:00+00:00",
    )
    store._jobs[run_id] = _hot_entry(run_id, status="running")
    payload = CombinedRequest(url="https://example.com")

    with patch("ka11y.api.v1.combined.runner._run_job_body", AsyncMock(side_effect=RuntimeError("boom"))):
        await dispatcher._run_tracked(run_id, payload, None)

    assert store._jobs.pop(run_id)["status"] == "failed"
    row = await repo.get_run(run_id)
    assert row["status"] == "failed" and row["error_stage"] == "dispatch"


# ── B5 ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admit_run_answers_503_when_queue_insert_fails():
    """No job id may be handed out for a run that was never queued."""
    async def failing_enqueue(job_id, payload, filter_rule=None):
        raise RuntimeError("disk full")

    async def no_ssrf(url):
        return None

    before = set(store._jobs)
    with patch.object(routes, "enqueue", failing_enqueue), patch.object(routes, "assert_public_url", no_ssrf):
        with pytest.raises(HTTPException) as exc:
            await routes._admit_run(CombinedRequest(url="https://example.com"))
    assert exc.value.status_code == 503
    assert set(store._jobs) == before, "hot-cache entry must be removed on enqueue failure"


@pytest.mark.asyncio
async def test_create_run_raises_when_store_write_fails(monkeypatch):
    """create_run is the one store write that must not swallow its error."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def boom():
        raise RuntimeError("connection refused")
        yield  # pragma: no cover

    monkeypatch.setattr(repo, "session_scope", boom)
    with pytest.raises(RuntimeError):
        await repo.create_run(
            run_id=str(_uuid.uuid4()), url="https://e.com", status="queued", lang_requested="en",
            wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at="2026-01-01T00:00:00+00:00",
        )


@pytest.mark.asyncio
async def test_create_run_rejects_non_uuid_ids():
    """The job id is the audit_jobs primary key (UUID); anything else is refused up front."""
    with pytest.raises(ValueError):
        await repo.create_run(
            run_id="not-a-uuid", url="https://e.com", status="queued", lang_requested="en",
            wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at=None,
        )


# ── B3 / B4 — authorization ──────────────────────────────────────────────────


def _user(is_admin: bool = False, org: _uuid.UUID | None = None) -> CurrentUser:
    return CurrentUser(
        user_id=_uuid.uuid4(), email="someone@example.com", name="Someone",
        session_id=_uuid.uuid4(), organization_id=org, is_admin=is_admin,
    )


@pytest.mark.asyncio
async def test_job_routes_hide_other_users_jobs(monkeypatch):
    """Every {job_id} route must apply the same owner/org check as export."""
    owner_id, owner_org = _uuid.uuid4(), _uuid.uuid4()

    async def owned_by_someone_else(job_id):
        return {"user_id": owner_id, "organization_id": owner_org, "session_id": None}

    monkeypatch.setattr(repo, "get_owner", owned_by_someone_else)
    job_id = "lifecycle-foreign-job"
    store._jobs[job_id] = _hot_entry(job_id, status="completed")
    stranger = _user()
    try:
        for call in (
            lambda: routes.get_combined_audit(job_id, user=stranger),
            lambda: routes.get_combined_audit_timings(job_id, user=stranger),
            lambda: routes.get_finding_reviews(job_id, user=stranger),
            lambda: routes.cancel_combined_audit(job_id, user=stranger),
            lambda: routes.rerun_combined_audit(job_id, user=stranger),
            lambda: routes.get_job_image(job_id, path="/x.png", user=stranger),
            lambda: routes.stream_combined_audit(job_id, user=stranger),
        ):
            with pytest.raises(HTTPException) as exc:
                await call()
            assert exc.value.status_code == 404, "foreign job must look non-existent"
        # Same org → visible.
        colleague = _user(org=owner_org)
        job = await routes.get_combined_audit(job_id, user=colleague)
        assert job["job_id"] == job_id
    finally:
        store._jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_combined_history_is_admin_only():
    with pytest.raises(HTTPException) as exc:
        await routes.list_combined_history(user=_user(is_admin=False))
    assert exc.value.status_code == 403


def test_admin_metrics_is_mounted_under_admin_router():
    from ka11y.main import app

    paths = {r.path for r in app.routes}
    assert "/api/v1/admin/metrics" in paths
    admin_router_paths = {"/api/v1" + r.path for r in __import__("ka11y.api.v1.admin", fromlist=["router"]).router.routes}
    assert "/api/v1/admin/metrics" in admin_router_paths


# ── B6 — cancellation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_queued_job_settles_hot_cache_and_closes_sse(isolated_db):  # noqa: F811
    """A queued job has no runner to notice the flag: the route itself must
    move it to 'cancelled' and send subscribers a terminal event."""
    import asyncio

    run_id = str(_uuid.uuid4())
    await repo.create_run(
        run_id=run_id, url="https://example.com", status="queued", lang_requested="en",
        wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at="2026-01-01T00:00:00+00:00",
    )
    store._jobs[run_id] = _hot_entry(run_id, status="queued")
    q: asyncio.Queue = asyncio.Queue()
    store._subscribers.setdefault(run_id, []).append(q)
    try:
        res = await routes.cancel_combined_audit(run_id)
        assert res["cancelled"] is True
        assert store._jobs[run_id]["status"] == "cancelled"
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        assert events[0]["event"] == "job_cancelled"
        assert events[-1] is None, "subscriber queue must be closed with the sentinel"
        assert run_id not in store._subscribers
    finally:
        store._jobs.pop(run_id, None)
        store._subscribers.pop(run_id, None)


@pytest.mark.asyncio
async def test_runner_honours_cancel_before_start(isolated_db, tmp_path):  # noqa: F811
    """A job cancelled while queued but picked up anyway ends as 'cancelled'
    with a job_cancelled event — not as a silent return leaving SSE open."""
    import asyncio

    run_id = str(_uuid.uuid4())
    await repo.create_run(
        run_id=run_id, url="https://example.com", status="cancelled", lang_requested="en",
        wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at="2026-01-01T00:00:00+00:00",
    )
    store._jobs[run_id] = _hot_entry(run_id, status="queued")
    q: asyncio.Queue = asyncio.Queue()
    store._subscribers.setdefault(run_id, []).append(q)
    detect = AsyncMock(return_value="en")
    try:
        with patch.object(runner, "detect_page_language", detect), patch.object(
            runner, "load_config", return_value={"input": {"output_dir": str(tmp_path)}}
        ):
            await runner._run_job_body(run_id, CombinedRequest(url="https://example.com", lang="auto"))
        assert store._jobs[run_id]["status"] == "cancelled"
        assert store._jobs[run_id]["completed_at"]
        detect.assert_not_called()
        events = [q.get_nowait() for _ in range(q.qsize())]
        assert any(e and e["event"] == "job_cancelled" for e in events)
    finally:
        store._jobs.pop(run_id, None)
        store._subscribers.pop(run_id, None)


def test_cancelled_jobs_are_evicted_like_finished_ones():
    """Eviction used to keep 'cancelled' entries in memory forever."""
    import inspect

    src = inspect.getsource(store._evict_old_jobs)
    assert '"cancelled"' in src


# ── B7 — rule tester isolation ───────────────────────────────────────────────


def test_rule_evaluator_registers_one_job_per_request():
    from ka11y.api.v1 import rule_evaluator as re_

    a = re_._register_job("https://a.example")
    b = re_._register_job("https://b.example")
    try:
        assert a != b and a in store._jobs and b in store._jobs
        assert store._jobs[a]["stages"] is not store._jobs[b]["stages"]
    finally:
        store._jobs.pop(a, None)
        store._jobs.pop(b, None)


def test_rule_evaluator_snapshot_cache_is_bounded():
    from ka11y.api.v1 import rule_evaluator as re_

    re_._SNAPSHOT_CACHE.clear()
    for i in range(re_._SNAPSHOT_CACHE_MAX + 5):
        re_._cache_put(f"https://site{i}.example", object())
    assert len(re_._SNAPSHOT_CACHE) == re_._SNAPSHOT_CACHE_MAX
    assert re_._cache_get("https://site0.example") is None  # oldest evicted
    re_._SNAPSHOT_CACHE.clear()


def test_stage_complete_clears_every_progress_throttle_key():
    from ka11y.api.v1.combined import stage_events as se

    job_id = "lifecycle-throttle"
    store._jobs[job_id] = _hot_entry(job_id, status="running")
    try:
        se._stage_start(job_id, "image_audit")
        for phase in ("crawl", "ocr", "alt_audit"):
            se.emit_stage_progress(job_id, "image_audit", 1, 2, phase=phase)
        assert any(k[0] == job_id for k in se._progress_last_emit)
        se._stage_complete(job_id, "image_audit", 0)
        assert not any(k[0] == job_id for k in se._progress_last_emit)
    finally:
        store._jobs.pop(job_id, None)


# ── submit-time SSRF check (now built on crawler/_ssrf_guard) ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",            # scheme
        "http:///path",                  # no host
        "http://localhost:8000/",        # loopback name
        "http://127.0.0.1/",             # loopback literal
        "http://10.0.0.5/",              # RFC-1918
        "http://[::1]/",                 # IPv6 loopback
        "http://169.254.169.254/latest", # cloud metadata
        "http://2130706433/",            # decimal-encoded 127.0.0.1
    ],
)
async def test_assert_public_url_rejects_non_public_targets(url):
    with pytest.raises(HTTPException) as exc:
        await routes.assert_public_url(url)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_assert_public_url_blocks_hostnames_resolving_privately(monkeypatch):
    monkeypatch.setattr(routes, "_resolve_hostname", lambda host: ("93.184.216.34", "10.1.2.3"))
    with pytest.raises(HTTPException) as exc:
        await routes.assert_public_url("https://rebinder.example/")
    assert "private/loopback" in exc.value.detail


@pytest.mark.asyncio
async def test_assert_public_url_accepts_public_hostname(monkeypatch):
    monkeypatch.setattr(routes, "_resolve_hostname", lambda host: ("93.184.216.34",))
    await routes.assert_public_url("https://example.com/page")  # no exception


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [-1, 3, 5])
async def test_submit_combined_audit_rejects_depth_outside_0_to_2(depth):
    """The query-string endpoint the UI uses answers 422 with a readable
    message (not a 500 from a ValidationError inside the handler)."""
    with pytest.raises(HTTPException) as exc:
        await routes.submit_combined_audit(
            url="https://example.com", max_depth=depth, max_pages=20, wcag_level="AA",
            email=None, lang="auto", user=_user(),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == "Crawl depth must be 0, 1 or 2."
