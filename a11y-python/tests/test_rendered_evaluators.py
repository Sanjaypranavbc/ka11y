"""
tests/test_rendered_evaluators.py
===================================
Unit tests for rendered-layout evaluators using synthetic PageSnapshot
and FocusStep objects — no browser needed.
"""


from a11y.accessibility.rendered.models import (
    ElementSnapshot,
    FocusStep,
    HoverInteractionResult,
    PageSnapshot,
    Rect,
)
from a11y.accessibility.rendered.evaluators import (
    reflow as ev_reflow,
    text_spacing as ev_text_spacing,
    resize_text as ev_resize,
    orientation as ev_orientation,
    hover_focus_content as ev_hover,
    focus_not_obscured_minimum as ev_fnom,
    focus_not_obscured_enhanced as ev_fnoe,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _rect(x=0, y=0, w=100, h=50) -> Rect:
    return Rect(x=x, y=y, width=w, height=h, top=y, left=x,
                bottom=y + h, right=x + w)


def _el(**kwargs) -> ElementSnapshot:
    defaults = dict(
        tag="p", text="Hello world", html_snippet="<p>Hello world</p>",
        rect=_rect(), client_width=300, client_height=50,
        scroll_width=300, scroll_height=50,
        overflow_x="visible", overflow_y="visible",
        position="static", visible=True, focusable=False,
        fixed_or_sticky=False, text_clipped=False,
    )
    defaults.update(kwargs)
    return ElementSnapshot(**defaults)


def _snap(scenario="baseline", vw=1280, vh=720, elements=None,
          doc_scroll_w=None, **kwargs) -> PageSnapshot:
    if doc_scroll_w is None:
        doc_scroll_w = vw
    return PageSnapshot(
        scenario=scenario,
        page_url="https://example.com",
        viewport_width=vw,
        viewport_height=vh,
        document_scroll_width=doc_scroll_w,
        document_scroll_height=2000,
        body_scroll_width=doc_scroll_w,
        body_scroll_height=2000,
        has_horizontal_scroll=doc_scroll_w > vw + 5,
        elements=elements or [],
        **kwargs,
    )


# ── WCAG 1.4.10 Reflow ─────────────────────────────────────────────────────────


class TestReflow:
    def test_no_scroll_passes(self):
        snap = _snap(scenario="reflow_320", vw=320, vh=640, doc_scroll_w=318)
        records = ev_reflow.evaluate(snap)
        assert any(r.status == "PASSED" for r in records)
        assert not any(r.status == "FAILED" for r in records)

    def test_horizontal_scroll_fails(self):
        # Element extending beyond 320px viewport
        el = _el(tag="div", rect=_rect(x=0, y=0, w=500, h=50))
        snap = _snap(scenario="reflow_320", vw=320, vh=640,
                     doc_scroll_w=500, elements=[el])
        records = ev_reflow.evaluate(snap)
        assert any(r.status == "FAILED" for r in records)

    def test_exempt_table_needs_review(self):
        el = _el(tag="table", rect=_rect(x=0, y=0, w=600, h=200),
                 html_snippet="<table><tr><td>data</td></tr></table>")
        snap = _snap(scenario="reflow_320", vw=320, vh=640,
                     doc_scroll_w=600, elements=[el])
        records = ev_reflow.evaluate(snap)
        statuses = [r.status for r in records]
        # Should have needs_review, not plain FAILED for the table
        assert "NEEDS_REVIEW" in statuses


# ── WCAG 1.4.12 Text Spacing ───────────────────────────────────────────────────


class TestTextSpacing:
    def test_no_change_passes(self):
        el = _el(tag="p", text="Some text", text_clipped=False, element_id="p1")
        baseline = _snap(elements=[el])
        modified = _snap(scenario="text_spacing_override", elements=[el])
        records = ev_text_spacing.evaluate(baseline, modified)
        assert any(r.status == "PASSED" for r in records)

    def test_newly_clipped_fails(self):
        # Baseline: not clipped; modified: clipped
        el_base = _el(tag="p", text="Some longer text here", text_clipped=False,
                      element_id="para1", client_width=300, scroll_width=300)
        el_mod = _el(tag="p", text="Some longer text here", text_clipped=True,
                     element_id="para1", client_width=200, scroll_width=400,
                     overflow_x="hidden")
        baseline = _snap(elements=[el_base])
        modified = _snap(scenario="text_spacing_override", elements=[el_mod])
        records = ev_text_spacing.evaluate(baseline, modified)
        assert any(r.status == "FAILED" for r in records)


# ── WCAG 1.4.4 Resize Text ────────────────────────────────────────────────────


class TestResizeText:
    def test_no_change_passes(self):
        el = _el(tag="p", text="Text here", text_clipped=False, element_id="t1")
        baseline = _snap(elements=[el])
        resized = _snap(scenario="resize_text_200", elements=[el])
        records = ev_resize.evaluate(baseline, resized)
        assert any(r.status == "PASSED" for r in records)

    def test_scroll_introduced_fails(self):
        baseline = _snap(doc_scroll_w=1280, vw=1280)
        resized = _snap(scenario="resize_text_200", vw=1280, doc_scroll_w=1600)
        records = ev_resize.evaluate(baseline, resized)
        assert any(r.status == "FAILED" for r in records)

    def test_newly_clipped_text_fails(self):
        el_base = _el(tag="button", text="Submit", text_clipped=False,
                      element_id="btn1", client_width=100, scroll_width=100)
        el_mod = _el(tag="button", text="Submit", text_clipped=True,
                     element_id="btn1", client_width=60, scroll_width=120,
                     overflow_x="hidden")
        baseline = _snap(elements=[el_base])
        resized = _snap(scenario="resize_text_200", elements=[el_mod])
        records = ev_resize.evaluate(baseline, resized)
        assert any(r.status == "FAILED" for r in records)


# ── WCAG 1.3.4 Orientation ────────────────────────────────────────────────────


class TestOrientation:
    def _text_el(self, idx: int) -> ElementSnapshot:
        return _el(tag="p", text=f"Paragraph {idx} with enough text to count.", element_id=f"p{idx}")

    def test_no_issues_passes(self):
        # Both orientations have good content
        portrait_els = [self._text_el(i) for i in range(5)]
        landscape_els = [self._text_el(i) for i in range(5)]
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=portrait_els)
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=landscape_els)
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "PASSED" for r in records)

    def test_rotate_overlay_detected(self):
        overlay = _el(tag="div", text="Please rotate your device to landscape",
                      html_snippet="<div>Please rotate your device</div>")
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844,
                         elements=[overlay])
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390,
                          elements=[self._text_el(1)])
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def test_missing_content_needs_review(self):
        # landscape has almost no visible text
        portrait_els = [self._text_el(i) for i in range(5)]
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=[])
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=portrait_els)
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def _focusable_el(self, idx: int) -> ElementSnapshot:
        return _el(
            tag="a", text=f"Link {idx}", element_id=f"a{idx}",
            focusable=True, visible=True,
        )

    def test_zero_interactive_portrait_triggers_needs_review(self):
        """P10: portrait returns 0 interactive elements → NEEDS_REVIEW (no division)."""
        portrait = _snap(
            scenario="orientation_portrait", vw=390, vh=844, elements=[]
        )
        landscape_els = [self._focusable_el(i) for i in range(5)]
        landscape = _snap(
            scenario="orientation_landscape", vw=844, vh=390, elements=landscape_els
        )
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def test_zero_interactive_landscape_triggers_needs_review(self):
        """P10: landscape returns 0 interactive elements → NEEDS_REVIEW (hamburger menu)."""
        portrait_els = [self._focusable_el(i) for i in range(5)]
        portrait = _snap(
            scenario="orientation_portrait", vw=390, vh=844, elements=portrait_els
        )
        landscape = _snap(
            scenario="orientation_landscape", vw=844, vh=390, elements=[]
        )
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def test_zero_interactive_both_orientations_no_ratio_crash(self):
        """P10: both orientations have 0 interactive elements — must not crash with ZeroDivisionError.
        When both counts are zero it is not a meaningful asymmetry, so no NEEDS_REVIEW for the ratio.
        """
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=[])
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=[])
        # Should not raise
        records = ev_orientation.evaluate(portrait, landscape)
        assert isinstance(records, list)
        # No ratio-related NEEDS_REVIEW when both are zero (no asymmetry)
        ratio_violations = [
            r for r in records
            if r.status == "NEEDS_REVIEW" and "interactive elements" in (r.violation or "")
        ]
        assert len(ratio_violations) == 0

    def test_equal_interactive_counts_no_ratio_issue(self):
        """Equal counts → ratio = 1.0 → no issue flagged for ratio check."""
        els = [self._focusable_el(i) for i in range(4)]
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=els)
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=els)
        records = ev_orientation.evaluate(portrait, landscape)
        # Should pass (no ratio violation)
        ratio_violations = [
            r for r in records
            if r.status == "NEEDS_REVIEW" and "Dramatic difference" in (r.violation or "")
        ]
        assert len(ratio_violations) == 0

    def test_landscape_introduces_horizontal_scroll(self):
        """Layout breaks on rotation — horizontal overflow appears only in landscape."""
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, doc_scroll_w=390)
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, doc_scroll_w=1200)
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" and "horizontal scrolling" in (r.violation or "") for r in records)

    def test_dramatic_ratio_flags_needs_review(self):
        """Portrait has 10 interactive elements, landscape has only 2 → ratio 0.2 < 0.5."""
        portrait_els = [self._focusable_el(i) for i in range(10)]
        landscape_els = [self._focusable_el(i) for i in range(2)]
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=portrait_els)
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=landscape_els)
        records = ev_orientation.evaluate(portrait, landscape)
        assert any("Dramatic difference" in (r.violation or "") for r in records)

    def test_css_transform_lock_detected(self):
        """Element with rotate transform on body → NEEDS_REVIEW."""
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=[], body_transform="matrix(0, 1, -1, 0, 0, 0)")
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=[])
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" and "CSS rotation transform" in (r.violation or "") for r in records)

    def test_portrait_only_overlay_in_landscape(self):
        """'Portrait only' overlay appears in landscape → NEEDS_REVIEW."""
        overlay = _el(tag="div", text="Portrait only. Turn your phone.")
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=[])
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=[overlay])
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" and "rotate-device overlay" in (r.violation or "") for r in records)

    def test_body_overflow_hidden_detected(self):
        """Body has overflow hidden → NEEDS_REVIEW."""
        portrait = _snap(scenario="orientation_portrait", vw=390, vh=844, elements=[], body_overflow_x="hidden")
        landscape = _snap(scenario="orientation_landscape", vw=844, vh=390, elements=[])
        records = ev_orientation.evaluate(portrait, landscape)
        assert any(r.status == "NEEDS_REVIEW" and "overflow: hidden or clip" in (r.violation or "") for r in records)


