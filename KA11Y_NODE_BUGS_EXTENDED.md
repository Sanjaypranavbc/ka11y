# ka11y-python — Bug Report & Edge Case Analysis

> **Date:** 2026-03-26
> **Scope:** `/ka11y-python/ka11y/` — all crawlers, OCR pipeline, contrast analysis, API layer
> **Status of previously fixed bugs:** Playwright Docker args (`--no-sandbox`, `--disable-dev-shm-usage`), `numpy.bool_` JSON serialization in `contrast_analyser.py`, `json.dump` safety-net in `runner.py`, Rich `force_terminal` — all confirmed applied.

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High     | 4 |
| Medium   | 5 |
| Low      | 4 |
| **Total**| **13** |

---

## High Severity

---

### H-1 — EasyOCR reader is not thread-safe for concurrent audit jobs

**File:** `ka11y/text_detector/ocrbase.py:34`

```python
def readtext(self, image_path: str):
    return self.reader.readtext(image_path)   # ← no lock
```

**Problem:** The `get_ocr_reader()` singleton is correctly protected against concurrent *initialisation* (double-checked locking). But once initialised, every job calls `self.reader.readtext(image_path)` on the same `easyocr.Reader` / PyTorch model instance with no lock. PyTorch inference is **not thread-safe** when multiple threads call the same model concurrently. With `asyncio.to_thread` used in `stages.py`, two simultaneous audit requests will hit this race.

**Symptoms:** corrupt bounding boxes, wrong OCR text, silent tensor shape errors, intermittent crashes under load.

**Fix:**

```python
# ocrbase.py
_reader_lock = threading.Lock()
_readtext_lock = threading.Lock()      # ← add this

class OCRReader:
    def readtext(self, image_path: str):
        with _readtext_lock:            # serialize inference
            return self.reader.readtext(image_path)
```

---

### H-2 — Module-level `config = load_config()` fails the entire process at import time

**File:** `ka11y/utils/config_loader.py:18`

```python
config = load_config()   # runs at import time
```

**Problem:** Any module that does `from ka11y.utils.config_loader import config` (e.g. `text_detector.py`, `crawler.py`) will trigger `load_config()` at import time. If `config/config.yml` is missing, misnamed, or unreadable in a Docker build layer, **every module that imports it fails with `FileNotFoundError`** and the entire service crashes on startup with an unhelpful traceback.

**Symptoms:** `ModuleNotFoundError` / `FileNotFoundError` at container start, no descriptive log output.

**Fix:** Remove the module-level call. Let each consumer call `load_config()` inside its own function/`__init__`:

```python
# config_loader.py  — remove line 18:
# config = load_config()    ← DELETE

# Each module:
from ka11y.utils.config_loader import load_config
CONFIG = load_config()   # inside the module, not at top-level if preferred
```

---

### H-3 — Seven concurrent Playwright browsers launched per audit job

**File:** `ka11y/api/v1/combined/stages.py` — `_run_python_stages()`

**Problem:** `asyncio.gather(...)` fires all 7 Python stage coroutines at once. Each stage opens its own Playwright/Chromium browser. Combined with axe-core (Node), a single audit job spawns **8 browser processes simultaneously**. With two concurrent audit requests (allowed by the rate limiter: 30 POST/60 s), that's **16 browser processes** competing for RAM and CPU, easily exhausting a container with 2–4 GB RAM.

Each Chromium instance uses ~300–500 MB RSS.

**Symptoms:** OOMKill of the Python container, jobs failing silently, Docker container restart loop.

**Fix (short-term):** Run the heavier stages (image_audit, rendered_layout) first, then the lighter ones in a second gather:

```python
# stages.py — two-phase gather
heavy_results = await asyncio.gather(
    _timed(_stage_image_audit(...)),
    _timed(_stage_rendered_layout_audit(...)),
    return_exceptions=True,
)
light_results = await asyncio.gather(
    _timed(_stage_form_audit(...)),
    _timed(_stage_label_in_name(...)),
    _timed(_stage_pause_stop_hide(...)),
    _timed(_stage_target_size(...)),
    _timed(_stage_text_spacing(...)),
    return_exceptions=True,
)
```

**Fix (long-term):** Implement a shared Playwright `BrowserPool` singleton that limits total browser instances to `N` (e.g. 3), with a semaphore, reusing contexts across stages.

---

### H-4 — SSRF guard is blind to DNS rebinding attacks

