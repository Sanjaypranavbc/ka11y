from .base_policy import WCAGPolicy
from ...models import TargetElement, RuleVerdict, VerdictStatus
from ...config.thresholds import MIN_TARGET_SIZE_PX, MIN_TARGET_SPACING_PX

class Policy258(WCAGPolicy):
    rule_id = "python_2_5_8_target_size"
    wcag_sc = "2.5.8"

    def evaluate(self, element: TargetElement) -> RuleVerdict:
        if not element.interaction.is_focusable and element.semantics.tag_name not in ("button", "a", "input"):
            return self._not_applicable(element, "not_interactive", "Target size minimum only applies to interactive elements.")
            
        # 1. Exemptions
        if "p" in element.semantics.parent_tags or element.visual.computed_styles.get("display") == "inline":
            return self._pass(element, "inline_exception", "Target is an inline link within a text block.")
            
        # 2. Evaluate effective clickable area (combines label + input from context extractor)
        w = element.interaction.effective_clickable_bbox.width
        h = element.interaction.effective_clickable_bbox.height
        
        area = element.interaction.effective_clickable_bbox.area
        
        # Both dimensions must be >= 24px per WCAG 2.5.8
        if w >= MIN_TARGET_SIZE_PX and h >= MIN_TARGET_SIZE_PX:
            return self._pass(element, "size_meets_minimum", f"Target bounding box ({w}x{h}px) meets 24x24px minimum.")

        # 3. Spacing Exception (heuristically gathered, assuming 0.0 for now)
        # In a real implementation, adjacent_spacing_px would be calculated via geometric bounds tree
        if element.interaction.adjacent_spacing_px >= MIN_TARGET_SPACING_PX:
            return self._pass(element, "spacing_exception", "Target is undersized but meets the 24px combined spacing exception.")

        return self._fail(element, "undersized_target", f"Target is undersized ({w}x{h}px) and lacks sufficient adjacent spacing.")
