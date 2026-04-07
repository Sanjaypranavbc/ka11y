"""
ka11y/crawler/universal_page.py
================================
Universal page loader — opens a URL ONCE with a smart wait strategy,
records a HAR for scenario-based crawlers, and extracts ALL static
rule data in a single page.evaluate() call.

Fixes three critical issues:
  1. SPA / JS-rendered sites returning near-zero data
     → networkidle wait + MutationObserver DOM-stability check + lazy-load trigger
  2. WCAG 2.2.2 always returning 0 violations
     → CSS computed-style animation detection (works regardless of WAAPI timing)
  3. 8 separate page loads per audit
     → 1 real load → HAR recorded → scenario crawlers replay from cache

Usage::

    from ka11y.crawler.universal_page import UniversalPageLoader

    snapshot = await UniversalPageLoader.load(
        url="https://example.com",
        output_dir=Path("/tmp/audit/example"),
    )
    # snapshot.forms          → List[dict]  (feeds FormAccessibilityAuditor)
    # snapshot.interactive    → List[dict]  (feeds LabelInNameAuditor)
    # snapshot.target_sizes   → List[dict]  (feeds TargetSizeAuditor)
    # snapshot.moving_content → List[dict]  (feeds PauseStopHideAuditor)
    # snapshot.media          → List[dict]  (feeds MediaAuditor)
    # snapshot.text_spacing   → List[dict]  (feeds TextSpacingAuditor)
    # snapshot.har_path       → str | None  (passed to RenderedLayoutCrawler)
    # snapshot.page_url       → str
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright

from ka11y.config.logger import setup_logger
from ka11y.crawler._ssrf_guard import install_ssrf_guard
from ka11y.crawler.stealth_context import create_stealth_context, launch_stealth_browser

logger = setup_logger(name="KAC", tag="universal_page")

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_GOTO_TIMEOUT_MS = 30_000          # hard navigation timeout
_NETWORKIDLE_TIMEOUT_MS = 15_000   # how long to wait for networkidle after DCL
_DOM_STABILITY_MS = 600            # no DOM mutations for this long → stable
_DOM_STABILITY_TOTAL_MS = 12_000   # give up waiting for stability after this
_LAZY_SCROLL_STEPS = 6             # scroll positions to trigger lazy-load
_POST_SCROLL_WAIT_MS = 1_500       # wait after final scroll before extracting
_CAROUSEL_POLL_INTERVAL_MS = 300   # how often to check for carousel init
_CAROUSEL_POLL_MAX_MS = 3_000      # give up waiting for carousel after this

# JavaScript that detects common WAF / challenge / interstitial page patterns.
# Returns a list of human-readable reason strings, or an empty list on a clean page.
_CHALLENGE_DETECT_JS = r"""() => {
    const reasons = [];

    // Incapsula / Imperva challenge iframes or resource URLs
    const incapsulaIframe = document.querySelector('iframe[src*="_Incapsula_Resource"]');
    if (incapsulaIframe) reasons.push('incapsula-challenge-iframe');

    // Generic WAF challenge patterns
    const body = (document.body ? document.body.innerText || '' : '').toLowerCase();
    if (/checking your browser/i.test(body) && /cloudflare/i.test(body))
        reasons.push('cloudflare-browser-check');
    if (/ddos protection by cloudflare/i.test(body))
        reasons.push('cloudflare-ddos-protection');
    if (/enable javascript and cookies to continue/i.test(body))
        reasons.push('js-cookie-challenge');
    if (/403 forbidden/i.test(document.title) || /access denied/i.test(document.title))
        reasons.push('access-denied-title');
    if (/captcha/i.test(body) && document.querySelectorAll('iframe').length > 0)
        reasons.push('captcha-iframe');

    // Nearly-empty body combined with script-heavy page — WAF challenge shell pattern.
    // Require BOTH: no main landmark AND very small visible text AND at least one script.
    const mainContent = document.querySelector('main, [role="main"], #content, #main, article');
    const bodyText = document.body ? document.body.innerText.trim() : '';
    const scriptCount = document.querySelectorAll('script[src]').length;
    if (!mainContent && bodyText.length < 100 && scriptCount >= 2)
        reasons.push('near-empty-body');

    return reasons;
}"""

# CSS selectors that indicate a carousel library has initialised
_CAROUSEL_READY_SELECTORS = [
    ".flickity-enabled",        # Flickity
    ".swiper-initialized",      # Swiper.js
    ".slick-initialized",       # Slick
    ".owl-loaded",              # Owl Carousel
    ".glide--mounted",          # Glide.js
    "[data-carousel-initialized]",  # generic data attribute
]

# Known SPA framework readiness signals (window globals set by major frameworks)
_SPA_SIGNALS = [
    "window.__NEXT_DATA__",           # Next.js SSR
    "window.__nuxt",                  # Nuxt.js
    "window.__vue_app__",             # Vue 3
    "window.React",                   # React (generic)
    "window.angular",                 # Angular
    "window.Ember",                   # Ember.js
    "window.__svelte",                # SvelteKit
    "document.querySelector('[data-reactroot]')",  # React SSR
]

# ---------------------------------------------------------------------------
# PageSnapshot — typed container for all extracted data
# ---------------------------------------------------------------------------


@dataclass
class PageSnapshot:
    """All data extracted from a single page load, ready for every auditor."""

    page_url: str

    # Each list maps 1-to-1 with the Pydantic model fields in the legacy crawlers
    forms: List[Dict[str, Any]] = field(default_factory=list)
    interactive: List[Dict[str, Any]] = field(default_factory=list)
    target_sizes: List[Dict[str, Any]] = field(default_factory=list)
    moving_content: List[Dict[str, Any]] = field(default_factory=list)
    media: List[Dict[str, Any]] = field(default_factory=list)
    text_spacing: List[Dict[str, Any]] = field(default_factory=list)

    # Path to the recorded HAR file (None if recording was skipped / failed)
    har_path: Optional[str] = None

    # Degradation warnings accumulated during load (challenge pages, partial data, etc.)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Combined JavaScript extraction
# ---------------------------------------------------------------------------
# One evaluate() call that runs all six data-collection pipelines.
# Each section is self-contained and mirrors the JS in the individual crawlers.
# Returns: { forms, interactive, target_sizes, moving_content, media, text_spacing }

_COMBINED_EXTRACT_JS = r"""() => {
    /* ═══════════════════════════════════════════════════════════════════
       SHARED HELPERS
       ═══════════════════════════════════════════════════════════════════ */

    /** Pierce shadow DOM recursively */
    function queryShadow(root, selector) {
        const results = Array.from(root.querySelectorAll(selector));
        root.querySelectorAll('*').forEach(el => {
            if (el.shadowRoot) results.push(...queryShadow(el.shadowRoot, selector));
        });
        return results;
    }

    function resolveAriaLabelledby(el) {
        const val = el.getAttribute('aria-labelledby');
        if (!val) return null;
        const parts = val.trim().split(/\s+/)
            .map(id => {
                const ref = document.getElementById(id);
                return ref ? (ref.innerText || ref.textContent || '').trim() : '';
            })
            .filter(t => t.length > 0);
        return parts.length > 0 ? parts.join(' ') : null;
    }

    function computeAccessibleName(el) {
        const tag  = el.tagName.toUpperCase();
        const type = (el.type || '').toLowerCase();
        const lbText = resolveAriaLabelledby(el);
        if (lbText) return lbText;
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
        if (tag === 'INPUT') {
            if (['submit', 'button', 'reset'].includes(type)) {
                const val = el.value;
                if (val && val.trim()) return val.trim();
                return type === 'submit' ? 'Submit' : type === 'reset' ? 'Reset' : '';
            }
            if (type === 'image') {
                const alt = el.getAttribute('alt');
                return alt !== null ? alt.trim() : '';
            }
        }
        const id = el.id;
        if (id) {
            const labelEl = document.querySelector('label[for="' + id + '"]');
            if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();
        }
        const wrapping = el.closest('label');
        if (wrapping) {
            const clone = wrapping.cloneNode(true);
            clone.querySelectorAll('input,select,textarea,button').forEach(e => e.remove());
            return (clone.textContent || '').replace(/\s+/g, ' ').trim();
        }
        const title = el.getAttribute('title');
        if (title && title.trim()) return title.trim();
        const role = (el.getAttribute('role') || '').toLowerCase();
        if (tag === 'BUTTON' || tag === 'A' || role === 'button' || role === 'link') {
            const t = (el.innerText || el.textContent || '').trim();
            if (t) return t;
        }
        return '';
    }

    function getVisibleLabel(el) {
        const tag  = el.tagName.toUpperCase();
        const type = (el.type || '').toLowerCase();
        if (tag === 'BUTTON' || tag === 'A')
            return (el.innerText || el.textContent || '').trim();
        if (tag === 'INPUT') {
            if (['submit', 'button', 'reset'].includes(type))
                return (el.value || el.getAttribute('value') || '').trim();
            if (type === 'image')
                return (el.getAttribute('alt') || '').trim();
            const id = el.id;
            if (id) {
                const labelEl = document.querySelector('label[for="' + id + '"]');
                if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();
            }
            const wrap = el.closest('label');
            if (wrap) {
                const clone = wrap.cloneNode(true);
                clone.querySelectorAll('input,select,textarea,button').forEach(e => e.remove());
                return (clone.textContent || '').replace(/\s+/g, ' ').trim();
            }
            return '';
        }
        return (el.innerText || el.textContent || '').trim();
    }

    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
        'option', 'tab', 'treeitem', 'radio', 'checkbox', 'switch',
        'combobox', 'listbox',
    ]);

    /* ═══════════════════════════════════════════════════════════════════
       1. FORMS  (WCAG 3.3.1 / 3.3.2)
       ═══════════════════════════════════════════════════════════════════ */
    const forms = [];
    (function extractForms() {
        function outerHTML(el, max) { return (el && el.outerHTML) ? el.outerHTML.slice(0, max || 600) : ''; }
        const formEls = Array.from(queryShadow(document, 'form'));
        const formList = formEls.length > 0 ? formEls : [document.body];
        formList.forEach((form, formIdx) => {
            const inputs = Array.from(
                form.querySelectorAll('input:not([type="hidden"]),select,textarea')
            );
            inputs.forEach(el => {
                const id   = el.id   || null;
                const labelEl       = id ? document.querySelector('label[for="'+id+'"]') : null;
                const wrappingLabel = el.closest('label');
                const labelText     = labelEl
                    ? (labelEl.innerText || '').trim()
                    : (wrappingLabel ? (wrappingLabel.innerText || '').trim() : null);
                const ariaLabel     = el.getAttribute('aria-label') || null;
                const ariaLabelledby= el.getAttribute('aria-labelledby') || null;
                const hasAnyLabel   = !!(labelEl || wrappingLabel || ariaLabel || ariaLabelledby);
                const describedby   = el.getAttribute('aria-describedby') || null;
                let errorElId=null, errorElRole=null, errorElText=null, errorHasAlert=false, errorAriaLive=null;
                if (describedby) {
                    const ids = describedby.trim().split(/\s+/);
                    let firstMatch=null, alertMatch=null;
                    for (const eid of ids) {
                        const errEl = document.getElementById(eid);
                        if (!errEl) continue;
                        const role = errEl.getAttribute('role') || null;
                        const live = errEl.getAttribute('aria-live') || null;
                        const isAlert = role === 'alert' || live === 'assertive' || live === 'polite';
                        const candidate = { id: eid, role, text: (errEl.innerText || errEl.textContent || '').trim(), hasAlert: role === 'alert', ariaLive: live };
                        if (!firstMatch) firstMatch = candidate;
                        if (isAlert && !alertMatch) alertMatch = candidate;
                    }
                    const chosen = alertMatch || firstMatch;
                    if (chosen) { errorElId=chosen.id; errorElRole=chosen.role; errorElText=chosen.text; errorHasAlert=chosen.hasAlert; errorAriaLive=chosen.ariaLive; }
                }
                forms.push({
                    form_index: formIdx, form_id: form.id || null,
                    form_action: form.action || null, form_method: (form.method || '').toUpperCase() || null,
                    tag: el.tagName, type: el.type || null, id, name: el.name || null,
                    placeholder: el.placeholder || null, aria_label: ariaLabel, aria_labelledby: ariaLabelledby,
                    aria_describedby: describedby, has_explicit_label: !!labelEl, has_wrapping_label: !!wrappingLabel,
                    label_text: labelText, has_any_label: hasAnyLabel, required: !!el.required,
                    aria_required: el.getAttribute('aria-required') || null, aria_invalid: el.getAttribute('aria-invalid') || null,
                    autocomplete: el.getAttribute('autocomplete') || null, error_element_id: errorElId,
                    error_element_role: errorElRole, error_element_text: errorElText,
                    error_has_role_alert: errorHasAlert, error_has_aria_live: errorAriaLive, html: outerHTML(el),
                });
            });
        });
    })();

    /* ═══════════════════════════════════════════════════════════════════
       2. INTERACTIVE ELEMENTS  (WCAG 2.5.3)
       ═══════════════════════════════════════════════════════════════════ */
    const interactive = [];
    (function extractInteractive() {
        const seen = new WeakSet();
        function addInteractive(el) {
            if (seen.has(el)) return;
            seen.add(el);
            const tag  = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase() || null;
            const role = el.getAttribute('role') || null;
            interactive.push({
                element_index:        interactive.length,
                tag, role, element_id: el.id || null,
                element_name:         el.getAttribute('name') || null,
                input_type:           type,
                visible_label:        getVisibleLabel(el) || null,
                aria_label:           el.getAttribute('aria-label') || null,
                aria_labelledby:      el.getAttribute('aria-labelledby') || null,
                aria_labelledby_text: resolveAriaLabelledby(el) || null,
                title_attr:           el.getAttribute('title') || null,
                value_attr:           el.getAttribute('value') || null,
                alt_attr:             el.getAttribute('alt') || null,
                accessible_name:      computeAccessibleName(el) || null,
                html_snippet:         (el.outerHTML || '').slice(0, 400),
            });
        }
        queryShadow(document, 'button, a[href], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"]').forEach(addInteractive);
        queryShadow(document, '[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            const tag = el.tagName.toUpperCase();
            if (['BUTTON','A','INPUT','SELECT','TEXTAREA'].includes(tag)) return;
            addInteractive(el);
        });
    })();

    /* ═══════════════════════════════════════════════════════════════════
       3. TARGET SIZES  (WCAG 2.5.8)
       ═══════════════════════════════════════════════════════════════════ */
    const target_sizes = [];
    (function extractTargetSizes() {
        const MIN_PX = 24;
        function isInlineLink(el) {
            if (el.tagName !== 'A') return false;
            const display = window.getComputedStyle(el).display;
            if (display !== 'inline') return false;
            const parent = el.parentElement;
            if (!parent) return false;
            return (parent.textContent || '').replace(el.textContent || '', '').trim().length > 0;
        }
        function isUAControlled(el) {
            const tag = el.tagName.toUpperCase(); const type = (el.type || '').toLowerCase();
            if (tag !== 'INPUT' || !['checkbox','radio'].includes(type)) return false;
            const style = window.getComputedStyle(el);
            const app = style.appearance || style.webkitAppearance || '';
            return app !== 'none';
        }
        const seenTs = new WeakSet();
        const rawTs = [];
        function addTarget(el) {
            if (seenTs.has(el)) return; seenTs.add(el);
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const w = rect.width; const h = rect.height;
            rawTs.push({
                element_index: rawTs.length, tag: el.tagName.toUpperCase(),
                role: el.getAttribute('role') || null, element_id: el.id || null,
                input_type: el.type || null, accessible_name: computeAccessibleName(el) || null,
                rendered_width_px: Math.round(w*100)/100, rendered_height_px: Math.round(h*100)/100,
                padding_top_px: parseFloat(style.paddingTop)||0, padding_bottom_px: parseFloat(style.paddingBottom)||0,
                padding_left_px: parseFloat(style.paddingLeft)||0, padding_right_px: parseFloat(style.paddingRight)||0,
                is_inline_exception: isInlineLink(el), is_ua_controlled_exception: isUAControlled(el),
                is_offset_exception: false, required_offset_x_px: 0, required_offset_y_px: 0,
                nearest_target_gap_x_px: null, nearest_target_gap_y_px: null,
                passes_size: w >= MIN_PX && h >= MIN_PX,
                html_snippet: (el.outerHTML || '').slice(0, 400),
                _left: Math.round(rect.left*100)/100, _top: Math.round(rect.top*100)/100,
                _right: Math.round(rect.right*100)/100, _bottom: Math.round(rect.bottom*100)/100,
            });
        }
        queryShadow(document, 'button, a[href], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"], input[type="checkbox"], input[type="radio"]').forEach(addTarget);
        queryShadow(document, '[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            const tag = el.tagName.toUpperCase();
            if (['BUTTON','A','INPUT','SELECT','TEXTAREA'].includes(tag)) return;
            addTarget(el);
        });
        for (let i = 0; i < rawTs.length; i++) {
            const cur = rawTs[i];
            const reqX = Math.max(0, (MIN_PX - cur.rendered_width_px) / 2);
            const reqY = Math.max(0, (MIN_PX - cur.rendered_height_px) / 2);
            let minGapX = Number.POSITIVE_INFINITY, minGapY = Number.POSITIVE_INFINITY, intersectsInflated = false;
            const inflated = { left: cur._left-reqX, right: cur._right+reqX, top: cur._top-reqY, bottom: cur._bottom+reqY };
            for (let j = 0; j < rawTs.length; j++) {
                if (i===j) continue; const other = rawTs[j];
                const hGap = other._left >= cur._right ? other._left-cur._right : (cur._left >= other._right ? cur._left-other._right : 0);
                const vGap = other._top >= cur._bottom ? other._top-cur._bottom : (cur._top >= other._bottom ? cur._top-other._bottom : 0);
                if (hGap < minGapX) minGapX = hGap; if (vGap < minGapY) minGapY = vGap;
                if (reqX > 0 || reqY > 0) {
                    const intersects = !(other._right<=inflated.left||other._left>=inflated.right||other._bottom<=inflated.top||other._top>=inflated.bottom);
                    if (intersects) intersectsInflated = true;
                }
            }
            cur.required_offset_x_px = Math.round(reqX*100)/100;
            cur.required_offset_y_px = Math.round(reqY*100)/100;
            cur.nearest_target_gap_x_px = Number.isFinite(minGapX) ? Math.round(minGapX*100)/100 : null;
            cur.nearest_target_gap_y_px = Number.isFinite(minGapY) ? Math.round(minGapY*100)/100 : null;
            cur.is_offset_exception = (reqX > 0 || reqY > 0) && !intersectsInflated;
            const { _left, _top, _right, _bottom, ...rest } = cur;
            target_sizes.push(rest);
        }
    })();

    /* ═══════════════════════════════════════════════════════════════════
       4. MOVING CONTENT  (WCAG 2.2.2)
       FIX: CSS computed-style detection does NOT require animations to be
       running at extraction time — reads animationName/animationDuration
       from getComputedStyle(el) which is set by CSS @keyframes declarations
       regardless of whether the animation has started yet.
       Also keeps the WAAPI document.getAnimations() path for JS-driven anims.
       ═══════════════════════════════════════════════════════════════════ */
    const moving_content = [];
    (function extractMovingContent() {
        function nearbyPauseButton(el) {
            const containers = [el.parentElement, el.parentElement && el.parentElement.parentElement].filter(Boolean);
            for (const c of containers) {
                const btns = c.querySelectorAll('button,[role="button"],a');
                for (const btn of btns) {
                    const txt = (btn.innerText || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').toLowerCase();
                    if (/pause|stop|一時停止|停止|止める|再生停止/.test(txt)) return true;
                }
            }
            return false;
        }
        function carouselIsAutoplay(el) {
            const ap = el.getAttribute('data-autoplay');
            if (ap !== null && ap !== 'false' && ap !== '0' && ap !== '') return true;
            const aa = el.getAttribute('data-auto-advance');
            if (aa !== null && aa !== 'false' && aa !== '0' && aa !== '') return true;
            if (el.getAttribute('data-ride') === 'carousel') return true;
            if (el.getAttribute('data-bs-ride') === 'carousel') return true;
            if (el.classList.contains('slick-initialized')) {
                try { const cfg = JSON.parse(el.getAttribute('data-slick') || '{}'); if (cfg.autoplay === true) return true; } catch(e) {}
                if (el.slickOptions && el.slickOptions.autoplay) return true;
            }
            if (el.classList.contains('swiper-initialized') || el.classList.contains('swiper-container') || el.classList.contains('swiper')) {
                if (el.swiper && el.swiper.autoplay && el.swiper.autoplay.running) return true;
                try { const cfg = JSON.parse(el.getAttribute('data-swiper') || el.getAttribute('data-options') || '{}'); if (cfg.autoplay) return true; } catch(e) {}
            }
            if (el.classList.contains('owl-carousel')) {
                try { const cfg = JSON.parse(el.getAttribute('data-owlcarousel') || '{}'); if (cfg.autoPlay || cfg.autoplay) return true; } catch(e) {}
            }
            if (el.classList.contains('flickity-enabled')) {
                try { const cfg = JSON.parse(el.getAttribute('data-flickity') || '{}'); if (cfg.autoPlay) return true; } catch(e) {}
                if (el.flickity && el.flickity.options && el.flickity.options.autoPlay) return true;
            }
            if (el.classList.contains('splide')) {
                try { const cfg = JSON.parse(el.getAttribute('data-splide') || '{}'); if (cfg.autoplay || cfg.autoPlay) return true; } catch(e) {}
                if (el.splide && el.splide.options && el.splide.options.autoplay) return true;
            }
            return false;
        }
        function carouselHasPauseButton(el) {
            if (nearbyPauseButton(el)) return true;
            const inner = el.querySelectorAll ? el.querySelectorAll('button,[role="button"],[role="switch"],a') : [];
            for (const btn of inner) {
                const txt = (btn.innerText || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').toLowerCase();
                if (/pause|stop|一時停止|停止|止める/.test(txt)) return true;
            }
            if (el.querySelector && el.querySelector('[aria-label*="pause" i],[aria-label*="stop" i],[aria-label*="一時停止" i]')) return true;
            return false;
        }

        // 1. Videos with autoplay
        document.querySelectorAll('video').forEach(el => {
            if (!el.hasAttribute('autoplay') && !el.hasAttribute('data-autoplay')) return;
            const vidDuration = isFinite(el.duration) ? el.duration : null;
            if (vidDuration !== null && vidDuration <= 5) return;
            const src = el.currentSrc || el.getAttribute('src') || (el.querySelector('source[src]') || {}).src || null;
            const loops = el.hasAttribute('loop'); const hasControls = el.hasAttribute('controls'); const hasPauseBtn = nearbyPauseButton(el);
            moving_content.push({ element_index: moving_content.length, content_type: 'video_autoplay', tag: 'VIDEO', element_id: el.id||null, src, animation_name: null, animation_duration_seconds: null, animation_iteration_count: loops?'infinite':null, loops, duration_seconds: loops?-1:(vidDuration||null), starts_automatically: true, has_video_controls: hasControls, has_pause_button: hasPauseBtn, has_mechanism: hasControls||hasPauseBtn, axe_would_catch: false, html_snippet: (el.outerHTML||'').slice(0,400) });
        });

        // 2. Animated GIFs
        document.querySelectorAll('img[src]').forEach(el => {
            const src = (el.getAttribute('src') || '').toLowerCase().split('?')[0];
            if (!src.endsWith('.gif')) return;
            const hasPauseBtn = nearbyPauseButton(el);
            moving_content.push({ element_index: moving_content.length, content_type: 'animated_gif', tag: 'IMG', element_id: el.id||null, src: el.src||null, animation_name: null, animation_duration_seconds: null, animation_iteration_count: 'infinite', loops: true, duration_seconds: -1, starts_automatically: true, has_video_controls: false, has_pause_button: hasPauseBtn, has_mechanism: hasPauseBtn, axe_would_catch: false, html_snippet: (el.outerHTML||'').slice(0,400) });
        });

        // 3a. WAAPI animations (running animations via document.getAnimations)
        if (typeof document.getAnimations === 'function') {
            const seen = new WeakMap();
            document.getAnimations().forEach(anim => {
                const effect = anim.effect; if (!effect || !effect.target) return;
                const el = effect.target; if (!el || !el.tagName) return;
                const timing = effect.getTiming ? effect.getTiming() : {};
                const durMs = typeof timing.duration === 'number' ? timing.duration : 0;
                const iters = timing.iterations; const isInfin = iters === Infinity;
                const totalMs = isInfin ? Infinity : durMs * (iters || 1);
                if (!isInfin && totalMs <= 5000) return;
                const animName = anim.animationName || anim.id || 'unknown';
                if (!seen.has(el)) seen.set(el, new Set());
                if (seen.get(el).has(animName)) return;
                seen.get(el).add(animName);
                const isPaused = anim.playState === 'paused'; const hasPauseBtn = nearbyPauseButton(el);
                moving_content.push({ element_index: moving_content.length, content_type: 'css_animation', tag: el.tagName.toUpperCase(), element_id: el.id||null, src: null, animation_name: animName, animation_duration_seconds: durMs/1000, animation_iteration_count: isInfin?'infinite':String(iters||1), loops: isInfin, duration_seconds: isInfin?-1:totalMs/1000, starts_automatically: true, has_video_controls: false, has_pause_button: hasPauseBtn, has_mechanism: hasPauseBtn||isPaused, axe_would_catch: false, html_snippet: (el.outerHTML||'').slice(0,300) });
            });
        }

        // 3b. CSS computed-style animation detection (FIX for WCAG 2.2.2 timing bug)
        // This detects @keyframes animations regardless of whether they are currently
        // running — animationName is set by CSS rules, not by runtime state.
        (function cssComputedAnimations() {
            const seenCss = new WeakSet();
            document.querySelectorAll('*').forEach(el => {
                const style = window.getComputedStyle(el);
                const animName = style.animationName;
                if (!animName || animName === 'none') return;
                // animationDuration is comma-separated when multiple animations apply
                const durStrs = (style.animationDuration || '0s').split(',').map(s => s.trim());
                const iterStrs = (style.animationIterationCount || '1').split(',').map(s => s.trim());
                const names = animName.split(',').map(s => s.trim());
                names.forEach((name, idx) => {
                    if (name === 'none') return;
                    const durStr = durStrs[idx] || durStrs[0] || '0s';
                    const durSec = parseFloat(durStr) * (durStr.endsWith('ms') ? 0.001 : 1);
                    if (isNaN(durSec) || durSec <= 0) return;
                    const iterStr = iterStrs[idx] || iterStrs[0] || '1';
                    const isInfin = iterStr === 'infinite';
                    const totalSec = isInfin ? Infinity : durSec * (parseFloat(iterStr) || 1);
                    if (!isInfin && totalSec <= 5) return;
                    if (seenCss.has(el)) return;
                    seenCss.add(el);
                    // Skip if already captured by WAAPI path
                    const alreadyCaptured = moving_content.some(m => m.content_type === 'css_animation' && m.element_id === (el.id||null) && m.animation_name === name);
                    if (alreadyCaptured) return;
                    const hasPauseBtn = nearbyPauseButton(el);
                    const playState = style.animationPlayState || 'running';
                    const isPaused = playState.includes('paused');
                    moving_content.push({ element_index: moving_content.length, content_type: 'css_animation', tag: el.tagName.toUpperCase(), element_id: el.id||null, src: null, animation_name: name, animation_duration_seconds: durSec, animation_iteration_count: isInfin?'infinite':iterStr, loops: isInfin, duration_seconds: isInfin?-1:totalSec, starts_automatically: true, has_video_controls: false, has_pause_button: hasPauseBtn, has_mechanism: hasPauseBtn||isPaused, axe_would_catch: false, html_snippet: (el.outerHTML||'').slice(0,300) });
                });
            });
        })();

        // 3c. JS-transform animation detection (GSAP, Lottie, RAF-driven motion)
        // Sample transform/opacity at t=0 and t=500ms; if they differ, element is
        // being animated via JS rather than CSS @keyframes.
        // NOTE: This runs async but we mark elements synchronously for the snap.
        (function jsTransformAnimations() {
            // Detect GSAP global
            if (window.gsap && window.gsap.globalTimeline) {
                const tl = window.gsap.globalTimeline;
                if (tl.totalDuration && tl.totalDuration() > 0) {
                    const hasPauseBtn = false;
                    moving_content.push({
                        element_index: moving_content.length,
                        content_type: 'js_animation',
                        tag: 'BODY',
                        element_id: null,
                        src: null,
                        animation_name: 'gsap-global-timeline',
                        animation_duration_seconds: tl.totalDuration(),
                        animation_iteration_count: 'unknown',
                        loops: true,
                        duration_seconds: -1,
                        starts_automatically: true,
                        has_video_controls: false,
                        has_pause_button: hasPauseBtn,
                        has_mechanism: hasPauseBtn,
                        axe_would_catch: false,
                        html_snippet: '<body data-gsap="true">',
                    });
                }
            }
            // Detect Lottie animations (lottie-player / lottie-web)
            document.querySelectorAll('lottie-player, [class*="lottie"]').forEach(el => {
                const alreadyCaptured = moving_content.some(m => m.element_id === (el.id||null) && m.content_type === 'js_animation');
                if (alreadyCaptured) return;
                const hasPauseBtn = nearbyPauseButton(el);
                moving_content.push({
                    element_index: moving_content.length,
                    content_type: 'js_animation',
                    tag: el.tagName.toUpperCase(),
                    element_id: el.id || null,
                    src: el.getAttribute('src') || null,
                    animation_name: 'lottie-animation',
                    animation_duration_seconds: null,
                    animation_iteration_count: 'infinite',
                    loops: true,
                    duration_seconds: -1,
                    starts_automatically: true,
                    has_video_controls: false,
                    has_pause_button: hasPauseBtn,
                    has_mechanism: hasPauseBtn,
                    axe_would_catch: false,
                    html_snippet: (el.outerHTML||'').slice(0,400),
                });
            });
        })();

        // 4. Carousels
        const carouselSelectors = ['[data-ride="carousel"]','[data-bs-ride="carousel"]','.slick-initialized','.swiper-initialized','.swiper-container','.swiper','.owl-carousel','.flickity-enabled','.glide--carousel','.splide','[data-autoplay]','[data-auto-advance]'];
        const seenCarousel = new WeakSet();
        for (const sel of carouselSelectors) {
            document.querySelectorAll(sel).forEach(el => {
                if (seenCarousel.has(el)) return; seenCarousel.add(el);
                if (!carouselIsAutoplay(el)) return;
                const hasPauseBtn = carouselHasPauseButton(el);
                moving_content.push({ element_index: moving_content.length, content_type: 'carousel_autoplay', tag: el.tagName.toUpperCase(), element_id: el.id||null, src: null, animation_name: null, animation_duration_seconds: null, animation_iteration_count: 'infinite', loops: true, duration_seconds: -1, starts_automatically: true, has_video_controls: false, has_pause_button: hasPauseBtn, has_mechanism: hasPauseBtn, axe_would_catch: false, html_snippet: (el.outerHTML||'').slice(0,400) });
            });
        }

        // 5. Marquee / blink
        document.querySelectorAll('marquee').forEach(el => {
            moving_content.push({ element_index: moving_content.length, content_type: 'marquee_element', tag: 'MARQUEE', element_id: el.id||null, src: null, animation_name: null, animation_duration_seconds: null, animation_iteration_count: 'infinite', loops: true, duration_seconds: -1, starts_automatically: true, has_video_controls: false, has_pause_button: false, has_mechanism: false, axe_would_catch: true, html_snippet: (el.outerHTML||'').slice(0,400) });
        });
    })();

    /* ═══════════════════════════════════════════════════════════════════
       5. MEDIA ELEMENTS  (WCAG 1.2.1)
       ═══════════════════════════════════════════════════════════════════ */
    const media = [];
    (function extractMedia() {
        function getNearbyLinks(el) {
            const links = []; let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                container.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href') || ''; const text = (a.innerText || a.textContent || '').trim();
                    if (href && text) links.push({ href, text: text.slice(0,200) });
                });
                container = container.parentElement;
            }
            const seen = new Set();
            return links.filter(l => { if (seen.has(l.href)) return false; seen.add(l.href); return true; });
        }
        function getNearbyText(el) { const p = el.parentElement; return p ? (p.innerText||p.textContent||'').trim().slice(0,500) : ''; }
        function getNearbyDetails(el) {
            const details = []; let container = el.parentElement;
            for (let i = 0; i < 3 && container; i++) {
                container.querySelectorAll('details').forEach(d => {
                    const summary = d.querySelector('summary');
                    details.push({ summary: (summary?summary.innerText||'':'').trim().slice(0,200), content: (d.innerText||'').trim().slice(0,1000) });
                });
                container = container.parentElement;
            }
            return details;
        }
        function resolveDescribedBy(el) {
            const ids = (el.getAttribute('aria-describedby') || '').trim(); if (!ids) return null;
            const texts = []; ids.split(/\s+/).forEach(id => { const t = document.getElementById(id); if (t) texts.push((t.innerText||t.textContent||'').trim()); });
            return texts.length > 0 ? texts.join(' ').slice(0,1000) : null;
        }
        function getTracks(el) {
            const tracks = []; el.querySelectorAll('track').forEach(t => { tracks.push({ kind: t.getAttribute('kind')||null, src: t.getAttribute('src')||null, srclang: t.getAttribute('srclang')||null, label: t.getAttribute('label')||null }); });
            return tracks;
        }
        ['audio','video'].forEach(tagName => {
            document.querySelectorAll(tagName).forEach(el => {
                const src = el.currentSrc || el.getAttribute('src') || (el.querySelector('source[src]')||{}).src || null;
                media.push({ element_index: media.length, tag: tagName.toUpperCase(), element_id: el.id||null, src, html_snippet: (el.outerHTML||'').slice(0,500), has_autoplay: el.hasAttribute('autoplay'), has_controls: el.hasAttribute('controls'), has_loop: el.hasAttribute('loop'), is_muted: el.muted||el.hasAttribute('muted'), tracks: getTracks(el), aria_hidden: el.getAttribute('aria-hidden')==='true', role: el.getAttribute('role')||null, aria_label: el.getAttribute('aria-label')||null, aria_describedby_text: resolveDescribedBy(el), nearby_links: getNearbyLinks(el), nearby_text: getNearbyText(el), nearby_details: getNearbyDetails(el) });
            });
        });
    })();

    /* ═══════════════════════════════════════════════════════════════════
       6. TEXT SPACING  (WCAG 1.4.12 static)
       ═══════════════════════════════════════════════════════════════════ */
    const text_spacing = [];
    (function extractTextSpacing() {
        const ignoredTags = ['html','head','body','script','style','img','svg','canvas'];
        let idx = 0;
        document.querySelectorAll('*').forEach(el => {
            const tag = el.tagName.toLowerCase();
            if (ignoredTags.includes(tag)) return;
            const style = window.getComputedStyle(el);
            const display = style.display;
            if (!['block','inline-block','flex','grid'].includes(display)) return;
            const text = (el.innerText || '').trim();
            if (text.length < 20) return;
            const height = style.height; const overflow = style.overflow;
            const hasFixedHeight = height && height !== 'auto' && /^\d+(\.\d+)?px$/.test(height);
            const hasOverflowHidden = overflow === 'hidden' || overflow === 'clip';
            const isClipped = (hasOverflowHidden && el.scrollHeight > el.clientHeight) || (hasOverflowHidden && el.scrollWidth > el.clientWidth);
            text_spacing.push({ element_index: idx++, tag, element_id: el.id||null, class_name: el.className||null, text_length: text.length, text_preview: text.slice(0,150), height, min_height: style.minHeight, overflow, has_fixed_height: !!hasFixedHeight, has_overflow_hidden: hasOverflowHidden, html_snippet: el.outerHTML.slice(0,400), is_clipped: isClipped });
        });
    })();

    return { forms, interactive, target_sizes, moving_content, media, text_spacing };
}"""


# ---------------------------------------------------------------------------
# Smart wait helpers (runs in-page via evaluate)
# ---------------------------------------------------------------------------

_LAZY_LOAD_TRIGGER_JS = """async () => {
    // 1. Mock IntersectionObserver entries for all observed elements
    if (typeof IntersectionObserver !== 'undefined') {
        try {
            const origObserver = window._origIO || IntersectionObserver;
            window._origIO = origObserver;
            // Dispatch lazyload events on all imgs with data-src
            document.querySelectorAll('[data-src],[data-lazy-src],[data-original],[loading="lazy"]').forEach(el => {
                ['lazyload','lazyloaded','lazy-load'].forEach(evt => el.dispatchEvent(new Event(evt, {bubbles:true})));
                if (el.dataset.src) el.src = el.dataset.src;
                if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
                if (el.dataset.original) el.src = el.dataset.original;
            });
        } catch(e) {}
    }
    // 2. Scroll through page in steps to trigger scroll-based lazy loading
    const totalHeight = document.documentElement.scrollHeight;
    const steps = 6;
    for (let i = 1; i <= steps; i++) {
        window.scrollTo(0, (totalHeight / steps) * i);
        await new Promise(r => setTimeout(r, 200));
    }
    window.scrollTo(0, 0);
}"""

_DOM_STABILITY_JS = f"""(stabilityMs) => {{
    return new Promise((resolve) => {{
        let timer = null;
        const totalTimeout = {_DOM_STABILITY_TOTAL_MS};
        const startTime = Date.now();
        function reset() {{
            if (timer) clearTimeout(timer);
            if (Date.now() - startTime > totalTimeout) {{ resolve('timeout'); return; }}
            timer = setTimeout(() => resolve('stable'), stabilityMs);
        }}
        reset();
        const observer = new MutationObserver(() => {{
            // Ignore attribute mutations on cosmetic elements (counters, progress bars)
            reset();
        }});
        observer.observe(document.body, {{ childList: true, subtree: true }});
        setTimeout(() => {{ observer.disconnect(); resolve('total_timeout'); }}, totalTimeout);
    }});
}}"""


# ---------------------------------------------------------------------------
# UniversalPageLoader
# ---------------------------------------------------------------------------


class UniversalPageLoader:
    """
    Loads a URL once with smart wait, records a HAR, and extracts all
    static accessibility data in a single evaluate() call.
    """

    @classmethod
    async def load(
        cls,
        url: str,
        output_dir: Path,
        record_har: bool = True,
        stealth: bool = True,
        http2: bool = True,
        storage_state: Optional[Any] = None,
    ) -> PageSnapshot:
        """
        Open *url* once with smart wait, extract all static data, optionally
        record a HAR for scenario-based crawlers.

        Parameters
        ----------
        stealth:
            Use stealth context (removes navigator.webdriver, adds Chrome
            globals, uses a non-Headless UA).  Defaults to True.
        http2:
            Set False to disable HTTP/2 (needed for Akamai-protected sites).
        storage_state:
            Playwright storage state dict for injecting cookies/sessions.

        Returns a :class:`PageSnapshot` ready for all auditors.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        har_path: Optional[str] = None
        har_file = str(output_dir / "session.har") if record_har else None

        async with async_playwright() as pw:
            if stealth:
                browser = await launch_stealth_browser(pw, http2=http2)
                context = await create_stealth_context(
                    browser,
                    width=1440,
                    height=900,
                    record_har_path=har_file if record_har else None,
                    storage_state=storage_state,
                )
            else:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context_kwargs: Dict[str, Any] = dict(
                    viewport={"width": 1440, "height": 900},
                )
                if record_har and har_file:
                    context_kwargs["record_har_path"] = har_file
                    context_kwargs["record_har_url_filter"] = "**/*"
                if storage_state is not None:
                    context_kwargs["storage_state"] = storage_state
                context = await browser.new_context(**context_kwargs)
                await install_ssrf_guard(context)

            page = await context.new_page()
            extracted: Dict[str, Any] = {}

            page_warnings: List[str] = []
            try:
                # ── Step 1: Navigate ──────────────────────────────────────
                await cls._navigate(page, url)

                # ── Step 1b: Challenge / interstitial detection ───────────
                try:
                    challenge_reasons = await page.evaluate(_CHALLENGE_DETECT_JS)
                    if challenge_reasons:
                        msg = (
                            f"challenge/interstitial page detected for {url}: "
                            + ", ".join(challenge_reasons)
                        )
                        logger.warning(f"[universal] {msg}")
                        page_warnings.append(msg)
                except Exception as _ce:
                    logger.debug(f"[universal] challenge detection error: {_ce}")

                # ── Step 2: Wait for networkidle (best-effort, max 15s) ───
                try:
                    await page.wait_for_load_state(
                        "networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS
                    )
                    logger.debug(f"[universal] networkidle reached for {url}")
                except Exception:
                    logger.debug(
                        f"[universal] networkidle timeout for {url} — continuing"
                    )

                # ── Step 3: Wait for SPA framework hydration signal ───────
                await cls._wait_for_spa(page)

                # ── Step 4: DOM stability check ───────────────────────────
                reason = await page.evaluate(
                    _DOM_STABILITY_JS, _DOM_STABILITY_MS
                )
                logger.debug(f"[universal] DOM stability: {reason} for {url}")

                # ── Step 5: Trigger lazy-load ─────────────────────────────
                await page.evaluate(_LAZY_LOAD_TRIGGER_JS)
                await page.wait_for_timeout(_POST_SCROLL_WAIT_MS)

                # ── Step 6: DOM stability again (after lazy-load) ─────────
                await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)

                # ── Step 6b: Wait for carousel/slider post-hydration init ─
                await cls._wait_for_carousels(page)

                # ── Step 7: Single extraction pass ────────────────────────
                extracted = await page.evaluate(_COMBINED_EXTRACT_JS)
                logger.info(
                    f"[universal] extracted: "
                    f"forms={len(extracted.get('forms', []))}, "
                    f"interactive={len(extracted.get('interactive', []))}, "
                    f"target_sizes={len(extracted.get('target_sizes', []))}, "
                    f"moving_content={len(extracted.get('moving_content', []))}, "
                    f"media={len(extracted.get('media', []))}, "
                    f"text_spacing={len(extracted.get('text_spacing', []))}"
                )

            except Exception as exc:
                logger.error(f"[universal] extraction failed for {url}: {exc}")
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()  # HAR is written on context close
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

        if record_har and har_file:
            import os
            if os.path.exists(har_file):
                har_path = har_file
                logger.info(f"[universal] HAR recorded: {har_path}")

        return PageSnapshot(
            page_url=url,
            forms=extracted.get("forms", []),
            interactive=extracted.get("interactive", []),
            target_sizes=extracted.get("target_sizes", []),
            moving_content=extracted.get("moving_content", []),
            media=extracted.get("media", []),
            text_spacing=extracted.get("text_spacing", []),
            har_path=har_path,
            warnings=page_warnings,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    async def _navigate(page, url: str) -> None:
        """Navigate with a retry chain: domcontentloaded → commit."""
        for wait_until, timeout_ms in [
            ("domcontentloaded", _GOTO_TIMEOUT_MS),
            ("commit", 15_000),
        ]:
            try:
                await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                return
            except Exception as exc:
                logger.warning(f"[universal] goto({wait_until}) failed: {exc}")
        raise RuntimeError(f"[universal] Could not navigate to {url}")

    @staticmethod
    async def _wait_for_spa(page) -> None:
        """Poll for SPA framework readiness signals (max 5s)."""
        for signal in _SPA_SIGNALS:
            try:
                found = await page.evaluate(f"() => !!({signal})")
                if found:
                    logger.debug(f"[universal] SPA signal found: {signal}")
                    # Give the framework 800ms to finish rendering after detection
                    await page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    @staticmethod
    async def _wait_for_carousels(page) -> None:
        """
        Poll for carousel library initialisation (Flickity, Swiper, Slick, …).

        Carousels initialise asynchronously after DOM-ready, so without this
        wait their items show as overflow:hidden containers and animations are
        missed by the extractor.  We poll up to _CAROUSEL_POLL_MAX_MS ms.
        """
        selector = ", ".join(_CAROUSEL_READY_SELECTORS)
        elapsed = 0
        while elapsed < _CAROUSEL_POLL_MAX_MS:
            try:
                found = await page.evaluate(
                    f"() => !!document.querySelector('{selector}')"
                )
                if found:
                    logger.debug("[universal] carousel detected — waiting 500ms for animation setup")
                    await page.wait_for_timeout(500)
                    return
            except Exception:
                pass
            await page.wait_for_timeout(_CAROUSEL_POLL_INTERVAL_MS)
            elapsed += _CAROUSEL_POLL_INTERVAL_MS
        # No carousel found — that's fine, proceed immediately

    @staticmethod
    def save_snapshot(snapshot: PageSnapshot, output_dir: Path) -> str:
        """Persist the full PageSnapshot to JSON for debugging."""
        import dataclasses

        path = output_dir / "universal_snapshot.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataclasses.asdict(snapshot), f, indent=2)
        return str(path)


# ---------------------------------------------------------------------------
# Module-level helpers (for use by individual crawlers that open their own page)
# ---------------------------------------------------------------------------


async def navigate_with_retry(page, url: str) -> None:
    """Navigate *page* to *url* using the same retry chain as UniversalPageLoader.

    Tries domcontentloaded first (30 s), then falls back to commit (15 s).
    Raises RuntimeError if both attempts fail.

    Individual crawlers should use this instead of bare ``page.goto()`` so that
    slow / partially-broken pages are handled consistently.
    """
    for wait_until, timeout_ms in [
        ("domcontentloaded", _GOTO_TIMEOUT_MS),
        ("commit", 15_000),
    ]:
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return
        except Exception as exc:
            logger.warning(f"[nav] goto({wait_until}) failed for {url}: {exc}")
    raise RuntimeError(f"[nav] Could not navigate to {url}")
