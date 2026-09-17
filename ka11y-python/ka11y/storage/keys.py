"""
ka11y/storage/keys.py
=====================
Object-key layout (spec §18). UUIDs only — never emails — in the path::

    organizations/{organization_id}/users/{user_id}/sessions/{session_id}/jobs/{job_id}/
        reports/   report.json · findings.csv · report.pdf
        assets/    screenshots/ · html/ · images/ · media/
        raw/       ocr/… · steps/… · crawler/…
        crash/     crash.json

A job the production DB does not know (anonymous submission, auth disabled,
DATABASE_URL unset) lands under ``anonymous/jobs/{job_id}/`` instead, so an
upload never has to wait on ownership data.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Dict, Optional

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="storage.keys")

# Asset kinds (store/assets.py) → folder under assets/
ASSET_FOLDERS: Dict[str, str] = {
    "screenshot": "screenshots",
    "context_screenshot": "screenshots",
    "finding_image": "images",
    "ocr_crop": "images",
    "contrast_region": "images",
    "html_snapshot": "html",
    "dom_snapshot": "html",
    "subtitles": "media",
    "har": "raw",
}

_prefix_cache: Dict[str, str] = {}


def _clean(part: str) -> str:
    return PurePosixPath(str(part)).name  # no slashes, no traversal


async def job_prefix(job_id: str) -> str:
    """Resolve (and cache) the key prefix for a job."""
    cached = _prefix_cache.get(job_id)
    if cached:
        return cached
    owner: Optional[dict] = None
    try:
        from ka11y.db import audit_repo

        owner = await audit_repo.get_owner(job_id)
    except Exception:  # noqa: BLE001
        logger.debug("[storage] owner lookup failed for %s", job_id, exc_info=True)
    if owner and owner.get("user_id"):
        prefix = (
            f"organizations/{owner.get('organization_id') or 'none'}/"
            f"users/{owner['user_id']}/sessions/{owner.get('session_id') or 'none'}/jobs/{_clean(job_id)}"
        )
    else:
        prefix = f"anonymous/jobs/{_clean(job_id)}"
    _prefix_cache[job_id] = prefix
    return prefix


def forget_job(job_id: str) -> None:
    _prefix_cache.pop(job_id, None)


def report_key(prefix: str, filename: str) -> str:
    return f"{prefix}/reports/{_clean(filename)}"


def asset_key(prefix: str, kind: str, filename: str, page_slug: Optional[str] = None) -> str:
    folder = ASSET_FOLDERS.get(kind, "images")
    mid = f"{_clean(page_slug)}/" if page_slug else ""
    return f"{prefix}/assets/{folder}/{mid}{_clean(filename)}"


def raw_key(prefix: str, *parts: str) -> str:
    return f"{prefix}/raw/" + "/".join(_clean(p) for p in parts if p)


def crash_key(prefix: str, filename: str = "crash.json") -> str:
    return f"{prefix}/crash/{_clean(filename)}"
