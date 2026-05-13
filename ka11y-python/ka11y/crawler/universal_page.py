from __future__ import annotations

import hashlib
import json
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import BrowserContext, Page

from ka11y.config.logger import setup_logger
from ka11y.crawler.navigation import navigate_with_resilience, NavigationError
from ka11y.crawler.policy import CrawlPolicy
from ka11y.crawler.cookie_handler import handle_cookies
from ka11y.utils.step_logger import ExecutionStepLogger

logger = setup_logger(name="KAC", tag="universal_page")

_GOTO_TIMEOUT_MS = 30_000
_NETWORKIDLE_TIMEOUT_MS = 15_000
_DOM_STABILITY_MS = 600
_DOM_STABILITY_TOTAL_MS = 12_000
_POST_SCROLL_WAIT_MS = 1_500

_SPA_SIGNALS = [
    "window.__NEXT_DATA__",
    "window.__nuxt",
    "window.__vue_app__",
    "window.React",
    "window.angular",
    "window.Ember",
    "window.__svelte",
    "document.querySelector('[data-reactroot]')",
]


class PageSnapshot(BaseModel):
    page_url: str
    forms: List[Dict[str, Any]] = Field(default_factory=list)
    interactive: List[Dict[str, Any]] = Field(default_factory=list)
    target_sizes: List[Dict[str, Any]] = Field(default_factory=list)
    moving_content: List[Dict[str, Any]] = Field(default_factory=list)
    media: List[Dict[str, Any]] = Field(default_factory=list)
    text_spacing: List[Dict[str, Any]] = Field(default_factory=list)
    sensory: List[Dict[str, Any]] = Field(default_factory=list)
    # Elements with a CSS background-image URL. Populated by background_images.js
    # so downstream image-audit hooks can flag informational backgrounds that
    # lack a text alternative (Sprint 3 / step 15).
    background_images: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    element_refs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    page_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    pages_crawled: int = 0
    partial: bool = False
    har_path: Optional[str] = None


_JS_DIR = Path(__file__).parent / "js"


def _load_js(name: str) -> str:
    """Read a sibling .js extractor from disk.

    The extractors used to live inline as multi-thousand-line ``r\"\"\"…\"\"\"``
    strings in this module, which defeated IDE syntax highlighting and made
    JS-side bugs invisible until runtime. Loading from disk is read-once at
    import time so the per-call overhead is the same as before.
    """
    return (_JS_DIR / name).read_text(encoding="utf-8")


_COMBINED_EXTRACT_JS = _load_js("universal_extract.js")

_LINK_EXTRACT_JS = _load_js("link_extract.js")

_LAZY_LOAD_TRIGGER_JS = _load_js("lazy_load_trigger.js")

_BACKGROUND_IMAGES_JS = _load_js("background_images.js")

_DOM_STABILITY_JS = f"""(stabilityMs) => {{
    return new Promise((resolve) => {{
        let timer = null;
        const start = Date.now();
        function reset() {{
            if (timer) clearTimeout(timer);
            if (Date.now() - start > {_DOM_STABILITY_TOTAL_MS}) {{
                resolve('timeout');
                return;
            }}
            timer = setTimeout(() => resolve('stable'), stabilityMs);
        }}
        reset();
        const observer = new MutationObserver(() => reset());
        observer.observe(document.body, {{ childList: true, subtree: true }});
        setTimeout(() => {{
            observer.disconnect();
            resolve('total_timeout');
        }}, {_DOM_STABILITY_TOTAL_MS});
    }});
}}"""


