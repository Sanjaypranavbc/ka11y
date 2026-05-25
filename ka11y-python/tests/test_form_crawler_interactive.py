"""
Tests for AsyncFormCrawler's interactive-validation pass (WCAG 3.3.1 fix J).

The crawler, when constructed with `interactive_validation=True`, must:
  • trigger a non-navigating submit on every form so JS validation renders;
  • block network traffic during that pass;
  • re-extract and surface dynamically-added error state (aria-invalid,
    error-message text, live regions).
"""
from __future__ import annotations

import pytest
from playwright.async_api import async_playwright

from ka11y.crawler.forms_crawler import AsyncFormCrawler


_HTML_DYNAMIC_REQUIRED = """
<!doctype html>
<html lang="en">
  <body>
    <form id="contact" novalidate>
      <label for="email">Email</label>
      <input id="email" name="email" type="email" required
             aria-errormessage="email-err" autocomplete="email">
      <span id="email-err" role="alert"></span>
      <button id="submit" type="submit">Send</button>
    </form>
    <script>
      // Form is fetched and validated entirely client-side. On submit, we
      // mark the field invalid and populate the error region only if the
      // value is missing — exactly the dynamic pattern static crawls miss.
      document.getElementById('contact').addEventListener('submit', function (e) {
        const input = document.getElementById('email');
        const err = document.getElementById('email-err');
        if (!input.value) {
          input.setAttribute('aria-invalid', 'true');
          err.textContent = 'Email is required.';
        }
      });
    </script>
  </body>
</html>
"""


@pytest.mark.asyncio
async def test_interactive_pass_surfaces_dynamic_aria_invalid(tmp_path):
    crawler = AsyncFormCrawler(
        base_url="http://example.com",
        output_dir=str(tmp_path),
        interactive_validation=True,
    )

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content(_HTML_DYNAMIC_REQUIRED, wait_until="domcontentloaded")
            await page.wait_for_timeout(100)

            # Confirm the static extractor does NOT yet see the error state.
            static_raw = await page.evaluate(AsyncFormCrawler.EXTRACT_JS)
            assert len(static_raw) == 1
            assert static_raw[0]["aria_invalid"] is None
            assert not (static_raw[0]["errormessage_element_text"] or "").strip()

            # Now exercise the interactive pass.
            dynamic_raw = await crawler._capture_dynamic_errors(page, static_raw)
            assert len(dynamic_raw) == 1
            row = dynamic_raw[0]
            assert row["aria_invalid"] == "true"
            assert "Email is required" in (row["errormessage_element_text"] or "")
            assert row["errormessage_is_live"] is True
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def test_interactive_pass_blocks_real_network_submission(tmp_path):
    """
    A form with action=URL must not actually post to that URL during the
    interactive pass — both the JS preventDefault and the Playwright route
    blocker should keep validation purely local.
    """
    seen_post_urls: list[str] = []

    html = """
    <!doctype html>
    <html><body>
      <form id="login" action="https://evil.example.com/submit" method="POST">
        <label for="u">User</label>
        <input id="u" name="user" required>
        <button type="submit">Go</button>
      </form>
    </body></html>
    """

    crawler = AsyncFormCrawler(
        base_url="http://example.com",
        output_dir=str(tmp_path),
        interactive_validation=True,
    )

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        page = await context.new_page()

        def _record(request):
            if request.method == "POST":
                seen_post_urls.append(request.url)

        page.on("request", _record)

        try:
            await page.set_content(html, wait_until="domcontentloaded")
            static_raw = await page.evaluate(AsyncFormCrawler.EXTRACT_JS)
            await crawler._capture_dynamic_errors(page, static_raw)
            assert seen_post_urls == []
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def test_excludes_submit_buttons_and_disabled_inputs(tmp_path):
    """Fix D: buttons and disabled inputs must not be audited as form fields."""
    html = """
    <!doctype html>
    <html><body>
      <form>
        <label for="ok">OK</label>
        <input id="ok" name="ok" type="text">
        <input id="disabled-input" name="disabled-input" type="text" disabled>
        <input type="submit" value="Submit">
        <input type="reset" value="Reset">
        <input type="button" value="Click">
        <input type="image" alt="img-button">
        <input type="file" name="upload">
        <button type="submit">Send</button>
      </form>
    </body></html>
    """

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content(html, wait_until="domcontentloaded")
            raw = await page.evaluate(AsyncFormCrawler.EXTRACT_JS)
            names = [r["name"] for r in raw]
            assert names == ["ok"], f"expected only ['ok'], got {names}"
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def test_aria_labelledby_must_resolve_to_nonempty_text(tmp_path):
    """Fix G: a broken aria-labelledby reference must not count as a label."""
    html = """
    <!doctype html>
    <html><body>
      <form>
        <input id="a" name="a" aria-labelledby="missing-id">
        <input id="b" name="b" aria-labelledby="real-label">
        <span id="real-label">Username</span>
      </form>
    </body></html>
    """

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content(html, wait_until="domcontentloaded")
            raw = await page.evaluate(AsyncFormCrawler.EXTRACT_JS)
            by_name = {r["name"]: r for r in raw}
            assert by_name["a"]["has_any_label"] is False
            assert by_name["b"]["has_any_label"] is True
            assert by_name["b"]["label_text"] == "Username"
        finally:
            await context.close()
            await browser.close()


@pytest.mark.asyncio
async def test_fieldset_legend_counts_as_label_for_radio(tmp_path):
    """Fix I: a <fieldset><legend> wrapping radios provides the group name."""
    html = """
    <!doctype html>
    <html><body>
      <form>
        <fieldset>
          <legend>Subscription</legend>
          <input id="r1" name="plan" type="radio" value="free">
          <input id="r2" name="plan" type="radio" value="paid">
        </fieldset>
      </form>
    </body></html>
    """

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"Chromium not available: {exc}")

        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.set_content(html, wait_until="domcontentloaded")
            raw = await page.evaluate(AsyncFormCrawler.EXTRACT_JS)
            assert len(raw) == 2
            for row in raw:
                assert row["has_any_label"] is True
                assert row["group_legend_text"] == "Subscription"
        finally:
            await context.close()
            await browser.close()
