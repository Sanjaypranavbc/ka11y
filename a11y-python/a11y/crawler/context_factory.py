from __future__ import annotations

from typing import Any

from a11y.crawler._ssrf_guard import install_ssrf_guard
from a11y.utils.config_loader import load_config


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
    context = await browser.new_context(**context_kwargs)
    await install_ssrf_guard(context)
    return context
