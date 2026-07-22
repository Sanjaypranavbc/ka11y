from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page

from ka11y.utils.url_canonical import canonicalize_url

from ka11y.config.logger import setup_logger
from ka11y.crawler.navigation import navigate_with_resilience, NavigationError
from ka11y.crawler.policy import CrawlPolicy
from ka11y.crawler.cookie_handler import handle_cookies
from ka11y.utils.step_logger import ExecutionStepLogger

# Pipeline extractors run per-page during the universal crawl so the unified
# pipeline (1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 2.4.7, 2.4.13, 2.5.3, 2.5.8 …)
# covers every BFS-discovered page without re-navigation. Imports are local to
# the helper that uses them to keep this module importable in test contexts
# that stub the pipeline.
from ka11y.accessibility.pipeline.extractors.element_context_extractor import (
    ElementContextExtractor,
)
from ka11y.accessibility.pipeline.extractors.semantic_relationship_engine import (
    SemanticRelationshipEngine,
)

logger = setup_logger(name="KAC", tag="universal_page")

# Number of pages the universal snapshot crawls in parallel. Each worker leases
# its own ``new_page()`` off the shared BrowserContext; 4 is the aggressive
# setting requested for EC2 and is overridable per-deploy. The hard
# ``max_pages`` budget still bounds total work regardless of concurrency.
_UNIVERSAL_PARALLEL_PAGES = max(
    1, int(os.environ.get("KA11Y_UNIVERSAL_PARALLEL_PAGES", "4"))
)

_GOTO_TIMEOUT_MS = 30_000
_NETWORKIDLE_TIMEOUT_MS = 15_000
_DOM_STABILITY_MS = 600
_DOM_STABILITY_TOTAL_MS = 12_000
_POST_SCROLL_WAIT_MS = 1_500
# Hard ceiling on the dedup set during chunked (infinite-scroll) extraction.
# Without it, a page that lazy-loads thousands of elements per scroll pass
# grows ``seen_refs`` unbounded across passes. Once we have catalogued this
# many distinct elements we stop scrolling for more.
_MAX_SEEN_REFS = 5_000

_SPA_SIGNALS = [
    "window.__NEXT_DATA__",
    "window.__nuxt",
    "window.__vue_app__",
    "window.React",
    "window.angular",
    "window.Ember",
    "window.__svelte",
    "document.querySelector('[data-reactroot]')",
]


class PageSnapshot(BaseModel):
    page_url: str
    media: List[Dict[str, Any]] = Field(default_factory=list)
    # Elements with a CSS background-image URL. Populated by background_images.js
    # so downstream image-audit hooks can flag informational backgrounds that
    # lack a text alternative (Sprint 3 / step 15).
    background_images: List[Dict[str, Any]] = Field(default_factory=list)
    # Pipeline element contexts, captured per page during the same visit that
    # populates the universal extractors. Each entry is
    # ``{"page_url": str, "contexts": List[ElementContext]}`` where contexts is
    # the Pydantic model from accessibility.pipeline.models. The DecisionEngine
    # consumes this side-channel offline so the unified pipeline does not need
    # to re-navigate every discovered page.
    pipeline_pages: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    element_refs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    page_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    pages_crawled: int = 0
    partial: bool = False
    har_path: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}


