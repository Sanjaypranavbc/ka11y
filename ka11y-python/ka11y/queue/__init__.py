"""
ka11y/queue/
============
The audit job queue — Amazon SQS.

    from ka11y.queue import AuditJobMessage, SQSClient, get_client

messages.py — ``AuditJobMessage``: the small JSON document the API publishes
              and the worker consumes. Job state and reports never travel
              through the queue; they live in object storage
              (``ka11y/storage/jobstate.py``).
sqs.py      — ``SQSClient``: boto3 behind ``asyncio.to_thread`` so the event
              loop is never blocked. Configured from the environment
              (SQS_QUEUE_URL, AWS_REGION, SQS_ENDPOINT_URL, …).
"""

from __future__ import annotations

from ka11y.queue.messages import AuditJobMessage
from ka11y.queue.sqs import ReceivedMessage, SQSClient, SQSSettings, get_client, reset_client, settings

__all__ = [
    "AuditJobMessage",
    "ReceivedMessage",
    "SQSClient",
    "SQSSettings",
    "get_client",
    "reset_client",
    "settings",
]
