"""
Shared pytest fixtures for ka11y-python test suite.
"""

import pytest


@pytest.fixture
def tmp_output(tmp_path) -> str:
    """Isolated temporary output directory for each test."""
    return str(tmp_path)