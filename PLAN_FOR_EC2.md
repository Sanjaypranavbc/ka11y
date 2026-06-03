# a11y — Production EC2 Plan + Progress Bar Redesign

_Scope locked with user (2026-04-24): **production on a t3.large (2 vCPU / 8 GB RAM)**, durable jobs required, full traceback in UI, SSE with replay, Tailwind or MUI frontend._

This document is the single source of truth for the EC2 hardening + progress-bar work. Fixes already landed are listed at the top so future-me doesn't redo them.

---

## 0. Fixes already landed (2026-04-24)

| File | Change |
|---|---|
| `a11y-python/a11y/api/v1/combined/runner.py:89` | `(el.get("image_src") or "")` — killed `None.get()` crash when `element: None` |
| `a11y-python/a11y/api/v1/combined/runner.py:325` | Rich failure log: type, stage, file:line:fn, full traceback; same surfaced via `_jobs[...]` and `job_failed` SSE |
| `a11y-python/a11y/text_detector/text_detector.py:593, 645` | `(det.color_info.get("foreground") or {})` — same None-vs-missing trap |
| `a11y-python/a11y/crawler/rendered_layout_crawler.py:469` | `el_data.get("rect") or {}` |
| `a11y-python/a11y/accessibility/rendered/snapshot_collector.py:183` | `item.get("rect") or {}` |
| `a11y-python/Dockerfile` | `ARG INSTALL_JAPANESE=1` installs `-E japanese` + `ja_core_news_lg`; pre-downloads NLTK corpora; pre-downloads faster-whisper `base` (int8/cpu); `NLTK_DATA=/usr/share/nltk_data` baked in |
| `docker-compose.yml` | passes `INSTALL_JAPANESE` build arg to the python service |

**Impact**: the combined audit job that failed mid-post-processing now completes; EC2 cold start no longer stalls on NLTK/HF/spaCy downloads.

---

## 1. t3.large sizing (2 vCPU / 8 GB RAM) — tight, doable with knobs

### Hard constraints on t3.large
- 8 GB RAM. Torch CPU wheels alone resident = ~800 MB. Playwright Chromium = ~400 MB per tab. faster-whisper `base` int8 = ~250 MB loaded. spaCy `ja_core_news_lg` = ~1.2 GB loaded. Simultaneous OCR + contrast + Playwright easily hits 4–5 GB working set, so **one concurrent job at a time** is the ceiling.
- 2 vCPU. CPU-bound stages (OCR, contrast, whisper) saturate fast; axe-core Node + 7 python stages in parallel will trash caches. We already use `asyncio.to_thread` — good — but need a concurrency semaphore.

### Mandatory changes for t3.large

1. **Serialize jobs.** Add a single asyncio semaphore around `_run_job` with `limit=1`. Queue additional jobs.
2. **Lazy-load spaCy `ja_core_news_lg`** — only instantiate when the audit `lang` actually requires it. Today it's not clear if we load it eagerly; audit the import paths.
3. **Whisper model size** default → keep `base`, but expose `WHISPER_MODEL_SIZE=tiny` as a compose override for very constrained boxes.
4. **Chromium flags.** `--disable-dev-shm-usage --disable-gpu --no-sandbox` (we use seccomp:unconfined already). Close contexts explicitly after each stage — check we're not leaking on exceptions.
5. **Swap file.** EC2 default AMI has no swap. Add 4 GB swap on the host via user-data — cheap insurance against OOM spikes during OCR.
6. **Docker memory limit.** `mem_limit: 6g` on the `python` service so it can't swallow node+frontend.
7. **OCR image budget** — already have `select_ocr_candidate_paths` with a limit. Tune the default down on t3.large (e.g. `MAX_OCR_IMAGES_PER_RUN=60`).

### Instance storage

- Root EBS: **40 GB gp3** minimum. Image alone is ~5 GB with Japanese + whisper + Playwright + torch.
- Add a nightly cron to purge `./output/crawled_images/*` older than 48h. Bind-mounted growth is the top silent failure.

### Verdict
t3.large works for **single-tenant demo-quality production**. For real concurrent load, move to t3.xlarge (16 GB) or split Whisper/OCR onto a worker container. Flag this when usage grows.

---

## 2. Latent bugs still to fix (non-blocking, low risk today)

Ordered by blast radius.

| # | File | Risk | Fix |
|---|---|---|---|
| 1 | `a11y/crawler/crawler.py:194, 375, 376` | CONFIG keys may be missing/None | `(CONFIG.get("crawler") or {}).get(...)` — YAML loader returns `{}` today but one PR away from regressing |
| 2 | `a11y/crawler/context_factory.py:11` | same | same idiom |
| 3 | `a11y/i18n/loader.py:67, 74` | locale overrides | guard |
| 4 | `a11y/api/v1/combined/routes.py:338` `current.get("result", {})` | when job is running/failed, `result` may be absent or `None` | `current.get("result") or {}` |
| 5 | Unchecked `.strip()` on possibly-None `record.get(...)` throughout converters | frontend shows empty reasons | add a helper `_s(x) = (x or "").strip()` |

