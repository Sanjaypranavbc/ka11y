"""
ka11y/crawler/moving_content_crawler.py
=========================================
Playwright-based crawler for moving / blinking / auto-updating content.
Detects what axe-core misses for WCAG 2.2.2 (Pause, Stop, Hide).

What is detected
────────────────
  • <video autoplay>               — starts automatically, no controls
  • <img src="*.gif">              — animated GIFs (assumed looping indefinitely)
  • CSS / WAAPI animations > 5 s   — long-running keyframe animations
  • Carousels with autoplay         — Bootstrap, Swiper, Slick, Owl, Glide, generic
  • <marquee> / <blink>            — deprecated HTML (also caught by axe-core)
"""

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel


class MovingContentData(BaseModel):
    """Data for one piece of auto-playing / animated content."""
    page_url: str
    element_index: int
    content_type: str       # video_autoplay | animated_gif | css_animation
                            # | carousel_autoplay | marquee_element | blink_element
    tag: str
    element_id: Optional[str] = None
    src: Optional[str] = None           # video / img src

    # CSS / WAAPI animation details
    animation_name: Optional[str] = None
    animation_duration_seconds: Optional[float] = None
    animation_iteration_count: Optional[str] = None   # "infinite" or "N"

    # Moving-content properties
    loops: bool = False
    duration_seconds: Optional[float] = None    # -1 means infinite
    starts_automatically: bool = True

    # Pause / Stop / Hide mechanism
    has_video_controls: bool = False    # <video controls> attribute present
    has_pause_button: bool = False      # nearby button with pause/stop/play text
    has_mechanism: bool = False         # any mechanism present

    # axe-core would already flag this element
    axe_would_catch: bool = False

    html_snippet: str = ""


