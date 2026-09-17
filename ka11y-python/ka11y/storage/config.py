"""
ka11y/storage/config.py
=======================
Object-storage settings, read from the environment on every call.

  KA11Y_STORAGE_BACKEND   auto (default) | s3 | local | off
                          auto = s3 when KA11Y_S3_BUCKET is set, else local
  KA11Y_S3_BUCKET         bucket name (required for s3)
  KA11Y_S3_PREFIX         key prefix inside the bucket   (default "wcag-auditor")
  KA11Y_S3_REGION         falls back to AWS_REGION / AWS_DEFAULT_REGION
  KA11Y_S3_ENDPOINT_URL   MinIO / LocalStack endpoint for local development
  KA11Y_S3_SSE            server-side encryption header ("AES256" or "aws:kms"; empty = bucket default)
  KA11Y_S3_KMS_KEY_ID     with KA11Y_S3_SSE=aws:kms
  KA11Y_S3_PRESIGN_SECONDS  lifetime of download links            (default 900)
  KA11Y_ARTIFACT_DIR      root of the local backend               (default logs/artifacts)

  KA11Y_ARTIFACT_PDF      "1" (default) renders + uploads the PDF report on completion
  KA11Y_HTML_SNAPSHOTS    "1" (default) saves each crawled page's rendered HTML
  KA11Y_ARTIFACT_DELETE_ON_RETENTION
                          "1" deletes a job's objects when the retention sweep
                          removes the run (default "0": keep; use an S3
                          lifecycle rule instead)

Credentials come from the standard AWS chain (env vars, shared config,
instance/task role) — never from this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class StorageSettings:
    backend: str  # s3 | local | off
    bucket: str
    prefix: str
    region: Optional[str]
    endpoint_url: Optional[str]
    sse: Optional[str]
    kms_key_id: Optional[str]
    presign_seconds: int
    local_dir: Path
    pdf_on_complete: bool
    html_snapshots: bool
    delete_on_retention: bool

    @property
    def enabled(self) -> bool:
        return self.backend in ("s3", "local")


def _default_local_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "logs" / "artifacts"


def settings() -> StorageSettings:
    bucket = os.getenv("KA11Y_S3_BUCKET", "").strip()
    backend = os.getenv("KA11Y_STORAGE_BACKEND", "auto").strip().lower() or "auto"
    if backend == "auto":
        backend = "s3" if bucket else "local"
    if backend == "s3" and not bucket:
        backend = "off"
    return StorageSettings(
        backend=backend,
        bucket=bucket,
        prefix=os.getenv("KA11Y_S3_PREFIX", "wcag-auditor").strip().strip("/"),
        region=(
            os.getenv("KA11Y_S3_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or None
        ),
        endpoint_url=os.getenv("KA11Y_S3_ENDPOINT_URL") or None,
        sse=os.getenv("KA11Y_S3_SSE") or None,
        kms_key_id=os.getenv("KA11Y_S3_KMS_KEY_ID") or None,
        presign_seconds=int(os.getenv("KA11Y_S3_PRESIGN_SECONDS", "900")),
        local_dir=Path(os.getenv("KA11Y_ARTIFACT_DIR") or _default_local_dir()),
        pdf_on_complete=_bool("KA11Y_ARTIFACT_PDF", True),
        html_snapshots=_bool("KA11Y_HTML_SNAPSHOTS", True),
        delete_on_retention=_bool("KA11Y_ARTIFACT_DELETE_ON_RETENTION", False),
    )
