# 4. Module-by-Module Breakdown — Group 2: Crawler

> **2026-09-15 — crawler consolidation.** The combined audit now navigates
> each page **once**: `universal_page.py` runs the image extractor + asset
> capture (moved out of `optimized/engine.py` into
> `ka11y/crawler/image_extractor.py`) on the page it already loaded, and the
> image stage only reads the resulting page docs. `optimized/engine.py` and its
> `BrowserManager` are CLI / legacy-route only; its private SSRF and
> cookie-reject copies now import the shared modules. `browser_pool.py` gained
> crash recovery and idle recycling and is the single browser-concurrency knob.
> The per-function detail below predates that change where it describes
> `engine.py` internals; see `ka11y-python/crawler-python.md` for the current
> data pathway.

Everything that drives Playwright/Chromium. Two large files
(`optimized/engine.py`, `universal_page.py`) each embed a substantial
in-browser JavaScript extraction script as a Python string constant executed
via `page.evaluate(...)`; those are documented by purpose/structure rather
than transcribed line-by-line (per the walkthrough's own scoping note — this
is non-Python code, and hundreds of lines of nearly-repetitive selector logic
add no further understanding beyond what's summarized here).

---

## `ka11y/crawler/browser_pool.py` (199 lines)

**Purpose**: one shared, bounded Chromium process pool, so the ~10 crawler
subsystems (image, media, sensory, forms, target-size, text-spacing,
rendered-layout, interactive, moving-content, universal) don't each launch
their own ~300MB browser process (module docstring, lines 6-13).

**Imports**: `asyncio`, `contextlib`, `logging`, `os`, `typing.*` (stdlib);
`playwright.async_api.Browser/BrowserContext/Playwright/async_playwright`
(third-party); `ka11y.crawler.context_factory.new_crawler_context` (internal).

**Module-level constant**: `_MAX_BROWSERS = int(os.environ.get("KA11Y_MAX_BROWSERS", "2"))`
(line 61) — bounds concurrent Chromium *processes* (not contexts — contexts
are cheap and unbounded per-browser here, gated only by the semaphore below).

**Class `BrowserPool`** (lines 64-154, explicitly "not designed for
inheritance" — use the module-level helpers):
- `__init__(self, max_browsers=_MAX_BROWSERS)` (lines 72-80): creates an
  `asyncio.Semaphore(max_browsers)`, an `asyncio.Lock()` for one-time
  Playwright startup, and stamps `self._loop = asyncio.get_event_loop()` —
  used later by `get_pool()` to detect a loop change (e.g. between pytest
  test cases) and rebuild the pool rather than reuse asyncio primitives bound
  to a dead loop.
- `_ensure_started(self)` (lines 82-88): double-checked-locking pattern —
  returns immediately if `self._pw` is set; otherwise acquires `_init_lock`
  and calls `await async_playwright().start()` exactly once.
- `_acquire_browser(self) -> Browser` (lines 90-101): reuses
  `self._browsers[0]` if a warm browser already exists; otherwise launches
  one Chromium instance with `args=["--no-sandbox", "--disable-dev-shm-usage"]`
  and appends it to `self._browsers` (a list, though in practice only ever
  holds one entry — one process for the whole pool).
- `lease_browser(self)` (`@asynccontextmanager`, lines 103-116): acquires the
  semaphore, gets the warm browser, yields it — **does not close it on
  exit**, since it's meant to be reused by subsequent leases. Documented for
  callers that need many contexts off one browser directly (e.g. a rendered-
  layout crawler fanning out 7 viewport contexts).
- `lease_context(self, **context_kwargs)` (`@asynccontextmanager`, lines
  118-139): the common path — acquires the semaphore, gets the browser, calls
  `new_crawler_context(browser, **context_kwargs)` (which installs the SSRF
  guard — see `context_factory.py` below), yields the fresh `BrowserContext`,
  and **always closes the context** in a `finally` block on exit (catching
  and debug-logging, not raising, if the close itself fails — e.g. a target
  torn down externally).
- `shutdown(self)` (lines 141-154): closes every browser in `self._browsers`
  and stops Playwright, each step independently try/excepted so one failure
  doesn't block the rest. Idempotent (`self._pw = None` after, so a second
  call is a no-op).

**Module-level singleton machinery** (lines 157-198): `_pool`, `_pool_loop`
globals; `get_pool() -> BrowserPool` (lines 163-175) lazily creates (or
recreates, if the current event loop differs from `_pool_loop`) the
process-wide singleton; `leased_context(**kwargs)` / `leased_browser()`
(lines 178-189) are thin async-context-manager wrappers around
`get_pool().lease_context(...)` / `.lease_browser()`; `shutdown_pool()`
(lines 192-198) tears down and clears the singleton — called from
`main.py`'s FastAPI `lifespan` teardown.

**Side effects**: launches/manages a real Chromium subprocess; no
filesystem/network I/O of its own beyond that.

**Used elsewhere**: `main.py` (lifespan shutdown), `utils/report_pdf.py`
(leases a context to render the PDF), and pervasively throughout
`api/v1/combined/stages.py` and the various crawler entry points that have
been migrated to the pool (the module docstring notes migration is
incremental — not-yet-migrated crawlers still launch their own browser).

---

## `ka11y/crawler/context_factory.py` (25 lines)

**Purpose**: the single place a new `BrowserContext` is actually created for
pooled crawling, so the SSRF guard is installed on every context without
each call site remembering to do it.

**Imports**: `typing.Any`; `ka11y.crawler._ssrf_guard.install_ssrf_guard`,
`ka11y.utils.config_loader.load_config` (internal).

**Functions**:
- `should_ignore_https_errors() -> bool` (lines 9-16): reads
  `config["browser"]["ignore_https_errors"]` (default `True`); coerces a
  string value (`"true"`/`"1"`/`"yes"`/`"on"`, case-insensitive) to `bool`,
  else `bool(raw)`.
- `new_crawler_context(browser, **kwargs) -> BrowserContext` (lines 19-24,
  async): sets `ignore_https_errors` from the config default if not
  overridden by the caller, calls `browser.new_context(**context_kwargs)`,
  then **always** `await install_ssrf_guard(context)` before returning it —
  so no code path through this factory can produce a context without the
  guard.

**Side effects**: none beyond the browser context creation itself.

**Used elsewhere**: `browser_pool.py`'s `_acquire_browser`/`lease_context`
path is the only caller.

---

## `ka11y/crawler/cookie_handler.py` (228 lines)

**Purpose**: reject-only cookie-consent banner handling (never accepts) for
crawler code paths that haven't been consolidated onto the newer
`optimized/engine.py`'s inline copy of the same logic (see that module's
`reject_cookies` — this file and that function are near-duplicates by
design, kept separate because they serve different crawler generations).

**Imports**: `logging`, `re`, `typing.Union` (stdlib); `playwright.async_api.Frame/Page`.

**Module-level constants**: `CookieContext = Union[Page, Frame]` type alias
(line 9); `_CLICK_TIMEOUT_MS = 1500`, `_STABILIZE_DELAY_MS = 800` (lines
12-13); `_REJECT_PATTERN` (lines 22-37) — a broad, case-insensitive regex
matching "reject", "decline", "deny", "no thanks", "continue without
accepting", "necessary/essential only", "save preferences", "do not
accept/consent/agree/sell/share", "opt-out", etc. — deliberately excludes any
"accept" variant (module comment, lines 19-21: this handler only rejects, so
captured screenshots reflect the "cookies rejected" state for audits);
`_EXPLICIT_REJECT_SELECTORS` (lines 49-63) — CSS selectors for named CMP
frameworks (OneTrust, Cookiebot, Didomi, TrustArc, Google's GDPR handler
`#W0wltc`) plus generic `[id*='reject-all' i]`-style patterns, tried before
text matching since they're highest-signal; `_OVERLAY_SELECTORS` (lines
71-98) — a longer list of banner/backdrop/preference-center selectors force-
removed from the DOM regardless of whether a reject click succeeded.

**Functions**:
- `_iter_cookie_contexts(page) -> list[CookieContext]` (lines 101-111):
  returns `[page, *every nested frame]` via a recursive `walk` closure over
  `frame.child_frames` — consent banners frequently live in an iframe.
- `_click_first_match(context, *, pattern, explicit_selector) -> bool`
  (lines 114-153, async): tries four locator strategies in precedence order
  — (1) the explicit CMP selector list, (2) `get_by_role("button",
  name=pattern)`, (3) any `button/a[href]/input[button|submit]/[role=button]`
  filtered by text match, (4) any `[role=button]`/`[role=link]` filtered by
  text match — each wrapped in its own `try`, returning `True` on the first
  successful `is_visible()` + `.click()`.
- `_cleanup_cookie_overlays(contexts) -> bool` (lines 156-175, async): for
  every context × every `_OVERLAY_SELECTORS` entry, finds all matching
  elements and calls `element.evaluate("node => node.remove()")` on any that
  are visible — runs unconditionally after every attempt (not just on
  failure), since some sites animate the banner out slowly or leave the
  backdrop behind even after a successful click.
- `handle_cookies(page) -> str` (lines 178-227, async) — the public entry
  point. Iterates every context calling `_click_first_match`; if any click
  succeeded, waits `_STABILIZE_DELAY_MS` for the close animation then runs
  cleanup and returns `"rejected"`; else runs cleanup anyway and returns
  `"removed"` if anything was force-removed, `"none"` if nothing was found
  at all; any exception anywhere is caught and turns into `"error"` — never
  raises, since a broken cookie-banner heuristic must not abort the crawl.

**Side effects**: DOM mutation (removes overlay elements) inside the browser
page; no filesystem/network I/O of its own.

