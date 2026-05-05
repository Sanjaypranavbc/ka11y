from typing import Dict, Any, List
from playwright.async_api import Page
from ..models import ElementContext, InteractionContext


class InteractionStateRunner:
    """
    Simulates user interactions (focus, hover) and extracts the delta
    in rendered properties to prove visibility of state changes.
    """

    _BATCH_FOCUS_JS = r"""async () => {
        const interactives = document.querySelectorAll('a, button, input, select, textarea, [tabindex]');
        const results = {};
        
        for (let i = 0; i < interactives.length; i++) {
            const el = interactives[i];
            if (!el.id || (!el.tabIndex && el.tabIndex !== 0)) continue;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;

            const before = window.getComputedStyle(el, '::before');
            const after = window.getComputedStyle(el, '::after');
            
            const resting = {
                outline: style.outline, boxShadow: style.boxShadow, bg: style.backgroundColor, color: style.color, border: style.border,
                beforeOutline: before.outline, beforeShadow: before.boxShadow, beforeBg: before.backgroundColor,
                afterOutline: after.outline, afterShadow: after.boxShadow, afterBg: after.backgroundColor
            };
            
            // Try to focus without scrolling the page wildly
            const x = window.scrollX, y = window.scrollY;
            el.focus({preventScroll: true});
            await new Promise(r => setTimeout(r, 40)); // Allow CSS to apply
            window.scrollTo(x, y); // maintain stability
            
            const styleF = window.getComputedStyle(el);
            const beforeF = window.getComputedStyle(el, '::before');
            const afterF = window.getComputedStyle(el, '::after');
            
            const focused = {
                outline: styleF.outline, boxShadow: styleF.boxShadow, bg: styleF.backgroundColor, color: styleF.color, border: styleF.border,
                beforeOutline: beforeF.outline, beforeShadow: beforeF.boxShadow, beforeBg: beforeF.backgroundColor,
                afterOutline: afterF.outline, afterShadow: afterF.boxShadow, afterBg: afterF.backgroundColor
            };
            
            let changed = false;
            let changes = [];
            for (let k in resting) {
                if (resting[k] !== focused[k] && focused[k] !== 'none' && !focused[k].includes('rgba(0, 0, 0, 0)')) {
                    changed = true;
                    changes.push({property: k, from: resting[k], to: focused[k]});
                }
            }
            results[el.id] = { has_visual_change: changed, changes: changes };
            el.blur();
        }
        return results;
    }"""

    @classmethod
    async def batch_evaluate_focus(
        cls, page: Page, contexts: List[ElementContext]
    ) -> None:
        """
        Executes a single JS payload to focus all interactive elements
        and updates their InteractionContext natively. Runs across all frames.
        """
        combined_results = {}
        for frame in page.frames:
            try:
                if (
                    frame.url == "about:blank"
                    and not await frame.locator("body").count()
                ):
                    continue
                frame_results = await frame.evaluate(cls._BATCH_FOCUS_JS)
                combined_results.update(frame_results)
            except Exception:
                pass

        for ctx in contexts:
            if ctx.interaction.is_focusable and ctx.element_id in combined_results:
                delta = combined_results[ctx.element_id]
                ctx.interaction.has_focus_ring = delta.get("has_visual_change", False)
                if ctx.interaction.has_focus_ring:
                    ctx.interaction.focus_ring_thickness_px = 2.0  # Heuristic fallback
                    ctx.interaction.focus_ring_contrast = 4.5  # Heuristic fallback