**File:** `ka11y/crawler/_ssrf_guard.py:63-72`, `ka11y/api/v1/combined/routes.py:142-193`

```python
async def _ssrf_route_handler(route, request) -> None:
    url = request.url
    m = _IP_HOST_RE.match(url)       # ← only blocks literal IP URLs
    if m:
        ...
    await route.continue_()          # ← all hostname URLs pass through
```

**Problem:** The pre-flight `_assert_public_url()` resolves the hostname and rejects private IPs. But there is a **TOCTOU window** between Python's DNS check and Chromium's actual TCP connection. An attacker who controls a domain can:
1. First resolution: returns a public IP → passes `_assert_public_url`
2. Before Playwright connects: rebind DNS to `169.254.169.254` (cloud metadata) or `10.x.x.x`
3. The SSRF guard only triggers for literal-IP URLs — `http://myevildomain.com/` with a private IP resolution is `route.continue_()`d

**Fix:** Pass `--host-resolver-rules` to Chromium so it is forced to use the pre-resolved verified IP:

```python
# In all crawlers, after _assert_public_url resolves the IP:
from urllib.parse import urlparse
import socket

hostname = urlparse(url).hostname
verified_ip = socket.gethostbyname(hostname)
browser = await pw.chromium.launch(
    headless=True,
    args=[
        "--no-sandbox",
        "--disable-dev-shm-usage",
        f"--host-resolver-rules=MAP {hostname} {verified_ip}",
    ],
)
```

---

## Medium Severity

---

### M-1 — `estimate_boldness()` returns `numpy.bool_`, not Python `bool`

**File:** `ka11y/utils/text_detector_helper.py:27`

```python
density = text_pixels / total_pixels   # np.float64
return density > 0.35                  # numpy.bool_  ← bug
```

**Problem:** `text_pixels = np.sum(thresh == 0)` is `np.intp`. Dividing by `int` gives `np.float64`. The comparison `> 0.35` produces `numpy.bool_`. The `is_bold` parameter travels into `check_wcag_compliance()` where `is_bold and font_size_px >= 18.5` evaluates with a numpy operand. Although the outer `bool()` cast added to `contrast_analyser.py` prevents JSON serialization failure, the `numpy.bool_` still propagates into Pydantic field values and any future code path that calls `isinstance(is_bold, bool)` will return `False`.

**Fix:**

```python
# text_detector_helper.py
return bool(density > 0.35)
```

---

### M-2 — `bbox_height_rotated` crashes with `IndexError` on short bounding boxes

**File:** `ka11y/utils/text_detector_helper.py:31-33`

```python
def bbox_height_rotated(bbox):
    p0 = np.array(bbox[0])
    p3 = np.array(bbox[3])   # IndexError if len(bbox) < 4
    return np.linalg.norm(p3 - p0)
```

**Problem:** EasyOCR normally returns 4-point bounding boxes, but degenerate or very small text regions can produce 2-point boxes. There is no guard before `bbox[3]` in either `bbox_height_rotated` or its callsite in `text_detector.py`. This crashes the entire `detect_text_in_image` call for that image, silently discarding the result.

**Fix:**

```python
# text_detector.py — before line 220
if len(clean_bbox) < 4:
    logger.warning(f"Skipping detection with degenerate bbox (len={len(clean_bbox)}): {text!r}")
    continue
```

---

### M-3 — numpy arrays (`region`, `mask`) accumulate in RAM throughout a job

**File:** `ka11y/text_detector/text_detector.py:366-367`, `ka11y/accessibility/rules/non_text/contrast_analyser.py:231-232`

```python
# contrast_analyser.py — analyze_text_region returns:
return {
    "region": region,   # full numpy array crop of the image
    "mask": mask,       # full numpy mask of the same shape
    ...
}
# text_detector.py — stored on the model:
DetailedDetection(contrast_info=contrast_info, ...)
```

**Problem:** Every text detection stores a full-resolution numpy image crop in `DetailedDetection.contrast_info["region"]` and `["mask"]`. These are used only during colour extraction (a few lines later). After that they have no purpose, but they remain in memory inside every `TextDetectionResult` object in `self.results`. A page with 200 images × 5 detections each = 1000 numpy arrays in RAM for the lifetime of the job. At ~50 KB each, that's ~50 MB of stale pixel data.

**Fix:** Strip the heavy keys immediately after colour extraction is done:

