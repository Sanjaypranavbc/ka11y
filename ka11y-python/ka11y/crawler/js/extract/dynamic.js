// Dynamic extractor: moving content (animations/autoplay) + media.
// Composed by universal_page.py: the shared helper preamble
// (extract/common.js) is prepended, then this body, inside one
// `(frameMeta) => { ... }` wrapper.
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
            if (shouldIgnoreForSnapshot(el)) return false;
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

    return { moving_content, media };
