import logging
import re
from playwright.async_api import Page

logger = logging.getLogger(__name__)

async def handle_cookies(page: Page) -> str:
    """
    Attempts to handle cookie consent banners safely without crashing.
    Prioritizes rejecting cookies, falls back to accepting, then optionally
    removes overlay backdrops if neither worked but a banner is suspected.
    Returns: "rejected", "accepted", "removed", "none", or "error".
    """
    # Use short timeouts for cookie banner checks
    click_timeout = 1500
    stabilize_delay = 800

    # Compiled regexes for common buttons (case-insensitive)
    reject_pattern = re.compile(
        r"^(reject|decline|no\s*thanks|continue\s*without|deny|reject\s*all|decline\s*all)$", 
        re.IGNORECASE
    )
    accept_pattern = re.compile(
        r"^(accept|agree|allow|got\s*it|i\s*accept|accept\s*all|allow\s*all)$", 
        re.IGNORECASE
    )
    
    # Common backdrop/overlay classes to hide if clicking fails
    overlay_selectors = [
        "#onetrust-consent-sdk",
        ".cc-window",
        ".cookie-banner",
        "[id*='cookie-banner']",
        "[id*='cookiebanner']",
        "[id*='consent-banner']",
        "[class*='cookie-banner']",
        "[class*='cookiebanner']",
        "[class*='consent-banner']",
        ".optanon-alert-box-wrapper",
        "#CybotCookiebotDialog"
    ]

    try:
        # 1. Try rejecting first via common accessibility roles
        try:
            reject_btn = page.get_by_role("button", name=reject_pattern).first
            if await reject_btn.is_visible(timeout=1000):
                await reject_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Rejected cookies via ARIA role")
                return "rejected"
        except Exception:
            pass

        # 2. Try rejecting via generic text fallback
        try:
            reject_btn = page.locator("button, a, [role='button']").filter(has_text=reject_pattern).first
            if await reject_btn.is_visible(timeout=500):
                await reject_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Rejected cookies via generic text")
                return "rejected"
        except Exception:
            pass
            
        # 3. Try standard reject IDs/Classes
        try:
            reject_btn = page.locator("#onetrust-reject-all-handler, .cookie-reject, #W0wltc").first
            if await reject_btn.is_visible(timeout=500):
                await reject_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Rejected cookies via ID/Class")
                return "rejected"
        except Exception:
            pass

        # 4. Try accepting via common accessibility roles
        try:
            accept_btn = page.get_by_role("button", name=accept_pattern).first
            if await accept_btn.is_visible(timeout=500):
                await accept_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Accepted cookies via ARIA role")
                return "accepted"
        except Exception:
            pass

        # 5. Try accepting via generic text fallback
        try:
            accept_btn = page.locator("button, a, [role='button']").filter(has_text=accept_pattern).first
            if await accept_btn.is_visible(timeout=500):
                await accept_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Accepted cookies via generic text")
                return "accepted"
        except Exception:
            pass

        # 6. Try standard accept IDs/Classes
        try:
            accept_btn = page.locator("#onetrust-accept-btn-handler, .cookie-accept, #L2AGLb").first
            if await accept_btn.is_visible(timeout=500):
                await accept_btn.click(timeout=click_timeout)
                await page.wait_for_timeout(stabilize_delay)
                logger.debug("[cookie_handler] Accepted cookies via ID/Class")
                return "accepted"
        except Exception:
            pass

        # 7. Optionally remove blocking overlays if neither worked
        removed_any = False
        for selector in overlay_selectors:
            try:
                elements = await page.locator(selector).all()
                for el in elements:
                    if await el.is_visible(timeout=100):
                        await el.evaluate("node => node.remove()")
                        removed_any = True
            except Exception:
                pass
                
        if removed_any:
            logger.debug("[cookie_handler] Removed cookie overlays from DOM")
            return "removed"
            
        return "none"
        
    except Exception as e:
        logger.debug(f"[cookie_handler] Cookie handling error: {e}")
        return "error"
