"""
ka11y/crawler/sensory_crawler.py
=================================
Playwright-based crawler for WCAG 1.3.3 — Sensory Characteristics.

Extracts all instructional text-bearing elements from a page:
  <p>, <li>, <label>, <legend>, <button>, aria-label values,
  <span>, <div> with direct text, <a>, <td>, <th>, <caption>,
  <summary>, <figcaption>, <dt>, <dd>

Each record captures the element's text, tag, ARIA attributes,
title tooltip, element-level language hint, and surrounding context
so the auditor can detect instructions that rely solely on shape,
size, color, position, or sound — in both English and Japanese.

Changes over v1:
  - SensoryElementData gains `title` (tooltip text) and `lang` fields
  - TARGET_SELECTOR extended: summary, figcaption, dt, dd
  - EXTRACT_JS:
      * isCJK() helper — CJK-aware minimum text length (≥1 vs ≥3)
      * directTextLength() — dedup div/span by direct text nodes only
      * elementLang()  — walks ancestors for closest lang= attribute
      * title + lang extracted into every record
      * next-sibling heading fallback in nearestHeading()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pydantic import BaseModel

from ka11y.crawler._ssrf_guard import install_ssrf_guard


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────


class SensoryElementData(BaseModel):
    page_url: str

    # Element identity
    tag: str                          # p | li | label | legend | button | span | …
    element_id: Optional[str] = None
    element_class: Optional[str] = None

    # Text content
    text: str                         # visible inner text (trimmed)
    aria_label: Optional[str] = None  # aria-label on the element itself
    aria_labelledby: Optional[str] = None
    placeholder: Optional[str] = None # for input / textarea neighbours
    value: Optional[str] = None       # visible value for button-like inputs

    # Structural context
    role: Optional[str] = None        # ARIA role
    parent_tag: Optional[str] = None
    nearest_heading: Optional[str] = None  # closest h1-h6 ancestor text

    # Tooltip / title attribute text (often carries instructional content)
    title: Optional[str] = None

    # Closest lang= attribute value (element's own or nearest ancestor)
    lang: Optional[str] = None

    # Raw markup (truncated)
    html: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────


class AsyncSensoryCrawler:
    """
    Crawl one URL (depth=0 by default) and extract every text-bearing
    element needed for WCAG 1.3.3 sensory-characteristics auditing.
    """

    # Tags that typically carry user-facing instructional text
    TARGET_SELECTOR = (
        "p, li, label, legend, button, input, textarea, select, option, "
        "a, caption, th, td, "
        "span, div, h1, h2, h3, h4, h5, h6, "
        "summary, figcaption, dt, dd"
    )

    EXTRACT_JS = r"""() => {
        function outerHTML(el, max) {
            return (el && el.outerHTML) ? el.outerHTML.slice(0, max || 500) : '';
        }

        function nearestHeading(el) {
            // Walk up the DOM looking for an h1-h6 ancestor
            let cur = el.parentElement;
            while (cur && cur !== document.body) {
                if (/^H[1-6]$/.test(cur.tagName)) {
                    return (cur.innerText || '').trim().slice(0, 200);
                }
                cur = cur.parentElement;
            }
            // Fallback: previous sibling heading
            let prev = el.previousElementSibling;
            while (prev) {
                if (/^H[1-6]$/.test(prev.tagName)) {
                    return (prev.innerText || '').trim().slice(0, 200);
                }
                prev = prev.previousElementSibling;
            }
            // Fallback: next sibling heading (element appears before its section header)
            let next = el.nextElementSibling;
            while (next) {
                if (/^H[1-6]$/.test(next.tagName)) {
                    return (next.innerText || '').trim().slice(0, 200);
                }
                next = next.nextElementSibling;
            }
            return null;
        }

        // True when text has >=15% CJK characters (Japanese / Chinese / Korean).
        // CJK characters carry more semantic weight per character than Latin letters,
        // so the minimum-length filter is lowered to 1 for CJK content.
        function isCJK(text) {
            if (!text) return false;
            const cjk = (text.match(/[\u3000-\u9fff\uff00-\uffef\u3400-\u4dbf]/g) || []).length;
            return cjk / Math.max(text.length, 1) >= 0.15;
        }

        // Length of text in DIRECT TEXT_NODE children only, ignoring descendant
        // elements.  Used to decide whether a div/span has its own meaningful text
        // beyond what its block-level children already contribute.
        function directTextLength(el) {
            let len = 0;
            for (const node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) {
                    len += (node.textContent || '').trim().length;
                }
            }
            return len;
        }

        // Walk up to the nearest ancestor with a lang= attribute; fall back to
        // the documentElement lang.
        function elementLang(el) {
            let cur = el;
            while (cur && cur !== document.documentElement) {
                const l = cur.getAttribute && cur.getAttribute('lang');
                if (l) return l;
                cur = cur.parentElement;
            }
            return document.documentElement.getAttribute('lang') || null;
        }

        const SELECTOR = (
            "p, li, label, legend, button, input, textarea, select, option, " +
            "a, caption, th, td, " +
            "span, div, h1, h2, h3, h4, h5, h6, " +
            "summary, figcaption, dt, dd"
        );
        const elements = Array.from(document.querySelectorAll(SELECTOR));
        const results  = [];

        for (const el of elements) {
            // Collect all text sources for this element
            const ariaLabel   = (el.getAttribute('aria-label') || '').trim();
            const placeholder = (el.getAttribute('placeholder') || '').trim();
            const titleAttr   = (el.getAttribute('title') || '').trim();
            const value       = ((el.value != null ? el.value : el.getAttribute('value')) || '').trim();
            const rawText     = (el.innerText || el.textContent || '').trim();

            // Skip hidden inputs entirely
            if (el.tagName === 'INPUT' && (el.getAttribute('type') || '').toLowerCase() === 'hidden') {
                continue;
            }

            // Skip elements with no content at all
            if (!rawText && !ariaLabel && !placeholder && !value && !titleAttr) continue;

            // Minimum text length:
            //   - CJK: 1 character (single kanji / hanzi is meaningful)
            //   - Others: 3 characters (avoids noise like "x", "ok")
            const minLen = (rawText && isCJK(rawText)) ? 1 : 3;
            if (rawText && rawText.length < minLen && !ariaLabel && !placeholder && !value && !titleAttr) continue;

            // For divs/spans: skip when they contain block-level children that
            // are captured separately AND they have no meaningful direct text of
            // their own (prevents massive duplication while retaining wrappers
            // that carry genuine inline instructions).
            if (el.tagName === 'DIV' || el.tagName === 'SPAN') {
                const hasBlockChild = Array.from(el.children).some(c =>
                    /^(P|LI|LABEL|LEGEND|BUTTON|H[1-6]|TABLE|UL|OL)$/.test(c.tagName)
                );
                if (hasBlockChild && directTextLength(el) < 5) continue;
            }

            // Skip visually hidden elements (but NOT aria-hidden — those can still
            // show sensory-only instructions to sighted users)
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

            results.push({
                tag:             el.tagName.toLowerCase(),
                element_id:      el.id        || null,
                element_class:   el.className || null,
                text:            rawText.slice(0, 500),
                aria_label:      el.getAttribute('aria-label')       || null,
                aria_labelledby: el.getAttribute('aria-labelledby')  || null,
                placeholder:     el.getAttribute('placeholder')      || null,
                value:           value || null,
                title:           titleAttr || null,
                lang:            elementLang(el),
                role:            el.getAttribute('role')             || null,
                parent_tag:      el.parentElement ? el.parentElement.tagName.toLowerCase() : null,
                nearest_heading: nearestHeading(el),
                html:            outerHTML(el, 500),
            });
        }

        return results;
    }"""

    def __init__(self, base_url: str, output_dir: str, max_depth: int = 0):
        self.base_url   = base_url
        self.output_dir = Path(output_dir)
        self.max_depth  = max_depth
        self.results: List[SensoryElementData] = []
        self.visited: set = set()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def crawl(self) -> List[SensoryElementData]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            await install_ssrf_guard(context)
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
                await page.goto(url, wait_until="commit", timeout=15_000)
            await page.wait_for_timeout(1500)

            raw: list = await page.evaluate(self.EXTRACT_JS)
            for item in raw:
                self.results.append(SensoryElementData(page_url=url, **item))

            # Follow same-origin links for deeper crawls
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
            print(f"[SensoryCrawler] Error on {url}: {exc}")
        finally:
            await page.close()

    def save_raw_json(self) -> str:
        path = self.output_dir / "sensory_raw.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump([r.model_dump() for r in self.results], f, indent=2)
        return str(path)
