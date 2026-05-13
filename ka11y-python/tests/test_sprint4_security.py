"""
Sprint 4 / steps 27 + 29: URL length cap on CombinedRequest, and TTL
eviction reclaiming the on-disk output directories.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from ka11y.api.v1.combined.models import CombinedRequest, _MAX_URL_CHARS
from ka11y.api.v1.combined import store as combined_store


# ── Step 27: URL max_length ───────────────────────────────────────────────────


def test_url_under_cap_validates():
    req = CombinedRequest(url="https://example.com/page", lang="en")
    assert str(req.url).startswith("https://example.com")


def test_url_at_cap_validates():
    # Build a URL exactly at the limit by padding query string.
    base = "https://example.com/?"
    pad = "a" * (_MAX_URL_CHARS - len(base))
    url = base + pad
    assert len(url) == _MAX_URL_CHARS
    req = CombinedRequest(url=url, lang="en")
    assert str(req.url)


def test_url_over_cap_rejected():
    url = "https://example.com/?" + ("a" * (_MAX_URL_CHARS + 1))
    with pytest.raises(ValidationError) as exc_info:
        CombinedRequest(url=url, lang="en")
    # The error message must mention the limit so operators can diagnose.
    assert str(_MAX_URL_CHARS) in str(exc_info.value)


def test_lang_field_still_capped():
    """Pre-existing length cap on `lang` must still hold."""
    with pytest.raises(ValidationError):
        CombinedRequest(url="https://example.com", lang="x" * 100)


# ── Step 29: on-disk TTL eviction ─────────────────────────────────────────────


def _seed_job(job_id: str, output_dir: Path, *, age_s: float) -> None:
    """Insert a fake completed job into _jobs aged `age_s` seconds."""
    combined_store._jobs[job_id] = {
        "job_id": job_id,
        "status": "completed",
        "output_dir": str(output_dir),
        "_created_at": time.time() - age_s,
    }


@pytest.fixture
def output_root(tmp_path, monkeypatch):
    """Patch config to point input.output_dir at a tmp root."""
    root = tmp_path / "output"
    root.mkdir()
    monkeypatch.setattr(
        "ka11y.utils.config_loader.load_config",
        lambda: {"input": {"output_dir": str(root)}},
    )
    yield root
    # Clean up any state we leaked into _jobs.
    for jid in list(combined_store._jobs):
        if jid.startswith("ttl-test-"):
            combined_store._jobs.pop(jid, None)


def test_safe_rmtree_deletes_subdir_inside_root(output_root):
    target = output_root / "site_0513_1234_abc_combined"
    target.mkdir()
    (target / "report.json").write_text("{}")
    assert combined_store._safe_rmtree(target) is True
    assert not target.exists()


def test_safe_rmtree_refuses_path_outside_root(output_root, tmp_path):
    """Defence-in-depth: a poisoned output_dir pointing outside the
    configured root must NOT be deleted by eviction."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "evidence.txt").write_text("important")
    assert combined_store._safe_rmtree(outside) is False
    assert (outside / "evidence.txt").exists()


def test_orphan_sweep_removes_old_crawler_dir(output_root):
    """An AsyncImageCrawler sibling dir not referenced by any live job and
    older than the cutoff must be deleted."""
    sibling = output_root / "site_0513_1234"
    sibling.mkdir()
    (sibling / "img.png").write_bytes(b"\x89PNG")
    # Backdate mtime well past the cutoff.
    old = time.time() - 7200  # 2 hours ago
    import os

    os.utime(sibling, (old, old))

    cutoff = time.time() - 3600  # 1 hour ago
    removed = combined_store._evict_orphan_output_dirs(cutoff)
    assert removed >= 1
    assert not sibling.exists()


def test_orphan_sweep_keeps_live_referenced_dir(output_root):
    """A dir referenced by a live job must NOT be evicted by the orphan
    sweep, even if mtime is older than the cutoff."""
    live = output_root / "site_0513_1234_abc_combined"
    live.mkdir()
    old = time.time() - 7200
    import os

    os.utime(live, (old, old))

    _seed_job("ttl-test-live", live, age_s=60)

    cutoff = time.time() - 3600
    combined_store._evict_orphan_output_dirs(cutoff)
    assert live.exists(), "live-referenced dir was evicted"


def test_orphan_sweep_keeps_recent_dir(output_root):
    """A dir whose mtime is newer than the cutoff must NOT be evicted,
    even if no job references it."""
    fresh = output_root / "site_0513_1234"
    fresh.mkdir()

    cutoff = time.time() - 3600  # 1 hour ago — fresh dir mtime is now-ish
    combined_store._evict_orphan_output_dirs(cutoff)
    assert fresh.exists(), "recent dir was evicted"
