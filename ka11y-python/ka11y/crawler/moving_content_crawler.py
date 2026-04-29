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
  • Carousels with autoplay         — Bootstrap, Swiper, Slick, Owl, Glide, Splide, generic
  • <marquee> / <blink>            — deprecated HTML (also caught by axe-core)
"""

import io
import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import httpx
from PIL import Image
from playwright.async_api import async_playwright
from pydantic import BaseModel

from ka11y.crawler.context_factory import new_crawler_context

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="moving_content")


class MovingContentData(BaseModel):
    """Data for one piece of auto-playing / animated content."""

    page_url: str
    element_index: int
    content_type: str  # video_autoplay | animated_gif | css_animation
    # | carousel_autoplay | marquee_element | blink_element
    tag: str
    element_id: Optional[str] = None
    src: Optional[str] = None  # video / img src

    # CSS / WAAPI animation details
    animation_name: Optional[str] = None
    animation_duration_seconds: Optional[float] = None
    animation_iteration_count: Optional[str] = None  # "infinite" or "N"

    # Moving-content properties
    loops: bool = False
    duration_seconds: Optional[float] = None  # -1 means infinite
    duration_known: bool = True
    starts_automatically: bool = True
    applicability_exception: Optional[str] = None

    # Pause / Stop / Hide mechanism
    has_video_controls: bool = False  # <video controls> attribute present
    has_pause_button: bool = False  # nearby button with pause/stop text
    has_mechanism: bool = False  # any mechanism present

    # axe-core would already flag this element
    axe_would_catch: bool = False

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None

    html_snippet: str = ""


async def _is_animated_gif(src: str, client: httpx.AsyncClient) -> bool:
    """Return True only if the GIF at `src` has more than 1 frame (is animated)."""
    try:
        resp = await client.get(src)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        if img.format != "GIF":
            return False
        frame_count = 0
        try:
            while True:
                frame_count += 1
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return frame_count > 1
    except Exception:
        # If we cannot fetch/parse, assume animated to err on the side of caution
        return True


class MovingContentCrawler:
    """
    Launches a headless Chromium browser, waits for JS animations to initialise,
    then extracts all auto-playing / animated elements on the page.
    """

    EXTRACT_JS = r"""() => {
        const results = [];
        const STATUS_ATTR_RE = /(^|[\s:_-])(spinner|loading|loader|progress|busy|skeleton|shimmer|throbber|preload|placeholder|buffer)([\s:_-]|$)/i;
        const STATUS_TEXT_RE = /(loading|please wait|working|processing|buffering|syncing|saving|uploading|読み込み|読み込み中|ロード中|処理中|進行中|お待ちください|同期中|保存中|アップロード中|通信中|送信中)/i;
        const STATUS_ROLE_SET = new Set(['progressbar', 'status']);
        const STATUS_TAG_SET = new Set(['progress', 'sl-spinner', 'sl-progress-ring', 'sl-progress-bar']);

        function textLikeValue(el, includeText = true) {
            if (!el) return '';
            const className = typeof el.className === 'string'
                ? el.className
                : (el.className && typeof el.className.baseVal === 'string' ? el.className.baseVal : '');
            const parts = [
                el.id || '',
                className || '',
                el.getAttribute ? (el.getAttribute('aria-label') || '') : '',
                el.getAttribute ? (el.getAttribute('title') || '') : '',
                el.getAttribute ? (el.getAttribute('data-testid') || '') : '',
                el.getAttribute ? (el.getAttribute('data-state') || '') : '',
                el.getAttribute ? (el.getAttribute('name') || '') : '',
            ];
            if (includeText) {
                parts.push(el.innerText || el.textContent || '');
            }
            return parts.join(' ').replace(/\s+/g, ' ').trim().slice(0, 240);
        }

        function hasLoadingStatusSignal(el, includeText = true) {
            if (!el || !el.tagName) return false;
            const localName = (el.localName || '').toLowerCase();
            const role = ((el.getAttribute && el.getAttribute('role')) || '').toLowerCase();
            const ariaBusy = ((el.getAttribute && el.getAttribute('aria-busy')) || '').toLowerCase();

            if (STATUS_TAG_SET.has(localName)) return true;
            if (STATUS_ROLE_SET.has(role)) return true;
            if (ariaBusy === 'true') return true;

            const signalValue = textLikeValue(el, includeText);
            return STATUS_ATTR_RE.test(signalValue) || STATUS_TEXT_RE.test(signalValue);
        }

        function loadingStatusExceptionFor(el) {
            let current = el;
            let depth = 0;
            while (current && depth < 8) {
                if (hasLoadingStatusSignal(current, depth === 0)) return 'loading_indicator';
                current = current.parentElement;
                depth += 1;
            }
            return null;
        }

        /* ── helper: look for a pause/stop button near an element (2 levels up) ── */
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
                    // Only pause/stop controls (EN/JP) — a plain "play" link is not a pause mechanism
                    if (/(^|\s)(pause|stop)(\s|$)|一時停止|停止|止める/i.test(txt)) return true;
                }
            }
            return false;
        }

        /* ── 1. Videos with autoplay ─────────────────────────────────── */
        document.querySelectorAll('video').forEach(el => {
            if (!el.hasAttribute('autoplay') && !el.hasAttribute('data-autoplay')) return;

            // WCAG 2.2.2 only applies when content lasts > 5 seconds.
            // el.duration is available after metadata loads (autoplay triggers that).
            // If duration is known and short, skip.
            const vidDuration = isFinite(el.duration) ? el.duration : null;
            if (vidDuration !== null && vidDuration <= 5) return;

            const hasControls = el.hasAttribute('controls');
            const hasPauseBtn = nearbyPauseButton(el);
            const loops       = el.hasAttribute('loop');
            const applicabilityException = loadingStatusExceptionFor(el);

            // Resolve src: prefer currentSrc, then src attribute, then first <source> child
            const src = el.currentSrc ||
                        el.getAttribute('src') ||
                        (el.querySelector('source[src]') || {}).src ||
                        null;

            results.push({
                element_index:              results.length,
                content_type:               'video_autoplay',
                tag:                        'VIDEO',
                element_id:                 el.id || null,
                src:                        src,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  loops ? 'infinite' : null,
                loops:                      loops,
                duration_seconds:           loops ? -1 : (vidDuration || null),
                starts_automatically:       true,
                applicability_exception:    applicabilityException,
                has_video_controls:         hasControls,
                has_pause_button:           hasPauseBtn,
                has_mechanism:              hasControls || hasPauseBtn,
                axe_would_catch:            false,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });

        /* ── 2. Animated GIFs ────────────────────────────────────────── */
        document.querySelectorAll('img[src]').forEach(el => {
            const src = (el.getAttribute('src') || '').toLowerCase().split('?')[0];
            if (!src.endsWith('.gif')) return;

            const hasPauseBtn = nearbyPauseButton(el);
            const applicabilityException = loadingStatusExceptionFor(el);
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
                applicability_exception:    applicabilityException,
                has_video_controls:         false,
                has_pause_button:           hasPauseBtn,
                has_mechanism:              hasPauseBtn,
                axe_would_catch:            false,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });

        /* ── 3. CSS / WAAPI animations (> 5 000 ms total, or infinite) ── */
        if (typeof document.getAnimations === 'function') {
            const seen = new WeakMap();
            document.getAnimations().forEach(anim => {
                const effect = anim.effect;
                if (!effect || !effect.target) return;
                const el = effect.target;
                if (!el || !el.tagName) return;

                // Skip visually hidden elements — they cannot distract users
                const cs = window.getComputedStyle(el);
                if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return;

                const timing  = effect.getTiming ? effect.getTiming() : {};
                const durMs   = typeof timing.duration === 'number' ? timing.duration : 0;
                const iters   = timing.iterations;
                const isInfin = iters === Infinity;
                const totalMs = isInfin ? Infinity : durMs * (iters || 1);

                // Skip if total duration is ≤ 5 000 ms (WCAG 2.2.2 threshold) and finite
                if (!isInfin && totalMs <= 5000) return;

                // Deduplicate: one entry per (element, animationName)
                const animName = anim.animationName || anim.id || 'unknown';
                if (!seen.has(el)) seen.set(el, new Set());
                if (seen.get(el).has(animName)) return;
                seen.get(el).add(animName);

                // All CSS animations in getAnimations() started via CSS/JS automatically.
                // If the animation is currently paused, something must have paused it,
                // which itself counts as a mechanism (JS-controlled pause state).
                const isPaused    = anim.playState === 'paused';
                const hasPauseBtn = nearbyPauseButton(el);
                const hasMechanism = hasPauseBtn || isPaused;
                const applicabilityException = loadingStatusExceptionFor(el);

                // Check if page honours prefers-reduced-motion for this element;
                // if so, the page provides a system-level mechanism.
                const style = window.getComputedStyle(el);
                const animPlayState = style && style.animationPlayState;
                // If reduced-motion media query would pause this, the page respects it
                // (we cannot directly query this from JS, so rely on paused state check above)

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
                    starts_automatically:       true,
                    applicability_exception:    applicabilityException,
                    has_video_controls:         false,
                    has_pause_button:           hasPauseBtn,
                    has_mechanism:              hasMechanism,
                    axe_would_catch:            false,
                    html_snippet:               (el.outerHTML || '').slice(0, 300),
                });
            });
        }

        /* ── helper: check if a carousel element has autoplay enabled ── */
        function carouselIsAutoplay(el) {
            // Explicit data-autoplay / data-auto-advance (any truthy value except false/0)
            const ap = el.getAttribute('data-autoplay');
            if (ap !== null && ap !== 'false' && ap !== '0' && ap !== '') return true;
            const aa = el.getAttribute('data-auto-advance');
            if (aa !== null && aa !== 'false' && aa !== '0' && aa !== '') return true;

            // Bootstrap: data-ride="carousel" enables autoplay by default
            if (el.getAttribute('data-ride') === 'carousel') return true;
            if (el.getAttribute('data-bs-ride') === 'carousel') return true;

            // Slick: check data-slick JSON or DOM-attached instance (set by Slick on element)
            if (el.classList.contains('slick-initialized')) {
                try {
                    const cfg = JSON.parse(el.getAttribute('data-slick') || '{}');
                    if (cfg.autoplay === true) return true;
                } catch(e) {}
                // Slick attaches options directly on the element's slickOptions property
                if (el.slickOptions && el.slickOptions.autoplay) return true;
            }

            // Swiper: check runtime instance (Swiper v6+ attaches to el.swiper)
            if (el.classList.contains('swiper-initialized') ||
                el.classList.contains('swiper-container') ||
                el.classList.contains('swiper')) {
                if (el.swiper && el.swiper.autoplay && el.swiper.autoplay.running) return true;
                // Fallback: check data-swiper JSON configuration
                try {
                    const raw = el.getAttribute('data-swiper') || el.getAttribute('data-options') || '{}';
                    const cfg = JSON.parse(raw);
                    if (cfg.autoplay) return true;
                } catch(e) {}
            }

            // Owl Carousel: check data-owlcarousel JSON (jQuery .data() is unavailable here)
            if (el.classList.contains('owl-carousel')) {
                try {
                    const cfg = JSON.parse(el.getAttribute('data-owlcarousel') || '{}');
                    if (cfg.autoPlay || cfg.autoplay) return true;
                } catch(e) {}
                // Some Owl implementations use data-auto-play or data-autoplay (checked above)
                if (el.hasAttribute('data-auto-play')) return true;
            }

            // Flickity: check data-flickity JSON or runtime instance
            if (el.classList.contains('flickity-enabled')) {
                try {
                    const cfg = JSON.parse(el.getAttribute('data-flickity') || '{}');
                    if (cfg.autoPlay) return true;
                } catch(e) {}
                // Flickity attaches instance to element via el.flickity
                if (el.flickity && el.flickity.options && el.flickity.options.autoPlay) return true;
            }

            // Glide.js: check data-glide JSON or the autoplay data attribute
            if (el.classList.contains('glide--carousel') || el.classList.contains('glide')) {
                try {
                    const cfg = JSON.parse(el.getAttribute('data-glide') || '{}');
                    if (cfg.autoplay) return true;
                } catch(e) {}
                // Some setups pass autoplay directly as an attribute
                if (el.hasAttribute('data-glide-autoplay')) return true;
            }

            // Splide.js: check data-splide JSON or runtime instance
            if (el.classList.contains('splide')) {
                try {
                    const cfg = JSON.parse(el.getAttribute('data-splide') || '{}');
                    if (cfg.autoplay || cfg.autoPlay) return true;
                } catch(e) {}
                if (el.splide && el.splide.options && el.splide.options.autoplay) return true;
            }

            // Generic data-carousel: treat as autoplay only if it also has data-autoplay
            // (already checked above); a bare data-carousel is just a marker, not autoplay
            return false;
        }

        /* ── helper: pause button search both inside carousel and 2 levels up ── */
        function carouselHasPauseButton(el) {
            if (nearbyPauseButton(el)) return true;
            // Search inside the carousel root for a pause/stop control
            const inner = el.querySelectorAll
                ? el.querySelectorAll('button,[role="button"],[role="switch"],a')
                : [];
            for (const btn of inner) {
                const txt = (
                    btn.innerText ||
                    btn.getAttribute('aria-label') ||
                    btn.getAttribute('title') || ''
                ).toLowerCase();
                if (/(^|\s)(pause|stop)(\s|$)|一時停止|停止|止める/i.test(txt)) return true;
            }
            // Also check aria-label on any child element
            if (el.querySelector) {
                if (el.querySelector('[aria-label~="pause" i],[aria-label~="stop" i],[aria-label*="一時停止" i],[aria-label*="停止" i]')) return true;
            }
            return false;
        }

        /* ── 4. Carousel / slider auto-play patterns ─────────────────── */
        const carouselSelectors = [
            '[data-ride="carousel"]',          // Bootstrap 4
            '[data-bs-ride="carousel"]',       // Bootstrap 5
            '.slick-initialized',              // Slick
            '.swiper-initialized',             // Swiper v8+ (after init)
            '.swiper-container',               // Swiper legacy (v6/v7)
            '.swiper',                         // Swiper v8+ root class
            '.owl-carousel',                   // Owl Carousel
            '.flickity-enabled',               // Flickity
            '.glide--carousel',                // Glide.js carousel mode
            '.splide',                         // Splide.js
            '[data-autoplay]',                 // Generic autoplay attribute (any value)
            '[data-auto-advance]',             // Generic auto-advance attribute
        ];

        const seenCarousel = new WeakSet();
        for (const sel of carouselSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (seenCarousel.has(el)) return;
                seenCarousel.add(el);

                if (!carouselIsAutoplay(el)) return;

                const hasPauseBtn = carouselHasPauseButton(el);
                const applicabilityException = loadingStatusExceptionFor(el);

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
                    applicability_exception:    applicabilityException,
                    has_video_controls:         false,
                    has_pause_button:           hasPauseBtn,
                    has_mechanism:              hasPauseBtn,
                    axe_would_catch:            false,
                    html_snippet:               (el.outerHTML || '').slice(0, 400),
                });
            });
        }

        /* ── 5. Embedded iframe videos (YouTube, Vimeo, Dailymotion, etc.) ── */
        // These never appear as <video> elements, so the section above misses them.
        // We detect known video embed hosts and report them as auto-playing unless
        // the URL contains explicit autoplay=0 / mute=false (conservative approach).
        const VIDEO_HOSTS = [
            'youtube.com/embed', 'youtu.be/', 'youtube-nocookie.com/embed',
            'player.vimeo.com', 'vimeo.com/video',
            'dailymotion.com/embed', 'dai.ly/',
            'fast.wistia.net', 'wistia.com/medias',
            'player.twitch.tv',
            'facebook.com/plugins/video',
            'embed.ted.com',
        ];
        const seenIframe = new WeakSet();
        document.querySelectorAll('iframe[src]').forEach(el => {
            if (seenIframe.has(el)) return;
            const src = (el.getAttribute('src') || '').toLowerCase();
            const isVideoHost = VIDEO_HOSTS.some(h => src.includes(h));
            if (!isVideoHost) return;
            seenIframe.add(el);

            // Check if autoplay is explicitly disabled in the URL
            const url = new URL(el.getAttribute('src'), location.href);
            const autoplayParam = url.searchParams.get('autoplay');
            const isAutoplay = autoplayParam === null || autoplayParam === '1' || autoplayParam === 'true';
            if (!isAutoplay) return;

            const hasPauseBtn = nearbyPauseButton(el);
            const applicabilityException = loadingStatusExceptionFor(el);
            results.push({
                element_index:              results.length,
                content_type:              'video_autoplay',
                tag:                       'IFRAME',
                element_id:                el.id || null,
                src:                       el.getAttribute('src') || null,
                animation_name:            null,
                animation_duration_seconds: null,
                animation_iteration_count: null,
                loops:                     false,
                duration_seconds:          null,
                starts_automatically:      true,
                applicability_exception:   applicabilityException,
                has_video_controls:        false,
                has_pause_button:          hasPauseBtn,
                has_mechanism:             hasPauseBtn,
                axe_would_catch:           false,
                html_snippet:              (el.outerHTML || '').slice(0, 400),
            });
        });

        /* ── 6. Generic custom sliders/carousels (CSS transform cycling) ── */
        // Detect containers where child elements cycle position or visibility
        // automatically — pattern used by many hand-rolled carousels.
        (function() {
            const genericCarouselSelectors = [
                '[class*="slider" i]',
                '[class*="carousel" i]',
                '[class*="slideshow" i]',
                '[class*="rotator" i]',
            ];
            const alreadySeen = new WeakSet();
            for (const sel of genericCarouselSelectors) {
                document.querySelectorAll(sel).forEach(el => {
                    if (alreadySeen.has(el) || seenCarousel.has(el)) return;
                    alreadySeen.add(el);

                    // Must not already be captured by a known library selector
                    if (
                        el.classList.contains('slick-initialized') ||
                        el.classList.contains('swiper-initialized') ||
                        el.classList.contains('swiper-container') ||
                        el.classList.contains('swiper') ||
                        el.classList.contains('owl-carousel') ||
                        el.classList.contains('flickity-enabled') ||
                        el.classList.contains('splide') ||
                        el.classList.contains('glide--carousel')
                    ) return;

                    // Require evidence of autoplay:
                    // data-autoplay / data-auto-advance / data-interval attributes
                    const hasAutoplayAttr = (
                        el.hasAttribute('data-autoplay') ||
                        el.hasAttribute('data-auto-advance') ||
                        el.hasAttribute('data-interval') ||
                        el.hasAttribute('data-speed')
                    );
                    if (!hasAutoplayAttr) return;

                    const hasPauseBtn = carouselHasPauseButton(el);
                    const applicabilityException = loadingStatusExceptionFor(el);
                    results.push({
                        element_index:              results.length,
                        content_type:              'carousel_autoplay',
                        tag:                       el.tagName.toUpperCase(),
                        element_id:                el.id || null,
                        src:                       null,
                        animation_name:            null,
                        animation_duration_seconds: null,
                        animation_iteration_count: 'infinite',
                        loops:                     true,
                        duration_seconds:          -1,
                        starts_automatically:      true,
                        applicability_exception:   applicabilityException,
                        has_video_controls:        false,
                        has_pause_button:          hasPauseBtn,
                        has_mechanism:             hasPauseBtn,
                        axe_would_catch:           false,
                        html_snippet:              (el.outerHTML || '').slice(0, 400),
                    });
                });
            }
        })();

        /* ── 7. <marquee> and <blink> (deprecated; axe-core also flags) ── */
        document.querySelectorAll('marquee').forEach(el => {
            const applicabilityException = loadingStatusExceptionFor(el);
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
                applicability_exception:    applicabilityException,
                has_video_controls:         false,
                has_pause_button:           false,
                has_mechanism:              false,
                axe_would_catch:            true,
                html_snippet:               (el.outerHTML || '').slice(0, 400),
            });
        });
        document.querySelectorAll('blink').forEach(el => {
            const applicabilityException = loadingStatusExceptionFor(el);
            results.push({
                element_index:             results.length,
                content_type:              'blink_element',
                tag:                       'BLINK',
                element_id:                 el.id || null,
                src:                        null,
                animation_name:             null,
                animation_duration_seconds: null,
                animation_iteration_count:  'infinite',
                loops:                      true,
                duration_seconds:           -1,
                starts_automatically:       true,
                applicability_exception:    applicabilityException,
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
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[MovingContentData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[MovingContentData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await new_crawler_context(
                browser,
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

        # Verify animated GIFs — filter out static GIFs to avoid false positives
        # One shared client for all GIF checks (3 s timeout; 50 GIFs ≠ 50 handshakes)
        verified: List[MovingContentData] = []
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as gif_client:
            for item in self.results:
                if item.content_type == "animated_gif" and item.src:
                    if not await _is_animated_gif(item.src, gif_client):
                        continue
                verified.append(item)
        self.results = verified

        return self.results

    async def _crawl_page(self, context, url: str, depth: int):
        if url in self.visited:
            return
        self.visited.add(url)

        page = await context.new_page()
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                except Exception:
                    await page.goto(url, wait_until="commit", timeout=15_000)
            # Wait for JS carousel libraries and animations to fully initialise
            await page.wait_for_timeout(2000)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(MovingContentData(page_url=url, **item))

            if depth < self.max_depth:
                links = await page.eval_on_selector_all(
                    "a[href]", "els => els.map(e => e.href)"
                )
                base_netloc = urlparse(self.base_url).netloc
                for href in links:
                    if (
                        urlparse(href).netloc == base_netloc
                        and href not in self.visited
                    ):
                        await self._crawl_page(context, href, depth + 1)
        except Exception as exc:
            logger.error(f"[MovingContentCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "moving_content_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
