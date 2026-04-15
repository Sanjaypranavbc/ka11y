import re
from .base_policy import WCAGPolicy
from ...models import TargetElement, RuleVerdict, VerdictStatus

class Policy253(WCAGPolicy):
    rule_id = "python_2_5_3_label_in_name"
    wcag_sc = "2.5.3"

    def evaluate(self, element: TargetElement) -> RuleVerdict:
        # Only applies to elements with a visible text label AND an accessible name
        visible_text = element.visual.visible_label_text
        if not visible_text or not element.accessible_name:
            return self._not_applicable(element, "no_visible_label", "Element has no visible text label or no accessible name to compare.")

        full_name = element.accessible_name.name
        
        # Normalization: Remove non-alphanumeric and extra whitespace
        def normalize(s): 
            return re.sub(r'[^a-z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', '', s.lower())

        norm_visible = normalize(visible_text)
        norm_full = normalize(full_name)

        if not norm_visible:
            return self._not_applicable(element, "empty_visible_label", "Visible label is empty or symbols-only.")

        # WCAG Requirement: Visible label must be CONTAINED within the accessible name
        if norm_visible in norm_full:
            return self._pass(
                element, 
                "label_contained", 
                f"Visible label '{visible_text}' is correctly contained in accessible name '{full_name}'."
            )

        return self._fail(
            element, 
            "label_mismatch", 
            f"Visible label '{visible_text}' is not found within accessible name '{full_name}'. "
            "This breaks speech-to-text navigation."
        )
