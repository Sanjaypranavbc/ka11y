"""
ka11y/accessibility/rendered/snapshot_collector.py
===================================================
Collects a structured PageSnapshot from a Playwright Page.

The collector runs a single JS evaluation that captures:
- Document / body scroll dimensions
- A list of element-level records (rect, styles, identifiers)

Only elements likely to be relevant to the rules being checked are
extracted (text containers, interactive elements, fixed/sticky layers).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from playwright.async_api import Page

from .models import ElementSnapshot, PageSnapshot, Rect
from .geometry import rect_from_dict

# Maximum number of elements to capture per snapshot (perf guard)
_MAX_ELEMENTS = 500

_COLLECT_JS = """
(maxElements) => {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const docScrollW = Math.max(
        document.body ? document.body.scrollWidth : 0,
        document.documentElement.scrollWidth
    );
    const docScrollH = Math.max(
        document.body ? document.body.scrollHeight : 0,
        document.documentElement.scrollHeight
    );
    const bodyScrollW = document.body ? document.body.scrollWidth : 0;
    const bodyScrollH = document.body ? document.body.scrollHeight : 0;

    // Selector for relevant elements
    const candidates = document.querySelectorAll(
        'p, span, h1, h2, h3, h4, h5, h6, li, td, th, label, ' +
        'a, button, input, select, textarea, ' +
        '[role], nav, header, footer, main, section, article, aside, ' +
        'div[class], [style]'
    );

    const results = [];
    let count = 0;

    for (const el of candidates) {
        if (count >= maxElements) break;

        const rect = el.getBoundingClientRect();
        // Skip zero-size elements
        if (rect.width === 0 && rect.height === 0) continue;

        const cs = window.getComputedStyle(el);

        const overflowX = cs.overflowX || 'visible';
        const overflowY = cs.overflowY || 'visible';
        const position = cs.position || 'static';
        const display = cs.display || '';
        const visibility = cs.visibility || 'visible';
        const opacity = parseFloat(cs.opacity) || 1.0;
        const zIndex = parseInt(cs.zIndex) || 0;
        const fontSize = cs.fontSize || '';
        const lineHeight = cs.lineHeight || '';

        const isFixedOrSticky = position === 'fixed' || position === 'sticky';
        const isFocusable = (
            el.tabIndex >= 0 ||
            ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)
        );

        const textClipped = (
            (overflowX === 'hidden' || overflowX === 'clip') &&
            el.scrollWidth > el.clientWidth + 2
        ) || (
            (overflowY === 'hidden' || overflowY === 'clip') &&
            el.scrollHeight > el.clientHeight + 2
        );

        // Safe HTML snippet (truncated)
        let html = '';
        try { html = el.outerHTML.slice(0, 300); } catch(e) {}

        // Safe text
        let text = '';
        try { text = (el.textContent || '').trim().slice(0, 200); } catch(e) {}

        results.push({
            element_id: el.id || null,
            selector: el.tagName.toLowerCase() +
                      (el.id ? '#' + el.id : '') +
                      (el.className && typeof el.className === 'string'
                        ? '.' + el.className.trim().split(/\\s+/).join('.').slice(0, 80)
                        : ''),
            tag: el.tagName.toLowerCase(),
            text: text,
            html_snippet: html,
            rect: {
                x: rect.x, y: rect.y,
                width: rect.width, height: rect.height,
                top: rect.top, right: rect.right,
                bottom: rect.bottom, left: rect.left
            },
            client_width: el.clientWidth,
            client_height: el.clientHeight,
            scroll_width: el.scrollWidth,
            scroll_height: el.scrollHeight,
            overflow_x: overflowX,
            overflow_y: overflowY,
            position: position,
            display: display,
            visibility: visibility,
            opacity: opacity,
            z_index: zIndex,
            font_size: fontSize,
            line_height: lineHeight,
            visible: display !== 'none' && visibility !== 'hidden' && opacity > 0,
            focusable: isFocusable,
            fixed_or_sticky: isFixedOrSticky,
            text_clipped: textClipped,
        });
        count++;
    }

    return {
        viewport_width: vw,
        viewport_height: vh,
        document_scroll_width: docScrollW,
        document_scroll_height: docScrollH,
        body_scroll_width: bodyScrollW,
        body_scroll_height: bodyScrollH,
        has_horizontal_scroll: docScrollW > vw + 5,
        elements: results,
    };
}
"""


async def collect_snapshot(
    page: Page,
    scenario: str,
    page_url: str,
    max_elements: int = _MAX_ELEMENTS,
) -> PageSnapshot:
    """
    Capture a full PageSnapshot from a live Playwright page.
    Tolerates JS errors gracefully.
    """
    try:
        raw = await page.evaluate(_COLLECT_JS, max_elements)
    except Exception as exc:
        return PageSnapshot(
            scenario=scenario,
            page_url=page_url,
            viewport_width=1280,
            viewport_height=720,
            raw={"error": str(exc)},
        )

    elements: List[ElementSnapshot] = []
    for item in raw.get("elements", []):
        rect_d = item.get("rect", {})
        elements.append(
            ElementSnapshot(
                element_id=item.get("element_id"),
                selector=item.get("selector", ""),
                tag=item.get("tag", ""),
                text=item.get("text", ""),
                html_snippet=item.get("html_snippet", ""),
                rect=rect_from_dict(rect_d),
                client_width=float(item.get("client_width", 0)),
                client_height=float(item.get("client_height", 0)),
                scroll_width=float(item.get("scroll_width", 0)),
                scroll_height=float(item.get("scroll_height", 0)),
                overflow_x=item.get("overflow_x", "visible"),
                overflow_y=item.get("overflow_y", "visible"),
                position=item.get("position", "static"),
                display=item.get("display", ""),
                visibility=item.get("visibility", "visible"),
                opacity=float(item.get("opacity", 1.0)),
                z_index=int(item.get("z_index", 0)),
                font_size=item.get("font_size", ""),
                line_height=item.get("line_height", ""),
                visible=bool(item.get("visible", True)),
                focusable=bool(item.get("focusable", False)),
                fixed_or_sticky=bool(item.get("fixed_or_sticky", False)),
                text_clipped=bool(item.get("text_clipped", False)),
                page_url=page_url,
            )
        )

    vw = int(raw.get("viewport_width", 1280))
    vh = int(raw.get("viewport_height", 720))
    return PageSnapshot(
        scenario=scenario,
        page_url=page_url,
        viewport_width=vw,
        viewport_height=vh,
        document_scroll_width=float(raw.get("document_scroll_width", 0)),
        document_scroll_height=float(raw.get("document_scroll_height", 0)),
        body_scroll_width=float(raw.get("body_scroll_width", 0)),
        body_scroll_height=float(raw.get("body_scroll_height", 0)),
        has_horizontal_scroll=bool(raw.get("has_horizontal_scroll", False)),
        elements=elements,
        raw=raw,
    )