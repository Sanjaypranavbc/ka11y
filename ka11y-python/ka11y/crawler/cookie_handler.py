import logging
import re
from typing import Union

from playwright.async_api import Frame, Page

logger = logging.getLogger(__name__)

CookieContext = Union[Page, Frame]


_CLICK_TIMEOUT_MS = 1500
_STABILIZE_DELAY_MS = 800

# ---------------------------------------------------------------------------
# Reject patterns — matched against button/link visible text (exact-word).
# Ordered broadest → most specific so a single re.search() is sufficient.
# The pattern deliberately does NOT include "accept" variants — this handler
# ONLY rejects, never accepts (by design, so captured UIs reflect the
# "cookies rejected" state for accessibility audits).
# ---------------------------------------------------------------------------
_REJECT_PATTERN = re.compile(
    r"(?:^|\b)("
    r"reject(\s+all)?|decline(\s+all)?|deny"
    r"|no[,\s]+thanks?"
    r"|continue\s+without(\s+accepting)?"
    r"|necessary(\s+only|cookies?\s+only)?"
    r"|essential(\s+only|cookies?\s+only)?"
    r"|required(\s+only)?"
    r"|save\s+(?:my\s+)?(?:preferences|settings|choices)"
    r"|manage\s+(?:preferences|settings|choices)"
    r"|do\s+not\s+(accept|consent|agree|sell|share)"
    r"|opt[\s-]out"
    r"|use\s+necessary(\s+only)?"
    r")(?:\b|$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Framework-specific explicit selectors (highest-signal, checked before text
# matching):
#   OneTrust  — #onetrust-reject-all-handler
#   Cookiebot — #CybotCookiebotDialogBodyButtonDecline
#   Quantcast — #qc-cmp2-ui .qc-cmp2-reject-all (varies; text-match catches it)
#   Google    — #W0wltc (GDPR rejection handler on Google services)
#   Didomi   — .didomi-refuse-all-button, button[id*=reject i]
#   TrustArc / OneTrust legacy — .cookie-reject, .truste_em_decline
# ---------------------------------------------------------------------------
_EXPLICIT_REJECT_SELECTORS = (
    "#onetrust-reject-all-handler,"
    "#CybotCookiebotDialogBodyButtonDecline,"
    ".didomi-refuse-all-button,"
    "[id*='reject-all' i],"
    "[id*='rejectAll' i],"
    "[class*='reject-all' i],"
    "[class*='rejectAll' i],"
    ".cookie-reject,"
    ".truste_em_decline,"
    "#W0wltc,"
    "[data-testid*='reject' i],"
    "[aria-label*='reject' i],"
    "[aria-label*='decline' i]"
)

# ---------------------------------------------------------------------------
# Overlay / backdrop selectors that should be removed from the DOM after any
# attempt (whether a reject button was clicked or not). Keeping these in a
# separate cleanup pass handles sites that animate banners out slowly or keep
# the backdrop element even after accepting/rejecting.
# ---------------------------------------------------------------------------
_OVERLAY_SELECTORS = [
    "#onetrust-consent-sdk",
    "#onetrust-banner-sdk",
    "#CybotCookiebotDialog",
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
    "#onetrust-pc-sdk",               # OneTrust preference-centre modal
    "#ot-sdk-btn-floating",           # OneTrust persistent "Cookie Settings" launcher
    ".ot-floating-button",
    ".qc-cmp2-container",
    ".didomi-popup-container",
    ".trustarc-banner-container",
    "[id*='sp_message_container']",   # SourcePoint CMP
    "[class*='sp-message']",          # SourcePoint CMP
    "[class*='cmpbox']",              # CMP generic
]


def _iter_cookie_contexts(page: Page) -> list[CookieContext]:
    """Return the page + all nested frames (consent banners often live in iframes)."""
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
    """
    Try up to four strategies to find and click a reject button in *context*.
    Returns True on the first successful click.

    Order of precedence (highest-signal first):
      1. Explicit CSS selectors for well-known CMPs
      2. ARIA role=button with text matching the pattern
      3. Any button/link/input whose visible text matches the pattern
    """
    candidates = [
        # 1. Framework-specific selectors (most reliable)
        context.locator(explicit_selector).first,
        # 2. ARIA role=button with text match
        context.get_by_role("button", name=pattern).first,
        # 3. Broad interactive-element text match
        context.locator(
            "button, a[href], input[type='button'], input[type='submit'], [role='button']"
        )
        .filter(has_text=pattern)
        .first,
        # 4. Any element with role=button or role=link and matching text
        context.locator("[role='button'], [role='link']")
        .filter(has_text=pattern)
        .first,
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
    """
    Force-remove any remaining consent overlay elements from the DOM.
    This runs after every attempt so backdrop divs don't contaminate screenshots
    even when no reject button was found.
    """
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
    Reject cookie-consent banners before any screenshot or image capture.

    Strategy (reject-only — never accepts):
      1. Try framework-specific reject selectors + text-pattern matching in
         every frame context (main frame + iframes).
      2. If a reject button was clicked, wait for the banner animation to
         settle, then strip any leftover overlay elements from the DOM.
      3. If no reject button was found, fall back to forcefully removing the
         overlay elements from the DOM so they cannot cover the page content.

    Returns one of: "rejected" | "removed" | "none" | "error"

    NOTE: The old "accepted" fallback path has been intentionally removed.
    Captured screenshots must reflect the cookies-rejected state so that
    accessibility audits see the real page, not a consent-gated shell.
    """
    try:
        contexts = _iter_cookie_contexts(page)

        rejected_any = False
        for context in contexts:
            rejected_any = (
                await _click_first_match(
                    context,
                    pattern=_REJECT_PATTERN,
                    explicit_selector=_EXPLICIT_REJECT_SELECTORS,
                )
                or rejected_any
            )

        if rejected_any:
            await page.wait_for_timeout(_STABILIZE_DELAY_MS)
            await _cleanup_cookie_overlays(contexts)
            logger.debug("[cookie_handler] Rejected cookies across available contexts")
            return "rejected"

        # No explicit reject button found — forcefully remove overlays so they
        # don't cover page content in screenshots.
        removed_any = await _cleanup_cookie_overlays(contexts)
        if removed_any:
            logger.debug("[cookie_handler] Removed cookie overlays from DOM (no reject button found)")
            return "removed"

        return "none"

    except Exception as e:
        logger.debug(f"[cookie_handler] Cookie handling error: {e}")
        return "error"
