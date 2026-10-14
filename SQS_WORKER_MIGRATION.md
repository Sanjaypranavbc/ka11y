# SQS worker migration + S3-only run store

Branch `aws-arch`, 2026-10-09. Commits:

| Commit | What |
|---|---|
| `ff81b7b` | `ka11y/queue`: `AuditJobMessage` + async SQS client |
| `5c05214` | `ka11y/storage/jobstate.py`: job state in object storage (`state.json`) + broadcast sinks |
| `d2ef5be` | `ka11y/worker`: SQS audit worker with Semaphore-bounded concurrency |
| `5487891` | API submit publishes to SQS; PostgreSQL switched off, object storage is the run store |
| `37e6e73` | LocalStack + worker compose services, queue env, README; PG dispatcher deleted |

This file covers three things: (1) the old in-process worker versus the new SQS worker, with the code that changed; (2) what was done to the database layer and what the system does when there is no database; (3) how a manual verdict on a *needs review* item moves it into *passes* or *fails* and updates the counts.

---

## 1. Previous worker vs implemented worker

### 1.1 Architecture

**Before** (`ab0fd20` and earlier) — one process did everything:

```
browser ──POST /combined──▶ FastAPI (uvicorn)
                              ├─ _jobs hot cache (in-memory dict)
                              ├─ repo.create_run()  → audit_jobs row, status='queued'   (PostgreSQL)
                              ├─ dispatcher.notify()
                              └─ dispatcher task (same process)
                                   ├─ repo.next_queued(free)  → claims rows, status='running'
                                   ├─ asyncio.create_task(_run_tracked) ×  KA11Y_MAX_CONCURRENT_JOBS (3 in compose, 4 default)
                                   └─ runner._run_job_body → repo.mark_completed / mark_failed + report rows
```

Polling, SSE, exports and the audits themselves all shared one event loop and one Chromium pool. A restart requeued every `running` row on boot (`repo.requeue_running`).

**After** — the API only admits jobs; a separate worker process runs them:

```
browser ──POST /combined──▶ FastAPI (API container)
                              ├─ jobstate.put_state()   → anonymous/jobs/{id}/state.json  status='queued'   (S3 / artifact dir)
                              └─ SQS send_message(AuditJobMessage)                                             (SQS)

worker container  (python -m ka11y.worker.worker)
   loop: limiter.acquire()  →  receive_messages(max=free slots)  →  one task per message
   task: parse → read state.json (idempotency / cancel / attempt cap)
         → state.json 'running' → heartbeat task → runner._run_job_body (unchanged)
         → progress sink mirrors every SSE event into state.json
         → final state.json → delete_message        (crash: leave for redelivery)

API reads:  GET /combined/{id}        ← state.json (+ reports/report.json when completed)
            GET /combined/{id}/stream ← polls state.json every 1 s, emits job_state / job_complete …
            GET /combined/{id}/export ← reports/report.json + reviews.json
```

### 1.2 Side-by-side differences