Each is a one-line change. Bundle into a single "defensive-None cleanup" PR before the progress-bar work so the progress SSE never dies mid-stream from an unrelated converter crash.

---

## 3. Durable job store (replaces in-memory `_jobs`)

**Current**: `a11y/api/v1/combined/store.py` → module-global `_jobs: dict`. Lost on restart. Blocks horizontal scale.

**Requirement from user**: "I don't want audit lost; make the python container perform better." Interpreted as: job state must survive a container restart AND restart must not re-execute an in-flight job blindly.

### Recommendation: SQLite + write-ahead log, not Redis

Reasons for SQLite on t3.large:
- One process, one container, single writer — SQLite is a good fit.
- Zero ops: no Redis container, no port, no eviction policy.
- Durable on the existing `./output/logs` or a new `./output/state` bind mount.
- Ships with Python stdlib; no new dependency.

Switch to Redis later when we scale to multiple python containers behind an ALB.

### Schema (minimal)

```sql
CREATE TABLE jobs (
  job_id       TEXT PRIMARY KEY,
  status       TEXT NOT NULL,           -- queued | running | completed | failed
  created_at   TEXT NOT NULL,
  completed_at TEXT,
  url          TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  result_json  TEXT,                    -- final report
  error_json   TEXT,                    -- {type, msg, stage, location, traceback}
  current_stage TEXT
);

CREATE TABLE stage_events (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id    TEXT NOT NULL,
  seq       INTEGER NOT NULL,           -- monotonic per-job, used as SSE Last-Event-ID
  ts        TEXT NOT NULL,
  event     TEXT NOT NULL,              -- job_plan | stage_start | stage_progress | stage_complete | stage_error | job_complete | job_failed
  payload_json TEXT NOT NULL,
  UNIQUE(job_id, seq)
);
CREATE INDEX idx_stage_events_job_seq ON stage_events(job_id, seq);
```

### Crash-recovery policy
On startup, mark any `status='running'` rows as `failed` with `error_json = {type:"ContainerRestart", ...}` and broadcast a synthetic `job_failed` event. This is honest: a half-done audit is not resumable mid-stage in our architecture (too much state is in Playwright/Python RAM).

Rationale: resuming mid-stage would require checkpointing every auditor, which is not worth it. Users retry; jobs are cheap.

### Migration
Write a `store.py` that adapts the existing `_jobs` dict API to SQLite. No call-site changes elsewhere except `_broadcast` → also INSERT into `stage_events`.

---

## 4. Progress bar — end-to-end design

### 4.1 Backend event contract (additive; no breaking changes)

New event schema sent over SSE at `GET /api/v1/combined/{job_id}/events`:

```
# fired once at job start, before any stage_start
event: job_plan
id: 1
data: {"job_id":"...", "stages":[
  {"key":"axe_core","label":"axe-core (Node)","weight":1},
  {"key":"image_audit","label":"Images & contrast (OCR)","weight":5},
  ...
],"total":9,"started_at":"..."}

# per stage (unchanged payloads, plus index/total/weight)
event: stage_start
id: 2
data: {"job_id":"...","stage":"image_audit","index":1,"total":9}

# NEW — optional, emitted by stages that can self-report
event: stage_progress
id: 3
data: {"job_id":"...","stage":"image_audit","phase":"crawl","current":17,"total":38}

event: stage_complete
id: 4
data: {"job_id":"...","stage":"image_audit","index":1,"total":9,"findings":27,"duration_ms":42130}

event: stage_error
id: 5
data: {"job_id":"...","stage":"image_audit","error":"...","index":1,"total":9}

# terminal
event: job_complete
data: {"job_id":"...","summary":{...}}

event: job_failed
data: {"job_id":"...","error":"NoneType: ...","stage":"post_processing","location":"runner.py:245","traceback":"..."}
```

### 4.2 Percent-complete formula (the important detail)

Naive "completed_stages / total" is lying to the user — image_audit is 20× slower than target_size.

Use weights:

```
overall_pct = sum(weight[s] for s in completed_stages)
            + weight[current_stage] * (current/total_in_stage)
           ────────────────────────────────────────────────
                     sum(weight[s] for s in plan.stages)
```

Weights (initial calibration from existing timings — tune later):

| stage | weight |
|---|---|
| axe_core | 1 |
| image_audit | 5 |
| form_audit | 1 |
| pipeline (2.5.3/2.5.8) | 2 |
| pause_stop_hide | 1 |
| text_spacing | 1 |
| rendered_layout_audit | 3 |
| media_audit | 2 |
| sensory_audit | 1 |

