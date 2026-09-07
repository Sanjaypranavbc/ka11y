# 4. Module-by-Module Breakdown — Group 1: Config & Utilities

The foundation layer. Nothing here imports from `crawler/`, `accessibility/`,
`api/`, `classifier/`, or `text_detector/` — with the two documented
exceptions noted in `02-ARCHITECTURE.md` (`utils/lang_detector.py` →
`crawler/_ssrf_guard.py`). Every other layer imports from here.

---

## `ka11y/config/logger.py` (166 lines)

**Purpose**: the single structured-logging implementation used by every other
module in the codebase (`setup_logger` is imported dozens of times).

**Imports**: `datetime`, `logging`, `os`, `logging.handlers.RotatingFileHandler`,
`pathlib.Path` (stdlib); `rich.console.Console`, `rich.highlighter.NullHighlighter`,
`rich.logging.RichHandler`, `rich.theme.Theme` (third-party — colorized console
output). No internal ka11y imports (this is a Layer 0 leaf).

**Module-level constants**:
- `SUCCESS_LEVEL = 25` (line 32) — a custom log level between `INFO` (20) and
  `WARNING` (30), registered via `logging.addLevelName` (lines 33-34, guarded
  so re-import doesn't re-register).
- `_THEME` (lines 37-47) — a Rich `Theme` mapping each level name to a color
  style (e.g. `"logging.level.error": "bold red"`).
- `_console` (line 49) — one shared `rich.Console`, `force_terminal=True` (so
  ANSI colors render even when stdout isn't a real TTY, e.g. inside Docker
  logs).
- `_FILE_FMT` (lines 51-54) — the plain-text formatter used for the rotating
  file handler: `"%(asctime)s | %(levelname)-8s | [%(tag)-14s] | %(name)s |
  %(message)s"`.

**Classes**:

- **`KaLogger(logging.LoggerAdapter)`** (lines 59-77) — wraps a stdlib
  `Logger` to prepend a `[TAG]` to every message and add two convenience
  methods.
  - `process(self, msg, kwargs) -> tuple[str, dict]` (lines 66-69): the
    `LoggerAdapter` hook called on every log call. Reads `self.extra["tag"]`
    (defaulting to `"GENERAL"`), merges any per-call `extra` dict over the
    adapter's own `extra`, and returns the message prefixed with a Rich
    markup tag (`[bold cyan]\[TAG][/bold cyan] msg`).
  - `success(self, msg, *args, **kwargs)` (lines 71-73): logs at
    `SUCCESS_LEVEL` with a `✓ ` prefix. Used throughout the codebase for
    "stage completed successfully" messages.
  - `processing(self, msg, *args, **kwargs)` (lines 75-77): logs at `INFO`
    with a `⚙ ` prefix, for "work in progress" messages.

**Functions**:

- `setup_logger(name: str = "KAC", tag: str | None = None) -> KaLogger`
  (lines 83-139) — the factory every module calls. Step by step:
  1. Computes `log_dir` as an **absolute** path:
     `Path(__file__).resolve().parent.parent.parent / "logs"` — i.e.
     `ka11y-python/logs/`, regardless of the process's current working
     directory (line 91).
  2. **Side effect**: `os.makedirs(log_dir, exist_ok=True)` (line 92) —
     creates that directory unconditionally, every time `setup_logger` is
     called (cheap no-op if it already exists). This is the *first*
     filesystem write of the whole application, since `main.py` calls this
     at import time before `load_config()`.
  3. `base = logging.getLogger(name)` — gets (or creates) the underlying
     stdlib logger by name (default `"KAC"` — every call site in this
     codebase uses the same name, so they all share one underlying logger
     with different `tag`s).
  4. **Handlers are attached only once** (`if not base.handlers:` guard,
     line 96) — repeated calls with the same `name` are idempotent, which
     matters because `setup_logger` is called at module-import time in
     dozens of files.
  5. Sets level `DEBUG`, `propagate = False` (so messages don't double-log
     via the root logger).
  6. Attaches a `RichHandler` for colorized console output (lines 101-114).
  7. **Side effect**: computes today's date and attaches a
     `RotatingFileHandler` writing to `logs/{name}_{date}.log`, 5 MB per
     file, 5 backups kept (lines 117-128). If file creation fails (e.g.
     read-only filesystem), the exception is caught and a warning is printed
     directly to `stderr` (lines 129-137) rather than raised — logging setup
     must never crash the app.
  8. Returns `KaLogger(base, {"tag": tag or "GENERAL"})`.

- `log_info` / `log_warning` / `log_error` / `log_debug` / `log_success` /
  `log_processing` (lines 145-166) — thin free-function wrappers
  (`logger.<level>(message)`) kept "for back-compat" per the comment; not
  used by newer code, which calls `logger.info(...)` etc. directly.

**Side effects**: creates `ka11y-python/logs/` on disk; opens/appends a
rotating log file per unique `(name)`. No network calls.

**Used elsewhere**: `setup_logger` is imported by nearly every module in the
codebase (`main.py`, all of `utils/`, `crawler/`, `api/v1/combined/`, rule
auditors, etc.) as the standard way to get a tagged logger.

---

## `ka11y/config/config.yml` (61 lines, not Python — the local fallback config)

Not a module, but documented here because `utils/config_loader.py` and every
`get_*_config` helper in `crawler_settings.py` reads it. Loaded as a plain
dict via `yaml.safe_load`. Top-level keys:

- `input`: default `url`, `max_depth`, `output_dir` for the legacy standalone
  image-crawler script path (see `12-OUTPUT-FILES.md`).
- `directories`: the category subfolder names created under a crawl's image
  output directory (`informative`, `decorative`, `functional/buttons`, etc.)
- `ocr`: base/contrast subfolder names and OCR category folder names.
- `browser`: `ignore_https_errors: true`.
- `crawler.include_data_uris` / `include_invisible` / `scroll_passes`:
  crawl-time tunables.
- `crawler.language.cjk_langs`: the language codes treated as CJK
  (`ja`, `zh`, `zh-CN`, `zh-TW`, `zh-HK`, `ko`) — read by
  `utils/crawler_settings.get_cjk_langs()`.
- `crawler.reporting.max_warning_samples`: cap on sample warnings surfaced
  per rule.
- `crawler.performance.*`: `max_focus_steps`, `max_hover_candidates`,
  `max_ocr_images_per_run` / `_per_page` / `_ceiling` — all read through
  `crawler_settings.py`'s `get_int_config` wrappers.
- `crawl_browser.width` / `height`: viewport size (1920×1080).

**Note**: as documented in `utils/config_loader.py` below, this file is only
used when the repo-root `config/universal.yml` (shared across `ka11y-python`
and `ka11y-node`) does not exist — `universal.yml` takes priority when
present.

---

## `ka11y/utils/__init__.py` (3 lines)

```python
from ka11y.utils.not_implemented import not_implemented
__all__ = ["not_implemented"]
```

Re-exports `not_implemented` so callers can `from ka11y.utils import
not_implemented` instead of the fully-qualified submodule path. No other
logic.

---

## `ka11y/utils/config_loader.py` (35 lines)

**Purpose**: locate and parse the YAML config file (shared `universal.yml` or
local `config.yml`), with caching.

**Imports**: `copy`, `functools.lru_cache`, `pathlib.Path` (stdlib); `yaml`
(third-party, PyYAML). No internal ka11y imports.

**Functions**:

- `_load_config_cached(config_path: str) -> dict` (lines 10-14) — decorated
  `@lru_cache(maxsize=4)`. Opens `config_path`, calls `yaml.safe_load(file)`
  (note: `safe_load`, not the unsafe `yaml.load` — deliberately avoids
  arbitrary Python object deserialization from YAML). The `maxsize=4` cache
  key is the **string** path, so this function is only ever actually
  re-executed for up to 4 distinct paths per process lifetime; subsequent
  calls with the same path return the cached dict object directly (not a
  copy — see next function for why that matters).

- `load_config(config_path: str | None = None)` (lines 17-32) — the public
  entry point.
  1. If no explicit `config_path` is given: computes `repo_root =
     Path(__file__).resolve().parents[3]` — walking up from
     `ka11y-python/ka11y/utils/config_loader.py` four levels lands at the
     **monorepo root** (`ka11y-project/ka11y/`), and checks for
     `<repo_root>/config/universal.yml` — the config shared between
     `ka11y-python` and `ka11y-node`.
  2. Falls back to `<ka11y-python>/ka11y/config/config.yml` (i.e.
     `Path(__file__).resolve().parents[1] / "config" / "config.yml"`) if
     `universal.yml` doesn't exist.
  3. Calls `_load_config_cached(str(config_path.resolve()))` and wraps the
     result in `copy.deepcopy(...)` before returning it — **this is the
     important line (32)**: because the underlying dict is `lru_cache`d and
     shared, returning it directly would let one caller's in-place mutation
     (`config["crawler"]["performance"]["max_ocr_images_per_run"] = 10`)
     leak into every other caller. The deep copy makes each `load_config()`
     call return an independently-mutable dict.

**Module-level state**: `config = load_config()` (line 35) — evaluated once
at import time, giving a module-level default config object. (Most callers
instead call `load_config()` themselves — via `crawler_settings.py`'s
wrappers — rather than importing this attribute directly, since each call
returns a fresh deep copy.)

**Side effects**: one file read + YAML parse per unique path (then cached).
No network, no writes.

**Used elsewhere**: `main.py` (`config = load_config()` at
`main.py:75`), `utils/crawler_settings.py` (every `get_*` helper), and
transitively by every module that calls those helpers.

---

## `ka11y/utils/crawler_settings.py` (261 lines)

**Purpose**: typed, defaulted accessors over the raw YAML config dict, plus
one non-trivial algorithm (`select_ocr_candidate_paths`) for picking which
images get OCR'd within a fixed budget.

**Imports**: `pathlib.Path`, `typing.Any/Iterable/Sequence` (stdlib);
`ka11y.utils.config_loader.load_config` (internal).

**Functions**:

- `_get_nested(config: dict, path: Sequence[str], default: Any) -> Any`
  (lines 9-15) — walks a dict by a sequence of keys (`config["crawler"]["performance"]["max_focus_steps"]`
  style), returning `default` the moment a key is missing or a non-dict is
  encountered partway through.

- `get_config_value(*path: str, default: Any = None) -> Any` (lines 18-20) —
  calls `load_config()` fresh (so always sees the latest deep copy) then
  `_get_nested`.

- `get_int_config(*path, default=None, minimum=None) -> int | None`
  (lines 23-35) — `get_config_value` + `int(...)` coercion; returns `None` on
  a non-coercible value (rather than raising); clamps to `minimum` if given.

- `get_cjk_langs() -> list[str]` (lines 38-48) — reads
  `crawler.language.cjk_langs`; falls back to a hardcoded 6-language list
  (`ja, zh, zh-CN, zh-TW, zh-HK, ko`) if the config value is missing or not a
  list, so the CJK-detection behaviour never silently disappears due to a
  config typo.

- `get_check_config_value(check_key, *path, default=None)` (lines 51-52) —
  shorthand for `get_config_value("checks", check_key, *path, ...)`.

- `get_localized_check_terms(check_key, term_key) -> list[str]` (lines 55-66)
  — reads a per-check term list that may be either a flat list or a
  `{lang: [terms]}` dict (in which case every language's terms are
  flattened and de-duplicated via `dict.fromkeys`).

- `get_max_warning_samples()` / `get_max_focus_steps()` /
  `get_max_hover_candidates()` (lines 69-96) — thin `get_int_config` wrappers
  with hardcoded defaults (3, 100, 20 respectively) matching `config.yml`.

- `get_max_ocr_images_per_run() -> int | None` (lines 99-106) — legacy
  single-page OCR budget (`crawler.performance.max_ocr_images_per_run`).

- `get_max_ocr_images_per_page() -> int` (lines 109-121) — the newer
  per-page budget for multi-page crawls; falls back to the legacy per-run
  value, then to a hardcoded `60`, if unset. Docstring explains the reasoning:
  scaling the OCR budget as `per_page * num_pages` (rather than one shared
  pool) prevents a child page's images from starving because a sibling page
  used up the run's OCR budget first.

- `get_max_ocr_images_ceiling() -> int` (lines 124-131) — hard cap
  (default 3000) regardless of page count, so a very deep crawl can't run
  unbounded OCR.

- `build_text_spacing_cjk_selector_css() -> str` (lines 134-155) — generates
  a CSS string (not a selector list) that disables `letter-spacing` /
  `word-spacing` overrides for CJK-language elements (via `:lang(ja)` and
  `[lang="ja"]` selectors for every configured CJK language and their
  descendants), because WCAG 1.4.12 (Text Spacing)'s letter/word-spacing
  requirements don't apply to CJK scripts (no inter-word spaces, built-in
  inter-character spacing). Returned as literal CSS text with an explanatory
  comment baked in, injected into the page for the text-spacing rendered
  evaluator (`accessibility/rendered/evaluators/text_spacing.py`, see
  `05-MODULES-pipeline.md`... actually cross-referenced in
  `06-MODULES-rules.md`).

