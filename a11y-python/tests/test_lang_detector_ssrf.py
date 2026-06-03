"""
Regression tests for N-1: the auto-language detector must not make a
server-side request to a non-public host (SSRF), and must validate the host
before opening a network stream.
"""

from __future__ import annotations

import pytest

from a11y.utils import lang_detector


class _NoStreamClient:
    """Stand-in for httpx.AsyncClient whose .stream() must never be called."""

    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, *args, **kwargs):  # pragma: no cover - must not run
        _NoStreamClient.calls += 1
        raise AssertionError("lang_detector fetched a blocked host (SSRF)")


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://localhost:8000/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://2130706433/",  # decimal-encoded 127.0.0.1
    ],
)
async def test_blocked_hosts_are_not_fetched(url, monkeypatch):
    _NoStreamClient.calls = 0
    monkeypatch.setattr(lang_detector.httpx, "AsyncClient", _NoStreamClient)
    lang_detector._LANG_CACHE.clear()

    result = await lang_detector.detect_page_language(url)

    assert result == "en"  # safe default, no exception
    assert _NoStreamClient.calls == 0  # never attempted a network stream
