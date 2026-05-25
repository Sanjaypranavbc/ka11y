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

    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
        'option', 'tab', 'treeitem', 'radio', 'checkbox', 'switch',
        'combobox', 'listbox',
    ]);

    // Per-category fault isolation (B-3): each extractor below runs inside its
    // own try/catch. A runtime error in one category (e.g. a malformed node in
    // the forms walk) no longer aborts the entire frame.evaluate — the other
    // six categories still return their data, and the failure is reported via
    // the `_errors` field rather than silently zeroing all seven outputs.
    const _extractorErrors = {};
    function _runExtractor(name, fn) {
        try {
            fn();
        } catch (e) {
            _extractorErrors[name] = String((e && e.message) || e);
        }
    }

    const forms = [];
    _runExtractor('forms', function extractForms() {
        const formEls = Array.from(queryShadow(document, 'form'));
        const formList = formEls.length ? formEls : [document.body].filter(Boolean);

        formList.forEach((form, formIdx) => {
            queryShadow(form, 'input:not([type="hidden"]),select,textarea').forEach(el => {
                if (shouldIgnoreForSnapshot(el)) return;
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
    _runExtractor('interactive', function extractInteractive() {
        const seen = new WeakSet();
        function addInteractive(el) {
            if (shouldIgnoreForSnapshot(el)) return;
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
    _runExtractor('target_sizes', function extractTargetSizes() {
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
            if (shouldIgnoreForSnapshot(el)) return;
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
    _runExtractor('moving_content', function extractMovingContent() {
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

    const text_spacing = [];
    (function extractTextSpacing() {
        let index = 0;
        const ignored = new Set(['html', 'head', 'body', 'script', 'style', 'img', 'svg', 'canvas']);
        queryShadow(document, '*').forEach(el => {
            if (shouldIgnoreForSnapshot(el)) return;
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
            const matches = text.match(/[　-鿿＀-￯㐀-䶿]/g) || [];
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
            if (shouldIgnoreForSnapshot(el)) return;
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
}
