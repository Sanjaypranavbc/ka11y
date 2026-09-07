# 1. Project Overview & 2. Installation → Entry-Point Trace

## 1. Project Overview

### Package manifest

`ka11y-python/pyproject.toml` (Poetry format):

```toml
[tool.poetry]
name = "ka11y"
version = "0.0.1"
description = "AI Based Web Accessibility Checker"
authors = ["meghana334 <meghanayabaku@gmail.com>"]
readme = "README.md"
package-mode = false
```

**`package-mode = false` is the single most important fact for section 2.** In
Poetry, this tells Poetry "this is an application, not a library to be built
into a wheel/sdist and published." Consequences:

- `poetry build` / `poetry publish` are not meaningful for this project.
- There is **no `[tool.poetry.scripts]` table** (confirmed: `grep -n
  "tool.poetry.scripts" pyproject.toml` returns nothing) — so no
  `console_scripts` entry point is registered anywhere.
- There is no `setup.py` and no `requirements.txt` in `ka11y-python/` (both
  absent — the project is Poetry-only, dependencies pinned via `poetry.lock`).
- **`pip install ka11y` does not install a runnable CLI**, and there is no
  package named `ka11y` published to PyPI that this repository produces. The
  only supported ways to run this code are (a) `poetry install` inside
  `ka11y-python/` followed by running `uvicorn` directly, or (b) the Docker
  image built from `ka11y-python/Dockerfile`.

### What the tool does

`ka11y-python` is the Python half of the ka11y accessibility-audit platform
(the other half, `ka11y-node`, runs axe-core/Puppeteer-based checks in
Node.js — out of scope here per the agreed scope). It is a **FastAPI web
service**, not a command-line tool. Given a URL, it:

1. Launches a pooled headless Chromium browser via Playwright
   (`ka11y/crawler/`) and crawls the target page (optionally following
   internal links up to a configured depth), guarded against SSRF.
2. Captures a structured "universal page" snapshot — DOM, ARIA tree, computed
   styles, screenshots, focus order, media elements, form fields — via an
   injected JS extraction script plus Python-side normalization
   (`ka11y/crawler/universal_page.py`, `ka11y/crawler/optimized/`).