_COMBINED_EXTRACT_JS = r"""(frameMeta) => {
    const pageUrl = frameMeta?.pageUrl || location.href;
    const framePath = frameMeta?.framePath || 'main';
    const documentUrl = frameMeta?.documentUrl || location.href;

    function queryShadow(root, selector) {
        const results = [];
        const seen = new WeakSet();
        const queue = [root];

        while (queue.length) {
            const current = queue.shift();
            if (!current || !current.querySelectorAll) continue;

            current.querySelectorAll(selector).forEach(el => {
                if (!seen.has(el)) {
                    seen.add(el);
                    results.push(el);
                }
            });

            current.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) queue.push(el.shadowRoot);
            });
        }

        return results;
    }

    function queryShadowOne(root, selector) {
        const all = queryShadow(root, selector);
        return all.length ? all[0] : null;
    }

    function deepGetElementById(root, id) {
        if (!id) return null;
        const queue = [root];
        while (queue.length) {
            const current = queue.shift();
            if (!current) continue;
            if (current.getElementById) {
                const match = current.getElementById(id);
                if (match) return match;
            }
            if (!current.querySelectorAll) continue;
            current.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) queue.push(el.shadowRoot);
            });
        }
        return null;
    }

    function safeEscape(value) {
        if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value);
        return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    }

    function segmentFor(el) {
        const tag = (el.tagName || 'unknown').toLowerCase();
        if (el.id) return `${tag}#${safeEscape(el.id)}`;
        const classes = Array.from(el.classList || []).slice(0, 2).map(c => `.${safeEscape(c)}`).join('');
        let idx = 1;
        let sib = el;
        while ((sib = sib.previousElementSibling)) {
            if (sib.tagName === el.tagName) idx += 1;
        }
        return `${tag}${classes}:nth-of-type(${idx})`;
    }

    function selectorWithinRoot(el) {
        const segments = [];
        let cur = el;
        while (cur && cur.nodeType === Node.ELEMENT_NODE) {
            segments.unshift(segmentFor(cur));
            cur = cur.parentElement;
        }
        return segments.join(' > ');
    }

    function buildSelector(el) {
        const scopes = [];
        let cur = el;
        while (cur && cur.nodeType === Node.ELEMENT_NODE) {
            scopes.unshift(selectorWithinRoot(cur));
            const root = cur.getRootNode();
            cur = root && root.host ? root.host : null;
        }
        return scopes.filter(Boolean).join(' >>> ');
    }

    function outerHTML(el, max = 600) {
        return (el && el.outerHTML) ? el.outerHTML.slice(0, max) : '';
    }

    function resolveDescribedByText(el) {
        const ids = (el.getAttribute('aria-describedby') || '').trim();
        if (!ids) return null;
        const texts = ids.split(/\s+/).map(id => {
            const ref = deepGetElementById(document, id);
            return ref ? (ref.innerText || ref.textContent || '').trim() : '';
        }).filter(Boolean);
        return texts.length ? texts.join(' ').slice(0, 1000) : null;
    }

    function composedParent(el) {
        if (!el) return null;
        if (el.parentElement) return el.parentElement;
        const root = el.getRootNode ? el.getRootNode() : null;
        return root && root.host ? root.host : null;
    }

    function attributeSignalText(el) {
        if (!el || !el.getAttribute) return '';
        const className = typeof el.className === 'string'
            ? el.className
            : (el.className && typeof el.className.baseVal === 'string' ? el.className.baseVal : '');
        return [
            el.id || '',
            className || '',
            el.getAttribute('role') || '',
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || '',
            el.getAttribute('data-testid') || '',
            el.getAttribute('data-state') || '',
            el.getAttribute('name') || '',
        ].join(' ').replace(/\s+/g, ' ').trim().slice(0, 240);
    }

    function textSignal(el) {
        if (!el) return '';
        return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 240);
    }

    const COOKIE_ATTR_RE = /(?:cookie|consent|onetrust|cookiebot|optanon|usercentrics|trustarc|didomi|qc-cmp|privacy[-_ ](?:center|preference|preferences|choice|choices))/i;
    const COOKIE_TEXT_RE = /(?:cookie|consent|accept\s+all|reject\s+all|decline|manage\s+(?:choices|preferences|settings)|privacy\s+choices|your\s+privacy\s+choices|cookie\s+settings|cookie\s+preferences)/i;

    function isElementVisible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0) return false;

        let cur = el;
        let depth = 0;
        while (cur && depth < 12) {
            if (cur.nodeType === Node.ELEMENT_NODE) {
                if (cur.hasAttribute && cur.hasAttribute('hidden')) return false;
                const ariaHidden = ((cur.getAttribute && cur.getAttribute('aria-hidden')) || '').toLowerCase();
                if (ariaHidden === 'true') return false;
                const style = window.getComputedStyle(cur);
                if (style.display === 'none' || style.visibility === 'hidden') return false;
                if (parseFloat(style.opacity || '1') === 0) return false;
            }
            cur = composedParent(cur);
            depth += 1;
        }
        return true;
    }

    function isConsentUi(el) {
        let cur = el;
        let depth = 0;
        const selfText = textSignal(el);
        const selfRole = ((el.getAttribute && el.getAttribute('role')) || '').toLowerCase();
        const selfTag = (el.tagName || '').toLowerCase();
        const selfLooksLikeConsentControl =
            ['button', 'a', 'form', 'input', 'select', 'textarea'].includes(selfTag) ||
            selfRole === 'button' ||
            selfRole === 'dialog' ||
            selfRole === 'alertdialog' ||
            selfRole === 'banner';

        if (COOKIE_TEXT_RE.test(selfText) && selfLooksLikeConsentControl) return true;

        while (cur && depth < 6) {
            if (cur.nodeType === Node.ELEMENT_NODE) {
                if (COOKIE_ATTR_RE.test(attributeSignalText(cur))) return true;
                if (depth > 0) {
                    const role = ((cur.getAttribute && cur.getAttribute('role')) || '').toLowerCase();
                    const tag = (cur.tagName || '').toLowerCase();
                    if (
                        COOKIE_TEXT_RE.test(textSignal(cur)) &&
                        (role === 'dialog' || role === 'alertdialog' || role === 'banner' || tag === 'dialog')
                    ) {
                        return true;
                    }
                }
            }
            cur = composedParent(cur);
            depth += 1;
        }
        return false;
    }

    function shouldIgnoreForSnapshot(el) {
        return !isElementVisible(el) || isConsentUi(el);
    }

    if (!window._ka11yIdCounter) window._ka11yIdCounter = 1;
    function getKa11yId(el) {
        if (!el || !el.getAttribute || !el.setAttribute) return null;
        if (!el.getAttribute('data-ka11y-id')) {
            el.setAttribute('data-ka11y-id', 'k-' + (window._ka11yIdCounter++));
        }
        return el.getAttribute('data-ka11y-id');
    }

    function metaFor(el) {
        return {
            page_url: pageUrl,
            document_url: documentUrl,
            frame_path: framePath,
            selector: buildSelector(el),
            element_ref_id: getKa11yId(el) || undefined,
        };
    }

    const media = [];
    (function extractMedia() {
        function getNearbyLinks(el) {
            const links = [];
            let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                queryShadow(container, 'a[href]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const text = (a.innerText || a.textContent || '').trim();
                    if (href && text) links.push({ href, text: text.slice(0, 200) });
                });
                container = container.parentElement;
            }
            const seen = new Set();
            return links.filter(link => {
                if (seen.has(link.href)) return false;
                seen.add(link.href);
                return true;
            });
        }

        function getNearbyText(el) {
            const parent = el.parentElement;
            return parent ? (parent.innerText || parent.textContent || '').trim().slice(0, 500) : '';
        }

        function getNearbyDetails(el) {
            const results = [];
            let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                queryShadow(container, 'details').forEach(details => {
                    const summary = details.querySelector('summary');
                    results.push({
                        summary: (summary ? summary.innerText || summary.textContent || '' : '').trim().slice(0, 200),
                        content: (details.innerText || details.textContent || '').trim().slice(0, 1000),
                    });
                });
                container = container.parentElement;
            }
            return results;
        }

        function tracksFor(el) {
            const tracks = [];
            queryShadow(el, 'track').forEach(track => {
                tracks.push({
                    kind: track.getAttribute('kind') || null,
                    src: track.getAttribute('src') || null,
                    srclang: track.getAttribute('srclang') || null,
                    label: track.getAttribute('label') || null,
                });
            });
            return tracks;
        }

        queryShadow(document, 'audio, video').forEach(el => {
            if (shouldIgnoreForSnapshot(el)) return;
            media.push({
                ...metaFor(el),
                element_index: media.length,
                tag: el.tagName.toUpperCase(),
                element_id: el.id || null,
                src: el.currentSrc || el.getAttribute('src') || (el.querySelector('source[src]') || {}).src || null,
                html_snippet: outerHTML(el, 500),
                has_autoplay: el.hasAttribute('autoplay'),
                has_controls: el.hasAttribute('controls'),
                has_loop: el.hasAttribute('loop'),
                is_muted: !!el.muted || el.hasAttribute('muted'),
                tracks: tracksFor(el),
                aria_hidden: el.getAttribute('aria-hidden') === 'true',
                role: el.getAttribute('role') || null,
                aria_label: el.getAttribute('aria-label') || null,
                aria_describedby_text: resolveDescribedByText(el),
                nearby_links: getNearbyLinks(el),
                nearby_text: getNearbyText(el),
                nearby_details: getNearbyDetails(el),
            });
        });
    })();

    return {
        media,
    };
}
"""

