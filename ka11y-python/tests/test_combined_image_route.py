"""
Tests for GET /api/v1/combined/{job_id}/image.

Regression guard: the defence-in-depth check used to require the image
path to live INSIDE the job's own output_dir. But the image crawler
writes to ``{output_root}/{domain}_{ts}`` which is a SIBLING of the
combined runner's ``{output_root}/{domain}_{ts}_{job_id}_combined``
dir, so every legitimate image returned 403 "Image path escapes the
job output directory" and the UI showed "image unavailable"
everywhere. Containment is now to the configured ``output_dir`` root
(plus the job dir's parent as a fallback) — sibling crawler dirs are
served, paths outside the configured root are still refused.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ka11y.main import app
from ka11y.api.v1.combined import store as combined_store
from ka11y.api.v1.combined import routes as combined_routes


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def image_job(tmp_path, monkeypatch):
    """Seed _jobs with a completed-style job and a real image on disk in
    a SIBLING directory (mimicking the AsyncImageCrawler layout)."""
    output_root = tmp_path / "output"
    output_root.mkdir()

    crawler_dir = output_root / "example_com_0513_1234"
    crawler_dir.mkdir()
    img_path = crawler_dir / "originals" / "text" / "img_abc.png"
    img_path.parent.mkdir(parents=True)
    # 1x1 PNG — magic header is enough for FileResponse to serve it.
    img_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
        b"\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xcf\xc0\x00\x00"
        b"\x00\x03\x00\x01\xc6\xa6\xc1\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    job_dir = output_root / "example_com_0513_1234_abc123_combined"
    job_dir.mkdir()

    job_id = "test-image-route-job"
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "output_dir": str(job_dir),
        "result": {
            "image_audit_report": {
                "images": [{"path": str(img_path), "filename": "img_abc.png"}],
            },
        },
    }

    # Point load_config -> { input: { output_dir: <tmp output root> } }
    monkeypatch.setattr(
        "ka11y.utils.config_loader.load_config",
        lambda: {"input": {"output_dir": str(output_root)}},
    )

    yield job_id, img_path

    combined_store._jobs.pop(job_id, None)


def test_image_in_sibling_crawler_dir_is_served(client, image_job):
    """The image lives in a sibling of the job's output_dir but inside
    the configured output root — must serve (200), not 403."""
    job_id, img_path = image_job
    resp = client.get(
        f"/api/v1/combined/{job_id}/image",
        params={"path": str(img_path)},
    )
    assert resp.status_code == 200, (
        f"expected 200 for legitimate sibling-dir image, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )
    assert resp.headers["content-type"].startswith("image/")
    assert resp.content.startswith(b"\x89PNG")


def test_path_outside_configured_root_is_refused(client, image_job):
    """A path on disk but OUTSIDE the configured output root must
    return 403 even if it exists. Pins the symlink-attack guard."""
    job_id, _ = image_job
    # Inject a poisoned entry pointing outside the output root.
    poisoned = "/etc/passwd"
    combined_store._jobs[job_id]["result"]["image_audit_report"]["images"].append(
        {"path": poisoned, "filename": "passwd"}
    )
    resp = client.get(
        f"/api/v1/combined/{job_id}/image",
        params={"path": poisoned},
    )
    assert resp.status_code == 403, (
        f"expected 403 for path outside output root, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )


def test_unknown_path_is_refused(client, image_job):
    """Paths not present in any of the job's report.images[] must
    return 403 regardless of where they live."""
    job_id, img_path = image_job
    bogus = img_path.parent / "not_in_report.png"
    bogus.write_bytes(b"\x89PNG")
    resp = client.get(
        f"/api/v1/combined/{job_id}/image",
        params={"path": str(bogus)},
    )
    assert resp.status_code == 403
