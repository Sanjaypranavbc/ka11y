from typing import Dict, Any
from playwright.async_api import Page
from ..models import ElementContext, InteractionContext

class InteractionStateRunner:
    """
    Simulates user interactions (focus, hover) and extracts the delta 
    in rendered properties to prove visibility of state changes.
    """

    _EXTRACT_STYLES_JS = r"""(el) => {
        const style = window.getComputedStyle(el);
        return {
            outline: style.outlineWidth + ' ' + style.outlineStyle + ' ' + style.outlineColor,
            boxShadow: style.boxShadow,
            backgroundColor: style.backgroundColor,
            border: style.borderWidth + ' ' + style.borderStyle + ' ' + style.borderColor,
            color: style.color,
            textDecoration: style.textDecoration
        };
    }"""

    @classmethod
    async def evaluate_focus_visibility(cls, page: Page, selector: str) -> Dict[str, Any]:
        """
        Focuses an element and captures the style delta.
        Returns evidence of visual change (or lack thereof).
        """
        try:
            locator = page.locator(selector).first
            
            # 1. Capture Resting State
            resting_styles = await locator.evaluate(cls._EXTRACT_STYLES_JS)
            
            # 2. Trigger Focus (Keyboard-like)
            await locator.focus()
            await page.wait_for_timeout(50)  # Allow CSS transitions to settle
            
            # 3. Capture Focused State
            focused_styles = await locator.evaluate(cls._EXTRACT_STYLES_JS)
            
            # 4. Compute Delta (Evidence)
            delta = {
                "has_visual_change": False,
                "changes": []
            }

            for prop in resting_styles.keys():
                if resting_styles[prop] != focused_styles[prop]:
                    # Exclude trivial none/0px changes
                    if focused_styles[prop] not in ("none", "0px none rgba(0, 0, 0, 0)", "0px none rgb(0, 0, 0)"):
                        delta["has_visual_change"] = True
                        delta["changes"].append({
                            "property": prop,
                            "from": resting_styles[prop],
                            "to": focused_styles[prop]
                        })
                        
            return delta
        except Exception as e:
            return {"has_visual_change": False, "error": str(e), "changes": []}