_LINK_EXTRACT_JS = r"""() => {
    function queryShadow(root, selector) {
        const results = [];
        const queue = [root];
        const seen = new Set();
        while (queue.length) {
            const current = queue.shift();
            if (!current || !current.querySelectorAll) continue;
            current.querySelectorAll(selector).forEach(el => {
                if (!seen.has(el)) {
                    seen.add(el);
                    results.push(el);
                }
            });
            current.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) queue.push(el.shadowRoot);
            });
        }
        return results;
    }

    return queryShadow(document, 'a[href]')
        .map(a => a.href || a.getAttribute('href'))
        .filter(Boolean);
}
"""

_LAZY_LOAD_TRIGGER_JS = r"""async () => {
    document.querySelectorAll('[data-src],[data-lazy-src],[data-original],[loading="lazy"]').forEach(el => {
        ['lazyload', 'lazyloaded', 'lazy-load'].forEach(evt => el.dispatchEvent(new Event(evt, { bubbles: true })));
        if (el.dataset.src) el.src = el.dataset.src;
        if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
        if (el.dataset.original) el.src = el.dataset.original;
    });

    const totalHeight = document.documentElement.scrollHeight;
    const steps = 6;
    for (let i = 1; i <= steps; i++) {
        window.scrollTo(0, (totalHeight / steps) * i);
        await new Promise(resolve => setTimeout(resolve, 200));
    }
    window.scrollTo(0, 0);
}
"""

