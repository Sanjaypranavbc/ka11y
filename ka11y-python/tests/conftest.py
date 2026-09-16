"""
Shared pytest fixtures for ka11y-python test suite.
"""

import os
import tempfile

import pytest
from bs4 import BeautifulSoup

# ── Store isolation ──────────────────────────────────────────────────────────
# Several tests boot the FastAPI app through its lifespan (TestClient), which
# calls ``init_db()`` and starts the durable-queue dispatcher. Without an
# override both resolve to the checkout's real ``logs/ka11y.db`` — the same
# file a dev server started from this directory is using. The dispatcher's
# crash recovery then re-queues that server's *running* jobs and re-runs them
# inside the pytest process (observed 2026-09-15: a live audit was started
# twice, once by the server and once by the test suite). Point the whole test
# session at a throwaway store before any test module imports the app.
# Tests that want their own DB (test_durable_store) still override per test.
# (Timing-file writes are left enabled: test_run_timing / stage-timing tests
# assert on them and write under tmp paths of their own.)
_STORE_TMP = tempfile.mkdtemp(prefix="ka11y-test-store-")
os.environ.setdefault("KA11Y_DB_PATH", os.path.join(_STORE_TMP, "ka11y.db"))
os.environ.setdefault("KA11Y_ASSET_DIR", os.path.join(_STORE_TMP, "assets"))


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