3. Runs that snapshot through a battery of WCAG 2.2 rule auditors:
   - Python rule auditors for media (`accessibility/rules/media/`) and
     non-text content — images/alt text, contrast
     (`accessibility/rules/non_text/`).
   - **Correction to an assumption in the original request**: an earlier,
     unverified pass over this repo (a `git diff` against an unrelated old
     branch, used for a prior security review in this session) suggested
     dedicated modules also exist for reflow, text spacing, resize-text,
     focus-not-obscured, hover/focus content, orientation, forms, target
     size, label-in-name, and pause-stop-hide. **They do not, as of this
     commit** — verified directly via `find`/`git ls-tree HEAD`. Those
     auditors were deliberately removed; `api/v1/combined/constants.py:40-41`
     says so explicitly ("weights for removed stages: axe_core, pipeline,
     form_audit, label_in_name, pause_stop_hide, target_size, text_spacing,
     rendered_layout_audit, sensory_audit"). Their **request/response model
     fields** (`run_label_in_name_audit`, `run_target_size_audit`, etc. in
     `api/v1/models/pipeline.py`) and their **rule-ID routing entries** in
     `api/v1/rules/run_router.py` (mapping WCAG SCs like 2.5.3, 2.2.2, 2.5.8,
     1.4.12, 1.4.4, 1.4.10, 1.3.4, 1.4.13, 2.4.11, 2.4.12 to those flags)
     still exist as dead references to modules that are gone — see
     `07-MODULES-api.md` and `13-EXTENSIBILITY.md` for what actually happens
     when one of those rule IDs is requested.
   - A generic decision-policy pipeline that classifies DOM elements against
     structured evidence and thresholds — `ka11y/accessibility/pipeline/`.
4. Runs OCR (EasyOCR for Latin scripts, PaddleOCR for CJK) over cropped image
   regions to find text embedded in images and measure its contrast —
   `ka11y/text_detector/`, `ka11y/preprocessor/`.
5. Classifies image type (informative/decorative/functional/complex) with a
   CLIP-family model and generates AI alt-text suggestions —
   `ka11y/classifier/`.
6. Combines all of the above (plus results proxied in from the Node service)
   into one report per audited job, persisted to SQLite and served back over
   HTTP as JSON, CSV, PDF, or emailed — `ka11y/api/v1/combined/`,
   `ka11y/store/`, `ka11y/utils/report_*.py`.
7. Exposes everything through a versioned REST API (`/api/v1/...`) built with
   FastAPI routers, with a background job/dispatcher model for long-running
   crawls (see `10-EXECUTION-FLOW.md`).

### Top-level dependencies (from `pyproject.toml`, `[tool.poetry.dependencies]`)

| Dependency | Role |
|---|---|
| `fastapi`, `uvicorn`, `starlette` (transitive) | HTTP API framework + ASGI server |
| `playwright` | Headless Chromium automation — the crawler |
| `pydantic` | Request/response schema validation (v2) |
| `aiohttp`, `httpx` | Async HTTP clients (asset downloads, Node service calls) |
| `bs4` / `beautifulsoup4`, `lxml` | HTML parsing outside the browser (`html_soup.py`) |
| `pillow`, `torch`, `torchvision` (CPU wheel via a pinned `pytorch-cpu` source) | Image tensors for OCR/classification models |
| `easyocr`, `paddleocr`, `paddlepaddle==3.2.2` (exact-pinned, see comment in `pyproject.toml`) | OCR engines — EasyOCR default, PaddleOCR for CJK |
| `transformers`, `accelerate`, `sentence-transformers`, `keybert` | HF models for image classification / alt-text / keyword extraction |
| `google-generativeai` | Gemini API client for AI-assisted checks (media quality, reading level) |
| `deepgram-sdk` | Deepgram transcription API for WCAG 1.2.1 audio/video transcript QA |
| `spacy`, `nltk`, `wordfreq`, `jiwer`, `yake` | NLP: reading-level scoring, keyword/entity extraction, WER for transcript QA |
| `pyyaml` | Loads `config/config.yml`, `config/universal.yml`, i18n YAML |
| `python-dotenv` | Loads `.env` (API keys) at process start |
| `rich` | Colorized structured console logging (`config/logger.py`) |
| `psutil` | Process/resource introspection (crawler timing/limits) |
| `tldextract` | Domain parsing for URL canonicalization / SSRF host checks |
| `sudachipy`, `sudachidict-core` (optional, `japanese` extra) | Japanese tokenization |
| `pytest`, `pytest-asyncio`, `pytest-html` | Test suite (dev) |

A `[[tool.poetry.source]]` pins `torch`/`torchvision` to the CPU-only PyTorch
wheel index (`https://download.pytorch.org/whl/cpu`) — deliberate, to avoid
pulling multi-GB CUDA wheels on a server with no GPU.

---

## 2. Installation → Entry-Point Trace

### What `pip install ka11y` actually does

Nothing useful, for two independent reasons:

1. **No such package is published.** This repository is the source of a
   private application, not a library shipped to PyPI under the name
   `ka11y`. `pip install ka11y` against the public index would either 404 or
   (worse) install an unrelated third-party package that happens to have
   claimed that name — it is not this codebase.
2. **Even installed locally, there's no entry point to run.** If you `cd
   ka11y-python && pip install .`, pip would delegate to the
   `poetry.core.masonry.api` build backend declared in `[build-system]`; with
   `package-mode = false` this project isn't set up to produce a console
   script, so nothing gets placed on `PATH`. There is no `__main__.py`
   anywhere under `ka11y/` either (confirmed: no file by that name in the
   package), so `python -m ka11y` also does not work.

### The two real ways to start this service

**A. Local development (Poetry):**

```bash
cd ka11y-python
poetry install                      # reads pyproject.toml + poetry.lock
poetry run playwright install chromium   # not run automatically by poetry install
uvicorn ka11y.main:app --reload --port 8000
```

`poetry install` resolves and installs the dependency table above into a
virtualenv (or the active environment, since `POETRY_VIRTUALENVS_CREATE=false`
is set in the Docker build — see below) but does **not** install anything
under a `[tool.poetry.scripts]` key because none exists. The only thing that
makes the service runnable is that `uvicorn` (itself one of the declared
dependencies) is now on `PATH` inside that environment, and you invoke it
directly, naming the ASGI app object `ka11y.main:app`.

**B. Docker (what actually ships), `ka11y-python/Dockerfile`:**

```dockerfile
CMD ["uvicorn", "ka11y.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This is the literal, authoritative "entry point" for the service. Preceding
`RUN` steps in the Dockerfile (in order): install OS packages (`ffmpeg`,
`libgl1`, etc. for OpenCV/media), install `poetry==2.3.2`, `poetry install
--only main [-E japanese]` (dependency table above, optionally with the
`sudachipy`/`sudachidict-core` Japanese extra — toggled by build arg
`INSTALL_JAPANESE`), download spaCy models (`ja_core_news_lg` conditionally,
`en_core_web_sm` always) with a retry loop against DNS flakiness, pre-download
NLTK corpora (`punkt`, `punkt_tab`, `averaged_perceptron_tagger_eng`,
`stopwords`) to `/usr/share/nltk_data`, then `playwright install chromium
--with-deps`. Only after all of that does it `COPY ka11y/ ./ka11y/` and `COPY
i18n/ ./i18n/` — application source is copied last deliberately, so a
code-only change doesn't invalidate the expensive dependency/model/browser
layers above it (see the Dockerfile's own comment above the `COPY` step).

### First line of code that executes

Tracing `uvicorn ka11y.main:app`:

1. `uvicorn` (an external package, not part of this codebase) parses
   `ka11y.main:app` as `<module>:<attribute>`, imports the module
   `ka11y.main`, and looks up the attribute `app` on it.
2. Importing `ka11y.main` executes `ka11y-python/ka11y/main.py` **top to
   bottom, at import time** — this is the actual first application code that
   runs (uvicorn's own startup happens first but is not this codebase's
   code). In source order:
   - `main.py:20` — `load_dotenv()` is called immediately at module scope
     (not inside a function), reading a `.env` file from the current working
     directory (or nearest ancestor) into `os.environ`. This is why
     `DEEPGRAM_API_KEY` (per `.env.example`) must exist before anything else
     that reads it runs.
   - `main.py:73` — `logger = setup_logger(name="KAC", tag="main")` — first
     call into another module (`ka11y.config.logger`, see
     `03-MODULES-config-utils.md` §`config/logger.py`). This creates
     `ka11y-python/logs/` on disk (via `os.makedirs`, `logger.py:92`) as a
     **side effect of import**, before any HTTP request has been handled.
   - `main.py:75` — `config = load_config()` — calls into
     `ka11y.utils.config_loader` (see `03-MODULES-config-utils.md`
     §`utils/config_loader.py`), which reads and YAML-parses either
     `config/universal.yml` (repo-root shared config, preferred if present)
     or `ka11y-python/ka11y/config/config.yml` (fallback), cached via
     `functools.lru_cache`.
   - `main.py:137-142` — the `FastAPI(...)` app object is constructed, with
     `lifespan=lifespan` wiring the startup/shutdown hooks defined at
     `main.py:79-134` (see `10-EXECUTION-FLOW.md` for what those do —
     opening the SQLite store, starting the job dispatcher, eviction and
     retention background loops).
   - `main.py:144-160` — middleware is attached in this order: the custom
     `_RateLimitMiddleware` (`main.py:23-56`), the custom
     `_SecurityHeadersMiddleware` (`main.py:59-70`), then Starlette's
     `CORSMiddleware` with a **hardcoded origin allowlist**
     (`main.py:151-156`: `ec2-34-228-40-177.compute-1.amazonaws.com:8080`,
     `a11y.bluecaffeine.in`, `localhost:3001`).
   - `main.py:162` — `app.include_router(router)` mounts the entire API
     surface, defined in `ka11y/api/router.py` (see `01`→`07-MODULES-api.md`).
     This is the last line of the module; after it, `ka11y.main.app` is a
     fully-configured (but not yet "started" — `lifespan` hasn't fired)
     ASGI application object.
3. Uvicorn then takes over: binds the socket, and on actually starting the
   event loop, enters the `lifespan` async context manager
   (`main.py:79-134`), whose `try: yield` body (`main.py:108`) is where the
   app is considered "up" and begins accepting requests.

So: **the very first line of *this codebase's* code to execute is
`load_dotenv()` at `ka11y-python/ka11y/main.py:20`**, triggered transitively
by uvicorn importing the module named on its command line.

### `ka11y/__init__.py` (5 lines) — package marker

```python
# This is a web accessibility checker


__version__: str = "0.0.1"
__author__: str = "Meghana"
```

Executes before `ka11y.main` (Python always initializes a parent package
before importing a submodule of it), but does nothing beyond defining two
module-level string constants — no I/O, no side effects. Not imported by name
anywhere else in the codebase (`__version__`/`__author__` are not read
elsewhere); it exists purely as the package marker.
