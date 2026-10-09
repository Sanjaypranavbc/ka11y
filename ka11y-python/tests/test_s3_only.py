"""
S3-only mode (PostgreSQL switched off): the object store is the whole run
store. Covers what used to need a database row — the asset registry, the
by-key asset route, manual verdicts (reviews.json), the history listing and
the per-job artifact listing / report download. Local backend; no network.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from ka11y.storage import jobstate, keys
from ka11y.storage.backends import get_store, reset_store


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KA11Y_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("KA11Y_ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.delenv("KA11Y_S3_BUCKET", raising=False)
    monkeypatch.setenv("KA11Y_ARTIFACT_PDF", "0")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_store()
    yield tmp_path / "artifacts"
    reset_store()


def _state(job_id: str, *, url: str, status: str, submitted_at: str) -> dict:
    st = jobstate.new_state(job_id, url=url, lang="en", params={"url": url, "max_depth": 0}, submitted_at=submitted_at)
    st["status"] = status
    return st


# ── asset registry without a database ────────────────────────────────────────


async def test_put_asset_uploads_and_returns_key_based_ref(local_env, tmp_path):
    from ka11y.store.assets import put_asset

    job_id = str(uuid.uuid4())
    img = tmp_path / "crop.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    ref = await put_asset(run_id=job_id, kind="finding_image", data=img, page_url="https://example.com/a", mime="image/png")
    assert ref is not None
    assert ref.asset_id == 0 and ref.object_key
    assert ref.object_key.startswith(f"anonymous/jobs/{job_id}/assets/images/")
    assert ref.url == f"/api/v1/assets/by-key/{ref.object_key}"
    assert await get_store().get_bytes(ref.object_key) == img.read_bytes()


async def test_register_report_assets_points_images_at_by_key_urls(local_env, tmp_path):
    from ka11y.store.assets import register_report_assets

    job_id = str(uuid.uuid4())
    img = tmp_path / "el.png"
    img.write_bytes(b"png-bytes")
    report = {
        "violations": [{"element": {"image_src": str(img), "page_url": "https://example.com/"}}],
        "needs_review": [], "passes": [],
        "contrast_report": {"images": [{"path": str(img), "page_url": "https://example.com/"}]},
    }
    n = await register_report_assets(job_id, report)
    assert n == 2
    src = report["violations"][0]["element"]["image_src"]
    assert src.startswith("/api/v1/assets/by-key/anonymous/jobs/")
    assert report["contrast_report"]["images"][0]["image_url"] == report["contrast_report"]["images"][0]["asset_url"]
    assert report["violations"][0]["element"]["asset_id"] is None


def test_by_key_route_serves_the_object_and_refuses_escapes(local_env, tmp_path):
    from ka11y.main import app
    from ka11y.store.assets import put_asset

    job_id = str(uuid.uuid4())
    img = tmp_path / "shot.png"
    img.write_bytes(b"shot-bytes")
    ref = asyncio.run(put_asset(run_id=job_id, kind="screenshot", data=img, mime="image/png"))
    assert ref is not None
    with TestClient(app) as c:
        r = c.get(ref.url)
        assert r.status_code == 200 and r.content == b"shot-bytes"
        assert r.headers["content-type"].startswith("image/png")
        assert c.get("/api/v1/assets/by-key/anonymous/jobs/x/../../etc/passwd").status_code == 404
        assert c.get("/api/v1/assets/by-key/organizations/none/jobs/x/assets/a.png").status_code == 404
        assert c.get(f"/api/v1/assets/by-key/anonymous/jobs/{job_id}/assets/screenshots/missing.png").status_code == 404


# ── manual verdicts in reviews.json ──────────────────────────────────────────


async def test_reviews_round_trip_and_clear(local_env):
    job_id = str(uuid.uuid4())
    assert await jobstate.get_reviews(job_id) == {}
    reviews = await jobstate.set_review(job_id, "f1", status="pass", note="ok", reviewer="qa@example.com", wcag_sc="1.1.1")
    assert reviews and reviews["f1"]["status"] == "pass" and reviews["f1"]["reviewer"] == "qa@example.com"
    assert reviews["f1"]["updated_at"]
    again = await jobstate.get_reviews(job_id)
    assert again["f1"]["note"] == "ok" and again["f1"]["wcag_sc"] == "1.1.1"
    # a second verdict overwrites, re-opening removes
    await jobstate.set_review(job_id, "f1", status="violation", reviewer="qa@example.com")
    assert (await jobstate.get_reviews(job_id))["f1"]["status"] == "violation"
    await jobstate.set_review(job_id, "f1", status="needs_review")
    assert await jobstate.get_reviews(job_id) == {}
    raw = await get_store().get_bytes(f"anonymous/jobs/{job_id}/reviews.json")
    assert json.loads(raw) == {}


# ── history listing from state.json ──────────────────────────────────────────


async def test_list_states_sorts_newest_first_and_filters(local_env):
    a, b, c = (str(uuid.uuid4()) for _ in range(3))
    await jobstate.put_state(a, _state(a, url="https://old.example.com", status="completed", submitted_at="2026-10-01T00:00:00+00:00"))
    await jobstate.put_state(b, _state(b, url="https://new.example.com", status="failed", submitted_at="2026-10-03T00:00:00+00:00"))
    await jobstate.put_state(c, _state(c, url="https://mid.example.com", status="completed", submitted_at="2026-10-02T00:00:00+00:00"))

    rows = await jobstate.list_states(limit=10)
    assert [r["run_id"] for r in rows] == [b, c, a]
    assert rows[0]["status"] == "failed" and rows[0]["job_id"] == b and rows[0]["params"]["max_depth"] == 0
    assert [r["run_id"] for r in await jobstate.list_states(status="completed")] == [c, a]
    assert [r["run_id"] for r in await jobstate.list_states(url="MID.example")] == [c]
    assert [r["run_id"] for r in await jobstate.list_states(limit=1, offset=1)] == [c]


# ── /audits: artifacts + download without report rows ─────────────────────────


def test_audit_artifacts_and_download_come_from_the_key_listing(local_env):
    from ka11y.main import app

    job_id = str(uuid.uuid4())

    async def _seed():
        await jobstate.put_state(job_id, _state(job_id, url="https://example.com", status="completed", submitted_at="2026-10-05T00:00:00+00:00"))
        prefix = await keys.job_prefix(job_id)
        store = get_store()
        await store.put_bytes(keys.report_key(prefix, "report.json"), b'{"summary": {}}', content_type="application/json")
        await store.put_bytes(keys.report_key(prefix, "findings.csv"), b"a,b\n", content_type="text/csv")
        await store.put_bytes(keys.asset_key(prefix, "screenshot", "s.png"), b"png", content_type="image/png")
        await jobstate.set_review(job_id, "f1", status="pass")

    asyncio.run(_seed())
    with TestClient(app) as c:
        r = c.get(f"/api/v1/audits/{job_id}/artifacts")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["storage"] == "local"
        assert sorted(x["report_id"] for x in body["reports"]) == ["findings.csv", "report.json"]
        assert {x["format"] for x in body["reports"]} == {"csv", "json"}
        assert len(body["assets"]) == 1 and body["assets"][0]["url"].startswith("/api/v1/assets/by-key/anonymous/jobs/")
        assert all(not a["rel_path"].endswith(("state.json", "reviews.json")) for a in body["assets"])

        d = c.get(f"/api/v1/audits/{job_id}/reports/findings.csv/download")
        assert d.status_code == 200 and d.content == b"a,b\n"
        assert d.headers["content-disposition"].endswith(f'{job_id}-findings.csv"')
        assert c.get(f"/api/v1/audits/{job_id}/reports/nope.csv/download").status_code == 404
        assert c.get(f"/api/v1/audits/{uuid.uuid4()}/artifacts").status_code == 404

        h = c.get("/api/v1/audits/history")
        assert h.status_code == 200 and any(i["run_id"] == job_id for i in h.json()["items"])
