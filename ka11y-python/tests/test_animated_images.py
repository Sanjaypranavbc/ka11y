"""G152: animated GIF/WebP/APNG inspection for WCAG 2.2.2."""

import io

from PIL import Image

from ka11y.accessibility.rules.media.animated_images import (
    animated_images_to_findings,
    inspect_image_bytes,
    scan_animated_images,
)
from ka11y.crawler.models import ImageData


def _gif(frames: int, duration_ms: int, loop):
    imgs = [Image.new("RGB", (4, 4), color=(min(255, 30 * i + 10), 0, 0)) for i in range(frames)]
    buf = io.BytesIO()
    kw = dict(save_all=True, append_images=imgs[1:], duration=duration_ms)
    if loop is not None:
        kw["loop"] = loop
    imgs[0].save(buf, format="GIF", **kw)
    return buf.getvalue()


def _img(src, **kw):
    d = dict(url="https://example.com/", src=src, alt_text="", classification="informative",
             screenshot_path="/tmp/x.png", filename="x.png")
    d.update(kw)
    return ImageData(**d)


def test_static_image_is_not_animated():
    buf = io.BytesIO(); Image.new("RGB", (4, 4)).save(buf, format="PNG")
    assert inspect_image_bytes(buf.getvalue()) is None


def test_animated_gif_metadata():
    info = inspect_image_bytes(_gif(10, 200, loop=0))
    assert info["frames"] == 10 and info["loop_infinite"] is True and info["total_ms"] == 2000


def test_short_finite_gif_passes():
    data = {"https://example.com/a.gif": _gif(5, 200, loop=1)}
    fs = animated_images_to_findings([_img("https://example.com/a.gif")], "https://example.com/", fetch=lambda s: data.get(s))
    assert len(fs) == 1 and fs[0]["status"] == "pass" and fs[0]["wcag_sc"] == "2.2.2"


def test_infinite_gif_needs_review_with_g152_reason():
    data = {"https://example.com/loop.gif": _gif(3, 300, loop=0)}
    fs = animated_images_to_findings([_img("https://example.com/loop.gif")], "https://example.com/", fetch=lambda s: data.get(s))
    assert fs[0]["status"] == "needs_review" and "G152" in fs[0]["reason"]


def test_non_candidates_and_duplicates_skipped():
    calls = []
    def fetch(s):
        calls.append(s); return _gif(2, 100, loop=1)
    imgs = [_img("https://example.com/a.gif"), _img("https://example.com/a.gif"), _img("https://example.com/photo.jpg")]
    recs = scan_animated_images(imgs, fetch=fetch)
    assert calls == ["https://example.com/a.gif"] and len(recs) == 1