- `select_ocr_candidate_paths(images, *, limit, fair_per_page=False) ->
  tuple[list[str], list[str]]` (lines 158-261) — the most complex function in
  this file. Given an iterable of image-like objects (duck-typed via
  `getattr`, so it works with dataclasses or dicts), returns
  `(selected_paths, skipped_paths)` within `limit`:
  1. **Dedup by resolved path** (line 180-183): `Path(path).resolve()`
     absolute-izes and dedupes so the same file referenced twice isn't OCR'd
     twice.
  2. **Dedup low-priority duplicate assets by source URL** (lines 195-206):
     for decorative/logo images specifically, builds an `asset_key =
     f"{classification}:{sub_type}:{src}"` and skips repeats — carousels /
     duplicated hero banners otherwise burn the OCR budget on identical
     content.
  3. **Priority ranking** (lines 208-223): assigns an integer priority 0
     (best, buttons) through 7 (worst, unclassified) based on
     `is_button`/`sub_type`, `is_text_image`, `classification` (functional >
     informative), `is_complex`, `is_logo`, `is_decorative` — the intent
     being to spend the limited OCR budget on images most likely to contain
     meaningful text.
  4. Sorts by `(priority, original_index)` (stable within a priority tier)
     and returns everything if under `limit`.
  5. If over `limit` and `fair_per_page=False`: simple truncation —
     `ordered[:limit], ordered[limit:]`.
  6. If `fair_per_page=True` (multi-page crawls): buckets the
     globally-ranked paths by source page into `OrderedDict[str,
     deque[str]]` (lines 242-244), then round-robins one image per page per
     round until `limit` is reached (lines 246-257) — so each page
     contributes its own top images rather than one page's images
     dominating purely by having more of them.

**Side effects**: none beyond reading config (via `load_config()`, itself
cached) and `Path.resolve()` (stats the filesystem to resolve symlinks —
technically an I/O call, but read-only and side-effect-free).

**Used elsewhere**: extensively by `api/v1/combined/stages.py` and the image
audit pipeline (OCR budget/selection), and by rendered evaluators needing CJK
detection or config-driven thresholds.

---

## `ka11y/utils/crawler_timing.py` (168 lines)

