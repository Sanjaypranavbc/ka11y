from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from a11y.crawler.universal_page import PageSnapshot

# These three tests assert an obsolete snapshot-gating architecture:
#   * they expect ``max_depth`` to gate whether the universal snapshot is
#     loaded, but current ``_run_python_stages`` gates on
#     ``static_rules_enabled`` (any static rule) and merely passes ``max_depth``
#     through to the crawler;
#   * they patch the pre-``_universal`` stage functions (``_stage_form_audit``,
#     ``_stage_media_audit`` …), which ``_run_python_stages`` no longer calls —
#     it runs the ``*_universal`` variants plus ``_run_pipeline_stage``;
#   * they expect a 2-tuple return, but the function now returns a typed
#     ``PythonStagesResult`` and image audit yields a 3-tuple.
# Skipped pending a rewrite against the current control flow (see code-review.md
# §5). Were already failing before the B-1…B-12 work; not a regression.
_OBSOLETE_ARCH_REASON = (
    "asserts removed max_depth snapshot-gating + non-universal stage layout; "
    "needs rewrite against static_rules_enabled / *_universal stages"
)


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


@pytest.mark.skip(reason=_OBSOLETE_ARCH_REASON)
@pytest.mark.asyncio
async def test_run_python_stages_uses_snapshot_only_in_single_page_mode():
    from a11y.api.v1.combined.stages import _run_python_stages

    snapshot = PageSnapshot(
        page_url="https://example.com",
        har_path="/tmp/a11y-stage-test.har",
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
        "a11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(return_value=snapshot),
    ) as snapshot_load, patch(
        "a11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(side_effect=_image_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(side_effect=_rendered_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ):
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/a11y-stage-test"),
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


@pytest.mark.skip(reason=_OBSOLETE_ARCH_REASON)
@pytest.mark.asyncio
async def test_run_python_stages_skips_snapshot_for_multi_page_depth():
    from a11y.api.v1.combined.stages import _run_python_stages

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
        "a11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(),
    ) as snapshot_load, patch(
        "a11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(side_effect=_image_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(side_effect=_snapshot_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(side_effect=_rendered_stage),
    ), patch(
        "a11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(side_effect=_snapshot_stage),
    ):
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/a11y-stage-test"),
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


@pytest.mark.skip(reason=_OBSOLETE_ARCH_REASON)
@pytest.mark.asyncio
async def test_run_python_stages_skips_snapshot_when_filtered_to_image_rule():
    from a11y.api.v1.combined.stages import _run_python_stages

    with patch(
        "a11y.api.v1.combined.stages.UniversalPageLoader.load",
        new=AsyncMock(),
    ) as snapshot_load, patch(
        "a11y.api.v1.combined.stages._stage_image_audit",
        new=AsyncMock(return_value=([], None)),
    ) as image_stage, patch(
        "a11y.api.v1.combined.stages._stage_form_audit",
        new=AsyncMock(return_value=[]),
    ) as form_stage, patch(
        "a11y.api.v1.combined.stages._stage_label_in_name",
        new=AsyncMock(return_value=[]),
    ) as lin_stage, patch(
        "a11y.api.v1.combined.stages._stage_pause_stop_hide",
        new=AsyncMock(return_value=[]),
    ) as psh_stage, patch(
        "a11y.api.v1.combined.stages._stage_target_size",
        new=AsyncMock(return_value=[]),
    ) as ts_stage, patch(
        "a11y.api.v1.combined.stages._stage_text_spacing",
        new=AsyncMock(return_value=[]),
    ) as spacing_stage, patch(
        "a11y.api.v1.combined.stages._stage_rendered_layout_audit",
        new=AsyncMock(return_value=[]),
    ) as rendered_stage, patch(
        "a11y.api.v1.combined.stages._stage_media_audit",
        new=AsyncMock(return_value=[]),
    ) as media_stage:
        findings, contrast_report = await _run_python_stages(
            url="https://example.com",
            output_dir=Path("/tmp/a11y-stage-test"),
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


class TestNodeHttpTimeout:
    """``_node_http_timeout`` must scale the Node flat-call read timeout with
    the page count so snapshot-fed child crawls don't silently drop all axe
    findings when the crawl outlasts the old fixed 300 s ceiling.
    """

    def test_single_page_keeps_300s_floor(self):
        from a11y.api.v1.combined.stages import _node_http_timeout

        assert _node_http_timeout(1) == 300.0

    def test_small_crawl_below_floor_still_300s(self):
        from a11y.api.v1.combined.stages import _node_http_timeout

        # 3 pages * 75s + 60s base = 285s < 300s floor.
        assert _node_http_timeout(3) == 300.0

    def test_grows_with_page_count(self):
        from a11y.api.v1.combined.stages import _node_http_timeout

        # 13 pages already exceeds the old 300 s ceiling — the exact regime
        # where the iana repro (138 s / 6 pages) showed ~23 s/page.
        assert _node_http_timeout(13) > 300.0

    def test_capped_at_job_budget(self):
        from a11y.api.v1.combined.stages import (
            _node_http_timeout,
            _NODE_HTTP_TIMEOUT_CAP_SECONDS,
        )

        # 1000 pages would scale to ~75000s; must clamp to the job budget.
        assert _node_http_timeout(1000) == _NODE_HTTP_TIMEOUT_CAP_SECONDS

    def test_monotonic_non_decreasing(self):
        from a11y.api.v1.combined.stages import _node_http_timeout

        prev = 0.0
        for n in (1, 5, 10, 25, 50, 200, 5000):
            cur = _node_http_timeout(n)
            assert cur >= prev
            prev = cur