| Concern | Previous (in-process dispatcher) | Implemented (SQS worker) |
|---|---|---|
| Queue | `audit_jobs` rows in PostgreSQL, `status='queued'` | Amazon SQS standard queue `ka11y-audit-jobs` (LocalStack locally) |
| Job record | `audit_jobs` row + `_jobs` hot cache in the API process | `state.json` in object storage; hot cache exists only inside the worker while a job runs |
| Who runs audits | The API process (dispatcher task) | The worker process; the API never runs an audit |
| Concurrency cap | `_MAX_CONCURRENT_JOBS` (`KA11Y_MAX_CONCURRENT_JOBS`, 3 in compose) checked by the dispatcher; a second semaphore in `runner._run_job` for the fallback path | `ConcurrencyLimiter` (`asyncio.Semaphore`, `WORKER_MAX_CONCURRENCY`, default 2). The runner's semaphore is bypassed: the worker calls `_run_job_body` directly |
| Admission order | Slot check **after** claiming the DB row | Slot acquired **before** `ReceiveMessage`; at most *free slots* messages are pulled |
| Crash of the runner | `_mark_crashed` → row `failed`, `error_stage='dispatch'` | Message left on the queue → SQS redelivers after the visibility timeout; after `WORKER_MAX_ATTEMPTS` (3) the job is failed and the message deleted |
| API restart | `repo.requeue_running()` on boot | Nothing to do: the queue holds un-acked messages, the worker holds the run |
| Worker restart mid-audit | n/a (same process as API) | Visibility timeout lapses → redelivery → `state.json` says `running` (not terminal) → the audit re-runs on the next attempt |
| Long audits | Nothing to extend | Heartbeat task calls `ChangeMessageVisibility` every `SQS_VISIBILITY_TIMEOUT/2` s |
| Duplicate work | Impossible (one process) | SQS is at-least-once → worker checks `state.json`; terminal status ⇒ delete and skip |
| Cancel | Route wrote `cancelled` to the row; runner polled `repo.is_cancelled` | Route writes `cancel.json` marker (and `state.json → cancelled` if still queued); runner polls `jobstate.is_cancel_requested` at its checkpoints |
| Progress / SSE | In-memory subscribers in the API process | Worker mirrors every broadcast into `state.json` (throttled to one write per 2 s for noisy events); API `/stream` polls it |
| Submit failure | DB insert failed → 503, no job id | `state.json` write failed or SQS publish failed → 503, no job id; if publish failed after the state was written, state is set to `failed` with `error_stage='queue'` |
| Poison message | Row with bad params → `failed`, `error_id='bad_params'` | Body that is not an `AuditJobMessage` → logged at ERROR and deleted (never cycles to the DLQ) |
| Dead letters | n/a | `ka11y-audit-jobs-dlq`, `RedrivePolicy.maxReceiveCount=3` (same as `WORKER_MAX_ATTEMPTS`) |
| Shutdown | uvicorn stop cancelled tasks | SIGTERM/SIGINT → stop polling, drain in-flight audits (`WORKER_SHUTDOWN_TIMEOUT`, default job timeout + 60 s); compose `stop_grace_period: 15m` |

### 1.3 Code changes with before / after

#### Submit path — `ka11y/api/v1/combined/routes.py::_admit_run`

Before:

```python
_jobs[job_id] = {"job_id": job_id, "status": "queued", ...}          # hot cache in the API
owner = user if isinstance(user, CurrentUser) else None
try:
    await enqueue(job_id, payload, user=owner)                        # dispatcher.enqueue → repo.create_run + notify()
except Exception:
    _jobs.pop(job_id, None)
    raise HTTPException(status_code=503, detail="Audit queue is unavailable. Please try again.")
```

After:

```python
state = jobstate.new_state(job_id, url=url, lang=payload.lang,
                           params=payload.model_dump(mode="json"), submitted_at=now, rerun_of=rerun_of)
if not await jobstate.put_state(job_id, state):                       # state.json IS the job
    raise HTTPException(status_code=503, detail="Audit queue is unavailable. Please try again.")

# PostgreSQL mirror (ownership, history) — switched off: commented out, see §2

try:
    message_id = await _publish_job(
        job_id, AuditJobMessage.for_request(job_id, payload, created_at=now, rerun_of=rerun_of)
    )
except Exception:
    await jobstate.update_state(job_id, status="failed", completed_at=..., error="Audit could not be queued.",
                                error_stage="queue", error_id=uuid.uuid4().hex)
    raise HTTPException(status_code=503, detail="Audit queue is unavailable. Please try again.")
```

`_publish_job` is a one-line seam (`get_client().send_message(message)`) so tests patch it instead of `enqueue`.

#### The message — `ka11y/queue/messages.py`

