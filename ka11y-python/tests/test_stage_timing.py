from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from ka11y.utils import stage_timing


@pytest.fixture
def run_id_and_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path]:
    monkeypatch.setenv("KA11Y_STAGE_TIMING_DIR", str(tmp_path))
    monkeypatch.delenv("KA11Y_STAGE_TIMING_DISABLE", raising=False)
    return ("test-run-001", tmp_path)


def test_record_writes_jsonl_row(run_id_and_dir):
    run_id, tmp = run_id_and_dir
    stage_timing.record(
        run_id,
        stage="image_audit",
        duration_ms=12.5,
        page_url="https://a.com",
        rule="1.4.3",
        item_count=7,
    )
    path = tmp / f"{run_id}.jsonl"
    assert path.exists()
    line = path.read_text().strip()
    row = json.loads(line)
    assert row["stage"] == "image_audit"
    assert row["page_url"] == "https://a.com"
    assert row["rule"] == "1.4.3"
    assert row["duration_ms"] == 12.5
    assert row["item_count"] == 7
    assert row["status"] == "ok"


def test_time_stage_sync_records_on_exit(run_id_and_dir):
    run_id, tmp = run_id_and_dir
    with stage_timing.time_stage(run_id, "ocr", rule="1.4.6"):
        pass
    rows = (tmp / f"{run_id}.jsonl").read_text().strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["stage"] == "ocr"


def test_time_stage_async_records_on_exception(run_id_and_dir):
    run_id, tmp = run_id_and_dir

    async def go():
        async with stage_timing.time_stage_async(run_id, "boom"):
            raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        asyncio.run(go())
    row = json.loads((tmp / f"{run_id}.jsonl").read_text().strip())
    assert row["status"] == "error"
    assert "kaboom" in row["error"]


def test_disabled_env_skips_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KA11Y_STAGE_TIMING_DIR", str(tmp_path))
    monkeypatch.setenv("KA11Y_STAGE_TIMING_DISABLE", "1")
    stage_timing.record("any-run", stage="x", duration_ms=1.0)
    assert list(tmp_path.iterdir()) == []


def test_emit_summary_produces_readable_log(run_id_and_dir):
    run_id, tmp = run_id_and_dir
    stage_timing.record(
        run_id, stage="image_audit", duration_ms=100.0,
        page_url="https://a.com", rule="1.4.3",
    )
    stage_timing.record(
        run_id, stage="image_audit", duration_ms=200.0,
        page_url="https://a.com/b", rule="1.4.3",
    )
    stage_timing.record(
        run_id, stage="form_audit", duration_ms=50.0,
        page_url="https://a.com", rule="3.3.1",
    )
    out = stage_timing.emit_summary(run_id)
    assert out is not None and out.exists()
    text = out.read_text()
    assert "Stage totals" in text
    assert "image_audit" in text
    assert "form_audit" in text
    assert "https://a.com" in text
    assert "https://a.com/b" in text


def test_safe_run_id_strips_traversal(run_id_and_dir):
    _, tmp = run_id_and_dir
    # A malicious run_id with path traversal must not escape the timings dir.
    # The sanitizer strips path separators (and any non-alnum/-/_/. char), so
    # the only path components a caller can produce are siblings of the dir.
    bad = "../../../etc/passwd"
    stage_timing.record(bad, stage="x", duration_ms=1.0)
    written = list(tmp.iterdir())
    assert written, "expected at least one file written"
    assert all(p.parent == tmp for p in written)
    # No path separator can survive the sanitizer.
    assert all("/" not in p.name and "\\" not in p.name for p in written)
