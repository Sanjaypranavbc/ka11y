"""
ka11y/crawler/image_extractor.py
================================
Per-page image extraction + asset capture, shared by both crawlers.

This is the engine-era ``EXTRACT_JS`` single DOM walk (classification,
accessible-name facts, image-of-text signals, contrast facts) plus the
screenshot / download / carousel capture that follows it — lifted out of
``optimized/engine.py`` so the universal page loader can run it on the page it
has *already* navigated instead of a second Chromium re-navigating every page.

Nothing in here owns a browser, a frontier, or a file layout beyond
``out_dir``. Callers hand in a ready page:

    doc = await extract_image_page(page, url, depth, raw_dir)
    write_page_doc(doc, raw_dir)          # → raw_dir/<slug>.json

``optimized/adapter.build_image_data`` reads those docs unchanged, so the OCR
and alt-text auditors never see a difference between the two producers.

Entry points
------------
extract_image_page   scroll → reveal hidden images → lazy-load nudge →
                     EXTRACT_JS → capture_assets → engine-shaped page doc
capture_assets       screenshot / download decision per image element
capture_carousel_slides, reveal_hidden_images, download_asset
write_page_doc       atomic JSON write keyed by ``url_slug(normalized_url)``
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from playwright.async_api import Error as PlaywrightError

from ka11y.config.logger import setup_logger
from ka11y.crawler._ssrf_guard import _host_is_blocked

try:
    import tldextract  # optional: exact eTLD+1 via the public-suffix list
except ImportError:  # pragma: no cover - optional dependency
    tldextract = None

# Must go through setup_logger: the project's "KAC" handlers format a ``tag``
# field that a bare ``logging.getLogger("KAC.x")`` child never carries, which
# turns every record into a "--- Logging error ---" traceback on stderr.
logger = setup_logger(name="KAC", tag="image_extractor")

VIEWPORT = {"width": 1366, "height": 900}

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
    "video_poster", "video",
}
# Per asset type, the element field holding a downloadable URL. Types absent
# here (inline svg, <use> sprites, canvas) have no fetchable source, so they
# are always screenshotted as a fallback.
ASSET_URL_FIELD = {
    "img": "src", "svg_via_img": "src", "input_image": "src",
    "svg_via_object": "data_url",
    "css_background_image": "resolved_background_url",
    "css_background_svg": "resolved_background_url",
}
SHOT_TIMEOUT_MS = 5_000
DOWNLOAD_TIMEOUT_MS = 30_000
# How many asset downloads _capture_assets runs concurrently per page (see
# Pass 2b). Bounds outbound connections on image-heavy pages; downloads go
# through BrowserContext.request, which is safe for concurrent use unlike
# Page/ElementHandle screenshots.
DOWNLOAD_CONCURRENCY = 10
# Carousel-specific limits.
# MAX_CAROUSEL_SLIDES: hard cap on how many slide-advances the crawler will
# attempt for a single carousel, preventing infinite loops on carousels that
# expose hundreds of items or never settle on a terminal state.
MAX_CAROUSEL_SLIDES = 20
# CAROUSEL_ADVANCE_TIMEOUT_MS: how long _capture_carousel_slides waits (via
# polling) for the active-slide fingerprint to change after clicking the next
# control.  1 200 ms covers most CSS transition durations with headroom.
CAROUSEL_ADVANCE_TIMEOUT_MS = 1_200

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

# ---------------------------------------------------------------------------
# Carousel / reel / slider detection helpers
# ---------------------------------------------------------------------------
# CAROUSEL_DETECT_JS: given any element on the page, walks up the DOM to find
# the nearest carousel/reel/slider root and returns a descriptor object:
#   { root: Element|null, slideCount: number, nextSelector: string|null }
# Detection covers:
#   • ARIA pattern: role="region" + aria-roledescription="carousel"
#   • Swiper (.swiper / .swiper-container)
#   • Slick (.slick-slider)
#   • Generic [data-carousel], [data-slider], [data-reel]
#   • reel-show / reel_show class/id patterns  (site-specific)
#   • Repeated <li>/<div> siblings with role="group"|"tabpanel" inside a
#     fixed-width overflow-hidden scroll container
# Returns null when no carousel ancestor is found within 8 ancestor hops.
CAROUSEL_DETECT_JS = """el => {
    // Selectors whose first matching ancestor is the carousel root.
    const ROOT_SELECTORS = [
        '[role="region"][aria-roledescription]',
        '[data-carousel]',
        '[data-slider]',
        '[data-reel]',
        '.swiper',
        '.swiper-container',
        '.slick-slider',
        '.reel-show',
        '.reel_show',
        '[class*="reel"]',
        '[id*="reel"]',
        '[class*="carousel"]',
        '[class*="slider"]',
    ];
    // Next-slide control selectors (tried in order; first match is used).
    const NEXT_SELECTORS = [
        '[aria-label*="next" i]',
        '[aria-label*="Next" i]',
        '.carousel-control-next',
        '.slick-next',
        '.swiper-button-next',
        '[data-slide="next"]',
        '[data-action="next"]',
        '.reel-next',
        'button.next',
    ];

    // Walk up at most 8 levels to find a carousel root.
    let node = el.parentElement;
    let root = null;
    for (let i = 0; i < 8 && node && node.tagName !== 'BODY'; i++) {
        for (const sel of ROOT_SELECTORS) {
            try {
                if (node.matches(sel)) { root = node; break; }
            } catch {}
        }
        if (root) break;
        node = node.parentElement;
    }
    if (!root) return null;

    // Count slide items: look for role=group/tabpanel children, then slick/swiper
    // slide classes, then direct li children, then any direct div children.
    let slideCount = 0;
    const byRole = root.querySelectorAll('[role="group"], [role="tabpanel"]');
    if (byRole.length > 1) {
        slideCount = byRole.length;
    } else {
        const byClass = root.querySelectorAll(
            '.slick-slide:not(.slick-cloned), .swiper-slide:not(.swiper-slide-duplicate)'
        );
        if (byClass.length > 1) {
            slideCount = byClass.length;
        } else {
            // Fallback: direct <li> or <div> children whose dimensions match the root.
            const rootRect = root.getBoundingClientRect();
            const items = Array.from(root.children).filter(ch => {
                const r = ch.getBoundingClientRect();
                return r.width > 0 && r.height > 0 &&
                       Math.abs(r.width - rootRect.width) < rootRect.width * 0.2;
            });
            if (items.length > 1) slideCount = items.length;
        }
    }

    // Find the next-slide control scoped to this root.
    let nextSelector = null;
    for (const sel of NEXT_SELECTORS) {
        try {
            if (root.querySelector(sel)) { nextSelector = sel; break; }
        } catch {}
    }

    return {
        rootSelector: (root.id ? '#' + CSS.escape(root.id) : null),
        slideCount: slideCount,
        nextSelector: nextSelector,
    };
}"""

# CAROUSEL_ADVANCE_JS: given a carousel root selector and next-control selector,
# clicks the next control (or dispatches ArrowRight as a fallback), then polls
# until the active-slide indicator changes or a timeout elapses.
# Returns true when the slide changed, false on timeout or no control found.
CAROUSEL_ADVANCE_JS = """async (args) => {
    const { rootSelector, nextSelector, timeoutMs } = args;
    const deadline = Date.now() + (timeoutMs || 1200);
    const pause = ms => new Promise(r => setTimeout(r, ms));

    // Locate the carousel root.
    let root = null;
    if (rootSelector) {
        try { root = document.querySelector(rootSelector); } catch {}
    }

    // Helper: fingerprint the current active slide so we can detect a change.
    const activeFingerprint = (r) => {
        if (!r) return '';
        // ARIA: aria-current, aria-selected on slide items
        const cur = r.querySelector('[aria-current="true"], [aria-selected="true"]');
        if (cur) return cur.getAttribute('aria-label') || cur.dataset.index || cur.id || cur.className;
        // Slick: .slick-current class
        const slickCur = r.querySelector('.slick-current');
        if (slickCur) return slickCur.innerHTML.slice(0, 80);
        // Swiper: .swiper-slide-active
        const swiperCur = r.querySelector('.swiper-slide-active');
        if (swiperCur) return swiperCur.innerHTML.slice(0, 80);
        // Transform-based: read translateX of track element
        const track = r.querySelector('.slick-track, .swiper-wrapper, [data-carousel-track]');
        if (track) return window.getComputedStyle(track).transform;
        return r.innerHTML.slice(0, 120);
    };

    const before = activeFingerprint(root);

    // Pause autoplay if a known API is accessible.
    try {
        if (root && root.swiper) { root.swiper.autoplay.stop(); }
    } catch {}

    // Try clicking the next-control.
    let clicked = false;
    if (nextSelector) {
        const scope = root || document;
        const btn = scope.querySelector(nextSelector);
        if (btn) {
            try { btn.click(); clicked = true; } catch {}
        }
    }
    // Fallback: dispatch ArrowRight on the root element.
    if (!clicked && root) {
        root.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    }

    // Poll until the fingerprint changes or deadline passes.
    while (Date.now() < deadline) {
        await pause(80);
        if (activeFingerprint(root) !== before) return true;
    }
    return false;
}"""


def _is_svg_asset(element_type: str, url: str) -> bool:
    """True when downloading *url* would yield SVG markup rather than pixels.
    OCR/contrast need a raster, so such elements are screenshotted instead
    (the rendered size is what visitors see anyway)."""
    if "svg" in (element_type or ""):
        return True
    u = (url or "").lower()
    if u.startswith("data:"):
        return u[5:].split(",", 1)[0].split(";", 1)[0] == "image/svg+xml"
    return urllib.parse.urlsplit(u).path.endswith(".svg")


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
    // OneTrust / Optanon cookie-consent widget markup. This is the CMP
    // vendor's DOM, injected on every page — not the audited site's own
    // content — so Kao does not want its banner, preference centre, or the
    // persistent "Cookie Settings" launcher counted as findings. Any element
    // inside one of these is dropped from the crawl (reject_cookies removes
    // the visible overlay for screenshots; this also covers the persistent
    // launcher and anything left hidden in the DOM).
    const CONSENT_SCOPE_SEL = [
        "#onetrust-consent-sdk", "#onetrust-banner-sdk", "#onetrust-pc-sdk",
        "#ot-sdk-btn", "#ot-sdk-btn-floating", ".ot-floating-button",
        ".onetrust-pc-dark-filter", ".optanon-alert-box-wrapper",
        '[id^="onetrust-"]', '[id^="ot-sdk-"]',
        '[class*="onetrust-"]', '[class*="optanon"]', '[class^="ot-sdk-"]'
    ].join(",");

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
        if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) return false;
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
    const baseFields = (el, elementType) => {
        const idStr = nextId();
        try { el.setAttribute("data-ka11y-id", idStr); } catch {}
        return {
            id: idStr,
            tag_name: el.tagName.toLowerCase(),
            element_type: elementType,
            selector: cssPath(el),
            outer_html_snippet: snippet(el),
            bounding_box: bbox(el),
            visible: isVisible(el),
        };
    };
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
        if (el.closest(CONSENT_SCOPE_SEL)) continue; // OneTrust/Optanon CMP — out of audit scope
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
            // Gap 3: full src fallback chain, ported from pranav-v2 _resolve_src().
            // Priority order matches pranav-v2 exactly:
            //   src → data-src → data-lazy-src → data-original → data-lazy → data-url
            // then srcset / data-srcset (first candidate, whitespace-split).
            // data: URIs are skipped at every step, same as pranav-v2.
            const _resolveSrc = (el) => {
                for (const a of ["src", "data-src", "data-lazy-src",
                                  "data-original", "data-lazy", "data-url"]) {
                    const v = el.currentSrc && a === "src"
                        ? el.currentSrc   // prefer browser-resolved currentSrc for "src"
                        : el.getAttribute(a);
                    if (v && !v.startsWith("data:")) return absUrl(v);
                }
                for (const a of ["srcset", "data-srcset"]) {
                    const v = el.getAttribute(a);
                    if (v) {
                        const first = v.trim().split(",")[0].trim().split(/\s+/)[0];
                        if (first && !first.startsWith("data:")) return absUrl(first);
                    }
                }
                return null;
            };
            const srcAbs = _resolveSrc(el);
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


async def download_asset(
    page,
    url: str,
    dest: Path,
    *,
    ssrf_check: Optional[Callable[[str], bool]] = _host_is_blocked,
) -> bool:
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
            if ssrf_check is not None and ssrf_check(
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

# ------------------------------------------------------------------
# Carousel-aware slide capture
# ------------------------------------------------------------------

async def capture_carousel_slides(
    page,
    carousel_elements: list,
    page_slug: str,
    out_dir: Path,
) -> None:
    """Advance through a carousel's slides, taking a unique screenshot per
    distinct slide before downloading/screenshotting each element.

    Algorithm:
      1. Detect the carousel root + slide count + next-control via JS.
      2. Pause autoplay (if the library API is accessible).
      3. Loop: advance one slide → wait for state change → screenshot the
         now-visible image(s) in the carousel.
      4. Stop when:
         - all ``carousel_elements`` are captured, OR
         - the slide count is exhausted, OR
         - the captured image hash matches a previously-seen hash
           (back to start on a looping carousel), OR
         - a hard cap of MAX_CAROUSEL_SLIDES is hit.
    Duplicate frames are skipped (flagged as 'carousel_duplicate').
    """
    if not carousel_elements:
        return

    shot_dir = out_dir / "screenshots" / page_slug
    shot_dir.mkdir(parents=True, exist_ok=True)

    # Probe the first element's carousel root.
    try:
        first_handle = await page.query_selector(carousel_elements[0]["selector"])
        if first_handle is None:
            return
        info = await first_handle.evaluate(CAROUSEL_DETECT_JS)
    except (PlaywrightError, Exception):
        info = None

    if not info:
        return  # not a real carousel — caller will fall back to normal path

    root_selector = info.get("rootSelector")
    next_selector = info.get("nextSelector")
    detected_slide_count = info.get("slideCount") or 0
    max_slides = min(
        max(detected_slide_count, len(carousel_elements)),
        MAX_CAROUSEL_SLIDES,
    )

    seen_hashes: set[str] = set()
    captured_count = 0
    # Track which element IDs have been assigned a carousel screenshot so
    # the regular _capture_assets loop can skip them.
    processed_ids: set[str] = set()

    for slide_index in range(max_slides):
        # Advance the carousel before the first capture too (unless this is
        # the very first slide — we want the initial state on slide 0).
        if slide_index > 0:
            try:
                changed = await page.evaluate(
                    CAROUSEL_ADVANCE_JS,
                    {
                        "rootSelector": root_selector,
                        "nextSelector": next_selector,
                        "timeoutMs": CAROUSEL_ADVANCE_TIMEOUT_MS,
                    },
                )
                if not changed:
                    break  # carousel did not advance — stop
            except (PlaywrightError, Exception):
                break

        # Screenshot every carousel image element that is now visible.
        slide_has_new_content = False
        for el in carousel_elements:
            if el.get("id") in processed_ids:
                continue
            try:
                handle = await page.query_selector(el["selector"])
                if handle is None:
                    continue
                visible = await handle.is_visible()
                if not visible:
                    continue

                # Take a screenshot of the visible element.
                rel = Path("screenshots") / page_slug / f"{el['id']}_slide{slide_index}.png"
                dest = out_dir / rel
                await handle.screenshot(path=str(dest), timeout=SHOT_TIMEOUT_MS)

                # Deduplication: hash the raw PNG bytes.
                img_bytes = dest.read_bytes()
                img_hash = hashlib.md5(img_bytes).hexdigest()
                if img_hash in seen_hashes:
                    # Identical frame — carousel has looped; skip + clean up.
                    dest.unlink(missing_ok=True)
                    el.setdefault("asset_capture", "carousel_duplicate")
                    continue

                seen_hashes.add(img_hash)
                el["screenshot"] = str(rel)
                el["asset_capture"] = f"carousel_slide_{slide_index}"
                processed_ids.add(el["id"])
                slide_has_new_content = True
                captured_count += 1

            except (PlaywrightError, Exception):
                continue

        if not slide_has_new_content and slide_index > 0:
            # No new elements appeared after advancing — assume loop-back.
            break

        if captured_count >= len(carousel_elements):
            break  # all elements captured

    # Any remaining uncaptured elements: mark so the caller knows.
    for el in carousel_elements:
        if el.get("id") not in processed_ids:
            el.setdefault("asset_capture", "carousel_not_reached")

# ------------------------------------------------------------------
# Main asset capture dispatcher
# ------------------------------------------------------------------

async def capture_assets(
    page,
    elements: list,
    url: str,
    out_dir: Path,
    *,
    ssrf_check: Optional[Callable[[str], bool]] = _host_is_blocked,
    download_sem: Optional[asyncio.Semaphore] = None,
) -> None:
    """Capture rendered pixels for every visible image/graphic element.

    Decision matrix per element (evaluated in order):

    1. Icons and logos (sub_type == 'icons' or 'logos', or flags.is_icon /
       flags.is_logo): ALWAYS screenshot the element in-place, bounded to
       its on-page position, including its actual background.  This captures
       the rendered UI rather than the isolated transparent/raw asset file,
       which is essential for accurate colour-contrast and branding checks.

    2. Text overlaid on the image (overlay container ≠ element): SCREENSHOT
       the overlay container so the composited text is preserved.

    3. Non-overlay image with a fetchable URL: DOWNLOAD the original bytes.

    4. Inline SVG, <use> sprites, <canvas>, or a failed download:
       SCREENSHOT the element as a fallback.

    For elements that live inside a carousel / reel / slider component:
      The carousel-aware ``_capture_carousel_slides`` loop is invoked
      instead, which advances the carousel between captures and deduplicates
      identical frames so each distinct slide is captured exactly once.

    Sets on each SCREENSHOT_TYPES element (other elements untouched):
      screenshot    — relative PNG path or None
      asset_file    — relative downloaded-file path or None
      asset_capture — 'screenshot_icon_logo' | 'screenshot_overlay' |
                      'download' | 'screenshot_fallback' |
                      'carousel_slide_<N>' | 'carousel_duplicate' |
                      'carousel_not_reached' | None
    Every capture is non-fatal; on failure the three fields stay None.
    """
    page_slug = url_slug(normalize_url(url))
    shot_dir = out_dir / "screenshots" / page_slug

    # ------------------------------------------------------------------
    # Pass 1: detect carousel elements and group them by carousel root.
    # Elements are probed in selector order; only img-type elements that
    # are inside a carousel root are routed to the carousel path.
    # ------------------------------------------------------------------
    carousel_groups: dict[str, list] = {}   # root_selector → [elements]
    carousel_element_ids: set[str] = set()  # IDs already routed to carousel path

    for el in elements:
        if el.get("element_type") not in SCREENSHOT_TYPES:
            continue

        # Quick pre-check: only probe elements that might plausibly be in a
        # carousel (skip icons/logos — those never need slide-advance).
        flags = el.get("flags") or {}
        sub_type = el.get("sub_type") or ""
        is_icon_or_logo = (
            sub_type in ("icons", "logos")
            or flags.get("is_icon")
            or flags.get("is_logo")
        )
        if is_icon_or_logo:
            continue
        try:
            handle = await page.query_selector(el["selector"])
            if handle is None:
                continue
            info = await handle.evaluate(CAROUSEL_DETECT_JS)
            if info and info.get("slideCount", 0) > 1:
                key = info.get("rootSelector") or f"__no_id_{id(info)}"
                carousel_groups.setdefault(key, []).append(el)
                carousel_element_ids.add(el["id"])
        except (PlaywrightError, Exception):
            pass  # non-carousel or detached — handled in Pass 2

    # ------------------------------------------------------------------
    # Pass 1b: run carousel capture for each detected group.
    # ------------------------------------------------------------------
    for _root_key, group in carousel_groups.items():
        try:
            await capture_carousel_slides(page, group, page_slug, out_dir)
        except (PlaywrightError, Exception):
            pass  # non-fatal: group elements stay with screenshot=None

    # ------------------------------------------------------------------
    # Pass 2: normal (non-carousel) capture for all remaining elements.
    #
    # Split into a DOM-decision phase (2a, sequential — query_selector /
    # evaluate_handle / on-page screenshots all operate on the shared
    # `page`/CDP session and are not safe to run concurrently) and a
    # download phase (2b, concurrent). Only asset downloads are
    # parallelized: they go through BrowserContext.request, which
    # Playwright documents as safe for concurrent use — unlike
    # Page/ElementHandle screenshots, which stay sequential here. This
    # is what turns the majority-case (real <img src> with no overlay)
    # from N sequential round-trips into one bounded concurrent batch.
    # ------------------------------------------------------------------
    # (el, asset_url, dest_path, fallback_target) — fallback_target is
    # the already-resolved handle to screenshot if the download fails,
    # so phase 2b never needs to re-query a possibly-stale selector.
    download_jobs: list[tuple[dict, str, Path, object]] = []

    for el in elements:
        if el.get("element_type") not in SCREENSHOT_TYPES:
            continue
        # Skip elements already handled by the carousel path.
        if el.get("id") in carousel_element_ids:
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

            # ── Decision: is this element an icon or logo? ──────────────
            flags = el.get("flags") or {}
            sub_type = el.get("sub_type") or ""
            is_icon_or_logo = (
                sub_type in ("icons", "logos")
                or flags.get("is_icon")
                or flags.get("is_logo")
            )

            if is_icon_or_logo:
                # Screenshot the element as rendered on the page (with real
                # background) instead of downloading the isolated raw asset.
                shot_dir.mkdir(parents=True, exist_ok=True)
                rel = Path("screenshots") / page_slug / f"{el['id']}.png"
                await handle.screenshot(
                    path=str(out_dir / rel),
                    timeout=SHOT_TIMEOUT_MS,
                )
                el["screenshot"] = str(rel)
                el["asset_capture"] = "screenshot_icon_logo"

                # WCAG 1.4.11 (Non-text Contrast) needs this component's
                # contrast measured against its *surrounding page
                # background* — the tight element screenshot above has no
                # context to measure a boundary against. Capture a second,
                # padded screenshot via a viewport-relative clip rect
                # (elementHandle.screenshot() has no margin option) and
                # record the element's bbox local to that crop. Best-effort
                # only: skip elements touching the viewport edge (no real
                # context to measure) and never let a failure here affect
                # the primary capture above — 1.4.11 falls back to its
                # existing OCR-text-in-image proxy when this is absent.
                try:
                    pad = 40
                    vp_rect = await handle.bounding_box()
                    viewport = page.viewport_size or {"width": 1280, "height": 800}
                    if vp_rect and vp_rect["width"] > 0 and vp_rect["height"] > 0:
                        cx0 = max(0, vp_rect["x"] - pad)
                        cy0 = max(0, vp_rect["y"] - pad)
                        cx1 = min(viewport["width"], vp_rect["x"] + vp_rect["width"] + pad)
                        cy1 = min(viewport["height"], vp_rect["y"] + vp_rect["height"] + pad)
                        cw, ch = cx1 - cx0, cy1 - cy0
                        touches_edge = (
                            cx0 <= 0 or cy0 <= 0
                            or cx1 >= viewport["width"] or cy1 >= viewport["height"]
                        )
                        if cw > 4 and ch > 4 and not touches_edge:
                            ctx_rel = Path("screenshots") / page_slug / f"{el['id']}_context.png"
                            await page.screenshot(
                                path=str(out_dir / ctx_rel),
                                clip={"x": cx0, "y": cy0, "width": cw, "height": ch},
                                timeout=SHOT_TIMEOUT_MS,
                            )
                            el["context_screenshot"] = str(ctx_rel)
                            el["context_bbox"] = {
                                "x": vp_rect["x"] - cx0,
                                "y": vp_rect["y"] - cy0,
                                "width": vp_rect["width"],
                                "height": vp_rect["height"],
                            }
                except (PlaywrightError, Exception):
                    pass  # non-fatal: 1.4.11 falls back to the OCR-text proxy
                continue

            # ── For all other categories: overlay → download → fallback ──
            container = await handle.evaluate_handle(OVERLAY_CONTAINER_JS)
            is_overlay = await container.evaluate("(c, img) => c !== img", handle)
            url_field = ASSET_URL_FIELD.get(el["element_type"])
            asset_url = el.get(url_field) if url_field else None
            target = (container.as_element() if is_overlay else handle) or handle

            # Non-overlay image with a fetchable URL -> queue the download
            # for the concurrent batch below instead of awaiting it here.
            # `target` travels with the job as the fallback screenshot if
            # the download fails. SVG sources are excluded: the download
            # would be XML, which no OCR/contrast step can read.
            if not is_overlay and asset_url and not _is_svg_asset(el.get("element_type", ""), asset_url):
                ext = _asset_ext(asset_url)
                rel = Path("assets") / page_slug / f"{el['id']}{ext}"
                download_jobs.append((el, asset_url, out_dir / rel, target))
                continue  # resolved in phase 2b

            # Overlay text or inline graphic with no fetchable URL ->
            # screenshot the rendered pixels now (sequential — shares the
            # page with every other on-page capture in this pass).
            shot_dir.mkdir(parents=True, exist_ok=True)
            rel = Path("screenshots") / page_slug / f"{el['id']}.png"
            await target.screenshot(path=str(out_dir / rel),
                                    timeout=SHOT_TIMEOUT_MS)
            el["screenshot"] = str(rel)
            el["asset_capture"] = "screenshot_overlay" if is_overlay else "screenshot_fallback"
        except (PlaywrightError, Exception):
            pass  # detached / offscreen / timeout — leave fields None

    # ------------------------------------------------------------------
    # Pass 2b: resolve every queued download concurrently. Bounded by a
    # semaphore so a page with hundreds of images doesn't open hundreds
    # of simultaneous connections at once.
    # ------------------------------------------------------------------
    if download_jobs:
        sem = download_sem or asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

        async def _bounded_download(asset_url: str, dest: Path) -> bool:
            async with sem:
                return await download_asset(page, asset_url, dest, ssrf_check=ssrf_check)

        outcomes = await asyncio.gather(
            *(_bounded_download(url, dest) for _el, url, dest, _target in download_jobs),
            return_exceptions=True,
        )

        # Fallback screenshots for failed downloads must stay sequential
        # (same page/CDP session as the rest of this pass).
        for (el, _url, dest, target), ok in zip(download_jobs, outcomes):
            if ok is True:
                el["asset_file"] = str(dest.relative_to(out_dir))
                el["asset_capture"] = "download"
                continue
            try:
                shot_dir.mkdir(parents=True, exist_ok=True)
                rel = Path("screenshots") / page_slug / f"{el['id']}.png"
                await target.screenshot(path=str(out_dir / rel),
                                        timeout=SHOT_TIMEOUT_MS)
                el["screenshot"] = str(rel)
                el["asset_capture"] = "screenshot_fallback"
            except (PlaywrightError, Exception):
                pass  # detached / offscreen / timeout — leave fields None

async def reveal_hidden_images(page) -> int:
    """Click tabs, accordions, dropdowns, carousels to expose hidden images using locators."""
    revealed = 0
    groups = {
        "tabs": '[role="tab"], .tab, [data-toggle="tab"], .nav-link',
        "accordions": '[data-toggle="collapse"], .accordion-toggle, .accordion-button, details summary',
        "dropdowns": '[data-toggle="dropdown"], .dropdown-toggle',
        "modals": '[data-toggle="modal"]',
        "carousels": '.carousel-control-next, .slick-next, [data-slide="next"], .swiper-button-next, .reel-next, button.next, [aria-label*="next" i]',
        "load_more": ".load-more, [data-load-more]",
    }
    for name, sel in groups.items():
        try:
            els = await page.locator(sel).all()
            unique = {
                await e.evaluate("el => el.outerHTML.slice(0,100)"): e for e in els
            }.values()
            count = 0
            for el in list(unique)[:8]:
                try:
                    # Opacity check added here as well for visibility
                    if await el.evaluate("""el => {
                        const cs = window.getComputedStyle(el);
                        return cs.display !== "none" && cs.visibility !== "hidden" && parseFloat(cs.opacity) !== 0;
                    }"""):
                        await el.click(timeout=1500)
                        await page.wait_for_timeout(400)
                        revealed += 1
                        count += 1
                except Exception:
                    pass
            if count:
                logger.debug("[image_extractor] %s: clicked %d", name, count)
        except Exception as e:
            logger.debug("[image_extractor] toggle group %s error: %s", name, e)
    return revealed


# ---------------------------------------------------------------------------
# Page-level driver
# ---------------------------------------------------------------------------

# Gap 2 (engine-era): dispatch a synthetic ``lazyload`` event to images that
# still carry data-src attributes after scrolling, so lazy-load libraries that
# listen for IntersectionObserver callbacks resolve their real src.
IO_LAZYLOAD_JS = """() => {
    const imgs = document.querySelectorAll("img[data-src],img[data-lazy-src],img[data-original]");
    imgs.forEach(img => {
        const obs = new IntersectionObserver(entries => {
            entries.forEach(e => e.target.dispatchEvent(new Event('lazyload')));
            obs.disconnect();
        });
        obs.observe(img);
    });
}"""

PAGE_LANG_JS = "() => ((document.documentElement && document.documentElement.lang) || '').trim() || null"


def empty_links_discovered() -> dict:
    return {
        "same_domain_enqueued": 0,
        "same_domain_depth_cutoff": 0,
        "off_domain_discarded": 0,
    }


async def extract_image_page(
    page,
    url: str,
    depth: int,
    out_dir: Path,
    *,
    screenshots: bool = True,
    ssrf_check: Optional[Callable[[str], bool]] = _host_is_blocked,
    download_sem: Optional[asyncio.Semaphore] = None,
    embed_hosts: Optional[list] = None,
) -> dict:
    """Run the image extraction + capture pipeline on an already-loaded page.

    The caller is responsible for navigation, readiness waits and cookie
    handling. This function only mutates page state in the ways the engine
    always did (scrolls, clicks tab/accordion/carousel controls to reveal
    hidden images) — run it *after* any extraction that must see the page in
    its arrival state.

    Returns the engine-shaped page document with ``processing_status ==
    "success"``. ``http_status`` is left ``None`` and ``links`` is the raw
    href list; the caller fills in ``links_discovered`` (or uses
    :func:`empty_links_discovered`).
    """
    out_dir = Path(out_dir)

    # Trigger lazy-loaded content before the DOM walk.
    await page.evaluate(SCROLL_JS)
    await page.wait_for_timeout(400)

    # Gap 1: reveal hidden images (tabs / accordions / carousels) using locators.
    await reveal_hidden_images(page)

    # Gap 2: IntersectionObserver + lazyload dispatch.
    await page.evaluate(IO_LAZYLOAD_JS)
    await page.wait_for_timeout(1000)

    extraction = await page.evaluate(EXTRACT_JS, embed_hosts or VIDEO_EMBED_HOSTS)

    elements = extraction["elements"]
    if screenshots:
        await capture_assets(
            page, elements, url, out_dir,
            ssrf_check=ssrf_check, download_sem=download_sem,
        )
    criteria_ids: dict[str, list[str]] = {key: [] for key in CRITERIA_KEYS}
    for element in elements:
        for criterion in element.pop("criteria", []):
            criteria_ids[criterion].append(element["id"])

    try:
        page_lang = await page.evaluate(PAGE_LANG_JS)
    except Exception:  # noqa: BLE001 — lang is advisory (OCR engine routing)
        page_lang = None

    try:
        viewport = page.viewport_size or VIEWPORT
    except Exception:  # noqa: BLE001
        viewport = VIEWPORT

    return {
        "page_url": url,
        "normalized_url": normalize_url(url),
        "crawl_timestamp": utc_now_iso(),
        "depth": depth,
        "http_status": None,
        "processing_status": "success",
        "failure_reason": None,
        "viewport": viewport,
        "page_lang": page_lang,
        "elements": elements,
        "criteria": {
            key: {
                "applicable": bool(ids),
                "element_ids": ids,
                "note": None if ids else NOT_PRESENT_NOTE,
            }
            for key, ids in criteria_ids.items()
        },
        "robots_txt": {"checked": False, "allowed": True},
        "links": list(extraction.get("links") or []),
        "links_discovered": empty_links_discovered(),
    }


def write_page_doc(doc: dict, out_dir: Path) -> Path:
    """Atomically write one page document to ``out_dir/<slug>.json``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{url_slug(doc['normalized_url'])}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)
    return path
