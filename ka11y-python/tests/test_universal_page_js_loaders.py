"""
Sprint 2 / step 10 smoke test. The three JS extractors used by
``universal_page.py`` live in ``ka11y/crawler/js/`` as ``.js`` files
loaded from disk at module import time. If any file is removed,
renamed, or has its top-level export shape changed, this test catches
it before a live browser invocation does.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ka11y.crawler import universal_page


_EXPECTED_TOP_KEYS = (
    "forms",
    "interactive",
    "target_sizes",
    "moving_content",
    "media",
    "text_spacing",
    "sensory",
)


def test_js_dir_exists():
    assert universal_page._JS_DIR.is_dir(), (
        f"expected JS extractor dir at {universal_page._JS_DIR}"
    )


@pytest.mark.parametrize(
    "name",
    [
        "link_extract.js",
        "lazy_load_trigger.js",
        "background_images.js",
        # The monolithic universal_extract.js was split into one shared helper
        # preamble + four focused category extractors. universal_page.py
        # composes them at import time into `(frameMeta) => { ... }` functions.
        "extract/common.js",
        "extract/structural.js",
        "extract/geometry.js",
        "extract/dynamic.js",
        "extract/sensory.js",
    ],
)
def test_each_js_file_loads(name: str):
    path: Path = universal_page._JS_DIR / name
    assert path.is_file(), f"missing JS extractor: {path}"
    body = path.read_text(encoding="utf-8")
    assert body.strip(), f"{name} is empty"


def test_page_snapshot_has_background_images_field():
    """The Pydantic snapshot must expose the new field so audit consumers
    can iterate without KeyError if no backgrounds were found."""
    snap = universal_page.PageSnapshot(page_url="https://example.com")
    assert hasattr(snap, "background_images")
    assert snap.background_images == []


def test_background_images_extractor_top_level_function():
    """The extractor must return a function (frameMeta) => [...records]."""
    body = universal_page._BACKGROUND_IMAGES_JS
    assert "url(" in body  # parses url(...) tokens
    assert "queryShadow" in body  # pierces shadow DOM
    assert "has_text_alternative" in body  # surfaces signal for audit


def test_extractors_cover_expected_top_keys():
    """The Python side parses each extractor's evaluate() result by these
    keys — if an extractor's return shape changes the auditors silently
    miss whole categories. Every expected key must be claimed by exactly
    one extractor in _EXTRACTORS."""
    claimed: dict[str, str] = {}
    for name, _js, keys in universal_page._EXTRACTORS:
        for key in keys:
            assert key not in claimed, (
                f"key '{key}' claimed by both {claimed[key]} and {name}"
            )
            claimed[key] = name
    assert set(claimed) == set(_EXPECTED_TOP_KEYS), (
        f"extractor key coverage drifted: {sorted(claimed)} "
        f"!= {sorted(_EXPECTED_TOP_KEYS)}"
    )


def test_each_extractor_is_a_composed_arrow_function():
    """Every extractor must be a single `(frameMeta) => { ... }` function
    with the shared helper preamble inlined, and must reference its keys."""
    for name, js, keys in universal_page._EXTRACTORS:
        assert js.startswith("(frameMeta) => {"), name
        assert js.rstrip().endswith("}"), name
        # the shared preamble must be present (helpers the body relies on)
        assert "function queryShadow(" in js, f"{name} missing helper preamble"
        for key in keys:
            assert key in js, f"{name} extractor no longer references '{key}'"


def test_link_extractor_returns_href_list():
    body = universal_page._LINK_EXTRACT_JS
    assert "a[href]" in body
    assert "queryShadow" in body