```python
class AuditJobMessage(BaseModel):
    version: int = MESSAGE_VERSION          # worker refuses other versions
    job_id: str
    url: str
    payload: Dict[str, Any]                 # CombinedRequest.model_dump(mode="json")
    created_at: str
    attempt: int = 1                        # publish attempt; delivery count comes from ApproximateReceiveCount
    rerun_of: Optional[str] = None
```

A few hundred bytes. Progress, reports and screenshots never go through the queue; they are keyed by `job_id` in object storage.

#### Queue loop — old `dispatcher._drain` vs new `Worker.run`

Before (`dispatcher.py`, deleted in `37e6e73`):

```python
async def _drain() -> None:
    free = _MAX_CONCURRENT_JOBS - len(_inflight)
    if free <= 0:
        return
    rows = await repo.next_queued(free)                    # claim rows first …
    for row in rows:
        await repo.update_run(run_id, status="running")
        task = asyncio.create_task(_run_tracked(run_id, payload, None))   # … then run
        _inflight.add(task)
```

After (`ka11y/worker/worker.py`):

```python
while not self._stopping.is_set():
    if not await self._acquire_or_stop():                 # block for ONE slot (or stop)
        break
    extra = await self.limiter.acquire_available(MAX_RECEIVE_BATCH - 1)   # never blocks
    held = 1 + extra
    messages = await self.sqs.receive_messages(max_messages=held, wait_time=self.poll_wait)
    for _ in range(held - len(messages)):
        self.limiter.release()                            # give back slots that got no message
    for received in messages:
        task = asyncio.create_task(self._run_message(received))   # releases its slot in finally
```

Why the order matters: a message received without a slot sits in memory while its visibility timeout counts down, then SQS hands it to another consumer and the audit runs twice.

#### Per-message handling — `Worker._handle`

```python
msg = received.parse(); request = msg.request()          # poison → delete, return
state = await jobstate.get_state(job_id) or jobstate.new_state(...)   # missing state is rebuilt from the message

if state["status"] in TERMINAL_STATUSES:                 # completed / failed / cancelled
    await self._delete(received); return                 # duplicate delivery
if await jobstate.is_cancel_requested(job_id):
    state.update(status="cancelled", ...); await self._write_final(...); await self._delete(received); return
if attempt > self.max_attempts:
    state.update(status="failed", error_id="max_attempts_exceeded", ...); await self._write_final(...); await self._delete(received); return

_jobs[job_id] = hot = jobstate.to_hot_entry(state)        # the runner still works on the hot cache
hot.update(status="running", attempt=attempt, worker_pid=os.getpid(), run_started_at=_now())
await jobstate.put_state(job_id, jobstate.snapshot(hot))

heartbeat = asyncio.create_task(self._heartbeat(received, job_id))
try:
    await self._run_job(job_id, request, None)           # runner._run_job_body — unchanged
except Exception:
    crashed = True
finally:
    heartbeat.cancel()

final = jobstate.snapshot(_jobs.get(job_id) or hot)
if crashed:  await self._settle_crash(received, job_id, final, attempt)    # leave message unless last attempt
else:        await self._settle_outcome(received, job_id, final, attempt)  # write final state, THEN delete
```

#### Heartbeat — `Worker._heartbeat`

```python
visibility = self.sqs.cfg.visibility_timeout          # 300 s by default
while True:
    await asyncio.sleep(self.heartbeat_interval)      # visibility / 2 = 150 s
    await self.sqs.change_visibility(received.receipt_handle, visibility)
```

So `SQS_VISIBILITY_TIMEOUT` only needs to cover the gap between two heartbeats, not a whole audit.

#### Delete only after success — `Worker._settle_outcome`

```python
if await self._write_final(job_id, final):     # 3 attempts at writing state.json
    await self._delete(received, job_id=job_id)
else:
    # state.json could not be written: leave the message so a redelivery re-runs the audit
    logger.error("... final state could not be written; message left on the queue")
```

#### Graceful shutdown — `worker._amain`

