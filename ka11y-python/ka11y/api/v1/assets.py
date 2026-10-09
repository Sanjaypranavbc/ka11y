"""
ka11y/api/v1/assets.py
=====================
Content-addressed asset serving.

  GET /api/v1/assets/by-key/{key}   Serve an asset straight from object storage
  GET /api/v1/assets/{asset_id}     Serve a stored asset by its PostgreSQL id
                                    (404 while the DB is switched off)

``by-key`` is the S3-only path: the runner registers every report image with
``store.assets.put_asset``, which uploads it and points ``image_src`` /
``image_url`` at this route. The key must sit under the jobs root
(``anonymous/jobs/…``) and contain no ``..`` segment, so the route can never
read outside the audit artifacts.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from ka11y.store.assets import get_asset_record
from ka11y.storage.backends import LocalObjectStore, get_store
from ka11y.storage.jobstate import JOBS_ROOT

router = APIRouter(tags=["assets"])


def _safe_key(key: str) -> str:
    parts = key.split("/")
    if not key.startswith(JOBS_ROOT) or any(p in ("", ".", "..") for p in parts):
        raise HTTPException(status_code=404, detail="Asset not found")
    return key


@router.get("/assets/by-key/{key:path}")
async def serve_asset_by_key(key: str):
    """Serve one object from the store: 302 to a presigned S3 URL, or the
    bytes / local file when the backend cannot presign."""
    key = _safe_key(key)
    store = get_store()
    if store is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
    if isinstance(store, LocalObjectStore):
        local = store.local_path(key)
        if local is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(str(local), media_type=media_type)
    url = await store.download_url(key)
    if url:
        return RedirectResponse(url, status_code=302)
    data = await store.get_bytes(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(content=data, media_type=media_type)


@router.get("/assets/{asset_id}")
async def serve_asset(asset_id: int):
    """Serve from local disk when the file is there; otherwise from object
    storage (302 to a presigned S3 URL, or the local artifact copy)."""
    row = await get_asset_record(asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    media_type = row.get("mime") or mimetypes.guess_type(row["rel_path"])[0] or "application/octet-stream"
    if row.get("abs_path"):
        return FileResponse(row["abs_path"], media_type=media_type)

    key = row.get("object_key")
    store = get_store() if key else None
    if store is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if isinstance(store, LocalObjectStore):
        local = store.local_path(key)
        if local is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(str(local), media_type=media_type)
    url = await store.download_url(key)
    if url:
        return RedirectResponse(url, status_code=302)
    data = await store.get_bytes(key)
    if data is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(content=data, media_type=media_type)
