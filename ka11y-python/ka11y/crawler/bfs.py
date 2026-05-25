"""
ka11y/crawler/bfs.py
====================
Shared, memory-bounded breadth-first crawl used by every per-category crawler.

Before this existed, ``media_crawler``, ``forms_crawler``, ``text_spacing_crawler``
and ``interactive_crawler`` each followed links by *recursing* into
``_crawl_page(href, depth + 1)`` with no global page budget. At ``max_depth >= 2``
on a link-heavy site that fans out combinatorially (100 links → 100² → 100³ …)
and exhausts RAM, even though a per-URL ``visited`` set prevented literal cycles.

``bounded_bfs`` replaces that pattern with one iterative queue-based traversal
that every crawler shares. It guarantees:

* a single ``visited`` set (no re-visits, no cycles),
* a hard ``policy.max_pages`` ceiling — the crawl stops after N pages no matter
  the depth, so memory and wall-clock are bounded,
* exact-hostname / internal-link filtering via ``policy.is_allowed`` (this is
  what "internal_links only" means),
* per-page link capping via ``policy.max_links_per_page``,
* every page is always closed, even on extraction error.

The caller supplies a ``visit`` coroutine that navigates + extracts for one page
and returns the raw hrefs found there; the helper owns traversal and budgeting.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Awaitable, Callable, List

from playwright.async_api import BrowserContext, Page

from ka11y.crawler.policy import CrawlPolicy

logger = logging.getLogger(__name__)

# A page-visit callback: given an open page, the normalized URL, and its depth,
# extract whatever the crawler needs and return the list of raw hrefs on the page
# (return [] if links should not be followed from here).
VisitFn = Callable[[Page, str, int], Awaitable[List[str]]]


async def bounded_bfs(
    *,
    context: BrowserContext,
    base_url: str,
    policy: CrawlPolicy,
    visit: VisitFn,
    log_prefix: str = "bfs",
) -> int:
    """Run a memory-bounded, same-origin BFS over a site.

    Parameters
    ----------
    context: a leased Playwright ``BrowserContext`` (one per crawl).
    base_url: the root URL; also the origin all links are filtered against.
    policy: traversal limits (``max_depth``, ``max_pages``,
        ``max_links_per_page``, ``same_origin`` / ``include_subdomains``).
    visit: ``await visit(page, url, depth) -> list[str]`` — extracts data for the
        page and returns hrefs discovered on it.
    log_prefix: tag used in log lines (e.g. ``"media_crawler"``).

    Returns
    -------
    The number of pages actually visited.
    """
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = set()
    pages_done = 0

    while queue:
        raw_url, depth = queue.popleft()
        url = policy.normalize_url(raw_url)
        if not url or url in visited:
            continue
        visited.add(url)

        if not policy.is_allowed(url, base_url):
            # Off-origin / external link — skipped when internal_links is on.
            continue

        if pages_done >= policy.max_pages:
            logger.warning(
                "[%s] page budget reached (%d pages); stopping crawl",
                log_prefix,
                policy.max_pages,
            )
            break

        page = await context.new_page()
        links: List[str] = []
        try:
            links = await visit(page, url, depth) or []
        except Exception as exc:  # noqa: BLE001 — one bad page must not abort the crawl
            logger.error("[%s] error visiting %s: %s", log_prefix, url, exc)
            links = []
        finally:
            try:
                await page.close()
            except Exception:  # noqa: BLE001
                logger.debug("[%s] page close raised for %s", log_prefix, url, exc_info=True)

        pages_done += 1

        if depth < policy.max_depth:
            enqueued = 0
            for href in links:
                if enqueued >= policy.max_links_per_page:
                    break
                nxt = policy.normalize_url(href)
                if nxt and nxt not in visited and policy.is_allowed(nxt, base_url):
                    queue.append((nxt, depth + 1))
                    enqueued += 1

    logger.info("[%s] crawl complete: %d page(s) visited", log_prefix, pages_done)
    return pages_done
