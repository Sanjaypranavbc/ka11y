import asyncio
import os
import re
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from ka11y.crawler.navigation import navigate_with_resilience
from ka11y.crawler.browser_pool import leased_context
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="consistent_nav")

MAX_PAGES = 6

EXCLUDED_KEYWORDS = [
    "login",
    "signin",
    "auth",
    "checkout",
    "cart",
    "payment"
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

def normalize_url(url):
    parsed = urlparse(url)
    cleaned = parsed._replace(
        query="",
        fragment=""
    )
    normalized = urlunparse(cleaned)
    if normalized.endswith("/") and len(normalized) > 8:
        normalized = normalized.rstrip("/")
    return normalized

def is_excluded(url):
    lower = url.lower()
    for keyword in EXCLUDED_KEYWORDS:
        if keyword in lower:
            return True
    return False

def get_accessible_name(link):
    text = link.get_text(" ", strip=True)
    if text:
        return text
    aria = link.get("aria-label")
    if aria:
        return aria.strip()
    title = link.get("title")
    if title:
        return title.strip()
    img = link.find("img")
    if img and img.get("alt"):
        return img["alt"].strip()
    svg_title = link.find("title")
    if svg_title:
        return svg_title.get_text(strip=True)
    return None

def extract_navigation(html):
    soup = BeautifulSoup(html, "lxml")
    nav_elements = []

    # Standard nav landmarks
    nav_elements.extend(
        soup.find_all("nav")
    )
    nav_elements.extend(
        soup.select('[role="navigation"]')
    )
    # Header fallback
    nav_elements.extend(
        soup.find_all("header")
    )

    # Common navigation classes
    common_classes = [
        "menu",
        "navbar",
        "navigation",
        "nav",
        "header-menu",
        "main-menu",
        "primary-menu"
    ]

    for class_name in common_classes:
        found = soup.find_all(
            class_=lambda x:
            x and class_name.lower() in str(x).lower()
        )
        nav_elements.extend(found)

    # Remove duplicates
    unique_navs = []
    seen = set()

    for nav in nav_elements:
        identifier = str(nav)[:1000]
        if identifier not in seen:
            seen.add(identifier)
            unique_navs.append(nav)

    navigation_data = []

    for nav in unique_navs:
        links = nav.find_all("a")
        items = []
        for link in links:
            accessible_name = get_accessible_name(link)
            if accessible_name:
                cleaned = accessible_name.strip()
                if (
                    cleaned
                    and cleaned not in items
                    and len(cleaned) <= 60
                ):
                    items.append(cleaned)

        # only meaningful nav menus
        if len(items) >= 3:
            navigation_data.append({
                "nav_name": "unnamed-navigation",
                "items": items
            })

    return navigation_data

def discover_links(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc
    urls = []
    normalized_base = normalize_url(base_url)
    urls.append(normalized_base)

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if href.startswith("#"):
            continue
        full_url = urljoin(base_url, href)
        normalized = normalize_url(full_url)
        parsed = urlparse(normalized)

        # Same domain only
        if parsed.netloc != domain:
            continue
        # Excluded pages
        if is_excluded(normalized):
            continue
        # Skip files
        if any(
            normalized.lower().endswith(ext)
            for ext in [
                ".pdf",
                ".jpg",
                ".jpeg",
                ".png",
                ".svg",
                ".zip",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx"
            ]
        ):
            continue

        if normalized not in urls:
            urls.append(normalized)

    return urls[:MAX_PAGES]

def relative_order_match(nav1, nav2):
    common_items = []
    for item in nav1:
        if item in nav2:
            common_items.append(item)

    seq1 = [x for x in nav1 if x in common_items]
    seq2 = [x for x in nav2 if x in common_items]
    return seq1 == seq2, seq1, seq2

async def fetch_page(context, url):
    page = await context.new_page()
    try:
        await navigate_with_resilience(page, url)
        # Wait for JS rendering
        await page.wait_for_timeout(4000)
        html = await page.content()
        return html
    except Exception as e:
        logger.error(f"Error fetching page {url}: {e}")
        return None
    finally:
        await page.close()

async def analyze_wcag_323(start_url) -> dict:
    """
    Main orchestrator for WCAG 3.2.3. Runs inside leased context.
    Returns a structured findings dict instead of stdout prints.
    """
    findings = []
    all_navigation = {}

    async with leased_context(
        viewport={
            "width": 1400,
            "height": 900
        }
    ) as context:
        start_html = await fetch_page(context, start_url)
        if not start_html:
            return {
                "status": "NEEDS_REVIEW",
                "reason": "Unable to fetch start page to discover links.",
                "details": {}
            }

        urls = discover_links(start_html, start_url)
        for url in urls:
            html = await fetch_page(context, url)
            if not html:
                continue
            navs = extract_navigation(html)
            if navs:
                all_navigation[url] = navs

    if len(all_navigation) < 2:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "Less than 2 pages with extractable navigation to perform comparison.",
            "details": {}
        }

    overall_pass = True
    ordered_urls = list(all_navigation.keys())
    comparisons = []

    for i in range(len(ordered_urls) - 1):
        url1 = ordered_urls[i]
        url2 = ordered_urls[i + 1]
        navs1 = all_navigation[url1]
        navs2 = all_navigation[url2]

        comparison_found = False
        for nav1 in navs1:
            for nav2 in navs2:
                result, seq1, seq2 = relative_order_match(
                    nav1["items"],
                    nav2["items"]
                )
                # meaningful repeated navigation
                if len(seq1) >= 3:
                    comparison_found = True
                    comparisons.append({
                        "url1": url1,
                        "url2": url2,
                        "seq1": seq1,
                        "seq2": seq2,
                        "pass": result
                    })
                    if not result:
                        overall_pass = False
                    break
            if comparison_found:
                break

    if not comparisons:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "No matching repeated navigation menus (3+ common items) found between pages.",
            "details": {}
        }

    return {
        "status": "PASS" if overall_pass else "FAIL",
        "reason": "Repeated navigation mechanisms maintain consistent relative order." if overall_pass else "Repeated navigation order changes between pages.",
        "details": {
            "urls_checked": ordered_urls,
            "comparisons": comparisons
        }
    }
