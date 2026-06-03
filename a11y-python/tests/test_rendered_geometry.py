"""
tests/test_rendered_geometry.py
================================
Unit tests for rendered-layout geometry helpers.
"""

import pytest
from a11y.accessibility.rendered.models import Rect
from a11y.accessibility.rendered.geometry import (
    intersection_area,
    overlap_ratio,
    has_intersection,
    is_clipped,
    is_offscreen,
    is_hidden,
    has_horizontal_scroll,
    text_container_overflows,
    document_has_horizontal_scroll,
    rect_from_dict,
)


def r(x, y, w, h) -> Rect:
    return Rect(x=x, y=y, width=w, height=h, top=y, left=x,
                bottom=y + h, right=x + w)


class TestIntersection:
    def test_full_overlap(self):
        a = r(0, 0, 100, 100)
        assert intersection_area(a, a) == pytest.approx(10_000)

    def test_no_overlap(self):
        assert intersection_area(r(0, 0, 50, 50), r(100, 0, 50, 50)) == 0.0

    def test_partial_overlap(self):
        a = r(0, 0, 100, 100)
        b = r(50, 50, 100, 100)
        assert intersection_area(a, b) == pytest.approx(2_500)

    def test_has_intersection_false(self):
        assert has_intersection(r(0, 0, 50, 50), r(60, 0, 50, 50)) is False

    def test_has_intersection_true(self):
        assert has_intersection(r(0, 0, 100, 100), r(50, 50, 100, 100)) is True


class TestOverlapRatio:
    def test_zero_area_target(self):
        assert overlap_ratio(r(0, 0, 0, 0), r(0, 0, 100, 100)) == 0.0

    def test_full_coverage(self):
        target = r(10, 10, 50, 50)
        overlay = r(0, 0, 200, 200)
        assert overlap_ratio(target, overlay) == pytest.approx(1.0)

    def test_half_coverage(self):
        target = r(0, 0, 100, 100)
        overlay = r(50, 0, 100, 100)
        assert overlap_ratio(target, overlay) == pytest.approx(0.5)

    def test_no_coverage(self):
        assert overlap_ratio(r(0, 0, 100, 100), r(200, 0, 100, 100)) == 0.0


class TestClipOffscreen:
    def test_is_clipped_right(self):
        el = r(1300, 0, 100, 50)
        assert is_clipped(el, 1280, 720) is True

    def test_not_clipped(self):
        el = r(100, 100, 200, 50)
        assert is_clipped(el, 1280, 720) is False

    def test_is_offscreen_below(self):
        el = r(0, 800, 100, 50)
        assert is_offscreen(el, 1280, 720) is True


class TestIsHidden:
    def test_hidden_display_none(self):
        assert is_hidden(True, 1.0, "none", "visible") is True

    def test_hidden_zero_opacity(self):
        assert is_hidden(True, 0.0, "block", "visible") is True

    def test_not_hidden(self):
        assert is_hidden(True, 1.0, "block", "visible") is False

    def test_hidden_visibility(self):
        assert is_hidden(True, 1.0, "block", "hidden") is True


class TestScrollHelpers:
    def test_horizontal_scroll_detected(self):
        assert has_horizontal_scroll(400, 300) is True

    def test_no_horizontal_scroll(self):
        assert has_horizontal_scroll(300, 300) is False

    def test_text_container_h_clip(self):
        h, v = text_container_overflows(400, 300, 100, 100, "hidden", "visible")
        assert h is True
        assert v is False

    def test_text_container_no_clip(self):
        h, v = text_container_overflows(300, 300, 100, 100, "hidden", "hidden")
        assert h is False
        assert v is False

    def test_document_scroll(self):
        assert document_has_horizontal_scroll(400, 320) is True
        assert document_has_horizontal_scroll(318, 320) is False


class TestRectFromDict:
    def test_basic(self):
        d = {"x": 10, "y": 20, "width": 100, "height": 50,
             "top": 20, "right": 110, "bottom": 70, "left": 10}
        rect = rect_from_dict(d)
        assert rect.width == 100
        assert rect.height == 50
        assert rect.right == 110