"""SVG image sources must never reach OCR as XML bytes under a .png name."""

from pathlib import Path

from ka11y.crawler.image_extractor import _is_svg_asset
from ka11y.crawler.optimized.adapter import _is_raster
from ka11y.text_detector.text_detector import _looks_like_raster

SVG = b'<svg width="80" height="80" xmlns="http://www.w3.org/2000/svg"><rect/></svg>'
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_svg_sources_are_detected():
    assert _is_svg_asset("svg_via_img", "https://x.test/a.png")
    assert _is_svg_asset("img", "https://x.test/logo.svg?v=2")
    assert _is_svg_asset("img", "data:image/svg+xml;base64,PHN2Zz4=")
    assert not _is_svg_asset("img", "https://x.test/photo.png")
    assert not _is_svg_asset("img", "data:image/png;base64,iVBORw0KGgo=")


def test_raster_sniffing(tmp_path: Path):
    svg_as_png = tmp_path / "svg_deadbeef.png"
    svg_as_png.write_bytes(SVG)
    real_png = tmp_path / "real.png"
    real_png.write_bytes(PNG)
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    for fn in (_is_raster, _looks_like_raster):
        assert fn(real_png)
        assert not fn(svg_as_png)
        assert not fn(empty)
        assert not fn(tmp_path / "missing.png")
    assert not _is_raster(None)