_BACKGROUND_IMAGES_JS = r"""// Sprint 3 / step 15. The existing universal extractor records
// `has_bg_image: bool` per form/interactive element but never extracts the
// URL or surfaces non-form elements whose only image is a CSS background.
// Informational hero divs / aria-labelled banner divs are therefore
// invisible to the image audit (a known false-negative source).
//
// This pass walks every visible element (piercing open shadow roots),
// extracts the URL list from computed-style `background-image`, and
// reports the element's accessible-name signals so the audit can decide
// whether a text alternative is required.

(frameMeta) => {
    const pageUrl = frameMeta?.pageUrl || location.href;
    const framePath = frameMeta?.framePath || 'main';
    const documentUrl = frameMeta?.documentUrl || location.href;

    function queryShadow(root, selector) {
        const results = [];
        const seen = new WeakSet();
        const queue = [root];
        while (queue.length) {
            const current = queue.shift();
            if (!current || !current.querySelectorAll) continue;
            current.querySelectorAll(selector).forEach(el => {
                if (!seen.has(el)) {
                    seen.add(el);
                    results.push(el);
                }
            });
            current.querySelectorAll('*').forEach(el => {
                if (el.shadowRoot) queue.push(el.shadowRoot);
            });
        }
        return results;
    }

    function isVisible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width < 4 || rect.height < 4) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') return false;
        if (parseFloat(style.opacity || '1') === 0) return false;
        return true;
    }

    function safeEscape(value) {
        if (typeof CSS !== 'undefined' && CSS.escape) return CSS.escape(value);
        return String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
    }

    function buildSelector(el) {
        const segments = [];
        let cur = el;
        while (cur && cur.nodeType === Node.ELEMENT_NODE && segments.length < 6) {
            const tag = (cur.tagName || 'unknown').toLowerCase();
            if (cur.id) {
                segments.unshift(`${tag}#${safeEscape(cur.id)}`);
                break;
            }
            const cls = Array.from(cur.classList || []).slice(0, 2)
                .map(c => `.${safeEscape(c)}`).join('');
            segments.unshift(`${tag}${cls}`);
            cur = cur.parentElement;
        }
        return segments.join(' > ');
    }

    // Strip CSS gradients / variables / "none" / "initial" and pull only the
    // url(...) tokens out of a (possibly multi-layered) background-image value.
    function extractUrls(bgImage) {
        if (!bgImage || bgImage === 'none' || bgImage === 'initial') return [];
        const urls = [];
        const re = /url\((?:"([^"]+)"|'([^']+)'|([^)]+))\)/g;
        let m;
        while ((m = re.exec(bgImage)) !== null) {
            const raw = (m[1] || m[2] || m[3] || '').trim();
            if (raw && !raw.startsWith('data:')) {
                try {
                    urls.push(new URL(raw, location.href).href);
                } catch (_) {
                    urls.push(raw);
                }
            }
        }
        return urls;
    }

    const results = [];
    const seen = new Set();

    queryShadow(document, '*').forEach(el => {
        if (!isVisible(el)) return;
        const style = window.getComputedStyle(el);
        const urls = extractUrls(style.backgroundImage);
        if (!urls.length) return;

        const ariaLabel = (el.getAttribute('aria-label') || '').trim();
        const role = (el.getAttribute('role') || '').toLowerCase();
        const ariaHidden = (el.getAttribute('aria-hidden') || '').toLowerCase() === 'true';
        // Visible text inside the element counts as a text alternative for
        // the background image (banner with copy doesn't need its bg
        // duplicated as alt text).
        const innerText = (el.innerText || el.textContent || '').trim();
        const hasTextAlternative = !!(ariaLabel || (innerText && innerText.length > 1));

        urls.forEach(url => {
            const key = `${buildSelector(el)}::${url}`;
            if (seen.has(key)) return;
            seen.add(key);
            results.push({
                page_url: pageUrl,
                document_url: documentUrl,
                frame_path: framePath,
                selector: buildSelector(el),
                tag: (el.tagName || '').toLowerCase(),
                element_id: el.id || null,
                url: url,
                role: role || null,
                aria_label: ariaLabel || null,
                aria_hidden: ariaHidden,
                has_text_alternative: hasTextAlternative,
                inner_text_snippet: innerText.slice(0, 120) || null,
                bbox: (() => {
                    const r = el.getBoundingClientRect();
                    return {
                        x: Math.round(r.left),
                        y: Math.round(r.top),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                    };
                })(),
            });
        });
    });

    return results;
}
"""


_DOM_STABILITY_JS = f"""(stabilityMs) => {{
    return new Promise((resolve) => {{
        let timer = null;
        const start = Date.now();
        function reset() {{
            if (timer) clearTimeout(timer);
            if (Date.now() - start > {_DOM_STABILITY_TOTAL_MS}) {{
                resolve('timeout');
                return;
            }}
            timer = setTimeout(() => resolve('stable'), stabilityMs);
        }}
        reset();
        const observer = new MutationObserver(() => reset());
        observer.observe(document.body, {{ childList: true, subtree: true }});
        setTimeout(() => {{
            observer.disconnect();
            resolve('total_timeout');
        }}, {_DOM_STABILITY_TOTAL_MS});
    }});
}}"""


