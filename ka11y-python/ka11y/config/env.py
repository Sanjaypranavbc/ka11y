"""
ka11y/config/env.py
===================
One switch for "may this process read ka11y-python/.env?".

``.env`` is a convenience for running the API or the enrichment CLI on a
laptop; Docker passes the same variables through compose. The test suite
sets ``KA11Y_LOAD_DOTENV=0`` (tests/conftest.py) so a developer's real
DATABASE_URL, OIDC redirect URI or Arize keys cannot leak into the test
process and change which tests run or what they assert. Every call site
that would load the file — ``ka11y.main``, ``observability.tracing``,
``enrich_audit`` — asks here first.
"""

from __future__ import annotations

import os


def dotenv_enabled() -> bool:
    return os.getenv("KA11Y_LOAD_DOTENV", "1") != "0"