```python
for sig in (signal.SIGTERM, signal.SIGINT):
    loop.add_signal_handler(sig, worker.request_stop)   # sets the stop event; poll loop exits
...
# Worker.run → finally: asyncio.wait(self._tasks, timeout=WORKER_SHUTDOWN_TIMEOUT)
```

#### Progress mirroring — `ka11y/api/v1/combined/store.py` + `jobstate.progress_sink`

`_broadcast()` (the SSE fan-out the runner already called) now also invokes registered sinks. The worker registers `jobstate.progress_sink`, which writes `snapshot(_jobs[job_id])` to `state.json` on every stage boundary / terminal event and at most every 2 s for `stage_progress`. The API's `/stream` endpoint polls that file and turns changes into the same SSE events the UI already understood.

#### Runner — `ka11y/api/v1/combined/runner.py`

`_run_job_body` is unchanged in what it audits. What changed around it:

- `_is_cancelled` reads only the `cancel.json` marker (the `repo.is_cancelled` DB check is commented out).
- `repo.mark_running / save_report / save_findings / save_pages / mark_completed / mark_failed / insert_event` are commented out. The report is still uploaded by `uploader.upload_job_artifacts` (`reports/report.json`, `findings.csv`, `report.pdf`) and the final status by the worker's `state.json` write.
- `_run_job` (the semaphore wrapper) remains only for the in-process path (rule tester, tests).

#### Compose / env

- `localstack` service, `localstack/init-sqs.sh` creates the queue + DLQ (`maxReceiveCount=3`).
- `worker` service: same image as `python`, `command: python -m ka11y.worker.worker`, `WORKER_MAX_CONCURRENCY=2`, `stop_grace_period: 15m`, shares `./output/*` with the API.
- `SQS_QUEUE_URL`, `SQS_ENDPOINT_URL`, `AWS_REGION`, `SQS_VISIBILITY_TIMEOUT` on both services; `.env.example` documents them.

---

## 2. Database changes

### 2.1 What was commented out (not deleted)

Every PostgreSQL call outside `ka11y/db`, `ka11y/store`, `ka11y/auth` and `admin.py` is commented out and marked `PostgreSQL: switched off`. The modules, models and Alembic migrations are untouched so the layer can be restored by uncommenting.

| File | What was switched off | Replaced by |
|---|---|---|
| `main.py` lifespan | `init_postgres()`, `init_store()` (row writer), PG queue dispatcher, retention sweep, their shutdowns | one log line; SQS worker; S3 lifecycle rule for retention |
| `worker/worker.py` | optional `init_postgres()` mirror | — |
| `combined/routes.py` | `repo.create_run` mirror on submit; `repo.get_run` fallbacks in rerun / status / stream / timings / cancel / reviews; `repo.get_reviews`, `repo.set_finding_review`; `repo.list_runs` history; `repo.mark_cancelled`; `_job_from_db` | `jobstate.get_state`, `jobstate.get_report`, `jobstate.get_reviews` / `set_review`, `jobstate.list_states`, `jobstate.request_cancel` |
| `combined/runner.py` | `repo.is_cancelled`, `mark_running`, `save_report`, `save_findings`, `save_pages`, `mark_completed`, `mark_failed`, `insert_event` | `cancel.json`, `state.json`, `reports/report.json` |
| `combined/dispatcher.py` | whole module (PG queue) | deleted in `37e6e73` |
| `store/assets.py::put_asset` | `audit_assets` INSERT … RETURNING id, `_upload_if_needed` | direct upload; `AssetRef.object_key`; URL `/api/v1/assets/by-key/{key}` |
| `api/v1/assets.py` | — (`/assets/{id}` kept, answers 404 without a DB) | new `GET /assets/by-key/{key:path}` |
| `api/v1/audits.py` | `run_repo.list_history`, `get_owner`, `list_reports`, `query_assets_with_keys`, `get_report_file` | `jobstate.list_states`, `_assert_can_view` always passes, `jobstate.list_artifacts`, download by file name |
| `storage/keys.py` | `repo.get_owner` lookup | every job is `anonymous/jobs/{job_id}/` |
| `storage/uploader.py` | `repo.add_report` (`reports` row per file) | the `reports/` key listing |
| `utils/run_timing.py`, `stage_timing.py`, `crawler_timing.py` | `repo.insert_event` / `insert_timing` mirrors | log files only (`KA11Y_TELEMETRY_FILES`) |
| `utils/report_pdf.py` | `store.assets.get_asset` for `/api/v1/assets/{id}` images | `by-key` images fetched from the store into a temp file |
| `docker-compose.yml` | `postgres` service, python `depends_on: postgres`, `KA11Y_DB_AUTO_MIGRATE` | — |
| `ka11y-python/.env` | `DATABASE_URL` (commented) | — |

