"""
ka11y/crawler/context_factory.py
================================
The one place a crawler ``BrowserContext`` is configured.

Every pooled context gets, in order:

1. ``ignore_https_errors`` from ``config.browser`` (overridable per call);
2. the anti-bot **stealth** profile — a real Chrome UA, a realistic locale and
   timezone, and an init script that patches the automation tells
   (``navigator.webdriver``, missing ``window.chrome`` / plugins / mimeTypes).
   Sites behind Akamai / Cloudflare / PerimeterX fingerprint exactly those and
   serve a "Just a moment…" challenge page instead of the real page — which
   then audits as an almost-empty document with no findings. This used to live
   only in the standalone image engine; the universal loader (now the one
   crawler on the combined path) must present the same fingerprint;
3. the SSRF route guard.

Callers may still pass any ``new_context`` kwarg (``viewport``,
``user_agent``, ``record_har_path`` …); explicit values win over the defaults.
"""

from __future__ import annotations

from typing import Any

from ka11y.crawler._ssrf_guard import install_ssrf_guard
from ka11y.utils.config_loader import load_config

# ── Anti-bot stealth (ported from meghana-v2 crawler/stealth_context.py) ─────
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--window-size=1366,900",
]
STEALTH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
STEALTH_LOCALE = "en-US"
STEALTH_TIMEZONE = "America/New_York"
STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
if (!window.chrome) {
    window.chrome = { runtime: { connect: () => {}, sendMessage: () => {} },
                      loadTimes: function(){ return {}; }, csi: function(){ return {}; }, app: {} };
}
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', { get: () => {
        const arr = [
            { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
            { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n) || null;
        arr.refresh = () => {};
        return arr;
    }, configurable: true });
}
if (navigator.mimeTypes.length === 0) {
    Object.defineProperty(navigator, 'mimeTypes', { get: () => {
        const arr = [
            { type: 'application/pdf', description: 'Portable Document Format' },
            { type: 'text/pdf', description: 'Portable Document Format' },
        ];
        arr.item = (i) => arr[i];
        arr.namedItem = (t) => arr.find(m => m.type === t) || null;
        return arr;
    }, configurable: true });
}
if (!navigator.languages || navigator.languages.length === 0) {
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'], configurable: true });
}
"""


def should_ignore_https_errors() -> bool:
    config = load_config()
    raw = config.get("browser", {}).get("ignore_https_errors", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


async def new_crawler_context(browser, **kwargs: Any):
    context_kwargs = dict(kwargs)
    context_kwargs.setdefault("ignore_https_errors", should_ignore_https_errors())
    context_kwargs.setdefault("user_agent", STEALTH_UA)
    context_kwargs.setdefault("locale", STEALTH_LOCALE)
    context_kwargs.setdefault("timezone_id", STEALTH_TIMEZONE)
    context = await browser.new_context(**context_kwargs)
    # The init script must be registered before any page in this context runs
    # site JS, which is why it is done here and not by individual crawlers.
    add_init_script = getattr(context, "add_init_script", None)
    if add_init_script is not None:
        await add_init_script(STEALTH_INIT_SCRIPT)
    await install_ssrf_guard(context)
    return context
