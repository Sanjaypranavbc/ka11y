# SQS worker: concepts behind the implementation

Branch `aws-arch`, 2026-10-12. Companion to `SQS_WORKER_MIGRATION.md`, which lists
the commits and the before/after code. This file explains the *ideas* each piece of
the implementation relies on, and where each idea lives in the code.

---

## Why the change was made

The previous design ran audits inside the API process. A FastAPI request wrote an
`audit_jobs` row to PostgreSQL with status `queued`, and a dispatcher task in the same
uvicorn process claimed rows and launched the audit as an asyncio task. Polling,
Server-Sent Events, exports and the Chromium pool shared one event loop and one
container.

Four problems followed from that, and SQS removes each of them:

| Problem before | What SQS gives |
|---|---|
| API and audits could not scale separately: every API replica was also a Chromium host | API only admits jobs; N workers run them; scale workers on queue depth |
| PostgreSQL was acting as a queue (polled rows, DB had to be up for a submit) | A real queue; the run store moved to object storage, so no relational table is needed |
| Crash recovery was manual (`_mark_crashed`, `requeue_running` on boot) | Un-acked messages reappear after the visibility timeout; a DLQ catches repeat failures |
| One heavy audit could starve the web tier on the shared event loop | Audits are isolated in the worker; the API stays responsive |

---

## 1. Producer and consumer split

The web API **produces** work and a separate process **consumes** it.

- `ka11y/api/v1/combined/routes.py::_admit_run` writes the job record, publishes a
  message, and returns the job id. The API never runs an audit.
- `ka11y/worker/worker.py::Worker.run` is a long-running loop that pulls messages and
  runs them.

The two sides agree on only two things: the message format and the storage layout.
That is what lets them be deployed, scaled and restarted independently.

## 2. The message is a pointer, not a payload

`ka11y/queue/messages.py::AuditJobMessage` carries the job id, URL, request
parameters, attempt number and a schema `version`. It is a few hundred bytes.

Everything heavy (progress, reports, screenshots) lives in object storage keyed by
job id. This is the *claim check* pattern: the queue moves a reference, storage holds
the data. It keeps the queue cheap and makes retries safe, because redelivering the
message never redelivers data.

The `version` field is a schema version. If the message format changes, an old worker
refuses a new message instead of misreading it.

## 3. Object storage as the system of record

`ka11y/storage/jobstate.py` replaces the PostgreSQL row with a small set of files per
job under `anonymous/jobs/{job_id}/`:

| File | Purpose |
|---|---|
| `state.json` | status, timestamps, attempt count, error details |
| `cancel.json` | presence alone means "cancel requested" |
| `reviews.json` | manual verdicts |
| `reports/report.json` | the finished result |

There is no database, so there is no transaction or lock. The design copes by making
each write a full replacement of a small document and by keeping the set of writers
narrow: the API writes `state.json` once at submit and `cancel.json` on cancel; the
worker owns `state.json` from the moment it picks the job up.

## 4. Long polling

`ka11y/queue/sqs.py::SQSClient.receive_messages` passes `WaitTimeSeconds` of up to
20 s. The call blocks server-side until a message arrives or the wait expires, instead
of hammering SQS with empty receives. The queue itself is created with
`ReceiveMessageWaitTimeSeconds=20` in `localstack/init-sqs.sh`.

## 5. Async over a synchronous SDK

boto3 is blocking. Every call in `sqs.py` runs inside `asyncio.to_thread`, so a 20 s
long poll does not freeze the worker's event loop while other audits are streaming
progress. The rest of the worker stays pure asyncio.

## 6. Visibility timeout and heartbeat (a renewable lease)

SQS does not delete a message on receive. It *hides* it for the visibility timeout
(`SQS_VISIBILITY_TIMEOUT`, 300 s). If the consumer has not deleted it by then, the
message reappears for another consumer. That is the entire crash-recovery story: a
worker that dies mid-audit never deletes the message, so it comes back.

Audits run longer than 5 minutes, so `Worker._heartbeat` calls
`ChangeMessageVisibility` every `visibility / 2` (150 s) to push the deadline out.
If the process dies, the heartbeat dies with it and the lease lapses naturally.