**Purpose**: append one Markdown-table row per crawler invocation to
`<output_dir>/crawler_timings.log`, and mirror the same row into the durable
SQLite `stage_timings` table.

**Imports**: `os`, `threading`, `time`, `contextlib.asynccontextmanager`,
`contextvars.ContextVar`, `pathlib.Path`, `typing.Callable/Optional` (stdlib).
No internal ka11y imports at module scope (the `ka11y.store.repo` import at
line 104 is deferred/local, to avoid a circular-import edge — `store` doesn't
need to depend on `utils` at import time).

**Module-level state**:
- `_run_id_ctx: ContextVar[Optional[str]]` (line 35) — an `asyncio`-aware
  context variable holding the current run's ID, set once per job by
  `set_run_id()` and automatically inherited by every `asyncio` task spawned
  from that context (the mechanism that lets deeply-nested crawler calls
  know "which run am I part of" without threading a parameter through every
  function signature).
- `_W_CRAWLER`, `_W_SCOPE`, `_W_PAGES`, `_W_DURATION`, `_W_STATUS` (lines
  46-50) — fixed column widths for the Markdown table.
- `_HEADER` (lines 52-57) — the pre-rendered Markdown table header + divider
  row.
- `_DEFAULT_FILENAME = "crawler_timings.log"` (line 59).
- `_locks: dict[str, threading.Lock]`, `_registry_lock` (lines 62-63) — a
  registry of per-file locks (see `_lock_for` below) so concurrent
  `asyncio.gather`'d stages don't interleave partial writes into the same
  file.

**Functions**:

- `set_run_id(run_id)` (lines 38-39) — sets `_run_id_ctx`.
- `_files_enabled()` (lines 42-43) — reads env var `KA11Y_TELEMETRY_FILES`
  (default `"1"`); returns `False` only if explicitly set to `"0"` — the
  opt-out switch for the human-readable log files (SQLite mirroring still
  happens regardless).
- `_lock_for(path: str) -> threading.Lock` (lines 66-72) — get-or-create a
  lock keyed by file path, itself guarded by `_registry_lock` so the
  dict-mutation-then-lookup is race-free.

**Class `CrawlerTimingLogger`** (lines 75-131):
- `__init__(self, output_dir, filename=_DEFAULT_FILENAME)` (lines 78-86):
  computes `self.path = Path(output_dir) / filename`; if telemetry files are
  disabled, returns early (no filesystem touch at all). Otherwise, under the
  per-path lock: **creates the parent directory** (`self.path.parent.mkdir(parents=True,
  exist_ok=True)`, line 83) and writes the header line **only if the file
  doesn't exist yet or is empty** (lines 85-86) — so the first crawler to
  finish in a run creates the file with its header; subsequent
  `CrawlerTimingLogger` instances for the same `output_dir` (one is
  constructed per `time_crawler` call) see the file already populated and
  skip re-writing the header.
