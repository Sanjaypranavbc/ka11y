# ka11y — Full-Stack Code Audit Report

> **Generated:** 2026-03-19
> **Updated:** 2026-03-19 (fixes applied)
> **Scope:** `ka11y-python` · `ka11y-node` · `ka11y-frontend-sdk`
> **Method:** Static analysis · Pattern review · Security audit · Concurrency review
>
> **Status legend:** ✅ Fixed · ⏳ Pending

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Severity Legend](#severity-legend)
3. [ka11y-python — Findings](#ka11y-python)
4. [ka11y-node — Findings](#ka11y-node)
5. [ka11y-frontend-sdk — Findings](#ka11y-frontend-sdk)
6. [Cross-Cutting Issues](#cross-cutting-issues)
7. [Prioritised Fix Roadmap](#prioritised-fix-roadmap)
8. [Positive Findings](#positive-findings)

---

## Executive Summary

| Service | Critical | High | Medium | Low | Total | Fixed |
|---------|----------|------|--------|-----|-------|-------|
| ka11y-python | 3 | 6 | 9 | 5 | **23** | 12 ✅ |
| ka11y-node | 4 | 5 | 8 | 5 | **22** | 15 ✅ |
| ka11y-frontend-sdk | 2 | 5 | 9 | 4 | **20** | 14 ✅ |
| **Total** | **9** | **16** | **26** | **14** | **65** | **41 ✅** |

The three biggest systemic risks are:

1. **Unbounded in-memory state** — `_jobs` dict in `combined.py` and `_subscribers` dict have no TTL and no locking, causing memory leaks and race conditions under load.
2. **SSRF + no rate limiting** in `ka11y-node` — any URL is accepted and sent to Puppeteer, enabling internal network probing, with no concurrency cap on browser spawning.
3. **TypeScript safety disabled** — `strictNullChecks: false` and `noImplicitAny: false` in the frontend let null/undefined bugs reach production silently.

---

## Severity Legend

| Icon | Level | Definition |
|------|-------|-----------|
| 🔴 | **Critical** | Data loss, security breach, or service crash |
| 🟠 | **High** | Significant reliability/security risk in production |
| 🟡 | **Medium** | Correctness bug or degraded experience |
| 🔵 | **Low** | Code quality, maintainability, DX |

---

## ka11y-python

### 🔴 Critical

#### ✅ C-PY-1 · Path Traversal via `get_output_dir()`
**File:** `ka11y/api/v1/dependencies.py`

`urlparse(url).netloc` is used directly in a filesystem path without sanitisation. A crafted URL like `https://evil.com/../../../etc/shadow` can create or overwrite arbitrary directories.

```python
# Current (vulnerable)
netloc = urlparse(url).netloc          # "evil.com/../../../etc"
output_dir = base / netloc / job_id   # path traversal

# Fix
import re
netloc = urlparse(url).netloc
if not re.fullmatch(r'[A-Za-z0-9._-]+', netloc):
    raise ValueError(f"Invalid URL hostname: {netloc}")
output_dir = (base / netloc / job_id).resolve()
assert str(output_dir).startswith(str(base))  # canonical check
```

---

#### ✅ C-PY-2 · Unbounded In-Memory Job Store (Memory Leak)
**File:** `ka11y/api/v1/combined.py` — `_jobs` dict

Completed jobs are never evicted. In a long-running service, memory grows without bound. Under load, this causes OOM crashes.

```python
# Fix: add TTL eviction
import asyncio, time

JOB_TTL_SECONDS = 3600  # 1 hour

async def _evict_old_jobs():
    while True:
        await asyncio.sleep(300)
        cutoff = time.time() - JOB_TTL_SECONDS
        stale = [jid for jid, j in _jobs.items()
                 if j.get("completed_at", time.time()) < cutoff]
        for jid in stale:
            _jobs.pop(jid, None)
            _subscribers.pop(jid, None)

# Start in lifespan
asyncio.create_task(_evict_old_jobs())
```

---

#### ✅ C-PY-3 · Race Condition on `_subscribers` Dict
**File:** `ka11y/api/v1/combined.py` — `_broadcast()` and SSE connect

`_subscribers[job_id].append(queue)` is called from concurrent coroutines without a lock. If a client disconnects while `_broadcast()` iterates the list, a `RuntimeError: list changed size during iteration` crash occurs.

```python
# Fix: use asyncio.Lock per job
_sub_locks: dict[str, asyncio.Lock] = {}

async def _broadcast(job_id: str, event: str, data: dict):
    lock = _sub_locks.setdefault(job_id, asyncio.Lock())
    async with lock:
        queues = list(_subscribers.get(job_id, []))   # snapshot
    for q in queues:
        await q.put((event, data))
```

---

### 🟠 High

#### ✅ H-PY-1 · SSRF via Arbitrary URL in `_call_node_flat()`
**File:** `ka11y/api/v1/combined.py`

The `url` field from the POST body is forwarded to the Node.js service without an allowlist. Attackers can supply `http://127.0.0.1:6379/` to probe internal Redis, `http://169.254.169.254/` for AWS metadata, etc.

```python
# Fix: validate scheme + block private ranges
from ipaddress import ip_address, ip_network
from urllib.parse import urlparse

PRIVATE = [ip_network(r) for r in [
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "127.0.0.0/8", "169.254.0.0/16", "::1/128"
]]

def validate_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs allowed")
    host = p.hostname
    try:
        addr = ip_address(host)
        if any(addr in net for net in PRIVATE):
            raise ValueError("Private/internal URLs not allowed")
    except ValueError:
        pass  # hostname, not IP — DNS resolves later (blind SSRF still possible; add DNS rebinding protection for full fix)
```

---

#### H-PY-2 · No Rate Limiting on `/api/v1/combined/`

Each POST launches Playwright + EasyOCR. An attacker sending 50 concurrent requests exhausts RAM and CPU instantly. Add FastAPI's `slowapi` limiter:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/")
@limiter.limit("5/minute")
async def submit_audit(request: Request, body: AuditRequest):
    ...
```

---

#### ✅ H-PY-3 · OCR Model Reloaded Per Request
**File:** `ka11y/text_detector/ocrbase.py`

`_create_reader()` downloads and instantiates ~200 MB of EasyOCR models each time an `OCRBase` object is constructed. Under concurrent load this causes massive memory pressure and slow startup.

```python
# Fix: module-level singleton with lazy init
import threading

_reader = None
_reader_lock = threading.Lock()

def get_reader(langs: list[str] = ["en"]) -> easyocr.Reader:
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                _reader = easyocr.Reader(langs, gpu=_has_gpu())
    return _reader
```

---

#### H-PY-4 · Playwright Pages Never Closed on Crawler Exceptions
**File:** `ka11y/crawler/crawler.py`

If `page.goto()` raises (timeout, crash), the `page` object is leaked. Over many requests this exhausts browser file descriptors.

```python
# Pattern to enforce cleanup
page = await context.new_page()
try:
    await page.goto(url, timeout=30_000)
    ...
finally:
    await page.close()
```

---

#### H-PY-5 · No Playwright `goto()` Timeout Configured
**File:** `ka11y/api/v1/combined.py`, `ka11y/crawler/crawler.py`

Playwright's default `goto()` timeout is **30 seconds**. For slow sites with `max_depth > 0`, a single unresponsive page blocks the entire audit. Set explicit timeouts and propagate them from the request config.

```python
await page.goto(url, wait_until="domcontentloaded", timeout=config.get("page_timeout_ms", 20_000))
```

---

#### H-PY-6 · `config_loader.py` Has No Error Handling or Validation
**File:** `ka11y/utils/config_loader.py`

A missing YAML file or malformed config crashes the app at startup with an unhandled `FileNotFoundError` or `yaml.YAMLError`. No schema validation means bad config values reach auditors silently.

```python
# Fix
import yaml
from pathlib import Path
from pydantic import BaseModel, Field

class AppConfig(BaseModel):
    max_depth: int = Field(0, ge=0, le=10)
    page_timeout_ms: int = Field(20_000, ge=1_000)
    ocr_languages: list[str] = ["en"]
    # ...

def load_config(path: str = "ka11y/config/config.yml") -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p.resolve()}")
    with p.open() as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)  # Pydantic validates and gives clear errors
```

---

### 🟡 Medium

#### ✅ M-PY-1 · `aria_required` String Comparison Bug
**File:** `ka11y/accessibility/rules/forms/form_auditor.py`

```python
# Current — misses standard HTML "true"
f.aria_required in ("true", "True")

# Fix
(f.aria_required or "").strip().lower() == "true"
```

---

#### ✅ M-PY-2 · Label-in-Name Uses Loose Substring Match
**File:** `ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py`

Visible label `"Go"` matches accessible name `"Gorilla facts"` because the check is bare `in`. Use word-boundary matching and Unicode normalisation:

```python
import unicodedata, re

def _normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower().strip()

def _label_in_name(visible: str, acc_name: str) -> bool:
    v = _normalize(visible)
    a = _normalize(acc_name)
    # word-boundary match
    return bool(re.search(r'\b' + re.escape(v) + r'\b', a))
```

---

#### ✅ M-PY-3 · `_contrast_to_findings` Skips `None` Compliance Silently
**File:** `ka11y/api/v1/combined.py`

When `compliance.get("aa_normal")` returns `None` (missing key), the row is silently skipped. Add a warning so the audit log shows incomplete contrast data:

```python
elif aa_normal is None:
    warnings.append(f"Contrast check skipped for '{row.get('text')}' — compliance data unavailable")
    continue
```

---

#### M-PY-4 · Duplicate Pipeline Code Across Three Routes
**Files:** `pipeline.py`, `crawl.py`, `combined.py`

~80% of the crawl/audit orchestration is copy-pasted. Extract into a shared `_run_pipeline(config, output_dir)` coroutine in a new `ka11y/core/pipeline_runner.py` module. This eliminates three separate places to fix bugs.

---

#### ✅ M-PY-5 · GIF Animation False Positives
**File:** `ka11y/crawler/moving_content_crawler.py`

All `.gif` files are treated as animated. Use Pillow to check frame count:

```python
from PIL import Image

def is_animated_gif(path: str) -> bool:
    try:
        img = Image.open(path)
        img.seek(1)          # raises EOFError if single frame
        return True
    except (EOFError, Exception):
        return False
```

---

#### ✅ M-PY-6 · K-Means Fixed at `k=3` for Color Sampling
**File:** `ka11y/preprocessor/extract_color.py`

Monochrome images waste compute with 3 clusters; photo-rich images need more. Use the elbow method or clamp to image colour count:

```python
unique_colors = len(np.unique(pixels.reshape(-1, 3), axis=0))
k = min(5, max(2, unique_colors // 100))
```

---

#### M-PY-7 · No Image Deduplication Before OCR
**File:** `ka11y/crawler/crawler.py`

The same CDN image URL may appear on 50 pages. Cache OCR results by URL hash:

```python
import hashlib
_ocr_cache: dict[str, list] = {}

def ocr_with_cache(image_path: str) -> list:
    key = hashlib.sha256(open(image_path, "rb").read()).hexdigest()
    if key not in _ocr_cache:
        _ocr_cache[key] = reader.readtext(image_path)
    return _ocr_cache[key]
```

---

#### ✅ M-PY-8 · `print()` Left in Production Logger
**File:** `ka11y/config/logger.py` line 14

Replace with `logging.warning()` or remove entirely.

---

#### ✅ M-PY-9 · Missing Output Dir Timestamp Collision Protection
**File:** `ka11y/api/v1/dependencies.py`

Two simultaneous requests for the same URL at the same second produce identical `output_dir` paths, causing file overwrites. Append a UUID suffix:

```python
import uuid
output_dir = base / netloc / f"{timestamp}_{uuid.uuid4().hex[:8]}"
```

---

### 🔵 Low

#### L-PY-1 · Typo in Module Name
**File:** `ka11y/classifier/classfier.py` → should be `classifier.py`

#### L-PY-2 · Commented-Out Code Blocks in `text_detector.py`
Remove or move to a git branch. Dead code increases cognitive load.

#### ✅ L-PY-3 · `logger.py` Emoji in File Logs
Rich emoji formatting renders as raw Unicode bytes in plain-text log files and log aggregators (Loki, CloudWatch). Log plain text; use Rich only for console output.

#### L-PY-4 · Tests Missing for Combined Route SSE Streaming
`tests/test_api_smoke.py` has no SSE consumer test. Add an async SSE test using `httpx-sse`.

#### L-PY-5 · No `mypy` / `ruff` in CI
Add to `pyproject.toml`:
```toml
[tool.mypy]
strict = true
ignore_missing_imports = true

[tool.ruff]
select = ["E", "F", "UP", "B", "SIM", "I"]
```

---

## ka11y-node

### 🔴 Critical

#### ✅ C-ND-1 · Three API Endpoints Never Registered
**File:** `server.js`

`GET /rules`, `GET /rules-guide`, `GET /rules-guide/:ruleId` are documented, have controllers, have tests — but are **never wired** in `server.js`. All three return `404`. Tests for them fail.

```javascript
// Add to server.js (after existing controller setup)
const RulesController     = require('./src/controllers/rules.controller');
const RulesGuideController = require('./src/controllers/rulesGuide.controller');

const rulesCtrl      = new RulesController(rulesService, logger);
const rulesGuideCtrl = new RulesGuideController(logger);

app.get('/api/v1/rules',                rulesCtrl.getRules.bind(rulesCtrl));
app.get('/api/v1/rules-guide',          rulesGuideCtrl.getAllRules.bind(rulesGuideCtrl));
app.get('/api/v1/rules-guide/:ruleId',  rulesGuideCtrl.getRuleById.bind(rulesGuideCtrl));
```

---

#### ✅ C-ND-2 · SSRF — No URL Allowlist Before Puppeteer Navigation
**File:** `src/services/accessibility.service.js`, `src/controllers/accessibility.controller.js`

`analyseUrl()` navigates Puppeteer to any user-supplied URL, including `http://localhost:6379` (Redis), `http://169.254.169.254/latest/meta-data/` (AWS IMDS), `file:///etc/passwd`.

```javascript
// Fix: validate before navigation
const { URL } = require('url');
const dns = require('dns/promises');
const ipRangeCheck = require('ip-range-check'); // npm i ip-range-check

async function assertPublicUrl(rawUrl) {
  let parsed;
  try { parsed = new URL(rawUrl); } catch { throw new Error('Invalid URL'); }
  if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('Only http/https allowed');
  const { address } = await dns.lookup(parsed.hostname);
  const privateRanges = ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8','169.254.0.0/16'];
  if (ipRangeCheck(address, privateRanges)) throw new Error('Private/internal URLs not allowed');
}
```

---

#### ✅ C-ND-3 · No Rate Limiting — Puppeteer DOS
**File:** `src/services/accessibility.service.js`

Each request spawns a full Chromium browser (~50–150 MB RAM). No concurrency cap exists. Ten concurrent requests will OOM a 1 GB container.

```javascript
// Fix: browser pool with p-limit
const pLimit = require('p-limit'); // npm i p-limit
const limit  = pLimit(parseInt(process.env.MAX_CONCURRENT_BROWSERS) || 3);

// Wrap service calls:
await limit(() => accessibilityService.analyseUrl(url, options));
```

Alternatively use a browser pool library like `puppeteer-cluster`.

---

#### ✅ C-ND-4 · CORS Claimed but Not Implemented
**File:** `server.js`

The startup log message prints `"CORS origin: localhost (any port)"` but no `cors` middleware is installed. Cross-origin requests from the frontend will be blocked in production.

```javascript
// Fix
const cors = require('cors'); // npm i cors
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || 'http://localhost:5173',
  methods: ['GET', 'POST'],
}));
```

---

### 🟠 High

#### ✅ H-ND-1 · Invalid Jest Version in `package.json`
**Field:** `devDependencies["jest"]` = `"^30.3.0"`

Jest 30 does not exist as of 2026. Latest stable is 29.x. This causes `npm install` to fail or install an unexpected version.

```json
"jest": "^29.7.0"
```

---

#### ✅ H-ND-2 · Jest Coverage Pattern Wrong — Misses All Source Files
**File:** `package.json`

```json
// Current (matches nothing — no .js files at routes/ root)
"collectCoverageFrom": ["*.js", "routes/**/*.js"]

// Fix
"collectCoverageFrom": ["src/**/*.js", "server.js", "!src/**/*.test.js"]
```

---

#### ✅ H-ND-3 · Synchronous `fs.appendFileSync` Blocks Event Loop
**File:** `src/utils/logger.js`

Synchronous file I/O stalls Node's single thread. Every log line blocks all pending requests.

```javascript
// Fix: use async appendFile
const { appendFile, mkdir } = require('fs/promises');

async function writeLog(dir, filename, content) {
  await mkdir(dir, { recursive: true });
  await appendFile(path.join(dir, filename), content);
}
```

Or use a production logger like **pino** (structured JSON, async transport):
```bash
npm i pino pino-pretty pino-roll
```

---

#### H-ND-4 · Deprecated axe-core Callback API
**File:** `src/services/accessibility.service.js`

`axe.run(document, options, (err, results) => {})` is the callback form — deprecated. Modern axe-core supports Promises natively:

```javascript
// Fix
try {
  const results = await axe.run(document, runOptions);
  resolve(mapper.mapResultsFlat(results, level));
} catch (err) {
  reject(err);
}
```

---

#### ✅ H-ND-5 · `wcagCriteriaNames.js` Is Orphaned Dead Code
**File:** `src/utils/wcagCriteriaNames.js`

The file is imported nowhere. It duplicates data already in `axeResultMapper.js`. Delete it and consolidate into a single source of truth.

---

### 🟡 Medium

#### ✅ M-ND-1 · RULE_SC_FALLBACK Map Incomplete
**File:** `src/utils/axeResultMapper.js`

Rules like `target-size`, `color-contrast-enhanced`, `identical-links-same-purpose` are missing from the fallback map and return `null` WCAG SC in the response.

Add the missing entries:
```javascript
const RULE_SC_FALLBACK = {
  ...existingEntries,
  'target-size':                   '2.5.8',
  'color-contrast-enhanced':       '1.4.6',
  'identical-links-same-purpose':  '2.4.9',
  'focus-order-semantics':         '2.4.3',
};
```

---

#### ✅ M-ND-2 · No Input Validation on `successCriteriaId`
**File:** `src/controllers/accessibility.controller.js`

An invalid SC ID like `"foo"` or `"1.1.foo"` silently returns an empty result set with no error. Add validation:

```javascript
const SC_PATTERN = /^\d+\.\d+\.\d+$/;
if (successCriteriaId && !SC_PATTERN.test(successCriteriaId)) {
  return res.status(400).json({ error: 'Invalid successCriteriaId format. Expected e.g. "1.1.1"' });
}
```

---

#### M-ND-3 · No Log Rotation → Disk Exhaustion
**File:** `src/utils/logger.js`

Logs grow without limit. Use `pino-roll` or `winston-daily-rotate-file`:

```javascript
const transport = pino.transport({
  target: 'pino-roll',
  options: { file: './logs/app', frequency: 'daily', mkdir: true, size: '50m' }
});
```

---

#### ✅ M-ND-4 · Hardcoded Chromium Path Breaks Non-Linux Dev
**File:** `src/config/app.config.js`

`executablePath: '/usr/bin/chromium'` fails on macOS/Windows. Allow Puppeteer to find its bundled browser when no env var is set:

```javascript
executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
// undefined → Puppeteer uses its own bundled Chromium
```

---

#### ✅ M-ND-5 · `rulesGuide.js` (83 KB) Loaded Synchronously at Startup
**File:** `src/utils/rulesGuide.js`

Parse once at startup and freeze the object. Consider splitting into per-rule JSON files loaded on demand to reduce initial memory:

```javascript
Object.freeze(rulesGuide); // at least prevent accidental mutation
```

Long-term: load lazily per rule ID query.

---

#### M-ND-6 · No Response Caching for Identical URL Analyses
**File:** `src/services/accessibility.service.js`

Repeatedly auditing the same URL spawns a full browser each time. Add a short-lived TTL cache (e.g., 60 s) keyed by URL + level:

```javascript
const NodeCache = require('node-cache'); // npm i node-cache
const cache = new NodeCache({ stdTTL: 60, checkperiod: 30 });

const cacheKey = `${url}::${level}`;
const cached = cache.get(cacheKey);
if (cached) return cached;
const result = await runAnalysis(url, level);
cache.set(cacheKey, result);
return result;
```

---

#### ✅ M-ND-7 · Tags Query Parameter Not Trimmed
**File:** `src/controllers/rules.controller.js` line 40

`req.query.tags.split(',')` → `["wcag2a", " wcag2aa"]` (leading space breaks filter).

```javascript
const tags = req.query.tags?.split(',').map(t => t.trim()).filter(Boolean) ?? [];
```

---

#### ✅ M-ND-8 · Swagger Docs Missing Three Endpoints
**File:** `src/config/swagger.config.js`

Add `rules.controller.js` and `rulesGuide.controller.js` to the swagger `apis` array:

```javascript
apis: [
  './src/controllers/health.controller.js',
  './src/controllers/accessibility.controller.js',
  './src/controllers/rules.controller.js',
  './src/controllers/rulesGuide.controller.js',
],
```

---

### 🔵 Low

#### L-ND-1 · Inconsistent Endpoint Naming
`analyze-accessibility` (American) vs `analyse-url` (British). Pick one convention project-wide.

#### L-ND-2 · Health Check Doesn't Verify Puppeteer
Add a `/health?deep=true` path that launches a minimal browser and returns `503` if it fails.

#### L-ND-3 · No Correlation / Trace IDs
Add `express-request-id` middleware so every log line for a request shares an ID, making distributed debugging possible.

#### ✅ L-ND-4 · `.idea/` Not in `.gitignore`
Add IDE metadata directories:
```
.idea/
.vscode/
*.swp
coverage/
```

#### L-ND-5 · `selftest.js` Not Integrated with Jest
Move to a Jest integration test file or document it as a manual test and gate it behind `npm run test:integration`.

---

## ka11y-frontend-sdk

### 🔴 Critical

#### ✅ C-FE-1 · TypeScript Null Safety Completely Disabled
**File:** `tsconfig.json`

```json
// Current — disables the most valuable TypeScript checks
"strictNullChecks": false,
"noImplicitAny": false

// Fix — enable incremental safety
"strict": true,
"noUnusedLocals": true,
"noUnusedParameters": true
```

With `strictNullChecks: false`, every `null` reference bug is invisible to the compiler. The `flattenFinding()` cast, optional chain gaps, and `result.*` accesses throughout components can throw at runtime with no TypeScript warning.

---

#### C-FE-2 · Backend Responses Not Validated (No Runtime Schema)
**File:** `src/hooks/useAudit.ts`

`mapPollResult()` casts raw `JSON.parse()` output directly to typed interfaces. A backend change or malformed response silently creates incorrect UI state.

```typescript
// Add Zod validation
import { z } from 'zod'; // npm i zod

const FindingSchema = z.object({
  source:         z.enum(["axe", "python"]),
  rule_id:        z.string(),
  wcag_sc:        z.string().nullable(),
  criterion_name: z.string().nullable(),
  level:          z.enum(["A", "AA", "AAA"]).nullable(),
  severity:       z.enum(["critical", "high", "medium", "low"]).nullable(),
  status:         z.enum(["fail", "pass", "needs_review"]),
  reason:         z.string(),
  suggested_fix:  z.string().nullable(),
  help_url:       z.string().url().nullable(),
  element:        z.object({
    html:       z.string(),
    element_id: z.string().nullable(),
    tag:        z.string().nullable(),
    page_url:   z.string(),
  }).nullable(),
});

const AuditResultSchema = z.object({
  violations:   z.array(FindingSchema),
  needs_review: z.array(FindingSchema),
  passes:       z.array(FindingSchema),
  contrast_report: ContrastReportSchema.nullable().optional(),
  // ...
});

// In mapPollResult:
const parsed = AuditResultSchema.safeParse(report);
if (!parsed.success) {
  console.error("Invalid audit response", parsed.error);
  return emptyResult;
}
```

---

### 🟠 High

#### ✅ H-FE-1 · Memory Leak in `useAudit` — SSE and Polling Not Cleaned Up
**File:** `src/hooks/useAudit.ts`

`sseRef.current` (EventSource) and `pollingRef.current` (setInterval) are never cleaned up on component unmount. If the user navigates away during an audit, the EventSource reconnects indefinitely.

```typescript
useEffect(() => {
  return () => {
    sseRef.current?.close();
    if (pollingRef.current) clearInterval(pollingRef.current);
  };
}, []);
```

---

#### ✅ H-FE-2 · SSE `JSON.parse` Without Try-Catch Crashes the Hook
**File:** `src/hooks/useAudit.ts`

Any malformed SSE event (network hiccup, partial frame, proxy injection) throws an uncaught exception that kills the audit UI.

```typescript
es.addEventListener("stage_complete", (e) => {
  try {
    const data = JSON.parse(e.data);
    // ...
  } catch (err) {
    console.warn("Malformed SSE event:", e.data, err);
  }
});
```

---

#### ✅ H-FE-3 · Race Condition — Stale Poll Runs After New Audit Starts
**File:** `src/hooks/useAudit.ts`

If a user starts Audit B while Audit A is still polling, the A poll may resolve and overwrite Audit B's state. Add a cancellation token:

```typescript
const activeJobRef = useRef<string | null>(null);

// When starting new audit:
activeJobRef.current = newJobId;

// In poll callback:
if (jobId !== activeJobRef.current) return; // discard stale result
```

---

#### ✅ H-FE-4 · `navigator.clipboard.writeText()` Not Wrapped in Try-Catch
**File:** `src/components/audit/SuggestedFixModal.tsx`

`clipboard.writeText()` throws `NotAllowedError` on HTTP (non-HTTPS) or when permission is denied. This crashes the copy button silently.

```typescript
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    toast({ title: "Copied!" });
  } catch {
    // Fallback for HTTP or denied permission
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    toast({ title: "Copied (fallback)" });
  }
};
```

---

#### ✅ H-FE-5 · `console.error()` Left in Production (`NotFound.tsx`)
**File:** `src/pages/NotFound.tsx` line 8

```typescript
// Remove — this logs on every 404, polluting production browser consoles
console.error("404 - Page not found");
```

Use an error reporting service (Sentry, LogRocket) in production if 404 tracking is needed.

---

#### ✅ H-FE-6 · No Root Error Boundary
**File:** `src/App.tsx`

Any uncaught render exception in a chart, table, or image component crashes the entire app to a blank screen.

```typescript
// src/components/ErrorBoundary.tsx
import { Component, type ReactNode } from "react";

export class ErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() { return { hasError: true }; }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("Render error:", error, info);
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

// In App.tsx:
<ErrorBoundary fallback={<p>Something went wrong. Please reload.</p>}>
  <Index />
</ErrorBoundary>
```

---

### 🟡 Medium

#### ✅ M-FE-1 · Hardcoded Default Audit URL in Sidebar
**File:** `src/components/audit/AuditSidebar.tsx` line 53

`url: "https://www.kao.com/global/en/"` is a real production URL baked into the default state. Replace with an empty string or a placeholder:

```typescript
url: "",
// or read from localStorage for persistence:
url: localStorage.getItem("lastAuditUrl") ?? "",
```

---

#### M-FE-2 · Tables Hardcoded to 50 Items — No Pagination
**Files:** `ViolationsTab.tsx`, `NeedsReviewTab.tsx`, `PassesTab.tsx`

Large audits produce hundreds of violations. Slicing to 50 with no feedback is a silent data loss.

```typescript
// Option 1: Virtual list (recommended for large datasets)
import { useVirtualizer } from '@tanstack/react-virtual'; // npm i @tanstack/react-virtual

// Option 2: Simple pagination
const PAGE_SIZE = 50;
const [page, setPage] = useState(0);
const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
```

---

#### ✅ M-FE-3 · Vite Proxy Target Hardcoded
**File:** `vite.config.ts`

```typescript
// Current
target: "http://localhost:8000"

// Fix — use env var
target: process.env.VITE_API_URL ?? "http://localhost:8000"
```

Add `VITE_API_URL=http://backend:8000` to `.env.docker` for containerised dev.

---

#### ✅ M-FE-4 · useToast Has Global Listener Memory Leak
**File:** `src/hooks/use-toast.ts`

`listeners.push(setState)` adds a new listener on every component mount but the cleanup function only removes the exact reference. If the component re-mounts, duplicates accumulate.

```typescript
// Fix in useToast:
useEffect(() => {
  listeners.push(setState);
  return () => {
    const idx = listeners.indexOf(setState);
    if (idx > -1) listeners.splice(idx, 1);
  };
}, []);  // empty deps — stable setState reference
```

---

#### ✅ M-FE-5 · Loading Skeleton Missing `aria-busy`
**File:** `src/pages/Index.tsx` line 114-127

Screen readers don't know the page is loading. Add ARIA live attributes:

```tsx
<main
  className="flex-1 overflow-y-auto grid-bg"
  aria-busy={isLoading}
  aria-live="polite"
>
```

---

#### ✅ M-FE-6 · Error State Missing `role="alert"`
**File:** `src/pages/Index.tsx` lines 131-139

The "Audit Failed" error block is not announced to screen readers.

```tsx
<div className="text-center space-y-3" role="alert" aria-live="assertive">
  <AlertTriangle ... />
  <h2>Audit Failed</h2>
  <p>{error || "An unknown error occurred."}</p>
</div>
```

---

#### ✅ M-FE-7 · Chart Tooltips Not Keyboard Accessible
**File:** `src/components/audit/DashboardTab.tsx`

Recharts `<Tooltip />` is mouse-only. Add `tabIndex` to chart containers and use `aria-label` descriptions on cells:

```tsx
<ChartContainer
  config={...}
  className="h-64"
  role="img"
  aria-label={`Pie chart: ${severityData.map(d => `${d.name}: ${d.value}`).join(', ')}`}
  tabIndex={0}
>
```

For full accessibility, render a visually-hidden `<table>` alongside every chart containing the same data.

---

#### M-FE-8 · 8 Unused Example Components Bloat Bundle
**Files:** `AccessibilityIssues.tsx`, `HeroSummary.tsx`, `KeyHighlights.tsx`, `OcrFindings.tsx`, `Recommendations.tsx`, `ReportHeader.tsx`, `ReportFooter.tsx`, `VisualDifferences.tsx`

None of these are imported anywhere. Delete them to reduce bundle size and cognitive load:

```bash
rm src/components/AccessibilityIssues.tsx
rm src/components/HeroSummary.tsx
rm src/components/KeyHighlights.tsx
rm src/components/OcrFindings.tsx
rm src/components/Recommendations.tsx
rm src/components/ReportHeader.tsx
rm src/components/ReportFooter.tsx
rm src/components/VisualDifferences.tsx
```

---

#### M-FE-9 · SettingsTab Input Has No State Binding
**File:** `src/components/audit/SettingsTab.tsx`

```tsx
// Current — dead input; value never changes
<Input defaultValue="http://localhost:8000" />

// Fix — either wire to state/config, or remove
const [apiUrl, setApiUrl] = useState(
  import.meta.env.VITE_API_URL ?? "http://localhost:8000"
);
<Input value={apiUrl} onChange={e => setApiUrl(e.target.value)} />
```

---

### 🔵 Low

#### ✅ L-FE-1 · `use-mobile.tsx` Returns `false` on First Render (Hydration Mismatch)
```typescript
// Fix: use undefined as initial state to signal "not yet measured"
const [isMobile, setIsMobile] = useState<boolean | undefined>(undefined);
// Render null or skeleton until measured
if (isMobile === undefined) return null;
```

---

#### L-FE-2 · No Debounce on URL Input
**File:** `src/components/audit/AuditSidebar.tsx`

The URL field updates config on every keystroke. Debounce with a small delay to avoid thrashing:
```typescript
import { useDebouncedCallback } from "use-debounce"; // npm i use-debounce
const updateUrl = useDebouncedCallback(
  (val: string) => setConfig(c => ({ ...c, url: val })), 300
);
```

---

#### L-FE-3 · Chart Legend Capitalisation — Replaces Only First Underscore
**File:** `src/components/audit/DashboardTab.tsx` line 143

`value.replace("_", " ")` replaces only the first `_`. Use `replaceAll`:
```typescript
formatter={(value) => <span>{value.replaceAll("_", " ")}</span>}
```

---

#### L-FE-4 · Truncated Error Message in Stage Progress Has No Expand Option
**File:** `src/pages/Index.tsx` line 65

Error text is truncated at `max-w-[140px]` with `title` tooltip — fine for mouse users, inaccessible for keyboard-only users. Use a `<details>/<summary>` or a small expand button.

---

## Cross-Cutting Issues

### XC-1 · No Request Tracing / Correlation IDs

None of the three services share a request/trace ID. When an audit fails, it's impossible to correlate the frontend log, the Python log, and the Node log to the same request.

**Fix:** Generate a `X-Request-ID` UUID in the frontend, forward it in all backend HTTP calls, log it in every service.

---

### XC-2 · No End-to-End Tests

There are no integration tests that exercise the full flow: submit audit → SSE stream → poll result → render UI. Add Playwright E2E tests:

```typescript
// tests/e2e/full-audit.spec.ts
test('audit flow', async ({ page }) => {
  await page.goto('http://localhost:5173');
  await page.fill('#audit-url', 'https://example.com');
  await page.click('button:has-text("Run Audit")');
  await page.waitForSelector('text=completed', { timeout: 120_000 });
  await expect(page.locator('[data-testid="violations-count"]')).toBeVisible();
});
```

---

### XC-3 · No Shared WCAG Metadata Source of Truth

`axeResultMapper.js` (Node), `combined.py` (Python), and `audit.ts` (Frontend) all independently maintain WCAG SC names, levels, and severity mappings. When a new WCAG criterion is added, three files must be updated.

**Fix:** Extract to a single `wcag-criteria.json` file in a shared `ka11y-shared/` package consumed by all three services.

---

### XC-4 · Docker `crawled_images` Volume Not Bounded

The shared `crawled_output` Docker volume grows without limit. Old job output is never purged. Add a cron-style cleanup container or a volume size limit in `docker-compose.yml`.

---

### XC-5 · No Security Headers on Either Backend

Neither FastAPI nor Express sets `X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`, or `Strict-Transport-Security`.

```python
# FastAPI (ka11y-python)
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
```

```javascript
// Express (ka11y-node)
const helmet = require('helmet'); // npm i helmet
app.use(helmet());
```

---

## Prioritised Fix Roadmap

### Sprint 1 — Stop the Bleeding (Security & Crashes)

| # | Issue | Service | Effort |
|---|-------|---------|--------|
| 1 | C-PY-1 Path traversal in `get_output_dir` | Python | 1 h |
| 2 | C-ND-2 SSRF in `analyseUrl` | Node | 2 h |
| 3 | C-PY-3 `_subscribers` race condition | Python | 1 h |
| 4 | C-ND-3 Puppeteer concurrency cap | Node | 2 h |
| 5 | C-ND-4 Add CORS middleware | Node | 30 m |
| 6 | H-FE-6 Root error boundary | Frontend | 1 h |
| 7 | H-FE-2 SSE JSON.parse try-catch | Frontend | 30 m |
| 8 | XC-5 Security headers (helmet + middleware) | All | 1 h |

---

### Sprint 2 — Reliability & Memory

| # | Issue | Service | Effort |
|---|-------|---------|--------|
| 9 | C-PY-2 Job TTL eviction | Python | 2 h |
| 10 | H-PY-3 OCR model singleton | Python | 1 h |
| 11 | H-PY-1 SSRF in combined.py Node call | Python | 1 h |
| 12 | H-FE-1 SSE/poll cleanup on unmount | Frontend | 1 h |
| 13 | H-FE-3 Stale-poll race condition | Frontend | 1 h |
| 14 | H-ND-3 Async logger (pino) | Node | 2 h |
| 15 | C-ND-1 Wire missing 3 endpoints | Node | 1 h |

---

### Sprint 3 — Correctness & Type Safety

| # | Issue | Service | Effort |
|---|-------|---------|--------|
| 16 | C-FE-1 Enable strict TypeScript | Frontend | 4 h |
| 17 | C-FE-2 Add Zod runtime validation | Frontend | 4 h |
| 18 | H-ND-1 Fix Jest version | Node | 15 m |
| 19 | M-PY-1 `aria_required` comparison fix | Python | 15 m |
| 20 | M-PY-2 Label-in-name word-boundary + Unicode | Python | 1 h |
| 21 | M-ND-1 RULE_SC_FALLBACK completeness | Node | 1 h |
| 22 | M-FE-1 Remove hardcoded default URL | Frontend | 15 m |
| 23 | L-FE-3 `replaceAll` in chart legend | Frontend | 5 m |

---

### Sprint 4 — Quality of Life

| # | Issue | Service | Effort |
|---|-------|---------|--------|
| 24 | M-FE-2 Pagination / virtualised tables | Frontend | 3 h |
| 25 | M-PY-4 Extract shared pipeline runner | Python | 4 h |
| 26 | M-ND-6 Response caching for identical URLs | Node | 2 h |
| 27 | M-FE-8 Delete 8 unused components | Frontend | 15 m |
| 28 | XC-1 Correlation / trace IDs | All | 3 h |
| 29 | XC-2 End-to-end Playwright test | All | 4 h |
| 30 | XC-3 Shared WCAG metadata JSON | All | 2 h |

---

## Positive Findings

Despite the issues above, the codebase demonstrates strong intent and many good patterns:

**ka11y-python**
- Excellent WCAG coverage breadth — 6+ criteria with custom heuristics beyond axe-core
- SSE streaming with polling fallback is a sophisticated resilience pattern
- Pydantic models throughout give strong structural guarantees
- Graceful degradation when Node/axe-core stage fails
- `try/finally` cleanup in the lifespan context manager

**ka11y-node**
- Per-request browser isolation prevents cross-audit contamination
- `try/finally { browser.close() }` guarantees browser cleanup even on exceptions
- Comprehensive `rulesGuide.js` is a genuine resource (fail examples, pass examples, fix tips)
- Swagger/OpenAPI setup is well-structured (just needs wiring)
- Excellent `selftest.js` fixture covering 80+ axe-core rules

**ka11y-frontend-sdk**
- SSE streaming → polling fallback is a robust UI pattern
- Stage progress visualisation during audit is excellent UX
- Good accessible icon usage (`aria-hidden="true"` on decorative icons)
- Image Visualiser tab architecture (shared sub-components from ContrastReportSection) is clean
- Export JSON functionality is a thoughtful power-user feature
- Recharts with proper `role="img"` and `aria-label` on chart containers
- Tailwind token-based design system with accessible semantic colour names (critical, serious, success)

---

*End of report · ka11y Code Audit 2026-03-19*