**Used elsewhere**: `universal_page.py`'s `_prepare_page` (imported as
`from ka11y.crawler.cookie_handler import handle_cookies`).

---

## `ka11y/crawler/media_crawler.py` (78 lines)

**Purpose**: pure Pydantic data model — no extraction logic of its own (the
module docstring is explicit: extraction happens in the shared universal-page
JS loader; this module only defines the shape).

**Imports**: `typing.Dict/List/Optional`; `pydantic.BaseModel`.

**Class `MediaElementData(BaseModel)`** (lines 33-77) — one instance per
`<audio>`/`<video>` element found on a page, feeding the WCAG 1.2.1 media
auditor. Fields grouped by the module docstring's own categories:
identity (`page_url`, `element_index`, `tag`, `element_id`, `src`,
`html_snippet`), media attributes (`has_autoplay`, `has_controls`,
`has_loop`, `is_muted`), track children (`tracks: List[Dict]` — each
`{kind, src, srclang, label}` for `<track>` captions/descriptions), ARIA/role
(`aria_hidden`, `role`, `aria_label`, `aria_describedby_text`), and "nearby
context for transcript detection" (`nearby_links`, `nearby_text`,
`nearby_details`) plus `selector`/`element_ref_id`/`frame_path` for
cross-referencing back to the DOM. No methods beyond Pydantic's generated
ones — a data-transfer object only.

**Side effects**: none. **Used elsewhere**: consumed by
`accessibility/rules/media/media_auditor.py`; instantiated by
`snapshot_normalizer.py` from raw dicts captured via `universal_page.py`.

---

## `ka11y/crawler/models.py` (305 lines)

**Purpose**: the core Pydantic models for the *image* pipeline —
`WcagViolation`, `ImageData` (crawler output), `ImageMetadata` (richer,
persisted sidecar with a self-contained violation-detection method).

**Imports**: `typing.Optional/List`; `pydantic.BaseModel`. No internal
imports.

**Class `WcagViolation(BaseModel)`** (lines 9-14): `rule` (e.g. `"1.1.1"`),
`level` (`A`/`AA`/`AAA`), `violation` (human description), `suggestion` (fix
text), `element` (truncated HTML snippet).

