"""
ka11y/queue/sqs.py
==================
Thin async wrapper around the boto3 SQS client.

boto3 is synchronous; every call here runs in ``asyncio.to_thread`` so a
20-second long poll or a slow network never blocks the event loop that is
driving audits (worker) or answering requests (API).

Configuration (environment; read on every :func:`settings` call so tests can
flip it):

  SQS_QUEUE_URL             the audit job queue (required to publish/consume)
  AWS_REGION                falls back to AWS_DEFAULT_REGION
  SQS_ENDPOINT_URL          LocalStack / ElasticMQ endpoint (empty = real AWS)
  SQS_VISIBILITY_TIMEOUT    seconds a received message stays hidden (default 300).
                            The worker extends it every timeout/2 while an
                            audit runs, so this does not have to cover a whole
                            audit — only the gap between two heartbeats.
  SQS_WAIT_TIME_SECONDS     long-poll duration, 0–20 (default 20)

Credentials come from the standard AWS chain (env vars, shared config,
instance/task role). LocalStack accepts any non-empty key pair.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ka11y.config.logger import setup_logger
from ka11y.queue.messages import AuditJobMessage

logger = setup_logger(name="KAC", tag="queue.sqs")

#: SQS caps one ReceiveMessage call at 10 messages.
MAX_RECEIVE_BATCH = 10


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[sqs] %s=%r is not an integer; using %d", name, raw, default)
        return default


@dataclass(frozen=True)
class SQSSettings:
    queue_url: str
    region: Optional[str]
    endpoint_url: Optional[str]
    visibility_timeout: int
    wait_time_seconds: int

    @property
    def configured(self) -> bool:
        return bool(self.queue_url)


def settings() -> SQSSettings:
    wait = _int_env("SQS_WAIT_TIME_SECONDS", 20)
    return SQSSettings(
        queue_url=os.getenv("SQS_QUEUE_URL", "").strip(),
        region=os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None,
        endpoint_url=(os.getenv("SQS_ENDPOINT_URL") or "").strip() or None,
        visibility_timeout=max(0, _int_env("SQS_VISIBILITY_TIMEOUT", 300)),
        wait_time_seconds=min(20, max(0, wait)),
    )


@dataclass
class ReceivedMessage:
    """One delivery of a queued message."""

    message_id: str
    receipt_handle: str
    body: str
    #: How many times SQS has handed this message out, this delivery included.
    receive_count: int
    attributes: Dict[str, Any]

    def parse(self) -> AuditJobMessage:
        return AuditJobMessage.from_json(self.body)


class SQSNotConfigured(RuntimeError):
    """SQS_QUEUE_URL is empty: nothing to publish to or consume from."""


class SQSClient:
    """Async facade over one SQS queue. Safe to share across tasks: the boto3
    client is thread-safe for API calls, and every call runs on a worker
    thread."""

    def __init__(self, cfg: Optional[SQSSettings] = None, client: Any = None) -> None:
        self._cfg = cfg or settings()
        self._client = client  # injected in tests; created lazily otherwise

    # ── configuration ───────────────────────────────────────────────────────

    @property
    def cfg(self) -> SQSSettings:
        return self._cfg

    @property
    def queue_url(self) -> str:
        return self._cfg.queue_url

    @property
    def configured(self) -> bool:
        return self._cfg.configured

    def _require(self) -> str:
        if not self._cfg.queue_url:
            raise SQSNotConfigured("SQS_QUEUE_URL is not set")
        return self._cfg.queue_url

    def client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "sqs",
                region_name=self._cfg.region,
                endpoint_url=self._cfg.endpoint_url,
                config=Config(retries={"max_attempts": 4, "mode": "standard"}),
            )
        return self._client

    # ── operations ──────────────────────────────────────────────────────────

    async def send_message(self, msg: AuditJobMessage) -> str:
        """Publish one job. Returns the SQS message id. Raises on failure so
        the caller (the submit route) can fail the job and answer 503."""
        url = self._require()
        body = msg.to_json()

        def _do() -> str:
            resp = self.client().send_message(
                QueueUrl=url,
                MessageBody=body,
                MessageAttributes={
                    "job_id": {"DataType": "String", "StringValue": msg.job_id},
                },
            )
            return str(resp.get("MessageId", ""))

        message_id = await asyncio.to_thread(_do)
        logger.info("[sqs] job %s published (message_id=%s)", msg.job_id, message_id)
        return message_id

    async def receive_messages(
        self, max_messages: int = 1, wait_time: Optional[int] = None
    ) -> List[ReceivedMessage]:
        """Long-poll for up to *max_messages* (1–10). Returns ``[]`` when the
        wait elapses with nothing to do."""
        url = self._require()
        n = max(1, min(MAX_RECEIVE_BATCH, int(max_messages)))
        wait = self._cfg.wait_time_seconds if wait_time is None else min(20, max(0, int(wait_time)))
        visibility = self._cfg.visibility_timeout

        def _do() -> List[ReceivedMessage]:
            kwargs: Dict[str, Any] = {
                "QueueUrl": url,
                "MaxNumberOfMessages": n,
                "WaitTimeSeconds": wait,
                "AttributeNames": ["ApproximateReceiveCount", "SentTimestamp"],
                "MessageAttributeNames": ["All"],
            }
            if visibility > 0:
                kwargs["VisibilityTimeout"] = visibility
            resp = self.client().receive_message(**kwargs)
            out: List[ReceivedMessage] = []
            for m in resp.get("Messages", []) or []:
                attrs = dict(m.get("Attributes") or {})
                try:
                    count = int(attrs.get("ApproximateReceiveCount", "1"))
                except (TypeError, ValueError):
                    count = 1
                out.append(
                    ReceivedMessage(
                        message_id=str(m.get("MessageId", "")),
                        receipt_handle=str(m["ReceiptHandle"]),
                        body=str(m.get("Body", "")),
                        receive_count=max(1, count),
                        attributes=attrs,
                    )
                )
            return out

        return await asyncio.to_thread(_do)

    async def delete_message(self, receipt_handle: str) -> None:
        url = self._require()

        def _do() -> None:
            self.client().delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)

        await asyncio.to_thread(_do)

    async def change_visibility(self, receipt_handle: str, seconds: int) -> None:
        """Hide (or, with 0, immediately re-expose) a received message."""
        url = self._require()
        secs = max(0, min(43200, int(seconds)))  # SQS maximum is 12 hours

        def _do() -> None:
            self.client().change_message_visibility(
                QueueUrl=url, ReceiptHandle=receipt_handle, VisibilityTimeout=secs
            )

        await asyncio.to_thread(_do)

    async def approximate_counts(self) -> Dict[str, int]:
        """Visible / in-flight / delayed counts, for health and tests."""
        url = self._require()

        def _do() -> Dict[str, int]:
            resp = self.client().get_queue_attributes(
                QueueUrl=url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                    "ApproximateNumberOfMessagesDelayed",
                ],
            )
            attrs = resp.get("Attributes") or {}
            return {
                "visible": int(attrs.get("ApproximateNumberOfMessages", 0)),
                "in_flight": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0)),
                "delayed": int(attrs.get("ApproximateNumberOfMessagesDelayed", 0)),
            }

        return await asyncio.to_thread(_do)


# ── module singleton ─────────────────────────────────────────────────────────

_client: Optional[SQSClient] = None
_client_signature: Optional[str] = None


def get_client() -> SQSClient:
    """The process-wide client, rebuilt when the environment changes (tests)."""
    global _client, _client_signature
    cfg = settings()
    signature = f"{cfg.queue_url}|{cfg.region}|{cfg.endpoint_url}|{cfg.visibility_timeout}|{cfg.wait_time_seconds}"
    if _client is None or _client_signature != signature:
        _client = SQSClient(cfg)
        _client_signature = signature
        if cfg.configured:
            logger.info(
                "[sqs] queue=%s endpoint=%s visibility=%ds wait=%ds",
                cfg.queue_url, cfg.endpoint_url or "aws", cfg.visibility_timeout, cfg.wait_time_seconds,
            )
    return _client


def reset_client() -> None:
    global _client, _client_signature
    _client = None
    _client_signature = None
