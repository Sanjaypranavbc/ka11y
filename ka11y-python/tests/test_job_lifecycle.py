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
    close the run out: SQLite row 'failed', hot entry 'failed', SSE closed."""
    run_id = "lifecycle-dispatcher-crash"
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
    class _Boom:
        async def execute(self, *a, **k):
            raise RuntimeError("database is locked")

    monkeypatch.setattr(repo, "get_db", lambda: _Boom())
    with pytest.raises(RuntimeError):
        await repo.create_run(
            run_id="x", url="https://e.com", status="queued", lang_requested="en",
            wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at="2026-01-01T00:00:00+00:00",
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
    from ka11y.db import audit_repo

    owner_id, owner_org = _uuid.uuid4(), _uuid.uuid4()

    async def owned_by_someone_else(job_id):
        return {"user_id": owner_id, "organization_id": owner_org, "session_id": None}

    monkeypatch.setattr(audit_repo, "get_owner", owned_by_someone_else)
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
