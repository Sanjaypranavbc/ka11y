// Sprint 3 / step 15. The existing universal extractor records
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