# ── WCAG 1.4.13 Content on Hover or Focus ─────────────────────────────────────


class TestHoverFocusContent:
    def test_no_interactions_passes(self):
        records = ev_hover.evaluate([])
        assert any(r.status == "PASSED" for r in records)

    def test_no_popup_no_issue(self):
        interactions = [HoverInteractionResult(
            trigger_tag="button", page_url="https://example.com",
            popup_appeared=False,
        )]
        records = ev_hover.evaluate(interactions)
        assert any(r.status == "PASSED" for r in records)

    def test_non_dismissible_popup_flagged(self):
        interactions = [HoverInteractionResult(
            trigger_tag="button", trigger_id="btn1",
            page_url="https://example.com",
            popup_appeared=True,
            dismissible_by_escape=False,
            pointer_can_move_over=True,
            certain=True,
        )]
        records = ev_hover.evaluate(interactions)
        assert any(r.status in ("FAILED", "NEEDS_REVIEW") for r in records)

    def test_non_hoverable_popup_flagged(self):
        interactions = [HoverInteractionResult(
            trigger_tag="a", page_url="https://example.com",
            popup_appeared=True,
            dismissible_by_escape=True,
            pointer_can_move_over=False,
            certain=False,
        )]
        records = ev_hover.evaluate(interactions)
        assert any(r.status in ("FAILED", "NEEDS_REVIEW") for r in records)

    def test_all_three_checks_true_returns_passed(self):
        interactions = [HoverInteractionResult(
            trigger_tag="button", trigger_id="ok",
            page_url="https://example.com",
            popup_appeared=True,
            dismissible_by_escape=True,
            pointer_can_move_over=True,
            persists_until_removed=True,
            certain=True,
        )]
        records = ev_hover.evaluate(interactions)
        assert any(r.status == "PASSED" for r in records)

    def test_unknown_checks_return_needs_review(self):
        interactions = [HoverInteractionResult(
            trigger_tag="button", trigger_id="maybe",
            page_url="https://example.com",
            popup_appeared=True,
            dismissible_by_escape=True,
            pointer_can_move_over=True,
            persists_until_removed=None,
            certain=False,
        )]
        records = ev_hover.evaluate(interactions)
        assert any(r.status == "NEEDS_REVIEW" for r in records)


