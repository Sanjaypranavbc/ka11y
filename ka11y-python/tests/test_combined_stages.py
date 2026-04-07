from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from ka11y.crawler.universal_page import PageSnapshot


def _stage_flags() -> dict:
    return {
        "run_ocr": False,
        "run_image_audit": False,
        "run_form_audit": True,
        "run_label_in_name_audit": True,
        "run_media_audit": True,
        "run_pause_stop_hide_audit": True,
        "run_target_size_audit": True,
        "run_resize_text_audit": False,
        "run_reflow_audit": False,
        "run_text_spacing_audit": True,
        "run_orientation_audit": False,
        "run_hover_focus_content_audit": False,
        "run_focus_not_obscured_min_audit": False,
        "run_focus_not_obscured_enh_audit": False,
    }


@pytest.mark.asyncio
async def test_run_python_stages_uses_snapshot_only_in_single_page_mode():
    from ka11y.api.v1.combined.stages import _run_python_stages

    snapshot = PageSnapshot(
        page_url="https://example.com",
        har_path="/tmp/ka11y-stage-test.har",
    )
    seen_snapshots: list[object] = []
    seen_har_paths: list[object] = []

    async def _image_stage(*args, **kwargs):
        return [], None

    async def _snapshot_stage(*args, **kwargs):
        seen_snapshots.append(kwargs.get("snapshot"))
        return []

    async def _rendered_stage(*args, **kwargs):
        seen_har_paths.append(kwargs.get("har_path"))
        return []

    with patch(
        "ka11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(return_value=snapshot),
    ) as snapshot_load, patch(
        "ka11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(side_effect=_image_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(side_effect=_rendered_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ):
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/ka11y-stage-test"),
            max_depth=0,
            job_id="job-single-page",
            lang="en",
            **_stage_flags(),
        )

    assert findings == []
    assert contrast_report is None
    snapshot_load.assert_awaited_once()
    assert seen_snapshots == [snapshot] * 6
    assert seen_har_paths == [snapshot.har_path]


@pytest.mark.asyncio
async def test_run_python_stages_skips_snapshot_for_multi_page_depth():
    from ka11y.api.v1.combined.stages import _run_python_stages

    seen_snapshots: list[object] = []
    seen_har_paths: list[object] = []

    async def _image_stage(*args, **kwargs):
        return [], None

    async def _snapshot_stage(*args, **kwargs):
        seen_snapshots.append(kwargs.get("snapshot"))
        return []

    async def _rendered_stage(*args, **kwargs):
        seen_har_paths.append(kwargs.get("har_path"))
        return []

    with patch(
        "ka11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(),
    ) as snapshot_load, patch(
        "ka11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(side_effect=_image_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(side_effect=_rendered_stage),
    ), patch(
        "ka11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ):
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/ka11y-stage-test"),
            max_depth=2,
            job_id="job-multi-page",
            lang="en",
            **_stage_flags(),
        )

    assert findings == []
    assert contrast_report is None
    snapshot_load.assert_not_awaited()
    assert seen_snapshots == [None] * 6
    assert seen_har_paths == [None]


@pytest.mark.asyncio
async def test_run_python_stages_skips_snapshot_when_filtered_to_image_rule():
    from ka11y.api.v1.combined.stages import _run_python_stages

    with patch(
        "ka11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(),
    ) as snapshot_load, patch(
        "ka11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(return_value=([], None)),
    ) as image_stage, patch(
        "ka11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(return_value=[]),
    ) as form_stage, patch(
        "ka11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(return_value=[]),
    ) as lin_stage, patch(
        "ka11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(return_value=[]),
    ) as psh_stage, patch(
        "ka11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(return_value=[]),
    ) as ts_stage, patch(
        "ka11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(return_value=[]),
    ) as spacing_stage, patch(
        "ka11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(return_value=[]),
    ) as rendered_stage, patch(
        "ka11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(return_value=[]),
    ) as media_stage:
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/ka11y-stage-test"),
            max_depth=0,
            job_id="job-image-only",
            lang="en",
            success_criteria_id="1.1.1",
            run_ocr=True,
            run_image_audit=True,
            run_form_audit=True,
            run_label_in_name_audit=True,
            run_media_audit=True,
            run_pause_stop_hide_audit=True,
            run_target_size_audit=True,
            run_resize_text_audit=True,
            run_reflow_audit=True,
            run_text_spacing_audit=True,
            run_orientation_audit=True,
            run_hover_focus_content_audit=True,
            run_focus_not_obscured_min_audit=True,
            run_focus_not_obscured_enh_audit=True,
        )

    assert findings == []
    assert contrast_report is None
    snapshot_load.assert_not_awaited()
    image_stage.assert_awaited_once()
    form_stage.assert_not_awaited()
    lin_stage.assert_not_awaited()
    psh_stage.assert_not_awaited()
    ts_stage.assert_not_awaited()
    spacing_stage.assert_not_awaited()
    rendered_stage.assert_not_awaited()
    media_stage.assert_not_awaited()
