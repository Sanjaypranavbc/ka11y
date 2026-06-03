import asyncio
import json
import re
import unicodedata
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urlunparse
from a11y.crawler.navigation import navigate_with_resilience
from a11y.crawler.browser_pool import leased_context
from a11y.config.logger import setup_logger

logger = setup_logger(name="AC", tag="consistent_id")

MAX_PAGES = 10
MIN_REPEAT_PAGES = 2

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

SKIP_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".pdf",
    ".zip",
    ".rar",
    ".mp4",
    ".mp3",
    ".webm",
    ".css",
    ".js",
    ".xml",
    ".json"
}

def normalize(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[\s\u3000]+", " ", text)
    return text.strip().lower()

def clean_label(label):
    label = normalize(label)
    prefixes = [
        "click ",
        "click to ",
        "tap ",
        "tap to ",
        "go to ",
        "navigate to "
    ]
    for prefix in prefixes:
        if label.startswith(prefix):
            label = label[len(prefix):]
    return normalize(label)

def detect_function(label):
    label = normalize(label)
    if not label:
        return None

    # =====================================================
    # SEARCH
    # =====================================================
    search_patterns = [
        r"\bsearch\b",
        r"\bfind\b",
        r"\blookup\b",
        r"検索"
    ]
    for pattern in search_patterns:
        if re.search(pattern, label):
            return "search"

    # =====================================================
    # LOGIN
    # =====================================================
    login_exact = {
        "login",
        "log in",
        "sign in",
        "signin",
        "member login",
        "customer login",
        "ログイン"
    }
    if label in login_exact:
        return "login"

    # =====================================================
    # LOGOUT
    # =====================================================
    logout_exact = {
        "logout",
        "log out",
        "sign out",
        "signout",
        "ログアウト"
    }
    if label in logout_exact:
        return "logout"

    # =====================================================
    # REGISTER
    # =====================================================
    register_exact = {
        "register",
        "registration",
        "sign up",
        "signup",
        "create account",
        "create an account",
        "join"
    }
    if label in register_exact:
        return "register"

    # =====================================================
    # CONTACT
    # =====================================================
    contact_exact = {
        "contact",
        "contact us",
        "get in touch",
        "reach us"
    }
    if label in contact_exact:
        return "contact"

    # =====================================================
    # SUBMIT
    # =====================================================
    submit_exact = {
        "submit",
        "send",
        "send message",
        "submit form"
    }
    if label in submit_exact:
        return "submit"

    # =====================================================
    # CART
    # =====================================================
    cart_exact = {
        "cart",
        "shopping cart",
        "basket",
        "view cart"
    }
    if label in cart_exact:
        return "cart"

    # =====================================================
    # PRINT
    # =====================================================
    print_exact = {
        "print",
        "print page",
        "print this page"
    }
    if label in print_exact:
        return "print"

    return None

def normalize_url(url):
    parsed = urlparse(url)
    cleaned = parsed._replace(
        fragment="",
        query=""
    )
    normalized = urlunparse(cleaned)
    if (
        normalized.endswith("/")
        and len(normalized) > 8
    ):
        normalized = normalized.rstrip("/")
    return normalized

async def extract(page, url, collected):
    try:
        data = await page.evaluate("""
        () => {
            function isVisible(el) {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) {
                    return false;
                }
                if (
                    style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    style.opacity === '0'
                ) {
                    return false;
                }
                if (el.getAttribute('aria-hidden') === 'true') {
                    return false;
                }
                return true;
            }

            function getText(el) {
                return (el.innerText || el.textContent || '').trim();
            }

            function accessibleName(el) {
                // aria-labelledby
                const labelledby = el.getAttribute('aria-labelledby');
                if (labelledby) {
                    const ids = labelledby.split(/\\s+/);
                    const txt = ids.map(id => {
                        const ref = document.getElementById(id);
                        return ref ? getText(ref) : '';
                    }).join(' ').trim();
                    if (txt) return txt;
                }

                // label[for]
                if (el.id) {
                    const lbl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
                    if (lbl) {
                        const txt = getText(lbl);
                        if (txt) return txt;
                    }
                }

                // wrapped label
                const wrapper = el.closest('label');
                if (wrapper) {
                    const txt = getText(wrapper);
                    if (txt) return txt;
                }

                // aria-label
                const aria = el.getAttribute('aria-label');
                if (aria && aria.trim()) return aria.trim();

                // title
                const title = el.getAttribute('title');
                if (title && title.trim()) return title.trim();

                // alt
                const alt = el.getAttribute('alt');
                if (alt && alt.trim()) return alt.trim();

                // SVG title
                const svgTitle = el.querySelector('title');
                if (svgTitle) {
                    const txt = getText(svgTitle);
                    if (txt) return txt;
                }

                // input value
                if (el.tagName.toLowerCase() === 'input') {
                    const type = (el.type || '').toLowerCase();
                    if (['submit', 'button', 'reset'].includes(type)) {
                        if (el.value && el.value.trim()) return el.value.trim();
                    }
                }

                // placeholder fallback
                if (el.tagName.toLowerCase() === 'input') {
                    const type = (el.type || '').toLowerCase();
                    if (['search', 'text'].includes(type)) {
                        const ph = el.getAttribute('placeholder');
                        if (ph && ph.trim()) return ph.trim();
                    }
                }

                return getText(el);
            }

            function region(el) {
                const header = el.closest('header,[role="banner"]');
                if (header) return 'header';
                const footer = el.closest('footer,[role="contentinfo"]');
                if (footer) return 'footer';
                const nav = el.closest('nav,[role="navigation"]');
                if (nav) return 'navigation';
                const main = el.closest('main,[role="main"]');
                if (main) return 'main';
                return 'unknown';
            }

            const selector = ['button', 'a[href]', 'input', '[role="button"]', '[role="link"]'].join(',');
            return Array.from(document.querySelectorAll(selector))
                .filter(isVisible)
                .map(el => ({
                    label: accessibleName(el),
                    region: region(el),
                    role: (el.getAttribute('role') || el.tagName).toLowerCase()
                }));
        }
        """)

        seen = set()
        for item in data:
            raw = normalize(item["label"])
            if not raw:
                continue
            label = clean_label(raw)
            if not label:
                continue
            if len(label) > 60:
                continue
            if label in {"read more", "learn more", "more", "details", "view", "explore"}:
                continue

            func = detect_function(label)
            if not func:
                continue

            region = item["region"]
            key = (func, label, region)
            if key in seen:
                continue
            seen.add(key)
            collected.append({
                "function": func,
                "label": label,
                "region": region,
                "url": url
            })
    except Exception as e:
        logger.error(f"Extract error on {url}: {e}")

async def get_links(page, base_url):
    domain = urlparse(base_url).netloc
    try:
        hrefs = await page.evaluate("() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)")
    except Exception:
        return []

    links = []
    seen = set()
    for href in hrefs:
        if not href:
            continue
        full = urljoin(base_url, href)
        normalized = normalize_url(full)
        parsed = urlparse(normalized)
        if parsed.netloc != domain:
            continue
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            continue
        if normalized not in seen:
            seen.add(normalized)
            links.append(normalized)
    return links

async def crawl(start_url) -> list:
    visited = set()
    queue = [start_url]
    collected = []

    async with leased_context(
        viewport={
            "width": 1400,
            "height": 900
        }
    ) as context:
        page = await context.new_page()
        while queue and len(visited) < MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                await navigate_with_resilience(page, url)
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Navigation error on {url}: {e}")
                continue

            await extract(page, url, collected)
            links = await get_links(page, url)
            for link in links:
                if link not in visited and link not in queue:
                    queue.append(link)

    return collected

def analyze(collected) -> dict:
    if not collected:
        return {
            "status": "FAIL",
            "reason": "No repeated identifiable components found.",
            "details": {}
        }

    groups = defaultdict(lambda: defaultdict(list))
    for item in collected:
        func = item["function"]
        label = item["label"]
        region = item["region"]
        url = item["url"]

        group_key = (func, region)
        if url not in groups[group_key][label]:
            groups[group_key][label].append(url)

    failures = {}
    summary = {}

    for group_key, label_map in groups.items():
        func, region = group_key
        all_pages = set()
        for urls in label_map.values():
            all_pages.update(urls)

        # repeated only
        if len(all_pages) < MIN_REPEAT_PAGES:
            continue

        key_name = f"{func} ({region})"
        summary[key_name] = list(label_map.keys())

        # inconsistent labels
        if len(label_map) > 1:
            failures[key_name] = {lbl: urls for lbl, urls in label_map.items()}

    if failures:
        return {
            "status": "FAIL",
            "reason": "Different labels used for same function in identical regions.",
            "details": failures
        }

    return {
        "status": "PASS",
        "reason": "Repeated components are identified consistently across pages.",
        "details": summary
    }

async def analyze_wcag_324(start_url) -> dict:
    collected = await crawl(start_url)
    return analyze(collected)