## 7. At-least-once delivery and idempotency

Standard SQS queues deliver a message *at least* once. Duplicates happen on network
hiccups or a late heartbeat. The worker therefore treats every message as a possible
repeat: `Worker._handle` reads `state.json` first, and if the status is already in
`TERMINAL_STATUSES` (`completed`, `failed`, `cancelled`) it deletes the message and
does nothing. `state.json` is the idempotency key.

## 8. Ack after persist

The worker deletes the message only **after** the final `state.json` is written
(`_settle_outcome`). If the order were reversed and the process crashed between the
two steps, the job would vanish with no record. With the current order the worst case
is a duplicate, which §7 absorbs.

## 9. Bounded concurrency and admission order

`ka11y/worker/concurrency.py::ConcurrencyLimiter` wraps an `asyncio.Semaphore` sized
by `WORKER_MAX_CONCURRENCY` (default 2). The order in `Worker.run` is the subtle part:

1. Block for **one** slot (or stop).
2. Grab any extra free slots without blocking.
3. Receive at most that many messages.
4. Release slots that got no message.
5. Each message runs in its own task and releases its slot in `finally`.

Why slot-first: if the worker received a message and *then* waited for a slot, the
message would sit in memory while its lease ran out, SQS would hand it to another
worker, and the audit would run twice. Taking the slot first guarantees every received
message starts immediately.

The runner's own semaphore is bypassed: the worker calls `runner._run_job_body`
directly, so there is exactly one concurrency cap instead of two overlapping ones.

## 10. Retry cap, dead-letter queue, poison messages

Three failure modes, three deliberately different responses:

| Failure | Response |
|---|---|
| Transient crash (runner raised) | Leave the message; SQS redelivers. `ApproximateReceiveCount` gives the attempt number |
| Repeated crash | After `WORKER_MAX_ATTEMPTS` (3): write `failed` / `max_attempts_exceeded`, delete the message. The queue's `RedrivePolicy.maxReceiveCount` is also 3, so anything the worker misses lands in `ka11y-audit-jobs-dlq` |
| Poison message (body is not an `AuditJobMessage`) | Retrying cannot help: log at ERROR and delete immediately, never cycle to the DLQ |

## 11. Cancellation without shared memory

The API and worker share no process, so cancel is a file. The route writes
`cancel.json` (and flips `state.json` to `cancelled` if the job is still queued). The
runner polls `jobstate.is_cancel_requested` at its existing checkpoints. If the worker
picks up a message and the marker is already present, it settles the job as cancelled
and deletes the message.

## 12. Progress mirroring and throttled writes

The old SSE stream had in-memory subscribers in the API. Now the worker registers
`jobstate.progress_sink` as a broadcast sink; every stage event the runner emits is
mirrored into `state.json`. Noisy events are throttled to one write per
`PROGRESS_MIN_INTERVAL_S` (2 s) so a fast crawl does not generate thousands of PUTs.
The API's `/combined/{id}/stream` polls the file every second and re-emits events.
Live progress is slightly delayed, but it survives API restarts and works with any
number of API replicas.

## 13. Graceful shutdown

On SIGTERM/SIGINT the worker stops receiving but lets in-flight audits finish, up to
`WORKER_SHUTDOWN_TIMEOUT` (job timeout + 60 s). The heartbeat keeps leases alive
during the drain. `docker-compose.yml` sets `stop_grace_period: 15m` so Docker does
not kill the container first. A rolling restart therefore never loses a running audit.

## 14. Local parity with LocalStack

`localstack/init-sqs.sh` creates the same queue, DLQ, visibility timeout and redrive
policy that production uses. The code never branches on "local vs AWS"; only the
endpoint URL and credentials change via environment variables. What passes locally is
what runs on AWS.

---

## How the pieces fit together

1. Submit writes `state.json` (`queued`) and sends an `AuditJobMessage`.
2. Worker takes a slot, long-polls, receives the message.
3. Worker reads `state.json`: terminal → delete and skip; cancel marker → settle as
   cancelled; attempt > cap → settle as failed.