```python
# text_detector.py — after extract_colors_from_mask call (around line 258)
extracted = extract_color.extract_colors_from_mask(
    contrast_info["region"], contrast_info["mask"], k_bg=3
)
contrast_info.pop("region", None)   # ← free the numpy crop
contrast_info.pop("mask", None)     # ← free the numpy mask
```

---

### M-4 — Background audit task not tracked; Playwright browsers orphaned on shutdown

**File:** `ka11y/api/v1/combined/routes.py:232`

```python
asyncio.create_task(_run_job(job_id, payload))
```

**Problem:** The task handle is discarded immediately. When uvicorn receives `SIGTERM` (during `docker compose down` or a container restart), the lifespan shutdown cancels only the `_evict_old_jobs` task. Any running `_run_job` tasks — which may have live Playwright browsers open — are **abandoned without cleanup**. This leaves zombie Chrome processes inside the container until the OS kills them.

**Fix:** Track the task in `_jobs` and cancel it during lifespan shutdown:

```python
# routes.py
task = asyncio.create_task(_run_job(job_id, payload))
_jobs[job_id]["_task"] = task

# main.py — in lifespan shutdown:
for job in _jobs.values():
    t = job.get("_task")
    if t and not t.done():
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t
```

---

### M-5 — Image serving endpoint does not anchor path to job output directory

**File:** `ka11y/api/v1/combined/routes.py:277-290`

```python
valid_paths = {img["path"] for img in contrast_report.get("images", [])}
if path not in valid_paths:
    raise HTTPException(...)
img_path = Path(path)
return FileResponse(str(img_path), ...)
```

**Problem:** The `valid_paths` whitelist only checks that the requested path matches one stored in the backend-generated contrast report. It does **not** verify that the path is actually inside the job's output directory. If a bug elsewhere causes an absolute path outside the output directory to end up in `contrast_report["images"]`, the endpoint will serve it without restriction.

**Fix:** Add a `.resolve()` + `is_relative_to()` check:

```python
job_output_dir = Path(_jobs[job_id]["output_dir"]).resolve()
img_path = Path(path).resolve()
if not img_path.is_relative_to(job_output_dir):
    raise HTTPException(status_code=403, detail="Path is outside the job output directory.")
```

---

## Low Severity

---

### L-1 — Image file existence not validated before calling `readtext`

**File:** `ka11y/text_detector/text_detector.py:197`

```python
detections = self.reader.readtext(image_path)
```

**Problem:** `image_path` is not checked for existence before being passed to EasyOCR. If a download failed silently (zero-byte file, partial write) or the file was deleted between the crawl and the OCR pass, EasyOCR throws a cryptic `cv2.error` or `PIL.UnidentifiedImageError` instead of returning an empty list. The outer `try/except Exception` catches it, but the log message is unclear.

**Fix:**

```python
if not Path(image_path).exists() or Path(image_path).stat().st_size == 0:
    logger.warning(f"[text_detector] Skipping missing/empty file: {image_path}")
    return result
detections = self.reader.readtext(image_path)
```

---

### L-2 — `aiohttp.ClientTimeout(total=30)` does not cap individual chunk reads

**File:** `ka11y/crawler/crawler.py:350-351`

```python
download_session = aiohttp.ClientSession(
    timeout=aiohttp.ClientTimeout(total=30)
)
```

**Problem:** `total=30` limits the total wall-clock time from connection to final byte. A server that deliberately sends 1 byte every 29 seconds can hold the session open almost indefinitely while never exceeding the `total` budget in practice (each individual connection hits 30 s but a keep-alive server resets the clock). This can stall the crawler for well over `_CRAWL_TIMEOUT_SECONDS`.

**Fix:** Add explicit per-socket timeouts:

```python
aiohttp.ClientTimeout(total=30, connect=5, sock_connect=5, sock_read=10)
```

---

### L-3 — `load_image_with_alpha` composites in BGR but comment says "RGBA → RGB"

**File:** `ka11y/utils/text_detector_helper.py:37-49`

```python
if len(img.shape) == 3 and img.shape[2] == 4:
    alpha = img[:, :, 3] / 255.0
    background = np.ones_like(img[:, :, :3]) * 255
    img = (img[:, :, :3] * alpha[..., None] + background * (1 - alpha[..., None])).astype(np.uint8)
```

