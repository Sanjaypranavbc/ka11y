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


@pytest.mark.asyncio
async def test_get_after_eviction_reads_from_db(isolated_db):
    """A run absent from the hot _jobs cache must still resolve from SQLite."""
    from ka11y.api.v1.combined.routes import get_combined_audit
    from ka11y.api.v1.combined.store import _jobs

    await _seed_completed("run-evicted")
    _jobs.pop("run-evicted", None)  # simulate TTL eviction / restart
    job = await get_combined_audit("run-evicted")
    assert job["status"] == "completed"
    assert job["result"]["summary"]["violations"] == 1
    # Image src rewritten to a job-scoped serving URL by the shared injector.
    el = job["result"]["violations"][0]["element"]
    assert el["selector"] == "img"


@pytest.mark.asyncio
async def test_history_endpoint(isolated_db):
    from ka11y.api.v1.combined.routes import list_combined_history

    await _seed_completed("run-h1")
    out = await list_combined_history(limit=10, offset=0, url=None, status="completed")
    assert out["count"] == 1
    assert out["runs"][0]["run_id"] == "run-h1"


@pytest.mark.asyncio
async def test_cancel_endpoint(isolated_db):
    from ka11y.api.v1.combined.routes import cancel_combined_audit
    from ka11y.api.v1.combined.store import _jobs

    await repo.create_run(
        run_id="run-c", url="https://e.com", status="queued",
        lang_requested="auto", wcag_level="AA", params={}, max_depth=0,
        max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )
    _jobs.pop("run-c", None)
    res = await cancel_combined_audit("run-c")
    assert res["cancelled"] is True
    assert (await repo.get_run("run-c"))["status"] == "cancelled"


@pytest.mark.asyncio
async def test_admin_metrics(isolated_db):
    from ka11y.api.v1.assets import admin_metrics

    await _seed_completed("run-m")
    m = await admin_metrics()
    assert m["status_counts"].get("completed", 0) >= 1
    assert m["totals"]["total_runs"] >= 1


def test_axe_mapper_shapes_findings():
    """P6: raw axe.run output maps to the flat finding shape merge/report expect."""
    from ka11y.crawler.axe_runner import map_axe_results

    raw = {
        "violations": [
            {
                "id": "image-alt",
                "impact": "critical",
                "help": "Images must have alternate text",
                "helpUrl": "https://dequeuniversity.com/rules/axe/image-alt",
                "tags": ["wcag2a", "wcag111"],
                "nodes": [{"html": "<img src='x'>", "target": ["#logo"]}],
            }
        ],
        "incomplete": [],
        "passes": [
            {"id": "document-title", "tags": ["wcag2a", "wcag242"], "help": "ok", "nodes": []}
        ],
    }
    findings = map_axe_results(raw, "https://example.com")
    fail = next(f for f in findings if f["status"] == "fail")
    assert fail["wcag_sc"] == "1.1.1"
    assert fail["level"] == "A"
    assert fail["source"] == "axe"
    assert fail["severity"] == "critical"
    assert fail["element"]["tag"] == "IMG"
    assert fail["element"]["selector"] == "#logo"
    assert fail["element"]["page_url"] == "https://example.com"
    assert any(f["status"] == "pass" and f["wcag_sc"] == "2.4.2" for f in findings)


@pytest.mark.asyncio
async def test_register_report_assets_rewrites_urls(isolated_db, tmp_path):
    """P2: report images + finding image_src local paths become /assets/{id}."""
    from ka11y.store.assets import register_report_assets

    await repo.create_run(
        run_id="run-p2", url="https://e.com", status="running",
        lang_requested="auto", wcag_level="AA", params={}, max_depth=0,
        max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"\x89PNG_crop")
    region = tmp_path / "region.png"
    region.write_bytes(b"\x89PNG_region")

    report = {
        "contrast_report": {"images": [{"path": str(region), "filename": "region.png"}]},
        "violations": [
            {"wcag_sc": "1.1.1", "status": "fail",
             "element": {"selector": "img", "image_src": str(crop)}}
        ],
        "needs_review": [], "passes": [],
    }
    n = await register_report_assets("run-p2", report)
    assert n == 2
    assert report["contrast_report"]["images"][0]["image_url"].startswith("/api/v1/assets/")
    assert report["violations"][0]["element"]["image_src"].startswith("/api/v1/assets/")
    rows = await repo.list_run_assets("run-p2")
    assert len(rows) == 2
    assert {r["kind"] for r in rows} == {"contrast_region", "finding_image"}


@pytest.mark.asyncio
async def test_crawler_timing_mirrors_to_db(isolated_db, tmp_path, monkeypatch):
    """P3: crawler rows mirror into stage_timings when a run_id is in context."""
    from ka11y.utils import crawler_timing

    monkeypatch.setenv("KA11Y_TELEMETRY_FILES", "0")
    crawler_timing.set_run_id("run-ct")
    crawler_timing.CrawlerTimingLogger(tmp_path).record(
        "image", scope="https://e.com", duration_s=1.5, status="ok", pages=4
    )
    await asyncio.sleep(0.1)  # let the fire-and-forget writer drain
    rows = await dbm.get_db().query(
        "SELECT stage, sub_stage, duration_ms, item_count FROM stage_timings WHERE run_id=?",
        ("run-ct",),
    )
    crawler_timing.set_run_id(None)
    assert any(r["stage"] == "image" and r["sub_stage"] == "crawl" for r in rows)


