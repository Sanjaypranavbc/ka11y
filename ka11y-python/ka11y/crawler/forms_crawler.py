"""
ka11y/crawler/forms_crawler.py
==============================
Playwright-based form element crawler.
Extracts inputs, labels, error message containers, and ARIA attributes
needed for WCAG 3.3.1 / 3.3.2 auditing.
"""

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel

from ka11y.crawler.context_factory import new_crawler_context

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────


class FormInputData(BaseModel):
    page_url: str
    form_index: int  # 0-based index of <form> on the page
    form_id: Optional[str] = None
    form_action: Optional[str] = None
    form_method: Optional[str] = None

    # Field identity
    tag: str  # INPUT | SELECT | TEXTAREA
    type: Optional[str] = None  # text | email | password | checkbox …
    id: Optional[str] = None
    name: Optional[str] = None
    placeholder: Optional[str] = None

    # Accessible name sources
    aria_label: Optional[str] = None
    aria_labelledby: Optional[str] = None
    aria_describedby: Optional[str] = None
    has_explicit_label: bool = False  # <label for="id">
    has_wrapping_label: bool = False  # <label><input …></label>
    label_text: Optional[str] = None
    has_any_label: bool = False

    # Validation / error state
    required: bool = False
    aria_required: Optional[str] = None
    aria_invalid: Optional[str] = None
    autocomplete: Optional[str] = None

    # Error message element linked via aria-describedby (may be help text, not an error)
    error_element_id: Optional[str] = None  # id of first resolving element in aria-describedby
    error_element_role: Optional[str] = None  # alert | status | …
    error_element_text: Optional[str] = None  # current visible text (may be empty)
    error_has_role_alert: bool = False  # role="alert" present
    error_has_aria_live: Optional[str] = None  # aria-live value if set
    error_is_live: bool = False  # role in {alert,status,log} OR aria-live in {polite,assertive}

    # Error message element linked via aria-errormessage (unambiguously an error region)
    aria_errormessage: Optional[str] = None
    errormessage_element_id: Optional[str] = None
    errormessage_element_role: Optional[str] = None
    errormessage_element_text: Optional[str] = None
    errormessage_is_live: bool = False

    # Group / context info
    group_legend_text: Optional[str] = None  # fieldset > legend (for radio/checkbox groups)
    is_disabled: bool = False

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None

    html: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────