**Problem:** `cv2.imread` returns BGR, not RGB. The comment implies an RGB conversion, but `img[:, :, :3]` is BGR channels. The composite is applied in BGR space. This is internally consistent (downstream cv2 calls also expect BGR) but the resulting HEX colours derived from alpha-composited images will have R and B channels **swapped** in the final colour report, showing incorrect foreground/background HEX values for PNG images with transparency.

**Fix:** Swap channels before compositing and swap back, or add a clear comment that the operation is intentionally in BGR:

```python
# Convert BGR→RGB for composite, then RGB→BGR for cv2 compatibility
img_rgb = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2RGB)
alpha = img[:, :, 3] / 255.0
background = np.ones_like(img_rgb) * 255
composited = (img_rgb * alpha[..., None] + background * (1 - alpha[..., None])).astype(np.uint8)
img = cv2.cvtColor(composited, cv2.COLOR_RGB2BGR)
```

---

### L-4 — `scan_directory()` processes all images sequentially with no progress feedback to the stage timeout

**File:** `ka11y/text_detector/text_detector.py:395-412`

```python
for idx, image_path in enumerate(image_files, 1):
    result = self.detect_text_in_image(image_path)
    self.results.append(result)
```

**Problem:** The entire OCR scan runs synchronously in a single `asyncio.to_thread` call. For a page with 300+ images, this can take 10–20 minutes and is totally opaque — no progress is reported back to the stage runner. The outer `_STAGE_TIMEOUT_SECONDS = 600` will fire and abandon the OCR results, but 600 seconds of blocking thread time still holds the thread pool slot, preventing other work.

Additionally there is no batching — `self.results` grows unbounded in memory (compounded by bug M-3).

**Fix (minimal):** Log progress every N images so the container logs show it's alive:

```python
if idx % 10 == 0:
    logger.info(f"[text_detector] OCR progress: {idx}/{len(image_files)}")
```

**Fix (proper):** Run OCR on a `ThreadPoolExecutor` with `max_workers=2` to process images in parallel without overloading the CPU.

---

## Edge Cases Reference Table

| Scenario | Which module fails | How it fails | Mitigated? |
|---|---|---|---|
| Site with 400+ images | `scan_directory` + RAM | OOM, job timeout | No |
| Two concurrent audit jobs | `ocrbase.readtext` | Silent PyTorch race | No (H-1) |
| PNG with alpha transparency | `load_image_with_alpha` | Wrong HEX colours in report | No (L-3) |
| EasyOCR returns 2-pt bbox | `bbox_height_rotated` | `IndexError`, detection dropped | No (M-2) |
| Deleted image between crawl and OCR | `readtext` | Cryptic cv2 error swallowed | Partial (L-1) |
| `config.yml` missing in Docker | All modules | Import-time crash, no log | No (H-2) |
| DNS rebinding during audit | SSRF guard | Private IP accessed | No (H-4) |
| Container SIGTERM during crawl | Playwright browsers | Zombie Chrome processes | No (M-4) |
| Site sends 1 byte/sec responses | `aiohttp` download | Session held for 30+ s each | No (L-2) |
| numpy.bool_ in is_bold | `check_wcag_compliance` | Wrong `isinstance` checks downstream | Partial (M-1 + contrast_analyser fix) |
| Job with >30 POST/60 s | Rate limiter | HTTP 429 — expected behaviour | ✓ |
| Non-public URL submitted | `_assert_public_url` | HTTP 400 — expected behaviour | ✓ |
| Malformed URL (no scheme) | Pydantic `AnyUrl` | HTTP 422 — expected behaviour | ✓ |
| contrast_report path traversal | Image endpoint | Path outside job dir served | Partial (M-5) |

---

## Fix Priority Order

```
H-2  config.yml import crash         — breaks startup, fix first
H-1  EasyOCR thread safety           — breaks concurrent usage
H-3  7 browsers per job              — OOM under normal load
H-4  DNS rebinding SSRF gap          — security
M-1  numpy.bool_ from estimate_boldness — already partially fixed
M-2  bbox IndexError                 — drops detections silently
M-3  numpy arrays in RAM             — memory leak per job
M-4  orphaned Playwright on shutdown — resource leak
M-5  image path not anchored         — security hardening
L-1  missing file check before readtext
L-3  BGR/RGB colour swap in alpha composite
L-2  aiohttp chunk read timeout
L-4  OCR batching / progress logging
```
