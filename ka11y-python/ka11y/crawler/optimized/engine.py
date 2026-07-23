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

# ---------------------------------------------------------------------------
# Anti-bot stealth (ported from meghana-v2 crawler/stealth_context.py). Many
# sites behind Akamai / Cloudflare / PerimeterX block automated browsers by
# fingerprinting navigator.webdriver, missing window.chrome / plugins, and the
# "HeadlessChrome" UA. We present a real Chrome UA and patch those tells so the
# crawler reaches pages a bot manager would otherwise serve a challenge page.
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--window-size=1366,900",
]
STEALTH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
if (!window.chrome) {
    window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} },
                      loadTimes: function(){ return {}; }, csi: function(){ return {}; }, app: {} };
}
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', { get: () => {
        const arr = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n) || null;
        arr.refresh = () => {};
        return arr;
    }, configurable: true });
}
if (navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, 'mimeTypes', { get: () => {
        const arr = [
            { type: 'application/pdf', description: 'Portable Document Format' },
            { type: 'text/pdf', description: 'Portable Document Format' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (t) => arr.find(m => m.type === t) || null;
        return arr;
    }, configurable: true });
}
if (!navigator.languages || navigator.languages.length === 0) {
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
}
"""

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

CRITERIA_KEYS = [
    "1.1.1", "1.2.1", "1.2.2", "1.2.3", "1.2.4", "1.4.2",
    "1.4.3", "1.4.5", "1.4.6", "1.4.11", "4.1.2",
]
NOT_PRESENT_NOTE = "element is not present on this page"

# Image/graphic element types that carry a rendered pixel asset a downstream
# CV/OCR checker needs (images-of-text 1.4.5, non-text content 1.1.1, non-text
# contrast 1.4.11). Per element we either SCREENSHOT (only when text is overlaid
# on the image, so the composited text is captured) or DOWNLOAD the original
# bytes (everything else). The crawler captures pixels; it never runs OCR/CV.
SCREENSHOT_TYPES = {
    "img", "svg_via_img", "svg_inline", "svg_via_object", "svg_via_use",
    "css_background_image", "css_background_svg", "input_image", "canvas",
    "video_poster",
}
# Per asset type, the element field holding a downloadable URL. Types absent
# here (inline svg, <use> sprites, canvas) have no fetchable source, so they
# are always screenshotted as a fallback.
ASSET_URL_FIELD = {
    "img": "src", "svg_via_img": "src", "input_image": "src",
    "svg_via_object": "data_url", "video_poster": "poster_url",
    "css_background_image": "resolved_background_url",
    "css_background_svg": "resolved_background_url",
}
SHOT_TIMEOUT_MS = 5_000
DOWNLOAD_TIMEOUT_MS = 30_000

# Text-overlay detection (ported from meghana-v2 classifier.get_visual_container):
# if a small image, keep it; otherwise walk up to 3 ancestors and return the
# first container that has an absolutely-positioned sibling with short text
# overlapping the image (i.e. text is composited on top of the picture). If none
# is found it returns the image itself, so the caller can tell overlay from not.
OVERLAY_CONTAINER_JS = """el => {
    const imgRect = el.getBoundingClientRect();
    if (imgRect.width < 60 || imgRect.height < 60) return el;
    let cur = el.parentElement;
    for (let i = 0; i < 3; i++) {
        if (!cur || cur.tagName === "BODY" || cur.tagName === "HTML") break;
        const rect = cur.getBoundingClientRect();
        if ((rect.width * rect.height) / (imgRect.width * imgRect.height) > 2) break;
        const hasOverlay = Array.from(cur.children).some(ch => {
            if (ch === el) return false;
            const cs = window.getComputedStyle(ch);
            const cr = ch.getBoundingClientRect();
            const txt = (ch.innerText || "").trim();
            const overlaps = !(cr.right < imgRect.left || cr.left > imgRect.right ||
                               cr.bottom < imgRect.top || cr.top > imgRect.bottom);
            return cs.position === "absolute" && overlaps &&
                   txt.length > 3 && txt.length < 200;
        });
        if (hasOverlay) return cur;
        cur = cur.parentElement;
    }
    return el;
}"""

# Cookie-consent handling (ported/trimmed from meghana-v2 cookie_handler):
# reject-first only (never accept), then strip leftover overlay backdrops.
COOKIE_STABILIZE_MS = 800
COOKIE_CLICK_TIMEOUT_MS = 1_500
COOKIE_REJECT_RE = re.compile(
    r"^(reject|decline|no\s*thanks|continue\s*without|deny|reject\s*all|decline\s*all)$",
    re.IGNORECASE,
)
COOKIE_REJECT_SELECTOR = "#onetrust-reject-all-handler, .cookie-reject, #W0wltc"
COOKIE_OVERLAY_SELECTORS = [
    "#onetrust-consent-sdk", "#onetrust-banner-sdk", ".cc-window", ".cookie-banner",
    "[id*='cookie-banner']", "[id*='cookiebanner']", "[id*='consent-banner']",
    "[id*='cookie']", "[id*='consent']", "[class*='cookie-banner']",
    "[class*='cookiebanner']", "[class*='consent-banner']", "[class*='cookie']",
    "[class*='consent']", ".optanon-alert-box-wrapper", ".onetrust-pc-dark-filter",
    ".qc-cmp2-container", ".didomi-popup-container", "#CybotCookiebotDialog",
]


def _cookie_contexts(page):
    """The page plus every (nested) frame — consent banners often live in an iframe."""
    contexts = [page]

    def walk(frame):
        for child in frame.child_frames:
            contexts.append(child)
            walk(child)

    walk(page.main_frame)
    return contexts


async def reject_cookies(page) -> str:
    """Reject cookie-consent banners by default, then remove any leftover overlay.
    Never accepts. Best-effort and non-fatal. Returns 'rejected', 'removed',
    'none', or 'error'."""
    try:
        contexts = _cookie_contexts(page)
        rejected = False
        for ctx in contexts:
            for locator in (
                ctx.get_by_role("button", name=COOKIE_REJECT_RE).first,
                ctx.locator(
                    "button, a, input[type='button'], input[type='submit'], [role='button']"
                ).filter(has_text=COOKIE_REJECT_RE).first,
                ctx.locator(COOKIE_REJECT_SELECTOR).first,
            ):
                try:
                    if await locator.is_visible(timeout=500):
                        await locator.click(timeout=COOKIE_CLICK_TIMEOUT_MS)
                        rejected = True
                        break
                except PlaywrightError:
                    continue

        removed = False
        for ctx in contexts:
            for selector in COOKIE_OVERLAY_SELECTORS:
                try:
                    for element in await ctx.locator(selector).all():
                        try:
                            if await element.is_visible(timeout=100):
                                await element.evaluate("node => node.remove()")
                                removed = True
                        except PlaywrightError:
                            continue
                except PlaywrightError:
                    continue

        if rejected:
            await page.wait_for_timeout(COOKIE_STABILIZE_MS)
            return "rejected"
        if removed:
            return "removed"
        return "none"
    except PlaywrightError:
        return "error"


def _asset_ext(url: str) -> str:
    """Best-effort file extension for a downloaded image URL."""
    if url.startswith("data:"):
        m = re.match(r"data:[\w.+-]+/([\w.+-]+)", url)
        return "." + m.group(1).split("+")[0] if m else ".bin"
    ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1]
    return ext if re.match(r"^\.[A-Za-z0-9]{1,5}$", ext) else ".bin"
IFRAME_NOTE = "manual check required — captions/tracks unverifiable via DOM"

# Known third-party video-embed hosts (config list, per the iframe rule).
VIDEO_EMBED_HOSTS = [
    "youtube.com", "youtube-nocookie.com", "youtu.be",
    "vimeo.com", "player.vimeo.com",
    "wistia.com", "wistia.net", "fast.wistia.net",
    "jwplayer.com", "content.jwplatform.com",
    "dailymotion.com", "players.brightcove.net", "facebook.com/plugins/video",
]

# Query params stripped during URL normalization.
TRACKING_PARAM_RE = re.compile(
    r"^(utm_\w+|gclid|fbclid|msclkid|mc_eid|mc_cid|igshid|ref_src|_hs\w+)$",
    re.IGNORECASE,
)

# Minimal multi-label public-suffix fallback used only when tldextract is
# absent; enough to keep the boundary sane on common hosts.
_TWO_LABEL_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "co.jp", "ne.jp", "or.jp",
    "com.au", "net.au", "org.au", "co.nz", "co.in", "com.br", "com.mx",
    "co.za", "com.sg", "com.hk", "co.kr",
}

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def registrable_domain(host: str) -> str:
    """eTLD+1 of a hostname; falls back to a small heuristic without tldextract."""
    host = host.lower().rstrip(".").split(":")[0]
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    if tldextract is not None:
        ext = tldextract.extract(host)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _TWO_LABEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def normalize_url(url: str) -> str:
    """Strip fragment + tracking params, normalize trailing slash and case."""
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    # Drop default ports.
    if (scheme, parts.port) in (("http", 80), ("https", 443)):
        netloc = parts.hostname or netloc
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = urllib.parse.urlencode(
        [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if not TRACKING_PARAM_RE.match(k)
        ]
    )
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def url_slug(normalized_url: str) -> str:
    return hashlib.sha1(normalized_url.encode("utf-8")).hexdigest()[:16]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


# ---------------------------------------------------------------------------
# SSRF guard (ported from meghana-v2 crawler/_ssrf_guard.py): block requests
# to private/loopback/link-local/reserved IPs so the crawler can't be pointed
# at internal services or the cloud metadata endpoint (169.254.169.254).
# ---------------------------------------------------------------------------
_SSRF_DNS_TTL = 30.0
_SSRF_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"), ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("192.0.0.0/24"), ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"), ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]
_ssrf_dns_cache: dict[str, tuple[float, tuple[str, ...]]] = {}
_ssrf_dns_lock = threading.Lock()


def _ssrf_classify_blocked(addr) -> bool:
    if (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_multicast or addr.is_reserved or addr.is_unspecified):
        return True
    if any(addr in net for net in _SSRF_BLOCKED_NETWORKS):
        return True
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _ssrf_classify_blocked(addr.ipv4_mapped)
    return False


def _ssrf_parse_literal_ip(host: str):
    """IP for any literal form of host — dotted quad, IPv6, IPv4-mapped, or
    pure-decimal/hex/octal integer (e.g. 2130706433, 0x7f000001). None if a
    real hostname."""
    if not host:
        return None
    cleaned = host.strip("[]")
    try:
        return ipaddress.ip_address(cleaned)
    except ValueError:
        pass
    if cleaned.isdigit() or (len(cleaned) >= 2 and cleaned[0] == "0"
                             and cleaned[1] in "xXoObB"):
        try:
            return ipaddress.ip_address(int(cleaned, 0))
        except (ValueError, OverflowError):
            return None
    return None


def _ssrf_resolve(host: str) -> tuple[str, ...]:
    """TTL-bounded getaddrinfo so a host that rebinds to a private IP after
    first contact is re-checked rather than trusted forever."""
    now = time.monotonic()
    with _ssrf_dns_lock:
        cached = _ssrf_dns_cache.get(host)
        if cached is not None and (now - cached[0]) < _SSRF_DNS_TTL:
            return cached[1]
    try:
        infos = socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        infos = []
    seen: list[str] = []
    for info in infos:
        ip = info[4][0] if info[4] else None
        if ip and ip not in seen:
            seen.append(ip)
    answers = tuple(seen)
    with _ssrf_dns_lock:
        if len(_ssrf_dns_cache) > 4096:
            _ssrf_dns_cache.clear()
        _ssrf_dns_cache[host] = (now, answers)
    return answers


def ssrf_host_is_blocked(host: str) -> bool:
    """True if host (literal IP or hostname) resolves to any blocked IP."""
    if not host:
        return False
    if host.lower() in ("localhost", "ip6-localhost", "ip6-loopback"):
        return True
    literal = _ssrf_parse_literal_ip(host)
    if literal is not None:
        return _ssrf_classify_blocked(literal)
    for ip in _ssrf_resolve(host):
        try:
            if _ssrf_classify_blocked(ipaddress.ip_address(ip)):
                return True
        except ValueError:
            continue
    return False


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
# In-page extraction (single DOM walk)
# ---------------------------------------------------------------------------

SCROLL_JS = """
async () => {
    // Incremental scroll to the bottom so lazy-loaded images resolve their
    // real src before extraction, then return to the top.
    const step = window.innerHeight;
    const pause = ms => new Promise(r => setTimeout(r, ms));
    let last = -1;
    for (let i = 0; i < 40; i++) {
        window.scrollBy(0, step);
        await pause(150);
        const y = window.scrollY;
        if (y + window.innerHeight >= document.documentElement.scrollHeight - 2) break;
        if (y === last) break;
        last = y;
    }
    window.scrollTo(0, 0);
    await pause(200);
}
"""

EXTRACT_JS = r"""
(embedHosts) => {
    const NOTE_IFRAME = "manual check required — captions/tracks unverifiable via DOM";
    const records = [];
    let counter = 0;
    const nextId = () => "el_" + String(++counter).padStart(4, "0");
    const SKIP_TAGS = new Set(["script","style","noscript","template","meta",
                               "link","title","head","base","track","source","br","wbr"]);

    // ---------- generic helpers ----------
    const cssPath = (el) => {
        const parts = [];
        let node = el;
        while (node && node.nodeType === 1 && node.tagName.toLowerCase() !== "html") {
            let sel = node.tagName.toLowerCase();
            if (node.id) {
                parts.unshift(sel + "#" + CSS.escape(node.id));
                break;
            }
            const parent = node.parentElement;
            if (parent) {
                const sibs = Array.from(parent.children)
                    .filter(c => c.tagName === node.tagName);
                if (sibs.length > 1) sel += `:nth-of-type(${sibs.indexOf(node) + 1})`;
            }
            parts.unshift(sel);
            node = parent;
        }
        return parts.join(" > ");
    };
    const snippet = (el) => (el.outerHTML || "").slice(0, 300);
    const bbox = (el) => {
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.x + window.scrollX), y: Math.round(r.y + window.scrollY),
                 width: Math.round(r.width), height: Math.round(r.height) };
    };
    const isRendered = (el) => {
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden") return false;
        const r = el.getBoundingClientRect();
        return !(r.width === 0 && r.height === 0);
    };
    const isVisible = (el) =>
        isRendered(el) && el.closest('[aria-hidden="true"]') === null;
    const absUrl = (u) => { try { return new URL(u, location.href).href; } catch { return null; } };
    const attr = (el, name) => el.hasAttribute(name) ? el.getAttribute(name) : null;
    const resolveLabelledby = (el) => {
        const ids = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
        if (!ids.length) return null;
        const text = ids.map(id => {
            const t = document.getElementById(id);
            return t ? t.textContent.trim() : "";
        }).join(" ").trim();
        return text || null;
    };
    const figcaptionText = (el) => {
        const fig = el.closest("figure");
        if (!fig) return null;
        const fc = fig.querySelector("figcaption");
        return fc ? fc.textContent.trim() : null;
    };
    // Best-effort accessible-name computation (accname precedence subset),
    // recorded as a cross-check against the raw attribute reads.
    const accName = (el) => {
        const lb = resolveLabelledby(el);
        if (lb !== null) return lb;
        const al = attr(el, "aria-label");
        if (al !== null && al.trim() !== "") return al;
        if (el.tagName.toLowerCase() === "img" && el.hasAttribute("alt"))
            return el.getAttribute("alt");
        if (el.tagName.toLowerCase() === "svg") {
            const t = el.querySelector(":scope > title");
            if (t) return t.textContent.trim();
        }
        const ti = attr(el, "title");
        if (ti !== null && ti.trim() !== "") return ti;
        return "";
    };
    const isTransparent = (color) => {
        if (color === "transparent") return true;
        const m = /^rgba\((?:[\d.]+,\s*){3}([\d.]+)\)$/.exec(color);
        return m !== null && parseFloat(m[1]) === 0;
    };
    // Ancestor background chain: walk up collecting background-color+opacity,
    // stopping at (and including) the first opaque background found.
    const bgChain = (el) => {
        const chain = [];
        let node = el.parentElement;
        while (node) {
            const cs = getComputedStyle(node);
            const entry = {
                selector: cssPath(node),
                background_color: cs.backgroundColor,
                opacity: parseFloat(cs.opacity),
            };
            chain.push(entry);
            if (!isTransparent(cs.backgroundColor) && entry.opacity > 0) break;
            node = node.parentElement;
        }
        return chain;
    };
    const bgImageUrl = (cs) => {
        const m = /url\((['"]?)(.*?)\1\)/.exec(cs.backgroundImage);
        return m ? absUrl(m[2]) : null;
    };

    // ---------- prepass: video-poster + schema.org VideoObject evidence ----------
    const posterUrlToVideo = new Map();
    for (const v of document.querySelectorAll("video[poster]")) {
        const u = absUrl(v.getAttribute("poster"));
        if (u) posterUrlToVideo.set(u, v);
    }
    const videoObjectThumbs = new Set();
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
        try {
            const stack = [JSON.parse(s.textContent)];
            while (stack.length) {
                const item = stack.pop();
                if (Array.isArray(item)) { stack.push(...item); continue; }
                if (!item || typeof item !== "object") continue;
                const type = item["@type"];
                const isVideo = type === "VideoObject" ||
                    (Array.isArray(type) && type.includes("VideoObject"));
                if (isVideo) {
                    for (const key of ["thumbnailUrl", "image"]) {
                        const v = item[key];
                        for (const u of Array.isArray(v) ? v : (v ? [v] : [])) {
                            if (typeof u === "string") {
                                const abs = absUrl(u);
                                if (abs) videoObjectThumbs.add(abs);
                            }
                        }
                    }
                }
                stack.push(...Object.values(item));
            }
        } catch {}
    }
    const inVideoObjectScope = (el) =>
        el.closest('[itemtype*="schema.org/VideoObject"]') !== null;
    // Strict decision tree: poster attribute, then schema.org VideoObject.
    // No classname / play-button / surrounding-text guessing.
    const classifyPoster = (el, srcAbs) => {
        if (srcAbs && posterUrlToVideo.has(srcAbs))
            return { rule: "video[poster] attribute", videoEl: posterUrlToVideo.get(srcAbs) };
        if ((srcAbs && videoObjectThumbs.has(srcAbs)) || inVideoObjectScope(el))
            return { rule: "schema.org VideoObject", videoEl: null };
        return null;
    };

    // ---------- media helpers ----------
    const liveSignals = (el) => {
        const signals = [];
        for (const a of el.attributes) {
            if (/^data-.*live/i.test(a.name)) { signals.push(`${a.name} attribute`); break; }
        }
        const src = el.currentSrc || attr(el, "src") || "";
        if (/\.m3u8(\?|$)/i.test(src)) signals.push("HLS .m3u8 source URL");
        const scope = el.parentElement?.parentElement || el.parentElement;
        if (scope) {
            for (const cand of scope.querySelectorAll("*")) {
                if (cand.children.length === 0 && cand.textContent.trim() === "LIVE") {
                    signals.push("standalone LIVE badge text nearby");
                    break;
                }
            }
        }
        return signals;
    };
    const transcriptLink = (el) => {
        const scopes = [el.parentElement, el.parentElement?.parentElement,
                        el.closest("figure")].filter(Boolean);
        for (const scope of scopes) {
            for (const a of scope.querySelectorAll("a[href]")) {
                if (/transcript/i.test(a.textContent) || /transcript/i.test(a.getAttribute("href"))) {
                    return cssPath(a);
                }
            }
        }
        return null;
    };
    // 1.2.1 transcript context (ported from meghana-v2 media_crawler): hand the
    // checker every nearby link, the surrounding text, and any <details> blocks
    // so it can decide whether a transcript / text-alternative is present.
    const mediaNearbyLinks = (el) => {
        const links = [];
        const seen = new Set();
        let container = el.parentElement;
        for (let i = 0; i < 3 && container; i++) {
            for (const a of container.querySelectorAll("a[href]")) {
                const href = a.getAttribute("href") || "";
                const text = (a.innerText || a.textContent || "").trim();
                if (href && text && !seen.has(href)) {
                    seen.add(href);
                    links.push({ href: absUrl(href), text: text.slice(0, 200) });
                }
            }
            container = container.parentElement;
        }
        return links;
    };
    const mediaNearbyText = (el) => {
        const parent = el.parentElement;
        return parent ? (parent.innerText || parent.textContent || "").trim().slice(0, 500) : "";
    };
    const mediaNearbyDetails = (el) => {
        const details = [];
        const seen = new Set();
        let container = el.parentElement;
        for (let i = 0; i < 3 && container; i++) {
            for (const d of container.querySelectorAll("details")) {
                if (seen.has(d)) continue;
                seen.add(d);
                const summary = d.querySelector("summary");
                details.push({
                    summary: (summary ? summary.innerText || "" : "").trim().slice(0, 200),
                    content: (d.innerText || "").trim().slice(0, 1000),
                });
            }
            container = container.parentElement;
        }
        return details;
    };
    const ariaDescribedByText = (el) => {
        const ids = (attr(el, "aria-describedby") || "").trim();
        if (!ids) return null;
        const texts = [];
        for (const id of ids.split(/\s+/)) {
            const t = document.getElementById(id);
            if (t) texts.push((t.innerText || t.textContent || "").trim());
        }
        return texts.length ? texts.join(" ").slice(0, 1000) : null;
    };
    const mediaTranscriptContext = (el) => ({
        nearby_links: mediaNearbyLinks(el),
        nearby_text: mediaNearbyText(el),
        nearby_details: mediaNearbyDetails(el),
        aria_describedby_text: ariaDescribedByText(el),
    });
    const trackList = (el) => Array.from(el.querySelectorAll(":scope > track")).map(t => ({
        kind: attr(t, "kind") || "subtitles",
        srclang: attr(t, "srclang"),
        label: attr(t, "label"),
        default: t.hasAttribute("default"),
    }));

    // ---------- image-of-text heuristics (1.4.5, no OCR) ----------
    const imageOfTextSignals = (el, altValue, srcAbs) => {
        const signals = [];
        if (altValue && /\w+\s+\w+.*[.!?]$/.test(altValue.trim()) && altValue.trim().split(/\s+/).length >= 3)
            signals.push("alt_text_reads_as_sentence");
        const r = el.getBoundingClientRect();
        if (r.height > 0 && r.width / r.height > 3) signals.push("aspect_ratio_matches_text_banner");
        const haystack = [srcAbs || "", el.className || "", el.id || ""].join(" ");
        const hints = (haystack.match(/banner|quote|heading|headline|caption|text/gi) || [])
            .map(h => h.toLowerCase());
        if (hints.length) signals.push("filename_or_class_hints");
        return {
            alt_text_reads_as_sentence: signals.includes("alt_text_reads_as_sentence"),
            aspect_ratio_matches_text_banner: signals.includes("aspect_ratio_matches_text_banner"),
            filename_or_class_hints: [...new Set(hints)],
            possible_image_of_text: signals.length > 0,
            signals,
        };
    };

    // ---------- 4.1.2 helpers ----------
    const IMPLICIT_INPUT_ROLES = { button: "button", submit: "button", reset: "button",
        image: "button", checkbox: "checkbox", radio: "radio", range: "slider",
        number: "spinbutton", search: "searchbox" };
    const implicitRole = (el) => {
        const tag = el.tagName.toLowerCase();
        if (tag === "a") return el.hasAttribute("href") ? "link" : null;
        if (tag === "button") return "button";
        if (tag === "select") return el.multiple || el.size > 1 ? "listbox" : "combobox";
        if (tag === "textarea") return "textbox";
        if (tag === "input") {
            const type = (attr(el, "type") || "text").toLowerCase();
            if (type === "hidden") return null;
            return IMPLICIT_INPUT_ROLES[type] || "textbox";
        }
        return null;
    };
    const labelForText = (el) => {
        if (!["input", "select", "textarea"].includes(el.tagName.toLowerCase())) return null;
        if (el.id) {
            const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
            if (lab) return lab.textContent.trim();
        }
        const wrap = el.closest("label");
        return wrap ? wrap.textContent.trim() : null;
    };

    // ---------- criteria tagging ----------
    const push = (rec, criteria) => {
        rec.criteria = criteria;
        records.push(rec);
        return rec;
    };
    const baseFields = (el, elementType) => ({
        id: nextId(),
        tag_name: el.tagName.toLowerCase(),
        element_type: elementType,
        selector: cssPath(el),
        outer_html_snippet: snippet(el),
        bounding_box: bbox(el),
        visible: isVisible(el),
    });
    const imageNameFields = (el) => ({
        alt_present: el.hasAttribute("alt"),
        alt_value: attr(el, "alt"),
        aria_label: attr(el, "aria-label"),
        aria_labelledby_resolved_text: resolveLabelledby(el),
        title_attr: attr(el, "title"),
        role: attr(el, "role"),
        figcaption_text: figcaptionText(el),
        accessibility_snapshot_name: accName(el),
    });

    // ---------- image classification (functional / decorative / complex /
    // informative) — DOM context + geometry heuristics, mirroring the
    // meghana-v2 classifier decision tree. Visual checks (logo/icon/chart) are
    // heuristic; a CV model can refine sub_type downstream.
    const _ctlAccName = (ctl) => {
        const lb = resolveLabelledby(ctl);
        if (lb) return lb;
        const al = ctl.getAttribute("aria-label");
        if (al && al.trim()) return al.trim();
        const txt = (ctl.textContent || "").trim();
        if (txt) return txt;
        const ti = ctl.getAttribute("title");
        return ti ? ti.trim() : "";
    };
    const imageContext = (el) => {
        const link = el.closest("a");
        const realLink = (link && link.hasAttribute("href")) ? link : null;
        const button = el.closest("button");
        const isInputImage = el.tagName.toLowerCase() === "input" &&
            (attr(el, "type") || "").toLowerCase() === "image";
        const selfArea = el.tagName.toLowerCase() === "area" && el.hasAttribute("href");
        const hasClick = el.closest('[onclick],[role="button"],[role="link"]') !== null;
        const ctl = realLink || button;
        const linkText = ctl ? (ctl.textContent || "").trim() : "";
        const tags = [], roles = [];
        let node = el.parentElement, hops = 0;
        while (node && hops < 6) {
            tags.push(node.tagName.toLowerCase());
            const r = node.getAttribute("role");
            if (r) roles.push(r.toLowerCase());
            node = node.parentElement; hops++;
        }
        return {
            in_link: link !== null || selfArea,
            in_real_link: realLink !== null || selfArea,
            in_button: button !== null || isInputImage,
            has_click: hasClick,
            link_href: realLink ? absUrl(realLink.getAttribute("href"))
                : (selfArea ? absUrl(el.getAttribute("href")) : null),
            link_has_visible_text: linkText.length > 0,
            is_sole_content: ctl !== null && linkText.length === 0,
            is_in_labeled_control: ctl !== null && _ctlAccName(ctl).length > 0,
            ancestor_tags: tags,
            ancestor_roles: roles,
        };
    };
    const decorativeSignals = (el, altPresent, altValue) => ({
        alt_empty: altPresent === true && (altValue || "") === "",
        role_presentation: ["presentation", "none"].includes(
            (attr(el, "role") || "").toLowerCase()),
        aria_hidden: el.closest('[aria-hidden="true"]') !== null,
    });
    const complexSignals = (el) => {
        const ids = (attr(el, "aria-describedby") || "").split(/\s+/).filter(Boolean);
        let desc = null;
        if (ids.length) {
            const t = ids.map(i => { const n = document.getElementById(i);
                return n ? n.textContent.trim() : ""; }).join(" ").trim();
            desc = t || null;
        }
        return {
            has_longdesc: el.hasAttribute("longdesc"),
            aria_describedby_text: desc,
            in_figure: el.closest("figure") !== null,
        };
    };
    const _clsHint = (el, src, alt, re) =>
        re.test([src || "", el.className || "", el.id || "", alt || ""].join(" "));
    const looksLikeIcon = (el, src) => {
        const r = el.getBoundingClientRect();
        const small = r.width > 0 && r.height > 0 && r.width <= 64 && r.height <= 64;
        const square = r.height > 0 && Math.abs(r.width / r.height - 1) < 0.4;
        const sprite = el.tagName.toLowerCase() === "svg" && el.querySelector("use") !== null;
        return (small && square) || sprite || _clsHint(el, src, "", /icon|glyph|symbol/i);
    };
    const looksLikeLogo = (el, src, alt) => {
        const inBanner = el.closest('header,[role="banner"],nav,[role="navigation"]') !== null;
        const r = el.getBoundingClientRect();
        return _clsHint(el, src, alt, /logo|brand|wordmark/i) || (inBanner && r.top < 220);
    };
    const looksLikeChart = (el, src, alt) => {
        const complexSvg = el.tagName.toLowerCase() === "svg" &&
            el.querySelectorAll("path,rect,circle,line,polygon,polyline,g").length > 12;
        return _clsHint(el, src, alt, /chart|graph|diagram|plot|infographic/i) || complexSvg;
    };
    // The decision tree — order mirrors meghana-v2 classifier STEP 1a..3.
    const classifyBlock = (el, srcAbs, altPresent, altValue) => {
        const ctx = imageContext(el);
        const dec = decorativeSignals(el, altPresent, altValue);
        const flags = { is_functional: false, is_decorative: false,
                        is_logo: false, is_icon: false, is_complex: false };
        const isLogo = looksLikeLogo(el, srcAbs, altValue);
        const isIcon = looksLikeIcon(el, srcAbs);
        const isChart = looksLikeChart(el, srcAbs, altValue);
        const clickable = ctx.in_link || ctx.has_click || ctx.in_button;
        let classification, sub_type;
        if (dec.alt_empty || dec.role_presentation || dec.aria_hidden) {
            flags.is_decorative = true; classification = "decorative"; sub_type = "images";
        } else if (el.tagName.toLowerCase() === "input") {
            // input[type=image] is definitionally a button.
            flags.is_functional = true; classification = "functional"; sub_type = "buttons";
        } else if (ctx.in_button) {
            // Functional container wins: an image inside a <button>/role=button is
            // labeled by its control (buttons), even when it looks like an icon.
            flags.is_functional = true; classification = "functional"; sub_type = "buttons";
        } else if (ctx.in_real_link && isLogo) {
            flags.is_functional = true; flags.is_logo = true;
            classification = "functional"; sub_type = "logos";
        } else if (isChart) {
            flags.is_complex = true; classification = "complex"; sub_type = "charts";
        } else if (clickable && isIcon) {
            // Reaches here only for links / has-click (in_button handled above):
            // an icon inside a link is labeled by its visual role (icons).
            flags.is_functional = true; flags.is_icon = true;
            classification = "functional"; sub_type = "icons";
        } else if (ctx.in_real_link) {
            flags.is_functional = true; classification = "functional"; sub_type = "images";
        } else if (isLogo) {
            flags.is_logo = true; classification = "informative"; sub_type = "logos";
        } else if (isIcon) {
            flags.is_icon = true; classification = "informative"; sub_type = "icons";
        } else {
            classification = "informative"; sub_type = "images";
        }
        return {
            functional_context: ctx,
            decorative_signals: dec,
            complex_signals: complexSignals(el),
            image_map: {
                has_usemap: el.hasAttribute("usemap"),
                map_name: (attr(el, "usemap") || "").replace(/^#/, "") || null,
            },
            classification, sub_type, flags,
        };
    };

    // ---------- single DOM walk ----------
    const videoRecordId = new Map(); // <video> element -> record id
    const pendingPosterLinks = [];   // records whose linked video comes later

    for (const el of document.querySelectorAll("*")) {
        const tag = el.tagName.toLowerCase();
        if (SKIP_TAGS.has(tag)) continue;
        if (el.ownerSVGElement) continue; // svg internals handled via svg root
        const criteria = [];
        let rec = null;

        // --- media elements (1.2.x) ---
        if (tag === "video") {
            if (el.hasAttribute("poster")) {
                const posterRec = push({
                    ...baseFields(el, "video_poster"),
                    poster_url: absUrl(el.getAttribute("poster")),
                    matched_rule: "video[poster] attribute",
                    linked_video_element_id: null, // filled below
                }, []);
                pendingPosterLinks.push({ rec: posterRec, videoEl: el });
            }
            const tracks = trackList(el);
            const capKinds = [...new Set(tracks.filter(t =>
                t.kind === "captions" || t.kind === "subtitles").map(t => t.kind))];
            const live = liveSignals(el);
            rec = push({
                ...baseFields(el, "video"),
                src: el.currentSrc || attr(el, "src"),
                controls: el.hasAttribute("controls"),
                autoplay: el.hasAttribute("autoplay"),
                muted: el.muted || el.hasAttribute("muted"),
                loop: el.hasAttribute("loop"),
                poster_url: el.hasAttribute("poster") ? absUrl(el.getAttribute("poster")) : null,
                tracks,
                caption_track_kinds: capKinds,
                has_captions_track: capKinds.length > 0,
                has_description_track: tracks.some(t => t.kind === "descriptions"),
                nearby_transcript_link_candidate: transcriptLink(el),
                transcript_context: mediaTranscriptContext(el),
                video_only_candidate: "undetermined_from_dom",
                live_signals: live,
            }, ["1.2.1", "1.2.2", "1.2.3",
                ...(live.length ? ["1.2.4"] : []),
                ...((el.hasAttribute("autoplay") &&
                     !(el.muted || el.hasAttribute("muted"))) ? ["1.4.2"] : [])]);
            videoRecordId.set(el, rec.id);
            continue;
        }
        if (tag === "audio") {
            const tracks = trackList(el);
            const live = liveSignals(el);
            push({
                ...baseFields(el, "audio"),
                src: el.currentSrc || attr(el, "src"),
                controls: el.hasAttribute("controls"),
                autoplay: el.hasAttribute("autoplay"),
                muted: el.muted || el.hasAttribute("muted"),
                loop: el.hasAttribute("loop"),
                tracks,
                audio_only_candidate: true,
                nearby_transcript_link_candidate: transcriptLink(el),
                transcript_context: mediaTranscriptContext(el),
                live_signals: live,
            }, ["1.2.1",
                ...(live.length ? ["1.2.4"] : []),
                ...((el.hasAttribute("autoplay") &&
                     !(el.muted || el.hasAttribute("muted"))) ? ["1.4.2"] : [])]);
            continue;
        }
        if (tag === "iframe") {
            const src = absUrl(attr(el, "src") || "");
            let host = null;
            try { host = src ? new URL(src).hostname.replace(/^www\./, "") : null; } catch {}
            const isEmbed = host !== null && embedHosts.some(h =>
                host === h || host.endsWith("." + h));
            if (isEmbed) {
                const live = liveSignals(el);
                push({
                    ...baseFields(el, "embedded_third_party_player"),
                    src,
                    title_attr: attr(el, "title"),
                    note: NOTE_IFRAME,
                    live_signals: live,
                }, ["1.2.1", "1.2.2", "1.2.3", "4.1.2",
                    ...(live.length ? ["1.2.4"] : [])]);
            }
            continue;
        }

        // --- image bucket (1.1.1 / 1.4.5) ---
        if (tag === "img") {
            const srcAbs = absUrl(el.currentSrc || attr(el, "src") || "");
            const poster = classifyPoster(el, srcAbs);
            if (poster) {
                const posterRec = push({
                    ...baseFields(el, "video_poster"),
                    poster_url: srcAbs,
                    matched_rule: poster.rule,
                    linked_video_element_id: null,
                }, []);
                if (poster.videoEl) pendingPosterLinks.push({ rec: posterRec, videoEl: poster.videoEl });
                continue;
            }
            const isSvg = srcAbs !== null && /\.svg(\?|#|$)/i.test(srcAbs.split("?")[0]);
            rec = {
                ...baseFields(el, isSvg ? "svg_via_img" : "img"),
                ...imageNameFields(el),
                src: srcAbs,
                srcset: attr(el, "srcset"),
                svg_delivery: isSvg ? "svg_via_img" : null,
                image_of_text: imageOfTextSignals(el, attr(el, "alt"), srcAbs),
                ...classifyBlock(el, srcAbs, el.hasAttribute("alt"), attr(el, "alt")),
            };
            criteria.push("1.1.1");
            if (rec.image_of_text.possible_image_of_text) criteria.push("1.4.5");
            push(rec, criteria);
            continue;
        }
        if (tag === "svg") {
            const useEl = el.querySelector("use");
            const useHref = useEl ? (useEl.getAttribute("href") ||
                useEl.getAttribute("xlink:href")) : null;
            const type = useHref ? "svg_via_use" : "svg_inline";
            const title = el.querySelector(":scope > title");
            const desc = el.querySelector(":scope > desc");
            const cs = getComputedStyle(el);
            rec = {
                ...baseFields(el, type),
                svg_delivery: type,
                title_child_text: title ? title.textContent.trim() : null,
                desc_child_text: desc ? desc.textContent.trim() : null,
                use_href: useHref,
                aria_label: attr(el, "aria-label"),
                aria_labelledby_resolved_text: resolveLabelledby(el),
                title_attr: attr(el, "title"),
                role: attr(el, "role"),
                figcaption_text: figcaptionText(el),
                accessibility_snapshot_name: accName(el),
                image_of_text: imageOfTextSignals(el, null, null),
                ...classifyBlock(el, null, false, null),
            };
            criteria.push("1.1.1");
            if (rec.image_of_text.possible_image_of_text) criteria.push("1.4.5");
            // Meaningful (non-decorative) graphic => 1.4.11 non-text contrast facts.
            if (el.closest('[aria-hidden="true"]') === null) {
                rec.fill = cs.fill;
                rec.stroke = cs.stroke;
                rec.ancestor_background_chain = bgChain(el);
                criteria.push("1.4.11");
            }
            push(rec, criteria);
            continue;
        }
        if (tag === "object" && /\.svg(\?|#|$)/i.test((attr(el, "data") || "").split("?")[0])) {
            push({
                ...baseFields(el, "svg_via_object"),
                svg_delivery: "svg_via_object",
                data_url: absUrl(el.getAttribute("data")),
                aria_label: attr(el, "aria-label"),
                aria_labelledby_resolved_text: resolveLabelledby(el),
                title_attr: attr(el, "title"),
                role: attr(el, "role"),
                figcaption_text: figcaptionText(el),
                fallback_text: el.textContent.trim() || null,
                accessibility_snapshot_name: accName(el),
                ...classifyBlock(el, absUrl(el.getAttribute("data")), false, null),
            }, ["1.1.1"]);
            continue;
        }
        if (tag === "area") {
            push({
                ...baseFields(el, "area"),
                ...imageNameFields(el),
                href: attr(el, "href"),
                ...classifyBlock(el, null, el.hasAttribute("alt"), attr(el, "alt")),
            }, ["1.1.1", ...(el.hasAttribute("href") ? ["4.1.2"] : [])]);
            continue;
        }
        if (tag === "input" && (attr(el, "type") || "").toLowerCase() === "image") {
            push({
                ...baseFields(el, "input_image"),
                ...imageNameFields(el),
                src: absUrl(attr(el, "src") || ""),
                is_native_control: true,
                is_custom_widget: false,
                implicit_role: "button",
                disabled: el.disabled,
                ...classifyBlock(el, absUrl(attr(el, "src") || ""), el.hasAttribute("alt"), attr(el, "alt")),
            }, ["1.1.1", "4.1.2", "1.4.11"]);
            continue;
        }
        if (tag === "canvas") {
            const hasFallback = el.textContent.trim().length > 0;
            if (!hasFallback && isRendered(el)) {
                rec = {
                    ...baseFields(el, "canvas"),
                    ...imageNameFields(el),
                    has_fallback_content: false,
                    image_of_text: imageOfTextSignals(el, null, null),
                    ...classifyBlock(el, null, el.hasAttribute("alt"), attr(el, "alt")),
                };
                criteria.push("1.1.1");
                if (rec.image_of_text.possible_image_of_text) criteria.push("1.4.5");
                push(rec, criteria);
            }
            continue;
        }

        // --- generic elements: css background, contrast text, ARIA controls ---
        const cs = getComputedStyle(el);
        const fields = {};

        if (cs.backgroundImage && cs.backgroundImage !== "none" && isRendered(el)) {
            const url = bgImageUrl(cs);
            if (url) {
                const poster = classifyPoster(el, url);
                if (poster) {
                    const posterRec = push({
                        ...baseFields(el, "video_poster"),
                        poster_url: url,
                        matched_rule: poster.rule,
                        linked_video_element_id: null,
                    }, []);
                    if (poster.videoEl) pendingPosterLinks.push({ rec: posterRec, videoEl: poster.videoEl });
                    continue;
                }
                const isSvg = /\.svg(\?|#|$)/i.test(url.split("?")[0]);
                fields.element_type = isSvg ? "css_background_svg" : "css_background_image";
                fields.resolved_background_url = url;
                fields.svg_delivery = isSvg ? "css_background_svg" : null;
                fields.has_own_text_content = Array.from(el.childNodes).some(
                    n => n.nodeType === 3 && n.textContent.trim() !== "");
                fields.aria_label = attr(el, "aria-label");
                fields.aria_labelledby_resolved_text = resolveLabelledby(el);
                fields.title_attr = attr(el, "title");
                fields.role = attr(el, "role");
                fields.accessibility_snapshot_name = accName(el);
                Object.assign(fields, classifyBlock(el, url, false, null));
                criteria.push("1.1.1");
            }
        }

        const hasOwnText = Array.from(el.childNodes).some(
            n => n.nodeType === 3 && n.textContent.trim() !== "");
        if (hasOwnText && isRendered(el)) {
            fields.computed_color = cs.color;
            fields.own_background_color = cs.backgroundColor;
            fields.ancestor_background_chain = fields.ancestor_background_chain || bgChain(el);
            fields.font_size_px = parseFloat(cs.fontSize);
            fields.font_weight = parseInt(cs.fontWeight, 10) || 400;
            // One extraction pass covers both 1.4.3 and 1.4.6 (thresholds
            // differ only downstream).
            criteria.push("1.4.3", "1.4.6");
        }

        const explicitRole = attr(el, "role");
        const nativeRole = implicitRole(el);
        const isNative = nativeRole !== null;
        if (isNative || explicitRole) {
            fields.role = explicitRole || nativeRole;
            fields.explicit_role = explicitRole;
            fields.implicit_role = nativeRole;
            fields.is_native_control = isNative;
            fields.is_custom_widget = !isNative && explicitRole !== null;
            fields.aria_label = attr(el, "aria-label");
            fields.aria_labelledby_resolved_text = resolveLabelledby(el);
            fields.label_for_text = labelForText(el);
            fields.title_attr = attr(el, "title");
            fields.text_content = (el.textContent || "").trim().slice(0, 200);
            fields.accessibility_snapshot_name = accName(el);
            for (const a of ["aria-checked", "aria-expanded", "aria-pressed",
                             "aria-valuenow", "aria-valuemin", "aria-valuemax",
                             "aria-selected"]) {
                fields[a.replace(/-/g, "_")] = attr(el, a);
            }
            fields.disabled = el.disabled === true;
            criteria.push("4.1.2");
            // Interactive UI component => 1.4.11 non-text contrast facts,
            // unless purely decorative.
            if (el.closest('[aria-hidden="true"]') === null &&
                explicitRole !== "presentation" && explicitRole !== "none") {
                fields.border_color = cs.borderTopColor;
                fields.outline_color = cs.outlineColor;
                fields.box_shadow = cs.boxShadow;
                fields.ancestor_background_chain =
                    fields.ancestor_background_chain || bgChain(el);
                criteria.push("1.4.11");
            }
        }

        if (criteria.length) {
            const primaryType = fields.element_type ||
                (criteria.includes("4.1.2") ? "interactive_control" : "text_contrast_candidate");
            delete fields.element_type;
            push({ ...baseFields(el, primaryType), ...fields }, criteria);
        }
    }

    // Resolve poster -> video record links now that every video has an id.
    for (const { rec, videoEl } of pendingPosterLinks) {
        rec.linked_video_element_id = videoRecordId.get(videoEl) ?? null;
    }

    const links = Array.from(document.querySelectorAll("a[href]"))
        .map(a => a.href)
        .filter(h => /^https?:/i.test(h));

    return { elements: records, links };
}
"""

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

    async def _download_asset(self, page, url: str, dest: Path) -> bool:
        """Save the original bytes of an image URL to dest. Decodes data: URIs
        inline and fetches http(s) through the browser context (so session
        cookies apply). Non-fatal — returns True only on success."""
        try:
            if url.startswith("data:"):
                header, _, data = url.partition(",")
                raw = (base64.b64decode(data) if ";base64" in header
                       else urllib.parse.unquote_to_bytes(data))
            elif url.startswith(("http://", "https://")):
                # context.request bypasses the context.route SSRF guard, so
                # re-check the host here before fetching asset bytes.
                if self.ssrf_guard and ssrf_host_is_blocked(
                        urllib.parse.urlsplit(url).hostname or ""):
                    return False
                resp = await page.context.request.get(
                    url, timeout=DOWNLOAD_TIMEOUT_MS)
                if not resp.ok:
                    return False
                raw = await resp.body()
            else:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            return True
        except (PlaywrightError, OSError, ValueError):
            return False

    async def _capture_assets(self, page, elements: list, url: str) -> None:
        """Capture rendered pixels for every visible image/graphic element.
        If text is overlaid on the image (composited via absolutely-positioned
        siblings) SCREENSHOT the overlay container so the text is preserved;
        otherwise DOWNLOAD the original image bytes. Inline SVG, <use> sprites
        and <canvas> have no fetchable URL, so they fall back to a screenshot.
        Sets on each SCREENSHOT_TYPES element (other elements untouched):
          screenshot    — relative PNG path or None
          asset_file    — relative downloaded-file path or None
          asset_capture — 'screenshot_overlay' | 'download' | 'screenshot_fallback' | None
        Every capture is non-fatal; on failure the three fields stay None."""
        page_slug = url_slug(normalize_url(url))
        shot_dir = self.out_dir / "screenshots" / page_slug
        for el in elements:
            if el.get("element_type") not in SCREENSHOT_TYPES:
                continue
            el["screenshot"] = None
            el["asset_file"] = None
            el["asset_capture"] = None
            bb = el.get("bounding_box") or {}
            if not el.get("visible", False) or bb.get("width", 0) <= 0 \
                    or bb.get("height", 0) <= 0:
                continue
            try:
                handle = await page.query_selector(el["selector"])
                if handle is None:
                    continue
                container = await handle.evaluate_handle(OVERLAY_CONTAINER_JS)
                is_overlay = await container.evaluate("(c, img) => c !== img", handle)
                url_field = ASSET_URL_FIELD.get(el["element_type"])
                asset_url = el.get(url_field) if url_field else None

                # Non-overlay image with a fetchable URL -> download the bytes.
                if not is_overlay and asset_url:
                    ext = _asset_ext(asset_url)
                    rel = Path("assets") / page_slug / f"{el['id']}{ext}"
                    if await self._download_asset(page, asset_url, self.out_dir / rel):
                        el["asset_file"] = str(rel)
                        el["asset_capture"] = "download"
                        continue  # captured — done with this element

                # Overlay text (screenshot the container), inline graphic with no
                # URL, or a failed download -> screenshot the rendered pixels.
                target = (container.as_element() if is_overlay else handle) or handle
                shot_dir.mkdir(parents=True, exist_ok=True)
                rel = Path("screenshots") / page_slug / f"{el['id']}.png"
                await target.screenshot(path=str(self.out_dir / rel),
                                        timeout=SHOT_TIMEOUT_MS)
                el["screenshot"] = str(rel)
                el["asset_capture"] = ("screenshot_overlay" if is_overlay
                                       else "screenshot_fallback")
            except (PlaywrightError, Exception):
                pass  # detached / offscreen / timeout — leave fields None

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

        # Trigger lazy-loaded content before the DOM walk.
        await page.evaluate(SCROLL_JS)
        await page.wait_for_timeout(400)

        extraction = await page.evaluate(EXTRACT_JS, VIDEO_EMBED_HOSTS)

        elements = extraction["elements"]
        if self.screenshots:
            await self._capture_assets(page, elements, url)
        criteria_ids: dict[str, list[str]] = {key: [] for key in CRITERIA_KEYS}
        for element in elements:
            for criterion in element.pop("criteria", []):
                criteria_ids[criterion].append(element["id"])

        links = self._process_links(extraction["links"], depth)

        return {
            "page_url": url,
            "normalized_url": normalize_url(url),
            "crawl_timestamp": utc_now_iso(),
            "depth": depth,
            "http_status": http_status,
            "processing_status": "success",
            "failure_reason": None,
            "viewport": VIEWPORT,
            "elements": elements,
            "criteria": {
                key: {
                    "applicable": bool(ids),
                    "element_ids": ids,
                    "note": None if ids else NOT_PRESENT_NOTE,
                }
                for key, ids in criteria_ids.items()
            },
            "robots_txt": {"checked": True, "allowed": True},
            "links_discovered": links,
        }

    async def _process_page(self, context, url: str, depth: int) -> None:
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
