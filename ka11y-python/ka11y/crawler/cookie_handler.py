import logging
import re
from typing import Union

from playwright.async_api import Frame, Page

logger = logging.getLogger(__name__)

CookieContext = Union[Page, Frame]


_CLICK_TIMEOUT_MS = 1500
_STABILIZE_DELAY_MS = 800

_REJECT_PATTERN = re.compile(
    r"^(reject|decline|no\s*thanks|continue\s*without|deny|reject\s*all|decline\s*all)$",
    re.IGNORECASE,
)
_ACCEPT_PATTERN = re.compile(
    r"^(accept|agree|allow|got\s*it|i\s*accept|accept\s*all|allow\s*all)$",
    re.IGNORECASE,
)

_OVERLAY_SELECTORS = [
    "#onetrust-consent-sdk",
    "#onetrust-banner-sdk",
    ".cc-window",
    ".cookie-banner",
    "[id*='cookie-banner']",
    "[id*='cookiebanner']",
    "[id*='consent-banner']",
    "[id*='cookie']",
    "[id*='consent']",
    "[class*='cookie-banner']",
    "[class*='cookiebanner']",
    "[class*='consent-banner']",
    "[class*='cookie']",
    "[class*='consent']",
    ".optanon-alert-box-wrapper",
    ".onetrust-pc-dark-filter",
    ".qc-cmp2-container",
    ".didomi-popup-container",
    "#CybotCookiebotDialog",
]


def _iter_cookie_contexts(page: Page) -> list[CookieContext]:
    contexts: list[CookieContext] = [page]

    def walk(frame: Frame) -> None:
        for child in frame.child_frames:
            contexts.append(child)
            walk(child)

    walk(page.main_frame)
    return contexts


async def _click_first_match(
    context: CookieContext,
    *,
    pattern: re.Pattern[str],
    explicit_selector: str,
) -> bool:
    candidates = [
        context.get_by_role("button", name=pattern).first,
        context.locator("button, a, input[type='button'], input[type='submit'], [role='button']").filter(
            has_text=pattern
        ).first,
        context.locator(explicit_selector).first,
    ]

    for locator in candidates:
        try:
            if await locator.is_visible(timeout=500):
                await locator.click(timeout=_CLICK_TIMEOUT_MS)
                return True
        except Exception:
            continue
    return False


async def _cleanup_cookie_overlays(contexts: list[CookieContext]) -> bool:
    removed_any = False
    for context in contexts:
        for selector in _OVERLAY_SELECTORS:
            try:
                for element in await context.locator(selector).all():
                    try:
                        if await element.is_visible(timeout=100):
                            await element.evaluate("node => node.remove()")
                            removed_any = True
                    except Exception:
                        continue
            except Exception:
                continue
    return removed_any


async def handle_cookies(page: Page) -> str:
    """
    Attempts to handle cookie consent banners safely without crashing.
    Prioritizes rejecting cookies, falls back to accepting, then optionally
    removes overlay backdrops if neither worked but a banner is suspected.
    Returns: "rejected", "accepted", "removed", "none", or "error".
    """
    try:
        contexts = _iter_cookie_contexts(page)

        rejected_any = False
        for context in contexts:
            rejected_any = await _click_first_match(
                context,
                pattern=_REJECT_PATTERN,
                explicit_selector="#onetrust-reject-all-handler, .cookie-reject, #W0wltc",
            ) or rejected_any

        if rejected_any:
            await page.wait_for_timeout(_STABILIZE_DELAY_MS)
            await _cleanup_cookie_overlays(contexts)
            logger.debug("[cookie_handler] Rejected cookies across available contexts")
            return "rejected"

        accepted_any = False
        for context in contexts:
            accepted_any = await _click_first_match(
                context,
                pattern=_ACCEPT_PATTERN,
                explicit_selector="#onetrust-accept-btn-handler, .cookie-accept, #L2AGLb",
            ) or accepted_any

        if accepted_any:
            await page.wait_for_timeout(_STABILIZE_DELAY_MS)
            await _cleanup_cookie_overlays(contexts)
            logger.debug("[cookie_handler] Accepted cookies across available contexts")
            return "accepted"

        removed_any = await _cleanup_cookie_overlays(contexts)
        if removed_any:
            logger.debug("[cookie_handler] Removed cookie overlays from DOM")
            return "removed"

        return "none"

    except Exception as e:
        logger.debug(f"[cookie_handler] Cookie handling error: {e}")
        return "error"
