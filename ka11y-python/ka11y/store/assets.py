"""
ka11y/store/assets.py
=====================
Content-addressed asset store (Decision #2: bytes on disk, metadata in DB).

``put_asset`` hashes the bytes, writes them under ``KA11Y_ASSET_DIR`` at a
path derived from the sha256 (so the same logo across 50 pages is stored once),
and records a row in ``assets``. ``get_asset`` resolves a row → absolute path
for the serving endpoint.

Nothing here may fail an audit: ``put_asset`` returns ``None`` on any error and
logs it. The caller keeps its existing on-disk path as a fallback.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ka11y.config.logger import setup_logger
from ka11y.store.db import get_db

logger = setup_logger(name="KAC", tag="store.assets")


def asset_dir() -> Path:
    override = os.getenv("KA11Y_ASSET_DIR")
    if override:
        return Path(override)
    # Default under the bind-mounted output/ tree so existing volume mounts work.
    return Path(__file__).resolve().parent.parent.parent / "logs" / "assets"


@dataclass
class AssetRef:
    asset_id: int
    rel_path: str
    sha256: str
    bytes: int

    @property
    def url(self) -> str:
        return f"/api/v1/assets/{self.asset_id}"


def _ext_for(mime: Optional[str], src_name: Optional[str]) -> str:
    if src_name and "." in Path(src_name).name:
        return Path(src_name).suffix.lstrip(".") or "bin"
    if mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            return guessed.lstrip(".")
    return "bin"


async def put_asset(
    *,
    run_id: str,
    kind: str,
    data: Union[bytes, str, Path],
    page_url: Optional[str] = None,
    mime: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Optional[AssetRef]:
    """Store *data* (raw bytes, or a path to copy from) and register it.

    Returns an :class:`AssetRef` or ``None`` on failure (never raises).
    """
    try:
        src_name: Optional[str] = None
        if isinstance(data, (str, Path)):
            src_path = Path(data)
            src_name = src_path.name
            raw = src_path.read_bytes()
            if mime is None:
                mime, _ = mimetypes.guess_type(str(src_path))
        else:
            raw = data

        sha = hashlib.sha256(raw).hexdigest()
        ext = _ext_for(mime, src_name)
        rel_path = f"{run_id}/{kind}/{sha[:2]}/{sha}.{ext}"
        dest = asset_dir() / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        if not dest.exists():
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(raw)
            os.replace(tmp, dest)  # atomic publish

        asset_id = await get_db().execute(
            "INSERT OR IGNORE INTO assets "
            "(run_id, page_url, kind, rel_path, sha256, mime, width, height, bytes) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, page_url, kind, rel_path, sha, mime, width, height, len(raw)),
        )
        if not asset_id:
            row = await get_db().query_one(
                "SELECT id FROM assets WHERE run_id=? AND rel_path=?",
                (run_id, rel_path),
            )
            asset_id = row["id"] if row else 0
        return AssetRef(asset_id=int(asset_id), rel_path=rel_path, sha256=sha, bytes=len(raw))
    except Exception:  # noqa: BLE001
        logger.warning("[store] put_asset(run=%s kind=%s) failed", run_id, kind, exc_info=True)
        return None


async def get_asset(asset_id: int) -> Optional[Dict[str, Any]]:
    """Resolve an asset row + absolute path for serving. Validates containment."""
    row = await get_db().query_one(
        "SELECT id, run_id, kind, rel_path, mime, bytes FROM assets WHERE id=?",
        (asset_id,),
    )
    if not row:
        return None
    base = asset_dir().resolve()
    abs_path = (base / row["rel_path"]).resolve()
    try:
        abs_path.relative_to(base)  # path-traversal guard
    except ValueError:
        logger.warning("[store] asset %s escapes asset_dir", asset_id)
        return None
    if not abs_path.is_file():
        return None
    row["abs_path"] = str(abs_path)
    return row


def prune_run_assets(run_id: str) -> None:
    """Delete the on-disk asset directory for a run (rows are removed by the
    ON DELETE CASCADE in the retention sweep). Best-effort; never raises."""
    try:
        run_dir = asset_dir() / run_id
        if run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        logger.debug("[store] prune_run_assets(%s) failed", run_id, exc_info=True)
