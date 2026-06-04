"""
ka11y/utils/html_soup.py
========================
Resilient BeautifulSoup factory.

Several auditors parsed HTML with ``BeautifulSoup(html, "lxml")``. That hard
dependency raises ``FeatureNotFound: Couldn't find a tree builder with the
features you requested: lxml`` on any environment where the optional ``lxml``
wheel isn't installed — which silently broke the consistent-navigation (3.2.3),
consistent-identification (3.2.4) and unusual-words (3.1.3) checks.

``make_soup`` prefers ``lxml`` (faster, more lenient on malformed markup) but
transparently falls back to the always-available stdlib ``html.parser`` so the
checks keep working regardless of what's installed.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup

# Resolve the best available parser once at import time.
_PARSER: str
try:  # pragma: no cover - import-time probe
    import lxml  # noqa: F401

    _PARSER = "lxml"
except Exception:  # noqa: BLE001
    _PARSER = "html.parser"


def best_parser() -> str:
    """Return the parser name that will actually be used."""
    return _PARSER


def make_soup(html: Any) -> BeautifulSoup:
    """Build a BeautifulSoup tree using the best available parser.

    Falls back to ``html.parser`` if the preferred parser raises at call time
    (e.g. lxml present but its C extension failed to load)."""
    try:
        return BeautifulSoup(html or "", _PARSER)
    except Exception:  # noqa: BLE001
        return BeautifulSoup(html or "", "html.parser")
