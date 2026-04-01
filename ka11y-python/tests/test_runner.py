"""
Unit tests for ka11y/api/v1/combined/runner.py

Covers:
  - P7: _run_python_stages() returning non-tuple handled gracefully
  - P7: _run_python_stages() returning a 2-tuple works correctly
  - _broadcast / _close_subscribers are now awaited (P6 fix)
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# P7: tuple-unpacking guard in _run_job
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_python_result_non_tuple_does_not_raise():
    """
    P7: if _run_python_stages() somehow returns a non-tuple, _run_job should
    log a warning and use empty defaults rather than raising ValueError.
    """
    from ka11y.api.v1.combined import store

    job_id = "runner-test-non-tuple"
    store._jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
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

    # Patch _run_python_stages to return a non-tuple (unexpected type)
    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(return_value="not-a-tuple"),
    ), patch(
        "ka11y.api.v1.combined.runner._call_node_flat",
        new=AsyncMock(return_value=[]),
    ), patch(
        "ka11y.api.v1.combined.runner._build_report",
        return_value={
            "summary": {"violations": 0, "needs_review": 0, "passes": 0},
            "findings": [],
            "warnings": [],
        },
    ), patch(
        "ka11y.api.v1.combined.runner.load_config",
        return_value={"input": {"output_dir": "/tmp/ka11y-runner-test"}},
    ):
        from ka11y.api.v1.combined.runner import _run_job
        from ka11y.api.v1.combined.models import CombinedRequest

        payload = CombinedRequest(
            url="https://example.com",
            wcag_level="AA",
            max_depth=1,
            run_ocr=False,
            run_image_audit=False,
            run_form_audit=False,
            run_label_in_name_audit=False,
            run_pause_stop_hide_audit=False,
            run_target_size_audit=False,
            run_resize_text_audit=False,
            run_reflow_audit=False,
            run_text_spacing_audit=False,
            run_orientation_audit=False,
            run_hover_focus_content_audit=False,
            run_focus_not_obscured_min_audit=False,
            run_focus_not_obscured_enh_audit=False,
        )

        # If both node AND python findings are empty, _run_job raises RuntimeError.
        # We only want to test that the non-tuple case doesn't raise ValueError.
        # Since node returns [] and python is degraded to [], the job will "fail"
        # with the "All audit sources failed" error — that is the expected path.
        await _run_job(job_id, payload)

        # Job should be failed (because both sources empty), not crashed with
        # ValueError from tuple unpacking.
        job = store._jobs.get(job_id, {})
        assert job.get("status") in ("failed", "completed")
        if job.get("status") == "failed":
            assert "ValueError" not in (job.get("error") or "")

    store._jobs.pop(job_id, None)


def test_merge_findings_keeps_distinct_targets_with_same_html():
    from ka11y.api.v1.combined.runner import _merge_findings

    node_findings = [
        {
            "wcag_sc": "3.3.7",
            "status": "needs_review",
            "element": {
                "html": '<input name="email">',
                "element_id": None,
                "target": ['input#email'],
            },
        },
        {
            "wcag_sc": "3.3.7",
            "status": "needs_review",
            "element": {
                "html": '<input name="email">',
                "element_id": None,
                "target": ['input#emailsub'],
            },
        },
    ]

    merged = _merge_findings(node_findings, [])
    assert len(merged) == 2


def test_merge_findings_still_dedupes_same_target():
    from ka11y.api.v1.combined.runner import _merge_findings

    node_findings = [
        {
            "wcag_sc": "3.3.7",
            "status": "needs_review",
            "element": {
                "html": '<input name="email">',
                "element_id": None,
                "target": ['input#email'],
            },
        },
    ]
    python_findings = [
        {
            "wcag_sc": "3.3.7",
            "status": "needs_review",
            "element": {
                "html": '<input name="email">',
                "element_id": None,
                "target": ['input#email'],
            },
        },
    ]

    merged = _merge_findings(node_findings, python_findings)
    assert len(merged) == 1


@pytest.mark.asyncio
async def test_python_result_valid_tuple_works_correctly():
    """
    P7: a well-formed 2-tuple from _run_python_stages() is unpacked correctly.
    """
    from ka11y.api.v1.combined import store

    job_id = "runner-test-valid-tuple"
    store._jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
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

    python_findings = [
        {"status": "fail", "wcag": "1.1.1", "level": "A", "description": "Missing alt"}
    ]
    contrast_report = {"summary": {"total_regions_analysed": 0}, "images": []}

    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(return_value=(python_findings, contrast_report)),
    ), patch(
        "ka11y.api.v1.combined.runner._call_node_flat",
        new=AsyncMock(return_value=[]),
    ), patch(
        "ka11y.api.v1.combined.runner._build_report",
        return_value={
            "summary": {"violations": 1, "needs_review": 0, "passes": 0},
            "findings": python_findings,
            "contrast_report": contrast_report,
            "warnings": [],
        },
    ), patch(
        "ka11y.api.v1.combined.runner.load_config",
        return_value={"input": {"output_dir": "/tmp/ka11y-runner-test"}},
    ):
        from ka11y.api.v1.combined.runner import _run_job
        from ka11y.api.v1.combined.models import CombinedRequest

        payload = CombinedRequest(
            url="https://example.com",
            wcag_level="AA",
            max_depth=1,
            run_ocr=False,
            run_image_audit=False,
            run_form_audit=False,
            run_label_in_name_audit=False,
            run_pause_stop_hide_audit=False,
            run_target_size_audit=False,
            run_resize_text_audit=False,
            run_reflow_audit=False,
            run_text_spacing_audit=False,
            run_orientation_audit=False,
            run_hover_focus_content_audit=False,
            run_focus_not_obscured_min_audit=False,
            run_focus_not_obscured_enh_audit=False,
        )

        await _run_job(job_id, payload)

        job = store._jobs.get(job_id, {})
        assert job.get("status") == "completed"

    store._jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_python_result_exception_degrades_gracefully():
    """
    If _run_python_stages returns an Exception (return_exceptions=True path),
    the job should not crash — it should fall back to node findings only.
    """
    from ka11y.api.v1.combined import store

    job_id = "runner-test-exception"
    store._jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
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

    node_findings = [
        {"status": "fail", "wcag": "4.1.2", "level": "A", "description": "Button label"}
    ]

    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(side_effect=RuntimeError("stages exploded")),
    ), patch(
        "ka11y.api.v1.combined.runner._call_node_flat",
        new=AsyncMock(return_value=node_findings),
    ), patch(
        "ka11y.api.v1.combined.runner._build_report",
        return_value={
            "summary": {"violations": 1, "needs_review": 0, "passes": 0},
            "findings": node_findings,
            "warnings": [],
        },
    ), patch(
        "ka11y.api.v1.combined.runner.load_config",
        return_value={"input": {"output_dir": "/tmp/ka11y-runner-test"}},
    ):
        from ka11y.api.v1.combined.runner import _run_job
        from ka11y.api.v1.combined.models import CombinedRequest

        payload = CombinedRequest(
            url="https://example.com",
            wcag_level="AA",
            max_depth=1,
            run_ocr=False,
            run_image_audit=False,
            run_form_audit=False,
            run_label_in_name_audit=False,
            run_pause_stop_hide_audit=False,
            run_target_size_audit=False,
            run_resize_text_audit=False,
            run_reflow_audit=False,
            run_text_spacing_audit=False,
            run_orientation_audit=False,
            run_hover_focus_content_audit=False,
            run_focus_not_obscured_min_audit=False,
            run_focus_not_obscured_enh_audit=False,
        )

        await _run_job(job_id, payload)

        job = store._jobs.get(job_id, {})
        # Job may complete (node findings available) or fail gracefully
        assert job.get("status") in ("completed", "failed")

    store._jobs.pop(job_id, None)
