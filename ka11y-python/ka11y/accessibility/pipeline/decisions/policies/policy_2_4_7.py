from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus

class Policy247(WCAGPolicy):
    rule_id = "python_2_4_7_focus_visible"
    wcag_sc = "2.4.7"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        if not element.interaction.is_focusable:
            return self._not_applicable(element, "not_focusable", "Element is not keyboard focusable.")
            
        if element.visual.computed_styles.get("display") == "none":
            return self._not_applicable(element, "hidden_element", "Element is hidden.")

        # Interaction runner sets `has_focus_ring` by checking outlines, box-shadows, backgrounds
        if element.interaction.has_focus_ring:
            return self._pass(element, "focus_indicator_present", "Element presents a visual change when focused via keyboard.")
            
        # If no visual change is detected, it fails 2.4.7
        return self._fail(element, "no_focus_indicator", "Element has no visible focus indicator (no outline, box-shadow, or color change).")
