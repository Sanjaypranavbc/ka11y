from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus
from ...runners.contrast_engine import ContrastEngine

class Policy1411(WCAGPolicy):
    rule_id = "python_1_4_11_non_text_contrast"
    wcag_sc = "1.4.11"
    
    # Needs 3.0:1 contrast for boundaries
    THRESHOLD = 3.0

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        # Only applies to UI components
        is_ui_component = element.interaction.is_focusable or element.semantics.tag_name in ("input", "button", "select", "textarea")
        if not is_ui_component and element.visual.cv_classification != "icon":
            return self._not_applicable(element, "not_ui_component", "Element is not an interactive UI component or graphical object.")
            
        if element.semantics.is_disabled:
            return self._pass(element, "inactive_exempt", "Disabled UI components are exempt from contrast requirements.")
            
        styles = element.visual.computed_styles
        # Naive boundary extraction - production engine needs full visual overlay extraction.
        bg_color = styles.get("background-color", "rgba(0, 0, 0, 0)")
        border_color = styles.get("border-top-color", "rgba(0, 0, 0, 0)")
        
        # If the element has no explicit background or border, it relies on surrounding context.
        if bg_color.endswith(", 0)") and border_color.endswith(", 0)"):
            return self._needs_review(element, "no_explicit_boundary", "Component lacks explicit border or background. Cannot compute boundary contrast automatically.")
            
        return self._needs_review(element, "boundary_contrast_review", "Visual boundary contrast requires visual context/screenshot resolution.")
