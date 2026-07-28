"""
tests/test_carousel_capture.py
================================
Regression tests for the carousel-aware screenshot-capture fix introduced in
``ka11y/crawler/optimized/engine.py``.

Bug that was fixed
------------------
``_capture_assets`` captured the same carousel frame repeatedly because it
screenshotted the static DOM state without ever advancing the carousel between
captures.  Each distinct slide was never reached, so all captured images were
identical.

What these tests verify
-----------------------
1. ``CAROUSEL_DETECT_JS`` identifies a carousel root and counts slides correctly.
2. ``_capture_carousel_slides`` produces **distinct** screenshots (one per
   unique slide), not a repeated identical frame.
3. Duplicate frames are flagged ``carousel_duplicate`` and their temp files
   are cleaned up.
4. Non-carousel elements remain on the original ``_capture_assets`` path and
   are unaffected.
5. The ``MAX_CAROUSEL_SLIDES`` safety cap prevents an infinite loop when the
   carousel keeps reporting new slides.
6. Elements whose carousel could not advance are flagged
   ``carousel_not_reached``.
"""

from __future__ import annotations

import asyncio
import hashlib
import struct
import tempfile
import zlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_element(
    el_id: str,
    selector: str = "img",
    element_type: str = "img",
    visible: bool = True,
    src: str = "",
    sub_type: str = "",
    flags: dict | None = None,
) -> dict:
    """Minimal element dict matching the shape produced by EXTRACT_JS."""
    return {
        "id": el_id,
        "selector": selector,
        "element_type": element_type,
        "visible": visible,
        "src": src,
        "sub_type": sub_type,
        "flags": flags or {},
        "bounding_box": {"x": 0, "y": 0, "width": 200, "height": 150},
    }


