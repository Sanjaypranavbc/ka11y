"""
Unit tests for ``ka11y.crawler.image_extractor`` — the per-page image
extraction + capture pipeline shared by the universal loader and the engine.

These use a mocked Playwright page so they run without Chromium; the real
browser round-trip is covered by ``test_universal_image_capture.py``.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ka11y.crawler import image_extractor as ie


def _fake_page(elements: list, links: list | None = None, lang: str | None = "en"):
    page = MagicMock()

    async def evaluate(script, arg=None):
        if script is ie.EXTRACT_JS:
            return {"elements": [dict(e) for e in elements], "links": list(links or [])}
        if script == ie.PAGE_LANG_JS:
            return lang
        return None

    page.evaluate = evaluate
    page.wait_for_timeout = AsyncMock()
    page.locator = MagicMock(return_value=MagicMock(all=AsyncMock(return_value=[])))
    page.query_selector = AsyncMock(return_value=None)
    page.viewport_size = {"width": 1000, "height": 800}
    return page


@pytest.mark.asyncio
async def test_extract_image_page_returns_engine_shaped_doc(tmp_path):
    elements = [
        {"id": "el_0001", "element_type": "img", "selector": "img", "visible": False,
         "criteria": ["1.1.1", "1.4.5"], "bounding_box": {"x": 0, "y": 0, "width": 0, "height": 0}},
        {"id": "el_0002", "element_type": "text_contrast_candidate", "selector": "p",
         "criteria": ["1.4.3", "1.4.6"]},
    ]
    page = _fake_page(elements, links=["https://a.test/x", "https://a.test/y"], lang="ja")

    doc = await ie.extract_image_page(page, "https://a.test/?utm_source=x", 2, tmp_path)

    assert doc["processing_status"] == "success"
    assert doc["page_url"] == "https://a.test/?utm_source=x"
    assert doc["normalized_url"] == "https://a.test/"  # tracker param stripped
    assert doc["depth"] == 2
    assert doc["page_lang"] == "ja"
    assert doc["links"] == ["https://a.test/x", "https://a.test/y"]
    assert doc["links_discovered"] == ie.empty_links_discovered()
    # criteria were popped off elements and rolled up per SC
    assert all("criteria" not in el for el in doc["elements"])
    assert doc["criteria"]["1.1.1"] == {"applicable": True, "element_ids": ["el_0001"], "note": None}
    assert doc["criteria"]["1.4.3"]["element_ids"] == ["el_0002"]
    assert doc["criteria"]["1.2.1"] == {"applicable": False, "element_ids": [], "note": ie.NOT_PRESENT_NOTE}
    # image-typed elements always get the capture fields, even when skipped
    assert doc["elements"][0]["screenshot"] is None
    assert doc["elements"][0]["asset_capture"] is None


@pytest.mark.asyncio
async def test_write_page_doc_is_keyed_by_slug_and_readable_by_adapter(tmp_path):
    page = _fake_page([])
    doc = await ie.extract_image_page(page, "https://a.test/page", 0, tmp_path)
    path = ie.write_page_doc(doc, tmp_path)

    assert path == tmp_path / f"{ie.url_slug('https://a.test/page')}.json"
    assert json.loads(path.read_text())["page_url"] == "https://a.test/page"
    assert not list(tmp_path.glob("*.tmp"))

    from ka11y.crawler.optimized.adapter import build_image_data

    images, langs, visited = build_image_data(tmp_path, tmp_path / "out")
    assert visited == {"https://a.test/page"}
    assert langs == {"https://a.test/page": "en"}
    assert images == []


@pytest.mark.asyncio
async def test_download_asset_decodes_data_uri_and_respects_ssrf_check(tmp_path):
    page = MagicMock()
    dest = tmp_path / "a" / "b.png"
    ok = await ie.download_asset(page, "data:image/png;base64,aGVsbG8=", dest)
    assert ok and dest.read_bytes() == b"hello"

    blocked = await ie.download_asset(
        page, "http://169.254.169.254/latest/meta-data", tmp_path / "meta",
        ssrf_check=lambda host: True,
    )
    assert blocked is False
    page.context.request.get.assert_not_called()


@pytest.mark.asyncio
async def test_capture_assets_uses_shared_download_semaphore(tmp_path):
    """The universal loader hands one semaphore to every page so N parallel
    pages can't open N × DOWNLOAD_CONCURRENCY fetches. Verify the semaphore
    passed in is the one that gates downloads."""
    elements = [
        {"id": f"el_{i:04d}", "element_type": "img", "selector": f"img:nth-of-type({i})",
         "visible": True, "src": f"https://cdn.test/{i}.png", "flags": {},
         "bounding_box": {"x": 0, "y": 0, "width": 50, "height": 50}}
        for i in range(1, 5)
    ]
    handle = MagicMock()
    handle.evaluate = AsyncMock(return_value=None)          # carousel probe → None
    container = MagicMock()
    container.evaluate = AsyncMock(return_value=False)      # not an overlay
    handle.evaluate_handle = AsyncMock(return_value=container)

    page = MagicMock()
    page.query_selector = AsyncMock(return_value=handle)

    in_flight = 0
    peak = 0
    sem = asyncio.Semaphore(1)

    async def fake_get(url, timeout=None):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        resp = MagicMock()
        resp.ok = True
        resp.body = AsyncMock(return_value=b"png")
        return resp

    page.context.request.get = fake_get

    await ie.capture_assets(
        page, elements, "https://a.test/", tmp_path, ssrf_check=None, download_sem=sem,
    )

    assert peak == 1, "downloads must serialise through the caller's semaphore"
    assert all(el["asset_capture"] == "download" for el in elements)
    assert all((tmp_path / el["asset_file"]).exists() for el in elements)


def test_engine_reexports_moved_names():
    """The CLI engine and older tests import these from engine.py."""
    from ka11y.crawler.optimized import engine

    for name in ("EXTRACT_JS", "SCROLL_JS", "MAX_CAROUSEL_SLIDES", "normalize_url",
                 "url_slug", "registrable_domain", "capture_assets"):
        assert getattr(engine, name) is getattr(ie, name)
