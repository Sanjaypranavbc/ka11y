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
    ["universal_extract.js", "link_extract.js", "lazy_load_trigger.js"],
)
def test_each_js_file_loads(name: str):
    path: Path = universal_page._JS_DIR / name
    assert path.is_file(), f"missing JS extractor: {path}"
    body = path.read_text(encoding="utf-8")
    assert body.strip(), f"{name} is empty"


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
