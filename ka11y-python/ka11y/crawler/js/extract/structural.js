// Structural extractor: forms + interactive controls.
// Composed by universal_page.py: the shared helper preamble
// (extract/common.js) is prepended, then this body, inside one
// `(frameMeta) => { ... }` wrapper.
    const forms = [];
    (function extractForms() {
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
    (function extractInteractive() {
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

    return { forms, interactive };
