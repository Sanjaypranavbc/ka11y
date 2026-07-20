from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from ka11y.crawler.cookie_handler import handle_cookies
from ka11y.crawler.universal_page import PageSnapshot, UniversalPageLoader


@pytest.mark.asyncio
async def test_dismissed_cookie_ui_is_excluded_from_universal_snapshot():
    html = """
    <!doctype html>
    <html lang="en">
      <body>
        <audio id="real-action" controls src="real.mp3"></audio>

        <div id="onetrust-consent-sdk" role="dialog" aria-label="Cookie consent">
          <form id="cookie-form">
            <audio id="cookie-audio" controls src="cookie.mp3"></audio>
            <button
              id="onetrust-reject-all-handler"
              type="button"
              onclick="document.getElementById('onetrust-consent-sdk').style.display='none'"
            >
              Reject All
            </button>
          </form>
        </div>

        <iframe id="cmp-frame" title="cmp-frame"></iframe>
        <script>
          const frame = document.getElementById('cmp-frame');
          const doc = frame.contentWindow.document;
          doc.open();
          doc.write(`
            <!doctype html>
            <html lang="en">
              <body>
                <div id="frame-cookie-banner" class="cookie-banner" role="dialog" aria-label="Cookie banner">
                  <audio id="frame-cookie-audio" controls src="framecookie.mp3"></audio>
                  <button
                    id="frame-reject"
                    type="button"
                    onclick="document.getElementById('frame-cookie-banner').style.visibility='hidden'"
                  >
                    Reject All
                  </button>
                </div>
                <audio id="frame-real" controls src="framereal.mp3"></audio>
              </body>
            </html>
          `);
          doc.close();
        </script>
      </body>
    </html>
    """

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover - environment-specific fallback
            pytest.skip(f"Chromium not available for universal snapshot cookie test: {exc}")

        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content(html, wait_until="domcontentloaded")
            await page.wait_for_timeout(100)

            state = await handle_cookies(page)
            assert state == "rejected"

            snapshot = PageSnapshot(page_url="http://example.com")
            await UniversalPageLoader._extract_page(
                page,
                page_url="http://example.com",
                output=snapshot,
            )

            media_ids = {item.get("element_id") for item in snapshot.media}

            assert media_ids == {"real-action", "frame-real"}
            assert "cookie-audio" not in media_ids
            assert "frame-cookie-audio" not in media_ids
        finally:
            await context.close()
            await browser.close()
