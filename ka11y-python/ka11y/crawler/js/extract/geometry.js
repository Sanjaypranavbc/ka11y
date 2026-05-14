// Geometry extractor: target sizes (getBoundingClientRect-heavy).
// Composed by universal_page.py: the shared helper preamble
// (extract/common.js) is prepended, then this body, inside one
// `(frameMeta) => { ... }` wrapper.
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

    return { target_sizes };
