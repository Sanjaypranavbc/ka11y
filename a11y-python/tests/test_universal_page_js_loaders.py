"""
Smoke test for the JS extractors used by ``universal_page.py``.

These extractors are now defined as inline Python string constants
(``_COMBINED_EXTRACT_JS``, ``_LINK_EXTRACT_JS``, ``_LAZY_LOAD_TRIGGER_JS``,
``_BACKGROUND_IMAGES_JS``) rather than loaded from separate ``.js`` files. If
any constant is removed, renamed, or emptied, this test catches it before a
live browser invocation does.
"""
from __future__ import annotations

import pytest

from a11y.crawler import universal_page


_EXPECTED_TOP_KEYS = (
    "forms",
    "interactive",
    "target_sizes",
    "moving_content",
    "media",
    "text_spacing",
    "sensory",
)

# The inline JS extractor constants the crawler evaluates in-page.
_JS_CONSTANTS = (
    "_COMBINED_EXTRACT_JS",
    "_LINK_EXTRACT_JS",
    "_LAZY_LOAD_TRIGGER_JS",
    "_BACKGROUND_IMAGES_JS",
)


@pytest.mark.parametrize("const_name", _JS_CONSTANTS)
def test_each_js_constant_present_and_nonempty(const_name: str):
    assert hasattr(universal_page, const_name), (
        f"universal_page no longer defines inline extractor {const_name}"
    )
    body = getattr(universal_page, const_name)
    assert isinstance(body, str) and body.strip(), f"{const_name} is empty"


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


def test_combined_extractor_returns_expected_top_keys():
    """The Python side parses the JS evaluate() result by these keys —
    if the JS top-level return shape changes the auditors silently
    miss whole categories."""
    body = universal_page._COMBINED_EXTRACT_JS
    for key in _EXPECTED_TOP_KEYS:
        assert key in body, (
            f"_COMBINED_EXTRACT_JS no longer references top-level key '{key}'"
        )


def test_link_extractor_returns_href_list():
    body = universal_page._LINK_EXTRACT_JS
    assert "a[href]" in body
    assert "queryShadow" in body