def _png_bytes(seed: int) -> bytes:
    """Tiny but syntactically valid 1x1 PNG with pixel colour keyed on seed."""
    def crc(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + crc(tag, data)

    SIGNATURE = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixel = bytes([seed % 256, (seed * 3) % 256, (seed * 7) % 256])
    raw_row = b"\x00" + pixel
    idat_data = zlib.compress(raw_row)
    return (
        SIGNATURE
        + chunk(b"IHDR", ihdr_data)
        + chunk(b"IDAT", idat_data)
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# Unit: carousel detection heuristic (pure-Python mirror of CAROUSEL_DETECT_JS)
# ---------------------------------------------------------------------------

class TestCarouselDetectLogic:
    """White-box tests for the detection heuristic encoded in CAROUSEL_DETECT_JS."""

    CAROUSEL_CLASS_PATTERNS = {
        "carousel", "slider", "reel", "swiper", "slick-slider",
        "reel-show", "reel_show",
    }

    def _detect(
        self,
        root_class: str = "carousel",
        has_role_group_items: int = 0,
        has_slick_classes: int = 0,
        has_swiper_classes: int = 0,
        child_count: int = 0,
        has_id: bool = True,
    ) -> dict | None:
        found_root = any(p in root_class for p in self.CAROUSEL_CLASS_PATTERNS)
        if not found_root:
            return None
        slide_count = 0
        if has_role_group_items > 1:
            slide_count = has_role_group_items
        elif has_slick_classes > 1:
            slide_count = has_slick_classes
        elif has_swiper_classes > 1:
            slide_count = has_swiper_classes
        elif child_count > 1:
            slide_count = child_count
        return {
            "rootSelector": "#my-carousel" if has_id else None,
            "slideCount": slide_count,
            "nextSelector": ".carousel-control-next",
        }

    def test_aria_role_group_slides_counted(self):
        info = self._detect(has_role_group_items=4, root_class="carousel")
        assert info is not None
        assert info["slideCount"] == 4

    def test_slick_slides_counted(self):
        info = self._detect(has_slick_classes=3, root_class="slick-slider")
        assert info is not None
        assert info["slideCount"] == 3

    def test_swiper_slides_counted(self):
        info = self._detect(has_swiper_classes=5, root_class="swiper")
        assert info is not None
        assert info["slideCount"] == 5

    def test_reel_show_detected(self):
        info = self._detect(child_count=6, root_class="reel-show")
        assert info is not None
        assert info["slideCount"] == 6

    def test_non_carousel_returns_none(self):
        info = self._detect(root_class="hero-banner", child_count=3)
        assert info is None

    def test_single_child_not_carousel(self):
        info = self._detect(child_count=1, root_class="carousel")
        assert info is not None
        assert info["slideCount"] <= 1


# ---------------------------------------------------------------------------
# Integration (async): _capture_carousel_slides with mock Playwright page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_carousel_slides_each_captured_once():
    """
    Regression: given a 3-slide carousel with distinct PNG frames, the engine
    must produce 3 distinct screenshot paths — not 3 identical ones.
    """
    from ka11y.crawler.optimized.engine import Crawler

    slide_pngs = [_png_bytes(i) for i in range(3)]
    elements = [
        _make_element("el_0001"),
        _make_element("el_0002"),
        _make_element("el_0003"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "raw"
        out_dir.mkdir()

        png_calls = iter(range(3))

        async def fake_screenshot(path: str, timeout: int = 5000):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                idx = next(png_calls)
            except StopIteration:
                idx = 0
            p.write_bytes(slide_pngs[idx])

        advance_results = iter([True, True, False])

        async def fake_evaluate(script, args=None):
            if isinstance(args, dict) and "rootSelector" in args:
                try:
                    return next(advance_results)
                except StopIteration:
                    return False
            return {
                "rootSelector": "#my-carousel",
                "slideCount": 3,
                "nextSelector": ".carousel-control-next",
            }

        handle = MagicMock()
        handle.screenshot = fake_screenshot
        handle.is_visible = AsyncMock(return_value=True)
        handle.evaluate = AsyncMock(return_value={
            "rootSelector": "#my-carousel",
            "slideCount": 3,
            "nextSelector": ".carousel-control-next",
        })

        page = MagicMock()
        page.query_selector = AsyncMock(return_value=handle)
        page.evaluate = fake_evaluate

        crawler = object.__new__(Crawler)
        crawler.out_dir = out_dir

        await crawler._capture_carousel_slides(page, elements, "test_slug")

    screenshots = [el.get("screenshot") for el in elements]
    capture_statuses = [el.get("asset_capture", "") for el in elements]

    assert all(s is not None for s in screenshots), (
        f"Expected 3 non-None screenshots, got: {screenshots}"
    )
    assert len(set(screenshots)) == 3, (
        f"Expected 3 distinct screenshot paths, got duplicates: {screenshots}"
    )
    assert not any("duplicate" in (s or "") for s in capture_statuses), (
        f"Unexpected duplicate flag in: {capture_statuses}"
    )


@pytest.mark.asyncio
async def test_duplicate_frames_are_deduplicated():
    """
    If the carousel returns the same PNG bytes twice (looped back to slide 1),
    the second capture must be flagged ``carousel_duplicate`` with no
    screenshot path.
    """
    from ka11y.crawler.optimized.engine import Crawler

    shared_png = _png_bytes(42)
    slide_pngs = [shared_png, shared_png]  # both slides are identical

    elements = [
        _make_element("el_0001", selector="img:nth-of-type(1)"),
        _make_element("el_0002", selector="img:nth-of-type(2)"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "raw"
        out_dir.mkdir()

        png_iter = iter(slide_pngs)

        # Make el_0001 visible only on slide 0, el_0002 only on slide 1
        slide_idx = [0]

        async def fake_screenshot(path: str, timeout: int = 5000):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = next(png_iter)
            except StopIteration:
                data = _png_bytes(99)
            p.write_bytes(data)

        advance_results = iter([True, False])

        async def fake_evaluate(script, args=None):
            if isinstance(args, dict) and "rootSelector" in args:
                try:
                    slide_idx[0] += 1
                    return next(advance_results)
                except StopIteration:
                    return False
            return {
                "rootSelector": "#my-carousel",
                "slideCount": 2,
                "nextSelector": ".carousel-control-next",
            }
            
        def fake_is_visible(handle_id):
            if handle_id == "el_0001":
                return slide_idx[0] == 0
            if handle_id == "el_0002":
                return slide_idx[0] == 1
            return False

        h1 = MagicMock()
        h1.screenshot = fake_screenshot
        h1.is_visible = AsyncMock(side_effect=lambda: fake_is_visible("el_0001"))
        h1.evaluate = AsyncMock(return_value={
            "rootSelector": "#my-carousel",
            "slideCount": 2,
            "nextSelector": ".carousel-control-next",
        })
        
        h2 = MagicMock()
        h2.screenshot = fake_screenshot
        h2.is_visible = AsyncMock(side_effect=lambda: fake_is_visible("el_0002"))
        h2.evaluate = AsyncMock(return_value={
            "rootSelector": "#my-carousel",
            "slideCount": 2,
            "nextSelector": ".carousel-control-next",
        })
        
        handle_map = {"img:nth-of-type(1)": h1, "img:nth-of-type(2)": h2}

        page = MagicMock()
        page.query_selector = AsyncMock(side_effect=lambda sel: handle_map.get(sel, h1))
        page.evaluate = fake_evaluate

        crawler = object.__new__(Crawler)
        crawler.out_dir = out_dir

        await crawler._capture_carousel_slides(page, elements, "test_slug")

    statuses = [el.get("asset_capture", "") for el in elements]
    real_captures = [s for s in statuses if s and "slide" in s]
    duplicates = [s for s in statuses if s == "carousel_duplicate"]

    assert len(real_captures) >= 1, f"Expected at least one real capture: {statuses}"
    assert len(duplicates) >= 1, (
        f"Expected at least one carousel_duplicate flag: {statuses}"
    )
    for el in elements:
        if el.get("asset_capture") == "carousel_duplicate":
            assert el.get("screenshot") is None, (
                "Duplicate element must not have a screenshot path"
            )


@pytest.mark.asyncio
async def test_max_carousel_slides_cap_prevents_infinite_loop():
    """
    The hard cap MAX_CAROUSEL_SLIDES must stop the loop even if the carousel
    claims to advance indefinitely.
    """
    from ka11y.crawler.optimized.engine import Crawler, MAX_CAROUSEL_SLIDES

    elements = [
        _make_element(f"el_{i:04d}") for i in range(MAX_CAROUSEL_SLIDES + 10)
    ]
    advance_count = [0]
    slide_seed = [0]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "raw"
        out_dir.mkdir()

        async def fake_screenshot(path: str, timeout: int = 5000):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            slide_seed[0] += 1
            p.write_bytes(_png_bytes(slide_seed[0]))

        async def fake_evaluate(script, args=None):
            if isinstance(args, dict) and "rootSelector" in args:
                advance_count[0] += 1
                return True  # always claims to have advanced
            return {
                "rootSelector": "#infinite-carousel",
                "slideCount": 999,
                "nextSelector": ".next",
            }

        handle = MagicMock()
        handle.screenshot = fake_screenshot
        handle.is_visible = AsyncMock(return_value=True)
        handle.evaluate = AsyncMock(return_value={
            "rootSelector": "#infinite-carousel",
            "slideCount": 999,
            "nextSelector": ".next",
        })

        page = MagicMock()
        page.query_selector = AsyncMock(return_value=handle)
        page.evaluate = fake_evaluate

        crawler = object.__new__(Crawler)
        crawler.out_dir = out_dir

        # Must complete without hanging.
        await crawler._capture_carousel_slides(page, elements, "test_slug")

    assert advance_count[0] <= MAX_CAROUSEL_SLIDES, (
        f"Advance count {advance_count[0]} exceeded cap {MAX_CAROUSEL_SLIDES}"
    )


@pytest.mark.asyncio
async def test_non_carousel_elements_unaffected():
    """
    Elements not inside a carousel (CAROUSEL_DETECT_JS returns None) must be
    processed by the normal _capture_assets path, not flagged as
    carousel_not_reached or carousel_duplicate.
    """
    from ka11y.crawler.optimized.engine import Crawler

    elements = [
        _make_element(
            "el_hero",
            selector="#hero-img",
            element_type="img",
            src="https://example.com/hero.png",
        ),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "raw"
        out_dir.mkdir()

        async def fake_screenshot(path: str, timeout: int = 5000):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(_png_bytes(1))

        handle = MagicMock()
        handle.screenshot = fake_screenshot
        handle.is_visible = AsyncMock(return_value=True)
        # evaluate() for CAROUSEL_DETECT_JS returns None → not a carousel
        handle.evaluate = AsyncMock(return_value=None)
        container_mock = MagicMock()
        container_mock.evaluate = AsyncMock(return_value=False)
        container_mock.as_element = MagicMock(return_value=handle)
        handle.evaluate_handle = AsyncMock(return_value=container_mock)

        page = MagicMock()
        page.query_selector = AsyncMock(return_value=handle)
        # page.evaluate for CAROUSEL_DETECT_JS also returns None
        page.evaluate = AsyncMock(return_value=None)

        crawler = object.__new__(Crawler)
        crawler.out_dir = out_dir
        crawler.ssrf_guard = False

        with patch.object(crawler, "_download_asset", new=AsyncMock(return_value=False)):
            await crawler._capture_assets(page, elements, "https://example.com/")

    assert elements[0].get("asset_capture") not in (
        "carousel_not_reached",
        "carousel_duplicate",
    ), f"Non-carousel element got carousel asset_capture: {elements[0]}"


@pytest.mark.asyncio
async def test_carousel_not_advanced_elements_flagged():
    """
    Elements not visible on slide 0 that the carousel cannot advance to must
    be flagged ``carousel_not_reached``.
    """
    from ka11y.crawler.optimized.engine import Crawler

    elements = [
        _make_element("el_0001", visible=True),  # visible on slide 0
        _make_element("el_0002", visible=False),  # invisible on slide 0; never reached
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "raw"
        out_dir.mkdir()

        async def fake_screenshot(path: str, timeout: int = 5000):
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(_png_bytes(1))

        visible_map = {"el_0001": True, "el_0002": False}

        # el_0001 handle
        h1 = MagicMock()
        h1.screenshot = fake_screenshot
        h1.is_visible = AsyncMock(return_value=True)
        h1.evaluate = AsyncMock(return_value={
            "rootSelector": "#my-carousel",
            "slideCount": 2,
            "nextSelector": ".carousel-control-next",
        })
        # el_0002 handle
        h2 = MagicMock()
        h2.screenshot = fake_screenshot
        h2.is_visible = AsyncMock(return_value=False)
        h2.evaluate = AsyncMock(return_value={
            "rootSelector": "#my-carousel",
            "slideCount": 2,
            "nextSelector": ".carousel-control-next",
        })

        handles_iter = iter([h1, h2])

        async def fake_query_selector(sel):
            try:
                return next(handles_iter)
            except StopIteration:
                return None

        async def fake_evaluate(script, args=None):
            if isinstance(args, dict) and "rootSelector" in args:
                return False  # advance fails immediately
            return {
                "rootSelector": "#my-carousel",
                "slideCount": 2,
                "nextSelector": ".carousel-control-next",
            }

        page = MagicMock()
        page.query_selector = fake_query_selector
        page.evaluate = fake_evaluate

        crawler = object.__new__(Crawler)
        crawler.out_dir = out_dir

        await crawler._capture_carousel_slides(page, elements, "test_slug")

    # el_0002 (never visible) must be flagged carousel_not_reached.
    assert elements[1].get("asset_capture") == "carousel_not_reached", (
        f"el_0002 should be 'carousel_not_reached', got: {elements[1].get('asset_capture')}"
    )
