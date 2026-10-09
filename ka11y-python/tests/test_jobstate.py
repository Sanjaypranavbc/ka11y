"""
ka11y.storage.jobstate — job state in object storage (local backend and
moto S3), the broadcast sink that mirrors hot-cache progress into it, and
the runner's cancel-marker check.
"""

from __future__ import annotations

import uuid

import pytest

from ka11y.api.v1.combined import store
from ka11y.storage import jobstate
from ka11y.storage.backends import reset_store


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KA11Y_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("KA11Y_S3_BUCKET", raising=False)
    reset_store()
    yield tmp_path / "artifacts"
    reset_store()


@pytest.fixture
def s3_env(monkeypatch):
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("KA11Y_S3_BUCKET", "ka11y-test")
    monkeypatch.setenv("KA11Y_S3_PREFIX", "wcag-auditor")
    monkeypatch.delenv("KA11Y_S3_ENDPOINT_URL", raising=False)
    reset_store()
    with moto.mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ka11y-test")
        yield boto3.client("s3", region_name="us-east-1")
    reset_store()


def _jid() -> str:
    return str(uuid.uuid4())


class TestStateRoundtrip:
    async def test_new_state_put_get_local(self, local_env):
        jid = _jid()
        state = jobstate.new_state(jid, url="https://example.com/", lang="auto", params={"url": "https://example.com/"})
        assert await jobstate.put_state(jid, state)
        got = await jobstate.get_state(jid)
        assert got["status"] == "queued" and got["params"]["url"] == "https://example.com/"
        assert got["updated_at"]
        assert (local_env / "anonymous" / "jobs" / jid / "state.json").is_file()

    async def test_update_state(self, local_env):
        jid = _jid()
        await jobstate.put_state(jid, jobstate.new_state(jid, url="u", lang="en", params={}))
        doc = await jobstate.update_state(jid, status="running", attempt=1)
        assert doc["status"] == "running" and doc["attempt"] == 1
        assert await jobstate.get_status(jid) == "running"

    async def test_unknown_job(self, local_env):
        assert await jobstate.get_state(_jid()) is None
        assert await jobstate.update_state(_jid(), status="x") is None
        assert await jobstate.get_report(_jid()) is None

    async def test_s3_backend(self, s3_env):
        jid = _jid()
        await jobstate.put_state(jid, jobstate.new_state(jid, url="u", lang="en", params={}))
        keys = [o["Key"] for o in s3_env.list_objects_v2(Bucket="ka11y-test")["Contents"]]
        assert f"wcag-auditor/anonymous/jobs/{jid}/state.json" in keys
        assert (await jobstate.get_state(jid))["status"] == "queued"
        assert jid in await jobstate.list_job_ids()

    async def test_storage_off(self, monkeypatch):
        monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "off")
        reset_store()
        try:
            assert not jobstate.storage_available()
            assert not await jobstate.put_state(_jid(), {})
            assert await jobstate.get_state(_jid()) is None
        finally:
            reset_store()


class TestCancelMarker:
    async def test_request_and_check(self, local_env):
        jid = _jid()
        assert not await jobstate.is_cancel_requested(jid)
        assert await jobstate.request_cancel(jid)
        assert await jobstate.is_cancel_requested(jid)

    async def test_runner_sees_marker_without_a_database(self, local_env):
        from ka11y.api.v1.combined import runner

        jid = _jid()
        assert not await runner._is_cancelled(jid)
        await jobstate.request_cancel(jid)
        assert await runner._is_cancelled(jid)


class TestSnapshot:
    def test_drops_result_and_private_fields_keeps_summary(self):
        hot = {
            "job_id": "j", "status": "completed", "url": "u", "submitted_at": "t", "lang": "en",
            "_created_at": 1.0, "report_path": "/x", "step_log_path": "/y",
            "result": {"summary": {"violations": 2}, "violations": [{"big": "x" * 1000}]},
            "stages": [{"name": "image_audit", "status": "completed"}],
        }
        snap = jobstate.snapshot(hot)
        assert "result" not in snap and "_created_at" not in snap and "report_path" not in snap
        assert snap["result_summary"] == {"violations": 2} and snap["has_report"] is True
        assert snap["stages"] == [{"name": "image_audit", "status": "completed"}]
        assert snap["warnings"] == []

    def test_to_hot_entry_has_runner_fields(self):
        state = jobstate.new_state("j", url="u", lang="ja", params={"url": "u"})
        hot = jobstate.to_hot_entry(state)
        for key in ("status", "url", "submitted_at", "lang", "stages", "warnings", "result", "_created_at"):
            assert key in hot
        assert hot["lang"] == "ja"


class TestProgressSink:
    async def test_broadcast_mirrors_hot_cache(self, local_env):
        jid = _jid()
        store._jobs[jid] = jobstate.to_hot_entry(jobstate.new_state(jid, url="u", lang="en", params={}))
        store._jobs[jid]["status"] = "running"
        store._jobs[jid]["current_stage"] = "image_audit"
        store.add_broadcast_sink(jobstate.progress_sink)
        try:
            await store._broadcast(jid, "stage_start", {"stage_name": "image_audit"})
            got = await jobstate.get_state(jid)
            assert got["status"] == "running" and got["current_stage"] == "image_audit"

            # Noisy per-image events are throttled…
            store._jobs[jid]["current_stage"] = "changed-by-progress"
            await store._broadcast(jid, "stage_progress", {"current": 1, "total": 9})
            assert (await jobstate.get_state(jid))["current_stage"] == "image_audit"
            # …but a stage boundary always writes.
            await store._broadcast(jid, "stage_complete", {"stage_name": "image_audit"})
            assert (await jobstate.get_state(jid))["current_stage"] == "changed-by-progress"
        finally:
            store.remove_broadcast_sink(jobstate.progress_sink)
            store._jobs.pop(jid, None)

    async def test_failing_sink_never_raises(self, local_env):
        async def bad_sink(job_id, event_type, data):
            raise RuntimeError("boom")

        store.add_broadcast_sink(bad_sink)
        try:
            await store._broadcast("any", "stage_start", {})
        finally:
            store.remove_broadcast_sink(bad_sink)
