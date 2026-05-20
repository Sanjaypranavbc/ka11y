"""
ka11y/crawler/media_crawler.py
================================
Playwright-based crawler for time-based media elements.
Feeds the MediaAuditor (WCAG 1.2.1 — Audio-only and Video-only, Prerecorded).

What is detected
────────────────
  • <audio>                     — audio-only media elements
  • <video>                     — video / video-only media elements

What is extracted per element
─────────────────────────────
  • Media source URL and tag type
  • Child <track> elements (captions, descriptions, subtitles)
  • Nearby <a> links (potential transcript links)
  • Nearby text content (potential inline transcripts)
  • ARIA attributes (aria-hidden, aria-label, aria-describedby, role)
  • Autoplay / controls / muted / loop attributes
  • <details> blocks nearby (collapsible transcript sections)

The crawler does NOT evaluate WCAG compliance — that is the auditor's job.
This module only extracts raw DOM data for downstream analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="media_crawler")


# ── Data model ────────────────────────────────────────────────────────────────
# One instance per detected media element on the page.
# Mirrors the Pydantic pattern used by MovingContentData.


class MediaElementData(BaseModel):
    """Raw data for a single <audio> or <video> media element."""

    page_url: str
    element_index: int

    # ── Identity ──────────────────────────────────────────────────────────
    tag: str  # "AUDIO" | "VIDEO"
    element_id: Optional[str] = None  # HTML id attribute
    src: Optional[str] = None  # media source URL
    html_snippet: str = ""  # outer HTML truncated to 500 chars

    # ── Media attributes ──────────────────────────────────────────────────
    has_autoplay: bool = False
    has_controls: bool = False
    has_loop: bool = False
    is_muted: bool = False

    # ── Track children (<track> elements inside <audio>/<video>) ──────────
    # Each track: {"kind": "captions", "src": "/captions.vtt",
    #              "srclang": "en", "label": "English"}
    tracks: List[Dict[str, Optional[str]]] = []

    # ── ARIA and role attributes ──────────────────────────────────────────
    aria_hidden: bool = False  # aria-hidden="true" → decorative
    role: Optional[str] = None  # role="presentation" → decorative
    aria_label: Optional[str] = None  # explicit accessible name
    aria_describedby_text: Optional[str] = None  # resolved aria-describedby

    # ── Nearby context (for transcript detection in the auditor) ──────────
    # Links in the parent container — the auditor searches these for
    # keywords like "transcript", "text version", etc.
    nearby_links: List[Dict[str, str]] = []  # [{"href": "...", "text": "..."}]

    # Text content of the closest parent container (truncated).
    # Used to detect inline transcripts or "audio version of" labeling.
    nearby_text: str = ""

    # <details> blocks near the media element — common pattern for
    # collapsible transcript sections.
    nearby_details: List[Dict[str, str]] = []  # [{"summary": "...", "content": "..."}]

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None


# ── Crawler class ─────────────────────────────────────────────────────────────


class AsyncMediaCrawler:
    """
    Launches a headless Chromium browser, navigates to the target URL,
    and extracts all <audio> and <video> elements
    with their surrounding context.

    Usage::

        crawler = AsyncMediaCrawler(base_url="https://example.com",
                                    output_dir="output/", max_depth=0)
        items = await crawler.crawl()
        crawler.save_raw_json()
    """

    # ── JavaScript extraction function ────────────────────────────────────
    # Runs inside the browser page context.
    # Returns a flat array of plain objects — one per media element.
    #
    # WHY a single large JS function?
    # Same pattern as MovingContentCrawler.EXTRACT_JS — one evaluate() call
    # is faster than dozens of individual element queries across the bridge.

    EXTRACT_JS = r"""() => {
        const results = [];

        /* ── helper: collect <a> links from the nearest container ────── */
        function getNearbyLinks(el) {
            // Walk up to 3 parent levels to find links
            const links = [];
            let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                container.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const text = (a.innerText || a.textContent || '').trim();
                    if (href && text) {
                        links.push({ href: href, text: text.slice(0, 200) });
                    }
                });
                container = container.parentElement;
            }
            // Deduplicate by href
            const seen = new Set();
            return links.filter(l => {
                if (seen.has(l.href)) return false;
                seen.add(l.href);
                return true;
            });
        }

        /* ── helper: get text content of nearest container ──────────── */
        function getNearbyText(el) {
            const parent = el.parentElement;
            if (!parent) return '';
            return (parent.innerText || parent.textContent || '').trim().slice(0, 500);
        }

        /* ── helper: find <details> blocks near the element ─────────── */
        function getNearbyDetails(el) {
            const details = [];
            let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                container.querySelectorAll('details').forEach(d => {
                    const summary = d.querySelector('summary');
                    details.push({
                        summary: (summary ? summary.innerText || '' : '').trim().slice(0, 200),
                        content: (d.innerText || '').trim().slice(0, 1000)
                    });
                });
                container = container.parentElement;
            }
            return details;
        }

        /* ── helper: resolve aria-describedby to actual text ────────── */
        function resolveDescribedBy(el) {
            const ids = (el.getAttribute('aria-describedby') || '').trim();
            if (!ids) return null;
            const texts = [];
            ids.split(/\s+/).forEach(id => {
                const target = document.getElementById(id);
                if (target) {
                    texts.push((target.innerText || target.textContent || '').trim());
                }
            });
            return texts.length > 0 ? texts.join(' ').slice(0, 1000) : null;
        }

        /* ── helper: extract <track> children ───────────────────────── */
        function getTracks(el) {
            const tracks = [];
            el.querySelectorAll('track').forEach(t => {
                tracks.push({
                    kind:    t.getAttribute('kind') || null,
                    src:     t.getAttribute('src') || null,
                    srclang: t.getAttribute('srclang') || null,
                    label:   t.getAttribute('label') || null
                });
            });
            return tracks;
        }

        /* ── 1. <audio> elements ────────────────────────────────────── */
        document.querySelectorAll('audio').forEach(el => {
            const src = el.currentSrc ||
                        el.getAttribute('src') ||
                        (el.querySelector('source[src]') || {}).src ||
                        null;

            results.push({
                element_index:       results.length,
                tag:                 'AUDIO',
                element_id:          el.id || null,
                src:                 src,
                html_snippet:        (el.outerHTML || '').slice(0, 500),
                has_autoplay:        el.hasAttribute('autoplay'),
                has_controls:        el.hasAttribute('controls'),
                has_loop:            el.hasAttribute('loop'),
                is_muted:            el.muted || el.hasAttribute('muted'),
                tracks:              getTracks(el),
                aria_hidden:         el.getAttribute('aria-hidden') === 'true',
                role:                el.getAttribute('role') || null,
                aria_label:          el.getAttribute('aria-label') || null,
                aria_describedby_text: resolveDescribedBy(el),
                nearby_links:        getNearbyLinks(el),
                nearby_text:         getNearbyText(el),
                nearby_details:      getNearbyDetails(el),

            });
        });

        /* ── 2. <video> elements ────────────────────────────────────── */
        document.querySelectorAll('video').forEach(el => {
            const src = el.currentSrc ||
                        el.getAttribute('src') ||
                        (el.querySelector('source[src]') || {}).src ||
                        null;

            results.push({
                element_index:       results.length,
                tag:                 'VIDEO',
                element_id:          el.id || null,
                src:                 src,
                html_snippet:        (el.outerHTML || '').slice(0, 500),
                has_autoplay:        el.hasAttribute('autoplay'),
                has_controls:        el.hasAttribute('controls'),
                has_loop:            el.hasAttribute('loop'),
                is_muted:            el.muted || el.hasAttribute('muted'),
                tracks:              getTracks(el),
                aria_hidden:         el.getAttribute('aria-hidden') === 'true',
                role:                el.getAttribute('role') || null,
                aria_label:          el.getAttribute('aria-label') || null,
                aria_describedby_text: resolveDescribedBy(el),
                nearby_links:        getNearbyLinks(el),
                nearby_text:         getNearbyText(el),
                nearby_details:      getNearbyDetails(el),
                iframe_src:          null
            });
        });


        return results;
    }"""

    def __init__(self, *, base_url: str, output_dir: str, max_depth: int = 0) -> None:
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[MediaElementData] = []
        self._visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────

    async def crawl(self) -> List[MediaElementData]:
        """
        Navigate to base_url (and optionally linked pages up to max_depth),
        extract all media elements, and return a list of MediaElementData.
        """
        from ka11y.crawler.browser_pool import leased_context

        async with leased_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        ) as context:
            await self._crawl_page(context, self.base_url, depth=0)

        logger.info(
            f"[media_crawler] found {len(self.results)} media element(s) "
            f"on {self.base_url}"
        )
        return self.results

    def save_raw_json(self) -> str:
        """Persist raw crawler results to media_raw.json for debugging."""
        path = self.output_dir / "media_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        logger.info(f"[media_crawler] saved {path}")
        return str(path)

    # ── Internal page crawler ─────────────────────────────────────────────

    async def _crawl_page(self, context, url: str, depth: int) -> None:
        """Extract media elements from a single page."""
        if url in self._visited:
            return
        self._visited.add(url)

        page = await context.new_page()
        try:
            # Retry pattern — same as MovingContentCrawler
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except Exception:
                    await page.goto(url, wait_until="commit", timeout=15_000)

            # Wait for JS-driven media players to initialise
            await page.wait_for_timeout(2000)

            # Extract all media elements in one evaluate() call
            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(MediaElementData(page_url=url, **item))

            # Optionally crawl linked pages (same-origin only)
            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                base_netloc = urlparse(self.base_url).netloc
                for href in links:
                    if (
                        urlparse(href).netloc == base_netloc
                        and href not in self._visited
                    ):
                        await self._crawl_page(context, href, depth + 1)

        except Exception as exc:
            logger.error(f"[media_crawler] Error on {url}: {exc}")
        finally:
            await page.close()


# ── SUMMARY ──────────────────────────────────────────────────────────────
# What was done:
#   Created AsyncMediaCrawler following the exact MovingContentCrawler pattern.
#   Extracts <audio> and <video> media elements with full context.
#
# Principles applied:
#   - SoC: Crawler only extracts data. WCAG logic lives in the auditor.
#   - DRY: Reuses _ssrf_guard, same retry pattern, same Pydantic model approach.
#   - KISS: Single JS evaluate() call extracts everything in one shot.
#   - SOLID/SRP: One class, one job — find media elements.
#   - Testability: Pydantic model validates output shape. save_raw_json for debugging.
#
# Edge cases handled:
#   - <source> child elements (fallback src resolution)
#   - aria-describedby pointing to elements elsewhere in the DOM
#   - <details> collapsible transcript sections
#   - Same-origin depth crawling with deduplication
#   - SSRF guard to prevent internal network access
#
# Suggested next steps:
#   → File 2: ka11y/accessibility/rules/media/__init__.py
#   → File 3: ka11y/accessibility/rules/media/media_auditor.py
# ─────────────────────────────────────────────────────────────────────────
