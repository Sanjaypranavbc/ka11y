"""Tests for the per-run timing logger (logs/run_timings.log)."""

from __future__ import annotations

from a11y.utils import run_timing


def test_log_run_timing_writes_block(tmp_path, monkeypatch):
    log_file = tmp_path / "run_timings.log"
    monkeypatch.setenv("A11Y_RUN_TIMING_LOG", str(log_file))

    stages = [
        {
            "name": "axe_core",
            "status": "completed",
            "started_at": "2026-05-26T16:50:00+00:00",
            "completed_at": "2026-05-26T16:50:12.4+00:00",
            "findings_count": 42,
        },
        {
            "name": "image_audit",
            "status": "completed",
            "started_at": "2026-05-26T16:50:00+00:00",
            "completed_at": "2026-05-26T16:50:08+00:00",
            "findings_count": 8,
        },
    ]

    run_timing.log_run_timing(
        job_id="b5ea3ea7deadbeef",
        url="https://example.com",
        status="completed",
        stages=stages,
        submitted_at="2026-05-26T16:49:59+00:00",
        run_started_at="2026-05-26T16:50:00+00:00",
        completed_at="2026-05-26T16:50:13+00:00",
        lang="en",
        summary={
            "score": 92.6,
            "total_findings": 62,
            "violations": 4,
            "needs_review": 8,
            "passes": 50,
            "page_count": 1,
        },
    )

    text = log_file.read_text(encoding="utf-8")
    assert "job=b5ea3ea7" in text
    assert "status=completed" in text
    assert "axe_core" in text and "12.40s" in text          # per-stage duration
    assert "image_audit" in text and "8.00s" in text
    assert "WALL" in text and "14.00s" in text                # submitted→done
    assert "queue_wait" in text and "1.00s" in text           # submitted→start
    assert "score=92.6" in text


def test_log_run_timing_handles_missing_timestamps(tmp_path, monkeypatch):
    """A failed run with incomplete stages must still log (no exception)."""
    log_file = tmp_path / "run_timings.log"
    monkeypatch.setenv("A11Y_RUN_TIMING_LOG", str(log_file))

    run_timing.log_run_timing(
        job_id="failedjob",
        url="https://broken.example",
        status="failed",
        stages=[{"name": "axe_core", "status": "running", "started_at": "2026-05-26T16:50:00+00:00"}],
        submitted_at="2026-05-26T16:49:59+00:00",
        run_started_at="2026-05-26T16:50:00+00:00",
        completed_at=None,           # never completed
        error_stage="image_audit",
    )

    text = log_file.read_text(encoding="utf-8")
    assert "status=failed" in text
    assert "failed_stage=image_audit" in text
    assert "—" in text  # missing durations render as em dash, no crash
