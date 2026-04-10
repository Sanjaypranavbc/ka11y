from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page, async_playwright

from ka11y.config.logger import setup_logger
from ka11y.crawler._ssrf_guard import install_ssrf_guard
from ka11y.utils.step_logger import ExecutionStepLogger

logger = setup_logger(name="KAC", tag="universal_page")

_GOTO_TIMEOUT_MS = 30_000
_NETWORKIDLE_TIMEOUT_MS = 15_000
_DOM_STABILITY_MS = 600
_DOM_STABILITY_TOTAL_MS = 12_000
_POST_SCROLL_WAIT_MS = 1_500

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


@dataclass
class PageSnapshot:
    page_url: str
    forms: List[Dict[str, Any]] = field(default_factory=list)
    interactive: List[Dict[str, Any]] = field(default_factory=list)
    target_sizes: List[Dict[str, Any]] = field(default_factory=list)
    moving_content: List[Dict[str, Any]] = field(default_factory=list)
    media: List[Dict[str, Any]] = field(default_factory=list)
    text_spacing: List[Dict[str, Any]] = field(default_factory=list)
    sensory: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    element_refs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    page_summaries: List[Dict[str, Any]] = field(default_factory=list)
    pages_crawled: int = 0
    partial: bool = False
    har_path: Optional[str] = None


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

    function resolveAriaLabelledby(el) {
        const value = el.getAttribute('aria-labelledby');
        if (!value) return null;
        const parts = value.trim().split(/\s+/)
            .map(id => {
                const ref = deepGetElementById(document, id);
                return ref ? (ref.innerText || ref.textContent || '').trim() : '';
            })
            .filter(Boolean);
        return parts.length ? parts.join(' ') : null;
    }

    function explicitLabelFor(el) {
        const id = el.id;
        if (!id) return null;
        const selector = `label[for="${safeEscape(id)}"]`;
        return queryShadowOne(document, selector);
    }

    function computeAccessibleName(el) {
        const tag = el.tagName.toUpperCase();
        const type = (el.type || '').toLowerCase();

        const labelledby = resolveAriaLabelledby(el);
        if (labelledby) return labelledby;

        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

        if (tag === 'INPUT') {
            if (['submit', 'button', 'reset'].includes(type)) {
                const value = el.value || el.getAttribute('value');
                if (value && value.trim()) return value.trim();
                return type === 'submit' ? 'Submit' : (type === 'reset' ? 'Reset' : '');
            }
            if (type === 'image') {
                const alt = el.getAttribute('alt');
                return alt !== null ? alt.trim() : '';
            }
        }

        const labelEl = explicitLabelFor(el);
        if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();

        const wrapping = el.closest('label');
        if (wrapping) {
            const clone = wrapping.cloneNode(true);
            clone.querySelectorAll('input,select,textarea,button').forEach(node => node.remove());
            return (clone.textContent || '').replace(/\s+/g, ' ').trim();
        }

        const title = el.getAttribute('title');
        if (title && title.trim()) return title.trim();

        const role = (el.getAttribute('role') || '').toLowerCase();
        if (tag === 'BUTTON' || tag === 'A' || role === 'button' || role === 'link') {
            const text = (el.innerText || el.textContent || '').trim();
            if (text) return text;
        }

        return '';
    }

    function getVisibleLabel(el) {
        const tag = el.tagName.toUpperCase();
        const type = (el.type || '').toLowerCase();

        if (tag === 'BUTTON' || tag === 'A') {
            return (el.innerText || el.textContent || '').trim();
        }

        if (tag === 'INPUT') {
            if (['submit', 'button', 'reset'].includes(type)) {
                return (el.value || el.getAttribute('value') || '').trim();
            }
            if (type === 'image') {
                return (el.getAttribute('alt') || '').trim();
            }
            const labelEl = explicitLabelFor(el);
            if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();
            const wrapping = el.closest('label');
            if (wrapping) {
                const clone = wrapping.cloneNode(true);
                clone.querySelectorAll('input,select,textarea,button').forEach(node => node.remove());
                return (clone.textContent || '').replace(/\s+/g, ' ').trim();
            }
        }

        return (el.innerText || el.textContent || '').trim();
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

    function metaFor(el) {
        return {
            page_url: pageUrl,
            document_url: documentUrl,
            frame_path: framePath,
            selector: buildSelector(el),
        };
    }

    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
        'option', 'tab', 'treeitem', 'radio', 'checkbox', 'switch',
        'combobox', 'listbox',
    ]);

    const forms = [];
    (function extractForms() {
        const formEls = Array.from(queryShadow(document, 'form'));
        const formList = formEls.length ? formEls : [document.body].filter(Boolean);

        formList.forEach((form, formIdx) => {
            queryShadow(form, 'input:not([type="hidden"]),select,textarea').forEach(el => {
                const labelEl = explicitLabelFor(el);
                const wrappingLabel = el.closest('label');
                const labelText = labelEl
                    ? (labelEl.innerText || labelEl.textContent || '').trim()
                    : (wrappingLabel ? (wrappingLabel.innerText || wrappingLabel.textContent || '').trim() : null);
                const describedby = el.getAttribute('aria-describedby') || null;

                let errorElId = null;
                let errorElRole = null;
                let errorElText = null;
                let errorHasAlert = false;
                let errorAriaLive = null;

                if (describedby) {
                    const ids = describedby.trim().split(/\s+/);
                    let firstMatch = null;
                    let alertMatch = null;
                    ids.forEach(eid => {
                        const errEl = deepGetElementById(document, eid);
                        if (!errEl) return;
                        const role = errEl.getAttribute('role') || null;
                        const live = errEl.getAttribute('aria-live') || null;
                        const candidate = {
                            id: eid,
                            role,
                            text: (errEl.innerText || errEl.textContent || '').trim(),
                            hasAlert: role === 'alert',
                            ariaLive: live,
                        };
                        if (!firstMatch) firstMatch = candidate;
                        if ((role === 'alert' || live === 'assertive' || live === 'polite') && !alertMatch) {
                            alertMatch = candidate;
                        }
                    });
                    const chosen = alertMatch || firstMatch;
                    if (chosen) {
                        errorElId = chosen.id;
                        errorElRole = chosen.role;
                        errorElText = chosen.text;
                        errorHasAlert = chosen.hasAlert;
                        errorAriaLive = chosen.ariaLive;
                    }
                }

                forms.push({
                    ...metaFor(el),
                    form_index: formIdx,
                    form_id: form.id || null,
                    form_action: form.action || null,
                    form_method: (form.method || '').toUpperCase() || null,
                    tag: el.tagName.toUpperCase(),
                    type: el.type || null,
                    id: el.id || null,
                    name: el.name || null,
                    placeholder: el.placeholder || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    aria_labelledby: el.getAttribute('aria-labelledby') || null,
                    aria_describedby: describedby,
                    has_explicit_label: !!labelEl,
                    has_wrapping_label: !!wrappingLabel,
                    label_text: labelText,
                    has_any_label: !!(labelEl || wrappingLabel || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')),
                    required: !!el.required,
                    aria_required: el.getAttribute('aria-required') || null,
                    aria_invalid: el.getAttribute('aria-invalid') || null,
                    autocomplete: el.getAttribute('autocomplete') || null,
                    error_element_id: errorElId,
                    error_element_role: errorElRole,
                    error_element_text: errorElText,
                    error_has_role_alert: errorHasAlert,
                    error_has_aria_live: errorAriaLive,
                    html: outerHTML(el, 600),
                });
            });
        });
    })();

    const interactive = [];
    (function extractInteractive() {
        const seen = new WeakSet();
        function addInteractive(el) {
            if (seen.has(el)) return;
            seen.add(el);
            const type = (el.type || '').toLowerCase() || null;
            interactive.push({
                ...metaFor(el),
                element_index: interactive.length,
                tag: el.tagName.toUpperCase(),
                role: el.getAttribute('role') || null,
                element_id: el.id || null,
                element_name: el.getAttribute('name') || null,
                input_type: type,
                visible_label: getVisibleLabel(el) || null,
                aria_label: el.getAttribute('aria-label') || null,
                aria_labelledby: el.getAttribute('aria-labelledby') || null,
                aria_labelledby_text: resolveAriaLabelledby(el) || null,
                title_attr: el.getAttribute('title') || null,
                value_attr: el.getAttribute('value') || null,
                alt_attr: el.getAttribute('alt') || null,
                accessible_name: computeAccessibleName(el) || null,
                html_snippet: outerHTML(el, 400),
            });
        }

        queryShadow(document, 'button, a[href], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"]').forEach(addInteractive);
        queryShadow(document, '[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName.toUpperCase())) return;
            addInteractive(el);
        });
    })();

    const target_sizes = [];
    (function extractTargetSizes() {
        const MIN_PX = 24;
        const seen = new WeakSet();
        const raw = [];

        function isInlineLink(el) {
            if (el.tagName !== 'A') return false;
            if (window.getComputedStyle(el).display !== 'inline') return false;
            const parent = el.parentElement;
            if (!parent) return false;
            return (parent.textContent || '').replace(el.textContent || '', '').trim().length > 0;
        }

        function isUAControlled(el) {
            const tag = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase();
            if (tag !== 'INPUT' || !['checkbox', 'radio'].includes(type)) return false;
            const style = window.getComputedStyle(el);
            const appearance = style.appearance || style.webkitAppearance || '';
            return appearance !== 'none';
        }

        function addTarget(el) {
            if (seen.has(el)) return;
            seen.add(el);
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;

            raw.push({
                ...metaFor(el),
                element_index: raw.length,
                tag: el.tagName.toUpperCase(),
                role: el.getAttribute('role') || null,
                element_id: el.id || null,
                input_type: el.type || null,
                accessible_name: computeAccessibleName(el) || null,
                rendered_width_px: Math.round(rect.width * 100) / 100,
                rendered_height_px: Math.round(rect.height * 100) / 100,
                padding_top_px: parseFloat(style.paddingTop) || 0,
                padding_bottom_px: parseFloat(style.paddingBottom) || 0,
                padding_left_px: parseFloat(style.paddingLeft) || 0,
                padding_right_px: parseFloat(style.paddingRight) || 0,
                is_inline_exception: isInlineLink(el),
                is_ua_controlled_exception: isUAControlled(el),
                is_offset_exception: false,
                required_offset_x_px: 0,
                required_offset_y_px: 0,
                nearest_target_gap_x_px: null,
                nearest_target_gap_y_px: null,
                passes_size: rect.width >= MIN_PX && rect.height >= MIN_PX,
                html_snippet: outerHTML(el, 400),
                _left: rect.left,
                _right: rect.right,
                _top: rect.top,
                _bottom: rect.bottom,
            });
        }

        queryShadow(document, 'button, a[href], input[type="submit"], input[type="button"], input[type="reset"], input[type="image"], input[type="checkbox"], input[type="radio"]').forEach(addTarget);
        queryShadow(document, '[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName.toUpperCase())) return;
            addTarget(el);
        });

        for (let i = 0; i < raw.length; i++) {
            const cur = raw[i];
            const reqX = Math.max(0, (MIN_PX - cur.rendered_width_px) / 2);
            const reqY = Math.max(0, (MIN_PX - cur.rendered_height_px) / 2);
            let minGapX = Number.POSITIVE_INFINITY;
            let minGapY = Number.POSITIVE_INFINITY;
            let intersectsInflated = false;

            const inflated = {
                left: cur._left - reqX,
                right: cur._right + reqX,
                top: cur._top - reqY,
                bottom: cur._bottom + reqY,
            };

            for (let j = 0; j < raw.length; j++) {
                if (i === j) continue;
                const other = raw[j];
                const hGap = other._left >= cur._right
                    ? other._left - cur._right
                    : (cur._left >= other._right ? cur._left - other._right : 0);
                const vGap = other._top >= cur._bottom
                    ? other._top - cur._bottom
                    : (cur._top >= other._bottom ? cur._top - other._bottom : 0);
                if (hGap < minGapX) minGapX = hGap;
                if (vGap < minGapY) minGapY = vGap;
                if (reqX > 0 || reqY > 0) {
                    const intersects = !(
                        other._right <= inflated.left ||
                        other._left >= inflated.right ||
                        other._bottom <= inflated.top ||
                        other._top >= inflated.bottom
                    );
                    if (intersects) intersectsInflated = true;
                }
            }

            cur.required_offset_x_px = Math.round(reqX * 100) / 100;
            cur.required_offset_y_px = Math.round(reqY * 100) / 100;
            cur.nearest_target_gap_x_px = Number.isFinite(minGapX) ? Math.round(minGapX * 100) / 100 : null;
            cur.nearest_target_gap_y_px = Number.isFinite(minGapY) ? Math.round(minGapY * 100) / 100 : null;
            cur.is_offset_exception = (reqX > 0 || reqY > 0) && !intersectsInflated;
            const { _left, _right, _top, _bottom, ...rest } = cur;
            target_sizes.push(rest);
        }
    })();

    const moving_content = [];
    (function extractMovingContent() {
        const STATUS_ATTR_RE = /(^|[\s:_-])(spinner|loading|loader|progress|busy|skeleton|shimmer|throbber|preload|placeholder|buffer)([\s:_-]|$)/i;
        const STATUS_TEXT_RE = /(loading|please wait|working|processing|buffering|syncing|saving|uploading|読み込み|読み込み中|ロード中|処理中|進行中|お待ちください|同期中|保存中|アップロード中|通信中|送信中)/i;
        const STATUS_ROLE_SET = new Set(['progressbar', 'status']);
        const STATUS_TAG_SET = new Set(['progress', 'sl-spinner', 'sl-progress-ring', 'sl-progress-bar']);

        function composedParent(el) {
            if (!el) return null;
            if (el.parentElement) return el.parentElement;
            const root = el.getRootNode ? el.getRootNode() : null;
            return root && root.host ? root.host : null;
        }

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
                current = composedParent(current);
                depth += 1;
            }
            return null;
        }

        function isVisibleMoving(el) {
            if (!el || !el.getBoundingClientRect) return false;
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 && rect.height === 0) return false;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            if (parseFloat(style.opacity || '1') === 0) return false;
            if (el.closest && el.closest('[hidden]')) return false;
            return true;
        }

        function nearbyPauseButton(el) {
            const containers = [el.parentElement, el.parentElement && el.parentElement.parentElement].filter(Boolean);
            for (const container of containers) {
                queryShadow(container, 'button,[role="button"],a').forEach(btn => {
                    const text = (btn.innerText || btn.getAttribute('aria-label') || btn.getAttribute('title') || '').toLowerCase();
                    if (/pause|stop|一時停止|停止|止める|再生停止/.test(text)) {
                        throw new Error('__KA11Y_HAS_PAUSE__');
                    }
                });
            }
            return false;
        }

        function hasPauseButton(el) {
            try {
                nearbyPauseButton(el);
                return false;
            } catch (err) {
                return String(err.message || err) === '__KA11Y_HAS_PAUSE__';
            }
        }

        function carouselIsAutoplay(el) {
            const autoplay = el.getAttribute('data-autoplay');
            if (autoplay !== null && autoplay !== 'false' && autoplay !== '0' && autoplay !== '') return true;
            const autoAdvance = el.getAttribute('data-auto-advance');
            if (autoAdvance !== null && autoAdvance !== 'false' && autoAdvance !== '0' && autoAdvance !== '') return true;
            if (el.getAttribute('data-ride') === 'carousel') return true;
            if (el.getAttribute('data-bs-ride') === 'carousel') return true;
            return false;
        }

        queryShadow(document, 'video').forEach(el => {
            if (!isVisibleMoving(el)) return;
            if (!el.hasAttribute('autoplay') && !el.hasAttribute('data-autoplay')) return;
            const duration = Number.isFinite(el.duration) ? el.duration : null;
            if (duration !== null && duration <= 5) return;
            const loops = el.hasAttribute('loop');
            const pause = hasPauseButton(el);
            const applicabilityException = loadingStatusExceptionFor(el);
            moving_content.push({
                ...metaFor(el),
                element_index: moving_content.length,
                content_type: 'video_autoplay',
                tag: 'VIDEO',
                element_id: el.id || null,
                src: el.currentSrc || el.getAttribute('src') || (el.querySelector('source[src]') || {}).src || null,
                animation_name: null,
                animation_duration_seconds: null,
                animation_iteration_count: loops ? 'infinite' : null,
                loops,
                duration_seconds: loops ? -1 : duration,
                duration_known: duration !== null || loops,
                starts_automatically: true,
                applicability_exception: applicabilityException,
                has_video_controls: el.hasAttribute('controls'),
                has_pause_button: pause,
                has_mechanism: el.hasAttribute('controls') || pause,
                axe_would_catch: false,
                html_snippet: outerHTML(el, 400),
            });
        });

        queryShadow(document, 'img[src]').forEach(el => {
            if (!isVisibleMoving(el)) return;
            const src = (el.getAttribute('src') || '').toLowerCase().split('?')[0];
            if (!src.endsWith('.gif')) return;
            const pause = hasPauseButton(el);
            const applicabilityException = loadingStatusExceptionFor(el);
            moving_content.push({
                ...metaFor(el),
                element_index: moving_content.length,
                content_type: 'animated_gif',
                tag: 'IMG',
                element_id: el.id || null,
                src: el.src || null,
                animation_name: null,
                animation_duration_seconds: null,
                animation_iteration_count: 'infinite',
                loops: true,
                duration_seconds: -1,
                duration_known: true,
                starts_automatically: true,
                applicability_exception: applicabilityException,
                has_video_controls: false,
                has_pause_button: pause,
                has_mechanism: pause,
                axe_would_catch: false,
                html_snippet: outerHTML(el, 400),
            });
        });

        if (typeof document.getAnimations === 'function') {
            const seen = new Set();
            document.getAnimations().forEach(anim => {
                const effect = anim.effect;
                if (!effect || !effect.target || !effect.target.tagName) return;
                const el = effect.target;
                if (!isVisibleMoving(el)) return;
                const timing = effect.getTiming ? effect.getTiming() : {};
                const durationMs = typeof timing.duration === 'number' ? timing.duration : 0;
                const iterations = timing.iterations;
                const infinite = iterations === Infinity;
                const totalMs = infinite ? Infinity : durationMs * (iterations || 1);
                if (!infinite && totalMs <= 5000) return;
                const animationName = anim.animationName || anim.id || 'unknown';
                const dedupKey = `${buildSelector(el)}::${animationName}`;
                if (seen.has(dedupKey)) return;
                seen.add(dedupKey);
                const pause = hasPauseButton(el);
                const applicabilityException = loadingStatusExceptionFor(el);
                moving_content.push({
                    ...metaFor(el),
                    element_index: moving_content.length,
                    content_type: 'css_animation',
                    tag: el.tagName.toUpperCase(),
                    element_id: el.id || null,
                    src: null,
                    animation_name: animationName,
                    animation_duration_seconds: durationMs / 1000,
                    animation_iteration_count: infinite ? 'infinite' : String(iterations || 1),
                    loops: infinite,
                    duration_seconds: infinite ? -1 : totalMs / 1000,
                    duration_known: true,
                    starts_automatically: true,
                    applicability_exception: applicabilityException,
                    has_video_controls: false,
                    has_pause_button: pause,
                    has_mechanism: pause || anim.playState === 'paused',
                    axe_would_catch: false,
                    html_snippet: outerHTML(el, 300),
                });
            });
        }

        queryShadow(document, '*').forEach(el => {
            if (!isVisibleMoving(el)) return;
            const style = window.getComputedStyle(el);
            const animationNames = (style.animationName || 'none').split(',').map(v => v.trim());
            if (!animationNames.length || animationNames.every(v => !v || v === 'none')) return;
            const durations = (style.animationDuration || '0s').split(',').map(v => v.trim());
            const iterations = (style.animationIterationCount || '1').split(',').map(v => v.trim());

            animationNames.forEach((name, idx) => {
                if (!name || name === 'none') return;
                const durationStr = durations[idx] || durations[0] || '0s';
                const seconds = parseFloat(durationStr) * (durationStr.endsWith('ms') ? 0.001 : 1);
                if (!Number.isFinite(seconds) || seconds <= 0) return;
                const iterationStr = iterations[idx] || iterations[0] || '1';
                const infinite = iterationStr === 'infinite';
                const totalSeconds = infinite ? Infinity : seconds * (parseFloat(iterationStr) || 1);
                if (!infinite && totalSeconds <= 5) return;

                const dedupKey = `${buildSelector(el)}::${name}`;
                if (moving_content.some(item => item.selector === buildSelector(el) && item.animation_name === name)) return;
                const pause = hasPauseButton(el);
                const applicabilityException = loadingStatusExceptionFor(el);
                moving_content.push({
                    ...metaFor(el),
                    element_index: moving_content.length,
                    content_type: 'css_animation',
                    tag: el.tagName.toUpperCase(),
                    element_id: el.id || null,
                    src: null,
                    animation_name: name,
                    animation_duration_seconds: seconds,
                    animation_iteration_count: infinite ? 'infinite' : iterationStr,
                    loops: infinite,
                    duration_seconds: infinite ? -1 : totalSeconds,
                    duration_known: true,
                    starts_automatically: true,
                    applicability_exception: applicabilityException,
                    has_video_controls: false,
                    has_pause_button: pause,
                    has_mechanism: pause || (style.animationPlayState || '').includes('paused'),
                    axe_would_catch: false,
                    html_snippet: outerHTML(el, 300),
                });
            });
        });

        queryShadow(document, '[data-ride="carousel"],[data-bs-ride="carousel"],[data-autoplay],[data-auto-advance],.slick-initialized,.swiper,.swiper-container,.swiper-initialized,.owl-carousel,.flickity-enabled,.glide--carousel,.splide').forEach(el => {
            if (!isVisibleMoving(el)) return;
            if (!carouselIsAutoplay(el)) return;
            const pause = hasPauseButton(el);
            const applicabilityException = loadingStatusExceptionFor(el);
            moving_content.push({
                ...metaFor(el),
                element_index: moving_content.length,
                content_type: 'carousel_autoplay',
                tag: el.tagName.toUpperCase(),
                element_id: el.id || null,
                src: null,
                animation_name: null,
                animation_duration_seconds: null,
                animation_iteration_count: 'infinite',
                loops: true,
                duration_seconds: -1,
                duration_known: true,
                starts_automatically: true,
                applicability_exception: applicabilityException,
                has_video_controls: false,
                has_pause_button: pause,
                has_mechanism: pause,
                axe_would_catch: false,
                html_snippet: outerHTML(el, 400),
            });
        });

        queryShadow(document, 'marquee, blink').forEach(el => {
            if (!isVisibleMoving(el)) return;
            const applicabilityException = loadingStatusExceptionFor(el);
            moving_content.push({
                ...metaFor(el),
                element_index: moving_content.length,
                content_type: el.tagName.toLowerCase() === 'marquee' ? 'marquee_element' : 'blink_element',
                tag: el.tagName.toUpperCase(),
                element_id: el.id || null,
                src: null,
                animation_name: null,
                animation_duration_seconds: null,
                animation_iteration_count: 'infinite',
                loops: true,
                duration_seconds: -1,
                duration_known: true,
                starts_automatically: true,
                applicability_exception: applicabilityException,
                has_video_controls: false,
                has_pause_button: false,
                has_mechanism: false,
                axe_would_catch: true,
                html_snippet: outerHTML(el, 400),
            });
        });
    })();

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

    const text_spacing = [];
    (function extractTextSpacing() {
        let index = 0;
        const ignored = new Set(['html', 'head', 'body', 'script', 'style', 'img', 'svg', 'canvas']);
        queryShadow(document, '*').forEach(el => {
            const tag = el.tagName.toLowerCase();
            if (ignored.has(tag)) return;
            const style = window.getComputedStyle(el);
            if (!['block', 'inline-block', 'flex', 'grid'].includes(style.display)) return;
            const text = (el.innerText || el.textContent || '').trim();
            if (text.length < 20) return;
            const height = style.height;
            const overflow = style.overflow;
            const hasFixedHeight = !!(height && height !== 'auto' && /^\d+(\.\d+)?px$/.test(height));
            const hasOverflowHidden = overflow === 'hidden' || overflow === 'clip';
            const isClipped = (hasOverflowHidden && el.scrollHeight > el.clientHeight) ||
                (hasOverflowHidden && el.scrollWidth > el.clientWidth);
            text_spacing.push({
                ...metaFor(el),
                element_index: index++,
                tag,
                element_id: el.id || null,
                class_name: el.className || null,
                text_length: text.length,
                text_preview: text.slice(0, 150),
                height,
                min_height: style.minHeight,
                overflow,
                has_fixed_height: hasFixedHeight,
                has_overflow_hidden: hasOverflowHidden,
                html_snippet: outerHTML(el, 400),
                is_clipped: isClipped,
            });
        });
    })();

    const sensory = [];
    (function extractSensory() {
        const selector = [
            'p', 'li', 'label', 'legend', 'button', 'input', 'textarea', 'select', 'option',
            'a', 'caption', 'th', 'td', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'summary', 'figcaption', 'dt', 'dd'
        ].join(', ');

        function isCJK(text) {
            if (!text) return false;
            const matches = text.match(/[\u3000-\u9fff\uff00-\uffef\u3400-\u4dbf]/g) || [];
            return matches.length / Math.max(text.length, 1) >= 0.15;
        }

        function directTextLength(el) {
            let length = 0;
            Array.from(el.childNodes || []).forEach(node => {
                if (node.nodeType === Node.TEXT_NODE) {
                    length += (node.textContent || '').trim().length;
                }
            });
            return length;
        }

        function nearestHeading(el) {
            let cur = el.parentElement;
            while (cur && cur !== document.body) {
                if (/^H[1-6]$/.test(cur.tagName)) return (cur.innerText || cur.textContent || '').trim().slice(0, 200);
                cur = cur.parentElement;
            }
            let prev = el.previousElementSibling;
            while (prev) {
                if (/^H[1-6]$/.test(prev.tagName)) return (prev.innerText || prev.textContent || '').trim().slice(0, 200);
                prev = prev.previousElementSibling;
            }
            let next = el.nextElementSibling;
            while (next) {
                if (/^H[1-6]$/.test(next.tagName)) return (next.innerText || next.textContent || '').trim().slice(0, 200);
                next = next.nextElementSibling;
            }
            return null;
        }

        function elementLang(el) {
            let cur = el;
            while (cur && cur !== document.documentElement) {
                const value = cur.getAttribute && cur.getAttribute('lang');
                if (value) return value;
                cur = cur.parentElement;
            }
            return document.documentElement.getAttribute('lang') || null;
        }

        queryShadow(document, selector).forEach(el => {
            if (el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'hidden') return;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

            const text = (el.innerText || el.textContent || '').trim();
            const ariaLabel = (el.getAttribute('aria-label') || '').trim();
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            const title = (el.getAttribute('title') || '').trim();
            const value = ((el.value != null ? el.value : el.getAttribute('value')) || '').trim();

            if (!text && !ariaLabel && !placeholder && !title && !value) return;

            const minLen = text && isCJK(text) ? 1 : 3;
            if (text && text.length < minLen && !ariaLabel && !placeholder && !title && !value) return;

            if (['DIV', 'SPAN'].includes(el.tagName)) {
                const hasBlockChild = Array.from(el.children || []).some(child =>
                    /^(P|LI|LABEL|LEGEND|BUTTON|H[1-6]|TABLE|UL|OL)$/.test(child.tagName)
                );
                if (hasBlockChild && directTextLength(el) < 5) return;
            }

            sensory.push({
                ...metaFor(el),
                tag: el.tagName.toLowerCase(),
                element_id: el.id || null,
                element_class: el.className || null,
                text: text.slice(0, 500),
                aria_label: el.getAttribute('aria-label') || null,
                aria_labelledby: el.getAttribute('aria-labelledby') || null,
                placeholder: el.getAttribute('placeholder') || null,
                value: value || null,
                role: el.getAttribute('role') || null,
                parent_tag: el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                nearest_heading: nearestHeading(el),
                title: title || null,
                lang: elementLang(el),
                html: outerHTML(el, 500),
            });
        });
    })();

    return {
        forms,
        interactive,
        target_sizes,
        moving_content,
        media,
        text_spacing,
        sensory,
    };
}"""

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
}"""

