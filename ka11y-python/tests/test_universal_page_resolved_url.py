"""
Resolved-URL stamping regression (max-depth a1/a2 child findings-loss).
==========================================================================
A child page reached inside a depth>0 crawl is identified by
``element.page_url``. The crawler discovers links by href (``/child``) but the
server may 301 that to a different path (``/child.html``). When the same child
is audited directly the caller passes the resolved form. If the snapshot stamps
the *requested* href, that one child's findings split across two page_url
buckets — half from the Python pipeline, half from Node — so the page looks like
it lost findings.

The fix (universal_page._crawl_one_url + Node _auditPageFlat) stamps the
resolved ``page.url()`` instead. This test serves a real local site with a
``/child`` → ``/child.html`` redirect and asserts the snapshot records the
resolved URL.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from playwright.async_api import async_playwright

from ka11y.crawler.policy import CrawlPolicy
from ka11y.crawler.universal_page import PageSnapshot, UniversalPageLoader
from ka11y.utils.url_canonical import canonicalize_url

_PARENT_HTML = b"""<!doctype html>
<html lang="en"><body>
  <h1>Parent</h1>
  <a href="/child">Go to child</a>
</body></html>"""

# Child carries a deliberate a11y signal (img with no alt) so extraction has
# something to record on the resolved page.
_CHILD_HTML = b"""<!doctype html>
<html lang="en"><body>
  <h1>Child</h1>
  <img src="/x.png">
  <button onclick="void 0">Click</button>
</body></html>"""


class _RedirectHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence the test output
        pass

    def do_GET(self):
        if self.path == "/parent":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_PARENT_HTML)
        elif self.path == "/child":
            # The crux: /child permanently redirects to /child.html.
            self.send_response(301)
            self.send_header("Location", "/child.html")
            self.end_headers()
        elif self.path == "/child.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_CHILD_HTML)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture
def redirect_server():
    server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_child_page_stamped_with_resolved_url(redirect_server):
    requested = f"{redirect_server}/child"          # what the crawler queues
    resolved = canonicalize_url(f"{redirect_server}/child.html")  # where it lands

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover - environment-specific
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        snapshot = PageSnapshot(page_url=requested)
        policy = CrawlPolicy(max_depth=0, max_pages=5, max_links_per_page=10)
        try:
            await UniversalPageLoader._crawl_one_url(
                context=context,
                root_url=requested,
                url=requested,
                depth=0,
                policy=policy,
                output=snapshot,
                step_logger=None,
            )
        finally:
            await context.close()
            await browser.close()

    assert snapshot.page_summaries, "crawl recorded no page summary"
    stamped = snapshot.page_summaries[0]["page_url"]
    # The page redirected, so the snapshot must record the RESOLVED url, never
    # the requested href — otherwise this page's findings split from the
    # direct-audit bucket.
    assert stamped == resolved, f"expected resolved {resolved!r}, got {stamped!r}"
    assert stamped != canonicalize_url(requested)
