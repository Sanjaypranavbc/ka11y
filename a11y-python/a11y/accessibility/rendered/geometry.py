"""
a11y/accessibility/rendered/geometry.py
=========================================
Reusable geometry and layout-analysis helpers.
All functions operate on plain dicts / Rect objects — no Playwright dependency.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from .models import Rect

# ── Rectangle helpers ─────────────────────────────────────────────────────────


def rect_from_dict(d: Dict[str, Any]) -> Rect:
    """Build a Rect from a getBoundingClientRect-style dict."""
    return Rect(
        x=float(d.get("x", 0)),
        y=float(d.get("y", 0)),
        width=float(d.get("width", 0)),
        height=float(d.get("height", 0)),
        top=float(d.get("top", 0)),
        right=float(d.get("right", 0)),
        bottom=float(d.get("bottom", 0)),
        left=float(d.get("left", 0)),
    )


def intersection_area(a: Rect, b: Rect) -> float:
    """Return the overlapping area between two rects (0 if no overlap)."""
    ix = max(0.0, min(a.right, b.right) - max(a.left, b.left))
    iy = max(0.0, min(a.bottom, b.bottom) - max(a.top, b.top))
    return ix * iy


def overlap_ratio(target: Rect, overlay: Rect) -> float:
    """
    Fraction of *target* that is covered by *overlay*.
    Returns 0.0 – 1.0.
    """
    if target.area == 0:
        return 0.0
    return min(1.0, intersection_area(target, overlay) / target.area)


def has_intersection(a: Rect, b: Rect) -> bool:
    """Return True if the two rects overlap at all."""
    return (
        a.left < b.right and a.right > b.left and a.top < b.bottom and a.bottom > b.top
    )


# ── Clip / overflow detection ─────────────────────────────────────────────────


def is_clipped(rect: Rect, viewport_width: int, viewport_height: int) -> bool:
    """
    Return True if the element rect is entirely outside the visible viewport
    horizontally (i.e. pushed offscreen to the right).
    """
    return rect.left >= viewport_width or rect.right <= 0


def is_offscreen(rect: Rect, viewport_width: int, viewport_height: int) -> bool:
    """Return True if the element is entirely outside the viewport in any direction."""
    return (
        rect.right <= 0
        or rect.bottom <= 0
        or rect.left >= viewport_width
        or rect.top >= viewport_height
    )


def is_hidden(visible: bool, opacity: float, display: str, visibility: str) -> bool:
    """Return True when computed style indicates the element is invisible."""
    if not visible:
        return True
    if opacity == 0:
        return True
    if display in ("none",):
        return True
    if visibility in ("hidden", "collapse"):
        return True
    return False


def has_horizontal_scroll(
    scroll_width: float, client_width: float, threshold: float = 5.0
) -> bool:
    """Return True when horizontal scrollbar content exceeds client width."""
    return scroll_width > client_width + threshold


def text_container_overflows(
    scroll_width: float,
    client_width: float,
    scroll_height: float,
    client_height: float,
    overflow_x: str,
    overflow_y: str,
) -> Tuple[bool, bool]:
    """
    Returns (h_overflow_clipped, v_overflow_clipped).
    Clipped means overflow is hidden and content overflows that axis.
    """
    h_clip = overflow_x in ("hidden", "clip") and scroll_width > client_width + 4
    v_clip = overflow_y in ("hidden", "clip") and scroll_height > client_height + 4
    return h_clip, v_clip


# ── Fixed / sticky overlay detection ─────────────────────────────────────────


def is_fixed_or_sticky(position: str) -> bool:
    return position in ("fixed", "sticky")


def is_covered_by_fixed(
    target: Rect,
    overlays: list,
    min_overlap_ratio: float = 0.5,
) -> Tuple[bool, float]:
    """
    Given a list of fixed/sticky overlay rects (plain dicts with x/y/w/h),
    return (is_covered, max_overlap_ratio).

    `overlays` items must have keys: x, y, width, height (top/right/bottom/left
    are derived).
    """
    best = 0.0
    for ov in overlays:
        r = Rect(
            x=float(ov.get("x", 0)),
            y=float(ov.get("y", 0)),
            width=float(ov.get("width", 0)),
            height=float(ov.get("height", 0)),
            top=float(ov.get("top", ov.get("y", 0))),
            left=float(ov.get("left", ov.get("x", 0))),
            bottom=float(ov.get("bottom", ov.get("y", 0) + ov.get("height", 0))),
            right=float(ov.get("right", ov.get("x", 0) + ov.get("width", 0))),
        )
        ratio = overlap_ratio(target, r)
        if ratio > best:
            best = ratio
    return best >= min_overlap_ratio, best


# ── Document-level scroll helpers ─────────────────────────────────────────────


def document_has_horizontal_scroll(
    doc_scroll_width: float, viewport_width: int, threshold: float = 5.0
) -> bool:
    """True if the document body is wider than the viewport (requires side-scroll)."""
    return doc_scroll_width > viewport_width + threshold
