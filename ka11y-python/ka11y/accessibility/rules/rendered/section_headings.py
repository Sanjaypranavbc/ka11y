import asyncio
import json
import re
from datetime import datetime
from urllib.parse import urlparse
from dataclasses import dataclass, field, asdict
from typing import Optional
from playwright.async_api import Page
from ka11y.crawler.navigation import navigate_with_resilience
from ka11y.crawler.browser_pool import leased_context
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="section_headings")

@dataclass
class SectionResult:
    url: str
    section_index: int
    tag: str
    role: Optional[str]
    verdict: str
    reason: str
    heading_tag: Optional[str]
    heading_text: Optional[str]
    aria_label: Optional[str]
    aria_labelledby: Optional[str]
    content_length: int
    outer_html_snippet: str
    path_selector: str

@dataclass
class PageReport:
    url: str
    timestamp: str
    title: str
    sections_found: int
    pass_count: int
    needs_review_count: int
    fail_count: int
    results: list[SectionResult] = field(default_factory=list)

EVALUATE_SCRIPT = """
() => {
    function getPath(el) {
        const parts = [];
        let cur = el;
        while (cur && cur !== document.body) {
            let part = cur.tagName.toLowerCase();
            const id = cur.id;
            const role = cur.getAttribute('role');
            if (id) part += '#' + id;
            else if (role) part += '[role=' + role + ']';
            else {
                const siblings = Array.from(cur.parentElement?.children || [])
                    .filter(s => s.tagName === cur.tagName);
                if (siblings.length > 1) {
                    part += ':nth-of-type(' + (siblings.indexOf(cur) + 1) + ')';
                }
            }
            parts.unshift(part);
            cur = cur.parentElement;
        }
        return parts.join(' > ');
    }

    function getVisibleText(el) {
        const clone = el.cloneNode(true);
        clone.querySelectorAll('script,style,noscript').forEach(n => n.remove());
        return (clone.innerText || clone.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function isHiddenFromAT(el) {
        if (el.getAttribute('aria-hidden') === 'true') return true;
        const style = window.getComputedStyle(el);
        return style.display === 'none' || style.visibility === 'hidden';
    }

    function headingLooksVague(text) {
        if (!text) return true;
        const t = text.trim().toLowerCase();
        const vague = ['section','content','main','info','details','more','page',
                       'area','block','panel','widget','module','item','untitled',''];
        return vague.includes(t) || t.length < 3;
    }

    function hasStyledFakeHeading(el) {
        const candidates = el.querySelectorAll(':scope > div, :scope > span, :scope > p');
        for (const c of candidates) {
            const style = window.getComputedStyle(c);
            const fontSize = parseFloat(style.fontSize);
            const fontWeight = parseInt(style.fontWeight);
            if (fontWeight >= 600 && fontSize >= 16) return true;
        }
        return false;
    }

    function isTrivial(visibleText, el) {
        if (visibleText.length < 80) {
            const complexTags = el.querySelectorAll('table, ul, ol, dl, form, figure');
            return complexTags.length === 0;
        }
        return false;
    }

    const SECTION_SELECTORS = [
        'section', 'article', 'main',
        '[role="region"]', '[role="main"]', '[role="article"]',
        '[role="complementary"]', '[role="form"]',
    ];

    const EXEMPT_ROLES = new Set([
        'navigation', 'complementary', 'banner', 'contentinfo',
        'search', 'presentation', 'none'
    ]);
    const EXEMPT_TAGS = new Set(['nav', 'header', 'footer', 'aside']);

    const allSections = new Set();
    for (const sel of SECTION_SELECTORS) {
        document.querySelectorAll(sel).forEach(el => allSections.add(el));
    }

    const results = [];
    let idx = 0;

    for (const el of allSections) {
        if (isHiddenFromAT(el)) continue;

        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || null;
        const ariaLabel = el.getAttribute('aria-label') || null;
        const ariaLabelledBy = el.getAttribute('aria-labelledby') || null;
        const visibleText = getVisibleText(el);
        const contentLength = visibleText.length;
        const outerSnippet = (el.outerHTML || '').substring(0, 200);
        const pathSelector = getPath(el);

        let verdict = '';
        let reason = '';
        let headingTag = null;
        let headingText = null;

        // ── 1. Exemption check ──────────────────────────────────────────────
        if (EXEMPT_TAGS.has(tag) || (role && EXEMPT_ROLES.has(role))) {
            verdict = 'PASS';
            reason = 'Exempt element (navigation / banner / contentinfo / etc.)';
            results.push({ idx, tag, role, verdict, reason, headingTag, headingText,
                           ariaLabel, ariaLabelledBy, contentLength, outerSnippet, pathSelector });
            idx++; continue;
        }

        // ── 2. Look for a direct semantic heading (h1-h6) ───────────────────
        const directHeading = el.querySelector(
            ':scope > h1,:scope > h2,:scope > h3,:scope > h4,:scope > h5,:scope > h6'
        );

        if (directHeading) {
            headingTag  = directHeading.tagName.toLowerCase();
            headingText = (directHeading.innerText || directHeading.textContent || '').trim();

            if (headingLooksVague(headingText)) {
                verdict = 'NEEDS_REVIEW';
                reason  = 'Heading exists but text is vague or too short: "' + headingText + '"';
            } else {
                verdict = 'PASS';
                reason  = 'Semantic heading found: <' + headingTag + '> "' + headingText + '"';
            }
            results.push({ idx, tag, role, verdict, reason, headingTag, headingText,
                           ariaLabel, ariaLabelledBy, contentLength, outerSnippet, pathSelector });
            idx++; continue;
        }

        // ── 3. aria-labelledby pointing to something ─────────────────────────
        if (ariaLabelledBy) {
            const target = document.getElementById(ariaLabelledBy);
            const targetText = target ? (target.innerText || target.textContent || '').trim() : null;
            const targetTag  = target ? target.tagName.toLowerCase() : null;

            if (target && /^h[1-6]$/.test(targetTag)) {
                headingTag  = targetTag;
                headingText = targetText;
                if (headingLooksVague(headingText)) {
                    verdict = 'NEEDS_REVIEW';
                    reason  = 'aria-labelledby points to heading but text is vague: "' + headingText + '"';
                } else {
                    verdict = 'PASS';
                    reason  = 'aria-labelledby → <' + targetTag + '> "' + headingText + '"';
                }
            } else {
                verdict = 'NEEDS_REVIEW';
                reason  = 'aria-labelledby present but target is not a heading element (' + (targetTag || 'not found') + ')';
                headingText = targetText;
            }
            results.push({ idx, tag, role, verdict, reason, headingTag, headingText,
                           ariaLabel, ariaLabelledBy, contentLength, outerSnippet, pathSelector });
            idx++; continue;
        }

        // ── 4. aria-label only ───────────────────────────────────────────────
        if (ariaLabel) {
            if (headingLooksVague(ariaLabel)) {
                verdict = 'NEEDS_REVIEW';
                reason  = 'Only aria-label found and it is vague: "' + ariaLabel + '"';
            } else {
                verdict = 'NEEDS_REVIEW';
                reason  = 'Region labelled via aria-label only (not a heading): "' + ariaLabel + '"';
            }
            results.push({ idx, tag, role, verdict, reason, headingTag, headingText,
                           ariaLabel, ariaLabelledBy, contentLength, outerSnippet, pathSelector });
            idx++; continue;
        }

        // ── 5. No heading of any kind — assess severity ──────────────────────
        if (isTrivial(visibleText, el)) {
            verdict = 'PASS';
            reason  = 'Section has minimal content — heading not required';
        } else if (hasStyledFakeHeading(el)) {
            verdict = 'FAIL';
            reason  = 'Section has significant content and a visually styled (non-semantic) heading. Use h1–h6.';
        } else {
            verdict = 'FAIL';
            reason  = 'Section has significant content (' + contentLength + ' chars) with no heading of any kind.';
        }

        results.push({ idx, tag, role, verdict, reason, headingTag, headingText,
                       ariaLabel, ariaLabelledBy, contentLength, outerSnippet, pathSelector });
        idx++;
    }

    return { title: document.title, results };
}
"""

