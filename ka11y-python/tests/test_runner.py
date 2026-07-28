"""
Unit tests for ka11y/api/v1/combined/runner.py

Covers:
  - P7: _run_python_stages() returning non-tuple handled gracefully
  - P7: _run_python_stages() returning a 2-tuple works correctly
  - _broadcast / _close_subscribers are now awaited (P6 fix)
  - Regression: CombinedRequest with only active fields does not raise
    AttributeError (guards against stale payload.run_* access after field removal)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


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

    job_id = "runner-test-non-tuple-EXPECTED-FAILURE"
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
    image_audit_report = {"images": []}

    from ka11y.api.v1.combined.stages import PythonStagesResult
    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(return_value=PythonStagesResult(
            findings=python_findings,
            contrast_report=contrast_report,
            image_audit_report=image_audit_report,
        )),
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

    job_id = "runner-test-exception-EXPECTED-FAILURE"
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
        )

        await _run_job(job_id, payload)

        job = store._jobs.get(job_id, {})
        # Job may complete (node findings available) or fail gracefully
        assert job.get("status") in ("completed", "failed")

    store._jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_run_job_forwards_success_criteria_id_to_node_and_python():
    from ka11y.api.v1.combined import store

    job_id = "runner-test-filter-forwarding"
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
        {"status": "pass", "wcag_sc": "1.1.1", "level": "A", "reason": "ok", "element": None}
    ]

    from ka11y.api.v1.combined.stages import PythonStagesResult
    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(return_value=PythonStagesResult(findings=[])),
    ) as run_python_stages, patch(
        "ka11y.api.v1.combined.runner._build_report",
        return_value={
            "summary": {"violations": 0, "needs_review": 0, "passes": 1},
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
            success_criteria_id="1.1.1",
        )

        await _run_job(job_id, payload)

        assert run_python_stages.await_args.kwargs["success_criteria_id"] == "1.1.1"

    store._jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# Regression: trimmed-schema guard
# Ensures that (a) CombinedRequest only has the currently active fields,
# (b) removed fields are truly absent (not silently defaulted), and
# (c) _run_job_body does not raise AttributeError when given a trimmed payload.
# This test class would have caught the original crash described in the bug report.
# ---------------------------------------------------------------------------


def test_combined_request_trimmed_schema_accepts_active_fields_only():
    """
    CombinedRequest must accept exactly the currently-active fields without
    raising a Pydantic validation error.  This is the positive side of the
    trimmed-schema guard.
    """
    from ka11y.api.v1.combined.models import CombinedRequest

    # All active fields — must not raise
    req = CombinedRequest(
        url="https://example.com",
        max_depth=0,
        internal_links=True,
        max_pages=10,
        wcag_level="AA",
        run_ocr=False,
        run_image_audit=True,
        run_media_audit=True,
        run_captions_audit=True,
        lang="en",
    )
    assert req.wcag_level == "AA"
    assert req.run_image_audit is True


def test_combined_request_removed_fields_raise_attribute_error():
    """
    Accessing any removed field on CombinedRequest must raise AttributeError,
    not silently return None/False.  This catches the class of bug where a
    stale payload.run_<removed_field> reference survives a field deletion and
    causes a crash only at runtime, not at import time.
    """
    from ka11y.api.v1.combined.models import CombinedRequest

    req = CombinedRequest(url="https://example.com")

    removed_fields = [
        "run_node_audit",
        "run_form_audit",
        "run_label_in_name_audit",
        "run_pause_stop_hide_audit",
        "run_target_size_audit",
        "run_resize_text_audit",
        "run_reflow_audit",
        "run_text_spacing_audit",
        "run_orientation_audit",
        "run_hover_focus_content_audit",
        "run_focus_not_obscured_min_audit",
        "run_focus_not_obscured_enh_audit",
        "run_sensory_audit",
        "run_consistent_navigation_audit",
        "run_consistent_id_audit",
        "run_unusual_words_audit",
        "run_section_headings_audit",
        "run_axe",
        "run_accesslint",
    ]
    for field in removed_fields:
        assert not hasattr(req, field), (
            f"CombinedRequest still exposes removed field '{field}'. "
            "Remove it from the model to prevent AttributeError at runtime."
        )


@pytest.mark.asyncio
async def test_run_job_body_trimmed_schema_no_attribute_error():
    """
    Regression test: _run_job_body must complete (or fail gracefully for
    expected reasons such as unreachable URLs) without raising AttributeError
    when given a CombinedRequest that uses only the currently-active fields.

    This test directly prevents the bug described in the issue:
        AttributeError: 'CombinedRequest' object has no attribute 'run_node_audit'
    """
    from ka11y.api.v1.combined import store
    from ka11y.api.v1.combined.models import CombinedRequest
    from ka11y.api.v1.combined.stages import PythonStagesResult

    job_id = "regression-trimmed-schema-no-attr-error"
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

    # Trimmed schema — only the currently active fields
    payload = CombinedRequest(
        url="https://example.com",
        run_ocr=False,
        run_image_audit=False,
        run_media_audit=False,
        run_captions_audit=False,
    )

    python_findings = [
        {"status": "fail", "wcag_sc": "1.1.1", "level": "A", "description": "Missing alt"}
    ]

    with patch(
        "ka11y.api.v1.combined.runner._run_python_stages",
        new=AsyncMock(return_value=PythonStagesResult(findings=python_findings)),
    ), patch(
        "ka11y.api.v1.combined.runner._fetch_node_findings",
        new=AsyncMock(return_value=[]),
    ), patch(
        "ka11y.api.v1.combined.runner._build_report",
        return_value={
            "summary": {"violations": 1, "needs_review": 0, "passes": 0},
            "findings": python_findings,
            "warnings": [],
        },
    ), patch(
        "ka11y.api.v1.combined.runner.load_config",
        return_value={"input": {"output_dir": "/tmp/ka11y-regression-test"}},
    ):
        from ka11y.api.v1.combined.runner import _run_job

        # Must not raise AttributeError at any point
        try:
            await _run_job(job_id, payload)
        except AttributeError as exc:
            raise AssertionError(
                f"_run_job raised AttributeError with trimmed schema — "
                f"stale payload.run_* access detected: {exc}"
            ) from exc

        job = store._jobs.get(job_id, {})
        # Job completed successfully (or failed for non-attribute reasons)
        assert job.get("status") in ("completed", "failed"), (
            f"Unexpected job status: {job.get('status')}"
        )
        if job.get("status") == "failed":
            assert "AttributeError" not in (job.get("error") or ""), (
                "Job failed with an AttributeError — stale payload.run_* reference detected."
            )

    store._jobs.pop(job_id, None)