_LAZY_LOAD_TRIGGER_JS = """async () => {
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
}"""

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
        record_har: bool = False,
        step_logger: ExecutionStepLogger | None = None,
    ) -> PageSnapshot:
        output_dir.mkdir(parents=True, exist_ok=True)
        snapshot = PageSnapshot(page_url=url)
        har_path: Optional[str] = None
        har_file = output_dir / "universal_session.har"

        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="running",
                message="Starting universal crawl",
                context={"url": url, "max_depth": max_depth, "record_har": record_har},
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context_kwargs: Dict[str, Any] = {
                "viewport": {"width": 1440, "height": 900},
                "user_agent": cls.USER_AGENT,
            }
            if record_har:
                context_kwargs["record_har_path"] = str(har_file)
                context_kwargs["record_har_url_filter"] = "**/*"

            context = await browser.new_context(**context_kwargs)
            await install_ssrf_guard(context)

            try:
                visited: set[str] = set()
                await cls._crawl_url(
                    context=context,
                    root_url=url,
                    url=url,
                    depth=0,
                    max_depth=max_depth,
                    visited=visited,
                    output=snapshot,
                    step_logger=step_logger,
                )
            finally:
                await context.close()
                await browser.close()

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
                    "forms": len(snapshot.forms),
                    "interactive": len(snapshot.interactive),
                    "target_sizes": len(snapshot.target_sizes),
                    "moving_content": len(snapshot.moving_content),
                    "media": len(snapshot.media),
                    "text_spacing": len(snapshot.text_spacing),
                    "sensory": len(snapshot.sensory),
                    "warnings": len(snapshot.warnings),
                    "har_path": har_path,
                },
            )

        return snapshot

    @classmethod
    async def _crawl_url(
        cls,
        *,
        context: BrowserContext,
        root_url: str,
        url: str,
        depth: int,
        max_depth: int,
        visited: set[str],
        output: PageSnapshot,
        step_logger: ExecutionStepLogger | None,
    ) -> None:
        normalized_url = cls._normalize_url(url)
        if normalized_url in visited:
            return
        visited.add(normalized_url)

        page = await context.new_page()
        page_warning_count = 0
        links: List[str] = []

        try:
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="running",
                    message="Opening page",
                    context={"url": normalized_url, "depth": depth},
                )

            await cls._prepare_page(page, normalized_url, step_logger=step_logger)
            extracted = await cls._extract_page(page, page_url=normalized_url, output=output)
            links = await cls._extract_links(page, root_url)
            output.page_summaries.append(
                {
                    "page_url": normalized_url,
                    "depth": depth,
                    "forms": len(extracted.get("forms", [])),
                    "interactive": len(extracted.get("interactive", [])),
                    "target_sizes": len(extracted.get("target_sizes", [])),
                    "moving_content": len(extracted.get("moving_content", [])),
                    "media": len(extracted.get("media", [])),
                    "text_spacing": len(extracted.get("text_spacing", [])),
                    "sensory": len(extracted.get("sensory", [])),
                    "links_found": len(links),
                }
            )
            output.pages_crawled += 1
            page_warning_count = len([w for w in output.warnings if w.get("page_url") == normalized_url])

            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="completed",
                    message="Extracted page",
                    context={
                        "url": normalized_url,
                        "depth": depth,
                        "forms": len(extracted.get("forms", [])),
                        "interactive": len(extracted.get("interactive", [])),
                        "target_sizes": len(extracted.get("target_sizes", [])),
                        "moving_content": len(extracted.get("moving_content", [])),
                        "media": len(extracted.get("media", [])),
                        "text_spacing": len(extracted.get("text_spacing", [])),
                        "sensory": len(extracted.get("sensory", [])),
                        "links_found": len(links),
                        "warnings": page_warning_count,
                    },
                )
        except Exception as exc:
            output.partial = True
            warning = {
                "code": "page_extract_failed",
                "page_url": normalized_url,
                "message": str(exc),
            }
            output.warnings.append(warning)
            logger.warning(f"[universal] failed to extract {normalized_url}: {exc}")
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="error",
                    message="Page extraction failed",
                    context=warning,
                )
        finally:
            await page.close()

        if depth >= max_depth:
            return

        for link in links:
            if cls._normalize_url(link) in visited:
                continue
            await cls._crawl_url(
                context=context,
                root_url=root_url,
                url=link,
                depth=depth + 1,
                max_depth=max_depth,
                visited=visited,
                output=output,
                step_logger=step_logger,
            )

    @classmethod
    async def _prepare_page(
        cls,
        page: Page,
        url: str,
        *,
        step_logger: ExecutionStepLogger | None,
    ) -> None:
        await cls._navigate(page, url)

        try:
            await page.wait_for_load_state("networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS)
        except Exception:
            logger.debug(f"[universal] networkidle timeout for {url}")

        await cls._wait_for_spa(page)
        try:
            await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
        except Exception:
            logger.debug(f"[universal] DOM stability pre-check failed for {url}")

        try:
            await page.evaluate(_LAZY_LOAD_TRIGGER_JS)
            await page.wait_for_timeout(_POST_SCROLL_WAIT_MS)
        except Exception:
            logger.debug(f"[universal] lazy-load trigger failed for {url}")

        try:
            await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
        except Exception:
            logger.debug(f"[universal] DOM stability post-check failed for {url}")

        if step_logger:
            step_logger.record(
                step="universal_page_ready",
                status="completed",
                message="Page reached extraction-ready state",
                context={"url": url},
            )

    @classmethod
    async def _extract_page(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
    ) -> Dict[str, List[Dict[str, Any]]]:
        combined = {
            "forms": [],
            "interactive": [],
            "target_sizes": [],
            "moving_content": [],
            "media": [],
            "text_spacing": [],
            "sensory": [],
        }

        frames = await cls._collect_same_origin_frames(page, page_url=page_url, output=output)
        for frame, frame_path in frames:
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
                )
                combined[key].extend(records)

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
    async def _extract_links(cls, page: Page, root_url: str) -> List[str]:
        try:
            raw_links: List[str] = await page.evaluate(_LINK_EXTRACT_JS)
        except Exception:
            return []

        resolved: List[str] = []
        for href in raw_links:
            try:
                url = cls._normalize_url(urljoin(page.url or root_url, href))
            except Exception:
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
                    warning = await cls._build_frame_warning(
                        code="cross_origin_frame_skipped",
                        page_url=page_url,
                        frame=child,
                        frame_path=child_path,
                        message="Skipped cross-origin frame during universal extraction",
                    )
                    output.warnings.append(warning)
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
            frame_meta = await frame_el.evaluate(
                """(el) => ({
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
                })"""
            )
        except Exception:
            frame_meta = None

        if isinstance(frame_meta, dict):
            for key, value in frame_meta.items():
                if value not in (None, "", []):
                    warning[key] = value

        return warning

    @staticmethod
    async def _navigate(page: Page, url: str) -> None:
        attempts = [
            ("domcontentloaded", _GOTO_TIMEOUT_MS),
            ("load", 20_000),
            ("commit", 15_000),
        ]
        for wait_until, timeout_ms in attempts:
            try:
                await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                if wait_until == "commit":
                    try:
                        await page.wait_for_selector("body", state="attached", timeout=5_000)
                    except Exception:
                        pass
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5_000)
                    except Exception:
                        pass
                return
            except Exception as exc:
                logger.warning(f"[universal] goto({wait_until}) failed for {url}: {exc}")
        raise RuntimeError(f"Could not navigate to {url}")

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
    def _normalize_url(url: str) -> str:
        normalized = url.split("#", 1)[0]
        if normalized.endswith("/") and len(normalized) > len("https://a/"):
            return normalized.rstrip("/")
        return normalized

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
            json.dump(dataclasses.asdict(snapshot), fh, indent=2, ensure_ascii=False)
        return str(path)
