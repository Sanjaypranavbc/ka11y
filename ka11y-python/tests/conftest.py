"""
Shared pytest fixtures for ka11y-python test suite.
"""

import pytest
from bs4 import BeautifulSoup


@pytest.fixture(scope="session", autouse=True)
def fallback_bs4_parser():
    original_init = BeautifulSoup.__init__
    def patched_init(self, markup="", features=None, *args, **kwargs):
        if features == "lxml":
            try:
                original_init(self, markup, "lxml", *args, **kwargs)
            except Exception:
                original_init(self, markup, "html.parser", *args, **kwargs)
        else:
            original_init(self, markup, features, *args, **kwargs)
    BeautifulSoup.__init__ = patched_init
    yield
    BeautifulSoup.__init__ = original_init


@pytest.fixture
def tmp_output(tmp_path) -> str:
    """Isolated temporary output directory for each test."""
    return str(tmp_path)