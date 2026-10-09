"""
ka11y/worker/
=============
The audit worker: a separate process that consumes ``AuditJobMessage``s from
SQS and runs audits, at most ``WORKER_MAX_CONCURRENCY`` (default 2) at a time.

    python -m ka11y.worker.worker

concurrency.py — ``ConcurrencyLimiter``: slots are acquired BEFORE a message
                 is received, and only as many messages as free slots are
                 pulled, so a message's visibility timeout never burns while
                 it waits for a slot.
worker.py      — ``Worker``: poll loop, per-message handler (idempotency,
                 cancel marker, attempt cap, visibility heartbeat), graceful
                 SIGTERM/SIGINT shutdown, and the ``main()`` entry point.
"""

from __future__ import annotations

from ka11y.worker.concurrency import ConcurrencyLimiter, max_concurrency_from_env
from ka11y.worker.worker import Worker

__all__ = ["ConcurrencyLimiter", "Worker", "max_concurrency_from_env"]
