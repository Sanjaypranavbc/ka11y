"""
a11y/crawler/stealth_context.py
==================================
Anti-bot stealth browser context factory.

Many high-profile websites (Domino's, Barnes & Noble, etc.) use bot-detection
middleware (Akamai Bot Manager, Cloudflare, PerimeterX) that fingerprints:

  1. ``navigator.webdriver`` — set to ``true`` by default in Playwright
  2. Missing Chrome-specific window globals (``window.chrome``, ``window.cdc_*``)
  3. HTTP/2 aggressive push behaviour (Akamai blocks ERR_HTTP2_PROTOCOL_ERROR)
  4. HeadlessChrome substring in the UA string
  5. Missing browser plugins array

``create_stealth_context()`` patches all of these in a single call and returns
a ready-to-use Playwright ``BrowserContext`` with SSRF guard installed.

Usage::

    from a11y.crawler.stealth_context import launch_stealth_browser, create_stealth_context

    browser = await launch_stealth_browser(pw)
    context = await create_stealth_context(browser, width=1440, height=900)
    # context is ready — SSRF guard already installed
    page = await context.new_page()
    ...
    await context.close()
    await browser.close()
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from a11y.crawler._ssrf_guard import install_ssrf_guard

# ---------------------------------------------------------------------------
# Chrome UA without "Headless" substring — passes basic UA checks
# ---------------------------------------------------------------------------
_STEALTH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Init script: patches navigator.webdriver and missing Chrome globals
# Injected before any page script runs so it cannot be detected via timing.
# ---------------------------------------------------------------------------
_STEALTH_INIT_SCRIPT = """
// 1. Remove the webdriver property that Playwright sets
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true,
});

// 2. Add window.chrome with a minimal runtime object
if (!window.chrome) {
    window.chrome = {
        runtime: {
            connect: () => {},
            sendMessage: () => {},
        },
        loadTimes: function() { return {}; },
        csi: function() { return {}; },
        app: {},
    };
}

// 3. Restore navigator.plugins to a non-empty list
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [
                { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
                { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
            ];
            arr.item = (i) => arr[i];
            arr.namedItem = (n) => arr.find(p => p.name === n) || null;
            arr.refresh = () => {};
            return arr;
        },
        configurable: true,
    });
}

// 4. Restore navigator.mimeTypes
if (navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => {
            const arr = [
                { type: 'application/pdf', description: 'Portable Document Format' },
                { type: 'text/pdf', description: 'Portable Document Format' },
            ];
            arr.item = (i) => arr[i];
            arr.namedItem = (t) => arr.find(m => m.type === t) || null;
            return arr;
        },
        configurable: true,
    });
}

// 5. Override languages if not set
if (!navigator.languages || navigator.languages.length === 0) {
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
        configurable: true,
    });
}
"""


async def launch_stealth_browser(pw, *, http2: bool = True):
    """
    Launch a Chromium browser with stealth launch args.

    Parameters
    ----------
    pw:
        The ``async_playwright()`` playwright instance.
    http2:
        Set to ``False`` to disable HTTP/2 (needed for Akamai-protected sites
        like barnesandnoble.com that return ERR_HTTP2_PROTOCOL_ERROR).
    """
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        # Remove automation-specific blink features used for detection
        "--disable-blink-features=AutomationControlled",
        # Suppress "Chrome is being controlled by automated software" banner
        "--disable-infobars",
        # Consistent window/screen dimensions
        "--window-size=1440,900",
    ]
    if not http2:
        args.append("--disable-http2")

    return await pw.chromium.launch(
        headless=True,
        args=args,
    )


async def create_stealth_context(
    browser,
    *,
    width: int = 1440,
    height: int = 900,
    record_har_path: Optional[str] = None,
    storage_state: Optional[Any] = None,
    extra_http_headers: Optional[Dict[str, str]] = None,
) -> Any:
    """
    Create a Playwright BrowserContext with:
      - Stealth UA (no "HeadlessChrome")
      - navigator.webdriver patched out
      - window.chrome / plugins / mimeTypes restored
      - SSRF guard installed
      - Optional HAR recording
      - Optional cookie/session state injection

    Returns the context ready for ``context.new_page()``.
    """
    kwargs: Dict[str, Any] = dict(
        viewport={"width": width, "height": height},
        user_agent=_STEALTH_UA,
        # Tell the server we accept modern content
        locale="en-US",
        timezone_id="America/New_York",
        # Emulate a real desktop
        is_mobile=False,
        has_touch=False,
        java_script_enabled=True,
        ignore_https_errors=True,
    )

    if record_har_path:
        kwargs["record_har_path"] = record_har_path
        kwargs["record_har_url_filter"] = "**/*"

    if storage_state is not None:
        kwargs["storage_state"] = storage_state

    if extra_http_headers:
        kwargs["extra_http_headers"] = extra_http_headers

    context = await browser.new_context(**kwargs)

    # Inject the stealth script before any page-level JS runs
    await context.add_init_script(_STEALTH_INIT_SCRIPT)

    # Install SSRF guard
    await install_ssrf_guard(context)

    return context
