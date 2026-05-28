import os
import json
import csv
import hashlib
import asyncio
from collections import deque
from urllib.parse import urljoin, urlparse

from ka11y.crawler.navigation import navigate_with_resilience
from ka11y.crawler.cookie_handler import handle_cookies
from ka11y.crawler.policy import CrawlPolicy
from pathlib import Path
from typing import List, Optional, Set, Tuple
from pydantic import BaseModel, Field
from datetime import datetime
import time
import aiohttp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
)
from rich import box

from ka11y.crawler.models import ImageData, ImageMetadata
from ka11y.config.logger import setup_logger
from ka11y.classifier.classifier import ClassifyAssets
from ka11y.utils.config_loader import load_config

CONFIG = load_config()

console = Console(force_terminal=True)
logger = setup_logger(name="KAC", tag="crawler")

_SCREENSHOT_TIMEOUT_MS = 5_000

# Upper bound on inline <svg> elements rasterised per page. Icon-heavy sites can
# have hundreds of inline SVGs; cap the work so a pathological page can't stall
# the image crawl.
_MAX_SVGS_PER_PAGE = 300


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────
class CrawlSummary(BaseModel):
    total_images: int = 0
    informative: int = 0
    decorative: int = 0
    functional: int = 0
    complex: int = 0
    text_images: int = 0
    functional_buttons: int = 0
    functional_icons: int = 0
    functional_logos: int = 0
    functional_images: int = 0
    pages_crawled: int = 0


class CrawlReport(BaseModel):
    base_url: str
    crawl_date: str
    summary: CrawlSummary
    sub_type_breakdown: dict[str, int] = Field(default_factory=dict)
    images: List[ImageData] = Field(default_factory=list)


class _CR:
    """Thin adapter: dict → attribute access."""

    def __init__(self, d: dict):
        self.type = d["classification"]
        self.sub_type = d.get("sub_type")
        self.is_text_image = d.get("is_text_image", False)
        self.is_functional = d.get("is_functional", False)
        self.is_decorative = d.get("is_decorative", False)
        self.is_complex = d.get("is_complex", False)
        self.is_logo = d.get("is_logo", False)
        self.is_icon = d.get("is_icon", False)
        self.is_button = d.get("is_button", False)
        self.file_format = d.get("file_format")


# ─────────────────────────────────────────────────────────────────────────────
class ImageCrawlerNavigationError(RuntimeError):
    """Raised when the image crawler cannot resolve or load the target page."""

    def __init__(
        self,
        *,
        code: str,
        url: str,
        host: str | None,
        original_message: str,
        attempts: int,
    ) -> None:
        self.code = code
        self.url = url
        self.host = host
        self.original_message = original_message
        self.attempts = attempts
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        host_part = f" host={self.host}" if self.host else ""
        if self.code == "dns_resolution_failed":
            return (
                f"dns_resolution_failed{host_part} url={self.url}; image crawl could not "
                f"resolve the hostname after {self.attempts} attempt(s), so OCR and "
                f"image-audit checks were skipped. Original error: {self.original_message}"
            )
        return (
            f"page_navigation_failed{host_part} url={self.url}; image crawl could not load "
            f"the page after {self.attempts} attempt(s), so OCR and image-audit checks were "
            f"skipped. Original error: {self.original_message}"
        )


