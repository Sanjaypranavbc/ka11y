"""
ka11y/api/v1/assets.py
=====================
Content-addressed asset serving.

  GET /api/v1/assets/{asset_id}     Serve a stored asset (screenshot/crop/HAR)

The asset endpoint replaces the per-job ``?path=`` scheme: an asset is served by
its DB id, the row is the authority for the on-disk location, and a containment
check in :func:`store.assets.get_asset` blocks path traversal.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response

from ka11y.store.assets import get_asset_record
from ka11y.storage.backends import LocalObjectStore, get_store

router = APIRouter(tags=["assets"])


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