class UniversalPageLoader:
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    @classmethod
    async def load(
        cls,
        url: str,
        output_dir: Path,
        *,
        max_depth: int = 0,
        record_har: bool = False,
        step_logger: ExecutionStepLogger | None = None,
        policy: CrawlPolicy | None = None,
    ) -> PageSnapshot:
        """
        Main entry point for universal crawling. Uses a single browser session
        and a bounded queue (Optimized v2).
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        if policy is None:
            policy = CrawlPolicy(
                max_depth=max_depth,
                max_pages=20,  # Default safety cap
                max_links_per_page=50,
            )

        snapshot = PageSnapshot(page_url=url)
        har_path: Optional[str] = None
        har_file = output_dir / "universal_session.har"

        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="running",
                message="Starting universal crawl (queue-based)",
                context={"url": url, "max_depth": max_depth, "record_har": record_har},
            )

        from collections import deque

        queue: deque[tuple[str, int]] = deque([(url, 0)])
        visited: set[str] = set()

        from ka11y.crawler.browser_pool import leased_context

        context_kwargs: Dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": cls.USER_AGENT,
        }
        if record_har:
            context_kwargs["record_har_path"] = str(har_file)
            context_kwargs["record_har_url_filter"] = "**/*"

        async with leased_context(**context_kwargs) as context:
            while queue:
                current_url, current_depth = queue.popleft()
                normalized_url = policy.normalize_url(current_url)

                if normalized_url in visited:
                    continue
                visited.add(normalized_url)

                if not policy.is_allowed(normalized_url, url):
                    logger.info(
                        f"[universal] skipping off-origin/disallowed URL: {normalized_url}"
                    )
                    continue

                if snapshot.pages_crawled >= policy.max_pages:
                    logger.warning(
                        f"[universal] crawl budget exceeded ({policy.max_pages} pages)"
                    )
                    break

                new_links = await cls._crawl_one_url(
                    context=context,
                    root_url=url,
                    url=normalized_url,
                    depth=current_depth,
                    policy=policy,
                    output=snapshot,
                    step_logger=step_logger,
                )

                if current_depth < policy.max_depth:
                    for link in new_links:
                        queue.append((link, current_depth + 1))

        if record_har and har_file.exists():
            har_path = str(har_file)

        snapshot.har_path = har_path

        if step_logger:
            step_logger.record(
                step="universal_loader",
                status="completed",
                message="Universal crawl completed",
                context={
                    "pages_crawled": snapshot.pages_crawled,
                    "forms": len(snapshot.forms),
                    "interactive": len(snapshot.interactive),
                    "target_sizes": len(snapshot.target_sizes),
                    "moving_content": len(snapshot.moving_content),
                    "media": len(snapshot.media),
                    "text_spacing": len(snapshot.text_spacing),
                    "sensory": len(snapshot.sensory),
                    "warnings": len(snapshot.warnings),
                    "har_path": har_path,
                },
            )

        return snapshot

    @classmethod
    async def _crawl_one_url(
        cls,
        *,
        context: BrowserContext,
        root_url: str,
        url: str,
        depth: int,
        policy: CrawlPolicy,
        output: PageSnapshot,
        step_logger: ExecutionStepLogger | None,
    ) -> List[str]:
        page = await context.new_page()
        page_warning_count = 0
        links: List[str] = []

        try:
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="running",
                    message="Opening page",
                    context={"url": url, "depth": depth},
                )

            await cls._prepare_page(page, url, step_logger=step_logger)

            # Chunked extraction to combat virtualized DOMs (Infinite scroll)
            await cls._extract_page_chunked(page, page_url=url, output=output)

            # Links extraction can just use the final state
            links = await cls._extract_links(page, root_url=url)

            # Limit links per page
            if len(links) > policy.max_links_per_page:
                logger.info(
                    f"[universal] capping links from {len(links)} to {policy.max_links_per_page}"
                )
                links = links[: policy.max_links_per_page]

            def _count_for_url(collection: list) -> int:
                return len([r for r in collection if r.get("page_url") == url])

            page_forms = _count_for_url(output.forms)
            page_interactive = _count_for_url(output.interactive)
            page_target_sizes = _count_for_url(output.target_sizes)
            page_moving = _count_for_url(output.moving_content)
            page_media = _count_for_url(output.media)
            page_text_spacing = _count_for_url(output.text_spacing)
            page_sensory = _count_for_url(output.sensory)

            output.page_summaries.append(
                {
                    "page_url": url,
                    "depth": depth,
                    "forms": page_forms,
                    "interactive": page_interactive,
                    "target_sizes": page_target_sizes,
                    "moving_content": page_moving,
                    "media": page_media,
                    "text_spacing": page_text_spacing,
                    "sensory": page_sensory,
                    "links_found": len(links),
                }
            )
            output.pages_crawled += 1
            page_warning_count = len(
                [w for w in output.warnings if w.get("page_url") == url]
            )

            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="completed",
                    message="Extracted page",
                    context={
                        "url": url,
                        "depth": depth,
                        "forms": page_forms,
                        "interactive": page_interactive,
                        "target_sizes": page_target_sizes,
                        "moving_content": page_moving,
                        "media": page_media,
                        "text_spacing": page_text_spacing,
                        "sensory": page_sensory,
                        "links_found": len(links),
                        "warnings": page_warning_count,
                    },
                )
        except NavigationError as exc:
            # Captured as warning instead of hard error for universal crawl
            warning = {
                "code": exc.code,
                "page_url": url,
                "message": str(exc),
            }
            output.warnings.append(warning)
            logger.warning(f"[universal] {exc.code} for {url}: {exc}")
        except Exception as exc:
            output.partial = True
            warning = {
                "code": "page_extract_failed",
                "page_url": url,
                "message": str(exc),
            }
            output.warnings.append(warning)
            logger.warning(f"[universal] failed to extract {url}: {exc}")
            if step_logger:
                step_logger.record(
                    step="universal_page",
                    status="error",
                    message="Page extraction failed",
                    context=warning,
                )
        finally:
            await page.close()

        return links

    @classmethod
    async def _prepare_page(
        cls,
        page: Page,
        url: str,
        *,
        step_logger: ExecutionStepLogger | None,
    ) -> None:
        await navigate_with_resilience(page, url)

        try:
            await page.wait_for_load_state(
                "networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS
            )
        except Exception:
            logger.debug(f"[universal] networkidle timeout for {url}")

        await cls._wait_for_spa(page)

        # ── Cookie Handling ──
        try:
            cookie_state = await handle_cookies(page)
            logger.debug(f"[universal] Cookie handling state for {url}: {cookie_state}")
        except Exception as e:
            logger.debug(f"[universal] Cookie handling exception for {url}: {e}")

        try:
            await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
        except Exception:
            logger.debug(f"[universal] DOM stability pre-check failed for {url}")

        if step_logger:
            step_logger.record(
                step="universal_page_ready",
                status="completed",
                message="Page reached extraction-ready state",
                context={"url": url},
            )

    @classmethod
    async def _extract_page_chunked(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
    ) -> None:
        """Extracts DOM in chunks by scrolling to bypass Virtualized DOMs."""
        seen_refs = set()

        # Read max scroll passes from config (fallback to 4)
        max_passes = 4

        # Trigger initial lazy-load setup without scrolling
        initial_lazy_js = """async () => {
            document.querySelectorAll('[data-src],[data-lazy-src],[data-original],[loading="lazy"]').forEach(el => {
                ['lazyload', 'lazyloaded', 'lazy-load'].forEach(evt => el.dispatchEvent(new Event(evt, { bubbles: true })));
                if (el.dataset.src) el.src = el.dataset.src;
                if (el.dataset.lazySrc) el.src = el.dataset.lazySrc;
                if (el.dataset.original) el.src = el.dataset.original;
            });
        }"""
        try:
            await page.evaluate(initial_lazy_js)
        except Exception:
            pass

        for i in range(max_passes):
            # 1. Wait for stability before extracting
            try:
                await page.evaluate(_DOM_STABILITY_JS, _DOM_STABILITY_MS)
            except Exception:
                pass

            # 2. Extract current viewport/DOM chunk
            await cls._extract_page(
                page, page_url=page_url, output=output, seen_refs=seen_refs
            )

            # 3. Check if we hit the bottom of the page
            is_at_bottom = await page.evaluate(
                "() => { const h = document.documentElement; return (window.innerHeight + window.scrollY) >= (h.scrollHeight - 100); }"
            )
            if is_at_bottom:
                break

            # 4. Scroll down
            await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
            await page.wait_for_timeout(_POST_SCROLL_WAIT_MS)

        # Reset scroll position to top
        await page.evaluate("window.scrollTo(0, 0)")

    @classmethod
    async def _extract_page(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
        seen_refs: set[str] | None = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        combined = {
            "forms": [],
            "interactive": [],
            "target_sizes": [],
            "moving_content": [],
            "media": [],
            "text_spacing": [],
            "sensory": [],
        }

        frames = await cls._collect_same_origin_frames(
            page, page_url=page_url, output=output
        )
        for frame, frame_path in frames:
            if frame.is_detached():
                # Silently skip detached frames if they were just transient/blank
                if not frame.url or frame.url == "about:blank":
                    continue

            try:
                frame_data = await frame.evaluate(
                    _COMBINED_EXTRACT_JS,
                    {
                        "pageUrl": page_url,
                        "framePath": frame_path,
                        "documentUrl": frame.url or page_url,
                    },
                )
            except Exception as exc:
                output.partial = True
                warning = await cls._build_frame_warning(
                    code="frame_extract_failed",
                    page_url=page_url,
                    frame=frame,
                    frame_path=frame_path,
                    message=str(exc),
                    error_type=type(exc).__name__,
                )
                output.warnings.append(warning)
                continue

            for key in combined:
                records = frame_data.get(key) or []
                cls._annotate_records(
                    output=output,
                    category=key,
                    page_url=page_url,
                    frame_path=frame_path,
                    records=records,
                    seen_refs=seen_refs,
                )
                combined[key].extend(records)

            # Separate pass: extract CSS background-image URLs. Kept out of
            # the universal extractor to avoid bloating its single page.evaluate
            # payload (Sprint 3 / step 15).
            try:
                bg_records = await frame.evaluate(
                    _BACKGROUND_IMAGES_JS,
                    {
                        "pageUrl": page_url,
                        "framePath": frame_path,
                        "documentUrl": frame.url or page_url,
                    },
                )
            except Exception:
                bg_records = []
            if bg_records:
                output.background_images.extend(bg_records)

        return combined

    @classmethod
    def _annotate_records(
        cls,
        *,
        output: PageSnapshot,
        category: str,
        page_url: str,
        frame_path: str,
        records: List[Dict[str, Any]],
        seen_refs: set[str] | None = None,
    ) -> None:
        bucket: List[Dict[str, Any]] = getattr(output, category)
        for idx, record in enumerate(records):
            entry = dict(record)
            entry["page_url"] = page_url
            entry.setdefault("frame_path", frame_path)
            entry.setdefault("selector", None)
            ref_id = entry.get("element_ref_id") or cls._make_ref_id(
                category=category,
                page_url=page_url,
                frame_path=frame_path,
                selector=entry.get("selector"),
                element_id=entry.get("id") or entry.get("element_id"),
                html=entry.get("html") or entry.get("html_snippet") or "",
                index=idx,
            )

            # Deduplication for virtualized DOMs (Infinite scroll chunking)
            if seen_refs is not None:
                if ref_id in seen_refs:
                    continue
                seen_refs.add(ref_id)

            entry["element_ref_id"] = ref_id
            bucket.append(entry)
            output.element_refs[ref_id] = {
                "category": category,
                "page_url": page_url,
                "document_url": entry.get("document_url") or page_url,
                "frame_path": frame_path,
                "selector": entry.get("selector"),
                "element_id": entry.get("id") or entry.get("element_id"),
                "tag": entry.get("tag"),
            }

    @classmethod
    async def _extract_links(cls, page: Page, root_url: str) -> List[str]:
        try:
            raw_links: List[str] = await page.evaluate(_LINK_EXTRACT_JS)
        except Exception:
            return []

        resolved: List[str] = []
        for href in raw_links:
            try:
                url = cls._normalize_url(urljoin(page.url or root_url, href))
            except Exception:
                continue
            if not cls._is_same_origin(root_url, url):
                continue
            resolved.append(url)
        return list(dict.fromkeys(resolved))

    @classmethod
    async def _collect_same_origin_frames(
        cls,
        page: Page,
        *,
        page_url: str,
        output: PageSnapshot,
    ) -> List[tuple]:
        frames: List[tuple] = []

        async def walk(frame, path: str) -> None:
            frames.append((frame, path))
            for index, child in enumerate(frame.child_frames):
                child_path = f"{path}.{index}"
                child_url = child.url or ""
                if child_url and not cls._is_same_origin(page_url, child_url):
                    logger.info(
                        f"Skipped cross-origin frame during universal extraction: {child_url}"
                    )
                    output.partial = True
                    continue
                await walk(child, child_path)

        await walk(page.main_frame, "main")
        return frames

    @classmethod
    async def _build_frame_warning(
        cls,
        *,
        code: str,
        page_url: str,
        frame,
        frame_path: str,
        message: str,
        error_type: str | None = None,
    ) -> Dict[str, Any]:
        warning: Dict[str, Any] = {
            "code": code,
            "page_url": page_url,
            "frame_path": frame_path,
            "parent_frame_path": frame_path.rpartition(".")[0] or None,
            "document_url": frame.url or page_url,
            "frame_name": getattr(frame, "name", "") or None,
            "message": message,
        }
        if error_type:
            warning["error_type"] = error_type

        try:
            frame_el = await frame.frame_element()
        except Exception:
            frame_el = None

        if frame_el is None:
            return warning

        try:
            frame_meta = await frame_el.evaluate("""(el) => ({
                    tag: (el.tagName || '').toLowerCase(),
                    id: el.id || null,
                    name_attr: el.getAttribute('name'),
                    title: el.getAttribute('title'),
                    src: el.getAttribute('src'),
                    sandbox: el.getAttribute('sandbox'),
                    loading: el.getAttribute('loading'),
                    referrerpolicy: el.getAttribute('referrerpolicy'),
                    allow: el.getAttribute('allow'),
                    aria_label: el.getAttribute('aria-label'),
                    html_snippet: (el.outerHTML || '').slice(0, 240),
                })""")
        except Exception:
            frame_meta = None

        if isinstance(frame_meta, dict):
            for key, value in frame_meta.items():
                if value not in (None, "", []):
                    warning[key] = value

        return warning

    @staticmethod
    async def _wait_for_spa(page: Page) -> None:
        for signal in _SPA_SIGNALS:
            try:
                found = await page.evaluate(f"() => !!({signal})")
                if found:
                    await page.wait_for_timeout(800)
                    return
            except Exception:
                continue

    @staticmethod
    def _make_ref_id(
        *,
        category: str,
        page_url: str,
        frame_path: str,
        selector: str | None,
        element_id: str | None,
        html: str,
        index: int,
    ) -> str:
        basis = "|".join(
            [
                category,
                page_url,
                frame_path,
                selector or "",
                element_id or "",
                html[:120],
                str(index),
            ]
        )
        digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
        return f"{category}_{digest}"

    @staticmethod
    def _is_same_origin(base_url: str, other_url: str) -> bool:
        if not other_url or other_url.startswith("about:"):
            return True
        base = urlparse(base_url)
        other = urlparse(other_url)

        def default_port(parsed) -> int | None:
            if parsed.port:
                return parsed.port
            if parsed.scheme == "https":
                return 443
            if parsed.scheme == "http":
                return 80
            return None

        return (
            base.scheme == other.scheme
            and base.hostname == other.hostname
            and default_port(base) == default_port(other)
        )

    @staticmethod
    def save_snapshot(snapshot: PageSnapshot, output_dir: Path) -> str:
        path = output_dir / "universal_snapshot_raw.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(snapshot.model_dump(), fh, indent=2, ensure_ascii=False)
        return str(path)