# ─────────────────────────────────────────────────────────────────────────────
class AsyncImageCrawler:

    def __init__(
        self,
        base_url: str,
        max_depth: int,
        max_pages: int | None = None,
        internal_links: bool = True,
    ):
        self.base_url = base_url
        self.max_depth = max_depth
        # Page budget is request-driven (default 50). The hard ceiling that keeps a
        # deep crawl from exhausting RAM regardless of how many links each page has;
        # falls back to the config value only when the caller passes nothing.
        self.max_pages = (
            max_pages
            if max_pages is not None
            else CONFIG.get("crawler", {}).get("max_pages", 50)
        )
        # internal_links is retained for API parity; link-following is always
        # confined to the exact base hostname (see crawl_page's CrawlPolicy), so
        # the crawler never leaves the audited domain regardless of this flag.
        self.internal_links = internal_links
        self.include_invisible = CONFIG["crawler"]["include_invisible"]
        self.images_data: List[ImageData] = []
        self.images_metadata: List[ImageMetadata] = []
        self.visited_urls: Set[str] = set()

        base_out = CONFIG["input"]["output_dir"]
        domain = urlparse(base_url).netloc.replace("www.", "").replace(".", "_")
        timestamp = time.strftime("%m%d_%H%M")
        self.output_dir = f"{base_out}/{domain}_{timestamp}"
        self.metadata_dir = f"{self.output_dir}/metadata"

        self.classifier = ClassifyAssets(output_dir=self.output_dir)
        self._create_directories()
        logger.info(f"Crawler initialised — base_url={base_url}")

    # ── directory setup ───────────────────────────────────────────────────────
    def _create_directories(self):
        base = Path(self.output_dir)
        dirs = [base] + [base / sub for sub in CONFIG["directories"]]
        dirs.append(base / "metadata")
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    async def _is_visible(self, element) -> bool:
        """
        Returns True when the element is NOT explicitly hidden via CSS.
        Intentionally does NOT require width/height > 0 so that lazy-loaded
        and off-screen images are still captured.
        On any JS exception, returns True (assume visible).
        """
        try:
            return await element.evaluate("""el => {
                const st  = window.getComputedStyle(el);
                const tag = el.tagName.toLowerCase();

                if (st.display     === "none")    return false;
                if (st.visibility  === "hidden")  return false;
                if (parseFloat(st.opacity) === 0) return false;

                // Any ancestor display:none hides the element
                let p = el.parentElement, d = 0;
                while (p && d < 6) {
                    if (window.getComputedStyle(p).display === "none") return false;
                    p = p.parentElement; d++;
                }

                // <img> / <input[type=image]> must have at least one src attribute
                if (tag === "img" || (tag === "input" && el.type === "image")) {
                    const hasSrc = !!(
                        el.getAttribute("src")           ||
                        el.getAttribute("data-src")      ||
                        el.getAttribute("data-lazy-src") ||
                        el.getAttribute("data-original") ||
                        el.getAttribute("srcset")        ||
                        el.getAttribute("data-srcset")
                    );
                    if (!hasSrc) return false;
                }
                return true;
            }""")
        except Exception:
            return True  # never silently drop images on JS error

    # ── lazy-loading triggers ─────────────────────────────────────────────────
    async def _trigger_lazy_loading(self, page):
        console.print(Rule("[dim]Triggering lazy-load (scroll passes)[/dim]"))
        passes = CONFIG.get("crawler", {}).get("scroll_passes", 3)
        for i in range(passes):
            logger.info(f"Scroll pass {i+1}/{passes}")
            await page.evaluate("""() => {
                return new Promise(resolve => {
                    const total = document.body.scrollHeight;
                    const step  = total / 10;
                    let pos = 0;
                    const timer = setInterval(() => {
                        pos += step;
                        window.scrollTo(0, pos);
                        if (pos >= total) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 150);
                });
            }""")
            await page.wait_for_timeout(500)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)

        # Fire IntersectionObserver callbacks manually
        await page.evaluate("""() => {
            const imgs = document.querySelectorAll("img[data-src],img[data-lazy-src],img[data-original]");
            imgs.forEach(img => {
                const obs = new IntersectionObserver(entries => {
                    entries.forEach(e => e.target.dispatchEvent(new Event("lazyload")));
                    obs.disconnect();
                });
                obs.observe(img);
            });
        }""")
        await page.wait_for_timeout(1000)
        logger.info("Lazy-load trigger complete")

    async def _reveal_hidden_images(self, page):
        """Click tabs, accordions, dropdowns, carousels to expose hidden images."""
        console.print(Rule("[dim]Revealing hidden content (tabs / accordions)[/dim]"))
        revealed = 0
        groups = {
            "tabs": '[role="tab"], .tab, [data-toggle="tab"], .nav-link',
            "accordions": '[data-toggle="collapse"], .accordion-toggle, .accordion-button, details summary',
            "dropdowns": '[data-toggle="dropdown"], .dropdown-toggle',
            "modals": '[data-toggle="modal"]',
            "carousels": '.carousel-control-next, .slick-next, [data-slide="next"]',
            "load_more": ".load-more, [data-load-more]",
        }
        for name, sel in groups.items():
            try:
                els = await page.locator(sel).all()
                unique = {
                    await e.evaluate("el => el.outerHTML.slice(0,100)"): e for e in els
                }.values()
                count = 0
                for el in list(unique)[:8]:
                    try:
                        if await el.is_visible(timeout=800):
                            await el.click(timeout=1500)
                            await page.wait_for_timeout(400)
                            revealed += 1
                            count += 1
                    except Exception:
                        pass
                if count:
                    logger.info(f"  {name}: clicked {count}")
            except Exception as e:
                logger.warning(f"Toggle group {name} error: {e}")

        logger.info(f"reveal_hidden_images complete — {revealed} elements triggered")

    # ── src resolution helper ─────────────────────────────────────────────────
    async def _resolve_src(self, el) -> str | None:
        """Return the best absolute URL for an image element, or None."""
        for attr in (
            "src",
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-lazy",
            "data-url",
        ):
            val = await el.get_attribute(attr)
            if val and not val.startswith("data:"):
                return urljoin(self.base_url, val)

        for attr in ("srcset", "data-srcset"):
            val = await el.get_attribute(attr)
            if val:
                first = val.strip().split(",")[0].strip().split()[0]
                if first and not first.startswith("data:"):
                    return urljoin(self.base_url, first)
        return None

    async def _safe_screenshot(
        self,
        element,
        *,
        path: str,
        timeout_ms: int = _SCREENSHOT_TIMEOUT_MS,
        min_width: int = 1,
        min_height: int = 1,
    ) -> bool:
        """
        Capture a screenshot with a hard upper bound and a fast visibility/size guard.
        """
        try:
            box = await element.bounding_box()
        except Exception:
            return False

        if not box:
            return False
        if box.get("width", 0) < min_width or box.get("height", 0) < min_height:
            return False

        try:
            await asyncio.wait_for(
                element.screenshot(path=path, timeout=timeout_ms),
                timeout=(timeout_ms / 1000) + 1,
            )
            return True
        except Exception:
            return False

    # ── save helper ───────────────────────────────────────────────────────────
    def _subpath(self, cr: _CR) -> str:
        if cr.type == "functional":
            sub = cr.sub_type or "images"
            return (
                f"functional/{sub}"
                if f"functional/{sub}" in set(CONFIG["directories"])
                else "functional"
            )
        if cr.type == "complex":
            sub = cr.sub_type or "charts"
            return (
                f"complex/{sub}"
                if f"complex/{sub}" in set(CONFIG["directories"])
                else "complex"
            )
        return cr.type  # informative / decorative

    def _make_image_data(
        self,
        *,
        url,
        src,
        alt,
        title,
        cr: _CR,
        screenshot_path,
        filename,
        element_id: str | None = None,
        capture_status: str = "ok",
        capture_error: str | None = None,
        aria_hidden: Optional[str] = None,
        role: Optional[str] = None,
    ) -> ImageData:
        return ImageData(
            url=url,
            src=src,
            alt_text=alt,
            title=title,
            classification=cr.type,
            sub_type=cr.sub_type,
            is_functional=cr.is_functional,
            is_decorative=cr.is_decorative,
            is_complex=cr.is_complex,
            is_text_image=cr.is_text_image,
            is_logo=cr.is_logo,
            is_icon=cr.is_icon,
            is_button=cr.is_button,
            file_format=cr.file_format,
            screenshot_path=screenshot_path,
            filename=filename,
            element_id=element_id,
            capture_status=capture_status,
            capture_error=capture_error,
            aria_hidden=aria_hidden,
            role=role,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Main crawl
    # ─────────────────────────────────────────────────────────────────────────
    async def crawl_page(self, discovered_urls: List[str] | None = None):
        """
        Crawl the base_url and its descendants up to max_depth using a single
        browser session and a bounded queue. (Optimized v2)
        """
        policy = CrawlPolicy(
            max_depth=self.max_depth,
            max_pages=self.max_pages,
            max_links_per_page=CONFIG.get("crawler", {}).get("max_links_per_page", 50),
            # Exact-hostname scope: only same-domain links are followed, never
            # subdomains or external hosts (memory-bounded, no SSRF via deep hops).
            same_origin=True,
            include_subdomains=False,
        )

        if discovered_urls:
            # Seed the queue with pre-discovered URLs at depth 0
            queue: deque[Tuple[str, int]] = deque([(u, 0) for u in discovered_urls])
        else:
            queue: deque[Tuple[str, int]] = deque([(self.base_url, 0)])

        self.visited_urls.clear()

        from ka11y.crawler.browser_pool import leased_context

        async with leased_context(
            viewport={
                "width": CONFIG["crawl_browser"]["width"],
                "height": CONFIG["crawl_browser"]["height"],
            },
        ) as context:

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            ) as download_session:

                while queue:
                    url, depth = queue.popleft()
                    normalized_url = policy.normalize_url(url)

                    if not normalized_url or normalized_url in self.visited_urls:
                        continue
                    # Budget check runs BEFORE visited.add so visited_urls
                    # tracks only URLs we actually attempted (was previously
                    # ``max_pages + 1`` after the final break).
                    if len(self.visited_urls) >= policy.max_pages:
                        logger.warning(
                            f"[image-crawler] Budget reached ({policy.max_pages} pages)"
                        )
                        break
                    self.visited_urls.add(normalized_url)

                    console.print(
                        Panel(
                            f"[bold cyan]Crawling:[/bold cyan] {normalized_url}\n"
                            f"[dim]Depth {depth}/{self.max_depth} | Pages {len(self.visited_urls)}/{policy.max_pages}[/dim]",
                            title="[bold]ka11y Image Crawler[/bold]",
                            border_style="cyan",
                        )
                    )

                    try:
                        new_links = await self._crawl_one_page(
                            context=context,
                            url=normalized_url,
                            depth=depth,
                            download_session=download_session,
                        )

                        if depth < self.max_depth:
                            for link in new_links:
                                if policy.is_allowed(link, self.base_url):
                                    queue.append((link, depth + 1))

                    except Exception as e:
                        logger.error(f"Error crawling {normalized_url}: {e}")

            # Context close handled by leased_context's __aexit__.
            if not self.visited_urls:
                raise ImageCrawlerNavigationError(
                    code="zero_pages_crawled",
                    url=self.base_url,
                    host=urlparse(self.base_url).hostname,
                    original_message="Crawl budget or navigation failures resulted in 0 pages being reached.",
                    attempts=1,
                )

            logger.info(
                f"Browser closed — finished image crawl for {self.base_url} ({len(self.visited_urls)} pages)"
            )

    async def _crawl_one_page(
        self,
        context,
        url: str,
        depth: int,
        download_session: aiohttp.ClientSession,
    ) -> List[str]:
        page = await context.new_page()
        page.set_default_timeout(60_000)
        links: List[str] = []

        try:
            # ── page load ──
            console.print(Rule("[dim]Loading page[/dim]"))
            await navigate_with_resilience(page, url)

            # ── Cookie Handling ──
            try:
                cookie_state = await handle_cookies(page)
                logger.debug(
                    f"[image_crawler] Cookie handling state for {url}: {cookie_state}"
                )
            except Exception as e:
                logger.debug(
                    f"[image_crawler] Cookie handling exception for {url}: {e}"
                )

            await page.wait_for_timeout(1_000)
            await self._trigger_lazy_loading(page)
            await self._reveal_hidden_images(page)
            await page.wait_for_timeout(500)

            # ═══════════════════════════════════════════════════════════
            # PASS 1 — <img> and <input type="image"> elements
            # ═══════════════════════════════════════════════════════════
            console.print(
                Panel(
                    "Scanning [bold]<img>[/bold] and [bold]<input type=image>[/bold]",
                    title="[yellow]PASS 1 · Image Elements[/yellow]",
                    border_style="yellow",
                )
            )

            img_els = await page.locator('img, input[type="image"]').all()
            console.print(f"  Found [bold]{len(img_els)}[/bold] elements")
            logger.info(f"PASS 1: {len(img_els)} img elements")

            seen_images: set[str] = set()
            captured = skipped_hidden = skipped_no_src = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                console=console,
                transient=True,
            ) as prog:
                task = prog.add_task("Processing images…", total=len(img_els))

                for idx, img in enumerate(img_els):
                    prog.update(
                        task,
                        advance=1,
                        description=f"[yellow]Image {idx+1}/{len(img_els)}[/yellow]",
                    )
                    try:
                        if not self.include_invisible and not await self._is_visible(
                            img
                        ):
                            skipped_hidden += 1
                            continue

                        abs_src = await self._resolve_src(img)
                        if not abs_src:
                            skipped_no_src += 1
                            continue

                        alt = await img.get_attribute("alt")

                        # Resolve the accessible label AND the surrounding
                        # context in a single round trip. These were two
                        # separate img.evaluate() calls (2 IPC hops per image);
                        # merged into one to halve cross-process traffic on
                        # image-heavy pages.
                        probe = await img.evaluate("""el => {
                            let resolvedLabel = null;
                            const labelledby = el.getAttribute("aria-labelledby");
                            if (labelledby) {
                                const text = labelledby.trim().split(/\\s+/)
                                    .map(id => {
                                        const node = document.getElementById(id);
                                        return node ? node.textContent.trim() : "";
                                    })
                                    .filter(Boolean)
                                    .join(" ");
                                if (text) resolvedLabel = text;
                            }
                            if (resolvedLabel === null) {
                                const ariaLabel = el.getAttribute("aria-label");
                                if (ariaLabel && ariaLabel.trim()) resolvedLabel = ariaLabel.trim();
                            }

                            const parent = el.closest("a, button, header, footer, nav, main, section, article") || el.parentElement;
                            return {
                                resolvedLabel: resolvedLabel,  // null → fall back to alt attribute
                                role: el.getAttribute("role") || "",
                                ariaHidden: el.getAttribute("aria-hidden") || "",
                                parentTag: parent ? parent.tagName.toLowerCase() : "",
                                parentRole: parent ? (parent.getAttribute("role") || "") : "",
                                clickable: !!el.closest("a, button, [role='button'], [onclick]"),
                            };
                        }""")

                        if probe.get("resolvedLabel") is not None:
                            alt = probe["resolvedLabel"]

                        el_context = probe

                        # Dedup key
                        alt_for_key = alt.strip() if isinstance(alt, str) else ""
                        dedup_key = f"{abs_src}|{alt_for_key}|{el_context['role']}|{el_context['parentTag']}|{el_context['clickable']}"

                        if dedup_key in seen_images:
                            continue
                        seen_images.add(dedup_key)

                        title = await img.get_attribute("title") or ""

                        # ML Classification
                        cr_dict = await self.classifier.classify_image(img, page)
                        cr = _CR(cr_dict)

                        img_hash = self.classifier.get_image_hash(abs_src)
                        sub_path = self._subpath(cr)
                        img_dir = os.path.join(self.output_dir, sub_path)
                        os.makedirs(img_dir, exist_ok=True)
                        filename = f"img_{img_hash}.png"
                        save_path = f"{img_dir}/{filename}"

                        # ── screenshot / download ──
                        saved = False
                        if cr.is_icon:
                            ext = os.path.splitext(urlparse(abs_src).path)[1] or ".png"
                            filename = f"img_{img_hash}{ext}"
                            save_path = f"{img_dir}/{filename}"
                            saved = await self.classifier._download_file(
                                download_session, abs_src, save_path
                            )
                            if not saved:
                                save_path = f"{img_dir}/img_{img_hash}.png"
                                filename = f"img_{img_hash}.png"
                                try:
                                    ph = await img.evaluate_handle(
                                        "el => el.closest('a,button,li,td,div') || el.parentElement"
                                    )
                                    saved = await self._safe_screenshot(
                                        ph,
                                        path=save_path,
                                    )
                                except Exception:
                                    pass

                        elif cr.is_button:
                            ext = os.path.splitext(urlparse(abs_src).path)[1] or ".png"
                            filename = f"img_{img_hash}{ext}"
                            save_path = f"{img_dir}/{filename}"
                            saved = await self.classifier._download_file(
                                download_session, abs_src, save_path
                            )
                            if not saved:
                                saved = await self._safe_screenshot(
                                    img,
                                    path=save_path,
                                )

                        else:
                            # Detect overlay container (text overlaid on image)
                            try:
                                container_h = (
                                    await self.classifier.get_visual_container(
                                        img, page
                                    )
                                )
                                is_overlay = await page.evaluate(
                                    "(args) => args[0] !== args[1]",
                                    [container_h, img],
                                )
                                target = container_h if is_overlay else img
                                saved = await self._safe_screenshot(
                                    target,
                                    path=save_path,
                                )
                            except Exception:
                                # Fallback: direct download
                                saved = await self.classifier._download_file(
                                    download_session, abs_src, save_path
                                )

                        # Decorative-classification + missing alt is only a
                        # WCAG 1.1.1 PASS when the image is hidden from AT
                        # (aria-hidden="true" or role in {presentation, none}).
                        # Plumb both signals into ImageData so the auditor can
                        # tell the two cases apart.
                        ah = (el_context.get("ariaHidden") or "").strip() or None
                        rl = (el_context.get("role") or "").strip() or None

                        if saved:
                            captured += 1
                            self.images_data.append(
                                self._make_image_data(
                                    url=url,
                                    src=abs_src,
                                    alt=alt,
                                    title=title,
                                    cr=cr,
                                    screenshot_path=save_path,
                                    filename=filename,
                                    element_id=f"img_{img_hash}",
                                    aria_hidden=ah,
                                    role=rl,
                                )
                            )
                            logger.info(
                                f"  ✓ [{cr.type}/{cr.sub_type}] {os.path.basename(save_path)}"
                            )
                        else:
                            # Register even failed captures so converters can emit INCOMPLETE
                            self.images_data.append(
                                self._make_image_data(
                                    url=url,
                                    src=abs_src,
                                    alt=alt,
                                    title=title,
                                    cr=cr,
                                    screenshot_path="",
                                    filename=filename,
                                    element_id=f"img_{img_hash}",
                                    capture_status="failed",
                                    aria_hidden=ah,
                                    role=rl,
                                )
                            )

                    except Exception as e:
                        logger.error(f"  ✗ Image {idx+1} error: {e}")

            console.print(
                f"  [green]✓ Captured {captured}[/green]  "
                f"[dim]hidden={skipped_hidden}  no-src={skipped_no_src}[/dim]"
            )

            # ═══════════════════════════════════════════════════════════
            # PASS 2 — Standalone button elements
            # ═══════════════════════════════════════════════════════════
            console.print(
                Panel(
                    "Scanning [bold]<button>[/bold], [bold]<input type=submit>[/bold], "
                    "[bold][role=button][/bold], Bootstrap .btn links",
                    title="[yellow]PASS 2 · Button Elements[/yellow]",
                    border_style="yellow",
                )
            )

            btn_sel = (
                "button, "
                'input[type="button"], input[type="submit"], input[type="reset"], '
                '[role="button"], '
                'a[class*="btn"]:not([role="button"])'
            )
            btn_els = await page.locator(btn_sel).all()
            console.print(f"  Found [bold]{len(btn_els)}[/bold] button elements")
            logger.info(f"PASS 2: {len(btn_els)} button elements")

            btn_dir = f"{self.output_dir}/functional/buttons"
            os.makedirs(btn_dir, exist_ok=True)
            seen_btns: set[str] = set()
            captured_btns = 0

            for bi, btn in enumerate(btn_els):
                try:
                    if not await self._is_visible(btn):
                        continue

                    info = await btn.evaluate("""el => {
                        const labelledby = el.getAttribute("aria-labelledby");
                        if (labelledby) {
                            const resolved = labelledby.trim().split(/\\s+/)
                                .map(id => {
                                    const node = document.getElementById(id);
                                    return node ? node.textContent.trim() : "";
                                })
                                .filter(Boolean)
                                .join(" ");
                            if (resolved) {
                                return {
                                    tag: el.tagName.toLowerCase(),
                                    text: resolved.slice(0, 80),
                                    type: el.getAttribute("type") || "",
                                    nameSource: "aria-labelledby"
                                };
                            }
                        }

                        const ariaLabel = (el.getAttribute("aria-label") || "").trim();
                        if (ariaLabel) {
                            return {
                                tag: el.tagName.toLowerCase(),
                                text: ariaLabel.slice(0, 80),
                                type: el.getAttribute("type") || "",
                                nameSource: "aria-label"
                            };
                        }

                        const innerName = (el.innerText || el.value || "").trim();
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: innerName.slice(0, 80),
                            type: el.getAttribute("type") || "",
                            nameSource: innerName ? "innerText" : "none"
                        };
                    }""")
                    html_hash = hashlib.md5(
                        (await btn.evaluate("el => el.outerHTML.slice(0,200)")).encode()
                    ).hexdigest()[:12]
                    if html_hash in seen_btns:
                        continue
                    seen_btns.add(html_hash)
                    btn_element_id = f"btn_{html_hash}"

                    btn_file = f"btn_{html_hash}.png"
                    btn_path = f"{btn_dir}/{btn_file}"
                    if not await btn.is_visible(timeout=1_000):
                        continue
                    if not await self._safe_screenshot(btn, path=btn_path):
                        continue

                    if os.path.getsize(btn_path) < 500:
                        os.remove(btn_path)
                        continue

                    captured_btns += 1
                    lbl = info["text"] or f"<{info['tag']} icon-only>"
                    console.print(
                        f"  [green]✓[/green] Button: [dim]{lbl[:60]}[/dim] "
                        f"[dim](name via {info.get('nameSource','?')})[/dim]"
                    )

                    btn_alt = info["text"] if info["text"] else None
                    self.images_data.append(
                        ImageData(
                            url=url,
                            src=url,
                            alt_text=btn_alt,
                            title=info["text"],
                            classification="functional",
                            sub_type="buttons",
                            is_functional=True,
                            is_decorative=False,
                            is_complex=False,
                            is_text_image=False,
                            is_logo=False,
                            is_icon=False,
                            is_button=True,
                            screenshot_path=btn_path,
                            filename=btn_file,
                            element_id=btn_element_id,
                        )
                    )
                except Exception as e:
                    logger.debug(f"  Button {bi+1} error: {e}")

            console.print(f"  [green]✓ Captured {captured_btns} buttons[/green]")

            # ── PASS 3 — inline <svg> elements ──────────────────────────────
            # Inline SVGs are rasterised to PNG (not saved as raw .svg markup):
            # downstream rules read screenshot_path with cv2.imread / OCR, which
            # cannot decode SVG text. We also capture NON-icon SVGs (logos,
            # illustrations, charts) — they still need a WCAG 1.1.1 accessible-name
            # check — and pull aria-label / <title> / role / aria-hidden so the
            # auditor can distinguish informative vs. correctly-hidden decorative.
            svg_els = await page.locator("svg").all()
            captured_svgs = 0
            seen_svgs: set[str] = set()
            for svg in svg_els:
                try:
                    if captured_svgs >= _MAX_SVGS_PER_PAGE:
                        break
                    if not await self._is_visible(svg):
                        continue

                    meta = await svg.evaluate("""el => {
                        const t = el.querySelector('title');
                        return {
                            ariaLabel:  el.getAttribute('aria-label') || '',
                            ariaHidden: el.getAttribute('aria-hidden') || '',
                            role:       el.getAttribute('role') || '',
                            title:      t ? (t.textContent || '').trim() : '',
                            outer:      el.outerHTML.slice(0, 300),
                        };
                    }""")
                    svg_hash = hashlib.md5(meta["outer"].encode()).hexdigest()[:12]
                    if svg_hash in seen_svgs:
                        continue
                    seen_svgs.add(svg_hash)

                    is_icon_svg = await self.classifier.is_icon(svg, "", "")
                    if is_icon_svg:
                        cr = _CR({
                            "classification": "functional",
                            "sub_type": "icons",
                            "is_functional": True,
                            "is_icon": True,
                        })
                    else:
                        cr = _CR({"classification": "informative", "sub_type": "images"})

                    sub_path = self._subpath(cr)
                    save_dir = f"{self.output_dir}/{sub_path}"
                    os.makedirs(save_dir, exist_ok=True)
                    svg_file = f"svg_{svg_hash}.png"
                    svg_path = f"{save_dir}/{svg_file}"

                    # Rasterise the rendered SVG so cv2/OCR-based rules can read it.
                    saved = await self._safe_screenshot(svg, path=svg_path)
                    if not saved:
                        continue

                    captured_svgs += 1
                    self.images_data.append(
                        self._make_image_data(
                            url=url,
                            src=url,
                            alt=(meta["ariaLabel"] or meta["title"]),
                            title=meta["title"],
                            cr=cr,
                            screenshot_path=svg_path,
                            filename=svg_file,
                            element_id=f"svg_{svg_hash}",
                            aria_hidden=(meta["ariaHidden"].strip() or None),
                            role=(meta["role"].strip() or None),
                        )
                    )
                except Exception as e:
                    logger.debug(f"  SVG capture error: {e}")

            console.print(f"  [green]✓ Captured {captured_svgs} SVGs[/green]")

            # ── link extraction ──
            links = await page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)"
            )

        finally:
            await page.close()

        return links

    # ─────────────────────────────────────────────────────────────────────────
    # Reporting
    # ─────────────────────────────────────────────────────────────────────────
    def save_results(self):
        console.print(Rule("[bold]Saving results[/bold]"))

        # Summary counts
        summary = CrawlSummary(pages_crawled=len(self.visited_urls))
        sub_breakdown: dict[str, int] = {}

        for img in self.images_data:
            summary.total_images += 1
            cls = img.classification
            if cls == "informative":
                summary.informative += 1
            elif cls == "decorative":
                summary.decorative += 1
            elif cls == "functional":
                summary.functional += 1
                if img.sub_type == "buttons":
                    summary.functional_buttons += 1
                elif img.sub_type == "icons":
                    summary.functional_icons += 1
                elif img.sub_type == "logos":
                    summary.functional_logos += 1
                else:
                    summary.functional_images += 1
            elif cls == "complex":
                summary.complex += 1
            if img.is_text_image:
                summary.text_images += 1
            key = f"{cls}/{img.sub_type}" if img.sub_type else cls
            sub_breakdown[key] = sub_breakdown.get(key, 0) + 1

        report = CrawlReport(
            base_url=self.base_url,
            crawl_date=datetime.now().isoformat(),
            summary=summary,
            sub_type_breakdown=sub_breakdown,
            images=self.images_data,
        )

        report_path = f"{self.output_dir}/images_report.json"
        with open(report_path, "w") as f:
            json.dump(report.model_dump(), f, indent=2)

        tbl = Table(
            title=f"[bold cyan]Crawl Complete — {self.base_url}[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan",
            show_header=True,
        )
        tbl.add_column("Category", style="bold")
        tbl.add_column("Count", justify="right")

        tbl.add_row("Total Images", str(summary.total_images))
        tbl.add_row("[green]Informative[/green]", str(summary.informative))
        tbl.add_row("[dim]Decorative[/dim]", str(summary.decorative))
        tbl.add_row("[yellow]Functional[/yellow]", str(summary.functional))
        tbl.add_row("  ↳ Buttons", str(summary.functional_buttons))
        tbl.add_row("  ↳ Icons", str(summary.functional_icons))
        tbl.add_row("  ↳ Logos", str(summary.functional_logos))
        tbl.add_row("  ↳ Images", str(summary.functional_images))
        tbl.add_row("[magenta]Complex[/magenta]", str(summary.complex))
        tbl.add_row("[dim]Pages crawled[/dim]", str(summary.pages_crawled))
        console.print(tbl)

        console.print(f"\n  [dim]Report → {report_path}[/dim]")
        logger.info(f"Report saved: {report_path}")

        self._export_csv()

    def _export_csv(self):
        if not self.images_data:
            return

        csv_path = f"{self.output_dir}/images_with_alt_text.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "src",
                    "alt_text",
                    "title",
                    "classification",
                    "sub_type",
                    "is_functional",
                    "is_decorative",
                    "is_complex",
                    "is_logo",
                    "is_icon",
                    "is_button",
                    "screenshot_path",
                ],
            )
            w.writeheader()
            for img in self.images_data:
                w.writerow(
                    {
                        "src": img.src,
                        "alt_text": img.alt_text if img.alt_text is not None else "",
                        "title": img.title,
                        "classification": img.classification,
                        "sub_type": img.sub_type,
                        "is_functional": img.is_functional,
                        "is_decorative": img.is_decorative,
                        "is_complex": img.is_complex,
                        "is_logo": img.is_logo,
                        "is_icon": img.is_icon,
                        "is_button": img.is_button,
                        "screenshot_path": img.screenshot_path,
                    }
                )

        logger.info(f"CSV saved: {csv_path}")