### 2.2 What object storage holds now (per job)

```
anonymous/jobs/{job_id}/
  state.json           status, url, submitted_at, run_started_at, completed_at, current_stage,
                       stages[], warnings[], plan, params, attempt, worker_pid, rerun_of,
                       error / error_id / error_code / error_stage, result_summary, has_report
  cancel.json          present ⇒ cancellation requested (written by the API)
  reviews.json         {finding_id: {status, note, reviewer, wcag_sc, page_url, updated_at}}
  reports/report.json  the full report (every finding)        ─┐ uploaded by the runner
  reports/findings.csv                                         │ on completion
  reports/report.pdf   (KA11Y_ARTIFACT_PDF=1)                  ─┘
  assets/{images|screenshots|html|media}/…   content-addressed (sha256) uploads
  raw/{ocr|steps|crawler}/…                  OCR reports, step logs
  crash/crash.json     traceback + context when the runner failed
```

Backend: S3 when `KA11Y_S3_BUCKET` is set, otherwise `KA11Y_ARTIFACT_DIR` (`./output/artifacts`, bind-mounted into both the API and the worker container).

### 2.3 What happens when there is no database

`DATABASE_URL` is ignored by the API and the worker (the code that read it is commented out), so "no database" is the only mode right now. Per feature:

| Feature | Behaviour without PostgreSQL |
|---|---|
| Submit / run / poll / SSE / export / cancel / rerun | Fully working on `state.json` + `reports/report.json` + SQS. |
| Manual verdicts | Fully working, stored in `reviews.json` (see §3). |
| Report images, HTML snapshots, OCR artifacts | Uploaded directly, served by `/api/v1/assets/by-key/{key}` (302 to a presigned S3 URL, or the bytes). The old `/api/v1/assets/{id}` answers 404. |
| History (`GET /combined/history`, `GET /audits/history`) | Built by listing `state.json` documents under the jobs root: one `ListObjects` + one `GET` per job, 16 in parallel, newest first, `url` substring / `status` filters. Fine for a few hundred jobs; for thousands an index object would be needed. |
| Job ownership | None. Every job is anonymous; `_assert_can_view` lets any caller see any job id. |
| Sign-in (OIDC / password) | Needs PostgreSQL for users and sessions, so it **cannot** be enabled. `KA11Y_AUTH_DISABLED=1` must stay set on both the python and ui services; everyone is the anonymous user. |
| Admin console (`/api/v1/admin/*`) | Requires a signed-in admin; with auth disabled nobody is an admin, so it is closed. Its endpoints would answer 503 (`_require_pg`) anyway. |
| Per-step timings (`/combined/{id}/timings`) | Computed from the stage timestamps in `state.json`. The fine-grained `stage_timings` table (per page/stage/rule) no longer exists; a job without `state.json` answers 404. |
| Retention | No sweep. Use an S3 lifecycle rule on the bucket prefix (or clean `./output/artifacts` by hand). |
| Telemetry (`run_events`, `stage_timings`) | Only the log files, when `KA11Y_TELEMETRY_FILES=1`. |
| Crash recovery after an API restart | Nothing needed: the queue and the worker own the run. |
| Tests | `pg_db`-backed tests skip. Two ownership tests are skipped with a reason. `tests/test_s3_only.py` covers the S3 paths. |