Store these in `combined/constants.py` so backend and frontend can't drift — frontend reads them from `job_plan.stages[].weight`.

### 4.3 Where to emit `stage_progress`

High value (has a natural loop count):
- `_stage_image_audit` — crawler loop (`phase:"crawl"`, current = saved images, total = candidate links) and OCR loop (`phase:"ocr"`).
- `_stage_rendered_layout_audit` — per discovered_url iteration.
- `_stage_media_audit` — per media element (whisper is the slow part).

Low/no value (too fast to matter): form_audit, target_size, sensory_audit. Skip.

Implementation pattern: pass an async callback into crawler/auditor inner loops:

```python
async def _progress(current, total, *, phase=None):
    await _broadcast(job_id, "stage_progress",
                     {"stage": "image_audit", "phase": phase,
                      "current": current, "total": total})
```

Throttle to ≥ 200ms between events (counter on last-emit timestamp) so we don't SSE-spam the client.

### 4.4 Replay buffer + reconnect

On SSE connect, the HTTP request may include:

```
GET /api/v1/combined/{job_id}/events?last_event_id=3
```

Or the browser's native `EventSource` automatically sends `Last-Event-ID: 3` on reconnect. Backend behavior:

1. Open subscriber queue as today.
2. Before serving live events, `SELECT * FROM stage_events WHERE job_id=? AND seq > ? ORDER BY seq` — stream the backlog.
3. Then stream live.

Browser `EventSource` handles this natively thanks to the `id:` line in the SSE frames above. No frontend reconnect logic needed beyond `new EventSource(url)`.

### 4.5 Heartbeats

Every 15s on each open SSE stream, write `: keepalive\n\n`. Defeats:
- nginx/ALB 60s idle close
- browser `EventSource` retry storm
- Cloudflare-like proxies if we ever put one in front

### 4.6 Frontend component (`<AuditProgress />`)

