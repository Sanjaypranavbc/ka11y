"""
ka11y/crawler/forms_crawler.py
==============================
Playwright-based form element crawler.
Extracts inputs, labels, error message containers, and ARIA attributes
needed for WCAG 3.3.1 / 3.3.2 auditing.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel

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

    # Error message element linked to this field
    error_element_id: Optional[str] = None  # id of element in aria-describedby
    error_element_role: Optional[str] = None  # alert | status | …
    error_element_text: Optional[str] = None  # current visible text (may be empty)
    error_has_role_alert: bool = False  # role="alert" present
    error_has_aria_live: Optional[str] = None  # aria-live value if set

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
    EXTRACT_JS = """() => {
        function outerHTML(el, max=600) {
            return (el && el.outerHTML) ? el.outerHTML.slice(0, max) : '';
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
                form.querySelectorAll('input:not([type="hidden"]),select,textarea')
            );

            inputs.forEach(el => {
                const id   = el.id   || null;
                const name = el.name || null;

                // --- label resolution ---
                const labelEl       = id ? document.querySelector('label[for="'+id+'"]') : null;
                const wrappingLabel = el.closest('label');
                const labelText     = labelEl
                    ? (labelEl.innerText || '').trim()
                    : (wrappingLabel ? (wrappingLabel.innerText || '').trim() : null);
                const ariaLabel     = el.getAttribute('aria-label')      || null;
                const ariaLabelledby= el.getAttribute('aria-labelledby') || null;
                const hasAnyLabel   = !!(labelEl || wrappingLabel || ariaLabel || ariaLabelledby);

                // --- aria-describedby → error element ---
                const describedby   = el.getAttribute('aria-describedby') || null;
                let errorElId       = null;
                let errorElRole     = null;
                let errorElText     = null;
                let errorHasAlert   = false;
                let errorAriaLive   = null;

                if (describedby) {
                    // There may be multiple space-separated IDs; check each
                    const ids = describedby.trim().split(/\s+/);
                    for (const eid of ids) {
                        const errEl = document.getElementById(eid);
                        if (errEl) {
                            errorElId     = eid;
                            errorElRole   = errEl.getAttribute('role') || null;
                            errorElText   = (errEl.innerText || errEl.textContent || '').trim();
                            errorHasAlert = (errorElRole === 'alert');
                            errorAriaLive = errEl.getAttribute('aria-live') || null;
                            break; // use first matched error element
                        }
                    }
                }

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
                    aria_labelledby:      ariaLabelledby,
                    aria_describedby:     describedby,
                    has_explicit_label:   !!labelEl,
                    has_wrapping_label:   !!wrappingLabel,
                    label_text:           labelText,
                    has_any_label:        hasAnyLabel,
                    required:             !!el.required,
                    aria_required:        el.getAttribute('aria-required') || null,
                    aria_invalid:         el.getAttribute('aria-invalid')  || null,
                    autocomplete:         el.getAttribute('autocomplete')  || null,
                    error_element_id:     errorElId,
                    error_element_role:   errorElRole,
                    error_element_text:   errorElText,
                    error_has_role_alert: errorHasAlert,
                    error_has_aria_live:  errorAriaLive,
                    html:                 outerHTML(el)
                });
            });
        });

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[FormInputData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[FormInputData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
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

    def save_raw_json(self) -> str:
        path = self.output_dir / "forms_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