- `record(self, crawler, scope="", duration_s=0.0, status="ok", pages=None)`
  (lines 88-130): truncates `scope` to the column width with an ellipsis if
  needed (lines 96-98); if `_run_id_ctx` is set, best-effort inserts a
  mirrored row into the durable store via `repo.insert_timing(...)` wrapped
  in a bare `except Exception: pass` (lines 102-118, "fire-and-forget; never
  raises"); if file telemetry is enabled, formats a fixed-width row string
  and appends it under the per-path lock (lines 120-130).

**Function `time_crawler`** (lines 133-168, `@asynccontextmanager`):
usage pattern is `async with time_crawler(output_dir, "universal_snapshot",
scope=url): await do_the_crawl()`. Records the elapsed wall time
(`time.perf_counter()` before/after), sets `status="error"` and re-raises if
the wrapped block throws (so a failing crawler still gets a timing row, with
its actual error surfaced up the stack), and optionally calls a
`pages_getter` callable afterward to record a page count — any exception
from `pages_getter` itself is swallowed (lines 163-166) so a broken counter
never breaks the actual audit.

**Side effects**: creates `<output_dir>/crawler_timings.log`; appends to it;
best-effort SQLite insert via `store.repo`.

**Used elsewhere**: wrapped around every crawler invocation inside
`api/v1/combined/stages.py`.

---

## `ka11y/utils/gmail_sender.py` (156 lines)

**Purpose**: send email via Gmail SMTP with an App Password, supporting
attachments (adapted from a standalone `gmail_smtp` module per the module
docstring).

**Imports**: `os`, `smtplib`, `email.mime.application.MIMEApplication`,
`email.mime.multipart.MIMEMultipart`, `email.mime.text.MIMEText`,
`typing.Optional/Sequence/Tuple/Union` (stdlib); `ka11y.config.logger.setup_logger`
(internal).

**Module-level constants**: `logger` (line 33); `Attachment` type alias
(`Tuple[str, Union[str, bytes], str]` — filename, content, MIME subtype,
line 37); `_PLACEHOLDERS` (line 41) — the two literal sentinel strings
shipped in `.env` templates (`"your_email@gmail.com"`,
`"your_16_digit_app_password"`), used to detect an unconfigured (vs.
misconfigured) sender.

**Class `GmailSender`** (lines 44-156):
- `__init__(self, smtp_server=None, smtp_port=None, sender_email=None,
  sender_password=None)` (lines 47-57): each parameter falls back to an env
  var if not passed explicitly — `SMTP_SERVER` (default `smtp.gmail.com`),
  `SMTP_PORT` (default `587`), `SENDER_EMAIL`, `SENDER_PASSWORD`. Reads
  `os.getenv` directly (side effect: environment read).
- `is_configured(self) -> bool` (lines 59-69): returns `False` if either
  `sender_email` or `sender_password` is falsy or contains one of the
  `_PLACEHOLDERS` strings. Used by callers to skip sending silently.
- `validate_credentials(self) -> None` (lines 71-84): the strict version —
  raises `ValueError` with a specific, actionable message if email or
  password is missing/placeholder. Called at the top of `send_email`.
- `send_email(self, receiver_email, subject, body_text, body_html=None,
  attachments=None) -> bool` (lines 86-155):
  1. Calls `validate_credentials()` (raises if not configured).
  2. Raises `ValueError` if `receiver_email` is empty.
  3. Builds a `MIMEMultipart("mixed")` outer message (so attachments and the
     text/html body coexist — comment at lines 100-103 explains why `mixed`
     rather than `alternative` was needed once attachments were added), sets
     `From`/`To`/`Subject`.
  4. Builds a nested `MIMEMultipart("alternative")` body with a plain-text
     part always, and an HTML part if `body_html` is given.
  5. For each `(filename, content, subtype)` in `attachments`: encodes `str`
     content to UTF-8 bytes (bytes content, e.g. a PDF, passed through
     as-is), wraps in `MIMEApplication`, sets `Content-Disposition:
     attachment; filename=...`.
  6. **Side effect (network)**: connects via `smtplib.SMTP_SSL` if
     `smtp_port == 465`, else `smtplib.SMTP` + `starttls()` (the 587/STARTTLS
     path); logs in with the sender credentials; calls
     `server.send_message(msg)`.
  7. On `SMTPAuthenticationError` / `SMTPConnectError` / any other exception:
     logs a specific, diagnostic error message (lines 141-154, e.g. pointing
     at "2-Step Verification... App Password, not the account password" for
     auth failures) and **re-raises** — unlike most of this codebase's
     `utils/report_*` wrappers, `GmailSender.send_email` itself does not
     swallow errors; its callers (`report_mail.py`) do.

**Side effects**: reads env vars; makes an outbound SMTP network connection.

**Used elsewhere**: `utils/report_mail.py` (the sole caller).

---

## `ka11y/utils/html_soup.py` (47 lines)

**Purpose**: a `BeautifulSoup` factory that prefers `lxml` but gracefully
falls back to the stdlib `html.parser` if `lxml` isn't installed, fixing a
class of `FeatureNotFound` crashes the docstring says previously broke three
checks silently.

**Imports**: `typing.Any`; `bs4.BeautifulSoup` (third-party).

**Module-level state**: `_PARSER: str` (lines 24-30) — resolved once at
import time by attempting `import lxml` inside a `try/except`; set to
`"lxml"` on success, `"html.parser"` on any exception.

**Functions**:
- `best_parser() -> str` (lines 33-35): returns the resolved `_PARSER` name
  (for diagnostics/tests).
- `make_soup(html: Any) -> BeautifulSoup` (lines 38-47): calls
  `BeautifulSoup(html or "", _PARSER)`; if that itself raises at *call* time
  (e.g. `lxml` importable but its C extension fails to load), falls back to
  `BeautifulSoup(html or "", "html.parser")` — a second, call-time safety net
  on top of the import-time probe.

**Side effects**: none beyond the one-time import probe.

**Used elsewhere**: the consistent-navigation (3.2.3), consistent-identification
(3.2.4), and unusual-words (3.1.3) checks referenced in the module docstring
(these live in `ka11y-node`, not `ka11y-python` — worth noting this module's
docstring describes fixing a Node-side... actually re-reading: the docstring
says "Several auditors parsed HTML" generically; the actual Python callers
are auditors under `accessibility/rules/` that need to parse raw HTML
strings, e.g. media/quality_engine.py-style text extraction).

---

## `ka11y/utils/lang_detector.py` (199 lines)

**Purpose**: detect a page's primary language (`en` or `ja`) by fetching just
the `<html lang="">` attribute — used when the audit request specifies
`lang: "auto"`.

**Imports**: `asyncio`, `logging`, `threading`, `time`, `typing.Optional/Set`,
`urllib.parse.urljoin/urlparse` (stdlib); `httpx`, `bs4.BeautifulSoup`
(third-party); `ka11y.crawler._ssrf_guard._host_is_blocked` (internal — the
one documented "layering violation," reusing the crawler's SSRF classifier).

**Module-level constants**: `_SUPPORTED_LANGS = {"en", "ja"}` (line 45);
`_DEFAULT_LANG = "en"` (line 47); `_MAX_BYTES = 16_384` (line 50, caps the
download to 16 KB — enough for the `<html>` open tag); `_TIMEOUT = 10.0`;
`_MAX_REDIRECTS = 5`; `_HEADERS` (a realistic desktop-Chrome `User-Agent`,
lines 54-60 — some sites block requests with no/bot-like UA strings);
`_LANG_CACHE_TTL_SECONDS = 600.0`; `_LANG_CACHE: dict[str, tuple[float,
str]]` and `_LANG_CACHE_LOCK` (lines 65-67) — a bounded (see `_cache_put`,
capped at 4096 entries then cleared) in-memory, per-process, per-**host**
result cache.

**Functions**:
- `_cache_get(host) -> Optional[str]` / `_cache_put(host, lang) -> None`
  (lines 70-87): straightforward TTL cache reads/writes guarded by
  `_LANG_CACHE_LOCK`.
- `_safe_fetch_head(url) -> Optional[bytes]` (lines 90-133) — the security-
  critical function (see the module docstring's "Security (N-1)" note): this
  runs **before** the Playwright browser (and its own SSRF-guarded browser
  context) exists, so it re-implements SSRF protection independently.
  1. Opens an `httpx.AsyncClient` with `follow_redirects=False` (line 100) —
     deliberate, so redirects are inspected one hop at a time rather than
     followed blindly.
  2. Loop up to `_MAX_REDIRECTS + 1` times: extracts the hostname of the
     *current* URL, and calls `await asyncio.to_thread(_host_is_blocked,
     host)` (line 105) — runs the (blocking, DNS-resolving)
     `_host_is_blocked` check off the event loop; if blocked, logs a warning
     and returns `None` immediately, **before making the HTTP request**.
  3. Streams the response (`client.stream("GET", current)`); if it's a
     redirect, extracts the `Location` header, resolves it against the
     current URL with `urljoin`, and loops back to step 2 to re-validate the
     *new* host before following it — this is exactly the redirect-time SSRF
     check that (per the earlier security review in this conversation) the
     Node crawler was found to be missing; this Python module already has
     it.
  4. On a non-redirect response: `raise_for_status()`, then streams up to
     `_MAX_BYTES` in 4096-byte chunks and returns the concatenated bytes.
  5. Falls through to `return None` if the loop exhausts `_MAX_REDIRECTS`
     without resolving.
- `detect_page_language(url) -> str` (lines 136-198) — the public entry
  point:
  1. Checks the per-host cache first; returns immediately on a hit.
  2. Calls `_safe_fetch_head(url)`; on `None` (blocked/failed), caches and
     returns `_DEFAULT_LANG`.
  3. Parses the bytes with `BeautifulSoup(html_bytes, "html.parser")`
     (stdlib parser — no `lxml` dependency needed for this small a document),
     finds the `<html>` tag, reads its `lang` attribute.
  4. Normalizes BCP-47 (`"ja-JP"` → `"ja"` via `.split("-")[0]`).
  5. Returns the primary subtag if it's in `_SUPPORTED_LANGS`, else
     `_DEFAULT_LANG` — either way, caches the result by host before
     returning.
  6. Wraps the whole body in `try/except Exception` (lines 150-198) so any
     unexpected failure (malformed HTML, encoding error, etc.) degrades to
     `_DEFAULT_LANG` with a logged warning rather than propagating.

**Side effects**: outbound HTTP GET to the audited URL's host (and any
redirect targets, each independently SSRF-checked); reads/writes the
in-memory language cache; logs via the stdlib `logging` module (not the
`ka11y` `KaLogger` — note `logger = logging.getLogger(__name__)` at line 41,
inconsistent with the rest of the codebase's `setup_logger` convention).

**Used elsewhere**: the combined-audit runner (`api/v1/combined/`) when the
requested `lang` is `"auto"`.

---

## `ka11y/utils/not_implemented.py` (66 lines)

**Purpose**: a decorator marking a function/coroutine as deliberately
unimplemented, raising a clear `NotImplementedError` with the fully-qualified
name if called — used as a placeholder for planned-but-not-yet-built checks.

**Imports**: `inspect`, `functools.wraps`,
`typing.Any/Callable/ParamSpec/TypeVar/overload` (stdlib). No internal
imports.

**Functions**:
- `_build_message(target, reason) -> str` (lines 11-15): formats
  `"<module>.<qualname> is not implemented yet[: reason]."`.
- `not_implemented(func=None, /, *, reason=None)` (lines 28-65) — a decorator
  supporting both `@not_implemented` (bare) and `@not_implemented(reason=
  "...")` (parametrized) usage via the two `@overload` signatures declared
  above it (lines 18-25, type-checking hints only, no runtime effect).
  Internally defines `decorator(target)` which:
  - Detects `inspect.iscoroutinefunction(target)` and produces either an
    `async def async_wrapper` or a sync `def wrapper`, both decorated with
    `@wraps(target)` (preserves `__name__`/`__doc__`/etc.) and both simply
    `raise NotImplementedError(message)` when called — the wrapped function's
    original body is never reachable.
  - Stamps `__not_implemented__ = True` and `__not_implemented_reason__ =
    reason` attributes onto the wrapper (introspectable by tooling/tests
    that want to enumerate stub functions).

**Side effects**: none (pure decorator machinery).

**Used elsewhere**: re-exported via `utils/__init__.py`; used to stub out
rule checks or endpoints not yet implemented (grep the codebase for
`@not_implemented` to find current stubs — none appear in the groups
documented so far, so this is infrastructure for future/in-progress work).

---

## `ka11y/utils/report_csv.py` (115 lines)

**Purpose**: server-side CSV builder for the combined findings report —
deliberately a byte-for-byte port of the frontend's `buildFindingsCsv`
(`ka11y-ui/src/lib/wcagAudit.ts`) so the emailed CSV and the browser
"Download CSV" button produce identical output.

**Imports**: `typing.Any/Dict/List/Sequence`. No internal ka11y imports (pure
function, no logging even).

**Functions**:
- `_csv_escape(value: Any) -> str` (lines 26-31): mirrors the TS
  `csvEscape` — wraps a field in double quotes and doubles any embedded `"`
  if the field contains `"`, `,`, or `\n`; otherwise returns it unmodified.
  Deliberately hand-rolled instead of using the stdlib `csv` module because
  `csv.writer` emits CRLF line endings and a trailing blank row, both of
  which would make this output byte-differ from the TS version (module
  docstring, lines 10-18).
- `_csv_section(title, headers, rows) -> str` (lines 34-40): builds one
  labeled section — a title line, a comma-joined header row, then one
  comma-joined row per data row — joined with `\n`.
- `_page_url_of(finding, fallback) -> str` (lines 43-47): reads
  `finding["element"]["page_url"]` if present, else returns `fallback` (the
  overall site URL) — used to populate a "Page URL" column on multi-page
  reports.
- `build_findings_csv(report: Dict) -> str` (lines 50-115) — the public
  entry point:
  1. Determines `multi_page = len(report["pages_scanned"]) > 1` — matches
     exactly how the frontend's page-selector UI decides whether to show a
     page column, so the two stay in sync (comment lines 55-56).
  2. Builds three sections — Violations (`WCAG SC, Severity, Level, Reason,
     Suggested Fix[, Page URL]`), Needs Review (`WCAG SC, Criterion, Level,
     Reason[, Page URL]`), Passes (`WCAG SC, Criterion, Level[, Page URL]`)
     — each via `_csv_section`.
  3. Joins them with a single blank line between sections and none after the
     last (`"\n".join([violations_section, "", needs_review_section, "",
     passes_section])`, lines 112-114).

**Side effects**: none — pure string transformation, no I/O.

**Used elsewhere**: `utils/report_mail.py` (attaches the CSV to the report
email).

---

## `ka11y/utils/report_mail.py` (102 lines)

**Purpose**: compose and send the "your accessibility report is ready" email
after a deep crawl finishes — deep crawls run longer than a browser tab will
wait/poll, so the result is delivered by email instead.

**Imports**: `typing.Any/Dict/Optional`, `urllib.parse.urlparse` (stdlib);
`ka11y.config.logger.setup_logger`, `ka11y.utils.gmail_sender.GmailSender`,
`ka11y.utils.report_csv.build_findings_csv` (internal).

**Module-level constants**: `logger` (line 23); `_CSV_FILENAME =
"a11y-findings.csv"`, `_PDF_FILENAME = "a11y-findings.pdf"` (lines 28-29 —
matching the filename the frontend's Download button produces, so the
attachment and the browser download are indistinguishable to the user).

**Functions**:
- `_body(site_url, summary, pages_scanned) -> str` (lines 32-43): plain-text
  email body — scan URL, page count, and the violations/needs-review/passes/
  score counts pulled from the report's `summary` dict.
- `send_report_email(to_email, report, job_id=None, pdf_bytes=None) -> bool`
  (lines 46-101) — the public entry point:
  1. Returns `False` immediately if `to_email` is falsy.
  2. Instantiates `GmailSender()`; if `not sender.is_configured()`, logs a
     warning naming the missing env vars and returns `False` — **does not
     raise**, so a missing SMTP config never turns a successful audit into a
     reported failure (module docstring's core guarantee).
  3. Builds `attachments`: the PDF first (if `pdf_bytes` provided — omitted
     rather than fatal if PDF rendering failed upstream), then always the
     CSV via `build_findings_csv(report)`.
  4. Calls `sender.send_email(...)` with subject `"Accessibility report —
     {host}"` (host parsed from the site URL).
  5. Wraps the whole body in `try/except Exception` (lines 59-101) — any
     failure (SMTP down, bad credentials, etc.) is logged with the
     job ID/recipient/exception type and message, and the function returns
     `False` rather than propagating.

**Side effects**: triggers the SMTP send in `gmail_sender.py` (network);
otherwise none.

**Used elsewhere**: called from the combined-audit runner
(`api/v1/combined/runner.py`) after a job completes, when the request
specified a notification email.

---

## `ka11y/utils/report_pdf.py` (715 lines)

**Purpose**: render the same three-section findings report as a printable
PDF, using a leased Chromium page from the existing crawler browser pool
(no new dependency, no extra browser process — module docstring).

**Imports**: `base64`, `io`, `math`, `re`, `html.escape`, `pathlib.Path`,
`typing.*`, `urllib.parse.parse_qs/unquote/urlparse` (stdlib);
`ka11y.config.logger.setup_logger` (internal); **deferred** imports inside
functions: `ka11y.store.assets.get_asset` (line 413), `ka11y.crawler.browser_pool.get_pool`
(line 681), `PIL.Image` (line 434) — deferred to avoid heavy/optional imports
at module load time and to sidestep circular-import risk with `store`/`crawler`.

**Module-level constants** (lines 33-115): the same brand colors as the
frontend's `globals.css` (`_C_VIOLATION`, `_C_REVIEW`, `_C_PASS`, `_C_TEAL`,
`_C_TEAL_DARK`, `_LEVEL_COLORS`) so the PDF's charts visually match the
dashboard; `_MAX_ROWS_PER_SECTION = 200` (caps each table section — a
multi-thousand-row PDF is neither readable nor cheap to render, docstring
lines 40-42); `_CSS` — a full print stylesheet (A4 landscape, table
header-repeat-across-pages, avoid-page-break rules, thumbnail image sizing);
`_THUMB_W, _THUMB_H = 190, 130`; `_IMAGE_BUDGET_BYTES = 6_000_000` (caps
total inlined-thumbnail size — base64 inflates ~33% and Gmail rejects
messages over 25 MB, so thumbnails get a conservative sub-budget, comment
lines 400-403); `_ASSET_URL_RE` (regex matching `/api/v1/assets/(\d+)`).

**Chart-building functions** (pure string/SVG builders, no I/O):
- `_legend(items) -> str` (lines 118-124): color-swatch + label + value
  legend row, shared by every chart.
- `_donut(segments) -> str` (lines 127-159): a donut chart built from
  concentric-circle `stroke-dasharray` arcs rather than computed arc paths
  ("far less trigonometry to get wrong," docstring line 131) — one `<circle>`
  per segment, offset by the running total of prior segments' arc length.
- `_gauge(score) -> str` (lines 162-180): a semicircular score gauge
  matching the dashboard's `PerformanceGauge` component, using a fixed SVG
  arc path with a `stroke-dasharray` proportional to `score`.
- `_level_bars(breakdown) -> str` (lines 183-222): grouped bar chart —
  3 bars (violations/needs_review/passes) per WCAG level (A/AA/AAA), scaled
  to the max value across all bars (`peak`).
- `_criteria_bars(criteria) -> str` (lines 225-254): horizontal bar chart of
  the top-N most-failed criteria, bar color keyed by WCAG level via
  `_LEVEL_COLORS`, label truncated to 30 chars with an ellipsis.

**Data-shaping functions**:
- `_level_breakdown(report) -> List[Dict]` (lines 257-270): reads
  `report["summary"]["by_level"]` and reshapes it into the
  `[{level, violations, needs_review, passes}, ...]` list `_level_bars`
  expects, for each of A/AA/AAA (defaulting missing counts to 0).
- `_top_criteria(report, limit=8) -> List[Dict]` (lines 273-299): "mirror of
  the dashboard's `getTopFailingCriteria`" — builds a `{sc: {level, label}}`
  metadata map by scanning all three finding lists once, then reads
  `summary["by_wcag_sc"]` for counts, filters to `count > 0`, sorts
  descending, truncates to `limit`.
- `_pages_table(report) -> str` (lines 302-338): per-page summary table
  (first 40 pages, with a "Showing 40 of N" note if truncated).
- `_charts(report) -> str` (lines 341-386): composes all four charts (donut
  overview, score gauge, level-breakdown bars, top-criteria bars) into the
  `.charts` grid, each wrapped by the local `card(title, body, wide=False)`
  closure.

**Class `_Raw(str)`** (lines 389-390): a `str` subclass used purely as a type
marker — a table cell wrapped in `_Raw` is known to already be safe HTML and
is not re-escaped by `_row_html` (contrast with plain `str` cells, which are
always passed through `html.escape`).

**Element-image functions**:
- `_src_to_path(src) -> Optional[str]` (async, lines 407-428): maps a report
  image `src` (as stored in a finding) back to a local filesystem path.
  Handles three cases: `/api/v1/assets/{id}` → look up via
  `store.assets.get_asset(id)` and return its `abs_path`; the legacy
  `/api/v1/...?path=...` route → URL-decode the `path` query param; anything
  starting with `http(s)://` or `data:` → returns `None` (**deliberately
  never fetches remote images while rendering**, per the section-header
  comment at lines 393-397, since Chromium renders via `set_content()` with
  no base URL / API credentials, so those srcs would fail anyway and remote
  fetches are avoided as unnecessary I/O + a potential SSRF surface).
- `_thumbnail_data_uri(path) -> Optional[Tuple[str, int]]` (lines 431-446):
  opens the image with Pillow, converts to RGB/L if needed, downsizes to
  `_THUMB_W × _THUMB_H` via `Image.thumbnail` (preserves aspect ratio),
  re-encodes as JPEG quality 72, base64-encodes, returns
  `(f"data:image/jpeg;base64,{encoded}", len(encoded))`. Any exception
  (corrupt image, unsupported format) is caught and returns `None` — "a bad
  crop must not sink the whole PDF" (line 445).
- `_collect_images(report, limit) -> Dict[str, str]` (async, lines 449-489):
  gathers up to `limit` findings' worth of `element.image_src` values
  (deduped), then for each resolves the path and builds a thumbnail,
  stopping early once `_IMAGE_BUDGET_BYTES` is spent (with an info log
  noting how many thumbnails made it in). Returns a `{src: data_uri}` map.
- `_element_cell(finding, images) -> _Raw` (lines 492-518): builds the
  "Element" table cell — an `<img>` thumbnail (if one was resolved) plus the
  image's display filename underneath (`image_reference` if the finding
  carries one, else derived from the URL/`path=` query param).

**Table-building functions**:
- `_row_html(cells) -> str` (lines 521-530): renders one `<tr>`; a `_Raw`
  cell is inserted verbatim, anything else is `str()`-coerced and
  HTML-escaped (careful to render `0` as `"0"` rather than blank — comment
  lines 522-523 note a naive `str(c or "")` would wrongly blank out a
  legitimate zero count).
- `_table(title, headers, rows, total) -> str` (lines 533-553): renders one
  full `<section>` with heading, table, and (if `total > len(rows)`, i.e.
  truncated by `_MAX_ROWS_PER_SECTION`) a note pointing to the attached CSV
  for the complete data.
- `_page_url_of(finding, fallback)` (lines 556-560): identical logic to the
  same-named function in `report_csv.py` (not shared/imported — duplicated).

**Top-level builders**:
- `build_report_html(report, images=None) -> str` (lines 563-671): the
  full HTML document — header cards (violations/needs review/passes/score/
  pages), the four charts, the per-page table, then the three findings
  tables (Violations/Needs Review/Passes), each row's Element column built
  via `_element_cell`. All text fields are `html.escape`d individually as
  they're placed into cells; the document itself has no external
  dependencies (charts are inline SVG, images are inline data URIs) — it is
  fully self-contained, matching the PDF-rendering requirement of no network
  access from within Chromium's `set_content()`.
- `build_report_pdf(report: Dict) -> Optional[bytes]` (async, lines
  674-715) — the actual entry point called by the mailer:
  1. **Side effect**: `images = await _collect_images(...)` — resolves and
     base64-encodes thumbnails (may hit the SQLite asset store and read
     files from disk).
  2. `html = build_report_html(report, images)`.
  3. Leases a browser context from the shared pool
     (`ka11y.crawler.browser_pool.get_pool()`, `pool.lease_context()`),
     opens a new page, calls `page.set_content(html, wait_until="load")`,
     then `page.pdf(format="A4", landscape=True, print_background=True,
     margin={...})` — **side effect**: drives a real headless Chromium
     render.
  4. Always closes the page in a `finally` block.
  5. On any exception anywhere in this process, logs the error and returns
     `None` rather than raising — so a PDF-rendering failure degrades to
     "email sent with CSV only," never to "email not sent at all."

**Side effects**: reads asset files from disk via `store.assets`; leases a
Chromium browser page (via the shared pool — no new process); no direct
network calls (deliberately refuses to fetch remote image `src`s).

**Used elsewhere**: `api/v1/combined/runner.py` calls `build_report_pdf`
before calling `report_mail.send_report_email`.

---

## `ka11y/utils/run_timing.py` (254 lines)

**Purpose**: after each combined audit finishes (success or failure), derive
and log one human-readable timing block (queue wait, per-stage durations,
total wall time) — the same computation also backs the
`GET /combined/{job_id}/timings` API endpoint, so the log file and the API
response can never disagree (module docstring, lines 99-101 of the function
doc).

**Imports**: `os`, `threading`, `datetime.datetime`, `pathlib.Path`,
`typing.Any/Optional` (stdlib); `ka11y.config.logger.setup_logger` (internal
at module scope); deferred `from ka11y.store import repo` (line 228, inside
`log_run_timing`, to mirror the aggregate into the durable store without a
module-level circular import).

**Module-level state**: `logger` (line 36); `_write_lock =
threading.Lock()` (line 40) — a single global lock (not per-path, unlike
`crawler_timing`/`step_logger`, because this module only ever writes to one
file); column-width constants `_W_STAGE`, `_W_STATUS`, `_W_DUR`, `_W_CRAWL`,
`_W_FIND` (lines 42-46).

**Functions**:
- `_log_path() -> Path` (lines 49-55): `$KA11Y_RUN_TIMING_LOG` env override,
  else `<ka11y-python>/logs/run_timings.log` (same `logs/` directory the
  rotating app logger and `stage_timing.py` use).
- `_parse(ts) -> Optional[datetime]` (lines 58-65): parses an ISO timestamp,
  tolerating a trailing `"Z"` (replaced with `"+00:00"` before
  `datetime.fromisoformat`); returns `None` on any parse failure rather than
  raising.
- `_delta_s(a, b) -> Optional[float]` (lines 68-73): seconds between two ISO
  timestamp strings, or `None` if either is missing/unparseable.
- `_fmt_dur(seconds) -> str` / `_round(seconds)` (lines 76-81): display and
  rounding helpers.
- `compute_run_timing(*, job_id, url, status, stages, submitted_at,
  run_started_at, completed_at, lang=None, summary=None, error_stage=None)
  -> dict` (lines 84-135) — **the single source of truth** shared by the log
  writer and the API endpoint. Purely derives durations from already-recorded
  timestamps (queue wait = `submitted_at → run_started_at`; run duration =
  `run_started_at → completed_at`; wall = `submitted_at → completed_at`) and
  per-stage durations from each stage's own `started_at`/`completed_at`.
  Measures nothing itself (no `time.time()` calls) — safe to call at any
  point, including mid-run, where an unfinished stage's `duration_s` comes
  back `None`.
- `_format_run_timing_block(data: dict) -> str` (lines 138-186): renders the
  dict from `compute_run_timing` into the fixed-width text block shown in
  the module docstring's example — a header line (timestamp, job ID prefix,
  status, lang), the URL, a score/findings summary line, an optional
  "failed_stage" line, then a per-stage table, then three summary lines
  (queue_wait / RUN / WALL). Explicitly notes (docstring lines 20-23) that
  per-stage durations do **not** sum to the wall time because stages run
  concurrently via `asyncio.gather`.
- `log_run_timing(*, job_id, url, status, stages, submitted_at,
  run_started_at, completed_at, lang=None, summary=None, error_stage=None)
  -> None` (lines 189-254) — the public entry point:
  1. Calls `compute_run_timing(...)`.
  2. **Side effect**: best-effort mirrors the computed dict into the durable
     store via `repo.insert_event(job_id, "run_timing", data)`, wrapped in a
     bare `except Exception: pass` (lines 227-232).
  3. **Side effect**: if `KA11Y_TELEMETRY_FILES` env var is not `"0"`,
     formats the block and appends it to `_log_path()` under `_write_lock`,
     creating the parent directory first (`path.parent.mkdir(parents=True,
     exist_ok=True)`).
  4. Emits a one-line `logger.info` summary regardless (for grep-ability in
     the main app log).
  5. **The whole function body is wrapped in `try/except Exception`** (lines
     207-253) — a timing-logging failure is caught, logged as a warning, and
     never propagates (module docstring's stated guarantee: "Nothing here
     can fail an audit").

**Side effects**: creates/appends `logs/run_timings.log`; best-effort SQLite
insert; app-log line.

**Used elsewhere**: called from `api/v1/combined/runner.py` at the end of
every job (success or failure path); `compute_run_timing` is also called
directly by the `GET /combined/{job_id}/timings` route handler.

---

## `ka11y/utils/stage_timing.py` (380 lines)

**Purpose**: the finest-grained timing instrument in the codebase — one JSON
row per individual step (page × stage × sub_stage × rule), letting you answer
"which page/rule/stage was the bottleneck" rather than only aggregate
per-run or per-crawler numbers.

**Imports**: `json`, `os`, `threading`, `time`, `collections.defaultdict`,
`contextlib.asynccontextmanager/contextmanager`, `datetime.datetime/timezone`,
`pathlib.Path`, `typing.*` (stdlib); `ka11y.config.logger.setup_logger`
(internal); deferred `from ka11y.store import repo` (line 127).

**Module-level constants**: `_DISABLE_ENV = "KA11Y_STAGE_TIMING_DISABLE"`,
`_DIR_ENV = "KA11Y_STAGE_TIMING_DIR"` (lines 67-68); `_locks`,
`_registry_lock` (per-file lock registry, same pattern as
`crawler_timing.py`/`step_logger.py`, lines 71-72).

**Functions**:
- `_is_disabled() -> bool` (lines 75-76): checks `KA11Y_STAGE_TIMING_DISABLE`
  against a set of truthy strings.
- `_timings_dir() -> Path` (lines 79-84): `$KA11Y_STAGE_TIMING_DIR` override,
  else `<ka11y-python>/logs/timings/`.
- `_lock_for(path)` (lines 87-93): same get-or-create lock pattern seen
  elsewhere in `utils/`.
- `_now_iso()` (lines 96-97): millisecond-precision UTC ISO timestamp.
- `_jsonl_path(run_id)` / `_summary_path(run_id)` (lines 100-105): per-run
  file paths, `<run_id>.jsonl` and `<run_id>.summary.log`.
- `_safe_run_id(run_id) -> str` (lines 108-111): **path-traversal guard** —
  strips every character that isn't alphanumeric, `-`, `_`, or `.`, so a
  malicious/malformed `run_id` (e.g. containing `../`) cannot escape the
  timings directory when used to build a filename. Falls back to
  `"unknown"` if the result is empty.
- `_files_enabled()` (lines 114-117): same `KA11Y_TELEMETRY_FILES` opt-out
  pattern as `crawler_timing.py`/`run_timing.py`.
- `_write_row(run_id, row: dict) -> None` (lines 120-143): first
  best-effort-mirrors the row into `store.repo.insert_timing(row)` (bare
  `except: pass`), then — if file telemetry is enabled — appends the row as
  one JSON line to `<run_id>.jsonl`, creating the parent directory, under
  the per-path lock. A write failure here is caught and logged as a warning
  (not silently swallowed like the DB mirror, but still never raised).
- `record(run_id, *, stage, duration_ms, status="ok", page_url=None,
  depth=None, sub_stage=None, rule=None, item_count=None, error=None,
  extra=None) -> None` (lines 146-175): builds the row dict matching the
  JSONL schema documented in the module docstring and calls `_write_row`.
- `time_stage_async(run_id, stage, *, page_url=None, depth=None,
  sub_stage=None, rule=None, extra=None)` (`@asynccontextmanager`, lines
  178-212) and its sync twin `time_stage` (`@contextmanager`, lines
  215-249): identical logic in async/sync form — times the wrapped block via
  `time.perf_counter()`, catches and re-raises any exception while recording
  `status="error"` and `error=repr(exc)[:200]`, and always calls `record(...)`
  in a `finally` block.

**Summary emission**:
- `_load_rows(run_id) -> List[dict]` (lines 255-272): reads back the JSONL
  file line by line, skipping (not raising on) any line that fails
  `json.loads`.
- `emit_summary(run_id) -> Optional[Path]` (lines 275-371) — called once at
  the end of a run:
  1. Loads all rows; returns `None` immediately if disabled or empty.
  2. Builds three nested aggregation dicts via `defaultdict(list)` /
     `defaultdict(lambda: defaultdict(list))` / a 3-level version: `stage →
     [durations]`, `page → stage → [durations]`, `page → stage → rule →
     [durations]`.
  3. Renders a human-readable report: a "Stage totals" table (sorted by
     total time descending, showing total/count/mean/max), then a
     "Per-page breakdown" section — for each page, sorted by that page's
     stage-time descending, showing total/count and the single
     heaviest-time rule for that (page, stage) pair.
  4. Writes the result to `<run_id>.summary.log`, overwriting any previous
     summary for the same run (safe to call multiple times, e.g. once at
     job completion and again if manually re-triggered).
  5. Wrapped in `try/except Exception`, logging a warning and returning
     `None` on any failure.

**`__all__`** (lines 374-379): `record`, `time_stage`, `time_stage_async`,
`emit_summary`.

**Side effects**: creates `logs/timings/`; appends JSONL rows; writes the
summary file; best-effort SQLite mirror.

**Used elsewhere**: wrapped around fine-grained steps inside
`api/v1/combined/stages.py` and rule evaluation loops; `emit_summary` called
once at job completion in `api/v1/combined/runner.py`.

---

## `ka11y/utils/step_logger.py` (126 lines)

**Purpose**: a JSONL "what happened during this run" execution log — coarser
than `stage_timing.py` (records human-readable step/status/message events
rather than pure durations) and used for both machine parsing and building a
per-run summary JSON.

**Imports**: `json`, `threading`, `datetime.datetime/timezone`,
`pathlib.Path`, `typing.Any/Dict/Optional` (stdlib);
`ka11y.config.logger.setup_logger` (internal).

**Module-level state**: `logger` (line 11); `_locks_registry`,
`_locks_registry_lock` (lines 17-18, the same per-path-lock pattern as the
other `utils/*_timing.py` modules).

**Functions**:
- `_lock_for(path)` (lines 21-27): standard get-or-create lock.
- `_utc_now() -> str` (lines 30-31): current UTC time as ISO string.
- `append_step_log(path, *, step, status, message, context=None) ->
  Optional[str]` (lines 34-61): the low-level writer. Returns `None`
  immediately if `path` is falsy (lets callers pass `None` to skip logging
  without an `if` at every call site). Otherwise: creates the parent
  directory, builds an entry dict (`timestamp, step, status, message,
  context`), serializes with `json.dumps(..., ensure_ascii=False)` (so
  non-ASCII text like Japanese findings isn't `\uXXXX`-escaped), and appends
  under the per-path lock. Returns the stringified path on success.

**Class `ExecutionStepLogger`** (lines 64-126):
- `__init__(self, *, output_dir, name, job_id=None)` (lines 65-79): computes
  `self.steps_dir = output_dir / "step_logs"` and **creates it immediately**
  (`self.steps_dir.mkdir(parents=True, exist_ok=True)`, line 76 — eager, not
  lazy); sets `self.jsonl_path = steps_dir / f"{name}.jsonl"` and
  `self.summary_path = steps_dir / f"{name}_summary.json"`; initializes a
  `self._counts` dict tracking how many `running`/`completed`/`warning`/
  `error` events have been recorded.
- `record(self, *, step, status, message, context=None) -> None` (lines
  81-108): merges `job_id` into the context (if set and not already
  present), calls `append_step_log`, increments `self._counts[status]`, and
  **also** emits the message through the regular `KaLogger` at a level
  matching `status` (`error`→`logger.error`, `warning`→`logger.warning`,
  `completed`→`logger.success`, anything else→`logger.processing`) — so
  every recorded step is visible both in the structured JSONL file and in
  the live console/app-log stream.
- `finalize(self, *, status, message, context=None) -> None` (lines
  110-126): records one final step event named after `self.name`, then
  **side effect**: writes a summary JSON (`name, job_id, status, message,
  counts, jsonl_path, completed_at, context`) to `self.summary_path` via
  `json.dump(..., indent=2, ensure_ascii=False)`.

**Side effects**: creates `<output_dir>/step_logs/`; appends the JSONL file;
writes the summary JSON file; emits log lines through `KaLogger`.

**Used elsewhere**: instantiated per named stage inside
`api/v1/combined/stages.py`/`runner.py` to produce a per-job execution trail
(see `12-OUTPUT-FILES.md` for the resulting `step_logs/` directory layout).

---

## `ka11y/utils/text_detector_helper.py` (62 lines)

**Purpose**: small OpenCV/NumPy helpers used by the OCR/text-detector
pipeline for bold-text heuristics and alpha-channel image loading.

**Imports**: `cv2` (OpenCV), `numpy as np` (both third-party). No internal
imports.

**Functions**:
- `estimate_boldness(img, bbox) -> bool` (lines 5-37): given a full image and
  a quadrilateral bounding box (`bbox`, a list of 4 `(x, y)` points — the
  OCR engines' polygon format), crops the bounding rectangle, converts to
  grayscale, applies Otsu thresholding (`cv2.threshold(..., THRESH_BINARY +
  THRESH_OTSU)`) to binarize foreground/background, computes the fraction of
  dark pixels (`dark_density`). **Key correctness fix documented inline**
  (lines 26-34): rather than assuming "dark pixels = text" (which
  misclassifies light text on a dark background — e.g. a hero banner CTA —
  as bold, because the dark *background* becomes the majority class), it
  takes `stroke_density = min(dark_density, 1 - dark_density)` — text is
  always the minority pixel class within a tight OCR box regardless of
  polarity. Returns `stroke_density > 0.35` (empirically tuned threshold,
  per the trailing comment). Returns `False` early if the cropped region is
  empty (`crop.size == 0`).
- `bbox_height_rotated(bbox) -> float` (lines 40-43): computes the Euclidean
  distance between the bbox's top-left (`bbox[0]`) and bottom-left
  (`bbox[3]`) corners via `np.linalg.norm` — gives the box's "height" even
  when the OCR polygon is rotated (not axis-aligned), unlike a naive
  `max_y - min_y`.
- `load_image_with_alpha(image_path) -> Optional[np.ndarray]` (lines 46-61):
  loads via `cv2.imread(path, cv2.IMREAD_UNCHANGED)` (preserves alpha
  channel if present); returns `None` if the load failed. If the image is
  RGBA (`shape[2] == 4`), composites it onto a white background using the
  alpha channel as a blend weight (`img * alpha + white * (1 - alpha)`) — so
  downstream OCR/contrast code always sees an opaque RGB image, matching how
  a transparent PNG would actually render on a typical white page background.

**Side effects**: file I/O via `cv2.imread` (in `load_image_with_alpha`).

**Used elsewhere**: `text_detector/text_detector.py` and/or
`preprocessor/extract_color.py` (see `09-MODULES-text-classifier-i18n.md`)
during image-region preprocessing before OCR.

---

## `ka11y/utils/url_canonical.py` (113 lines)

**Purpose**: normalize a URL into a canonical "page identity" string, used
everywhere a `page_url` is stamped on a finding, so that trivially-different
URLs for the same logical page (`/about` vs `/about/`) group together in the
UI instead of appearing as separate page tabs.

**Imports**: `urllib.parse.urlsplit/urlunsplit` (stdlib). No internal
imports — pure, no I/O, never raises (module docstring's explicit safety
contract, lines 36-39).

**Module-level constants**: `_DEFAULT_PORTS = {"http": 80, "https": 443}`
(lines 46-49); `_INDEX_SUFFIXES = ("/index.html", "/index.htm")` (line 51).

**Function `canonicalize_url(url: str) -> str`** (lines 54-109):
1. Returns the input unchanged if it's not a non-empty string, or if
   `urlsplit` raises `ValueError` on malformed input (lines 66-72).
2. Returns unchanged if the scheme isn't `http`/`https` (leaves `mailto:`,
   `tel:`, `data:` etc. untouched, line 74-77).
3. Lowercases the hostname; returns unchanged if there's no hostname at all
   (line 81-83).
4. Preserves userinfo (`user:pass@`) verbatim if present (lines 85-90) —
   noted as "rare in crawled URLs but technically valid."
5. Drops the port if it matches the scheme's default (`:443` for https,
   `:80` for http); keeps any non-default port.
6. On the path: strips a trailing `/index.html` or `/index.htm` (case-
   insensitive match via `lower_path`, but the *original*-case path is
   sliced, preserving case elsewhere in the path); then strips a trailing
   `/` unless the path is just `/` (root).
7. Always drops the fragment (`#...`); keeps the query string unchanged.
8. Reassembles via `urlunsplit`.

Docstring explicitly lists what is deliberately **not** normalized yet:
arbitrary trailing `.html` (unsafe to strip blindly — `/about` and
`/about.html` can be genuinely different resources), query-parameter
ordering, and percent-encoding case — each with a one-line rationale.

**`__all__`**: `["canonicalize_url"]`.

**Side effects**: none.

**Used elsewhere**: stamped onto every finding's `element.page_url` during
report assembly (`api/v1/combined/findings.py`), and used by the crawler /
universal-page snapshot builder to key per-page data consistently with the
Node engine (which has its own equivalent, `ka11y-node/src/utils/canonicalUrl.js`,
per the module's own docstring cross-reference).
