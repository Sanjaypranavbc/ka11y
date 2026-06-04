"""
Sprint 3 / step 19: alpha-aware contrast engine.

The previous parser used ``re.findall(r"\\d+")`` which silently split the
"0.5" of ``rgba(255,0,0,0.5)`` into ``["0", "5"]`` and read those as the
G and B channels — producing the wrong contrast ratio for every
semi-transparent foreground. The fix:

  * parse rgba/hex with alpha,
  * Porter-Duff composite the foreground over the resolved background
    before measuring luminance,
  * accept the real ``font-weight`` already handled upstream in
    Policy143._is_large_text.
"""
from __future__ import annotations

import pytest

from ka11y.accessibility.pipeline.runners.contrast_engine import ContrastEngine


# ── parse_color ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "color, expected",
    [
        ("#000", (0, 0, 0, 1.0)),
        ("#fff", (255, 255, 255, 1.0)),
        ("#abc", (170, 187, 204, 1.0)),
        ("#ff0000", (255, 0, 0, 1.0)),
        ("#ff000080", (255, 0, 0, pytest.approx(128 / 255.0, rel=1e-3))),
        ("#f00f", (255, 0, 0, 1.0)),
        ("rgb(10, 20, 30)", (10, 20, 30, 1.0)),
        ("rgb(255,0,0)", (255, 0, 0, 1.0)),
        ("rgba(255,0,0,0.5)", (255, 0, 0, 0.5)),
        ("rgba(0, 0, 0, 0)", (0, 0, 0, 0.0)),
        ("rgba(120, 200, 50, 0.25)", (120, 200, 50, 0.25)),
    ],
)
def test_parse_color_roundtrip(color, expected):
    """Both opaque and alpha forms must yield the right tuple. The
    decimal alpha of rgba(...) used to fall victim to the `\\d+`-only
    regex; the new parser must preserve it."""
    result = ContrastEngine.parse_color(color)
    assert result[0] == expected[0]
    assert result[1] == expected[1]
    assert result[2] == expected[2]
    assert result[3] == expected[3]


def test_parse_color_clamps_out_of_range():
    """Defensive: malformed CSS can over- or under-shoot 0-255 and 0-1."""
    r, g, b, a = ContrastEngine.parse_color("rgba(999, -10, 200, 1.5)")
    assert r == 255
    assert g == 0
    assert b == 200
    assert a == 1.0


def test_parse_rgb_backcompat_shim_returns_three_tuple():
    assert ContrastEngine.parse_rgb("#ff0000") == (255, 0, 0)


# ── compositing ───────────────────────────────────────────────────────────


def test_composite_full_alpha_is_passthrough():
    assert ContrastEngine.composite_over((100, 150, 200, 1.0), (0, 0, 0)) == (
        100,
        150,
        200,
    )


def test_composite_zero_alpha_yields_background():
    assert ContrastEngine.composite_over((100, 150, 200, 0.0), (10, 20, 30)) == (
        10,
        20,
        30,
    )


def test_composite_half_alpha_red_over_white_is_pink():
    """rgba(255,0,0,0.5) over white should produce a near-pink (≈ 255,128,128).
    Used to round-trip through the buggy parser as (255,0,0) ignoring alpha
    entirely, giving an incorrectly *high* contrast against white text."""
    r, g, b = ContrastEngine.composite_over((255, 0, 0, 0.5), (255, 255, 255))
    assert r == 255
    assert 127 <= g <= 128
    assert 127 <= b <= 128


# ── ratio ─────────────────────────────────────────────────────────────────


def test_ratio_black_on_white_is_21():
    assert ContrastEngine.calculate_ratio("rgb(0,0,0)", "rgb(255,255,255)") == 21.0


def test_ratio_white_on_white_is_one():
    assert ContrastEngine.calculate_ratio("#fff", "#fff") == 1.0


def test_ratio_translucent_foreground_uses_composited_value():
    """Semi-transparent red on white should yield a lower ratio than the
    opaque-red baseline ratio of 4.0:1, because the composited pink is
    closer in luminance to white. The buggy parser produced the *opaque*
    ratio (~4:1) regardless of alpha."""
    opaque_ratio = ContrastEngine.calculate_ratio("rgb(255,0,0)", "rgb(255,255,255)")
    alpha_ratio = ContrastEngine.calculate_ratio(
        "rgba(255,0,0,0.5)", "rgb(255,255,255)"
    )
    assert alpha_ratio < opaque_ratio
    # And it must not be the buggy "treat alpha as a channel" result.
    assert alpha_ratio != opaque_ratio