class MovingContentCrawler:
    """
    Launches a headless Chromium browser, waits for JS animations to initialise,
    then extracts all auto-playing / animated elements on the page.
    """

    EXTRACT_JS = r"""() => {
        const results = [];

        /* ── helper: look for a pause/stop/play button near an element ── */
        function nearbyPauseButton(el) {
            const containers = [
                el.parentElement,
                el.parentElement && el.parentElement.parentElement,
            ].filter(Boolean);
            for (const c of containers) {
                const btns = c.querySelectorAll('button,[role="button"],a');
                for (const btn of btns) {
                    const txt = (
                        btn.innerText ||
                        btn.getAttribute('aria-label') ||
                        btn.getAttribute('title') || ''
                    ).toLowerCase();
                    if (/pause|stop|play/.test(txt)) return true;
                }
            }
            return false;
        }

        /* ── 1. Videos with autoplay ─────────────────────────────────── */
        document.querySelectorAll('video').forEach(el => {
            if (!el.hasAttribute('autoplay') && !el.hasAttribute('data-autoplay')) return;
            const hasControls = el.hasAttribute('controls');
            const hasPauseBtn = nearbyPauseButton(el);
            results.push({
                element_index:              results.length,
                content_type:               'video_autoplay',
                tag:                        'VIDEO',
                element_id:                 el.id || null,
                src:                        el.currentSrc || el.src || null,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  null,
                loops:                      true,
                duration_seconds:           -1,
                starts_automatically:       true,
                has_video_controls:         hasControls,
                has_pause_button:           hasPauseBtn,
                has_mechanism:              hasControls || hasPauseBtn,
                axe_would_catch:            false,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });

        /* ── 2. Animated GIFs ────────────────────────────────────────── */
        document.querySelectorAll('img[src]').forEach(el => {
            const src = (el.src || el.getAttribute('src') || '').toLowerCase();
            if (!src.includes('.gif')) return;
            results.push({
                element_index:              results.length,
                content_type:               'animated_gif',
                tag:                        'IMG',
                element_id:                 el.id || null,
                src:                        el.src || null,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  'infinite',
                loops:                      true,
                duration_seconds:           -1,
                starts_automatically:       true,
                has_video_controls:         false,
                has_pause_button:           false,
                has_mechanism:              false,
                axe_would_catch:            false,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });

        /* ── 3. CSS / WAAPI animations (> 5 000 ms or infinite) ──────── */
        if (typeof document.getAnimations === 'function') {
            const seen = new WeakMap();
            document.getAnimations().forEach(anim => {
                const effect = anim.effect;
                if (!effect || !effect.target) return;
                const el = effect.target;
                if (!el || !el.tagName) return;

                const timing  = effect.getTiming ? effect.getTiming() : {};
                const durMs   = typeof timing.duration === 'number' ? timing.duration : 0;
                const iters   = timing.iterations;
                const isInfin = iters === Infinity;
                const totalMs = isInfin ? Infinity : durMs * (iters || 1);

                // Only flag if > 5 000 ms total or infinite, and not a micro-animation
                if (durMs < 500) return;
                if (!isInfin && totalMs <= 5000) return;

                // Deduplicate: one entry per (element, animationName)
                const animName = anim.animationName || anim.id || 'unknown';
                if (!seen.has(el)) seen.set(el, new Set());
                if (seen.get(el).has(animName)) return;
                seen.get(el).add(animName);

                const hasPauseBtn = nearbyPauseButton(el);
                results.push({
                    element_index:              results.length,
                    content_type:               'css_animation',
                    tag:                        el.tagName.toUpperCase(),
                    element_id:                 el.id || null,
                    src:                        null,
                    animation_name:             animName,
                    animation_duration_seconds: durMs / 1000,
                    animation_iteration_count:  isInfin ? 'infinite' : String(iters || 1),
                    loops:                      isInfin,
                    duration_seconds:           isInfin ? -1 : totalMs / 1000,
                    starts_automatically:       anim.playState === 'running',
                    has_video_controls:         false,
                    has_pause_button:           hasPauseBtn,
                    has_mechanism:              hasPauseBtn,
                    axe_would_catch:            false,
                    html_snippet:               (el.outerHTML || '').slice(0, 300),
                });
            });
        }

        /* ── 4. Carousel / slider auto-play patterns ─────────────────── */
        const carouselSelectors = [
            '[data-ride="carousel"]',          // Bootstrap 4
            '[data-bs-ride="carousel"]',       // Bootstrap 5
            '.slick-initialized',              // Slick
            '.swiper-initialized',             // Swiper v8+
            '.swiper-container',               // Swiper legacy
            '.owl-carousel',                   // Owl Carousel
            '.flickity-enabled',               // Flickity
            '.glide--carousel',                // Glide.js
            '[data-autoplay="true"]',
            '[data-auto-advance="true"]',
        ];

        const seenCarousel = new WeakSet();
        for (const sel of carouselSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (seenCarousel.has(el)) return;
                seenCarousel.add(el);

                const isAutoplay =
                    el.hasAttribute('data-autoplay')    ||
                    el.hasAttribute('data-auto-advance')||
                    el.getAttribute('data-ride')    === 'carousel' ||
                    el.getAttribute('data-bs-ride') === 'carousel' ||
                    el.classList.contains('slick-initialized')   ||
                    el.classList.contains('swiper-initialized')  ||
                    el.classList.contains('swiper-container')    ||
                    el.classList.contains('owl-carousel')        ||
                    el.classList.contains('flickity-enabled')    ||
                    el.classList.contains('glide--carousel');

                if (!isAutoplay) return;

                const hasPauseBtn = nearbyPauseButton(el) ||
                    !!el.querySelector('[aria-label*="pause" i],[aria-label*="stop" i]');

                results.push({
                    element_index:              results.length,
                    content_type:               'carousel_autoplay',
                    tag:                        el.tagName.toUpperCase(),
                    element_id:                 el.id || null,
                    src:                        null,
                    animation_name:             null,
                    animation_duration_seconds: null,
                    animation_iteration_count:  'infinite',
                    loops:                      true,
                    duration_seconds:           -1,
                    starts_automatically:       true,
                    has_video_controls:         false,
                    has_pause_button:           hasPauseBtn,
                    has_mechanism:              hasPauseBtn,
                    axe_would_catch:            false,
                    html_snippet:               (el.outerHTML || '').slice(0, 400),
                });
            });
        }

        /* ── 5. <marquee> and <blink> (deprecated; axe-core also flags) */
        document.querySelectorAll('marquee').forEach(el => {
            results.push({
                element_index:              results.length,
                content_type:               'marquee_element',
                tag:                        'MARQUEE',
                element_id:                 el.id || null,
                src:                        null,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  'infinite',
                loops:                      true,
                duration_seconds:           -1,
                starts_automatically:       true,
                has_video_controls:         false,
                has_pause_button:           false,
                has_mechanism:              false,
                axe_would_catch:            true,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });
        document.querySelectorAll('blink').forEach(el => {
            results.push({
                element_index:              results.length,
                content_type:               'blink_element',
                tag:                        'BLINK',
                element_id:                 el.id || null,
                src:                        null,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  'infinite',
                loops:                      true,
                duration_seconds:           -1,
                starts_automatically:       true,
                has_video_controls:         false,
                has_pause_button:           false,
                has_mechanism:              false,
                axe_would_catch:            true,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url   = base_url
        self.output_dir = Path(output_dir)
        self.max_depth  = max_depth
        self.results: List[MovingContentData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[MovingContentData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            try:
                await self._crawl_page(context, self.base_url, depth=0)
            finally:
                await context.close()
                await browser.close()
        return self.results

    async def _crawl_page(self, context, url: str, depth: int):
        if url in self.visited:
            return
        self.visited.add(url)

        page = await context.new_page()
        try:
            try:
                await page.goto(url, wait_until="networkidle", timeout=30_000)
            except Exception:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except Exception:
                    await page.goto(url, wait_until="commit", timeout=15_000)
            # Wait longer so JS animations and carousel libraries can initialise
            await page.wait_for_timeout(3000)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(MovingContentData(page_url=url, **item))

            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                base_netloc = urlparse(self.base_url).netloc
                for href in links:
                    if urlparse(href).netloc == base_netloc and href not in self.visited:
                        await self._crawl_page(context, href, depth + 1)
        except Exception as exc:
            print(f"[MovingContentCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "moving_content_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
