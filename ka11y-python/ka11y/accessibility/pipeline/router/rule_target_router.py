from typing import List
from ..models import TargetElement

class RuleTargetRouter:
    """Determines which WCAG rules apply to a given element context."""
    
    @staticmethod
    def get_applicable_rules(element: TargetElement) -> List[str]:
        rules = []
        
        # 1. Images & Visual Media
        if element.semantics.tag_name in ("img", "svg") or element.semantics.role == "img":
            rules.append("1.1.1")
            rules.append("1.4.5")
            
        # 2. Interactive Controls / UI Components
        is_interactive = (
            element.semantics.tag_name in ("button", "a", "input", "select", "textarea") or \
            element.semantics.role in ("button", "link", "checkbox", "radio", "menuitem", "tab", "textbox") or \
            element.interaction.is_focusable
        )
                         
        if is_interactive:
            rules.extend(["1.4.11", "2.4.7", "2.4.13", "2.5.3", "2.5.8"])
            
        # 3. Text Elements (including inputs with values/labels)
        if element.accessible_name or element.visual.ocr_text:
            rules.extend(["1.4.3", "1.4.6"])
            
        return list(set(rules))
