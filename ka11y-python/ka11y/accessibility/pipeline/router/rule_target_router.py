from typing import List
from ..models import ElementContext


class RuleTargetRouter:
    """Determines which WCAG rules apply to a given element context."""

    @staticmethod
    def get_applicable_rules(element: ElementContext) -> List[str]:
        rules = []

        # 1. Images & Visual Media
        if (
            element.semantics.tag_name in ("img", "svg")
            or element.semantics.role == "img"
        ):
            rules.append("1.1.1")
            rules.append("1.4.5")

        # 2. Interactive Controls / UI Components
        is_interactive = (
            element.semantics.tag_name in ("button", "a", "input", "select", "textarea")
            or element.semantics.role
            in ("button", "link", "checkbox", "radio", "menuitem", "tab", "textbox")
            or element.interaction.is_focusable
        )

        if is_interactive:
            rules.append("1.4.11")

        # 3. Text Elements (including inputs with values/labels)
        if (
            element.accessible_name
            or element.visual.ocr_text
            or element.visual.visible_label_text
        ):
            rules.extend(["1.4.3", "1.4.6"])

        # Order-preserving dedup. `list(set(...))` produced a non-deterministic
        # ordering across hash randomisation runs, which made test snapshots
        # flaky and the `applicable_rules` order unstable for downstream
        # consumers that iterate rule-by-rule.
        seen: set[str] = set()
        deduped: list[str] = []
        for sc in rules:
            if sc not in seen:
                seen.add(sc)
                deduped.append(sc)
        return deduped