class AsyncFormCrawler:
    """
    Crawl one URL (depth=0 by default) and extract every form input
    with all metadata required for WCAG 3.3.1 / 3.3.2 auditing.
    """

    # JS injected into every page to extract form data
    EXTRACT_JS = r"""() => {
        function outerHTML(el, max=600) {
            return (el && el.outerHTML) ? el.outerHTML.slice(0, max) : '';
        }

        // Types we never audit: hidden state, non-data buttons, file picker
        const SKIP_TYPES = new Set(['hidden', 'submit', 'reset', 'button', 'image', 'file']);

        // Live-region roles whose presence makes an element announceable
        const LIVE_ROLES = new Set(['alert', 'status', 'log']);

        function resolveRefs(attrValue) {
            // Parse a space-separated id-ref list and return resolved elements.
            if (!attrValue) return [];
            return attrValue.trim().split(/\s+/)
                .map(id => ({ id, el: document.getElementById(id) }))
                .filter(x => x.el);
        }

        function collectLiveInfo(refs) {
            // Walk a list of {id, el} pairs and summarize live-region semantics + text.
            let primaryId = null;
            let primaryRole = null;
            let primaryLive = null;
            let isLive = false;
            const texts = [];
            for (const { id, el } of refs) {
                const role = (el.getAttribute('role') || '').toLowerCase();
                const live = (el.getAttribute('aria-live') || '').toLowerCase();
                const text = (el.innerText || el.textContent || '').trim();
                if (text) texts.push(text);
                if (!primaryId) primaryId = id;
                if (!primaryRole && role) primaryRole = role;
                if (!primaryLive && live) primaryLive = live;
                if (LIVE_ROLES.has(role) || live === 'assertive' || live === 'polite') {
                    isLive = true;
                }
            }
            return {
                primaryId,
                primaryRole,
                primaryLive,
                isLive,
                text: texts.length ? texts.join(' | ') : null,
            };
        }

        const results = [];

        const forms = Array.from(document.querySelectorAll('form'));
        // If no <form> tags, treat the whole document as one implicit form
        const formList = forms.length > 0 ? forms : [document.body];

        formList.forEach((form, formIdx) => {
            const formId     = form.id     || null;
            const formAction = form.action || null;
            const formMethod = (form.method || '').toUpperCase() || null;

            const inputs = Array.from(
                form.querySelectorAll('input,select,textarea')
            ).filter(el => {
                if (el.disabled) return false;
                const t = (el.getAttribute('type') || el.type || '').toLowerCase();
                if (SKIP_TYPES.has(t)) return false;
                return true;
            });

            inputs.forEach(el => {
                const id   = el.id   || null;
                const name = el.name || null;
                const inputType = (el.type || '').toLowerCase();

                // --- label resolution (text must be non-empty for it to count) ---
                const labelEl = id ? document.querySelector('label[for="'+id+'"]') : null;
                const explicitLabelText = labelEl ? (labelEl.innerText || '').trim() : '';
                const hasExplicitLabel = !!explicitLabelText;

                const wrappingLabel = el.closest('label');
                let wrappingLabelText = '';
                if (wrappingLabel) {
                    // Clone and strip nested form controls so only the label text remains.
                    const clone = wrappingLabel.cloneNode(true);
                    clone.querySelectorAll('input,select,textarea,button').forEach(n => n.remove());
                    wrappingLabelText = (clone.innerText || clone.textContent || '').trim();
                }
                const hasWrappingLabel = !!wrappingLabelText;

                const ariaLabelRaw = el.getAttribute('aria-label');
                const ariaLabel = (ariaLabelRaw && ariaLabelRaw.trim()) ? ariaLabelRaw.trim() : null;

                const ariaLabelledbyAttr = el.getAttribute('aria-labelledby') || null;
                let labelledbyText = '';
                if (ariaLabelledbyAttr) {
                    const parts = [];
                    for (const { el: ref } of resolveRefs(ariaLabelledbyAttr)) {
                        const t = (ref.innerText || ref.textContent || '').trim();
                        if (t) parts.push(t);
                    }
                    labelledbyText = parts.join(' ');
                }
                const hasResolvedLabelledby = !!labelledbyText;

                // Fieldset / legend (treated as a label source for radio/checkbox groups)
                let groupLegendText = null;
                if (inputType === 'radio' || inputType === 'checkbox') {
                    const fs = el.closest('fieldset');
                    if (fs) {
                        const lg = fs.querySelector(':scope > legend');
                        if (lg) {
                            const t = (lg.innerText || '').trim();
                            if (t) groupLegendText = t;
                        }
                    }
                }

                const labelText = explicitLabelText
                    || wrappingLabelText
                    || ariaLabel
                    || labelledbyText
                    || groupLegendText
                    || null;
                const hasAnyLabel = !!(
                    hasExplicitLabel
                    || hasWrappingLabel
                    || ariaLabel
                    || hasResolvedLabelledby
                    || groupLegendText
                );

                // --- aria-describedby (may be help text, may be error) ---
                const describedby = el.getAttribute('aria-describedby') || null;
                const describedInfo = collectLiveInfo(resolveRefs(describedby));

                // --- aria-errormessage (unambiguously an error association) ---
                const errormessage = el.getAttribute('aria-errormessage') || null;
                const errormessageInfo = collectLiveInfo(resolveRefs(errormessage));

                results.push({
                    form_index:           formIdx,
                    form_id:              formId,
                    form_action:          formAction,
                    form_method:          formMethod,
                    tag:                  el.tagName,
                    type:                 el.type         || null,
                    id:                   id,
                    name:                 name,
                    placeholder:          el.placeholder  || null,
                    aria_label:           ariaLabel,
                    aria_labelledby:      ariaLabelledbyAttr,
                    aria_describedby:     describedby,
                    has_explicit_label:   hasExplicitLabel,
                    has_wrapping_label:   hasWrappingLabel,
                    label_text:           labelText,
                    has_any_label:        hasAnyLabel,
                    required:             !!el.required,
                    aria_required:        el.getAttribute('aria-required') || null,
                    aria_invalid:         el.getAttribute('aria-invalid')  || null,
                    autocomplete:         el.getAttribute('autocomplete')  || null,
                    // aria-describedby summary
                    error_element_id:     describedInfo.primaryId,
                    error_element_role:   describedInfo.primaryRole,
                    error_element_text:   describedInfo.text,
                    error_has_role_alert: describedInfo.isLive,
                    error_has_aria_live:  describedInfo.primaryLive,
                    error_is_live:        describedInfo.isLive,
                    // aria-errormessage summary
                    aria_errormessage:         errormessage,
                    errormessage_element_id:   errormessageInfo.primaryId,
                    errormessage_element_role: errormessageInfo.primaryRole,
                    errormessage_element_text: errormessageInfo.text,
                    errormessage_is_live:      errormessageInfo.isLive,
                    // Group / state
                    group_legend_text:    groupLegendText,
                    is_disabled:          !!el.disabled,
                    html:                 outerHTML(el)
                });
            });
        });

        return results;
    }"""

    # Triggers a non-navigating submit on every form so JS-rendered validation
    # errors (aria-invalid, error-message text, dynamically-inserted live
    # regions, etc.) become visible to the static extractor on the next pass.
    TRIGGER_VALIDATION_JS = r"""() => {
        const forms = Array.from(document.querySelectorAll('form'));
        // Mark forms we've already touched so re-entry is idempotent.
        forms.forEach((form) => {
            if (form.__ka11ySubmitGuard) return;
            form.__ka11ySubmitGuard = true;
            // Capture-phase listener so it runs before the form's own onsubmit.
            form.addEventListener('submit', function (e) {
                e.preventDefault();
            }, true);
        });
        forms.forEach((form) => {
            try {
                const btn = form.querySelector(
                    'button[type="submit"], input[type="submit"], button:not([type])'
                );
                if (btn && !btn.disabled) {
                    btn.click();
                } else if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                }
            } catch (e) { /* validation handler threw — keep going */ }
        });
        return forms.length;
    }"""

    POST_SUBMIT_WAIT_MS = 1200

    def __init__(
        self,
        base_url: str,
        output_dir: str,
        max_depth: int = 0,
        interactive_validation: bool = False,
    ):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.interactive_validation = interactive_validation
        self.results: List[FormInputData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[FormInputData]:
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
                # If even domcontentloaded times out, try with no wait condition
                await page.goto(url, wait_until="commit", timeout=15_000)
            await page.wait_for_timeout(2000)  # let JS render forms

            raw: list = await page.evaluate(self.EXTRACT_JS)

            if self.interactive_validation and raw:
                raw = await self._capture_dynamic_errors(page, raw)

            for item in raw:
                self.results.append(FormInputData(page_url=url, **item))

            # Follow links for deeper crawls
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
            print(f"[FormCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    async def _capture_dynamic_errors(self, page, static_raw: list) -> list:
        """
        Submit each form with `preventDefault` installed so JS validation
        renders its error UI, then re-extract.

        Belt-and-suspenders: a Playwright route handler aborts every non-GET
        and every navigation/XHR request during this pass, so even validation
        code that bypasses the JS-side preventDefault cannot reach the network.
        """
        # Block all navigations, document loads, XHR/fetch, and websockets.
        # Allow GET-able assets (CSS, JS, images, fonts) so the page does not
        # visually collapse if the JS handler depends on them mid-validation.
        _BLOCK_RESOURCE_TYPES = {
            "document", "xhr", "fetch", "websocket", "manifest", "eventsource",
        }

        async def _block_external(route):
            try:
                req = route.request
                if req.resource_type in _BLOCK_RESOURCE_TYPES or req.method != "GET":
                    await route.abort()
                else:
                    await route.continue_()
            except Exception:
                # Page may have torn down during routing — ignore.
                pass

        await page.route("**/*", _block_external)
        try:
            try:
                await page.evaluate(self.TRIGGER_VALIDATION_JS)
            except Exception as exc:
                print(f"[FormCrawler] submit-trigger failed: {exc}")
                return static_raw

            await page.wait_for_timeout(self.POST_SUBMIT_WAIT_MS)

            try:
                dynamic_raw = await page.evaluate(self.EXTRACT_JS)
            except Exception as exc:
                print(f"[FormCrawler] post-submit extract failed: {exc}")
                return static_raw
        finally:
            try:
                await page.unroute("**/*", _block_external)
            except Exception:
                pass

        # If the post-submit DOM no longer matches the static one (e.g. a
        # multi-step form replaced its inputs), fall back to the static
        # snapshot rather than reporting a structurally different page.
        if len(dynamic_raw) != len(static_raw):
            print(
                f"[FormCrawler] post-submit field count changed "
                f"({len(static_raw)} -> {len(dynamic_raw)}) — keeping static snapshot."
            )
            return static_raw

        return dynamic_raw

    def save_raw_json(self) -> str:
        path = self.output_dir / "forms_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
