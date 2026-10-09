"""
ka11y/queue/messages.py
=======================
The SQS message body for one audit job.

Deliberately small (a few hundred bytes): the job id, the audited URL, the
request parameters the worker needs to rebuild a ``CombinedRequest``, and
attempt metadata. Everything large — stage progress, the report, findings,
screenshots — is written to object storage keyed by ``job_id`` and never
passes through the queue.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ka11y.api.v1.combined.models import CombinedRequest

#: Bump when the body shape changes incompatibly; the worker refuses unknown versions.
MESSAGE_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditJobMessage(BaseModel):
    """One queued audit. ``payload`` is ``CombinedRequest.model_dump(mode="json")``."""

    version: int = Field(default=MESSAGE_VERSION)
    job_id: str
    url: str
    payload: Dict[str, Any]
    created_at: str = Field(default_factory=_now_iso)
    #: 1-based publish attempt. SQS redeliveries do not change it — the worker
    #: reads the delivery count from the ``ApproximateReceiveCount`` attribute.
    attempt: int = Field(default=1, ge=1)
    #: The job this one re-audits, when submitted through POST /{job_id}/rerun.
    rerun_of: Optional[str] = None

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def for_request(
        cls,
        job_id: str,
        request: CombinedRequest,
        *,
        created_at: Optional[str] = None,
        rerun_of: Optional[str] = None,
    ) -> "AuditJobMessage":
        return cls(
            job_id=job_id,
            url=str(request.url),
            payload=request.model_dump(mode="json"),
            created_at=created_at or _now_iso(),
            rerun_of=rerun_of,
        )

    def request(self) -> CombinedRequest:
        """Rebuild the audit request. Raises ``pydantic.ValidationError`` when
        the payload is not a valid ``CombinedRequest`` (poison message)."""
        return CombinedRequest(**self.payload)

    # ── wire format ─────────────────────────────────────────────────────────

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)

    @classmethod
    def from_json(cls, body: str) -> "AuditJobMessage":
        """Parse a message body. Raises ``ValueError`` on malformed JSON, a
        wrong version, or a body that does not fit the model."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"message body is not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("message body must be a JSON object")
        version = data.get("version", MESSAGE_VERSION)
        if version != MESSAGE_VERSION:
            raise ValueError(f"unsupported message version {version!r} (expected {MESSAGE_VERSION})")
        try:
            return cls(**data)
        except Exception as exc:  # pydantic.ValidationError, TypeError
            raise ValueError(f"message body does not fit AuditJobMessage: {exc}") from exc
