import os
import json
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

from ka11y.crawler._ssrf_guard import install_ssrf_guard
from pathlib import Path
from typing import List, Set
from pydantic import BaseModel, Field
from datetime import datetime
import time
import aiohttp
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.text import Text
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
from ka11y.classifier.classfier import ClassifyAssets
from ka11y.utils.config_loader import load_config

CONFIG = load_config()

console = Console()
logger = setup_logger(name="KAC", tag="crawler")


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
class AsyncImageCrawler:

    def __init__(self, base_url: str, max_depth: int):
        self.base_url = base_url
        self.max_depth = max_depth
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

    # ── visibility check ──────────────────────────────────────────────────────
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
        self, *, url, src, alt, title, cr: _CR, screenshot_path, filename,
        element_id: str | None = None,
    ) -> ImageData:
        return ImageData(
            url=url,
            src=src,
            alt_text=alt,  # None = absent, "" = explicit empty (F18)
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
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Main crawl
    # ─────────────────────────────────────────────────────────────────────────
    async def crawl_page(self, current_depth: int = 0):
        if self.base_url in self.visited_urls or current_depth > self.max_depth:
            return
        self.visited_urls.add(self.base_url)

        console.print(
            Panel(
                f"[bold cyan]Crawling:[/bold cyan] {self.base_url}\n"
                f"[dim]Depth {current_depth}/{self.max_depth}[/dim]",
                title="[bold]ka11y Image Crawler[/bold]",
                border_style="cyan",
            )
        )

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={
                    "width": CONFIG["crawl_browser"]["width"],
                    "height": CONFIG["crawl_browser"]["height"],
                }
            )
            # Bug 1 fix: install SSRF route guard on the context so all pages
            # (including redirect hops) are protected against private-IP access.
            await install_ssrf_guard(context)
            page = await context.new_page()
            page.set_default_timeout(60_000)
            download_session = None

            # ── page load ──
            console.print(Rule("[dim]Loading page[/dim]"))
            try:
                await page.goto(
                    self.base_url, wait_until="domcontentloaded", timeout=30_000
                )
                console.print(f"  [green]✓[/green] Page loaded (domcontentloaded)")
                logger.info("Page loaded (domcontentloaded strategy)")
            except Exception as e:
                logger.warning(
                    f"'load' timed out: {e}  — retrying with domcontentloaded"
                )
                await page.goto(
                    self.base_url, wait_until="domcontentloaded", timeout=60_000
                )
                console.print(
                    f"  [yellow]⚠[/yellow] Page loaded (domcontentloaded fallback)"
                )

            await page.wait_for_timeout(1_000)
            await self._trigger_lazy_loading(page)
            await self._reveal_hidden_images(page)
            await page.wait_for_timeout(500)

            try:
                download_session = aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30)
                )
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
                            if (
                                not self.include_invisible
                                and not await self._is_visible(img)
                            ):
                                skipped_hidden += 1
                                continue

                            abs_src = await self._resolve_src(img)
                            if not abs_src:
                                skipped_no_src += 1
                                continue

                            # F18 fix: preserve None (absent) vs "" (explicit empty).
                            # None  → alt attribute missing → 1.1.1 fail candidate.
                            # ""    → alt="" present → intentionally decorative.
                            alt = await img.get_attribute("alt")

                            # F17 fix: resolve aria-labelledby for <img>.
                            # acc-name spec: aria-labelledby > aria-label > alt.
                            resolved_label = await img.evaluate("""el => {
                                const labelledby = el.getAttribute("aria-labelledby");
                                if (labelledby) {
                                    const text = labelledby.trim().split(/\\s+/)
                                        .map(id => {
                                            const node = document.getElementById(id);
                                            return node ? node.textContent.trim() : "";
                                        })
                                        .filter(Boolean)
                                        .join(" ");
                                    if (text) return text;
                                }
                                const ariaLabel = el.getAttribute("aria-label");
                                if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
                                return null;  // fall back to alt attribute
                            }""")
                            if resolved_label is not None:
                                alt = resolved_label

                            # 🔽 ADD CONTEXT EXTRACTION HERE
                            el_context = await img.evaluate("""el => {
                                const parent = el.closest("a, button, header, footer, nav, main, section, article") || el.parentElement;

                                return {
                                    role: el.getAttribute("role") || "",
                                    ariaHidden: el.getAttribute("aria-hidden") || "",
                                    parentTag: parent ? parent.tagName.toLowerCase() : "",
                                    parentRole: parent ? (parent.getAttribute("role") || "") : "",
                                    clickable: !!el.closest("a, button, [role='button'], [onclick]"),
                                };
                            }""")

                            # 🔽 BUILD NEW DEDUP KEY
                            dedup_key = f"{abs_src}|{alt.strip()}|{el_context['role']}|{el_context['parentTag']}|{el_context['clickable']}"

                            # 🔽 REPLACE OLD seen_srcs CHECK
                            if dedup_key in seen_images:
                                continue
                            seen_images.add(dedup_key)


                            title = await img.get_attribute("title") or ""

                            cr = _CR(await self.classifier.classify_image(img, page))

                            img_hash = self.classifier.get_image_hash(abs_src)
                            sub_path = self._subpath(cr)
                            img_dir = os.path.join(self.output_dir, sub_path)
                            os.makedirs(img_dir, exist_ok=True)
                            filename = f"img_{img_hash}.png"
                            save_path = f"{img_dir}/{filename}"

                            # ── screenshot / download ──
                            saved = False
                            if cr.is_icon:
                                ext = (
                                    os.path.splitext(urlparse(abs_src).path)[1]
                                    or ".png"
                                )
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
                                        await ph.screenshot(path=save_path)
                                        saved = True
                                    except Exception:
                                        pass

                            elif cr.is_button:
                                ext = (
                                    os.path.splitext(urlparse(abs_src).path)[1]
                                    or ".png"
                                )
                                filename = f"img_{img_hash}{ext}"
                                save_path = f"{img_dir}/{filename}"
                                saved = await self.classifier._download_file(
                                    download_session, abs_src, save_path
                                )
                                if not saved:
                                    try:
                                        await img.screenshot(path=save_path)
                                        saved = True
                                    except Exception:
                                        pass

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
                                    await target.screenshot(path=save_path)
                                    saved = True
                                except Exception:
                                    # Fallback: direct download
                                    saved = await self.classifier._download_file(
                                        download_session, abs_src, save_path
                                    )

                            if saved:
                                captured += 1
                                self.images_data.append(
                                    self._make_image_data(
                                        url=self.base_url,
                                        src=abs_src,
                                        alt=alt,   # None=absent, ""=explicit-empty (F18)
                                        title=title,
                                        cr=cr,
                                        screenshot_path=save_path,
                                        filename=filename,
                                        element_id=f"img_{img_hash}",
                                    )
                                )
                                logger.info(
                                    f"  ✓ [{cr.type}/{cr.sub_type}] {os.path.basename(save_path)}"
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
                            // F17 fix: full accName resolution for buttons.
                            // Priority: aria-labelledby > aria-label > innerText/value.

                            // 1. aria-labelledby
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

                            // 2. aria-label
                            const ariaLabel = (el.getAttribute("aria-label") || "").trim();
                            if (ariaLabel) {
                                return {
                                    tag: el.tagName.toLowerCase(),
                                    text: ariaLabel.slice(0, 80),
                                    type: el.getAttribute("type") || "",
                                    nameSource: "aria-label"
                                };
                            }

                            // 3. innerText / value (F16: may be "" for icon-only buttons)
                            const innerName = (el.innerText || el.value || "").trim();
                            return {
                                tag: el.tagName.toLowerCase(),
                                text: innerName.slice(0, 80),
                                type: el.getAttribute("type") || "",
                                nameSource: innerName ? "innerText" : "none"
                            };
                        }""")
                        html_hash = hashlib.md5(
                            (
                                await btn.evaluate("el => el.outerHTML.slice(0,200)")
                            ).encode()
                        ).hexdigest()[:12]
                        if html_hash in seen_btns:
                            continue
                        seen_btns.add(html_hash)
                        # F16 fix: stable element_id for dedup — two icon-only buttons
                        # both produce text="" but have distinct html_hash values, so
                        # each gets its own record and neither masks the other.
                        btn_element_id = f"btn_{html_hash}"

                        btn_file = f"btn_{html_hash}.png"
                        btn_path = f"{btn_dir}/{btn_file}"
                        await btn.screenshot(path=btn_path, timeout=5_000)

                        # Reject near-empty screenshots
                        if os.path.getsize(btn_path) < 500:
                            os.remove(btn_path)
                            continue
                        try:
                            from PIL import Image as PILImage

                            with PILImage.open(btn_path) as im:
                                if im.width < 20 or im.height < 10:
                                    os.remove(btn_path)
                                    continue
                        except Exception:
                            pass

                        captured_btns += 1
                        # F16: use resolved accessible name; icon-only buttons
                        # will have text="" (no innerText) but a non-empty
                        # nameSource tells the auditor which resolution path fired.
                        lbl = info["text"] or f"<{info['tag']} icon-only>"
                        console.print(
                            f"  [green]✓[/green] Button: [dim]{lbl[:60]}[/dim] "
                            f"[dim](name via {info.get('nameSource','?')})[/dim]"
                        )
                        logger.info(f"  ✓ Button captured: {btn_path} ({lbl})")

                        # F16/F18: alt_text=None signals "no accessible name found"
                        # so the auditor can raise a 4.1.2 violation rather than
                        # treating it the same as a named button.
                        btn_alt = info["text"] if info["text"] else None
                        self.images_data.append(
                            ImageData(
                                url=self.base_url,
                                src=self.base_url,
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

                # ═══════════════════════════════════════════════════════════
                # PASS 3 — Inline <svg> elements (icons + charts)
                # ═══════════════════════════════════════════════════════════
                console.print(
                    Panel(
                        "Scanning inline [bold]<svg>[/bold] elements",
                        title="[yellow]PASS 3 · Inline SVG Elements[/yellow]",
                        border_style="yellow",
                    )
                )

                svg_els = await page.locator("svg").all()
                console.print(f"  Found [bold]{len(svg_els)}[/bold] SVG elements")
                logger.info(f"PASS 3: {len(svg_els)} SVG elements")

                seen_svgs: set[str] = set()
                captured_svgs = 0

                for si, svg in enumerate(svg_els):
                    try:
                        if not await self._is_visible(svg):
                            continue

                        svg_html = await svg.evaluate("el => el.outerHTML.slice(0,300)")
                        svg_hash = hashlib.md5(svg_html.encode()).hexdigest()[:12]
                        if svg_hash in seen_svgs:
                            continue
                        seen_svgs.add(svg_hash)

                        # Gather context for classification
                        svg_ctx = await svg.evaluate("""el => {
                            const a   = el.closest("a");
                            const btn = el.closest("button, [role='button']");
                            const href = a ? (a.getAttribute("href") || "") : "";
                            const deadHref = !href || href=="#" || href.startsWith("javascript:");
                            return {
                                inLink:    a   !== null,
                                inRealLink: a !== null && !deadHref,
                                inButton:  btn !== null,
                                ariaLabel: el.getAttribute("aria-label") || "",
                                ariaHidden: el.getAttribute("aria-hidden") || "",
                                role:      el.getAttribute("role") || ""
                            };
                        }""")

                        is_icon_svg = await self.classifier.is_icon(svg, "", "")
                        is_chart_svg = (
                            not is_icon_svg
                            and await self.classifier.is_chart(svg, "", "", page)
                        )

                        if not is_icon_svg and not is_chart_svg:
                            continue

                        if is_icon_svg:
                            sub_dir = (
                                "functional/icons"
                                if (svg_ctx["inLink"] or svg_ctx["inButton"])
                                else "informative"
                            )
                        else:
                            sub_dir = "complex/charts"

                        save_dir = f"{self.output_dir}/{sub_dir}"
                        os.makedirs(save_dir, exist_ok=True)
                        svg_file = f"svg_{svg_hash}.svg"
                        svg_path = f"{save_dir}/{svg_file}"

                        svg_content = await svg.evaluate("el => el.outerHTML")
                        with open(svg_path, "w", encoding="utf-8") as f:
                            f.write(svg_content)

                        captured_svgs += 1
                        kind = "icon" if is_icon_svg else "chart"
                        console.print(
                            f"  [green]✓[/green] SVG {kind}: [dim]{sub_dir}[/dim]"
                        )
                        logger.info(f"  ✓ SVG {kind} saved: {svg_path}")
                        # Extract accessible name properly
                        alt_text = await svg.evaluate("""el => {
                            // 1. aria-labelledby
                            const labelledby = el.getAttribute("aria-labelledby");
                            if (labelledby) {
                                const ids = labelledby.split(/\\s+/);
                                let text = "";
                                ids.forEach(id => {
                                    const ref = document.getElementById(id);
                                    if (ref) text += ref.textContent.trim() + " ";
                                });
                                if (text.trim()) return text.trim();
                            }

                            // 2. aria-label
                            const ariaLabel = el.getAttribute("aria-label");
                            if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

                            // 3. <title>
                            const titleEl = el.querySelector("title");
                            if (titleEl && titleEl.textContent.trim()) {
                                return titleEl.textContent.trim();
                            }

                            // 4. <desc> (optional fallback)
                            const descEl = el.querySelector("desc");
                            if (descEl && descEl.textContent.trim()) {
                                return descEl.textContent.trim();
                            }

                            return "";
                        }""")

                        # 2. Apply aria-hidden override
                        if (
                                svg_ctx["ariaHidden"] == "true"
                                or svg_ctx["role"] in ("presentation", "none")
                        ):
                            alt_text = ""

                        self.images_data.append(
                            ImageData(
                                url=self.base_url,
                                src=self.base_url,
                                alt_text=alt_text,
                                title="",
                                classification=(
                                    "functional" if is_icon_svg else "complex"
                                ),
                                sub_type="icons" if is_icon_svg else "charts",
                                is_functional=is_icon_svg,
                                is_decorative=False,
                                is_complex=is_chart_svg,
                                is_text_image=False,
                                is_logo=False,
                                is_icon=is_icon_svg,
                                is_button=False,
                                screenshot_path=svg_path,
                                filename=svg_file,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"  SVG {si+1} error: {e}")

                console.print(f"  [green]✓ Captured {captured_svgs} SVGs[/green]")

                # ═══════════════════════════════════════════════════════════
                # PASS 4 — Font icons (<i> and <span> with icon classes)
                # ═══════════════════════════════════════════════════════════
                console.print(
                    Panel(
                        "Scanning font-icon [bold]<i>[/bold] and [bold]<span>[/bold] elements",
                        title="[yellow]PASS 4 · Font Icons[/yellow]",
                        border_style="yellow",
                    )
                )

                fi_sel = (
                    'i[class*="fa"], i[class*="material"], i[class*="bi"], '
                    'i[class*="glyphicon"], i[class*="feather"], i[class*="icon"], '
                    'span[class*="material-icons"], span[class*="material-symbols"]'
                )
                fi_els = await page.locator(fi_sel).all()
                console.print(f"  Found [bold]{len(fi_els)}[/bold] font icon elements")
                logger.info(f"PASS 4: {len(fi_els)} font icon elements")

                fi_dir = f"{self.output_dir}/functional/icons"
                os.makedirs(fi_dir, exist_ok=True)
                seen_fi: set[str] = set()
                captured_fi = 0

                for fii, fi in enumerate(fi_els):
                    try:
                        if not await self._is_visible(fi):
                            continue

                        fi_html = await fi.evaluate("el => el.outerHTML.slice(0,200)")
                        fi_hash = hashlib.md5(fi_html.encode()).hexdigest()[:12]
                        if fi_hash in seen_fi:
                            continue
                        seen_fi.add(fi_hash)

                        fi_info = await fi.evaluate("""el => {
                            const interactiveParent = el.closest(`
                                a,
                                button,
                                [role="button"],
                                [role="link"],
                                [onclick],
                                [tabindex]
                            `);

                            const hasClick = el.closest("[onclick]") !== null;
                            const hasTabindex = el.closest("[tabindex]") !== null;

                            // F17 fix: resolve aria-labelledby for font-icons.
                            // Check the icon itself and its nearest interactive parent.
                            let label = "";
                            const labelTarget = interactiveParent || el;
                            const labelledby = labelTarget.getAttribute("aria-labelledby");
                            if (labelledby) {
                                const resolved = labelledby.trim().split(/\\s+/)
                                    .map(id => {
                                        const node = document.getElementById(id);
                                        return node ? node.textContent.trim() : "";
                                    })
                                    .filter(Boolean)
                                    .join(" ");
                                if (resolved) label = resolved;
                            }
                            if (!label) {
                                label = (labelTarget.getAttribute("aria-label") || "").trim()
                                     || (el.getAttribute("aria-label") || "").trim()
                                     || (el.getAttribute("title") || "").trim();
                            }

                            return {
                                inLink: el.closest("a") !== null,
                                inButton: el.closest("button,[role='button']") !== null,
                                hasRoleButton: el.closest('[role="button"]') !== null,
                                hasRoleLink: el.closest('[role="link"]') !== null,
                                hasOnClick: hasClick,
                                hasTabindex: hasTabindex,
                                isInteractive: interactiveParent !== null,
                                label: label
                            };
                        }""")

                        is_functional = (
                                fi_info["inLink"]
                                or fi_info["inButton"]
                                or fi_info["hasRoleButton"]
                                or fi_info["hasRoleLink"]
                                or fi_info["hasOnClick"]
                                or (fi_info["hasTabindex"] and fi_info["hasOnClick"])
                        )
                        fi_sub_dir = (
                            "functional/icons" if is_functional else "decorative"
                        )
                        save_dir = f"{self.output_dir}/{fi_sub_dir}"
                        os.makedirs(save_dir, exist_ok=True)
                        fi_file = f"fi_{fi_hash}.png"
                        fi_path = f"{save_dir}/{fi_file}"

                        # Screenshot the icon's nearest meaningful container
                        try:
                            parent_h = await fi.evaluate_handle(
                                "el => el.closest('a,button,li,[role=\"button\"]') "
                                "     || el.parentElement || el"
                            )
                            await parent_h.screenshot(path=fi_path, timeout=5_000)
                        except Exception:
                            await fi.screenshot(path=fi_path, timeout=5_000)

                        captured_fi += 1
                        console.print(
                            f"  [green]✓[/green] Font icon "
                            f"[dim]({'functional' if is_functional else 'decorative'})[/dim]"
                        )
                        logger.info(f"  ✓ Font icon saved: {fi_path}")

                        self.images_data.append(
                            ImageData(
                                url=self.base_url,
                                src=self.base_url,
                                alt_text=fi_info["label"],
                                title="",
                                classification=(
                                    "functional" if is_functional else "decorative"
                                ),
                                sub_type="icons" if is_functional else "decorative",
                                is_functional=is_functional,
                                is_decorative=not is_functional,
                                is_complex=False,
                                is_text_image=False,
                                is_logo=False,
                                is_icon=True,
                                is_button=False,
                                screenshot_path=fi_path,
                                filename=fi_file,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"  Font icon {fii+1} error: {e}")

                console.print(f"  [green]✓ Captured {captured_fi} font icons[/green]")

                # ═══════════════════════════════════════════════════════════
                # PASS 5 — CSS background-image elements
                # ═══════════════════════════════════════════════════════════
                console.print(
                    Panel(
                        "Scanning elements with [bold]background-image[/bold] CSS property",
                        title="[yellow]PASS 5 · CSS Background Images[/yellow]",
                        border_style="yellow",
                    )
                )

                bg_candidates = await page.evaluate("""() => {
                    const results = [];
                    const all = document.querySelectorAll("*");
                    for (const el of all) {
                        const bg = window.getComputedStyle(el).backgroundImage;
                        if (!bg || bg === "none" || !bg.startsWith("url(")) continue;
                        const match = bg.match(/url\\(["']?([^"')]+)["']?\\)/);
                        if (!match) continue;
                        const src = match[1];
                        if (src.startsWith("data:")) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 100 || rect.height < 100) continue;
                        const ratio = rect.width / rect.height;
                        if (ratio < 0.2 || ratio > 10) continue;
                        results.push({
                            src:       src,
                            width:     rect.width,
                            height:    rect.height,
                            ariaHidden: el.getAttribute("aria-hidden") || "",
                            ariaLabel:  el.getAttribute("aria-label") || "",
                            role:       el.getAttribute("role") || "",
                            tagName:    el.tagName.toLowerCase()
                        });
                    }
                    return results;
                }""")

                console.print(
                    f"  Found [bold]{len(bg_candidates)}[/bold] background-image candidates"
                )
                logger.info(f"PASS 5: {len(bg_candidates)} background candidates")

                seen_bgs: set[str] = set()
                captured_bg = 0

                for bg in bg_candidates:
                    try:
                        abs_src = urljoin(self.base_url, bg["src"])
                        if abs_src in seen_bgs or abs_src in seen_images:
                            continue
                        seen_bgs.add(abs_src)

                        bg_hash = hashlib.md5(abs_src.encode()).hexdigest()[:12]

                        role = (bg["role"] or "").strip().lower()
                        has_label = bool(bg["ariaLabel"].strip())
                        is_hidden = bg["ariaHidden"] == "true" or role in ("presentation", "none")

                        if is_hidden:
                            cls, sub = "decorative", "presentational"

                        elif role == "img":
                            # Explicitly declared as image → must be informative
                            if has_label:
                                cls, sub = "informative", "succinct_information"
                            else:
                                cls, sub = "informative", "missing_alt"  # 🔥 key fix

                        elif has_label:
                            cls, sub = "informative", "succinct_information"

                        else:
                            cls, sub = "decorative", "decorative"

                        save_dir = f"{self.output_dir}/{cls}"
                        os.makedirs(save_dir, exist_ok=True)
                        ext = os.path.splitext(urlparse(abs_src).path)[1] or ".jpg"
                        bg_file = f"bg_{bg_hash}{ext}"
                        bg_path = f"{save_dir}/{bg_file}"

                        ok = await self.classifier._download_file(
                            download_session, abs_src, bg_path
                        )

                        if ok:
                            captured_bg += 1
                            console.print(
                                f"  [green]✓[/green] BG image [{cls}/{sub}] "
                                f"[dim]{bg['width']:.0f}×{bg['height']:.0f}[/dim]"
                            )
                            logger.info(f"  ✓ BG image saved: {bg_path}")

                            self.images_data.append(
                                ImageData(
                                    url=self.base_url,
                                    src=abs_src,
                                    alt_text=bg["ariaLabel"],
                                    title="",
                                    classification=cls,
                                    sub_type=sub,
                                    is_functional=False,
                                    is_decorative=(cls == "decorative"),
                                    is_complex=False,
                                    is_text_image=False,
                                    is_logo=False,
                                    is_icon=False,
                                    is_button=False,
                                    screenshot_path=bg_path,
                                    filename=bg_file,
                                )
                            )
                    except Exception as e:
                        logger.debug(f"  BG image error: {e}")

                console.print(
                    f"  [green]✓ Captured {captured_bg} background images[/green]"
                )

                # ── link-following (multi-depth) ───────────────────────────
                if current_depth < self.max_depth:
                    console.print(
                        Rule(
                            f"[dim]Finding links (depth {current_depth}→{self.max_depth})[/dim]"
                        )
                    )
                    links = await page.locator("a[href]").all()
                    for link in links:
                        try:
                            href = await link.get_attribute("href")
                            if not href:
                                continue
                            abs_href = urljoin(self.base_url, href)
                            parsed = urlparse(abs_href)
                            if parsed.netloc != urlparse(self.base_url).netloc:
                                continue
                            if abs_href not in self.visited_urls:
                                sub_crawler = AsyncImageCrawler(
                                    base_url=abs_href, max_depth=self.max_depth
                                )
                                sub_crawler.visited_urls = self.visited_urls
                                sub_crawler.images_data = self.images_data
                                await sub_crawler.crawl_page(current_depth + 1)
                        except Exception:
                            pass

            except Exception as e:
                logger.error(f"Crawl error: {e}")
                import traceback

                traceback.print_exc()

            finally:
                if download_session is not None and not download_session.closed:
                    await download_session.close()
                await context.close()
                await browser.close()
                logger.info(f"Browser closed — finished crawling {self.base_url}")

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

        # ── Rich summary table ──
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

        # CSV export
        self._export_csv()

    def _export_csv(self):
        """
        Export ALL crawled images to images_with_alt_text.csv.
        Includes decorative and missing-alt images (alt_text column is empty for those).
        Previously this method filtered to only images where alt_text was truthy.
        """
        if not self.images_data:
            return

        csv_path = f"{self.output_dir}/images_with_alt_text.csv"

        import csv as _csv

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(
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
                        # Use empty string when alt is None (missing) so the CSV
                        # column is always present — the auditor distinguishes
                        # None vs "" via the classification / sub_type fields.
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

        from rich.console import Console

        Console().print(
            f"  [dim]CSV  → {csv_path} ({len(self.images_data)} rows, "
            f"all images including decorative)[/dim]"
        )

        setup_logger(name="KAC", tag="crawler").info(f"CSV saved: {csv_path}")