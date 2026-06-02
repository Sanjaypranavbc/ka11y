"""
Integration tests for the durable persistence layer (P0–P6 wiring):
SQLite store, asset store, durable queue dispatcher, and the DB-backed API
fallbacks (history, cancel, get-after-eviction, metrics).
"""

from __future__ import annotations

import asyncio

import pytest

from ka11y.store import db as dbm
from ka11y.store import repo


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Point the global store at a throwaway SQLite file for this test."""
    db_path = tmp_path / "t.db"
    asset_path = tmp_path / "assets"
    monkeypatch.setenv("KA11Y_DB_PATH", str(db_path))
    monkeypatch.setenv("KA11Y_ASSET_DIR", str(asset_path))
    monkeypatch.setenv("KA11Y_TELEMETRY_FILES", "0")
    dbm.shutdown_db()
    dbm.init_db(str(db_path))
    yield
    dbm.shutdown_db()


async def _seed_completed(run_id: str) -> dict:
    await repo.create_run(
        run_id=run_id,
        url="https://example.com",
        status="queued",
        lang_requested="auto",
        wcag_level="AA",
        params={"url": "https://example.com", "max_depth": 0},
        max_depth=0,
        max_pages=5,
        submitted_at="2026-06-02T00:00:00+00:00",
    )
    await repo.mark_running(run_id, "2026-06-02T00:00:01+00:00", "2026-06-02T00:00:00+00:00")
    report = {
        "summary": {"violations": 1, "needs_review": 0, "passes": 2},
        "violations": [
            {"wcag_sc": "1.1.1", "level": "A", "status": "fail",
             "element": {"selector": "img", "page_url": "https://example.com"}}
        ],
        "needs_review": [],
        "passes": [],
    }
    await repo.save_report(run_id, report)
    await repo.save_findings(run_id, report)
    await repo.mark_completed(
        run_id, completed_at="2026-06-02T00:00:05+00:00",
        run_started_at="2026-06-02T00:00:01+00:00",
        summary=report["summary"], output_dir="/tmp/o",
    )
    return report


@pytest.mark.asyncio
async def test_run_report_roundtrip(isolated_db):
    await _seed_completed("run-rt")
    run = await repo.get_run("run-rt")
    assert run["status"] == "completed"
    assert run["wall_ms"] == 4000 and run["queue_wait_ms"] == 1000
    rep = await repo.get_report("run-rt")
    assert rep["summary"]["violations"] == 1
    runs = await repo.list_runs(limit=10)
    assert any(r["run_id"] == "run-rt" for r in runs)
    assert runs[0]["summary"]["violations"] == 1


@pytest.mark.asyncio
async def test_findings_flattened(isolated_db):
    await _seed_completed("run-f")
    rows = await dbm.get_db().query(
        "SELECT wcag_sc, status, source FROM findings WHERE run_id=?", ("run-f",)
    )
    assert {"wcag_sc": "1.1.1", "status": "fail", "source": "python"} in rows


@pytest.mark.asyncio
async def test_asset_put_get_roundtrip(isolated_db):
    from ka11y.store.assets import get_asset, put_asset

    # Assets FK-reference a run, so create it first (mirrors production order).
    await repo.create_run(
        run_id="run-a", url="https://e.com", status="running",
        lang_requested="auto", wcag_level="AA", params={}, max_depth=0,
        max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )
    ref = await put_asset(run_id="run-a", kind="screenshot", data=b"\x89PNG_fake", mime="image/png")
    assert ref is not None and ref.asset_id > 0
    # Same bytes again → content-addressed dedup (same row id).
    ref2 = await put_asset(run_id="run-a", kind="screenshot", data=b"\x89PNG_fake", mime="image/png")
    assert ref2.asset_id == ref.asset_id
    row = await get_asset(ref.asset_id)
    assert row and row["abs_path"].endswith(".png")


@pytest.mark.asyncio
async def test_crash_recovery_requeues_running(isolated_db):
    await repo.create_run(
        run_id="run-crash", url="https://e.com", status="running",
        lang_requested="auto", wcag_level="AA", params={"url": "https://e.com"},
        max_depth=0, max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )
    requeued = await repo.requeue_running()
    assert any(o["run_id"] == "run-crash" for o in requeued)
    run = await repo.get_run("run-crash")
    assert run["status"] == "queued" and run["attempt"] == 1


@pytest.mark.asyncio
async def test_retention_sweep_removes_old(isolated_db):
    await _seed_completed("run-old")
    # submitted_at is 2026 in the seed; sweep with 0-day retention removes it.
    removed = await repo.retention_sweep(retention_days=0)
    assert "run-old" in removed
    assert await repo.get_run("run-old") is None


@pytest.mark.asyncio
async def test_dispatcher_executes_queued_run(isolated_db, monkeypatch):
    """The dispatcher should pick a queued row and drive it through the runner."""
    from ka11y.api.v1.combined import dispatcher
    from ka11y.api.v1.combined import runner as runner_mod
    from ka11y.api.v1.combined.store import _jobs

    ran: list[str] = []

    async def fake_body(job_id, payload, filter_rule=None):
        ran.append(job_id)
        await repo.mark_completed(
            job_id, completed_at="2026-06-02T00:00:09+00:00",
            run_started_at="2026-06-02T00:00:08+00:00", summary={"violations": 0},
            output_dir="/tmp",
        )
        _jobs[job_id]["status"] = "completed"

    monkeypatch.setattr(runner_mod, "_run_job_body", fake_body)

    await repo.create_run(
        run_id="run-disp", url="https://example.com", status="queued",
        lang_requested="auto", wcag_level="AA",
        params={"url": "https://example.com", "max_depth": 0},
        max_depth=0, max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )

    task = asyncio.create_task(dispatcher.run_dispatcher())
    try:
        dispatcher.notify()
        for _ in range(50):
            await asyncio.sleep(0.05)
            if "run-disp" in ran:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert "run-disp" in ran
    assert (await repo.get_run("run-disp"))["status"] == "completed"
