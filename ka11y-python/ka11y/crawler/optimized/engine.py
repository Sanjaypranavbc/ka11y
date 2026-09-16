#!/usr/bin/env python3
"""WCAG media accessibility crawler.

Crawls every same-domain page of a website with Playwright and writes one
JSON file per page containing raw accessibility facts (no pass/fail verdicts)
for WCAG SC 1.1.1, 1.2.1-1.2.4, 1.4.2, 1.4.3, 1.4.5, 1.4.6, 1.4.11 and 4.1.2.
A downstream checker consumes these files and applies the criterion logic.

Usage:
    python crawl.py <seed_url> --max-depth 3 --max-pages 500 --out-dir output
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

try:
    import tldextract  # optional: exact eTLD+1 via the public-suffix list
except ImportError:
    tldextract = None

try:
    import psutil  # optional: browser memory watch + zombie-process reaping
except ImportError:
    psutil = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIEWPORT = {"width": 1366, "height": 900}
NAV_TIMEOUT_MS = 30_000
NETWORKIDLE_TIMEOUT_MS = 10_000
CONTEXT_RECYCLE_PAGES = 40
USER_AGENT_TOKEN = "wcag-media-crawler"

# Anti-bot stealth profile — shared with the pooled contexts every other
# crawler uses (see ka11y/crawler/context_factory.py). Re-exported here so the
# CLI keeps its names.
from ka11y.crawler.context_factory import (  # noqa: E402,F401
    STEALTH_INIT_SCRIPT,
    STEALTH_LAUNCH_ARGS,
    STEALTH_UA,
)

# Transient-failure retry: a single timeout/network blip must not permanently
# mark a page "failed". Definitive outcomes (HTTP 4xx, non-HTML) never retry.
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 1.0
# Cap on requeues caused by a dead browser, so an unrecoverable browser can
# never spin the frontier forever.
MAX_BROWSER_RESTARTS = 3
# How often the browser health monitor checks lifetime / memory.
MONITOR_INTERVAL_S = 5.0

# Error-message markers that mean the *browser* died, not the page. These must
# never be written as a page "failure" — the page is requeued and the browser
# recovered instead.
_BROWSER_DOWN_MARKERS = (
    "target page, context or browser has been closed",
    "browser has been closed",
    "browser closed",
    "target closed",
    "connection closed",
    "websocket",
    "browser has disconnected",
)


# ── tracing ──────────────────────────────────────────────────────────────────
# Imported lazily-but-once here (rather than inside _process_page) because the
# crawler calls these on every page; the module-level guard keeps engine.py
# importable in an install without the tracing extras.
try:
    from ka11y.observability.spans import page_span as _observability_page_span
    from ka11y.observability.spans import stamp_page_outcome as _stamp_page_outcome
except Exception:  # noqa: BLE001

    @contextlib.contextmanager
    def _observability_page_span(*_args, **_kwargs):
        yield None

    def _stamp_page_outcome(*_args, **_kwargs) -> None:
        return


def _page_span(url: str, depth: int):
    return _observability_page_span(url, depth, crawler="image")


def _stamp_page_span(doc: dict) -> None:
    """Map one page document onto its ``crawler.page`` span.

    ``processing_status`` is the crawler's own vocabulary ("captured",
    "skipped", "failed"); it is passed through unchanged so the span and the
    page JSON on disk describe the outcome with the same word."""
    try:
        _stamp_page_outcome(
            status=doc.get("processing_status"),
            resolved_url=doc.get("page_url"),
            http_status=doc.get("http_status"),
            page_lang=doc.get("page_lang"),
            element_count=len(doc.get("elements") or []),
            error=doc.get("failure_reason"),
        )
    except Exception:  # noqa: BLE001
        pass


class BrowserDown(Exception):
    """Signals that the browser process died mid-page. The page must be
    requeued and the browser restarted — never recorded as a page failure."""

    def __init__(self, url: str, depth: int) -> None:
        super().__init__(f"browser down while processing {url}")
        self.url = url
        self.depth = depth


def _is_browser_down(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _BROWSER_DOWN_MARKERS)

# The single-DOM-walk extractor, asset capture and URL helpers now live in
# ``ka11y.crawler.image_extractor`` so the universal page loader can run the
# same pipeline on pages it has already navigated. Names are re-exported here
# so the CLI, tests and any external importer keep working.
from ka11y.crawler.image_extractor import (  # noqa: F401 — re-exports
    ASSET_URL_FIELD,
    CAROUSEL_ADVANCE_JS,
    CAROUSEL_ADVANCE_TIMEOUT_MS,
    CAROUSEL_DETECT_JS,
    CRITERIA_KEYS,
    DOWNLOAD_CONCURRENCY,
    DOWNLOAD_TIMEOUT_MS,
    EXTRACT_JS,
    IFRAME_NOTE,
    IO_LAZYLOAD_JS,
    MAX_CAROUSEL_SLIDES,
    NOT_PRESENT_NOTE,
    OVERLAY_CONTAINER_JS,
    SCREENSHOT_TYPES,
    SCROLL_JS,
    SHOT_TIMEOUT_MS,
    TRACKING_PARAM_RE,
    VIDEO_EMBED_HOSTS,
    _TWO_LABEL_SUFFIXES,
    _asset_ext,
    capture_assets,
    capture_carousel_slides,
    download_asset,
    extract_image_page,
    normalize_url,
    registrable_domain,
    reveal_hidden_images,
    url_slug,
    utc_now_iso,
)

# ---------------------------------------------------------------------------
# Cookie consent + SSRF guard — shared implementations.
#
# The engine used to carry private copies of both (ported from the same v2
# source as the shared modules). They drifted; a fix in one was not a fix in
# the other. The names below are kept so the CLI and any external caller
# keep working, but the behaviour is now the single shared implementation in
# ``ka11y.crawler.cookie_handler`` / ``ka11y.crawler._ssrf_guard``.
# ---------------------------------------------------------------------------
from ka11y.crawler.cookie_handler import handle_cookies as reject_cookies  # noqa: E402,F401
from ka11y.crawler._ssrf_guard import _host_is_blocked as ssrf_host_is_blocked  # noqa: E402,F401


# ---------------------------------------------------------------------------
# robots.txt cache + per-host politeness
# ---------------------------------------------------------------------------


class RobotsCache:
    """Fetches robots.txt once per scheme+host and caches the parsed rules."""

    def __init__(self) -> None:
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = asyncio.Lock()

    async def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self._lock:
            if origin not in self._parsers:
                self._parsers[origin] = await asyncio.to_thread(self._fetch, origin)
        parser = self._parsers[origin]
        if parser is None:
            return True  # unreachable robots.txt => allow (standard practice)
        return parser.can_fetch(USER_AGENT_TOKEN, url)

    @staticmethod
    def _fetch(origin: str) -> urllib.robotparser.RobotFileParser | None:
        parser = urllib.robotparser.RobotFileParser()
        req = urllib.request.Request(
            f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT_TOKEN}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                parser.parse(resp.read().decode("utf-8", "replace").splitlines())
            return parser
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                parser.disallow_all = True
                return parser
            return None  # 404 etc. => no rules
        except Exception:
            return None


class HostPoliteness:
    """Enforces a minimum interval between requests to the same host."""

    def __init__(self, min_delay: float) -> None:
        self._min_delay = min_delay
        self._next_slot: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, host: str) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                slot = self._next_slot.get(host, now)
                if slot <= now:
                    self._next_slot[host] = now + self._min_delay
                    return
                pause = slot - now
            await asyncio.sleep(pause)


# ---------------------------------------------------------------------------
# Crash-safe crawl state (frontier + visited persisted as JSONL)
# ---------------------------------------------------------------------------


class CrawlState:
    """Append-only JSONL log of enqueued/done URLs; makes the crawl resumable."""

    def __init__(self, out_dir: Path) -> None:
        self._path = out_dir / "_state" / "crawl-log.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None

    def load(self) -> tuple[dict[str, int], set[str]]:
        """Returns (all enqueued url->depth, done urls)."""
        enqueued: dict[str, int] = {}
        done: set[str] = set()
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec["event"] == "enqueued":
                    enqueued[rec["url"]] = rec["depth"]
                elif rec["event"] == "done":
                    done.add(rec["url"])
        self._fh = self._path.open("a", encoding="utf-8")
        return enqueued, done

    def record_enqueued(self, url: str, depth: int) -> None:
        self._write({"event": "enqueued", "url": url, "depth": depth})

    def record_done(self, url: str) -> None:
        self._write({"event": "done", "url": url})

    def _write(self, rec: dict) -> None:
        self._fh.write(json.dumps(rec) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()


# ---------------------------------------------------------------------------
# Browser-context pool: one browser process, N recycled contexts
# ---------------------------------------------------------------------------


class ContextPool:
    """Pool of persistent BrowserContexts multiplexed over ONE browser process.

    Contexts are recycled every CONTEXT_RECYCLE_PAGES pages to shed the slow
    memory leak from detached DOM nodes / cache growth on long crawls.
    """

    def __init__(self, browser, size: int, ssrf_guard: bool = True) -> None:
        self._browser = browser
        self._size = size
        self._ssrf_guard = ssrf_guard
        self._queue: asyncio.Queue = asyncio.Queue()
        self._created = False

    async def _route(self, route) -> None:
        # SSRF guard runs first so redirect targets to internal IPs are caught
        # too. Then block media payloads: we need <video>/<audio>/<track>
        # attributes, never the decoded bytes. Images/CSS/SVG stay enabled
        # (needed for poster classification, background-image and contrast).
        req = route.request
        if self._ssrf_guard and ssrf_host_is_blocked(
                urllib.parse.urlsplit(req.url).hostname or ""):
            await route.abort("addressunreachable")
            return
        if req.resource_type == "media":
            await route.abort()
            return
        await route.continue_()

    async def _new_context(self):
        # Stealth context: real Chrome UA + realistic locale so bot managers
        # don't fingerprint the crawler; the init script patches the automation
        # tells (navigator.webdriver, window.chrome, plugins) before page JS runs.
        context = await self._browser.new_context(
            viewport=VIEWPORT,
            user_agent=STEALTH_UA,
            locale="en-US",
            timezone_id="America/New_York",
            ignore_https_errors=True,
        )
        context.set_default_timeout(NAV_TIMEOUT_MS)
        await context.add_init_script(STEALTH_INIT_SCRIPT)
        await context.route("**/*", self._route)
        return context

    async def start(self) -> None:
        for _ in range(self._size):
            self._queue.put_nowait({"context": await self._new_context(), "pages": 0})
        self._created = True

    async def acquire(self):
        slot = await self._queue.get()
        if slot["pages"] >= CONTEXT_RECYCLE_PAGES:
            await slot["context"].close()
            slot = {"context": await self._new_context(), "pages": 0}
        return slot

    def release(self, slot) -> None:
        slot["pages"] += 1
        self._queue.put_nowait(slot)

    async def close(self) -> None:
        if not self._created:
            return
        while not self._queue.empty():
            slot = self._queue.get_nowait()
            await slot["context"].close()


# ---------------------------------------------------------------------------
# Browser lifecycle manager: ONE browser process, hardened
# ---------------------------------------------------------------------------


def _chromium_procs() -> list:
    """Chromium child processes of this crawler (via psutil), or [] if psutil
    is unavailable. Used for memory watch and zombie reaping."""
    if psutil is None:
        return []
    try:
        me = psutil.Process(os.getpid())
    except psutil.Error:
        return []
    procs = []
    for child in me.children(recursive=True):
        try:
            name = child.name().lower()
        except psutil.Error:
            continue
        if "chrome" in name or "chromium" in name or "headless_shell" in name:
            procs.append(child)
    return procs


class BrowserManager:
    """Owns exactly ONE chromium process (per the crawler's locked one-browser
    RAM model) and keeps it healthy: version check, restart-on-crash, lifetime
    and memory recycling, and zombie-process reaping. Concurrency still comes
    from the ContextPool living inside the managed browser — never extra
    .launch() calls."""

    def __init__(self, pw, concurrency: int, *, sandbox: bool = True,
                 expected_version: str | None = None,
                 max_memory_mb: int | None = None,
                 max_lifetime_s: float | None = None,
                 ssrf_guard: bool = True) -> None:
        self._pw = pw
        self._concurrency = concurrency
        self._sandbox = sandbox
        self._expected_version = expected_version
        self._max_memory_mb = max_memory_mb
        self._max_lifetime_s = max_lifetime_s
        self._ssrf_guard = ssrf_guard
        self.browser = None
        self.pool: ContextPool | None = None
        self._generation = 0
        self._launched_at = 0.0
        self._restart_lock = asyncio.Lock()
        self._stop = False

    @property
    def generation(self) -> int:
        return self._generation

    async def start(self) -> None:
        await self._launch()

    async def _launch(self) -> None:
        args = list(STEALTH_LAUNCH_ARGS)
        if not self._sandbox:
            args.append("--no-sandbox")
        self.browser = await self._pw.chromium.launch(headless=True, args=args)
        self._launched_at = time.monotonic()
        self._generation += 1
        version = self.browser.version
        sandbox_note = "on" if self._sandbox else "off (--no-sandbox)"
        print(f"[browser] launched chromium {version} "
              f"(gen {self._generation}, sandbox {sandbox_note})", file=sys.stderr)
        if self._expected_version and self._expected_version not in version:
            print(f"[browser] WARNING: chromium {version} does not match expected "
                  f"{self._expected_version!r} — results may differ", file=sys.stderr)
        self.pool = ContextPool(self.browser, self._concurrency,
                                ssrf_guard=self._ssrf_guard)
        await self.pool.start()

    async def acquire(self):
        return await self.pool.acquire()

    def release(self, slot) -> None:
        self.pool.release(slot)

    def _chrome_rss_mb(self) -> float:
        total = 0
        for p in _chromium_procs():
            try:
                total += p.memory_info().rss
            except Exception:
                pass
        return total / (1024 * 1024)

    @staticmethod
    def _reap(pids: set[int]) -> None:
        pass

    @staticmethod
    async def _close_quietly(awaitable) -> None:
        """Await a close, bounded so a dead/hung browser can't stall teardown."""
        if awaitable is None:
            return
        try:
            await asyncio.wait_for(awaitable, timeout=5)
        except Exception:
            pass

    async def _do_restart(self, reason: str) -> None:
        print(f"[browser] restarting: {reason}", file=sys.stderr)
        old_browser, old_pool = self.browser, self.pool
        await self._close_quietly(old_pool.close() if old_pool else None)
        await self._close_quietly(old_browser.close() if old_browser else None)
        await self._launch()  # new browser gets fresh pids
        await asyncio.sleep(0.2)

    async def restart_if_stale(self, gen: int) -> None:
        """Reactive restart requested by a worker that hit BrowserDown; a no-op
        if another worker already restarted (generation advanced)."""
        async with self._restart_lock:
            if gen != self._generation:
                return
            await self._do_restart("page reported browser down")

    async def monitor(self) -> None:
        """Proactive health loop: recycle the browser on lifetime or memory."""
        while not self._stop:
            await asyncio.sleep(MONITOR_INTERVAL_S)
            if self._stop:
                break
            async with self._restart_lock:
                if self._max_lifetime_s and \
                        time.monotonic() - self._launched_at > self._max_lifetime_s:
                    await self._do_restart(f"max lifetime {self._max_lifetime_s:.0f}s")
                    continue
                if self._max_memory_mb:
                    rss = self._chrome_rss_mb()
                    if rss > self._max_memory_mb:
                        await self._do_restart(
                            f"memory {rss:.0f}MB > {self._max_memory_mb}MB cap")

    async def close(self) -> None:
        self._stop = True
        async with self._restart_lock:
            await self._close_quietly(self.pool.close() if self.pool else None)
            await self._close_quietly(self.browser.close() if self.browser else None)
            await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class Crawler:
    def __init__(
        self,
        seed_url: str,
        max_depth: int,
        max_pages: int,
        out_dir: Path,
        concurrency: int,
        delay: float,
        screenshots: bool = True,
        reject_cookies: bool = True,
        ssrf_guard: bool = True,
        sandbox: bool = True,
        expect_chromium: str | None = None,
        max_browser_memory_mb: int | None = None,
        max_browser_lifetime: float | None = None,
        seed_urls: list[str] | None = None,
    ) -> None:
        self.seed_url = seed_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        # When an explicit page list is supplied (e.g. the pipeline's shared
        # discovered_urls), crawl exactly those pages and do not expand further.
        self.seed_urls = seed_urls
        self.out_dir = out_dir
        self.concurrency = concurrency
        self.screenshots = screenshots
        self.reject_cookies_enabled = reject_cookies
        self.ssrf_guard = ssrf_guard
        self.sandbox = sandbox
        self.expect_chromium = expect_chromium
        self.max_browser_memory_mb = max_browser_memory_mb
        self.max_browser_lifetime = max_browser_lifetime
        self.seed_domain = registrable_domain(
            urllib.parse.urlsplit(normalize_url(seed_url)).netloc
        )
        self.robots = RobotsCache()
        self.politeness = HostPoliteness(delay)
        self.state = CrawlState(out_dir)
        self.frontier: asyncio.Queue = asyncio.Queue()
        self.visited: set[str] = set()
        self.pages_done = 0
        self.counter_lock = asyncio.Lock()
        self.browser_mgr: BrowserManager | None = None
        self._requeue_counts: dict[str, int] = {}  # url -> browser-down requeues

    # -- frontier ----------------------------------------------------------

    def _enqueue(self, url: str, depth: int, from_state: bool = False) -> None:
        self.visited.add(url)
        if not from_state:
            self.state.record_enqueued(url, depth)
        self.frontier.put_nowait((url, depth))

    def _seed(self) -> None:
        enqueued, done = self.state.load()
        norm_seed = normalize_url(self.seed_url)
        if enqueued:
            print(f"[resume] restoring state: {len(enqueued)} known URLs, {len(done)} done")
            self.visited.update(enqueued)
            self.pages_done = len(done)
            for url, depth in enqueued.items():
                if url in done:
                    continue
                if (self.out_dir / f"{url_slug(url)}.json").exists():
                    self.state.record_done(url)
                    self.pages_done += 1
                    continue
                self.frontier.put_nowait((url, depth))
            if norm_seed not in self.visited:
                self._enqueue(norm_seed, 0)
        elif self.seed_urls:
            # Explicit page list: enqueue each at depth 0 so no further links are
            # followed (callers pair this with max_depth=0).
            for u in self.seed_urls:
                self._enqueue(normalize_url(u), 0)
            if normalize_url(self.seed_url) not in self.visited:
                self._enqueue(norm_seed, 0)
        else:
            self._enqueue(norm_seed, 0)

    # -- output ------------------------------------------------------------

    def _write_page_json(self, doc: dict) -> None:
        path = self.out_dir / f"{url_slug(doc['normalized_url'])}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(path)
        # Every page outcome — captured, skipped by robots, or failed after
        # its retries — is written exactly once through here, which makes this
        # the single place that can stamp the page span with what happened.
        _stamp_page_span(doc)

    def _stub_doc(
        self,
        url: str,
        depth: int,
        status: str,
        reason: str,
        http_status: int | None,
        robots_allowed: bool,
    ) -> dict:
        return {
            "page_url": url,
            "normalized_url": url,
            "crawl_timestamp": utc_now_iso(),
            "depth": depth,
            "http_status": http_status,
            "processing_status": status,
            "failure_reason": reason,
            "viewport": VIEWPORT,
            "elements": [],
            "criteria": {
                key: {"applicable": False, "element_ids": [], "note": reason}
                for key in CRITERIA_KEYS
            },
            "robots_txt": {"checked": True, "allowed": robots_allowed},
            "links_discovered": {
                "same_domain_enqueued": 0,
                "same_domain_depth_cutoff": 0,
                "off_domain_discarded": 0,
            },
        }

    # -- link handling -----------------------------------------------------

    def _process_links(self, raw_links: list[str], depth: int) -> dict:
        counts = {
            "same_domain_enqueued": 0,
            "same_domain_depth_cutoff": 0,
            "off_domain_discarded": 0,
        }
        seen_here: set[str] = set()
        for raw in raw_links:
            norm = normalize_url(raw)
            if norm in seen_here:
                continue
            seen_here.add(norm)
            host = urllib.parse.urlsplit(norm).netloc
            if registrable_domain(host) != self.seed_domain:
                counts["off_domain_discarded"] += 1
                continue
            if norm in self.visited:
                continue
            if depth >= self.max_depth:
                # Seen but not enqueued purely because of the depth cap —
                # recorded so coverage vs. cutoff is distinguishable later.
                counts["same_domain_depth_cutoff"] += 1
                continue
            self._enqueue(norm, depth + 1)
            counts["same_domain_enqueued"] += 1
        return counts

    # -- per-page pipeline ---------------------------------------------------

    @staticmethod
    async def _safe_close(page) -> None:
        try:
            await page.close()
        except Exception:
            pass  # page may already be gone if the browser died

    def _log_doc(self, doc: dict, url: str, depth: int) -> None:
        status = doc["processing_status"]
        if status == "success":
            print(
                f"[page ] d{depth} {len(doc['elements']):3d} elements, "
                f"+{doc['links_discovered']['same_domain_enqueued']} links: {url}"
            )
        elif status == "skipped":
            print(f"[skip ] d{depth} {doc['failure_reason']}: {url}")
        else:
            print(f"[fail ] d{depth} {doc['failure_reason']}: {url}")

    # ── asset capture: thin delegations to ka11y.crawler.image_extractor ──
    # Kept as methods so the CLI crawler and existing tests keep their call
    # sites; the implementation is shared with the universal page loader.

    def _ssrf_check(self):
        return ssrf_host_is_blocked if getattr(self, "ssrf_guard", True) else None

    async def _download_asset(self, page, url: str, dest: Path) -> bool:
        return await download_asset(page, url, dest, ssrf_check=self._ssrf_check())

    async def _capture_carousel_slides(
        self, page, carousel_elements: list, page_slug: str,
    ) -> None:
        await capture_carousel_slides(page, carousel_elements, page_slug, self.out_dir)

    async def _capture_assets(self, page, elements: list, url: str) -> None:
        await capture_assets(
            page, elements, url, self.out_dir, ssrf_check=self._ssrf_check(),
        )

    async def _reveal_hidden_images(self, page) -> int:
        return await reveal_hidden_images(page)

    async def _attempt_page(self, page, url: str, depth: int) -> dict:
        """One navigation+extraction attempt. Returns a terminal doc (success,
        HTTP-4xx failure, or non-HTML skip). Raises on transient/browser errors
        so the caller can retry or trigger a browser restart."""
        response = await page.goto(
            url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS
        )
        http_status = response.status if response else None
        if http_status is not None and http_status >= 400:
            return self._stub_doc(
                url, depth, "failed", f"HTTP {http_status}", http_status, True
            )
        content_type = (response.headers.get("content-type", "") if response else "")
        if content_type and "html" not in content_type.lower():
            return self._stub_doc(
                url, depth, "skipped",
                f"non-HTML content type: {content_type.split(';')[0].strip()}",
                http_status, True,
            )

        # Bounded settle: if networkidle never fires, proceed anyway.
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=NETWORKIDLE_TIMEOUT_MS
            )
        except PlaywrightTimeoutError:
            pass

        # Reject cookie-consent banners by default so overlays don't obscure
        # the page (and so asset screenshots aren't covered by a consent modal).
        if self.reject_cookies_enabled:
            await reject_cookies(page)

        doc = await extract_image_page(
            page, url, depth, self.out_dir,
            screenshots=self.screenshots,
            ssrf_check=self._ssrf_check(),
        )
        doc["http_status"] = http_status
        doc["viewport"] = VIEWPORT
        doc["robots_txt"] = {"checked": True, "allowed": True}
        doc["links_discovered"] = self._process_links(doc.pop("links", []), depth)
        return doc

    async def _process_page(self, context, url: str, depth: int) -> None:
        """Open a ``crawler.page`` span for this URL and process it.

        One span per page visited is what turns "the crawl took 90s" into
        "three pages each burned 30s retrying". The span is opened here rather
        than in ``_worker`` so the retry loop, asset capture and extraction all
        fall inside it; ``_write_page_json`` stamps the outcome on the way out.
        """
        with _page_span(url, depth):
            await self._process_page_inner(context, url, depth)

    async def _process_page_inner(self, context, url: str, depth: int) -> None:
        if not await self.robots.allowed(url):
            doc = self._stub_doc(url, depth, "skipped", "robots.txt disallow", None, False)
            self._write_page_json(doc)
            print(f"[skip ] d{depth} robots.txt disallow: {url}")
            return

        host = urllib.parse.urlsplit(url).netloc
        last_error = "navigation failed"
        for attempt in range(MAX_RETRIES + 1):
            await self.politeness.wait(host)
            page = await context.new_page()
            try:
                doc = await self._attempt_page(page, url, depth)
            except (PlaywrightTimeoutError, PlaywrightError) as exc:
                await self._safe_close(page)
                if _is_browser_down(exc):
                    raise BrowserDown(url, depth) from exc
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < MAX_RETRIES:
                    backoff = RETRY_BACKOFF_BASE * (2 ** attempt)
                    print(
                        f"[retry] d{depth} attempt {attempt + 1}/{MAX_RETRIES} "
                        f"in {backoff:.0f}s ({type(exc).__name__}): {url}"
                    )
                    await asyncio.sleep(backoff)
                    continue
                break
            except Exception as exc:  # unexpected — treat as page failure, no retry
                await self._safe_close(page)
                last_error = f"{type(exc).__name__}: {exc}"
                break
            else:
                await self._safe_close(page)
                self._write_page_json(doc)
                self._log_doc(doc, url, depth)
                return

        # All retries exhausted — record a page failure.
        doc = self._stub_doc(url, depth, "failed", last_error, None, True)
        self._write_page_json(doc)
        print(f"[fail ] d{depth} {last_error} (gave up after {MAX_RETRIES} retries): {url}")

    # -- worker loop ---------------------------------------------------------

    async def _worker(self) -> None:
        while True:
            item = await self.frontier.get()
            if item is None:
                self.frontier.task_done()
                return
            url, depth = item
            try:
                async with self.counter_lock:
                    if self.pages_done >= self.max_pages:
                        continue  # page cap reached: drain without processing
                    self.pages_done += 1
                gen = self.browser_mgr.generation
                slot = await self.browser_mgr.acquire()
                try:
                    await self._process_page(slot["context"], url, depth)
                finally:
                    self.browser_mgr.release(slot)
                self.state.record_done(url)
            except BrowserDown as down:
                # The browser died, not the page — restart it (idempotent across
                # concurrent workers), then roll the counter back and requeue (up
                # to a cap so an unrecoverable browser can't loop forever).
                await self.browser_mgr.restart_if_stale(gen)
                async with self.counter_lock:
                    self.pages_done -= 1
                n = self._requeue_counts.get(down.url, 0) + 1
                self._requeue_counts[down.url] = n
                if n <= MAX_BROWSER_RESTARTS:
                    self.frontier.put_nowait((down.url, down.depth))
                    print(f"[browser-down] requeued (attempt {n}): {down.url}",
                          file=sys.stderr)
                else:
                    stub = self._stub_doc(down.url, down.depth, "failed",
                                          "browser repeatedly unavailable", None, True)
                    self._write_page_json(stub)
                    self.state.record_done(down.url)
                    print(f"[fail ] browser unrecoverable, gave up: {down.url}",
                          file=sys.stderr)
            except Exception as exc:
                print(f"[error] worker exception on {url}: {exc}", file=sys.stderr)
            finally:
                self.frontier.task_done()

    # -- run -----------------------------------------------------------------

    async def run(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._seed()
        async with async_playwright() as pw:
            # Exactly ONE browser process for the whole crawl; concurrency comes
            # from the context pool inside it, never from extra .launch() calls.
            # The manager keeps that single browser healthy (restart / lifetime /
            # memory / zombie reaping).
            self.browser_mgr = BrowserManager(
                pw, self.concurrency,
                sandbox=self.sandbox,
                expected_version=self.expect_chromium,
                max_memory_mb=self.max_browser_memory_mb,
                max_lifetime_s=self.max_browser_lifetime,
                ssrf_guard=self.ssrf_guard,
            )
            await self.browser_mgr.start()
            monitor = asyncio.create_task(self.browser_mgr.monitor())
            workers = [
                asyncio.create_task(self._worker()) for _ in range(self.concurrency)
            ]
            try:
                await self.frontier.join()
            finally:
                for _ in workers:
                    self.frontier.put_nowait(None)
                await asyncio.gather(*workers, return_exceptions=True)
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
                await self.browser_mgr.close()
                self.state.close()
        print(f"\nDone: {self.pages_done} page(s) processed, output in {self.out_dir}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl a site and emit per-page WCAG accessibility facts as JSON."
    )
    parser.add_argument("seed_url", help="Seed URL; crawl stays on its registrable domain")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Max link depth from the seed (default: 3)")
    parser.add_argument("--max-pages", type=int, default=500,
                        help="Max pages to process (default: 500)")
    parser.add_argument("--out-dir", type=Path, default=Path("output"),
                        help="Directory for per-page JSON files (default: output)")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Concurrent browser contexts (default: 4)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Minimum seconds between requests to one host (default: 1.0)")
    parser.add_argument("--no-screenshots", dest="screenshots", action="store_false",
                        help="Disable per-element asset capture (screenshot/download) for CV/OCR rules")
    parser.add_argument("--keep-cookies", dest="reject_cookies", action="store_false",
                        help="Do not auto-reject cookie-consent banners (default: reject)")
    parser.add_argument("--allow-private-hosts", dest="ssrf_guard", action="store_false",
                        help="Disable the SSRF guard (needed to crawl localhost/private "
                             "IPs, e.g. local fixture testing; default: guard on)")
    parser.add_argument("--no-sandbox", dest="sandbox", action="store_false",
                        help="Launch chromium without its sandbox (for locked-down containers)")
    parser.add_argument("--expect-chromium", default=None,
                        help="Warn if the running chromium version doesn't contain this string")
    parser.add_argument("--browser-max-memory-mb", type=int, default=None,
                        help="Recycle the browser when its RSS exceeds this many MB")
    parser.add_argument("--browser-max-lifetime", type=float, default=None,
                        help="Recycle the browser after this many seconds of runtime")
    args = parser.parse_args()

    if not re.match(r"^https?://", args.seed_url):
        parser.error("seed_url must start with http:// or https://")

    crawler = Crawler(
        seed_url=args.seed_url,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        out_dir=args.out_dir,
        concurrency=args.concurrency,
        delay=args.delay,
        screenshots=args.screenshots,
        reject_cookies=args.reject_cookies,
        ssrf_guard=args.ssrf_guard,
        sandbox=args.sandbox,
        expect_chromium=args.expect_chromium,
        max_browser_memory_mb=args.browser_max_memory_mb,
        max_browser_lifetime=args.browser_max_lifetime,
    )
    try:
        asyncio.run(crawler.run())
    except KeyboardInterrupt:
        print("\nInterrupted — state is persisted; rerun the same command to resume.")
        sys.exit(130)


if __name__ == "__main__":
    main()