# ── WCAG 2.4.11 Focus Not Obscured (Minimum) ─────────────────────────────────


class TestFocusNotObscuredMinimum:
    def _step(self, ratio, idx=0) -> FocusStep:
        return FocusStep(
            step_index=idx, tag="a", page_url="https://example.com",
            rect=_rect(x=0, y=50, w=200, h=30),
            obscuration_ratio=ratio,
            fully_obscured=ratio >= 0.95,
            partially_obscured=0.10 <= ratio < 0.95,
            covering_elements=[{"tag": "header"}] if ratio > 0 else [],
        )

    def test_no_steps_passes(self):
        records = ev_fnom.evaluate([])
        assert any(r.status == "PASSED" for r in records)

    def test_not_obscured_passes(self):
        records = ev_fnom.evaluate([self._step(0.0)])
        assert any(r.status == "PASSED" for r in records)

    def test_fully_obscured_fails(self):
        records = ev_fnom.evaluate([self._step(0.97)])
        assert any(r.status == "FAILED" for r in records)

    def test_partially_obscured_needs_review(self):
        records = ev_fnom.evaluate([self._step(0.5)])
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def test_small_overlap_passes_minimum(self):
        # 2.4.11 only fails on *full* obscuration (>= 95%)
        records = ev_fnom.evaluate([self._step(0.5)])
        # 50% overlap → needs_review for 2.4.11 (not a hard fail)
        statuses = {r.status for r in records}
        assert "FAILED" not in statuses or "NEEDS_REVIEW" in statuses

    def test_94_percent_obscuration_is_needs_review_not_fail(self):
        """P9 boundary: 94% < 95% threshold → NEEDS_REVIEW, not FAIL."""
        records = ev_fnom.evaluate([self._step(0.94)])
        statuses = {r.status for r in records}
        assert "NEEDS_REVIEW" in statuses
        assert "FAILED" not in statuses

    def test_95_percent_obscuration_is_fail(self):
        """P9 boundary: 95% >= threshold → FAIL."""
        records = ev_fnom.evaluate([self._step(0.95)])
        assert any(r.status == "FAILED" for r in records)

    def test_96_percent_obscuration_is_fail(self):
        """P9 boundary: 96% > threshold → FAIL."""
        records = ev_fnom.evaluate([self._step(0.96)])
        assert any(r.status == "FAILED" for r in records)

    def test_9_percent_obscuration_passes_minimum(self):
        """P9 boundary: 9% < 10% partial threshold → PASSED (not NEEDS_REVIEW)."""
        records = ev_fnom.evaluate([self._step(0.09)])
        statuses = {r.status for r in records}
        assert "FAILED" not in statuses
        assert "NEEDS_REVIEW" not in statuses

    def test_10_percent_obscuration_is_needs_review(self):
        """P9 boundary: 10% >= partial threshold → NEEDS_REVIEW."""
        records = ev_fnom.evaluate([self._step(0.10)])
        assert any(r.status == "NEEDS_REVIEW" for r in records)


