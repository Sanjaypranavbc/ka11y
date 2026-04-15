from .base_policy import WCAGPolicy
from ...models import TargetElement, RuleVerdict, VerdictStatus
from ...config.thresholds import MIN_FOCUS_THICKNESS_PX, MIN_FOCUS_CONTRAST

class Policy2413(WCAGPolicy):
    rule_id = "python_2_4_13_focus_appearance"
    wcag_sc = "2.4.13"

    def evaluate(self, element: TargetElement) -> RuleVerdict:
        if not element.interaction.is_focusable:
            return self._not_applicable(element, "not_focusable", "Element is not keyboard focusable.")
            
        if not element.interaction.has_focus_ring:
            return self._fail(element, "no_focus_indicator", "Element has no visible focus indicator (fails 2.4.7 prerequisite).")
            
        thickness = element.interaction.focus_ring_thickness_px
        if thickness < MIN_FOCUS_THICKNESS_PX:
            return self._needs_review(element, "thin_focus_ring", f"Focus indicator thickness ({thickness}px) is below the {MIN_FOCUS_THICKNESS_PX}px minimum. Manual review required.")
            
        contrast = element.interaction.focus_ring_contrast
        if contrast and contrast < MIN_FOCUS_CONTRAST:
            return self._fail(element, "low_contrast_focus", f"Focus indicator contrast ({contrast}:1) is below the {MIN_FOCUS_CONTRAST}:1 minimum.")
            
        return self._pass(element, "valid_focus_appearance", f"Focus indicator meets thickness ({thickness}px) and contrast ({contrast or 'adequate'}:1) requirements.")