@pytest.mark.asyncio
async def test_run_timing_mirrors_to_run_events(isolated_db):
    """P3: the aggregate run-timing block lands in run_events as well."""
    from ka11y.utils.run_timing import log_run_timing

    log_run_timing(
        job_id="run-rt2", url="https://e.com", status="completed", stages=[],
        submitted_at="2026-06-02T00:00:00+00:00",
        run_started_at="2026-06-02T00:00:01+00:00",
        completed_at="2026-06-02T00:00:05+00:00", lang="en",
        summary={"violations": 0},
    )
    await asyncio.sleep(0.1)
    events = await repo.get_events("run-rt2")
    assert any(e["event"] == "run_timing" for e in events)


@pytest.mark.asyncio
async def test_merge_findings_via_run_cpu(isolated_db):
    """P5: _merge_findings runs through run_cpu (thread fallback by default)."""
    from ka11y.api.v1.combined.runner import _merge_findings
    from ka11y.store.cpu_pool import run_cpu

    node = [{"wcag_sc": "1.1.1", "status": "fail", "element": {"selector": "a"}}]
    py = [{"wcag_sc": "1.4.3", "status": "fail", "element": {"selector": "b"}}]
    merged = await run_cpu(_merge_findings, node, py)
    scs = {f["wcag_sc"] for f in merged}
    assert scs == {"1.1.1", "1.4.3"}


def _sample_findings():
    return [
        {"source": "axe", "rule_id": "image-alt", "wcag_sc": "1.1.1", "level": "A",
         "status": "fail", "element": {"selector": "img.logo", "page_url": "https://e.com"}},
        {"source": "python", "rule_id": "py_143", "wcag_sc": "1.4.3", "level": "AA",
         "status": "needs_review", "element": {"selector": "p.hero", "page_url": "https://e.com"}},
        {"source": "axe", "rule_id": "document-title", "wcag_sc": "2.4.2", "level": "A",
         "status": "pass", "element": {"selector": "title", "page_url": "https://e.com"}},
    ]


def test_build_report_stamps_finding_ids_and_manual_review():
    from ka11y.api.v1.combined.report import _build_report

    rep = _build_report("https://e.com", _sample_findings())
    assert rep["summary"]["manual_review_required"] == 1
    nr = rep["needs_review"][0]
    assert nr["manual_review"] is True
    assert len(nr["finding_id"]) == 16
    # pass/(pass+violation) = 1/2
    assert rep["summary"]["score"] == 50.0


def test_apply_reviews_recomputes_score():
    from ka11y.api.v1.combined.report import _build_report, apply_reviews

    rep = _build_report("https://e.com", _sample_findings())
    fid = rep["needs_review"][0]["finding_id"]

    apply_reviews(rep, {fid: {"status": "violation"}})
    s = rep["summary"]
    assert s["violations"] == 2 and s["passes"] == 1 and s["needs_review"] == 0
    assert s["score"] == 33.3
    assert s["automated"] == {"violations": 1, "needs_review": 1, "passes": 1, "score": 50.0}

    # Idempotent + re-review to pass flips it the other way.
    apply_reviews(rep, {fid: {"status": "pass"}})
    s = rep["summary"]
    assert s["violations"] == 1 and s["passes"] == 2 and s["score"] == 66.7

    # Clearing the review restores automated numbers.
    apply_reviews(rep, {})
    assert rep["summary"]["score"] == 50.0 and rep["summary"]["needs_review"] == 1


@pytest.mark.asyncio
async def test_review_endpoint_updates_effective_score(isolated_db):
    from ka11y.api.v1.combined.report import _build_report
    from ka11y.api.v1.combined.routes import (
        FindingReviewRequest,
        get_combined_audit,
        review_finding,
    )
    from ka11y.api.v1.combined.store import _jobs

    rep = _build_report("https://e.com", _sample_findings())
    await repo.create_run(
        run_id="run-rev", url="https://e.com", status="completed",
        lang_requested="auto", wcag_level="AA", params={}, max_depth=0,
        max_pages=5, submitted_at="2026-06-02T00:00:00+00:00",
    )
    await repo.save_report("run-rev", rep)
    _jobs.pop("run-rev", None)

    fid = rep["needs_review"][0]["finding_id"]
    out = await review_finding("run-rev", fid, FindingReviewRequest(status="violation", note="confirmed"))
    assert out["status"] == "violation" and out["wcag_sc"] == "1.4.3"

    job = await get_combined_audit("run-rev")
    s = job["result"]["summary"]
    assert s["violations"] == 2 and s["needs_review"] == 0 and s["score"] == 33.3
    assert s["reviews"]["as_violation"] == 1
    # The reviewed finding carries its decision for the UI.
    assert job["result"]["needs_review"][0]["review_status"] == "violation"

    # Reviewing a non-existent / non-needs_review finding id → 404.
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        await review_finding("run-rev", "deadbeefdeadbeef", FindingReviewRequest(status="pass"))


def test_new_routes_registered(isolated_db):
    """The new endpoints are wired into the app and reachable."""
    from fastapi.testclient import TestClient

    from ka11y.main import app

    with TestClient(app) as client:
        h = client.get("/api/v1/combined/history")
        assert h.status_code == 200 and "runs" in h.json()
        m = client.get("/api/v1/admin/metrics")
        assert m.status_code == 200 and "status_counts" in m.json()
        # Unknown asset → 404 (route exists, not a 404-because-no-route).
        a = client.get("/api/v1/assets/999999")
        assert a.status_code == 404