class UniversalPageLoader:
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    @classmethod
    async def load(
        cls,
        url: str,
        output_dir: Path,
        *,
        max_depth: int = 0,
        max_pages: int = 50,
        internal_links: bool = True,
        record_har: bool = False,
        step_logger: ExecutionStepLogger | None = None,
        policy: CrawlPolicy | None = None,
        seed_url: Optional[List[str]] = None,
    ) -> PageSnapshot:
        """
        Main entry point for universal crawling. Uses a single browser session
        and a bounded queue (Optimized v2).

        ``max_pages`` / ``internal_links`` are honoured when no explicit
        ``policy`` is supplied — previously they were ignored here and the page
        budget was hardcoded to 50, so a direct ``load()`` call (any path that
        didn't build its own policy) silently capped the crawl regardless of the
        request. ``_load_universal_snapshot`` still passes an explicit policy, so
        this only affects callers that rely on the defaults.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        if policy is None:
            policy = CrawlPolicy(
                max_depth=max_depth,
                max_pages=max_pages,
                max_links_per_page=max(50, max_pages),
                same_origin=internal_links,
            )

        snapshot = PageSnapshot(page_url=url)
        har_path: Optional[str] = None
        har_file = output_dir / "universal_session.har"

        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="running",
                message="Starting universal crawl (queue-based)",
                context={"url": url, "max_depth": max_depth, "record_har": record_har},
            )

        from collections import deque

        queue: deque[tuple[str, int]] = deque()
        if seed_url:
            for su in seed_url:
                queue.append((su, 0))
        else:
            queue.append((url, 0))

        visited: set[str] = set()

        from ka11y.crawler.browser_pool import leased_context

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": cls.USER_AGENT,
        }
        if record_har:
            context_kwargs["record_har_path"] = str(har_file)
            context_kwargs["record_har_url_filter"] = "**/*"

        # Parallel BFS: up to _UNIVERSAL_PARALLEL_PAGES pages crawl
        # concurrently against the SAME BrowserContext (one Chromium, many
        # Pages). BFS ordering is preserved because the queue is consumed in
        # FIFO order and discovered links are appended as workers finish.
        # ``visited`` is updated *before* a task launches so no two workers
        # ever crawl the same URL, and ``snapshot.pages_crawled`` (incremented
        # inside ``_crawl_one_url``) gates further launches once the budget
        # is hit. Per-page extraction code only mutates ``snapshot`` between
        # awaits, so the single-threaded asyncio interleaving keeps appends
        # to the shared lists safe.
        async with leased_context(**context_kwargs) as context:
            inflight: Dict[asyncio.Task, int] = {}

            def _can_launch() -> bool:
                # In-flight tasks already count against the budget, since each
                # increments ``pages_crawled`` only AFTER its work succeeds.
                # Bound launches by the budget MINUS what's still running so
                # we don't briefly over-shoot ``max_pages``.
                return (
                    snapshot.pages_crawled + len(inflight)
                ) < policy.max_pages

            budget_hit = False
            while queue or inflight:
                while (
                    queue
                    and len(inflight) < _UNIVERSAL_PARALLEL_PAGES
                    and not budget_hit
                ):
                    if not _can_launch():
                        logger.warning(
                            f"[universal] crawl budget reached "
                            f"({policy.max_pages} pages); not launching more"
                        )
                        budget_hit = True
                        break

                    current_url, current_depth = queue.popleft()
                    normalized_url = policy.normalize_url(current_url)

                    if not normalized_url or normalized_url in visited:
                        continue
                    visited.add(normalized_url)

                    if not policy.is_allowed(normalized_url, url):
                        logger.info(
                            f"[universal] skipping off-origin/disallowed URL: "
                            f"{normalized_url}"
                        )
                        continue

                    task = asyncio.create_task(
                        cls._crawl_one_url(
                            context=context,
                            root_url=url,
                            url=normalized_url,
                            depth=current_depth,
                            policy=policy,
                            output=snapshot,
                            step_logger=step_logger,
                        )
                    )
                    inflight[task] = current_depth

                if not inflight:
                    break

                done, _pending = await asyncio.wait(
                    inflight.keys(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    depth = inflight.pop(task)
                    try:
                        new_links = await task
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"[universal] page task raised: {exc}")
                        new_links = []
                    if depth < policy.max_depth and not budget_hit:
                        for link in new_links:
                            queue.append((link, depth + 1))

        if record_har and har_file.exists():
            har_path = str(har_file)

        snapshot.har_path = har_path

        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="completed",
                message="Universal crawl completed",
                context={
                    "pages_crawled": snapshot.pages_crawled,
                    "media": len(snapshot.media),
                    "warnings": len(snapshot.warnings),
                    "har_path": har_path,
                },
            )

        return snapshot

    @classmethod
    async def _crawl_one_url(
        cls,
        *,
        context: BrowserContext,
        root_url: str,
        url: str,
        depth: int,
        policy: CrawlPolicy,
        output: PageSnapshot,
        step_logger: ExecutionStepLogger | None,
    ) -> List[str]:
        page = await context.new_page()
        page_warning_count = 0
        links: List[str] = []

        try:
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="running",
                    message="Opening page",
                    context={"url": url, "depth": depth},
                )

            await cls._prepare_page(page, url, step_logger=step_logger)

            # Stamp every finding with the URL the page actually resolved to,
            # not the URL we queued. A child discovered as ``/worldwide`` may
            # 301 to ``/worldwide.html`` (or vice-versa); when that same page is
            # audited directly the caller passes the resolved form. Stamping the
            # requested URL split one child page's findings across two page_url
            # buckets — and because Node now stamps ``page.url()`` too, both
            # engines must agree on the resolved identity or the buckets diverge
            # again. ``canonicalize_url`` keeps the key consistent with the
            # finding-stamp sites; fall back to the queued URL if the browser
            # reports nothing usable (e.g. ``about:blank`` after a hard nav fail).
            # NB: Playwright-Python exposes ``page.url`` as a property (the JS
            # binding uses ``page.url()`` — do not add parens here).
            resolved_url = canonicalize_url(page.url or "") or url

            # Chunked extraction to combat virtualized DOMs (Infinite scroll)
            await cls._extract_page_chunked(page, page_url=resolved_url, output=output)

            # Pipeline element contexts for this page. Runs on the same loaded
            # page as the universal extractor — every page reached by the BFS
            # gets pipeline coverage, not just the root. Failures degrade to a
            # warning and never abort the snapshot.
            await cls._extract_pipeline_contexts(
                page=page, page_url=resolved_url, output=output, step_logger=step_logger
            )

            # Links extraction can just use the final state. We hand the
            # active CrawlPolicy in so its normalize_url drives href dedup;
            # the previous code called ``cls._normalize_url`` which never
            # existed and silently returned an empty list, so the universal
            # BFS only ever visited the entry URL even at max_depth>0.
            links = await cls._extract_links(page, root_url=url, policy=policy)

            # Limit links per page
            if len(links) > policy.max_links_per_page:
                logger.info(
                    f"[universal] capping links from {len(links)} to {policy.max_links_per_page}"
                )
                links = links[: policy.max_links_per_page]

            def _count_for_url(collection: list) -> int:
                return len([r for r in collection if r.get("page_url") == resolved_url])

            page_media = _count_for_url(output.media)

            output.page_summaries.append(
                {
                    "page_url": resolved_url,
                    "depth": depth,
                    "media": page_media,
                    "links_found": len(links),
                }
            )
            output.pages_crawled += 1
            page_warning_count = len(
                [w for w in output.warnings if w.get("page_url") == resolved_url]
            )

            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="completed",
                    message="Extracted page",
                    context={
                        "url": url,
                        "depth": depth,
                        "media": page_media,
                        "links_found": len(links),
                        "warnings": page_warning_count,
                    },
                )
        except NavigationError as exc:
            # Captured as warning instead of hard error for universal crawl
            warning = {
                "code": exc.code,
                "page_url": url,
                "message": str(exc),
            }
            output.warnings.append(warning)
            logger.warning(f"[universal] {exc.code} for {url}: {exc}")
        except Exception as exc:
            output.partial = True
            warning = {
                "code": "page_extract_failed",
                "page_url": url,
                "message": str(exc),
            }
            output.warnings.append(warning)
            logger.warning(f"[universal] failed to extract {url}: {exc}")
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="error",
                    message="Page extraction failed",
                    context=warning,
                )
        finally:
            await page.close()

        return links

    @classmethod
    async def _prepare_page(
        cls,
        page: Page,
        url: str,
        *,
        step_logger: ExecutionStepLogger | None,
    ) -> None:
        await navigate_with_resilience(page, url)

        try:
            await page.wait_for_load_state(
                "networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS
            )
        except Exception:
            logger.debug(f"[universal] networkidle timeout for {url}")

        await cls._wait_for_spa(page)

        # ── Cookie Handling ──
        try:
            cookie_state = await handle_cookies(page)
            logger.debug(f"[universal] Cookie handling state for {url}: {cookie_state}")
        except Exception as e:
            logger.debug(f"[universal] Cookie handling exception for {url}: {e}")

        try:
            await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
        except Exception:
            logger.debug(f"[universal] DOM stability pre-check failed for {url}")

        if step_logger:
            step_logger.record(
                step="universal_page_ready",
                status="completed",
                message="Page reached extraction-ready state",
                context={"url": url},
            )

    @classmethod
    async def _extract_page_chunked(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
    ) -> None:
        """Extracts DOM in chunks by scrolling to bypass Virtualized DOMs."""
        seen_refs = set()

        # Read max scroll passes from config (fallback to 4)
        max_passes = 4

        # Trigger initial lazy-load setup without scrolling
        initial_lazy_js = """async () => {
            document.querySelectorAll('[data-src],[data-lazy-src],[data-original],[loading="lazy"]').forEach(el => {
                ['lazyload', 'lazyloaded', 'lazy-load'].forEach(evt => el.dispatchEvent(new Event(evt, { bubbles: true })));
                if (el.dataset.src) el.src = el.dataset.src;
                if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
                if (el.dataset.original) el.src = el.dataset.original;
            });
        }"""
        try:
            await page.evaluate(initial_lazy_js)
        except Exception:
            pass

        for i in range(max_passes):
            # 1. Wait for stability before extracting
            try:
                await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
            except Exception:
                pass

            # 2. Extract current viewport/DOM chunk
            await cls._extract_page(
                page, page_url=page_url, output=output, seen_refs=seen_refs
            )

            # 3. Stop if the dedup set has hit its ceiling — further scrolling
            # on a pathological infinite-scroll page would only grow memory.
            if len(seen_refs) >= _MAX_SEEN_REFS:
                output.partial = True
                break

            # 4. Check if we hit the bottom of the page
            is_at_bottom = await page.evaluate(
                "() => { const h = document.documentElement; return (window.innerHeight + window.scrollY) >= (h.scrollHeight - 100); }"
            )
            if is_at_bottom:
                break

            # 5. Scroll down
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await page.wait_for_timeout(_POST_SCROLL_WAIT_MS)

        # Reset scroll position to top
        await page.evaluate("window.scrollTo(0, 0)")

    @classmethod
    async def _extract_pipeline_contexts(
        cls,
        *,
        page: Page,
        page_url: str,
        output: PageSnapshot,
        step_logger: ExecutionStepLogger | None,
    ) -> None:
        """Run the unified-pipeline extractors against the currently-loaded
        page and append the resulting contexts to ``output.pipeline_pages``.

        This is what closes the multi-page coverage gap: every BFS-visited
        page contributes its own contexts so DecisionEngine can produce
        verdicts per page, not just for the root URL. The work runs in three
        steps that must touch the live page:

        1. ElementContextExtractor.extract_contexts — gathers element data.
        2. SemanticRelationshipEngine.enrich_semantics — resolves aria-*
           references against the document; mutates contexts in place.

        Failures degrade to a warning + an empty entry so DecisionEngine
        can still report "no findings here" rather than the page being
        silently dropped from the pipeline output.
        """
        contexts: list = []
        try:
            contexts = await ElementContextExtractor.extract_contexts(page)
            if contexts:
                await SemanticRelationshipEngine.enrich_semantics(page, contexts)
        except Exception as exc:  # noqa: BLE001 — pipeline must not abort the crawl
            output.partial = True
            output.warnings.append(
                {
                    "code": "pipeline_extract_failed",
                    "page_url": page_url,
                    "message": str(exc),
                }
            )
            logger.warning(
                f"[universal] pipeline extraction failed for {page_url}: {exc}"
            )
            contexts = []

        output.pipeline_pages.append(
            {"page_url": page_url, "contexts": contexts}
        )

        if step_logger:
            step_logger.record(
                step="universal_pipeline",
                status="completed",
                message="Pipeline contexts captured",
                context={
                    "url": page_url,
                    "contexts": len(contexts),
                },
            )

    @classmethod
    async def _extract_page(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
        seen_refs: set[str] | None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        combined = {
            "media": [],
        }

        frames = await cls._collect_same_origin_frames(
            page, page_url=page_url, output=output
        )
        for frame, frame_path in frames:
            if frame.is_detached():
                # Silently skip detached frames if they were just transient/blank
                if not frame.url or frame.url == "about:blank":
                    continue

            try:
                frame_data = await frame.evaluate(
                    _COMBINED_EXTRACT_JS,
                    {
                        "pageUrl": page_url,
                        "framePath": frame_path,
                        "documentUrl": frame.url or page_url,
                    },
                )
            except Exception as exc:
                output.partial = True
                warning = await cls._build_frame_warning(
                    code="frame_extract_failed",
                    page_url=page_url,
                    frame=frame,
                    frame_path=frame_path,
                    message=str(exc),
                    error_type=type(exc).__name__,
                )
                output.warnings.append(warning)
                continue

            for key in combined:
                records = frame_data.get(key) or []
                cls._annotate_records(
                    output=output,
                    category=key,
                    page_url=page_url,
                    frame_path=frame_path,
                    records=records,
                    seen_refs=seen_refs,
                )
                combined[key].extend(records)

            # Per-category extractor faults (B-3). The universal extractor now
            # isolates each category in its own try/catch, so a failure in one
            # no longer zeroes all seven. Surface any that failed as warnings
            # instead of losing the signal.
            extractor_errors = frame_data.get("_errors") or {}
            for category, err in extractor_errors.items():
                output.partial = True
                warning = await cls._build_frame_warning(
                    code="category_extract_failed",
                    page_url=page_url,
                    frame=frame,
                    frame_path=frame_path,
                    message=f"{category} extractor failed: {err}",
                    error_type="ExtractorError",
                )
                output.warnings.append(warning)

            # Separate pass: extract CSS background-image URLs. Kept out of
            # the universal extractor to avoid bloating its single page.evaluate
            # payload (Sprint 3 / step 15).
            try:
                bg_records = await frame.evaluate(
                    _BACKGROUND_IMAGES_JS,
                    {
                        "pageUrl": page_url,
                        "framePath": frame_path,
                        "documentUrl": frame.url or page_url,
                    },
                )
            except Exception:
                bg_records = []
            if bg_records:
                output.background_images.extend(bg_records)

        return combined

    @classmethod
    def _annotate_records(
        cls,
        *,
        output: PageSnapshot,
        category: str,
        page_url: str,
        frame_path: str,
        records: List[Dict[str, Any]],
        seen_refs: set[str] | None = None,
    ) -> None:
        bucket: List[Dict[str, Any]] = getattr(output, category)
        for idx, record in enumerate(records):
            entry = dict(record)
            entry["page_url"] = page_url
            entry.setdefault("frame_path", frame_path)
            entry.setdefault("selector", None)
            ref_id = entry.get("element_ref_id") or cls._make_ref_id(
                category=category,
                page_url=page_url,
                frame_path=frame_path,
                selector=entry.get("selector"),
                element_id=entry.get("id") or entry.get("element_id"),
                html=entry.get("html") or entry.get("html_snippet") or "",
                index=idx,
            )

            # Deduplication for virtualized DOMs (Infinite scroll chunking)
            if seen_refs is not None:
                if ref_id in seen_refs:
                    continue
                seen_refs.add(ref_id)

            entry["element_ref_id"] = ref_id
            bucket.append(entry)
            output.element_refs[ref_id] = {
                "category": category,
                "page_url": page_url,
                "document_url": entry.get("document_url") or page_url,
                "frame_path": frame_path,
                "selector": entry.get("selector"),
                "element_id": entry.get("id") or entry.get("element_id"),
                "tag": entry.get("tag"),
            }

    @classmethod
    async def _extract_links(
        cls, page: Page, root_url: str, policy: CrawlPolicy
    ) -> List[str]:
        try:
            raw_links: List[str] = await page.evaluate(_LINK_EXTRACT_JS)
        except Exception:
            return []

        resolved: List[str] = []
        for href in raw_links:
            try:
                url = policy.normalize_url(urljoin(page.url or root_url, href))
            except Exception:
                continue
            if not url:
                continue
            if not cls._is_same_origin(root_url, url):
                continue
            resolved.append(url)
        return list(dict.fromkeys(resolved))

    @classmethod
    async def _collect_same_origin_frames(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
    ) -> List[tuple]:
        frames: List[tuple] = []

        async def walk(frame, path: str) -> None:
            frames.append((frame, path))
            for index, child in enumerate(frame.child_frames):
                child_path = f"{path}.{index}"
                child_url = child.url or ""
                if child_url and not cls._is_same_origin(page_url, child_url):
                    logger.info(
                        f"Skipped cross-origin frame during universal extraction: {child_url}"
                    )
                    output.partial = True
                    continue
                await walk(child, child_path)

        await walk(page.main_frame, "main")
        return frames

    @classmethod
    async def _build_frame_warning(
        cls,
        *,
        code: str,
        page_url: str,
        frame,
        frame_path: str,
        message: str,
        error_type: str | None = None,
    ) -> Dict[str, Any]:
        warning: Dict[str, Any] = {
            "code": code,
            "page_url": page_url,
            "frame_path": frame_path,
            "parent_frame_path": frame_path.rpartition(".")[0] or None,
            "document_url": frame.url or page_url,
            "frame_name": getattr(frame, "name", "") or None,
            "message": message,
        }
        if error_type:
            warning["error_type"] = error_type

        try:
            frame_el = await frame.frame_element()
        except Exception:
            frame_el = None

        if frame_el is None:
            return warning

        try:
            frame_meta = await frame_el.evaluate("""(el) => ({
                    tag: (el.tagName || '').toLowerCase(),
                    id: el.id || null,
                    name_attr: el.getAttribute('name'),
                    title: el.getAttribute('title'),
                    src: el.getAttribute('src'),
                    sandbox: el.getAttribute('sandbox'),
                    loading: el.getAttribute('loading'),
                    referrerpolicy: el.getAttribute('referrerpolicy'),
                    allow: el.getAttribute('allow'),
                    aria_label: el.getAttribute('aria-label'),
                    html_snippet: (el.outerHTML || '').slice(0, 240),
                })""")
        except Exception:
            frame_meta = None

        if isinstance(frame_meta, dict):
            for key, value in frame_meta.items():
                if value not in (None, "", []):
                    warning[key] = value

        return warning

    @staticmethod
    async def _wait_for_spa(page: Page) -> None:
        for signal in _SPA_SIGNALS:
            try:
                found = await page.evaluate(f"() => !!({signal})")
                if found:
                    await page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    @staticmethod
    def _make_ref_id(
        *,
        category: str,
        page_url: str,
        frame_path: str,
        selector: str | None,
        element_id: str | None,
        html: str,
        index: int,
    ) -> str:
        basis = "|".join(
            [
                category,
                page_url,
                frame_path,
                selector or "",
                element_id or "",
                html[:120],
                str(index),
            ]
        )
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
        return f"{category}_{digest}"

    @staticmethod
    def _is_same_origin(base_url: str, other_url: str) -> bool:
        if not other_url or other_url.startswith("about:"):
            return True
        base = urlparse(base_url)
        other = urlparse(other_url)

        def default_port(parsed) -> int | None:
            if parsed.port:
                return parsed.port
            if parsed.scheme == "https":
                return 443
            if parsed.scheme == "http":
                return 80
            return None

        return (
            base.scheme == other.scheme
            and base.hostname == other.hostname
            and default_port(base) == default_port(other)
        )

    @staticmethod
    def save_snapshot(snapshot: PageSnapshot, output_dir: Path) -> str:
        path = output_dir / "universal_snapshot_raw.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(snapshot.model_dump(), fh, indent=2, ensure_ascii=False)
        return str(path)