**Class `ImageData(BaseModel)`** (lines 20-90) — the record type produced by
the crawler and consumed by OCR/classification/auditors. Grouped fields:
core identity/classification (`url`, `src`, `alt_text`, `title`,
`classification`, `sub_type`, `is_functional`/`is_decorative`/`is_complex`/
`is_text_image`/`is_logo`/`is_icon`/`is_button`), capture bookkeeping
(`screenshot_path`, `filename`, `capture_status` — one of `ok/failed/
timeout/network/dom_missing`, `capture_error`), WCAG 1.1.1 hidden/role
signals (`aria_hidden`, `role`), WCAG 1.4.11 page-context capture
(`full_page_screenshot_path`, `page_bbox: list[tuple[int,int]]` — see
`adapter.py`'s explanation of why this must be pre-rounded to ints),
accessible-name context for 1.1.1/4.1.2 (`element_type`, `alt_present`,
`in_link`, `in_button`, `in_labeled_control`, `has_own_text_content` — module
comment lines 59-66 explains the *why*: an `<img>` inside a labeled control
is named by that control, so judging it in isolation produces false
positives), and long-description context for complex images
(`figcaption_text`, `aria_describedby_text`, `has_longdesc`, `in_figure`).
- Method `has_long_description(self) -> bool` (lines 84-90): `True` if any of
  `has_longdesc`, a non-empty `aria_describedby_text`, or a non-empty
  `figcaption_text` is set.

**Class `ImageMetadata(BaseModel)`** (lines 97-304) — a much richer,
independently-populated model (the module comment says it's "saved as JSON
sidecar + master metadata.json per crawl run" — the legacy/parallel richer
metadata format, distinct from `ImageData`). Groups: identity, dimensions,
WCAG 1.1.1 attributes (`alt`/`title_attr`/ARIA/`longdesc`), 1.4.5 images-of-
text (`contains_text`, set post-crawl by OCR), 2.1.1 keyboard (`tabindex`,
`has_onclick`, `cursor_style`), 2.4.4 link purpose context, button context,
document-structure context (figure/heading/surrounding text), responsive-
image attributes (`srcset`, `sizes`, `loading`, `decoding`, etc.), computed
CSS relevant to accessibility, raw HTML snippets, classification mirror
fields, and `wcag_violations: List[WcagViolation]`.
- Method `compute_violations(self) -> "ImageMetadata"` (lines 185-304) — a
  **self-contained rule engine** distinct from (and simpler than) the
  dedicated auditors elsewhere in the codebase; checks, in order:
  1. **1.1.1 missing alt** (lines 204-219): flags if not presentational
     (`aria_hidden != "true"` and `role not in (presentation, none)`) and
     `alt is None` and no `aria_label`/`aria_labelledby`.
  2. **1.1.1 functional image, no accessible name** (lines 221-243): if
     `in_link`/`in_button`/`has_onclick`, requires *some* name source
     (non-empty `alt`, `aria_label`, `aria_labelledby`, `link_text`, or
     `button_text`).
  3. **2.1.1 clickable image not keyboard-reachable** (lines 245-263): if
     `has_onclick` or `cursor_style == "pointer"`, and not already in a
     link/button, and `tabindex` is missing or `"-1"`.
  4. **2.4.4 link with no discernible purpose** (lines 265-285): for images
     inside a link, requires a name from `alt`/`link_text`/`link_aria_label`/
     `aria_label`.
  5. **4.1.2 button with no accessible name** (lines 287-302): for images
     inside a button, requires `alt`/`aria_label`/`button_text`.
  Sets `self.wcag_violations = v` and returns `self` (fluent style — callers
  do `ImageMetadata(**data).compute_violations()`).

**Side effects**: none — pure data model + pure classification logic.

**Used elsewhere**: `ImageData` is the type flowing through
`optimized/adapter.py` → `accessibility/rules/non_text/alttext.py`,
`contrast_analyser.py`, and the image-audit stage in
`api/v1/combined/stages.py`. `ImageMetadata` appears to be from an earlier
generation of the pipeline (its `compute_violations` duplicates logic that
now lives in the dedicated auditors); grep shows it's still constructed by
some legacy path but the primary flow uses `ImageData`.

---

## `ka11y/crawler/navigation.py` (170 lines)

**Purpose**: resilient page navigation — DNS preflight + retry/backoff around
`page.goto()`, with a typed `NavigationError` carrying a stable error `code`
callers can branch on.

**Imports**: `asyncio`, `socket`, `logging`, `urllib.parse.urlparse`
(stdlib); `playwright.async_api.Page`.

**Module-level constants**: `_RETRYABLE_NAVIGATION_TOKENS` (lines 12-26) — a
list of Chromium/Firefox network-error substrings (`ERR_CONNECTION_REFUSED`,
`ERR_NAME_NOT_RESOLVED`, `NS_ERROR_NET_TIMEOUT`, `TIMEOUT`, etc.) considered
transient/retryable; `_DNS_PRECHECK_ATTEMPTS = 3`, `_NAVIGATION_ATTEMPTS = 3`,
`_NAVIGATION_BACKOFF_SECONDS = [1.0, 2.5, 5.0]` (lines 28-30).

**Class `NavigationError(Exception)`** (lines 33-54): carries `code`, `url`,
`host`, `original_message`, `attempts`; `_build_message` (lines 49-54)
formats a single diagnostic string combining all of them.

**Functions**:
- `_host_from_url(url) -> str | None` (lines 57-59): `urlparse(url).hostname`.
- `_is_retryable_navigation_error(message) -> bool` (lines 62-64): substring
  match (case-insensitive) against `_RETRYABLE_NAVIGATION_TOKENS`.
- `dns_preflight(url)` (lines 67-109, async): resolves the URL's hostname via
  `asyncio.to_thread(socket.getaddrinfo, host, 443, 0, SOCK_STREAM)` up to
  `_DNS_PRECHECK_ATTEMPTS` times, with the shared backoff schedule between
  attempts, logging a warning each retry; raises `NavigationError(code=
  "dns_resolution_failed", ...)` if every attempt fails. No-ops (returns
  immediately) if the URL has no hostname.
- `navigate_with_resilience(page, url, *, wait_until="domcontentloaded",
  timeout_ms=30000)` (lines 112-169, async) — the public entry point:
  1. Calls `dns_preflight(url)` first (raises immediately if DNS never
     resolves — no point attempting `page.goto` at all).
  2. Loop up to `_NAVIGATION_ATTEMPTS` times: uses the full requested
     `timeout_ms` on the first attempt, but **extends to
     `max(timeout_ms, 60000)` on retries** (line 125 — a page that timed out
     once gets more time on the retry, on the theory that the first attempt
     may have triggered a slow first-load / CDN cold cache).
  3. On success (`page.goto` doesn't raise), returns immediately.
  4. On exception: if attempts remain, waits the backoff delay, and — only if
     the error looks retryable (`_is_retryable_navigation_error`) — re-runs
     `dns_preflight` before the next attempt (in case the failure was itself
     a DNS blip that's now resolved).
  5. After exhausting all attempts, classifies the final error's `code` as
     `"dns_resolution_failed"` if the message mentions
     `ERR_NAME_NOT_RESOLVED`/`NS_ERROR_UNKNOWN_HOST`, else
     `"page_navigation_failed"`, and raises `NavigationError`.

**Side effects**: DNS lookups (blocking, offloaded to a thread); drives the
actual page navigation (network).

**Used elsewhere**: `universal_page.py`'s `_prepare_page` calls
`navigate_with_resilience` as the first step of loading every page.

---

## `ka11y/crawler/policy.py` (126 lines)

**Purpose**: `CrawlPolicy` — the Pydantic model encapsulating BFS crawl rules
(depth/page budget, same-origin filtering, URL normalization, query-param
canonicalization).

**Imports**: `pydantic.BaseModel/Field`; `typing.Set/ClassVar`;
`urllib.parse.urlparse/urlunparse`.

**Class `CrawlPolicy(BaseModel)`** (lines 8-125):
- Fields: `max_depth=0`, `max_pages=50` (global page budget — "the hard
  ceiling that keeps a deep crawl from exhausting RAM regardless of how many
  links each page has," comment lines 10-13), `max_links_per_page=50`,
  `same_origin=True`, `include_subdomains=False`, `strip_fragments=True`,
  `strip_trailing_slash=True`, `query_allow_list`/`query_deny_list: Set[str]`
  (both empty by default), `canonical_query=True` (sorts params + strips
  trackers), `max_retries=3`.
- `TRACKER_PARAMS: ClassVar[Set[str]]` (lines 34-46) — `utm_*`, `fbclid`,
  `gclid`, `_ga`, `msclkid`, `mc_cid`, `mc_eid` — a `ClassVar` (shared across
  instances, not a per-instance Pydantic field) since it's a fixed constant.
- `normalize_url(self, url) -> str` (lines 48-109): (1) lowercases scheme and
  hostname, **drops userinfo** (`user:pass@`) from the rebuilt netloc so
  credentials never leak into the visited-set/logs/report URLs (comment
  lines 54-57), bracket-wraps an IPv6 hostname; (2) strips the fragment if
  `strip_fragments`; (3) strips a trailing `/` on non-root paths if
  `strip_trailing_slash`; (4) walks the query string parameter-by-parameter,
  dropping tracker params (if `canonical_query`) and anything excluded by the
  allow/deny lists, sorting the remainder (if `canonical_query`); (5)
  reassembles via `urlunparse`.
- `is_allowed(self, url, base_url) -> bool` (lines 111-125): if
  `same_origin`, compares hostnames exactly (or allows a subdomain match via
  `.endswith(f".{base_host}")` if `include_subdomains`); returns `False` if
  either hostname is empty; returns `True` unconditionally if
  `same_origin=False`.

**Side effects**: none — pure URL string manipulation.

**Used elsewhere**: `universal_page.py`'s `UniversalPageLoader.load` builds a
`CrawlPolicy` from request parameters (or accepts one directly) and uses it
for both link normalization and origin filtering throughout the BFS.

---

## `ka11y/crawler/snapshot_normalizer.py` (132 lines)

**Purpose**: converts a raw `PageSnapshot` (untyped dicts from
`universal_page.py`'s JS extraction) into a `NormalizedPageSnapshot` whose
`media` field is validated `MediaElementData` Pydantic models — bridging the
newer universal-crawler output back into the shape the existing (older)
media auditor expects.

**Imports**: `json`, `pathlib.Path`, `typing.*` (stdlib); `pydantic.BaseModel/
Field/ValidationError`; `ka11y.config.logger.setup_logger`,
`ka11y.crawler.media_crawler.MediaElementData`,
`ka11y.crawler.universal_page.PageSnapshot`,
`ka11y.utils.step_logger.ExecutionStepLogger` (internal).

**Class `NormalizedPageSnapshot(BaseModel)`** (lines 17-25): mirrors
`PageSnapshot`'s shape but with `media: List[MediaElementData]` typed
strictly (vs. `PageSnapshot.media: List[Dict[str, Any]]`).

**Class `SnapshotNormalizer`** (lines 28-131):
- `MODEL_MAP: Dict[str, Type[BaseModel]] = {"media": MediaElementData}`
  (lines 29-31) — currently only one field is normalized this way (a
  single-entry map, presumably extensible for future typed fields).
- `normalize(cls, snapshot, *, output_dir=None, step_logger=None) ->
  NormalizedPageSnapshot` (classmethod, lines 33-77): copies the untyped
  fields straight across (`warnings`, `element_refs`, `page_summaries`,
  `partial`, `pages_crawled`, `har_path`), then for each `MODEL_MAP` entry
  calls `_parse_items` to validate/convert that field's raw dict list into
  typed model instances, `setattr`s the result. If `output_dir` given, calls
  `cls.save(...)` (side effect: writes a JSON file). Logs a `step_logger`
  completion event with counts.
- `_parse_items(cls, *, field_name, items, model_cls, page_url, warnings,
  step_logger) -> List[Any]` (classmethod, lines 79-114): for each raw dict,
  sets a `page_url` default, then tries `model_cls(**payload)`; on
  `pydantic.ValidationError`, **skips that one item** (does not abort the
  whole snapshot), appends a `{"code": "normalization_error", ...}` entry to
  the shared `warnings` list, logs a warning, and records a `step_logger`
  warning event.
- `save(snapshot, output_dir) -> str` (staticmethod, lines 116-131): writes
  `<output_dir>/universal_snapshot_normalized.json` via `model_dump()` on
  each media item plus the raw dict fields, `json.dump(..., indent=2,
  ensure_ascii=False)`.

**Side effects**: writes `universal_snapshot_normalized.json` when
`output_dir` is passed; otherwise none.

**Used elsewhere**: `api/v1/combined/stages.py` (see `07-MODULES-api.md`)
calls `SnapshotNormalizer.normalize` on the `PageSnapshot` returned by
`UniversalPageLoader.load` before handing the media list to the media
auditor.

---

## `ka11y/crawler/_ssrf_guard.py` (211 lines)

**Purpose**: the canonical SSRF defense for Playwright — a route handler
installed on every `BrowserContext` that blocks requests (including redirect
targets, which Playwright re-dispatches as fresh requests) to private,
loopback, link-local, or otherwise non-public IP ranges. Documented in depth
in the earlier security review of this session (`SECURITY_REVIEW_production.md`)
as the pattern the *Node* crawler was found to be missing; this is the
Python original it should be brought in line with.

**Imports**: `ipaddress`, `socket`, `threading`, `time`, `typing.Optional`,
`urllib.parse.urlparse` (stdlib only — deliberately no internal imports, so
this module can be imported early with no circularity risk).

**Module docstring's stated hardening** (lines 6-26, three numbered points):
(1) encoded-IP coverage — decimal/hex/octal integer hostnames and IPv4-mapped
IPv6 all resolve through `ipaddress.ip_address`/`int(host, 0)` rather than a
dotted-quad regex; (2) hostname resolution — even innocuous hostnames get a
cached `getaddrinfo` and are blocked if *any* answer is private; (3) a single
classification function (`_ip_is_blocked`) so there's one source of truth,
recursing into IPv6 `ipv4_mapped` forms.

**Module-level constants**: `_DNS_CACHE_TTL_SECONDS = 30.0` (line 50 — a
deliberately **bounded** TTL; the docstring at lines 38-49 explains this
replaced an earlier unbounded `lru_cache` that could be poisoned permanently
by a DNS-rebinding attacker who lets a domain resolve public once, then
rebinds it — explicitly noting this narrows but does not eliminate the
TOCTOU gap against Chromium's *own*, independent DNS resolution at connect
time); `_BLOCKED_NETWORKS` (lines 52-67) — 13 `ipaddress.ip_network` ranges
covering IPv4 loopback/RFC-1918/link-local (incl. cloud metadata
`169.254.0.0/16`)/shared-address-space/TEST-NET-*/"this network", plus IPv6
loopback/unique-local/link-local.

**Functions**:
- `_classify_blocked(addr) -> bool` (lines 70-84): checks Python's own
  `ipaddress` attribute flags (`is_private`, `is_loopback`, `is_link_local`,
  `is_multicast`, `is_reserved`, `is_unspecified`) first, then falls back to
  explicit membership in `_BLOCKED_NETWORKS`, then recurses into
  `addr.ipv4_mapped` for IPv6 addresses (so `::ffff:10.0.0.1` is caught via
  its embedded IPv4 form).
- `_ip_is_blocked(ip_str) -> bool` (lines 87-93): parses via
  `ipaddress.ip_address`, returns `False` (not blocked) if unparseable
  (a hostname, not an IP), else `_classify_blocked`.
- `_parse_literal_ip(host) -> Optional[ipaddress._BaseAddress]` (lines
  96-126): strips `[]` brackets, tries `ipaddress.ip_address(cleaned)`
  directly; if that fails, checks whether `cleaned` is **pure decimal**
  (`isdigit()`) or has an explicit base prefix (`0x`/`0o`/`0b`) — deliberately
  narrow so a real hostname containing hex-looking characters (e.g.
  `cdn.example.com`, which has an `e`) never accidentally parses as an
  integer (comment lines 107-110) — and if so, calls `int(cleaned, 0)` then
  `ipaddress.ip_address(value)`.
- `_resolve_hostname(host) -> tuple[str, ...]` (lines 133-166): the
  TTL-bounded, thread-lock-guarded DNS cache. Checks `_dns_cache` under
  `_dns_cache_lock`; on a miss (or expired entry), calls
  `socket.getaddrinfo(host, None, 0, SOCK_STREAM)` (catches `gaierror` →
  empty result), dedupes the resolved IPs into a tuple, stores it with the
  current `time.monotonic()` timestamp — and if the cache has grown past
  4096 entries, clears the *whole* cache rather than implementing LRU
  eviction (comment: "the working set of audited hosts is small," line 163).
- `_host_is_blocked(host) -> bool` (lines 169-185) — the public
  classification function used elsewhere (imported directly by
  `utils/lang_detector.py`). Returns `True` immediately for
  `localhost`/`ip6-localhost`/`ip6-loopback` (case-insensitive); if `host` is
  a literal IP form, classifies it directly; otherwise resolves it and
  returns `True` if *any* resolved address is blocked.
- `_ssrf_route_handler(route, request)` (lines 188-200, async): the
  Playwright route callback — parses `request.url`, checks
  `_host_is_blocked(hostname)`, and calls `route.abort("addressunreachable")`
  or `route.continue_()` accordingly.
- `install_ssrf_guard(context)` (lines 203-210, async): `await
  context.route("**/*", _ssrf_route_handler)` — installing on the *context*
  (not per-page) means every page created from it, including pages opened
  via redirect or popup, inherits the guard automatically (docstring lines
  204-209).

**Side effects**: DNS lookups (blocking `socket.getaddrinfo`, called
synchronously inside the async route handler — a potential event-loop
stall under heavy concurrent navigation, though bounded by the TTL cache).

**Used elsewhere**: `context_factory.new_crawler_context` (installs on every
pooled context); `utils/lang_detector.py` imports `_host_is_blocked`
directly (the one documented cross-layer dependency, see
`02-ARCHITECTURE.md`). Note `optimized/engine.py` (below) has its own
**independent, near-identical copy** of this entire guard (`_ssrf_classify_blocked`,
`_ssrf_parse_literal_ip`, `_ssrf_resolve`, `ssrf_host_is_blocked`) rather than
importing this module — the engine is designed to also run as a standalone
CLI script (`python crawl.py ...`, see its own `main()`), so it avoids a
package-relative import dependency.

---

## `ka11y/crawler/optimized/adapter.py` (307 lines)

**Purpose**: converts the optimized engine's raw per-page JSON files into
`List[ImageData]` — the type the rest of the image pipeline (OCR, alt-text
auditor, contrast auditor) already consumes — without changing any
downstream code.

**Imports**: `hashlib`, `json`, `shutil`, `pathlib.Path`, `typing.*`
(stdlib); `ka11y.crawler.models.ImageData` (internal).

**Module-level constants**: `_IMAGE_TYPES` (lines 28-35) — the set of
`element_type` values that become an `ImageData` record (`img`,
`svg_via_img`, `svg_inline`, `svg_via_use`, `svg_via_object`,
`css_background_image`, `css_background_svg`, `input_image`, `canvas`,
`area` — the last explicitly commented as needed for WCAG 1.1.1 image-map
coverage even though it has no standalone pixels); `_NO_PIXEL_TYPES =
{"area"}` (element types audited from the DOM alone, so a missing capture
there is expected, not a failure); `_SRC_FIELD` (lines 44-49) — per
`element_type`, which field on the raw element dict holds its source URL
(handles `svg_via_use`'s sprite-reference field `use_href` specially, per
the inline comment).

**Functions**:
- `_src_of(el) -> str` (lines 52-54): looks up `_SRC_FIELD[element_type]` and
  reads that field off `el`, or `""`.
- `_alt_text(el)` (lines 57-67): computes the *effective accessible name* —
  prefers the browser's computed `accessibility_snapshot_name`, falling back
  to the raw `alt` attribute value; returns `""` for an explicit empty
  `alt=""` (decorative), returns `None` only when the alt attribute is
  genuinely absent (the signal WCAG 1.1.1 cares about).
- `_ext(el, captured) -> str` (lines 70-79): file extension — from the
  captured file's own suffix if present, else parsed from a `data:` URI's
  MIME type, else from the URL's path suffix (if it looks like a real
  extension, ≤5 chars), else defaults to `"png"`.
- `_sha1_of(path) -> str` (lines 82-89): streaming SHA-1 of a file's bytes
  (64KB chunks) — used to distinguish "same image reused" from "different
  element that happens to share a src."
- `_unique_basename(taken, prefix, digest, ext, element_id, content_hash) ->
  str` (lines 92-124) — the collision-resolution logic explained at length
  in its own docstring (lines 100-109): basenames are the OCR-correlation
  join key (`Path(filename).name`), so naming purely by `md5(src)` collapsed
  every element sharing a `src` onto one file — a logo appearing in both a
  sticky header and a footer renders differently in each place, and the
  second capture silently overwrote the first. Fix: only assign a distinct
  suffixed name (`{prefix}{digest}_{md5(element_id)[:6]}.{ext}`, with a
  numeric tiebreaker loop if even that collides) when the **content hash
  differs** from what's already claimed that basename — identical bytes
  still share a name (keeping OCR deduplicated), only genuinely different
  pixels get a new one.
- `_subpath(classification, sub_type) -> Path` (lines 127-139): maps
  classification/sub_type to the output subdirectory
  (`functional/buttons`, `complex/charts`, etc., defaulting sensibly),
  matching the category folders the OCR heuristic keys off of (module
  docstring).
- `build_image_data(raw_dir, output_dir) -> Tuple[List[ImageData],
  Dict[str,str], Set[str]]` (lines 142-306) — the main entry point:
  1. Iterates every `*.json` file in `raw_dir` (sorted, for determinism),
     skips ones that fail to parse or aren't `processing_status ==
     "success"`.
  2. Tracks `visited` page URLs and `page_langs` (from `doc["page_lang"]`).
  3. For each element whose `element_type` is in `_IMAGE_TYPES` and has a
     non-`None` `classification`: resolves its captured pixel file (from
     `el["screenshot"]` or `el["asset_file"]`, relative to `raw_dir`);
  4. **Side effect**: if a captured file exists, computes a content digest,
     picks a prefix (`svg_`/`btn_`/`img_`) and forces `.png` for SVG
     captures, ensures the destination subdirectory exists
     (`dest_dir.mkdir(parents=True, exist_ok=True)`), gets a unique basename
     via `_unique_basename`, and **copies the file** (`shutil.copy2(captured,
     dest)`) — this is where pixel data physically moves from the engine's
     private `_raw/` scratch directory into the crawl's public `output_dir`.
     On `OSError`, marks `capture_status="failed"`.
  5. **1.4.11 page-context copy** (lines 231-264): if the element carries a
     `context_screenshot` + `context_bbox` (captured by
     `optimized/engine.py`'s `_capture_assets` for icon/logo elements — see
     below), copies that padded context screenshot too and builds
     `page_bbox` as **rounded** integer coordinate pairs — the inline
     comment (lines 253-258) flags this as a real bug fix: `getBoundingClientRect()`
     returns sub-pixel floats, and `ImageData.page_bbox` is typed
     `list[tuple[int,int]]`, so an unrounded float previously raised an
     uncaught `pydantic.ValidationError` at `ImageData(...)` construction —
     which aborted `build_image_data()` for the **entire page**, silently
     zeroing out every image on it. `round()` here fixes that class of bug.
  6. Constructs `ImageData(...)` with every field mapped from the raw
     element dict's nested `flags`/`decorative_signals`/`functional_context`/
     `complex_signals` sub-objects, appends to `images`.
  7. Returns `(images, page_langs, visited)`.

**Side effects**: copies image files from `raw_dir` into `output_dir`
(potentially thousands of small file copies per crawl); reads/parses JSON
files.

**Used elsewhere**: `optimized_crawler.py`'s `OptimizedImageCrawler.crawl_page`
is the sole caller.

---

## `ka11y/crawler/optimized/optimized_crawler.py` (259 lines)

**Purpose**: a drop-in replacement for the (presumably older/legacy, not
present in this file group) `AsyncImageCrawler`, backed by the hardened
`optimized.engine.Crawler`, exposing the exact same public surface
(`crawl_page()`, `save_results()`, `images_data`, `images_metadata`,
`visited_urls`, `page_langs`, `output_dir`) so downstream OCR/audit/report
stages need no changes (module docstring).

**Imports**: `json`, `time`, `pathlib.Path`, `typing.*`,
`urllib.parse.urlparse` (stdlib); `csv`, `datetime.datetime`,
`pydantic.BaseModel/Field` (stdlib/third-party, imported mid-file at line
33-35 rather than the top — notable style inconsistency);
`ka11y.utils.config_loader.load_config`, `ka11y.crawler.models.ImageData/
ImageMetadata`, `ka11y.crawler.optimized.engine.Crawler as _Engine`,
`ka11y.crawler.optimized.adapter.build_image_data` (internal).

**Module-level state**: `CONFIG = load_config()` (line 30) — a module-level
snapshot of config, evaluated once at import time (unlike most other modules
which call `load_config()` fresh per use).

**Classes `CrawlSummary(BaseModel)` / `CrawlReport(BaseModel)`** (lines
38-57): simple aggregation containers — counts per classification/sub-type,
and the full `images: List[ImageData]`, wrapped with `base_url`/`crawl_date`.

**Class `OptimizedImageCrawler`** (lines 60-226):
- `__init__(self, base_url, max_depth, max_pages=None, internal_links=True,
  job_id=None)` (lines 61-87): resolves `max_pages` from config if not
  passed; **side effect**: computes `self.output_dir` as
  `{CONFIG.input.output_dir}/{domain}_{MMDD_HHMM}` (domain slugified by
  stripping `www.` and replacing dots with underscores, timestamp via
  `time.strftime`) and immediately calls `self._create_directories()`.
- `_create_directories(self)` (lines 89-94): **side effect**: creates
  `output_dir`, every configured category subdirectory
  (`CONFIG["directories"]`), and `output_dir/metadata/` — all via
  `Path.mkdir(parents=True, exist_ok=True)`.
- `crawl_page(self, discovered_urls=None)` (lines 96-132, async):
  1. Re-runs `_create_directories()` (idempotent) and computes `raw =
     out / "_raw"` — the engine's private scratch directory.
  2. If `discovered_urls` is given (the pipeline's shared multi-page URL
     list), crawls **exactly those pages** at depth 0
     (`max_pages = max(self.max_pages, len(seeds))`, so the explicit list is
     never truncated below its own length); otherwise uses `self.max_depth`
     for a fresh BFS from `self.base_url`.
  3. Constructs and runs an `_Engine` (i.e. `optimized.engine.Crawler`,
     documented above) against `raw`.
  4. Calls `build_image_data(raw, out)` to populate `self.images_data`,
     `self.page_langs`, `self.visited_urls`.
  5. Raises `ImageCrawlerNavigationError(code="zero_pages_crawled", ...)` if
     nothing was visited — surfaces a crawl-budget/navigation-failure
     condition as a typed, catchable error rather than silently returning
     empty data.
- `save_results(self)` (lines 134-184): **side effects** — writes
  `metadata/images_data.json` (raw `ImageData` dump list); computes a
  `CrawlSummary` by iterating `self.images_data` (counting by
  classification/sub_type and building a `sub_type_breakdown` dict); writes
  `images_report.json` (the full `CrawlReport`); calls `self._export_csv()`.
- `_export_csv(self)` (lines 186-225): **side effect** — writes
  `images_with_alt_text.csv` with one row per image (src, alt_text, title,
  classification, sub_type, is_functional/decorative/complex/logo/icon/
  button, screenshot_path) via `csv.DictWriter`; no-ops if `images_data` is
  empty.

**Class `ImageCrawlerNavigationError(RuntimeError)`** (lines 227-258):
carries `code`/`url`/`host`/`original_message`/`attempts`; `_build_message`
formats a specific message distinguishing `dns_resolution_failed` from
`page_navigation_failed`, both explicitly noting "OCR and image-audit checks
were skipped" — so this error, when it propagates up to the combined-audit
stage runner, carries enough context to explain a degraded (not merely
failed) report.

**Side effects**: creates the crawl's whole output directory tree; writes
three JSON/CSV summary files; runs the full engine crawl (browser + network +
disk).

**Used elsewhere**: instantiated by `api/v1/combined/stages.py`'s image-audit
stage as the entry point into the whole optimized-crawler subsystem.

---

## `ka11y/crawler/optimized/engine.py` (2,754 lines) — the standalone crawl engine

The largest file in the codebase. Originally a **standalone CLI script**
(`python crawl.py <seed_url> --max-depth 3 ...`, see `main()` at the bottom)
that also gets driven programmatically by `optimized_crawler.py`. Organized
here by class/section per the walkthrough's own allowance for large files.

**Imports**: `argparse`, `asyncio`, `base64`, `hashlib`, `ipaddress`, `json`,
`os`, `re`, `socket`, `sys`, `threading`, `time`, `urllib.error/parse/request/
robotparser`, `datetime.datetime/timezone`, `pathlib.Path` (stdlib);
`playwright.async_api.Error/TimeoutError/async_playwright` (third-party);
optional `tldextract` (eTLD+1 domain parsing, falls back to a small
hardcoded two-label-suffix heuristic if absent) and optional `psutil`
(browser memory watch — the whole feature no-ops if unavailable). **No
internal ka11y imports at all** — confirms this module is designed to be
fully standalone/runnable outside the FastAPI app.

### Constants & JS payloads (lines 48-451)

- `VIEWPORT = {"width": 1366, "height": 900}`, `NAV_TIMEOUT_MS = 30_000`,
  `NETWORKIDLE_TIMEOUT_MS = 10_000`, `CONTEXT_RECYCLE_PAGES = 40` (recycle a
  browser context after this many pages, to shed memory leaks — see
  `ContextPool` below), `USER_AGENT_TOKEN = "wcag-media-crawler"` (used only
  for the robots.txt `User-Agent` match, not the real browser UA).
- **Stealth configuration** (lines 58-108): `STEALTH_LAUNCH_ARGS`
  (`--disable-blink-features=AutomationControlled`, etc.), `STEALTH_UA` (a
  real desktop Chrome UA string), `STEALTH_INIT_SCRIPT` (a JS snippet
  injected via `context.add_init_script` that patches
  `navigator.webdriver`, `window.chrome`, `navigator.plugins`,
  `navigator.mimeTypes`, `navigator.languages` to look like a real browser) —
  the module comment (lines 59-63) explains this exists because
  Akamai/Cloudflare/PerimeterX-protected sites fingerprint and block
  headless automation otherwise.
- Retry/health constants: `MAX_RETRIES = 2`, `RETRY_BACKOFF_BASE = 1.0`,
  `MAX_BROWSER_RESTARTS = 3`, `MONITOR_INTERVAL_S = 5.0`;
  `_BROWSER_DOWN_MARKERS` (lines 123-131) — error substrings meaning the
  *browser process itself* died (vs. just this page failing), so those pages
  get requeued and the browser restarted rather than the page being recorded
  as a failure.
- `CRITERIA_KEYS` (lines 148-151): the WCAG SCs this engine's extraction
  covers (`1.1.1, 1.2.1-1.2.4, 1.4.2, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2`).
- **Asset-capture constants** (lines 154-217): `SCREENSHOT_TYPES` (element
  types that carry a rendered pixel asset needing capture),
  `ASSET_URL_FIELD` (per-type field holding a downloadable URL — types
  absent here always screenshot instead), `SHOT_TIMEOUT_MS = 5_000`,
  `DOWNLOAD_TIMEOUT_MS = 30_000`, `DOWNLOAD_CONCURRENCY = 10`; carousel
  limits `MAX_CAROUSEL_SLIDES = 20`, `CAROUSEL_ADVANCE_TIMEOUT_MS = 1_200`;
  `OVERLAY_CONTAINER_JS` (an in-page JS function ported from a prior
  `meghana-v2` codebase — walks up to 3 ancestors from a small image looking
  for an absolutely-positioned sibling with short overlapping text, i.e.
  "is text composited on top of this picture").
- **Carousel detection JS** (lines 219-377): `CAROUSEL_DETECT_JS` (walks up
  to 8 DOM ancestors looking for ARIA-carousel/Swiper/Slick/generic
  `data-carousel` markers, counts slides via role/class heuristics, finds a
  "next" control selector) and `CAROUSEL_ADVANCE_JS` (clicks the next
  control or dispatches an `ArrowRight` keydown fallback, then polls an
  "active slide fingerprint" — ARIA `aria-current`/`aria-selected`, Slick's
  `.slick-current`, Swiper's `.swiper-slide-active`, or a transform-based
  fallback — until it changes or times out).
- **Cookie-consent constants** (lines 379-451): `COOKIE_REJECT_RE`,
  `COOKIE_REJECT_SELECTOR`, `COOKIE_OVERLAY_SELECTORS` — functionally
  identical to `cookie_handler.py`'s equivalents (this engine keeps its own
  copy rather than importing that module, consistent with its standalone-
  script design).

### URL/robots/politeness helpers (lines 454-676)

- `_cookie_contexts(page)` / `reject_cookies(page) -> str` (lines 454-527):
  same reject-only strategy as `cookie_handler.handle_cookies` — four-tier
  locator fallback per context, wait + cleanup on success, forced overlay
  removal otherwise, `"error"` on any exception.
- `_asset_ext(url) -> str` (lines 530-536): best-effort file extension for a
  downloadable image URL, from a `data:` MIME type or the URL path suffix.
- `IFRAME_NOTE`, `VIDEO_EMBED_HOSTS` (lines 537-546): known third-party
  video-embed hosts (YouTube, Vimeo, Wistia, JW Player, Dailymotion,
  Brightcove, Facebook) — passed into `EXTRACT_JS` so embedded players are
  recognized rather than treated as generic iframes.
- `TRACKING_PARAM_RE` (lines 549-552): regex for `utm_*`/`gclid`/`fbclid`/
  etc. query params stripped during normalization.
- `_TWO_LABEL_SUFFIXES` (lines 556-560): minimal public-suffix fallback
  (`co.uk`, `co.jp`, `com.au`, etc.) used only when `tldextract` is absent.
- `registrable_domain(host) -> str` (lines 567-585): eTLD+1 via `tldextract`
  if available, else the two-label heuristic; returns the host unchanged if
  it's a literal IP.
- `normalize_url(url) -> str` (lines 588-606): lowercases scheme/netloc,
  drops default ports, strips trailing slash (except root), strips
  tracking params, drops the fragment.
- `url_slug(normalized_url) -> str` (lines 609-610): first 16 hex chars of
  the URL's SHA-1 — the filename key for that page's output JSON.
- `utc_now_iso()` (lines 613-614): `"%Y-%m-%dT%H:%M:%SZ"`.
- **`RobotsCache`** (lines 622-656): fetches and caches `robots.txt` per
  origin (`asyncio.Lock`-guarded so concurrent workers don't double-fetch);
  `allowed(url)` returns `True` if the parser couldn't be fetched at all
  ("standard practice" per the comment) or `parser.can_fetch(...)`
  otherwise; a 401/403 fetching robots.txt itself is treated as
  disallow-all.
- **`HostPoliteness`** (lines 659-676): enforces a minimum interval between
  requests to the same host via a `_next_slot: dict[host, float]` scheduled
  under a lock — `wait(host)` loops, computing the pause needed and sleeping
  outside the lock, until it can claim a slot.
- **`CrawlState`** (lines 684-720): an append-only JSONL log
  (`_state/crawl-log.jsonl`) of `enqueued`/`done` events, making a crashed
  crawl resumable — `load()` replays the log into `(enqueued: dict[url,
  depth], done: set[url])`; `record_enqueued`/`record_done` append and
  flush immediately (durability over throughput); `close()` closes the file
  handle.

### SSRF guard (duplicate copy, lines 728-817)

Functionally identical to `crawler/_ssrf_guard.py` documented above
(`_ssrf_classify_blocked`, `_ssrf_parse_literal_ip`, `_ssrf_resolve` with the
same 30s TTL cache, `ssrf_host_is_blocked`) — a separate copy rather than an
import, for the same "standalone script" reason as the cookie-consent
constants.

### `ContextPool` (lines 820-887)

Pool of persistent `BrowserContext`s multiplexed over **one** browser
process, recycled every `CONTEXT_RECYCLE_PAGES` (40) pages to shed the slow
memory leak from detached DOM nodes/cache growth on long crawls (class
docstring).
- `_route(self, route)` (lines 834-847, async): the per-context route
  handler — checks the SSRF guard first (so redirect targets are caught),
  then aborts any `resource_type == "media"` request (video/audio bytes are
  never needed — only the element's attributes are — comment lines 835-838),
  otherwise continues.
- `_new_context(self)` (lines 849-863, async): creates a context with the
  stealth UA/viewport/locale/timezone, sets the default navigation timeout,
  injects `STEALTH_INIT_SCRIPT`, installs `self._route`.
- `start(self)` (lines 865-868): pre-fills the internal `asyncio.Queue` with
  `self._size` fresh `{context, pages: 0}` slots.
- `acquire(self)` (lines 870-875): pops a slot; if it's exhausted its page
  budget (`pages >= CONTEXT_RECYCLE_PAGES`), closes it and creates a fresh
  replacement instead of returning the stale one.
- `release(self, slot)` (lines 877-879): increments the slot's page counter,
  returns it to the queue.
- `close(self)` (lines 881-886): drains the queue, closing every context.

### `BrowserManager` (lines 894-1030)

Owns **exactly one** Chromium process (per the class docstring's "locked
one-browser RAM model") and keeps it healthy: version check, restart-on-
crash, lifetime/memory-based recycling, zombie-process reaping. Concurrency
comes entirely from the `ContextPool` living inside that one browser — never
from additional `.launch()` calls.
- `_chromium_procs()` (module function, lines 894-911): via `psutil`, lists
  this process's child processes whose name contains "chrome"/"chromium"/
  "headless_shell" — returns `[]` if `psutil` is unavailable.
- `__init__` (lines 921-939): stores launch config (`sandbox`,
  `expected_version`, `max_memory_mb`, `max_lifetime_s`, `ssrf_guard`);
  `self._generation = 0` tracks browser restarts (used by workers to detect
  a stale slot after a restart they didn't cause).
- `_launch(self)` (lines 947-963, async): launches Chromium with
  `STEALTH_LAUNCH_ARGS` (plus `--no-sandbox` if `sandbox=False`), increments
  `_generation`, prints a diagnostic line to stderr (browser version,
  generation, sandbox state), warns (still to stderr) if
  `expected_version` doesn't match, then creates and starts a new
  `ContextPool`.
- `acquire`/`release` (lines 965-969): delegate straight to `self.pool`.
- `_chrome_rss_mb(self)` (lines 971-978): sums `memory_info().rss` across
  all Chromium child processes (via `_chromium_procs`), converted to MB.
- `_close_quietly(awaitable)` (staticmethod, lines 984-992): awaits with a
  5-second timeout, swallowing any exception — so tearing down a
  dead/hung browser during a restart can never itself stall forever.
- `_do_restart(self, reason)` (lines 994-1000): closes the old pool+browser
  quietly, relaunches (`_launch`, which bumps `_generation`), sleeps 0.2s.
- `restart_if_stale(self, gen)` (lines 1002-1008): called reactively by a
  worker that caught `BrowserDown`; under `_restart_lock`, restarts only if
  `gen` still matches the current generation — otherwise another worker
  already restarted concurrently, so this is a no-op (idempotency across
  concurrent workers hitting the same dead browser).
- `monitor(self)` (lines 1010-1026, async loop): every `MONITOR_INTERVAL_S`
  (5s), proactively restarts if `max_lifetime_s` has elapsed since launch,
  or if `_chrome_rss_mb()` exceeds `max_memory_mb`.
- `close(self)` (lines 1027-1032): sets `self._stop = True`, closes pool and
  browser quietly.

### In-page extraction JS (lines 1035-1866)

`SCROLL_JS` (incremental scroll-to-bottom-and-back, so lazy-loaded images
resolve their real `src` before extraction) and the much larger `EXTRACT_JS`
— a single `page.evaluate()` payload that walks the live DOM once and, per
visible element, classifies its `element_type` (img / svg variants / css
background / input[type=image] / canvas / iframe / area / audio / video),
resolves its accessible name and ARIA state, detects the OneTrust/Optanon
cookie-consent DOM subtree to exclude it from results (the `CONSENT_SCOPE_SEL`
list — this project's Kao-specific exemption, matching the "Kao-logo 1.4.3
exemption" and "OneTrust exclusion" noted as already-done in project memory),
determines which `CRITERIA_KEYS` each element is relevant to, and gathers the
1.2.1-relevant media context (nearby links/text/details) inline rather than
via a separate pass. Returns `{elements: [...], links: [...]}` (the same-page
`<a href>` list, filtered to `http(s)`).

### `Crawler` (lines 1873-2689) — the BFS orchestrator

- `__init__` (lines 1874-1918): stores all constructor parameters; computes
  `seed_domain` via `registrable_domain(normalize_url(seed_url))`;
  constructs `RobotsCache`, `HostPoliteness(delay)`, `CrawlState(out_dir)`,
  an `asyncio.Queue` frontier, a `visited: set[str]`, `pages_done` +
  `counter_lock`, and `_requeue_counts: dict[url, int]` (bounds how many
  times a single URL can be requeued after a `BrowserDown`, so a
  permanently-broken browser can't loop forever on one page).
- `_enqueue` / `_seed` (lines 1921-1952): `_seed()` handles three cases —
  resume from a prior `CrawlState` (re-enqueues everything not yet `done`,
  skipping URLs whose output JSON already exists on disk — a second
  crash-recovery layer beyond the JSONL log itself), an explicit
  `seed_urls` list (enqueues each at depth 0, no further link-following —
  paired with `max_depth=0` by the caller), or a fresh single-seed crawl.
- `_write_page_json(self, doc)` (lines 1956-1960): **side effect** —
  writes atomically via a `.json.tmp` file + `tmp.rename(path)` (rename is
  atomic on POSIX, so a concurrent reader — or a crash mid-write — never
  sees a partially-written page JSON).
- `_stub_doc(...)` (lines 1962-1991): builds a terminal "this page didn't
  produce real content" document (used for HTTP failures, non-HTML content
  types, robots.txt disallow, or exhausted retries) with every
  `CRITERIA_KEYS` entry marked `applicable: False`.
- `_process_links(self, raw_links, depth)` (lines 1995-2020): normalizes and
  dedupes discovered links, classifying each into
  `same_domain_enqueued`/`same_domain_depth_cutoff` (seen but not enqueued
  purely due to the depth cap — recorded distinctly so "coverage vs. depth
  cutoff" is diagnosable later)/`off_domain_discarded`.
- `_download_asset(self, page, url, dest)` (lines 2043-2069, async):
  decodes `data:` URIs inline, or fetches `http(s)` via
  `page.context.request.get(...)` — **re-checking the SSRF guard here too**
  (comment lines 2053-2054: `context.request` bypasses the `context.route`
  interceptor, so this is a second, necessary enforcement point, not
  redundant). Writes bytes to `dest`, creating parent dirs. Returns `False`
  (never raises) on any `PlaywrightError`/`OSError`/`ValueError`.
- `_capture_carousel_slides(...)` (lines 2075-2194, async) — documented at
  length in its own docstring (reproduced in essence): detects the carousel
  root/slide-count/next-control via `CAROUSEL_DETECT_JS`, then loops:
  advance → screenshot every now-visible carousel image not yet captured →
  dedupe via MD5 of the screenshot bytes (a repeated hash means the carousel
  looped back to a slide already seen) → stop on exhausting `max_slides`,
  all elements captured, or two consecutive non-advancing/no-new-content
  slides.
- `_capture_assets(self, page, elements, url)` (lines 2200-2441, async) —
  the central asset-capture dispatcher, whose docstring lays out the
  decision matrix documented here verbatim because it's the crux of the
  file's asset strategy:
  1. Icons/logos → **always screenshot in place** (with real background) —
     needed for accurate contrast/branding checks against the rendered UI,
     not an isolated asset. Also opportunistically captures a second,
     padded "context" screenshot (40px margin, clipped to the viewport,
     skipped if the element touches the viewport edge) plus the element's
     local bounding box within it, feeding WCAG 1.4.11's boundary-contrast
     measurement (falls back to an OCR-text-in-image proxy when absent).
  2. Text visually overlaid on an image (via `OVERLAY_CONTAINER_JS`) →
     screenshot the **overlay container**, not just the image, so the
     composited text is preserved.
  3. A non-overlay image with a fetchable URL → **queue for concurrent
     download** (Pass 2b) rather than downloading inline, since
     `page.query_selector`/`evaluate_handle`/screenshot calls share one CDP
     session and aren't safe to parallelize, but `BrowserContext.request`
     downloads are.
  4. Inline SVG / `<use>` sprites / `<canvas>` / a failed download →
     screenshot as a fallback.
  Implementation is split into **Pass 1** (carousel detection — probes every
  non-icon/logo `SCREENSHOT_TYPES` element for a carousel ancestor, grouping
  by detected root), **Pass 1b** (runs `_capture_carousel_slides` per
  group), **Pass 2** (sequential DOM-bound decisions for everything else,
  building a `download_jobs` list for anything queued rather than captured
  immediately), and **Pass 2b** (the queued downloads run concurrently,
  bounded by `asyncio.Semaphore(DOWNLOAD_CONCURRENCY)`; any that fail get a
  sequential fallback screenshot afterward, since screenshots must stay on
  the single shared page/CDP session).
- `_reveal_hidden_images(self, page)` (lines 2443-2477, async): clicks up to
  8 unique elements per interaction-group (tabs, accordions, dropdowns,
  modals, carousel-next controls, "load more" buttons), each gated by a
  visibility check, to expose images that only render after user
  interaction — pure best-effort, all exceptions swallowed per-element.
- `_attempt_page(self, page, url, depth)` (lines 2479-2565, async) — one
  navigation+extraction attempt (raises on transient/browser-down errors so
  the caller can retry/restart):
  1. `page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)`.
  2. Returns a `_stub_doc(..., "failed", ...)` immediately for HTTP ≥400, or
     `_stub_doc(..., "skipped", ...)` for a non-HTML content type — neither
     is a Python exception, both are terminal outcomes recorded as-is.
  3. Best-effort waits for `networkidle` (bounded timeout, proceeds anyway
     on timeout).
  4. Rejects cookies (if enabled), runs `SCROLL_JS`, `_reveal_hidden_images`,
     dispatches synthetic `lazyload` events via an `IntersectionObserver` for
     any `img[data-src]`-style lazy elements, waits a further 1000ms.
  5. Runs `EXTRACT_JS` to get `{elements, links}`.
  6. If `self.screenshots`, calls `_capture_assets`.
  7. Builds the `criteria` dict by popping each element's `criteria` list and
     inverting it into `{sc: {applicable, element_ids, note}}`.
  8. Calls `_process_links` on the discovered links.
  9. Returns the full success document.
- `_process_page(self, context, url, depth)` (lines 2566-2607, async): the
  robots-check + retry wrapper around `_attempt_page` — checks
  `self.robots.allowed(url)` first (writes a `skipped` stub if disallowed);
  otherwise loops up to `MAX_RETRIES + 1` attempts, waiting for host
  politeness before each, opening a fresh `page` per attempt; a
  `BrowserDown`-classified exception is **re-raised** (not retried here —
  the caller's `_worker` handles browser restart + requeue); other
  Playwright errors get exponential backoff (`RETRY_BACKOFF_BASE * 2**attempt`)
  and a retry; any other unexpected exception breaks immediately (treated as
  a page failure, no retry). On success, writes the page JSON and logs a
  one-line status. After exhausting retries, writes a `_stub_doc(...,
  "failed", ...)`.
- `_worker(self)` (lines 2611-2653, async loop): pulls `(url, depth)` from
  the frontier (or `None` as the poison-pill shutdown signal); checks the
  page-budget under `counter_lock` (drains without processing once
  `max_pages` is hit); acquires a `ContextPool` slot from `self.browser_mgr`,
  calls `_process_page`, always releases the slot; records the URL `done` in
  `CrawlState`. On `BrowserDown`: calls `restart_if_stale`, decrements
  `pages_done` (the page didn't actually get processed), and either
  requeues the URL (up to `MAX_BROWSER_RESTARTS` times) or gives up and
  writes a permanent-failure stub. Any other exception is logged and
  swallowed (the frontier task is still marked done in the `finally`, so a
  single bad page can never hang the whole crawl).
- `run(self)` (lines 2657-2688, async) — the top-level orchestration:
  creates `out_dir`, seeds the frontier, opens **one** `async_playwright()`
  context for the whole crawl, constructs and starts a `BrowserManager`,
  launches the health `monitor()` task and `self.concurrency` `_worker()`
  tasks, waits for `self.frontier.join()` (all enqueued work drained), then
  tears everything down in a `finally` (poison-pills every worker, gathers
  them, cancels the monitor, closes the browser manager, closes the crawl
  state file).

### `main()` (lines 2696-2751) — standalone CLI

Uses `argparse` to expose every `Crawler` constructor parameter as a CLI
flag (`--max-depth`, `--max-pages`, `--out-dir`, `--concurrency`, `--delay`,
`--no-screenshots`, `--keep-cookies`, `--allow-private-hosts` — explicitly
documented as needed for local fixture testing against `localhost`/private
IPs, `--no-sandbox`, `--expect-chromium`, `--browser-max-memory-mb`,
`--browser-max-lifetime`). Validates `seed_url` starts with `http(s)://`.
Runs `asyncio.run(crawler.run())`; on `KeyboardInterrupt`, prints a
resume-hint message and exits with code 130 (the standard SIGINT exit code).

**Side effects (whole module)**: launches and manages a real Chromium
process; makes outbound HTTP requests (navigation, asset downloads, robots.txt
fetches, DNS resolution); writes per-page JSON files, a JSONL crawl-state
log, and screenshot/asset files to `out_dir`.

**Used elsewhere**: `optimized_crawler.OptimizedImageCrawler.crawl_page`
constructs and runs an `_Engine` (i.e. this module's `Crawler`) against a
private `_raw/` subdirectory; can also be run directly as a script.

---

## `ka11y/crawler/universal_page.py` (1,365 lines)

**Purpose**: the "universal" page-snapshot loader — a single, parallel-BFS
crawl that captures a much broader per-page dataset (media elements,
CSS-background images, and — critically — feeds the shared
`accessibility/pipeline/` extractors per page) than the image-focused
`optimized/engine.py`. This is what backs most of the WCAG rule coverage
outside the pure image pipeline.

**Imports**: `asyncio`, `hashlib`, `json`, `os` (stdlib); `pydantic.BaseModel/
Field`; `pathlib.Path`; `typing.*`; `urllib.parse.urljoin/urlparse`
(stdlib); `playwright.async_api.BrowserContext/Page`;
`ka11y.utils.url_canonical.canonicalize_url`, `ka11y.config.logger.setup_logger`,
`ka11y.crawler.navigation.navigate_with_resilience/NavigationError`,
`ka11y.crawler.policy.CrawlPolicy`, `ka11y.crawler.cookie_handler.handle_cookies`,
`ka11y.utils.step_logger.ExecutionStepLogger` (internal); and, notably, two
imports from the **decision-policy pipeline** —
`ka11y.accessibility.pipeline.extractors.element_context_extractor.ElementContextExtractor`
and `...semantic_relationship_engine.SemanticRelationshipEngine` — this is
the "layering violation" flagged in `02-ARCHITECTURE.md`: the crawler calls
directly into the pipeline's evidence extractors so semantic context is
computed once, at snapshot time.

**Module-level constants**: `_UNIVERSAL_PARALLEL_PAGES` (line 40, env
`KA11Y_UNIVERSAL_PARALLEL_PAGES`, default 4 — how many pages crawl
concurrently against the same `BrowserContext`); `_GOTO_TIMEOUT_MS = 30_000`,
`_NETWORKIDLE_TIMEOUT_MS = 15_000`, `_DOM_STABILITY_MS = 600`,
`_DOM_STABILITY_TOTAL_MS = 12_000`, `_POST_SCROLL_WAIT_MS = 1_500`;
`_MAX_SEEN_REFS = 5_000` (hard ceiling on the extraction dedup set — without
it, an infinite-scroll page with unbounded lazy-loaded content would grow
`seen_refs` without bound across scroll passes); `_SPA_SIGNALS` (lines
55-64) — JS expressions probing for common SPA framework globals
(`window.__NEXT_DATA__`, `window.__nuxt`, `window.React`, etc.) used to wait
longer on pages that are client-rendered.

**Class `PageSnapshot(BaseModel)`** (lines 67-88): the top-level accumulator
for one crawl run — `page_url`, `media: List[Dict]`, `background_images:
List[Dict]` (from a separate `_BACKGROUND_IMAGES_JS` pass, kept out of the
main extractor "to avoid bloating its single page.evaluate payload," per an
inline comment), `pipeline_pages: List[Dict]` (each `{page_url, contexts}` —
the side-channel the `DecisionEngine` consumes offline, so it doesn't need
to re-navigate every page itself), `warnings`, `element_refs` (a flat map
from a generated ref ID to metadata about where that element came from —
category/page/frame/selector), `page_summaries`, `pages_crawled: int`,
`partial: bool` (set `True` anywhere extraction degraded rather than failed
outright), `har_path: Optional[str]`.

### Embedded in-page JS (lines 91-598)

`_COMBINED_EXTRACT_JS` — a large, `frameMeta`-parameterized extraction
function supporting **shadow-DOM traversal** (`queryShadow`/`queryShadowOne`
helper closures that walk into every `shadowRoot` found under the document,
so web-component-based sites aren't invisible to extraction) alongside the
same category of element-classification logic as `optimized/engine.py`'s
`EXTRACT_JS`, isolating each extraction *category* in its own try/catch
(surfaced back to Python as a per-frame `_errors` map — the "B-3" fix
referenced in `_extract_page`'s docstring: previously one category's failure
zeroed out all seven). The tail of this block (around line 560+) defines a
DOM-stability watcher (`_DOM_STABILITY_JS`, an f-string parameterized by
`_DOM_STABILITY_MS`/`_DOM_STABILITY_TOTAL_MS`) using a `MutationObserver`
that resolves a promise once no DOM mutation has occurred for
`stabilityMs`, or resolves `"timeout"`/`"total_timeout"` if mutations never
settle within the total budget. (`_BACKGROUND_IMAGES_JS` and
`_LINK_EXTRACT_JS`, referenced by name in the Python methods below, are
further constants in this same block, each a small standalone `page.evaluate`
payload for their one job.)

### `UniversalPageLoader` (lines 602-1365)

- `USER_AGENT` (lines 603-607): a realistic macOS Chrome UA string
  (deliberately different from `optimized/engine.py`'s Windows UA — no
  functional significance noted, just two independently-authored stealth
  configs).
- `load(cls, url, output_dir, *, max_depth=0, max_pages=50,
  internal_links=True, record_har=False, step_logger=None, policy=None,
  seed_url=None) -> PageSnapshot` (classmethod, lines 609-775, async) — the
  main entry point:
  1. Creates `output_dir`; builds a `CrawlPolicy` from the loose parameters
     if `policy` isn't supplied directly (docstring notes a past bug: this
     path used to hardcode `max_pages=50` regardless of the caller's
     request — now fixed to actually honor the passed-in values).
  2. Seeds a `deque[(url, depth)]` — either every URL in `seed_url` (an
     explicit page list) or just the root `url`.
  3. **Side effect**: leases a pooled `BrowserContext` via
     `browser_pool.leased_context(...)` (viewport 1440×900, the class's
     `USER_AGENT`; if `record_har`, adds `record_har_path`/`record_har_url_filter`
     to capture a HAR file of the whole session).
  4. Runs a **parallel BFS**: up to `_UNIVERSAL_PARALLEL_PAGES` `_crawl_one_url`
     tasks in flight at once against the shared context (one browser, many
     `Page`s); `visited` is updated *before* a task launches (so no two
     workers ever crawl the same URL) and `_can_launch()` checks
     `pages_crawled + len(inflight) < policy.max_pages` (subtracting
     in-flight tasks from the remaining budget so it can't briefly
     overshoot); as tasks complete (`asyncio.wait(..., FIRST_COMPLETED)`),
     their discovered links are pushed back onto the queue at `depth + 1`
     (only if under `max_depth` and the budget hasn't been hit) — BFS
     ordering is preserved because the queue is FIFO and the inline comment
     (lines 676-685) explains why the shared-list mutations are safe despite
     concurrency: single-threaded `asyncio` interleaving only switches
     between tasks at `await` points, and list appends happen between them.
  5. Records the HAR path if one was captured, logs a completion
     `step_logger` event, returns the populated `snapshot`.
- `_crawl_one_url(cls, *, context, root_url, url, depth, policy, output,
  step_logger) -> List[str]` (classmethod, lines 778-902, async) — one
  page's worth of work:
  1. Opens a fresh `page = await context.new_page()`.
  2. Calls `_prepare_page` (navigation + settle), then computes
     `resolved_url = canonicalize_url(page.url or "") or url` — stamped on
     every finding from this page. The inline comment (lines 804-816)
     explains why this matters: a child page discovered as `/worldwide` may
     301-redirect to `/worldwide.html`; if that same page is later audited
     directly, the direct-audit caller passes the resolved form — using the
     *queued* URL here would split one logical page's findings across two
     `page_url` buckets in the report. Uses `canonicalize_url` specifically
     because the Node engine independently stamps `page.url()` too, and both
     engines must agree on the identity string or the buckets diverge again
     between them.
  3. Calls `_extract_page_chunked` (the scroll-and-extract loop, below).
  4. Calls `_extract_pipeline_contexts` — running the shared
     `ElementContextExtractor`/`SemanticRelationshipEngine` against this
     page, so **every** BFS-visited page (not just the root) gets policy-
     pipeline coverage.
  5. Calls `_extract_links`, capped to `policy.max_links_per_page`.
  6. Appends a `page_summaries` entry (media count, links found) and
     increments `output.pages_crawled`.
  7. On `NavigationError`: appends a warning (not fatal to the whole
     snapshot — one unreachable child page doesn't abort the crawl). On any
     other exception: sets `output.partial = True` and appends a
     `page_extract_failed` warning.
  8. **Always** closes the page in a `finally`, and returns the discovered
     `links` (empty on failure) so the caller can still enqueue them if the
     exception happened after link extraction — in practice an exception
     anywhere aborts before reaching the `links = ...` line, so this mostly
     returns `[]` on failure paths.
- `_prepare_page(cls, page, url, *, step_logger)` (classmethod, lines
  904-941, async): `navigate_with_resilience` → best-effort
  `wait_for_load_state("networkidle")` → `_wait_for_spa` → `handle_cookies`
  (from `cookie_handler.py`) → a best-effort DOM-stability wait via
  `_DOM_STABILITY_JS`. Every step after navigation is wrapped so a failure
  in cookie-handling or stability-waiting never prevents extraction from at
  least being attempted.
- `_extract_page_chunked(cls, page, *, page_url, output)` (classmethod,
  lines 943-1001, async): the infinite-scroll defense. Dispatches synthetic
  lazy-load events once up front, then loops up to 4 passes: wait for DOM
  stability, call `_extract_page` (accumulating into a shared `seen_refs`
  set that survives across passes so re-extracting after a scroll doesn't
  duplicate already-seen elements), stop early if `seen_refs` hits
  `_MAX_SEEN_REFS` (marking `output.partial = True`) or if the page is
  already at the scroll bottom, else scroll down 1.5 viewport-heights and
  wait; resets scroll to top at the end.
- `_extract_pipeline_contexts(cls, *, page, page_url, output, step_logger)`
  (classmethod, lines 1003-1060, async) — explained in its own docstring
  (reproduced above in the module purpose section): runs
  `ElementContextExtractor.extract_contexts(page)` then, if any contexts
  came back, `SemanticRelationshipEngine.enrich_semantics(page, contexts)`
  (mutates in place); any exception degrades to a `pipeline_extract_failed`
  warning + an **empty** `contexts` entry (still appended to
  `output.pipeline_pages`) rather than dropping the page from pipeline
  output entirely, so `DecisionEngine` can report "no findings here" instead
  of the page vanishing silently.
- `_extract_page(cls, page, *, page_url, output, seen_refs=None) ->
  Dict[str, List[Dict]]` (classmethod, lines 1062-1152, async): collects
  every same-origin frame (`_collect_same_origin_frames`), and for each runs
  `_COMBINED_EXTRACT_JS` (skipping detached frames whose URL was
  transient/blank); on a per-frame extraction exception, builds a detailed
  `_build_frame_warning` and continues with the remaining frames rather than
  aborting; annotates and dedupes every returned record via
  `_annotate_records`; surfaces any per-category extractor faults
  (`frame_data["_errors"]`) as additional warnings; separately runs
  `_BACKGROUND_IMAGES_JS` per frame and extends `output.background_images`.
- `_annotate_records(cls, *, output, category, page_url, frame_path,
  records, seen_refs=None)` (classmethod, lines 1154-1198): for each raw
  record, stamps `page_url`/`frame_path`/`selector` defaults, computes (or
  reuses) an `element_ref_id` via `_make_ref_id`, **deduplicates against
  `seen_refs`** if provided (the mechanism that makes chunked/scrolled
  extraction not double-count elements already seen in a prior pass),
  appends to the matching `output` list (`getattr(output, category)`), and
  registers the ref in `output.element_refs`.
- `_extract_links(cls, page, root_url, policy) -> List[str]` (classmethod,
  lines 1200-1219, async): runs `_LINK_EXTRACT_JS`, resolves each href
  against `page.url` via `urljoin`, normalizes via `policy.normalize_url`,
  filters to same-origin (`_is_same_origin`), dedupes preserving order
  (`dict.fromkeys`).
- `_collect_same_origin_frames(cls, page, *, page_url, output) ->
  List[tuple]` (classmethod, lines 1222-1245, async): recursively walks
  `page.main_frame.child_frames`, building `(frame, path)` pairs where
  `path` is a dot-joined index string (`"main.0.1"`); skips (and flags
  `output.partial = True` for) any cross-origin child frame, logging why.
- `_build_frame_warning(cls, *, code, page_url, frame, frame_path, message,
  error_type=None) -> Dict` (classmethod, lines 1248-1300, async): builds a
  rich diagnostic warning dict, best-effort enriched with the `<iframe>`
  element's own attributes (`tag, id, name, title, src, sandbox, loading,
  referrerpolicy, allow, aria-label`, truncated outer HTML) if the frame's
  owning element can still be reached.
- `_wait_for_spa(page)` (staticmethod, lines 1302-1311, async): probes each
  `_SPA_SIGNALS` expression; on the first truthy hit, waits an extra 800ms
  and returns (does not check the rest).
- `_make_ref_id(...)` (staticmethod, lines 1313-1336): SHA-1 (first 16 hex
  chars) of `category|page_url|frame_path|selector|element_id|html[:120]|index`,
  prefixed with the category name — deterministic given the same inputs,
  which is what lets `_annotate_records` deduplicate across scroll passes.
- `_is_same_origin(base_url, other_url) -> bool` (staticmethod, lines
  1338-1358): scheme + hostname + (explicit or scheme-default) port
  equality; treats empty/`about:` URLs as same-origin (harmless placeholder
  frames).
- `save_snapshot(snapshot, output_dir) -> str` (staticmethod, lines
  1360-1365): **side effect** — writes `<output_dir>/universal_snapshot_raw.json`
  via `model_dump()`.

**Side effects (whole module)**: drives Playwright navigation across
potentially many pages in parallel; DOM mutation (cookie rejection, scroll);
writes `universal_snapshot_raw.json` when `save_snapshot` is called; no
direct network calls beyond what Playwright itself performs.

**Used elsewhere**: `api/v1/combined/stages.py` is the primary caller
(`UniversalPageLoader.load(...)`), feeding `snapshot_normalizer.py` and the
various rule auditors/rendered evaluators. `api/v1/pipeline.py` and
`api/v1/crawl.py` also drive it directly for their narrower endpoints (see
`07-MODULES-api.md`).