If `DATABASE_URL` is set anyway nothing changes: no engine is created, no migration runs, no row is written.

### 2.4 Bringing PostgreSQL back

1. Uncomment the `postgres` service and `depends_on` in `docker-compose.yml`, and `DATABASE_URL` in `ka11y-python/.env`.
2. Uncomment the blocks marked `PostgreSQL: switched off` in `main.py`, `worker/worker.py`, `combined/routes.py`, `combined/runner.py`, `store/assets.py`, `storage/keys.py`, `storage/uploader.py`, `api/v1/audits.py` and the timing utils. The `repo` import lines are commented next to each.
3. Decide whether the DB mirrors the object store (ownership + history, S3 stays the source of truth) or becomes the run store again. The dispatcher is gone; the SQS worker stays either way.

---

## 3. Manual verdicts: how needs review, pass and fail update

### 3.1 Where the automated status comes from

Every finding carries an immutable engine `status`: `fail`, `pass` or `needs_review`. `needs_review` items are the ones a human must adjudicate; `_stamp_finding_ids` gives each finding a deterministic `finding_id` (sha1 of wcag_sc + rule + page + selector + element identity) and sets `manual_review: true` on them. The report's `summary` holds the automated counts: `violations`, `needs_review`, `passes`, `score`.

### 3.2 Choosing a verdict

```
POST /api/v1/combined/{job_id}/findings/{finding_id}/review
{"status": "pass" | "violation" | "needs_review", "note": "...", "reviewer": "..."}
```

The route (`routes.review_finding`):

1. Loads the report: hot cache → `reports/report.json`. Finds the finding by `finding_id` in any bucket.
2. Guards: a finding whose engine status is `fail` or `pass` → **409** ("Only findings the engine marked needs_review can be given a manual verdict"). Unknown id → 404.
3. `reviewer` is the signed-in user's email or name; with auth disabled the request body's `reviewer` (or `"user"`) is used.
4. Writes `reviews.json` with `jobstate.set_review`:
   - `pass` or `violation` → upsert `{finding_id, status, note, reviewer, wcag_sc, page_url, updated_at}`
   - `needs_review` → remove the entry (re-opens the item)
5. Answers with `verdict_source`, `review_status`, `reviewed_by`, `reviewed_at`, `review_message` for that finding.

Before this change the same thing was an upsert into the `finding_reviews` table (`repo.set_finding_review`, unique on `(job_id, finding_id)`) plus an `audit_logs` row; the file replaces both.

### 3.3 How the overlay re-buckets findings — `report.apply_reviews`

Every read that returns findings (`GET /combined/{id}`, `/export`, the email) calls `_apply_reviews_to_job`, which loads `reviews.json` and runs `apply_reviews(result, reviews)`. It never rewrites the engine `status`; it partitions by **engine status + review overlay**:

```python
for f in violations + needs_review + passes:
    if f["status"] == "needs_review":
        rev = reviews.get(f["finding_id"])
        if rev and rev["status"] in ("pass", "violation"):
            f["review_status"]  = rev["status"]          # the human verdict
            f["review_note"]    = rev.get("note")
            f["reviewed"]       = True
            f["reviewed_by"]    = rev.get("reviewer")
            f["reviewed_at"]    = rev.get("updated_at")
            f["review_message"] = review_message(rev["status"], lang)   # "Reviewed by user and manually changed to Pass."
            f["verdict_source"] = "manual"
        else:
            drop every review_* field; f["verdict_source"] = "engine"
    else:
        f["verdict_source"] = "engine"

    rs = f.get("review_status")
    if f["status"] == "fail" or rs == "violation":   → violations
    elif f["status"] == "pass" or rs == "pass":      → passes
    else:                                            → needs_review
```

Then the counts are recomputed from the new arrays:

