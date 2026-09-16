"""
End-to-end (real Chromium, no network): the universal page loader with
``image_capture=True`` produces page docs the image adapter can consume —
i.e. one navigation now feeds both the media rules and the image rules.

Navigation is stubbed by monkeypatching ``_prepare_page`` to ``set_content``
the fixture HTML, so the SSRF guard on the pooled context is never in play.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ka11y.crawler import browser_pool as bp
from ka11y.crawler.universal_page import UniversalPageLoader

# 1x1 red PNG.
_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_HTML = f"""<!doctype html>
<html lang="ja">
<body>
  <header><a href="/"><img id="logo" src="{_PNG}" alt="Kao" width="120" height="40"></a></header>
  <main>
    <img id="hero" src="{_PNG}" alt="" width="300" height="200">
    <img id="noalt" src="{_PNG}" width="80" height="80">
    <video id="clip" src="/clip.mp4" controls></video>
    <a href="https://example.test/about">About</a>
    <a href="https://other.test/off-site">Off-site</a>
  </main>
</body>
</html>"""


@pytest.fixture(autouse=True)
async def _pool():
    await bp.shutdown_pool()
    yield
    await bp.shutdown_pool()


@pytest.mark.asyncio
async def test_single_pass_produces_media_and_image_docs(tmp_path, monkeypatch):
    async def fake_prepare(cls, page, url, *, step_logger=None):
        await page.set_content(_HTML, wait_until="domcontentloaded")

    monkeypatch.setattr(UniversalPageLoader, "_prepare_page", classmethod(fake_prepare))

    url = "https://example.test/"
    raw_dir = tmp_path / "image_raw"
    snapshot = await UniversalPageLoader.load(
        url, tmp_path, max_depth=0, max_pages=1,
        image_capture=True, image_raw_dir=raw_dir,
    )

    # media + links + lang from the one visit
    assert snapshot.pages_crawled == 1
    assert [m["element_id"] for m in snapshot.media] == ["clip"]
    summary = snapshot.page_summaries[0]
    assert summary["page_url"] == url
    assert summary["page_lang"] == "ja"
    assert summary["images"] >= 3
    assert not any(w["code"] == "image_extract_failed" for w in snapshot.warnings)

    # the image doc is on disk in the engine's shape
    docs = list(raw_dir.glob("*.json"))
    assert len(docs) == 1

    # …and the adapter + OptimizedImageCrawler fast path consume it unchanged
    from ka11y.crawler.optimized.optimized_crawler import OptimizedImageCrawler

    crawler = OptimizedImageCrawler(url, max_depth=0, output_dir=str(tmp_path / "images"))
    await crawler.crawl_page(raw_dir=raw_dir)

    assert crawler.visited_urls == {url}
    assert crawler.page_langs == {url: "ja"}
    by_id = {img.element_id: img for img in crawler.images_data}
    assert {"logo", "hero", "noalt"} <= {
        # element ids are engine-assigned (el_0001…); match on alt/flags instead
        "logo" if img.in_link and img.alt_text == "Kao" else
        "hero" if img.alt_present and img.alt_text == "" else
        "noalt" if not img.alt_present else "?"
        for img in crawler.images_data
    }
    # pixels were captured and copied under the job's images/ tree
    captured = [img for img in crawler.images_data if img.capture_status == "ok"]
    assert captured, "expected at least one captured image"
    for img in captured:
        assert Path(img.screenshot_path).exists()
        assert Path(img.screenshot_path).is_relative_to(tmp_path / "images")
    assert Path(crawler.output_dir) == tmp_path / "images"


@pytest.mark.asyncio
async def test_time_budget_stops_launching_pages(tmp_path, monkeypatch):
    launched: list[str] = []

    async def fake_crawl(cls, *, context, root_url, url, depth, policy, output, step_logger, image_opts=None):
        launched.append(url)
        output.pages_crawled += 1
        return []

    monkeypatch.setattr(UniversalPageLoader, "_crawl_one_url", classmethod(fake_crawl))

    snapshot = await UniversalPageLoader.load(
        "https://example.test/", tmp_path, max_depth=0, max_pages=10,
        seed_url=["https://example.test/a", "https://example.test/b"],
        time_budget_s=1e-6,
    )
    # Budget was already spent before the first launch → nothing visited,
    # but the snapshot says why instead of silently returning empty.
    assert launched == []
    assert snapshot.partial is True
    assert any(w["code"] == "crawl_time_budget_exceeded" for w in snapshot.warnings)