async def check_page(page: Page, url: str) -> PageReport:
    await navigate_with_resilience(page, url)
    await page.wait_for_timeout(800)

    raw = await page.evaluate(EVALUATE_SCRIPT)
    title = raw.get("title", "")
    raw_results = raw.get("results", [])

    section_results: list[SectionResult] = []
    pass_count = needs_count = fail_count = 0

    for r in raw_results:
        sr = SectionResult(
            url=url,
            section_index=r["idx"],
            tag=r["tag"],
            role=r.get("role"),
            verdict=r["verdict"],
            reason=r["reason"],
            heading_tag=r.get("headingTag"),
            heading_text=r.get("headingText"),
            aria_label=r.get("ariaLabel"),
            aria_labelledby=r.get("ariaLabelledBy"),
            content_length=r.get("contentLength", 0),
            outer_html_snippet=r.get("outerSnippet", ""),
            path_selector=r.get("pathSelector", ""),
        )
        section_results.append(sr)

        if sr.verdict == "PASS":
            pass_count += 1
        elif sr.verdict == "NEEDS_REVIEW":
            needs_count += 1
        else:
            fail_count += 1

    return PageReport(
        url=url,
        timestamp=datetime.now().isoformat(),
        title=title,
        sections_found=len(section_results),
        pass_count=pass_count,
        needs_review_count=needs_count,
        fail_count=fail_count,
        results=section_results,
    )

async def analyze_wcag_2410(start_url, max_pages: int = 5) -> dict:
    origin = urlparse(start_url).netloc
    visited: set[str] = set()
    queue = [start_url]
    reports: list[PageReport] = []

    async with leased_context(
        viewport={
            "width": 1400,
            "height": 900
        }
    ) as context:
        page = await context.new_page()
        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                report = await check_page(page, url)
                reports.append(report)

                # Collect same-origin links for crawling
                if len(visited) < max_pages:
                    links = await page.eval_on_selector_all(
                        "a[href]",
                        "els => els.map(e => e.href)"
                    )
                    for link in links:
                        parsed = urlparse(link)
                        if (parsed.netloc == origin
                                and link not in visited
                                and link not in queue
                                and parsed.scheme in ("http", "https")
                                and not parsed.fragment
                                and not link.endswith((".pdf", ".jpg", ".png", ".svg"))):
                            queue.append(link)
            except Exception as e:
                logger.error(f"Error checking page {url}: {e}")

    # Format findings in system-wide JSON format
    overall_verdict = "PASS"
    all_results = []
    
    total_pass = total_needs = total_fail = 0
    for rep in reports:
        total_pass += rep.pass_count
        total_needs += rep.needs_review_count
        total_fail += rep.fail_count
        for r in rep.results:
            all_results.append(asdict(r))

    if total_fail > 0:
        overall_verdict = "FAIL"
    elif total_needs > 0:
        overall_verdict = "NEEDS_REVIEW"

    return {
        "status": overall_verdict,
        "reason": "Section headings correctly validate under WCAG 2.4.10" if overall_verdict == "PASS" else "Sections discovered with visual non-semantic headings or missing headings entirely.",
        "details": {
            "summary": {
                "pages_crawled": len(reports),
                "pass_count": total_pass,
                "needs_review_count": total_needs,
                "fail_count": total_fail
            },
            "findings": all_results
        }
    }
