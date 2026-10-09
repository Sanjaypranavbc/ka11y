"""
ka11y/store/assets.py
=====================
Content-addressed asset store (bytes on disk, mirrored to object storage).

``put_asset`` hashes the bytes, writes them under ``KA11Y_ASSET_DIR`` at a
path derived from the sha256 (so the same logo across 50 pages is stored once)
and uploads them to the object store (S3 / local artifact dir). The returned
ref's ``url`` is ``/api/v1/assets/by-key/{object key}``, which the API serves
straight from the store — so the UI can load an image whichever process
(API or worker) produced it.

PostgreSQL is switched off for now: the ``audit_assets`` index and the
``/api/v1/assets/{id}`` ids it handed out are commented out below, not
removed. ``get_asset`` / ``get_asset_record`` answer None without a DB.

Nothing here may fail an audit: ``put_asset`` returns ``None`` on any error and
logs it. The caller keeps its existing on-disk path as a fallback.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ka11y.config.logger import setup_logger
from ka11y.db.engine import is_configured, session_scope
from ka11y.db.models import AuditAsset

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
    object_key: Optional[str] = None  # key in the object store (S3-only mode)

    @property
    def url(self) -> str:
        if self.object_key:
            return f"/api/v1/assets/by-key/{self.object_key}"
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

        try:
            uuid.UUID(str(run_id))
        except (ValueError, TypeError):
            logger.warning("[store] put_asset(run=%s): job id is not a UUID", run_id)
            return None

        # ── PostgreSQL index — switched off (S3-only deployment) ─────────────
        # The id was taken from the INSERT's RETURNING, or — when the UNIQUE
        # (job_id, rel_path) row already existed — from a SELECT in the same
        # transaction. Never from a "last insert id": with the old SQLite
        # INSERT OR IGNORE that pointed at the PREVIOUS successful insert, so
        # every image referenced by more than one finding (the same crop is
        # registered once per rule: 1.1.1, then 4.1.2, 1.4.5 …) rendered as
        # whichever image had been inserted before it.
        #
        # jid = uuid.UUID(str(run_id))
        # if not is_configured():
        #     return None
        # async with session_scope() as s:
        #     stmt = (
        #         pg_insert(AuditAsset)
        #         .values(job_id=jid, page_url=page_url, kind=kind, rel_path=rel_path, sha256=sha,
        #                 mime=mime, width=width, height=height, bytes=len(raw))
        #         .on_conflict_do_nothing(constraint="uq_audit_assets_job_rel_path")
        #         .returning(AuditAsset.id)
        #     )
        #     asset_id = (await s.execute(stmt)).scalar()
        #     if asset_id is None:
        #         asset_id = (
        #             await s.execute(
        #                 select(AuditAsset.id).where(AuditAsset.job_id == jid, AuditAsset.rel_path == rel_path)
        #             )
        #         ).scalar()
        # if not asset_id:
        #     logger.warning("[store] put_asset(run=%s kind=%s) could not resolve an asset id", run_id, kind)
        #     return None
        # await _upload_if_needed(int(asset_id), run_id=run_id, kind=kind, dest=dest,
        #                         filename=object_name, page_url=page_url, mime=mime)
        # return AssetRef(asset_id=int(asset_id), rel_path=rel_path, sha256=sha, bytes=len(raw))
        # ─────────────────────────────────────────────────────────────────────

        # Object-storage name: content hash for images/HTML (deduped, stable);
        # hash-prefixed original name for report-like files so raw/ocr/ keeps
        # "text_detection_report.json" and "contrast_report.csv" readable.
        object_name = (
            f"{sha[:8]}-{src_name}"
            if kind in ("ocr_report", "step_log", "crawler_json") and src_name
            else f"{sha}.{ext}"
        )
        from ka11y.storage.uploader import upload_asset_file

        ref = await upload_asset_file(
            run_id, kind=kind, path=dest, filename=object_name, page_url=page_url, content_type=mime
        )
        if ref is None:
            # Storage off or the upload failed: the local copy stays usable
            # through the legacy ?path= route; nothing to register.
            return None
        return AssetRef(asset_id=0, rel_path=rel_path, sha256=sha, bytes=len(raw), object_key=ref.key)
    except Exception:  # noqa: BLE001
        logger.warning("[store] put_asset(run=%s kind=%s) failed", run_id, kind, exc_info=True)
        return None


# ── PostgreSQL-era upload bookkeeping — switched off; put_asset uploads directly ──
# async def _upload_if_needed(
#     asset_id: int,
#     *,
#     run_id: str,
#     kind: str,
#     dest: Path,
#     filename: str,
#     page_url: Optional[str],
#     mime: Optional[str],
# ) -> None:
#     """Mirror the bytes to object storage (S3 / local artifact dir) once per
#     row and remember the key. Storage off, or already uploaded → no-op.
#     Never raises: the local copy is the fallback."""
#     try:
#         from ka11y.storage.backends import get_store
#
#         if get_store() is None:
#             return
#         async with session_scope() as s:
#             existing = (await s.execute(select(AuditAsset.object_key).where(AuditAsset.id == asset_id))).scalar()
#         if existing:
#             return
#         from ka11y.storage.uploader import upload_asset_file
#
#         ref = await upload_asset_file(
#             run_id, kind=kind, path=dest, filename=filename, page_url=page_url, content_type=mime
#         )
#         if ref:
#             async with session_scope() as s:
#                 await s.execute(
#                     update(AuditAsset)
#                     .where(AuditAsset.id == asset_id)
#                     .values(object_key=ref.key, object_bucket=ref.bucket if ref.backend == "s3" else None)
#                 )
#     except Exception:  # noqa: BLE001
#         logger.debug("[store] asset %s upload skipped", asset_id, exc_info=True)