```python
summary["automated"]   = {violations, needs_review, passes, score}   # the engine baseline, kept once
summary["violations"]  = len(violations)       # effective
summary["needs_review"] = len(needs_review)
summary["passes"]      = len(passes)
summary["score"]       = 100 * passes / (passes + violations)        # needs_review never counts
summary["manual_review_required"] = len(needs_review)
summary["reviews"]     = {"reviewed": n, "pending": len(needs_review), "as_pass": …, "as_violation": …}
```

The same repartition runs on each entry of `report["pages"]` so per-page tables agree with the headline.

### 3.4 Worked example

Engine result: 3 fails, 2 needs review, 5 passes → `violations 3, needs_review 2, passes 5, score 62.5` (5 / 8).

| Action on finding R1 (needs_review) | violations | needs_review | passes | score | R1 fields |
|---|---|---|---|---|---|
| none | 3 | 2 | 5 | 62.5 | `verdict_source: engine`, `manual_review: true` |
| verdict `pass` | 3 | 1 | 6 | 66.7 | `review_status: pass`, `reviewed: true`, `review_message: "Reviewed by user and manually changed to Pass."` |
| verdict `violation` (overwrites) | 4 | 1 | 5 | 55.6 | `review_status: violation`, message "… changed to Fail." (「不合格」 in a Japanese report) |
| verdict `needs_review` (re-open) | 3 | 2 | 5 | 62.5 | review fields removed, `verdict_source: engine` |

`summary.automated` stays `{3, 2, 5, 62.5}` throughout, so the UI can show "engine said X, after review Y".

### 3.5 Properties worth knowing

- **Idempotent.** The partition is derived from `status` + `review_status` each time, so applying the overlay twice to the same (cached) object gives the same arrays and counts; a cleared verdict is re-partitioned back into `needs_review` on the next read.
- **Engine verdicts are authoritative.** Only `needs_review` items can be adjudicated (409 otherwise); a reviewed item still shows `status: needs_review` so nothing pretends the engine passed it.
- **Exports carry it.** JSON/CSV/HTML/PDF exports go through `_full_report`, which applies the overlay, so a reviewed item appears under its new bucket with `review_status`, `reviewed_by`, `reviewed_at`, `review_note`, `review_message`.
- **Stored once per finding.** `reviews.json` is read-modify-write on one small object; reviewers are people, so concurrent verdicts on the same run do not race in practice. If storage is off or the write fails the route answers 503 and nothing changes.
- **UI.** `ka11y-ui/src/lib/reviewApi.ts` posts the verdict and `wcagAudit.ts` renders `verdict_source: "manual"` with the `review_message` as the audit-trail line; the counters on the dashboard are `summary.violations / needs_review / passes` and therefore move with the verdict.

---

## 4. Running and verifying

```bash
docker compose up --build            # localstack (queues created by localstack/init-sqs.sh) + node + python + worker + ui
docker compose logs -f worker        # "[worker] started pid=… max_concurrency=2 max_attempts=3 queue=…"
curl -X POST localhost:8000/api/v1/combined -H 'content-type: application/json' -d '{"url":"https://example.com"}'
# → 202 {"job_id": …}; poll GET /api/v1/combined/{job_id} or open the dashboard
ls output/artifacts/anonymous/jobs/<job_id>/   # state.json, reports/, assets/ once the worker finishes
```

Tests: `cd ka11y-python && poetry run pytest -q` → 720 passed, 51 skipped (PostgreSQL-backed and ownership tests). Queue and worker tests: `tests/test_queue_sqs.py` (moto), `tests/test_worker.py`, `tests/test_job_concurrency.py`; S3-only paths: `tests/test_s3_only.py`.

Known gaps:

- The compose stack has not yet been run end-to-end after these commits.
- `ka11y-python/.env` sets `S3_BUCKET_NAME`; the code reads `KA11Y_S3_BUCKET`. Until renamed, both containers use `./output/artifacts`, not S3.
- History listing scales linearly with the number of jobs (one GET each).
- No retention without PostgreSQL; add an S3 lifecycle rule.
