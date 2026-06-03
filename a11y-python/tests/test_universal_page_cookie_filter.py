from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from a11y.crawler.cookie_handler import handle_cookies
from a11y.crawler.universal_page import PageSnapshot, UniversalPageLoader


@pytest.mark.asyncio
async def test_dismissed_cookie_ui_is_excluded_from_universal_snapshot():
    html = """
    <!doctype html>
    <html lang="en">
      <body>
        <button id="real-action" type="button">Continue</button>

        <div id="onetrust-consent-sdk" role="dialog" aria-label="Cookie consent">
          <form id="cookie-form">
            <input id="cookie-pref" name="cookie-pref" placeholder="Cookie preference" />
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
                  <button
                    id="frame-reject"
                    type="button"
                    onclick="document.getElementById('frame-cookie-banner').style.visibility='hidden'"
                  >
                    Reject All
                  </button>
                </div>
                <button id="frame-real" type="button">Frame CTA</button>
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

            interactive_ids = {item.get("element_id") for item in snapshot.interactive}
            form_ids = {item.get("id") for item in snapshot.forms}

            assert interactive_ids == {"real-action", "frame-real"}
            assert "cookie-pref" not in form_ids
        finally:
            await context.close()
            await browser.close()
