"""
ka11y/worker/worker.py
======================
The audit worker process.

    python -m ka11y.worker.worker

Loop
    acquire a slot → long-poll SQS for at most (free slots) messages → one
    task per message → the task releases its slot in ``finally``.

Per message
    1. Parse. A body that is not an ``AuditJobMessage`` can never succeed and
       is deleted (logged at ERROR) instead of cycling through the DLQ.
    2. Read state.json. Already completed/failed/cancelled → duplicate
       delivery (SQS standard queues are at-least-once): delete, skip.
       Cancel marker present → settle as cancelled, delete.
       Delivered more than WORKER_MAX_ATTEMPTS times → fail, delete.
    3. Seed the in-process hot cache, write state.json ``running``, start the
       visibility heartbeat, run the existing audit (``runner._run_job_body``,
       untouched) with the progress sink mirroring every stage event.
    4. The runner records its own outcome in the hot cache. Completed or
       failed → write the final state.json, delete the message.
       The runner *crashed* (raised past its own handler) → state goes back to
       ``queued`` and the message is left for SQS to redeliver after the
       visibility timeout; on the last permitted attempt it is failed instead.
       Set WORKER_RETRY_FAILED_AUDITS=1 to also redeliver audits the runner
       itself recorded as failed (off by default: those are usually a site
       that is down or blocks crawlers, and a retry costs a whole audit).

Shutdown
    SIGTERM/SIGINT stop the poll loop; in-flight audits finish; then exit.

Environment
    WORKER_MAX_CONCURRENCY       slots (default 2)
    WORKER_MAX_ATTEMPTS          deliveries before a job is failed (default 3,
                                 the DLQ's maxReceiveCount)
    WORKER_RETRY_FAILED_AUDITS   "1" redelivers runner-recorded failures too
    WORKER_SHUTDOWN_TIMEOUT      seconds to wait for in-flight audits (default
                                 the job timeout + 60)
    SQS_*                        see ka11y/queue/sqs.py
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Set

from ka11y.api.v1.combined.models import CombinedRequest
from ka11y.config.logger import setup_logger
from ka11y.queue.sqs import MAX_RECEIVE_BATCH, ReceivedMessage, SQSClient, get_client
from ka11y.storage import jobstate
from ka11y.storage.jobstate import TERMINAL_STATUSES
from ka11y.worker.concurrency import ConcurrencyLimiter

logger = setup_logger(name="KAC", tag="worker")

RunJob = Callable[[str, CombinedRequest, Optional[str]], Awaitable[None]]

_GENERIC_ERROR = "Audit failed due to an internal error."
_STATE_WRITE_RETRIES = 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("[worker] %s=%r is not an integer; using %d", name, raw, default)
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


async def _default_run_job(job_id: str, request: CombinedRequest, filter_rule: Optional[str]) -> None:
    from ka11y.api.v1.combined.runner import _run_job_body

    await _run_job_body(job_id, request, filter_rule)


class Worker:
    """One poll loop over one SQS queue. Construct, then ``await run()``."""

    def __init__(
        self,
        *,
        sqs: Optional[SQSClient] = None,
        limiter: Optional[ConcurrencyLimiter] = None,
        run_job: Optional[RunJob] = None,
        max_attempts: Optional[int] = None,
        retry_failed_audits: Optional[bool] = None,
        heartbeat_interval: Optional[float] = None,
        poll_wait: Optional[int] = None,
        idle_exit: bool = False,
    ) -> None:
        self.sqs = sqs or get_client()
        self.limiter = limiter or ConcurrencyLimiter()
        self._run_job: RunJob = run_job or _default_run_job
        self.max_attempts = max(1, max_attempts if max_attempts is not None else _int_env("WORKER_MAX_ATTEMPTS", 3))
        self.retry_failed_audits = (
            retry_failed_audits if retry_failed_audits is not None else _bool_env("WORKER_RETRY_FAILED_AUDITS", False)
        )
        visibility = self.sqs.cfg.visibility_timeout
        self.heartbeat_interval = (
            float(heartbeat_interval) if heartbeat_interval is not None else max(1.0, visibility / 2.0)
        )
        self.poll_wait = poll_wait
        #: Tests: return from run() once a poll comes back empty with nothing in flight.
        self.idle_exit = idle_exit
        self._stopping: Optional[asyncio.Event] = None
        self._tasks: Set[asyncio.Task] = set()
        self.processed = 0

    # ── lifecycle ───────────────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Stop polling; in-flight audits run to completion. Signal-handler safe."""
        if self._stopping is not None and not self._stopping.is_set():
            logger.info("[worker] stop requested; waiting for %d in-flight audit(s)", self.limiter.active)
            self._stopping.set()

    @property
    def stopping(self) -> bool:
        return self._stopping is not None and self._stopping.is_set()

    async def run(self) -> None:
        self._stopping = asyncio.Event()
        from ka11y.api.v1.combined.store import add_broadcast_sink, remove_broadcast_sink

        add_broadcast_sink(jobstate.progress_sink)
        logger.info(
            "[worker] started pid=%d max_concurrency=%d max_attempts=%d queue=%s",
            os.getpid(), self.limiter.max_concurrency, self.max_attempts, self.sqs.queue_url,
        )
        backoff = 1.0
        try:
            while not self._stopping.is_set():
                if not await self._acquire_or_stop():
                    break
                extra = await self.limiter.acquire_available(MAX_RECEIVE_BATCH - 1)
                held = 1 + extra
                try:
                    messages = await self.sqs.receive_messages(max_messages=held, wait_time=self.poll_wait)
                    backoff = 1.0
                except Exception:  # noqa: BLE001
                    logger.exception("[worker] receive failed; retrying in %.0fs", backoff)
                    for _ in range(held):
                        self.limiter.release()
                    await self._sleep_or_stop(backoff)
                    backoff = min(30.0, backoff * 2)
                    continue
                for _ in range(held - len(messages)):
                    self.limiter.release()
                if not messages:
                    if self.idle_exit and not self._tasks:
                        break
                    continue
                for received in messages:
                    task = asyncio.create_task(self._run_message(received), name=f"audit:{received.message_id}")
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
        finally:
            if self._tasks:
                timeout = _int_env("WORKER_SHUTDOWN_TIMEOUT", _int_env("KA11Y_JOB_TIMEOUT_SECONDS", 1800) + 60)
                logger.info("[worker] draining %d in-flight audit(s) (timeout %ds)", len(self._tasks), timeout)
                done, pending = await asyncio.wait(set(self._tasks), timeout=timeout)
                for t in pending:
                    logger.error("[worker] task %s did not finish before shutdown timeout", t.get_name())
            remove_broadcast_sink(jobstate.progress_sink)
            logger.info("[worker] stopped (processed=%d)", self.processed)

    async def _acquire_or_stop(self) -> bool:
        """Wait for a slot, but give up as soon as a stop is requested."""
        assert self._stopping is not None
        acquire = asyncio.create_task(self.limiter.acquire())
        stop = asyncio.create_task(self._stopping.wait())
        done, _ = await asyncio.wait({acquire, stop}, return_when=asyncio.FIRST_COMPLETED)
        if acquire in done:
            stop.cancel()
            if self._stopping.is_set():
                self.limiter.release()
                return False
            return True
        acquire.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await acquire
        if not acquire.cancelled() and acquire.exception() is None:
            self.limiter.release()  # it completed in the same tick as the stop
        return False

    async def _sleep_or_stop(self, seconds: float) -> None:
        assert self._stopping is not None
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)

    # ── per message ─────────────────────────────────────────────────────────

    async def _run_message(self, received: ReceivedMessage) -> None:
        try:
            await self._handle(received)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("[worker] message %s: unhandled error", received.message_id)
        finally:
            self.limiter.release()

    async def _handle(self, received: ReceivedMessage) -> None:
        # 1. parse ------------------------------------------------------------
        try:
            msg = received.parse()
            request = msg.request()
        except Exception as exc:  # noqa: BLE001 — poison message
            logger.error(
                "[worker] message %s is not a valid AuditJobMessage (%s); deleting", received.message_id, exc
            )
            await self._delete(received, job_id="?")
            return
        job_id = msg.job_id
        attempt = received.receive_count

        # 2. idempotency / cancel / attempt cap ---------------------------------
        state = await jobstate.get_state(job_id)
        if state is None:
            logger.warning("[worker] job %s: no state.json; rebuilding it from the message", job_id)
            state = jobstate.new_state(
                job_id, url=msg.url, lang=request.lang, params=msg.payload,
                submitted_at=msg.created_at, rerun_of=msg.rerun_of,
            )
        status = state.get("status")
        if status in TERMINAL_STATUSES:
            logger.info("[worker] job %s: already %s; duplicate delivery skipped", job_id, status)
            await self._delete(received, job_id=job_id)
            return
        if await jobstate.is_cancel_requested(job_id):
            state.update(status="cancelled", completed_at=_now(), current_stage=None)
            await self._write_final(job_id, state)
            logger.info("[worker] job %s: cancelled before start", job_id)
            await self._delete(received, job_id=job_id)
            return
        if attempt > self.max_attempts:
            state.update(
                status="failed", completed_at=_now(), error=_GENERIC_ERROR,
                error_stage="worker", error_id="max_attempts_exceeded", attempt=attempt,
            )
            await self._write_final(job_id, state)
            logger.error("[worker] job %s: delivered %d times (max %d); failed", job_id, attempt, self.max_attempts)
            await self._delete(received, job_id=job_id)
            return

        # 3. run -----------------------------------------------------------------
        from ka11y.api.v1.combined.store import _close_subscribers, _drop_job_lock, _jobs
        from ka11y.storage import keys

        hot = jobstate.to_hot_entry(state)
        hot.update(status="running", attempt=attempt, worker_pid=os.getpid(), run_started_at=_now())
        _jobs[job_id] = hot
        await jobstate.put_state(job_id, jobstate.snapshot(hot))
        logger.info(
            "[worker] job %s: starting (attempt %d/%d, url=%s, active=%d/%d)",
            job_id, attempt, self.max_attempts, msg.url, self.limiter.active, self.limiter.max_concurrency,
        )

        heartbeat = asyncio.create_task(self._heartbeat(received, job_id), name=f"heartbeat:{job_id}")
        crashed = False
        try:
            await self._run_job(job_id, request, None)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            crashed = True
            logger.exception("[worker] job %s: runner raised outside its own handler", job_id)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

        # 4. settle ----------------------------------------------------------------
        try:
            final = jobstate.snapshot(_jobs.get(job_id) or hot)
            final["attempt"] = attempt
            if crashed:
                await self._settle_crash(received, job_id, final, attempt)
            else:
                await self._settle_outcome(received, job_id, final, attempt)
        finally:
            self.processed += 1
            _jobs.pop(job_id, None)
            _drop_job_lock(job_id)
            keys.forget_job(job_id)
            with contextlib.suppress(Exception):
                await _close_subscribers(job_id)

    async def _settle_crash(self, received: ReceivedMessage, job_id: str, final: dict, attempt: int) -> None:
        final.update(completed_at=_now(), current_stage=None, error=_GENERIC_ERROR, error_stage="worker")
        final.setdefault("error_id", uuid.uuid4().hex)
        if attempt < self.max_attempts:
            final["status"] = "queued"
            final.pop("completed_at", None)
            await self._write_final(job_id, final)
            logger.warning(
                "[worker] job %s: crashed on attempt %d/%d; left on the queue for redelivery",
                job_id, attempt, self.max_attempts,
            )
            return  # not deleted: SQS redelivers after the visibility timeout
        final["status"] = "failed"
        if await self._write_final(job_id, final):
            await self._delete(received, job_id=job_id)
        logger.error("[worker] job %s: crashed on final attempt %d/%d; failed", job_id, attempt, self.max_attempts)

    async def _settle_outcome(self, received: ReceivedMessage, job_id: str, final: dict, attempt: int) -> None:
        status = final.get("status")
        if status not in TERMINAL_STATUSES:
            # The runner always settles the hot entry; reaching here means it did not.
            logger.error("[worker] job %s: runner returned with status %r; recording as failed", job_id, status)
            final.update(
                status="failed", completed_at=_now(), current_stage=None,
                error=_GENERIC_ERROR, error_stage="worker", error_id=uuid.uuid4().hex,
            )
            status = "failed"
        if status == "failed" and self.retry_failed_audits and attempt < self.max_attempts:
            final["status"] = "queued"
            final.pop("completed_at", None)
            await self._write_final(job_id, final)
            logger.warning(
                "[worker] job %s: failed on attempt %d/%d; WORKER_RETRY_FAILED_AUDITS is on, left for redelivery",
                job_id, attempt, self.max_attempts,
            )
            return
        if await self._write_final(job_id, final):
            await self._delete(received, job_id=job_id)
        else:
            # Without state.json the API would show this job 'running' forever.
            # Leaving the message means a redelivery re-runs the audit, which is
            # the lesser evil; the next attempt's idempotency check reads state.json.
            logger.error("[worker] job %s: final state could not be written; message left on the queue", job_id)
        summary = final.get("result_summary") or {}
        logger.info(
            "[worker] job %s: %s (violations=%s needs_review=%s passes=%s, error_stage=%s)",
            job_id, status, summary.get("violations"), summary.get("needs_review"), summary.get("passes"),
            final.get("error_stage"),
        )

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _heartbeat(self, received: ReceivedMessage, job_id: str) -> None:
        """Extend the message's visibility every ``heartbeat_interval`` seconds
        so a long audit is not redelivered mid-run."""
        visibility = self.sqs.cfg.visibility_timeout or int(self.heartbeat_interval * 2)
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            try:
                await self.sqs.change_visibility(received.receipt_handle, visibility)
                logger.debug("[worker] job %s: visibility extended by %ds", job_id, visibility)
            except Exception:  # noqa: BLE001
                logger.warning("[worker] job %s: visibility heartbeat failed", job_id, exc_info=True)

    async def _write_final(self, job_id: str, state: dict) -> bool:
        for n in range(_STATE_WRITE_RETRIES):
            if await jobstate.put_state(job_id, state):
                return True
            await asyncio.sleep(0.2 * (n + 1))
        return False

    async def _delete(self, received: ReceivedMessage, *, job_id: str) -> None:
        try:
            await self.sqs.delete_message(received.receipt_handle)
            logger.debug("[worker] job %s: message %s deleted", job_id, received.message_id)
        except Exception:  # noqa: BLE001
            logger.warning("[worker] job %s: delete of message %s failed", job_id, received.message_id, exc_info=True)


