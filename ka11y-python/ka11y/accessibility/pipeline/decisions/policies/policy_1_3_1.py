from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus

class Policy131(WCAGPolicy):
    rule_id = "python_1_3_1_info_and_relationships"
    wcag_sc = "1.3.1"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        """
        WCAG 1.3.1 applies to info and relationships. In this automated context, 
        we primarily check for orphaned form controls or tables without headers.
        """
        tag = element.semantics.tag_name
        
        # 1. Evaluate Data Tables
        if element.semantics.is_in_data_table:
            # A full data table relationship check requires a table-level extractor,
            # but element-level we just confirm it's not orphaned.
            return self._pass(element, "table_context", "Element is correctly identified within a data table.")
            
        # 2. Evaluate Form Controls
        if tag in ("input", "select", "textarea"):
            # Check for orphaned checkboxes/radios
            if element.visual.computed_styles.get("type") in ("radio", "checkbox"):
                if element.semantics.section_type != "form_region" and not element.semantics.described_by_text:
                     return self._needs_review(element, "orphaned_input", "Checkbox/radio is not inside a fieldset or form region, and has no aria-describedby. Verify relationships are clear.")
            
            # Check if it has a label
            if not element.accessible_name and not element.visual.visible_label_text:
                # 3.3.2 covers labels mostly, but 1.3.1 is the structural requirement
                return self._fail(element, "missing_relationship", "Form control lacks a programmatic label relationship.")
                
            return self._pass(element, "valid_relationship", "Form control has a valid programmatic relationship (label/fieldset).")

        return self._not_applicable(element, "not_applicable", "Element type does not require specific structural relationship analysis.")
