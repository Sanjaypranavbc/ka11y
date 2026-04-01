"""
ka11y/accessibility/rendered/heuristics.py
==========================================
High-level heuristic helpers that combine geometry and semantic signals
to detect accessibility issues.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .geometry import (
    document_has_horizontal_scroll,
    has_horizontal_scroll,
    is_fixed_or_sticky,
    overlap_ratio,
    text_container_overflows,
)
from .models import ElementSnapshot, PageSnapshot, Rect

# Regex for rotate-device gatekeeper overlay text
_ROTATE_RE = re.compile(
    r"rotate\s+(your\s+)?device|landscape\s+only|portrait\s+only|"
    r"please\s+rotate|turn\s+your\s+phone|works\s+best\s+in\s+(landscape|portrait)",
    re.IGNORECASE,
)


def detect_page_horizontal_scroll(snapshot: PageSnapshot) -> bool:
    """True when the page requires horizontal scrolling at its viewport width."""
    return document_has_horizontal_scroll(
        snapshot.document_scroll_width, snapshot.viewport_width
    )


def find_clipped_text_elements(
    snapshot: PageSnapshot,
    min_text_length: int = 3,
) -> List[ElementSnapshot]:
    """Return elements whose text is likely clipped by overflow: hidden."""
    clipped = []
    for el in snapshot.elements:
        if not el.text or len(el.text) < min_text_length:
            continue
        h_clip, v_clip = text_container_overflows(
            el.scroll_width,
            el.client_width,
            el.scroll_height,
            el.client_height,
            el.overflow_x,
            el.overflow_y,
        )
        if h_clip or v_clip:
            clipped.append(el)
    return clipped


def find_fixed_sticky_overlays(snapshot: PageSnapshot) -> List[ElementSnapshot]:
    """Return elements with position: fixed or sticky."""
    return [el for el in snapshot.elements if el.fixed_or_sticky]


def detect_rotate_overlay(snapshot: PageSnapshot) -> Optional[ElementSnapshot]:
    """
    Return the first element that looks like a rotate-device blocking overlay,
    or None.
    """
    for el in snapshot.elements:
        if el.text and _ROTATE_RE.search(el.text):
            return el
    return None


def detect_missing_main_content(snapshot: PageSnapshot) -> bool:
    """
    Heuristic: True if the snapshot has very few visible text-bearing elements,
    suggesting the main content is hidden/missing for this orientation.
    """
    visible_text = [
        el
        for el in snapshot.elements
        if el.visible
        and el.text
        and len(el.text.strip()) > 20
        and el.tag in ("p", "span", "h1", "h2", "h3", "li", "td", "article", "main")
    ]
    return len(visible_text) < 3


def detect_css_transform_lock(snapshot: PageSnapshot) -> bool:
    """
    True if the body has a CSS rotation transform, often used to 
    force orientation via a CSS/JS hack instead of native capabilities.
    """
    transform = snapshot.body_transform.strip().lower()
    return "matrix(" in transform or "rotate(" in transform


def detect_body_overflow_hidden(snapshot: PageSnapshot) -> bool:
    """
    True if document body has overflow:hidden or overflow-x:hidden,
    which could clip content when rotated if the layout isn't fluid.
    """
    ox = snapshot.body_overflow_x.strip().lower()
    return ox in ("hidden", "clip")


def detect_landscape_horizontal_overflow(portrait: PageSnapshot, landscape: PageSnapshot) -> bool:
    """
    True if landscape snapshot has a horizontal scroll but portrait doesn't.
    This often indicates the layout broke when rotated sideways.
    """
    return landscape.has_horizontal_scroll and not portrait.has_horizontal_scroll


def elements_with_horizontal_overflow(
    snapshot: PageSnapshot,
) -> List[ElementSnapshot]:
    """Return elements that overflow horizontally beyond the viewport."""
    result = []
    for el in snapshot.elements:
        if not el.visible:
            continue
        if el.rect.right > snapshot.viewport_width + 10:
            result.append(el)
    return result


def compute_obscuration(
    focus_rect: Rect,
    overlay_rects: List[Dict[str, Any]],
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Compute the maximum overlap ratio of the focus rect against a list of
    overlay rects.

    Returns (max_ratio, covering_overlays).
    """
    covering = []
    best = 0.0
    for ov in overlay_rects:
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
        ratio = overlap_ratio(focus_rect, r)
        if ratio > 0.05:
            covering.append({**ov, "_overlap_ratio": round(ratio, 3)})
        if ratio > best:
            best = ratio
    return best, covering
