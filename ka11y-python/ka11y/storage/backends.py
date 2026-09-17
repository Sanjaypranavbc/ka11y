"""
ka11y/storage/backends.py
=========================
The object store behind every audit artifact (screenshots, HTML snapshots,
OCR artifacts, JSON/CSV/PDF reports, crash dumps).

Two interchangeable backends behind one small async interface:

* :class:`S3ObjectStore`    — Amazon S3 (or any S3-compatible endpoint such as
                              MinIO/LocalStack via KA11Y_S3_ENDPOINT_URL).
                              boto3 is synchronous, so every call runs in a
                              worker thread; the event loop never blocks.
* :class:`LocalObjectStore` — the same keys as files under KA11Y_ARTIFACT_DIR,
                              for development and for deployments without S3.

Keys are always *relative* (``organizations/…/jobs/<id>/reports/report.json``);
the store prepends the configured bucket prefix. Nothing here knows about
jobs or users — see ``keys.py`` for the layout and ``uploader.py`` for what
gets uploaded when.
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union

from ka11y.config.logger import setup_logger
from ka11y.storage.config import StorageSettings, settings

logger = setup_logger(name="KAC", tag="storage")

Bytes = Union[bytes, bytearray, memoryview]


@dataclass(frozen=True)
class ObjectRef:
    backend: str  # s3 | local
    bucket: str  # bucket name, or the local root dir
    key: str  # relative key (without the bucket prefix)
    size: int
    content_type: Optional[str]

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}" if self.backend == "s3" else f"file://{self.bucket}/{self.key}"


def guess_type(name: str, default: str = "application/octet-stream") -> str:
    ct, _ = mimetypes.guess_type(name)
    return ct or default


class ObjectStore(Protocol):
    backend: str

    async def put_bytes(self, key: str, data: Bytes, *, content_type: Optional[str] = None) -> ObjectRef: ...
    async def put_file(self, key: str, path: Union[str, Path], *, content_type: Optional[str] = None) -> ObjectRef: ...
    async def get_bytes(self, key: str) -> Optional[bytes]: ...
    async def exists(self, key: str) -> bool: ...
    async def download_url(self, key: str, *, expires: Optional[int] = None, filename: Optional[str] = None) -> Optional[str]: ...
    async def list_keys(self, prefix: str) -> List[str]: ...
    async def delete_prefix(self, prefix: str) -> int: ...


# ── S3 ───────────────────────────────────────────────────────────────────────


class S3ObjectStore:
    backend = "s3"

    def __init__(self, cfg: StorageSettings, client: Any = None) -> None:
        self._cfg = cfg
        self._client = client  # injected in tests; created lazily otherwise

    @property
    def bucket(self) -> str:
        return self._cfg.bucket

    def _full(self, key: str) -> str:
        key = key.lstrip("/")
        return f"{self._cfg.prefix}/{key}" if self._cfg.prefix else key

    def _strip(self, full_key: str) -> str:
        p = self._cfg.prefix + "/" if self._cfg.prefix else ""
        return full_key[len(p):] if p and full_key.startswith(p) else full_key

    def client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                region_name=self._cfg.region,
                endpoint_url=self._cfg.endpoint_url,
                config=Config(retries={"max_attempts": 4, "mode": "standard"}, signature_version="s3v4"),
            )
        return self._client

    def _extra_args(self, content_type: Optional[str]) -> Dict[str, Any]:
        extra: Dict[str, Any] = {}
        if content_type:
            extra["ContentType"] = content_type
        if self._cfg.sse:
            extra["ServerSideEncryption"] = self._cfg.sse
            if self._cfg.sse == "aws:kms" and self._cfg.kms_key_id:
                extra["SSEKMSKeyId"] = self._cfg.kms_key_id
        return extra

    async def put_bytes(self, key: str, data: Bytes, *, content_type: Optional[str] = None) -> ObjectRef:
        content_type = content_type or guess_type(key)
        raw = bytes(data)

        def _do() -> None:
            self.client().put_object(
                Bucket=self.bucket, Key=self._full(key), Body=raw, **self._extra_args(content_type)
            )

        await asyncio.to_thread(_do)
        return ObjectRef("s3", self.bucket, key, len(raw), content_type)

    async def put_file(self, key: str, path: Union[str, Path], *, content_type: Optional[str] = None) -> ObjectRef:
        p = Path(path)
        content_type = content_type or guess_type(p.name)
        size = p.stat().st_size

        def _do() -> None:
            self.client().upload_file(
                str(p), self.bucket, self._full(key), ExtraArgs=self._extra_args(content_type)
            )

        await asyncio.to_thread(_do)
        return ObjectRef("s3", self.bucket, key, size, content_type)

    async def get_bytes(self, key: str) -> Optional[bytes]:
        def _do() -> Optional[bytes]:
            try:
                obj = self.client().get_object(Bucket=self.bucket, Key=self._full(key))
                return obj["Body"].read()
            except self.client().exceptions.NoSuchKey:
                return None

        return await asyncio.to_thread(_do)

    async def exists(self, key: str) -> bool:
        def _do() -> bool:
            try:
                self.client().head_object(Bucket=self.bucket, Key=self._full(key))
                return True
            except Exception:  # noqa: BLE001 — botocore ClientError 404
                return False

        return await asyncio.to_thread(_do)

    async def download_url(self, key: str, *, expires: Optional[int] = None, filename: Optional[str] = None) -> Optional[str]:
        params: Dict[str, Any] = {"Bucket": self.bucket, "Key": self._full(key)}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        def _do() -> str:
            return self.client().generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires or self._cfg.presign_seconds
            )

        return await asyncio.to_thread(_do)

    async def list_keys(self, prefix: str) -> List[str]:
        def _do() -> List[str]:
            out: List[str] = []
            paginator = self.client().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self._full(prefix)):
                for item in page.get("Contents", []) or []:
                    out.append(self._strip(item["Key"]))
            return out

        return await asyncio.to_thread(_do)

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list_keys(prefix)
        if not keys:
            return 0

        def _do() -> None:
            c = self.client()
            for i in range(0, len(keys), 1000):
                chunk = [{"Key": self._full(k)} for k in keys[i : i + 1000]]
                c.delete_objects(Bucket=self.bucket, Delete={"Objects": chunk, "Quiet": True})

        await asyncio.to_thread(_do)
        return len(keys)


# ── local disk ───────────────────────────────────────────────────────────────


class LocalObjectStore:
    backend = "local"

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    @property
    def bucket(self) -> str:
        return str(self._root)

    def _path(self, key: str) -> Path:
        p = (self._root / key.lstrip("/")).resolve()
        p.relative_to(self._root)  # traversal guard (raises ValueError)
        return p

    async def put_bytes(self, key: str, data: Bytes, *, content_type: Optional[str] = None) -> ObjectRef:
        p = self._path(key)
        raw = bytes(data)

        def _do() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(raw)
            os.replace(tmp, p)

        await asyncio.to_thread(_do)
        return ObjectRef("local", self.bucket, key, len(raw), content_type or guess_type(key))

    async def put_file(self, key: str, path: Union[str, Path], *, content_type: Optional[str] = None) -> ObjectRef:
        src = Path(path)
        p = self._path(key)

        def _do() -> int:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            shutil.copyfile(src, tmp)
            os.replace(tmp, p)
            return p.stat().st_size

        size = await asyncio.to_thread(_do)
        return ObjectRef("local", self.bucket, key, size, content_type or guess_type(src.name))

    async def get_bytes(self, key: str) -> Optional[bytes]:
        p = self._path(key)
        return await asyncio.to_thread(lambda: p.read_bytes() if p.is_file() else None)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def download_url(self, key: str, *, expires: Optional[int] = None, filename: Optional[str] = None) -> Optional[str]:
        return None  # served through the API instead (no direct URL for local files)

    def local_path(self, key: str) -> Optional[Path]:
        p = self._path(key)
        return p if p.is_file() else None

    async def list_keys(self, prefix: str) -> List[str]:
        base = self._path(prefix)

        def _do() -> List[str]:
            if not base.exists():
                return []
            return sorted(
                str(f.relative_to(self._root)).replace(os.sep, "/")
                for f in base.rglob("*")
                if f.is_file()
            )

        return await asyncio.to_thread(_do)

    async def delete_prefix(self, prefix: str) -> int:
        keys = await self.list_keys(prefix)
        base = self._path(prefix)
        await asyncio.to_thread(lambda: shutil.rmtree(base, ignore_errors=True))
        return len(keys)


# ── factory ──────────────────────────────────────────────────────────────────

_store: Optional[Any] = None
_store_backend: Optional[str] = None


def get_store() -> Optional[Any]:
    """The configured store, or None when storage is off. Re-created when the
    backend setting changes (tests flip it)."""
    global _store, _store_backend
    cfg = settings()
    if not cfg.enabled:
        return None
    signature = f"{cfg.backend}|{cfg.bucket}|{cfg.prefix}|{cfg.local_dir}|{cfg.endpoint_url}"
    if _store is None or _store_backend != signature:
        _store = S3ObjectStore(cfg) if cfg.backend == "s3" else LocalObjectStore(cfg.local_dir)
        _store_backend = signature
        logger.info("[storage] backend=%s target=%s", cfg.backend, cfg.bucket or cfg.local_dir)
    return _store


def reset_store() -> None:
    global _store, _store_backend
    _store = None
    _store_backend = None
