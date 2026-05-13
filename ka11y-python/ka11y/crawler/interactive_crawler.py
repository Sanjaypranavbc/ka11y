"""
ka11y/crawler/interactive_crawler.py
=====================================
Playwright-based crawler for interactive elements.
Extracts visible labels and computed accessible names for WCAG 2.5.3 auditing.

What is crawled
───────────────
  • <button> elements
  • <a href="…"> links
  • <input type="submit|button|reset|image">
  • Elements with interactive ARIA roles (role="button|link|menuitem|option|tab|…")
"""

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel



class InteractiveElementData(BaseModel):
    """One interactive element record, consumed by LabelInNameAuditor."""

    page_url: str
    element_index: int
    tag: str  # BUTTON | A | INPUT | DIV …
    role: Optional[str] = None  # explicit ARIA role (if present)
    element_id: Optional[str] = None
    element_name: Optional[str] = None
    input_type: Optional[str] = None  # submit | button | reset | image

    # Visible text rendered on screen (what sighted users see)
    visible_label: Optional[str] = None

    # Accessible-name computation inputs
    aria_label: Optional[str] = None
    aria_labelledby: Optional[str] = None
    aria_labelledby_text: Optional[str] = None  # resolved text from aria-labelledby IDs
    title_attr: Optional[str] = None
    value_attr: Optional[str] = None  # for <input type="submit|button|reset">
    alt_attr: Optional[str] = None  # for <input type="image">

    # Final computed accessible name (AccName-1.1 approximation)
    accessible_name: Optional[str] = None

    selector: Optional[str] = None
    element_ref_id: Optional[str] = None
    frame_path: Optional[str] = None

    html_snippet: str = ""


class InteractiveElementCrawler:
    """
    Launches a headless Chromium browser, navigates to base_url,
    and extracts interactive elements with their visible labels
    and computed accessible names.
    """

    EXTRACT_JS = r"""() => {
        /* ── helpers ──────────────────────────────────────────────────── */

        function resolveAriaLabelledby(el) {
            const val = el.getAttribute('aria-labelledby');
            if (!val) return null;
            const ids = val.trim().split(/\s+/);
            const parts = ids
                .map(id => {
                    const ref = document.getElementById(id);
                    return ref ? (ref.innerText || ref.textContent || '').trim() : '';
                })
                .filter(t => t.length > 0);
            return parts.length > 0 ? parts.join(' ') : null;
        }

        function computeAccessibleName(el) {
            const tag  = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase();

            // 1. aria-labelledby (highest priority per AccName-1.1)
            const lbText = resolveAriaLabelledby(el);
            if (lbText) return lbText;

            // 2. aria-label
            const ariaLabel = el.getAttribute('aria-label');
            if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

            // 3. Input-type-specific native name
            if (tag === 'INPUT') {
                if (['submit', 'button', 'reset'].includes(type)) {
                    const val = el.value;
                    if (val && val.trim()) return val.trim();
                    if (type === 'submit') return 'Submit';
                    if (type === 'reset')  return 'Reset';
                    return '';
                }
                if (type === 'image') {
                    const alt = el.getAttribute('alt');
                    return alt !== null ? alt.trim() : '';
                }
            }

            // 4. <label for="id"> or wrapping <label>
            const id = el.id;
            if (id) {
                const labelEl = document.querySelector('label[for="' + id + '"]');
                if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();
            }
            const wrapping = el.closest('label');
            if (wrapping) {
                const clone = wrapping.cloneNode(true);
                clone.querySelectorAll('input,select,textarea,button').forEach(e => e.remove());
                return (clone.textContent || '').replace(/\s+/g, ' ').trim();
            }

            // 5. title attribute
            const title = el.getAttribute('title');
            if (title && title.trim()) return title.trim();

            // 6. Text content (buttons / links / role=button elements)
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (tag === 'BUTTON' || tag === 'A' || role === 'button' || role === 'link') {
                const t = (el.innerText || el.textContent || '').trim();
                if (t) return t;
            }

            return '';
        }

        function getVisibleLabel(el) {
            const tag  = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase();

            if (tag === 'BUTTON' || tag === 'A') {
                // innerText respects CSS display:none / visibility:hidden
                return (el.innerText || el.textContent || '').trim();
            }

            if (tag === 'INPUT') {
                if (['submit', 'button', 'reset'].includes(type)) {
                    return (el.value || el.getAttribute('value') || '').trim();
                }
                if (type === 'image') {
                    return (el.getAttribute('alt') || '').trim();
                }
                // For labeled text inputs, visible label is the <label> text
                const id = el.id;
                if (id) {
                    const labelEl = document.querySelector('label[for="' + id + '"]');
                    if (labelEl) return (labelEl.innerText || labelEl.textContent || '').trim();
                }
                const wrap = el.closest('label');
                if (wrap) {
                    const clone = wrap.cloneNode(true);
                    clone.querySelectorAll('input,select,textarea,button').forEach(e => e.remove());
                    return (clone.textContent || '').replace(/\s+/g, ' ').trim();
                }
                return '';
            }

            // Custom role elements
            return (el.innerText || el.textContent || '').trim();
        }

        /* ── element collection ─────────────────────────────────────── */

        const INTERACTIVE_ROLES = new Set([
            'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
            'option', 'tab', 'treeitem', 'radio', 'checkbox', 'switch',
            'combobox', 'listbox',
        ]);

        const seen    = new WeakSet();
        const results = [];

        function addElement(el) {
            if (seen.has(el)) return;
            seen.add(el);

            const tag  = el.tagName.toUpperCase();
            const type = (el.type || '').toLowerCase() || null;
            const role = el.getAttribute('role') || null;

            const visibleLabel   = getVisibleLabel(el)       || null;
            const accessibleName = computeAccessibleName(el) || null;
            const lbText         = resolveAriaLabelledby(el) || null;

            results.push({
                element_index:          results.length,
                tag:                    tag,
                role:                   role,
                element_id:             el.id                                  || null,
                element_name:           el.getAttribute('name')                || null,
                input_type:             type,
                visible_label:          visibleLabel,
                aria_label:             el.getAttribute('aria-label')          || null,
                aria_labelledby:        el.getAttribute('aria-labelledby')     || null,
                aria_labelledby_text:   lbText,
                title_attr:             el.getAttribute('title')               || null,
                value_attr:             el.getAttribute('value')               || null,
                alt_attr:               el.getAttribute('alt')                 || null,
                accessible_name:        accessibleName,
                html_snippet:           (el.outerHTML || '').slice(0, 400),
            });
        }

        // 1. Native interactive elements
        document.querySelectorAll(
            'button, a[href], input[type="submit"], input[type="button"],' +
            ' input[type="reset"], input[type="image"]'
        ).forEach(addElement);

        // 2. ARIA-role elements on non-native tags
        document.querySelectorAll('[role]').forEach(el => {
            const role = (el.getAttribute('role') || '').toLowerCase();
            if (!INTERACTIVE_ROLES.has(role)) return;
            const tag = el.tagName.toUpperCase();
            if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(tag)) return;
            addElement(el);
        });

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.max_depth = max_depth
        self.results: List[InteractiveElementData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[InteractiveElementData]:
        from ka11y.crawler.browser_pool import leased_context

        async with leased_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        ) as context:
            await self._crawl_page(context, self.base_url, depth=0)
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
                await page.goto(url, wait_until="commit", timeout=15_000)
            await page.wait_for_timeout(2000)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(InteractiveElementData(page_url=url, **item))

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
            print(f"[InteractiveCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "interactive_elements_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