async def get_asset_record(asset_id: int) -> Optional[Dict[str, Any]]:
    """The asset row plus ``abs_path`` (None when the local file is gone, e.g.
    pruned by retention — the object store copy may still exist). Always
    None while PostgreSQL is switched off: there are no asset rows."""
    if not is_configured():
        return None
    async with session_scope() as s:
        a = await s.get(AuditAsset, int(asset_id))
        if a is None:
            return None
        row: Dict[str, Any] = {
            "id": a.id, "run_id": str(a.job_id), "job_id": str(a.job_id), "kind": a.kind,
            "rel_path": a.rel_path, "mime": a.mime, "bytes": a.bytes,
            "object_key": a.object_key, "object_bucket": a.object_bucket,
        }
    base = asset_dir().resolve()
    abs_path = (base / row["rel_path"]).resolve()
    try:
        abs_path.relative_to(base)  # path-traversal guard
    except ValueError:
        logger.warning("[store] asset %s escapes asset_dir", asset_id)
        return None
    row["abs_path"] = str(abs_path) if abs_path.is_file() else None
    return row


async def get_asset(asset_id: int) -> Optional[Dict[str, Any]]:
    """Resolve an asset row + absolute local path for serving, or None when
    the file is not on local disk (callers that need the bytes regardless
    use :func:`get_asset_record` and the object store)."""
    row = await get_asset_record(asset_id)
    if not row or not row.get("abs_path"):
        return None
    return row


def _is_local_path(src: Optional[str]) -> bool:
    """True only for an on-disk file path (not a URL, data URI, or served route)."""
    if not src or not isinstance(src, str):
        return False
    if src.startswith(("http://", "https://", "data:", "/api/v1/")):
        return False
    try:
        return Path(src).is_file()
    except OSError:
        return False


async def register_report_assets(run_id: str, report: Dict[str, Any]) -> int:
    """Content-address every on-disk image the report references and rewrite the
    frontend-facing URL fields to the ``/api/v1/assets/{id}`` route.

    This is the P2 integration point. Producers keep writing to their working
    dirs; the report is the one place that knows which files survived into the
    final result, so we register them here and repoint:
      * contrast/image-report ``images[].image_url`` → asset URL (was ?path=)
      * finding ``element.image_src`` local paths → asset URL (was ?path=)

    Idempotent + best-effort: a failure on one image never aborts the rest or
    the audit. Returns the number of assets registered.
    """
    n = 0
    try:
        # Report image blocks (contrast / OCR visualiser).
        for report_key, kind in (
            ("contrast_report", "contrast_region"),
            ("image_audit_report", "ocr_crop"),
        ):
            block = report.get(report_key) or {}
            for img in block.get("images", []) or []:
                path = img.get("path")
                if not path or not Path(path).is_file():
                    continue
                ref = await put_asset(
                    run_id=run_id, kind=kind, data=path, page_url=img.get("page_url")
                )
                if ref:
                    img["asset_id"] = ref.asset_id or None
                    img["asset_key"] = ref.object_key
                    img["asset_url"] = ref.url
                    img["image_url"] = ref.url  # served via /assets, not ?path=
                    n += 1

        # Finding-level images (element.image_src pointing at a local crop).
        for array_key in ("violations", "needs_review", "passes"):
            for finding in report.get(array_key, []) or []:
                element = finding.get("element")
                if not isinstance(element, dict):
                    continue
                src = element.get("image_src")
                if not _is_local_path(src):
                    continue
                ref = await put_asset(
                    run_id=run_id,
                    kind="finding_image",
                    data=src,
                    page_url=element.get("page_url"),
                )
                if ref:
                    element["image_src"] = ref.url
                    element["asset_id"] = ref.asset_id or None
                    element["asset_key"] = ref.object_key
                    n += 1
    except Exception:  # noqa: BLE001
        logger.warning("[store] register_report_assets(%s) failed", run_id, exc_info=True)
    return n


def prune_run_assets(run_id: str) -> None:
    """Delete the on-disk asset directory for a run. Best-effort; never raises."""
    try:
        run_dir = asset_dir() / run_id
        if run_dir.is_dir():
            shutil.rmtree(run_dir, ignore_errors=True)
    except Exception:  # noqa: BLE001
        logger.debug("[store] prune_run_assets(%s) failed", run_id, exc_info=True)
