"""
Object storage for audit artifacts: local + S3 (moto) backends, key layout,
asset-registry upload, completion/crash uploads, and serving fallbacks.
No PostgreSQL needed (jobs land under anonymous/…); no network.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

from ka11y.storage import backends, keys
from ka11y.storage.backends import LocalObjectStore, S3ObjectStore, get_store, reset_store
from ka11y.storage.config import StorageSettings, settings

# async tests run under asyncio_mode=auto (pyproject); the TestClient test
# below is deliberately synchronous — TestClient drives the app's lifespan
# on its own loop and deadlocks when opened from inside a running one.


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def local_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "local")
    monkeypatch.setenv("KA11Y_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("KA11Y_S3_BUCKET", raising=False)
    monkeypatch.setenv("KA11Y_ARTIFACT_PDF", "0")
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
    monkeypatch.setenv("KA11Y_S3_SSE", "AES256")
    monkeypatch.setenv("KA11Y_ARTIFACT_PDF", "0")
    monkeypatch.delenv("KA11Y_S3_ENDPOINT_URL", raising=False)
    reset_store()
    with moto.mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="ka11y-test")
        yield boto3.client("s3", region_name="us-east-1")
    reset_store()


async def _ensure_run(run_id: str) -> None:
    """assets.run_id → runs.run_id (FK on); a real audit persists the run first."""
    from ka11y.store import repo

    await repo.create_run(
        run_id=run_id, url="https://example.com", status="running", lang_requested="en",
        wcag_level="AA", params={}, max_depth=0, max_pages=1, submitted_at="2026-09-16T00:00:00+00:00",
    )


def _report() -> dict:
    return {
        "url": "https://example.com",
        "summary": {"violations": 1, "needs_review": 0, "passes": 2, "score": 66.7, "page_count": 1,
                    "by_severity": {"critical": 1}},
        "violations": [{"wcag_sc": "1.1.1", "level": "A", "status": "fail", "severity": "critical",
                        "reason": "Image is missing alt", "element": {"page_url": "https://example.com", "selector": "img"}}],
        "needs_review": [],
        "passes": [],
        "pages": [],
    }


# ── settings ─────────────────────────────────────────────────────────────────


class TestSettings:
    def test_auto_picks_s3_when_bucket_set(self, monkeypatch):
        monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "auto")
        monkeypatch.setenv("KA11Y_S3_BUCKET", "b")
        assert settings().backend == "s3"
        monkeypatch.delenv("KA11Y_S3_BUCKET")
        assert settings().backend == "local"

    def test_s3_without_bucket_is_off(self, monkeypatch):
        monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "s3")
        monkeypatch.delenv("KA11Y_S3_BUCKET", raising=False)
        assert settings().backend == "off"
        reset_store()
        assert get_store() is None


# ── key layout ───────────────────────────────────────────────────────────────


class TestKeys:
    async def test_anonymous_prefix_without_postgres(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        jid = str(uuid.uuid4())
        keys.forget_job(jid)
        assert await keys.job_prefix(jid) == f"anonymous/jobs/{jid}"

    async def test_owned_prefix_uses_uuids_only(self, monkeypatch):
        from ka11y.db import audit_repo

        org, usr, sess, jid = (uuid.uuid4() for _ in range(4))

        async def fake_owner(job_id):
            return {"user_id": usr, "organization_id": org, "session_id": sess}

        monkeypatch.setattr(audit_repo, "get_owner", fake_owner)
        keys.forget_job(str(jid))
        prefix = await keys.job_prefix(str(jid))
        assert prefix == f"organizations/{org}/users/{usr}/sessions/{sess}/jobs/{jid}"
        assert "@" not in prefix
        assert keys.report_key(prefix, "report.pdf").endswith("/reports/report.pdf")
        assert keys.asset_key(prefix, "html_snapshot", "abc.html", page_slug="p1").endswith("/assets/html/p1/abc.html")
        assert keys.asset_key(prefix, "finding_image", "x.png").endswith("/assets/images/x.png")
        assert keys.asset_key(prefix, "screenshot", "s.png").endswith("/assets/screenshots/s.png")
        assert keys.raw_key(prefix, "ocr", "text_detection_report.json").endswith("/raw/ocr/text_detection_report.json")
        assert keys.crash_key(prefix).endswith("/crash/crash.json")
        keys.forget_job(str(jid))

    def test_key_parts_cannot_traverse(self):
        assert keys.report_key("p", "../../etc/passwd") == "p/reports/passwd"


# ── local backend ────────────────────────────────────────────────────────────


class TestLocalStore:
    async def test_roundtrip_list_delete(self, tmp_path):
        store = LocalObjectStore(tmp_path)
        ref = await store.put_bytes("a/b/c.txt", b"hello", content_type="text/plain")
        assert ref.backend == "local" and ref.size == 5 and ref.key == "a/b/c.txt"
        assert await store.get_bytes("a/b/c.txt") == b"hello"
        assert await store.exists("a/b/c.txt")
        src = tmp_path / "src.bin"
        src.write_bytes(b"\x00\x01")
        ref2 = await store.put_file("a/d.bin", src)
        assert ref2.size == 2
        assert await store.list_keys("a") == ["a/b/c.txt", "a/d.bin"]
        assert await store.download_url("a/b/c.txt") is None
        assert await store.delete_prefix("a") == 2
        assert not await store.exists("a/b/c.txt")

    async def test_traversal_guard(self, tmp_path):
        store = LocalObjectStore(tmp_path / "root")
        with pytest.raises(ValueError):
            await store.put_bytes("../escape.txt", b"x")


# ── S3 backend (moto) ────────────────────────────────────────────────────────


class TestS3Store:
    async def test_roundtrip_with_prefix_and_sse(self, s3_env):
        store = get_store()
        assert isinstance(store, S3ObjectStore)
        ref = await store.put_bytes("jobs/1/reports/report.json", b"{}", content_type="application/json")
        assert ref.uri == "s3://ka11y-test/jobs/1/reports/report.json"
        head = s3_env.head_object(Bucket="ka11y-test", Key="wcag-auditor/jobs/1/reports/report.json")
        assert head["ContentType"] == "application/json"
        assert head["ServerSideEncryption"] == "AES256"
        assert await store.get_bytes("jobs/1/reports/report.json") == b"{}"
        assert await store.get_bytes("jobs/1/missing") is None
        assert await store.exists("jobs/1/reports/report.json")
        url = await store.download_url("jobs/1/reports/report.json", filename="r.json")
        assert "ka11y-test" in url and "X-Amz-Signature" in url
        assert await store.list_keys("jobs/1") == ["jobs/1/reports/report.json"]
        assert await store.delete_prefix("jobs/1") == 1
        assert not await store.exists("jobs/1/reports/report.json")

    async def test_put_file(self, s3_env, tmp_path):
        p = tmp_path / "shot.png"
        p.write_bytes(b"\x89PNG")
        ref = await get_store().put_file("jobs/2/assets/screenshots/shot.png", p)
        assert ref.size == 4 and ref.content_type == "image/png"
        assert s3_env.head_object(Bucket="ka11y-test", Key="wcag-auditor/jobs/2/assets/screenshots/shot.png")["ContentType"] == "image/png"


# ── asset registry → object store ────────────────────────────────────────────


class TestAssetUpload:
    async def test_put_asset_mirrors_to_store_once(self, local_env, tmp_path):
        from ka11y.store.assets import put_asset, get_asset_record
        from ka11y.store.db import get_db

        run_id = str(uuid.uuid4())
        await _ensure_run(run_id)
        img = tmp_path / "crop.png"
        img.write_bytes(b"\x89PNG-crop")
        ref = await put_asset(run_id=run_id, kind="finding_image", data=img, page_url="https://example.com/a", mime="image/png")
        assert ref is not None
        row = await get_asset_record(ref.asset_id)
        assert row["object_key"].startswith(f"anonymous/jobs/{run_id}/assets/images/")
        assert row["object_key"].endswith(f"{ref.sha256}.png")
        assert (local_env / row["object_key"]).is_file()
        # same bytes registered again (second rule) → same row, no second upload
        ref2 = await put_asset(run_id=run_id, kind="finding_image", data=img, page_url="https://example.com/a", mime="image/png")
        assert ref2.asset_id == ref.asset_id
        n = (await get_db().query_one("SELECT COUNT(*) AS n FROM assets WHERE run_id=?", (run_id,)))["n"]
        assert n == 1

    async def test_ocr_report_keeps_readable_name(self, local_env, tmp_path):
        from ka11y.store.assets import put_asset, get_asset_record

        run_id = str(uuid.uuid4())
        await _ensure_run(run_id)
        f = tmp_path / "text_detection_report.json"
        f.write_text("{}")
        ref = await put_asset(run_id=run_id, kind="ocr_report", data=f, mime="application/json")
        row = await get_asset_record(ref.asset_id)
        assert row["object_key"].endswith("/raw/ocr/" + ref.sha256[:8] + "-text_detection_report.json")


# ── completion / crash uploads ───────────────────────────────────────────────


class TestUploader:
    async def test_upload_job_artifacts_local(self, local_env, tmp_path):
        from ka11y.storage.uploader import upload_job_artifacts

        run_id = str(uuid.uuid4())
        await _ensure_run(run_id)
        out = tmp_path / "run"
        ocr = out / "image_raw" / "text_detected" / "contrast"
        ocr.mkdir(parents=True)
        (out / "image_raw" / "text_detected" / "text_detection_report.json").write_text("{}")
        (ocr / "contrast_report.csv").write_text("a,b\n")
        html = out / "html" / "page.html"
        html.parent.mkdir()
        html.write_text("<html><body>hi</body></html>")
        steps = out / "steps.jsonl"
        steps.write_text("{}\n")

        result = await upload_job_artifacts(
            run_id, report=_report(), output_dir=out,
            html_snapshots={"https://example.com": str(html)}, step_log_paths=[str(steps)],
        )
        prefix = f"anonymous/jobs/{run_id}"
        assert result["reports"]["json"] == f"{prefix}/reports/report.json"
        assert result["reports"]["csv"] == f"{prefix}/reports/findings.csv"
        assert "pdf" not in result["reports"]  # KA11Y_ARTIFACT_PDF=0
        assert result["assets"] == 4  # html + 2 ocr files + step log
        stored = json.loads((local_env / prefix / "reports" / "report.json").read_text())
        assert stored["url"] == "https://example.com"
        assert (local_env / prefix / "reports" / "findings.csv").read_text().startswith("")
        listed = await get_store().list_keys(prefix)
        assert any("/assets/html/" in k and k.endswith(".html") for k in listed)
        assert any(k.endswith("-text_detection_report.json") and "/raw/ocr/" in k for k in listed)
        assert any(k.endswith("-contrast_report.csv") for k in listed)
        assert any("/raw/steps/" in k for k in listed)

    async def test_upload_job_artifacts_s3(self, s3_env):
        from ka11y.storage.uploader import upload_job_artifacts

        run_id = str(uuid.uuid4())
        result = await upload_job_artifacts(run_id, report=_report(), output_dir=None)
        listed = s3_env.list_objects_v2(Bucket="ka11y-test", Prefix=f"wcag-auditor/anonymous/jobs/{run_id}/")
        got = sorted(o["Key"].rsplit("/", 1)[1] for o in listed["Contents"])
        assert got == ["findings.csv", "report.json"]
        assert result["reports"]["json"].startswith("anonymous/jobs/")

    async def test_crash_upload(self, local_env):
        from ka11y.storage.uploader import upload_crash

        run_id = str(uuid.uuid4())
        ref = await upload_crash(run_id, {"error_id": "e1", "stage": "crawl", "traceback": "…"})
        assert ref.key == f"anonymous/jobs/{run_id}/crash/crash.json"
        assert json.loads((local_env / ref.key).read_text())["stage"] == "crawl"

    async def test_storage_off_is_noop(self, monkeypatch):
        monkeypatch.setenv("KA11Y_STORAGE_BACKEND", "off")
        reset_store()
        from ka11y.storage.uploader import upload_job_artifacts, upload_crash

        assert (await upload_job_artifacts("x", report=_report(), output_dir=None))["reports"] == {}
        assert await upload_crash("x", {}) is None
        reset_store()


# ── serving fallback ─────────────────────────────────────────────────────────


class TestServeAsset:
    def test_serves_from_store_after_local_prune(self, local_env, tmp_path):
        import asyncio

        from fastapi.testclient import TestClient
        from ka11y.main import app
        from ka11y.store.assets import put_asset, get_asset_record

        run_id = str(uuid.uuid4())

        async def _setup():
            await _ensure_run(run_id)
            img = tmp_path / "a.png"
            img.write_bytes(b"\x89PNG-served")
            ref = await put_asset(run_id=run_id, kind="finding_image", data=img, mime="image/png")
            return ref, await get_asset_record(ref.asset_id)

        ref, row = asyncio.run(_setup())
        Path(row["abs_path"]).unlink()  # simulate the retention prune of local bytes
        with TestClient(app) as c:
            r = c.get(f"/api/v1/assets/{ref.asset_id}")
            assert r.status_code == 200
            assert r.content == b"\x89PNG-served"
            assert r.headers["content-type"].startswith("image/png")