# ── WCAG 2.4.12 Focus Not Obscured (Enhanced) ────────────────────────────────


class TestFocusNotObscuredEnhanced:
    def _step(self, ratio, idx=0) -> FocusStep:
        return FocusStep(
            step_index=idx, tag="button", page_url="https://example.com",
            rect=_rect(x=0, y=50, w=120, h=44),
            obscuration_ratio=ratio,
            fully_obscured=ratio >= 0.95,
            partially_obscured=0.10 <= ratio < 0.95,
            covering_elements=[{"tag": "div", "id": "sticky-bar"}] if ratio > 0 else [],
        )

    def test_no_steps_passes(self):
        records = ev_fnoe.evaluate([])
        assert any(r.status == "PASSED" for r in records)

    def test_zero_overlap_passes(self):
        records = ev_fnoe.evaluate([self._step(0.0)])
        assert any(r.status == "PASSED" for r in records)

    def test_ten_percent_fails(self):
        # 2.4.12 is stricter — any non-trivial overlap should fail
        records = ev_fnoe.evaluate([self._step(0.15)])
        assert any(r.status == "FAILED" for r in records)

    def test_tiny_overlap_needs_review(self):
        records = ev_fnoe.evaluate([self._step(0.03)])
        assert any(r.status == "NEEDS_REVIEW" for r in records)

    def test_full_obscuration_fails(self):
        records = ev_fnoe.evaluate([self._step(1.0)])
        assert any(r.status == "FAILED" for r in records)
