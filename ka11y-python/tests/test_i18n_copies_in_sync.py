"""
The WCAG rule catalogue (i18n/rules.yml + locales/*.yml) is shared by the
Python and Node services. Each service's Docker build context is its own
directory, so each ships a *copy* of the repo-root i18n/. On a developer
machine the loaders prefer the repo-root files, in Docker they read the copy
— so when the copies drift, production shows different rule text (and, as
happened before 2026-09-27, loses reason templates and severities) from what
was tested locally.

This test fails the moment the copies differ. Fix: edit i18n/ at the repo
root and copy it over both service directories (or the other way round).
Skipped inside Docker, where only one copy exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PY_DIR = Path(__file__).resolve().parents[1]
_ROOT = _PY_DIR.parent
_SHARED = _ROOT / "i18n"
_FILES = ("rules.yml", "locales/ja.yml", "locales/de.yml")


@pytest.mark.skipif(not (_SHARED / "rules.yml").exists(), reason="no repo-root i18n/ (Docker build)")
@pytest.mark.parametrize("copy_dir", [_PY_DIR / "i18n", _ROOT / "ka11y-node" / "i18n"])
@pytest.mark.parametrize("rel", _FILES)
def test_service_i18n_copy_matches_shared(copy_dir: Path, rel: str) -> None:
    if not (copy_dir / rel).exists():
        pytest.skip(f"{copy_dir} not present in this checkout")
    shared = (_SHARED / rel).read_text(encoding="utf-8")
    copy = (copy_dir / rel).read_text(encoding="utf-8")
    assert copy == shared, (
        f"{copy_dir.relative_to(_ROOT)}/{rel} differs from i18n/{rel}; "
        "sync it so Docker ships the same catalogue developers test against"
    )