Stack: **MUI** (user preference, and shadcn isn't worth pulling in if MUI is already there).

```tsx
// apps/web/src/components/AuditProgress.tsx
interface Props { jobId: string; onDone?: (report: CombinedReport) => void; }

function AuditProgress({ jobId, onDone }: Props) {
  const [plan, setPlan] = useState<JobPlan | null>(null);
  const [completed, setCompleted] = useState<Record<string, StageComplete>>({});
  const [current, setCurrent] = useState<StageProgress | null>(null);
  const [error, setError] = useState<JobFailure | null>(null);

  useEffect(() => {
    const es = new EventSource(`/api/v1/combined/${jobId}/events`);
    es.addEventListener("job_plan", e => setPlan(JSON.parse(e.data)));
    es.addEventListener("stage_start", e => {
      const d = JSON.parse(e.data);
      setCurrent({ stage: d.stage, current: 0, total: 1, phase: null });
    });
    es.addEventListener("stage_progress", e => setCurrent(JSON.parse(e.data)));
    es.addEventListener("stage_complete", e => {
      const d = JSON.parse(e.data);
      setCompleted(c => ({ ...c, [d.stage]: d }));
      setCurrent(null);
    });
    es.addEventListener("stage_error", e => {
      const d = JSON.parse(e.data);
      setCompleted(c => ({ ...c, [d.stage]: { ...d, failed: true } }));
      setCurrent(null);
    });
    es.addEventListener("job_complete", e => { onDone?.(JSON.parse(e.data)); es.close(); });
    es.addEventListener("job_failed", e => { setError(JSON.parse(e.data)); es.close(); });
    return () => es.close();
  }, [jobId]);

  const pct = computePct(plan, completed, current);

  return (
    <Paper sx={{ p: 3 }}>
      <LinearProgress variant="determinate" value={pct} />
      <Typography variant="caption">{pct.toFixed(0)}%</Typography>

      {current && (
        <Box mt={1}>
          <Typography variant="body2">
            {labelFor(current.stage)} {current.phase ? `— ${current.phase}` : ""}
          </Typography>
          <LinearProgress
            variant={current.total > 0 ? "determinate" : "indeterminate"}
            value={current.total > 0 ? (current.current / current.total) * 100 : undefined}
          />
          <Typography variant="caption">{current.current}/{current.total}</Typography>
        </Box>
      )}

      <List dense>
        {plan?.stages.map(s => (
          <ListItem key={s.key}>
            <ListItemIcon>{iconFor(s.key, completed, current)}</ListItemIcon>
            <ListItemText primary={s.label}
              secondary={completed[s.key]?.findings != null
                ? `${completed[s.key].findings} findings · ${fmtMs(completed[s.key].duration_ms)}`
                : null}/>
          </ListItem>
        ))}
      </List>

      {error && <ErrorPanel error={error} />}
    </Paper>
  );
}
```

`<ErrorPanel>` shows `type: message` in an `<Alert severity="error">`, with a collapsible `<Accordion>` for the full traceback (user asked for full traceback visible).

### 4.7 Files that change

Backend:
- `a11y/api/v1/combined/stage_events.py` — add `index/total/weight`, add `stage_progress`, add `job_plan`.
- `a11y/api/v1/combined/store.py` — SQLite migration, stage_events table, `append_event()`, `events_since(job_id, seq)`.
- `a11y/api/v1/combined/routes.py:322` — SSE endpoint: honor `Last-Event-ID`, replay from DB, heartbeat loop.
- `a11y/api/v1/combined/runner.py` — emit `job_plan` at top; pass `index/total` into `_stage_*` helpers.
- `a11y/api/v1/combined/stages.py` — plumb progress callbacks into `_stage_image_audit`, `_stage_rendered_layout_audit`, `_stage_media_audit`.
- `a11y/api/v1/combined/constants.py` — `STAGE_WEIGHTS` dict.

Frontend:
- new `apps/web/src/components/AuditProgress.tsx`
- new `apps/web/src/lib/sse.ts` (thin wrapper only if we want custom reconnect behavior beyond `EventSource` defaults — probably not needed)

---

## 5. Deployment (EC2)

### Machine
- AMI: Ubuntu 24.04 LTS (x86_64)
- Instance: `t3.large`
- Root: `40 GB gp3`
- 4 GB swap added via user-data:
  ```bash
  #!/bin/bash
  fallocate -l 4G /swapfile && chmod 600 /swapfile
  mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  ```

### Security group
- **In**: 22 (SSH, restricted to admin IP), 443 (HTTPS)
- **Out**: all
- **NOT exposed**: 8000 (python), 3000 (node), 8080 (frontend-raw)

### Reverse proxy (new — add to compose)
Add **Caddy** as a 5th service (auto-TLS via Let's Encrypt; zero-config):
```yaml
caddy:
  image: caddy:2-alpine
  ports: ["443:443", "80:80"]
  volumes: [./Caddyfile:/etc/caddy/Caddyfile, caddy_data:/data, caddy_config:/config]
  depends_on: [frontend, python]
```
`Caddyfile`:
```
a11y.example.com {
  reverse_proxy /api/* python:8000
  reverse_proxy /* frontend:80
  encode zstd gzip
  header /api/v1/combined/*/events Cache-Control "no-cache"   # don't buffer SSE
  flush_interval -1                                             # SSE: immediate flush
}
```

### Compose changes
- Remove `0.0.0.0:8000:8000` and `0.0.0.0:3000:3000` host bindings (only Caddy talks to them via internal net).
- Keep `0.0.0.0:8080` off; Caddy replaces it.
- Add `mem_limit: 6g` on python, `mem_limit: 800m` on node, `mem_limit: 300m` on frontend.

### Observability (v1)
- Docker `json-file` log driver already rotating. Good.
- Ship logs to CloudWatch via the awslogs driver when you're ready.
- Add a `/api/v1/health/detail` that returns Node reachability + SQLite ping + last successful audit timestamp — cheap status page.

---

## 6. Rollout order (ranked, do not reorder)

1. ✅ `None.get()` fixes — already landed.
2. ✅ Dockerfile pre-downloads — already landed.
3. **Defensive-None cleanup PR** (section 2 table). Small, safe.
4. **SQLite-backed job store** (section 3). Behind a feature flag env `A11Y_STORE=sqlite|memory` so we can flip back.
5. **Event schema upgrade** (section 4.1–4.2): `job_plan`, `index/total/weight`, `stage_progress` types — backend only, no UI yet. Existing frontend ignores unknown events.
6. **`stage_progress` emission** from `image_audit` first (highest value), then rendered_layout, then media.
7. **Replay buffer + heartbeat** on the SSE route (section 4.4–4.5).
8. **`<AuditProgress>` MUI component** + wire it into the audit page.
9. **Caddy + compose hardening** (section 5).
10. **Instance provisioning script** (user-data + SG + gp3) — write an `infra/ec2-bootstrap.sh`.

Each item is PR-sized (≤ 400 LOC diff). Do not combine.

---

## 7. Open questions / future work (do not block)

- When we outgrow t3.large, split `python` into `api` (FastAPI + orchestration) and `worker` (Playwright + OCR + whisper) containers, communicating via SQLite → eventually Redis + RQ.
- Auth. Today `/api/v1/audit` is open. For real production, put a shared-secret header check or Cognito in front.
- Rate limiting. Caddy can do this (`{remote_ip}` + leaky bucket) without adding a dep.
- Cost cap. faster-whisper `base` on CPU is free but slow. If we ever swap to OpenAI Whisper API, add a per-job cost cap.
