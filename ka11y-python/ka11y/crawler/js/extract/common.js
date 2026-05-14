// AUTO-COMPOSED: this file is the helper preamble shared by every
// extract/*.js category extractor. universal_page.py prepends it inside a
// single `(frameMeta) => { ... }` wrapper. Do not add a wrapper here.
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
