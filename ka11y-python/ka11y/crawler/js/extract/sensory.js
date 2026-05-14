// Sensory extractor: text spacing + sensory-characteristic text.
// Composed by universal_page.py: the shared helper preamble
// (extract/common.js) is prepended, then this body, inside one
// `(frameMeta) => { ... }` wrapper.
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

    return { text_spacing, sensory };