# ── process entry point ──────────────────────────────────────────────────────


async def _amain() -> int:
    from ka11y.config.env import dotenv_enabled

    if dotenv_enabled():
        from dotenv import load_dotenv

        load_dotenv()

    try:
        from ka11y.observability import init_tracing

        init_tracing()
    except Exception:  # noqa: BLE001
        logger.exception("[worker] tracing failed to initialise; running untraced")

    # PostgreSQL — switched off (S3 only). Every repo call in the runner is
    # commented out; object storage is the only store. Uncomment to mirror
    # runs into the run store again when DATABASE_URL is set.
    # from ka11y.db.engine import is_configured as pg_configured
    #
    # if pg_configured():
    #     try:
    #         from ka11y.db import init_postgres
    #         from ka11y.store import init_store
    #
    #         await init_postgres()
    #         init_store()
    #     except Exception:  # noqa: BLE001
    #         logger.exception("[worker] PostgreSQL layer failed to initialise; continuing on object storage only")
    # else:
    #     logger.info("[worker] DATABASE_URL not set; job state lives in object storage only")
    logger.info("[worker] PostgreSQL is switched off; job state lives in object storage only")

    if not jobstate.storage_available():
        logger.error("[worker] KA11Y_STORAGE_BACKEND=off: there is nowhere to write job state; exiting")
        return 2
    sqs = get_client()
    if not sqs.configured:
        logger.error("[worker] SQS_QUEUE_URL is not set; exiting")
        return 2

    worker = Worker(sqs=sqs)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except (NotImplementedError, RuntimeError):  # Windows / non-main thread
            signal.signal(sig, lambda *_: worker.request_stop())

    try:
        await worker.run()
    finally:
        for label, shutdown in (
            ("browser pool", "ka11y.crawler.browser_pool:shutdown_pool"),
            # ("run-store writer", "ka11y.store:shutdown_store"),  # PostgreSQL: off
            # ("PostgreSQL", "ka11y.db:shutdown_postgres"),        # PostgreSQL: off
            ("CPU pool", "ka11y.store.cpu_pool:shutdown_pool"),
            ("tracing", "ka11y.observability:shutdown_tracing"),
        ):
            try:
                mod_name, fn_name = shutdown.split(":")
                mod = __import__(mod_name, fromlist=[fn_name])
                result = getattr(mod, fn_name)()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.exception("[worker] %s shutdown failed", label)
    return 0


def main() -> int:
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