4. Worker marks `running`, starts the heartbeat, runs the unchanged audit body.
5. Progress is mirrored to `state.json` as it goes; the API streams it to the browser.
6. Success: write final state, **then** delete the message.
7. Crash: leave the message; it returns after the lease expires. After three returns
   the job is failed and the message retired (or dead-lettered).

Every step is recoverable because the message is tiny, the state is durable, and the
worker assumes it may see the same job twice.

## Trade-offs to keep in mind

- At-least-once means idempotency is the worker's job (`state.json` check), not free.
- Progress is polled from storage, so SSE latency is ~1–2 s higher than in-memory.
- Cross-run history and ownership that PostgreSQL provided are switched off, which is
  why auth must stay disabled in S3-only mode (see `SQS_WORKER_MIGRATION.md` §2).

---

## Glossary of terms used in this implementation

| Term | Meaning | Where it shows up |
|---|---|---|
| **Message queue** | A buffer that holds units of work until a consumer takes them. Decouples the sender from the receiver in time and in process. | SQS queue `ka11y-audit-jobs` |
| **Amazon SQS** | AWS's managed message queue. Standard queues scale without limit and deliver at-least-once; FIFO queues add ordering and exactly-once. We use a standard queue. | `ka11y/queue/sqs.py` |
| **Producer** | The side that puts messages on the queue. | API `_admit_run` → `send_message` |
| **Consumer** | The side that takes messages off the queue and does the work. | `Worker.run` |
| **Message body** | The JSON payload of a message. Ours is a serialized `AuditJobMessage`. | `ka11y/queue/messages.py` |
| **Receipt handle** | A per-delivery token SQS returns on receive. Needed to delete the message or change its visibility. Differs on every redelivery of the same message. | `ReceivedMessage.receipt_handle` |
| **Short polling** | `ReceiveMessage` returns immediately, possibly empty. Cheap to call, expensive in aggregate. | Not used |
| **Long polling** | `ReceiveMessage` waits up to `WaitTimeSeconds` (max 20 s) for a message before returning. Fewer empty responses, lower latency and cost. | `SQS_WAIT_TIME_SECONDS`, `ReceiveMessageWaitTimeSeconds=20` on the queue |
| **Visibility timeout** | After a receive, the message is hidden from other consumers for this many seconds. If it is not deleted in time it becomes visible again. This is the crash-recovery mechanism. | `SQS_VISIBILITY_TIMEOUT` (300 s) |
| **ChangeMessageVisibility** | API call that resets the visibility timeout for an in-flight message. Used to extend a lease for long work. | `SQSClient.change_visibility` |
| **Heartbeat** | A periodic task that renews the lease (calls ChangeMessageVisibility) while an audit is still running. Stops automatically if the process dies. | `Worker._heartbeat`, every 150 s |
| **Lease** | General term for "I hold this work item for a limited time". The visibility timeout plus heartbeat implement a renewable lease. | §6 above |
| **Acknowledge (ack)** | Telling the queue the work is done so the message is removed. In SQS this is `DeleteMessage`. | `SQSClient.delete_message` |
| **Ack after persist** | Rule: write the result durably first, then delete the message. Guarantees a crash can only cause a duplicate, never a lost job. | `_settle_outcome` |
| **At-least-once delivery** | The queue guarantees each message is delivered one or more times. Duplicates are possible and must be tolerated. | Standard SQS semantics |
| **Exactly-once** | Each message processed once. SQS FIFO queues approximate this; standard queues do not. We get the same effect by idempotency instead. | Not used |
| **Idempotency** | Processing the same message twice produces the same result as processing it once. Ours is enforced by checking `state.json` for a terminal status. | `Worker._handle` |
| **Idempotency key** | The value used to detect a repeat. Ours is the job id, looked up in `state.json`. | `jobstate.get_state` |
| **ApproximateReceiveCount** | SQS attribute counting how many times a message has been delivered. We use it as the attempt number. | `ReceivedMessage.receive_count` |
| **Retry** | Re-running a failed job. Happens implicitly: a crashed worker does not delete the message, so SQS redelivers it. | `_settle_crash` |
| **Max attempts** | Cap on retries. After this many deliveries the worker fails the job and deletes the message. | `WORKER_MAX_ATTEMPTS` (3) |
| **Dead-letter queue (DLQ)** | A second queue that receives messages the main queue has delivered more than `maxReceiveCount` times. A holding area for inspection, not automatic retry. | `ka11y-audit-jobs-dlq` |
| **Redrive policy** | Queue attribute linking the main queue to its DLQ and setting `maxReceiveCount`. | `localstack/init-sqs.sh` |
| **Poison message** | A message that can never be processed (malformed body, unknown version). Retrying is pointless, so it is logged and deleted immediately. | `Worker._handle` parse failure |
| **Message retention** | How long an undelivered message stays in the queue before SQS discards it. | 4 days main queue, 14 days DLQ |
| **Claim check pattern** | Send a small reference through the queue and keep the large data elsewhere. | Message has job id; reports live in S3 |
| **Schema version** | A field in the message that lets consumers reject formats they do not understand. | `AuditJobMessage.version` |
| **Object storage** | Flat key/value blob store (S3, or a local directory in dev). No transactions, no queries, just put/get/list by key. Our run store. | `ka11y/storage/`, `KA11Y_S3_BUCKET` |
| **System of record** | The single place the truth lives. For a job it is `state.json`, not any in-memory cache. | `ka11y/storage/jobstate.py` |
| **Marker file** | A file whose existence is the signal; its contents do not matter. | `cancel.json` |
| **Terminal status** | A status that will never change again: `completed`, `failed`, `cancelled`. | `TERMINAL_STATUSES` |
| **Semaphore** | A counter that allows at most N holders at once. Used to bound how many audits run in parallel. | `asyncio.Semaphore` in `ConcurrencyLimiter` |
| **Bounded concurrency** | Never running more than N jobs in a process, so memory and Chromium instances stay predictable. | `WORKER_MAX_CONCURRENCY` (2) |
| **Admission control** | Deciding whether to take new work before taking it. We acquire a slot before calling ReceiveMessage. | `Worker.run` |
| **Backpressure** | When consumers are full they stop pulling, and work accumulates in the queue instead of in memory. Follows from admission control. | Queue depth grows, worker does not |
| **Broadcast sink** | A callback registered with the in-process event bus; receives every progress event. The worker uses one to mirror events to storage. | `store.add_broadcast_sink`, `jobstate.progress_sink` |
| **Throttling (writes)** | Coalescing frequent updates so storage sees at most one write per interval. | `PROGRESS_MIN_INTERVAL_S` (2 s) |
| **Server-Sent Events (SSE)** | One-way HTTP stream from server to browser. The API now feeds it by polling `state.json`. | `GET /combined/{id}/stream` |
| **Graceful shutdown / drain** | On SIGTERM stop taking new work and let in-flight work finish before exiting. | `WORKER_SHUTDOWN_TIMEOUT`, `stop_grace_period: 15m` |
| **SIGTERM / SIGINT** | Signals Docker and Ctrl-C send to ask a process to stop. The worker catches them to start the drain. | `Worker` signal handlers |
| **asyncio.to_thread** | Runs a blocking function on a thread pool so the event loop stays free. Used because boto3 is synchronous. | Every call in `sqs.py` |
| **LocalStack** | A local emulator of AWS services (SQS, S3, and more). Lets the full pipeline run on a laptop with no AWS account. | `docker-compose.yml` service `localstack` |
| **awslocal** | The AWS CLI wrapper pointed at LocalStack. Used in the init script to create queues and the bucket. | `localstack/init-sqs.sh` |
| **Endpoint URL** | Override that points boto3 at LocalStack instead of real AWS. The only thing that differs between local and prod. | `KA11Y_SQS_ENDPOINT_URL` |
| **Local parity** | Running the same code and queue configuration locally as in production so there is no "works on my machine" gap. | §14 above |
| **Horizontal scaling** | Adding more worker containers rather than a bigger one. Safe because workers share nothing except the queue and storage. | Any number of `worker` replicas |
| **Queue depth** | Number of messages waiting. The natural autoscaling signal for workers. | `SQSClient.approximate_counts` |
