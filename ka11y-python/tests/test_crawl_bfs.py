"""
tests/test_crawl_bfs.py
=======================
Regression tests for the memory-bounded, same-host crawl that backs max_depth in
the Python engine: ``ka11y.crawler.bfs.bounded_bfs`` and the ``CrawlPolicy`` scope
rules it relies on. These run fully offline (a fake BrowserContext/Page), so they
pin the traversal contract without launching Chromium.

Contract under test:
  * max_depth gates how many link-hops are followed (0 = root only),
  * max_pages is a hard ceiling so a deep, link-heavy site can't exhaust RAM,
  * only exact-hostname (same-domain) links are followed — never subdomains or
    external hosts,
  * every opened page is closed, and link cycles never loop forever.
"""

from __future__ import annotations

import pytest

from ka11y.crawler.bfs import bounded_bfs
from ka11y.crawler.policy import CrawlPolicy


class _FakePage:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class _FakeContext:
    """Minimal stand-in for a Playwright BrowserContext (only needs new_page)."""

    def __init__(self):
        self.opened: list[_FakePage] = []

    async def new_page(self):
        page = _FakePage()
        self.opened.append(page)
        return page


def _make_visit(links_by_url: dict[str, list[str]], visited: list):
    async def visit(page, url, depth):
        visited.append((url, depth))
        return links_by_url.get(url, [])

    return visit


@pytest.mark.asyncio
async def test_depth_zero_visits_only_root():
    ctx = _FakeContext()
    visited: list = []
    visit = _make_visit(
        {"https://example.com": ["https://example.com/a", "https://example.com/b"]},
        visited,
    )
    policy = CrawlPolicy(max_depth=0, max_pages=50)

    n = await bounded_bfs(
        context=ctx, base_url="https://example.com", policy=policy, visit=visit
    )

    assert n == 1
    assert visited == [("https://example.com", 0)]


@pytest.mark.asyncio
async def test_depth_one_follows_same_host_and_skips_external():
    ctx = _FakeContext()
    visited: list = []
    visit = _make_visit(
        {
            "https://example.com": [
                "https://example.com/a",
                "https://evil.com/x",          # external — must be skipped
                "https://blog.example.com/y",  # subdomain — must be skipped
                "https://example.com/b",
            ],
            "https://example.com/a": ["https://example.com/c"],  # depth 2 — not visited
        },
        visited,
    )
    policy = CrawlPolicy(max_depth=1, max_pages=50)

    n = await bounded_bfs(
        context=ctx, base_url="https://example.com", policy=policy, visit=visit
    )

    visited_urls = [u for u, _ in visited]
    assert visited_urls == [
        "https://example.com",
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert n == 3
    assert "https://evil.com/x" not in visited_urls
    assert "https://blog.example.com/y" not in visited_urls
    assert "https://example.com/c" not in visited_urls


@pytest.mark.asyncio
async def test_max_pages_bounds_a_deep_fanout_crawl():
    ctx = _FakeContext()
    visited: list = []

    async def visit(page, url, depth):
        visited.append(url)
        # Each page fans out to 10 fresh same-host links → unbounded without the cap.
        return [f"https://example.com/{len(visited)}-{i}" for i in range(10)]

    policy = CrawlPolicy(max_depth=5, max_pages=3)

    n = await bounded_bfs(
        context=ctx, base_url="https://example.com", policy=policy, visit=visit
    )

    assert n == 3
    assert len(visited) == 3


@pytest.mark.asyncio
async def test_link_cycle_does_not_loop_forever():
    ctx = _FakeContext()
    visited: list = []
    visit = _make_visit(
        {
            "https://example.com": ["https://example.com/a"],
            "https://example.com/a": ["https://example.com"],  # back-edge
        },
        visited,
    )
    policy = CrawlPolicy(max_depth=10, max_pages=50)

    n = await bounded_bfs(
        context=ctx, base_url="https://example.com", policy=policy, visit=visit
    )

    assert n == 2
    assert [u for u, _ in visited] == ["https://example.com", "https://example.com/a"]


@pytest.mark.asyncio
async def test_pages_are_always_closed_even_when_visit_raises():
    ctx = _FakeContext()

    async def visit(page, url, depth):
        raise RuntimeError("extraction blew up")

    policy = CrawlPolicy(max_depth=0, max_pages=50)

    n = await bounded_bfs(
        context=ctx, base_url="https://example.com", policy=policy, visit=visit
    )

    assert n == 1  # the page still counts as visited
    assert ctx.opened and all(p.closed for p in ctx.opened)


def test_crawl_policy_exact_host_scope():
    policy = CrawlPolicy(same_origin=True, include_subdomains=False)
    base = "https://example.com"
    assert policy.is_allowed("https://example.com/path", base) is True
    assert policy.is_allowed("https://blog.example.com/x", base) is False
    assert policy.is_allowed("https://other.com/x", base) is False


def test_crawl_policy_subdomains_opt_in():
    policy = CrawlPolicy(same_origin=True, include_subdomains=True)
    base = "https://example.com"
    assert policy.is_allowed("https://blog.example.com/x", base) is True
    assert policy.is_allowed("https://other.com/x", base) is False
