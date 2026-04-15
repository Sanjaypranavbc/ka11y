from typing import List, Dict, Any
from playwright.async_api import Page
from ..models import ElementContext, SemanticContext

class SemanticRelationshipEngine:
    """
    Builds semantic graphs between elements. Resolves ARIA pointers 
    and native HTML grouping mechanisms to provide complete context.
    """

    _RELATIONSHIP_JS = r"""(elementId) => {
        const el = document.getElementById(elementId);
        if (!el) return null;

        let describedByText = null;
        const describedBy = el.getAttribute('aria-describedby');
        if (describedBy) {
            const ids = describedBy.trim().split(/\s+/);
            const texts = [];
            for (const id of ids) {
                const target = document.getElementById(id);
                if (target) texts.push((target.innerText || target.textContent || '').trim());
            }
            if (texts.length > 0) describedByText = texts.join(' | ');
        }

        let groupName = null;
        const fieldset = el.closest('fieldset');
        if (fieldset) {
            const legend = fieldset.querySelector('legend');
            if (legend) groupName = (legend.innerText || legend.textContent || '').trim();
        }

        let nativeLabelText = null;
        const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
        if (label) {
            nativeLabelText = (label.innerText || label.textContent || '').trim();
        }

        return {
            described_by_text: describedByText,
            group_name: groupName,
            native_label_text: nativeLabelText,
            is_in_data_table: !!el.closest('table:not([role="presentation"])')
        };
    }"""

    @classmethod
    async def enrich_semantics(cls, page: Page, contexts: List[ElementContext]) -> None:
        """
        Mutates the ElementContext list in place, attaching resolved semantic 
        relationships to each element's SemanticContext.
        """
        for context in contexts:
            if not context.element_id:
                continue

            try:
                relations = await page.evaluate(cls._RELATIONSHIP_JS, context.element_id)
                if not relations:
                    continue

                context.semantics.described_by_text = relations.get("described_by_text")
                context.semantics.is_in_data_table = relations.get("is_in_data_table", False)
                
                group_name = relations.get("group_name")
                if group_name and context.accessible_name:
                    context.accessible_name.name = f"{group_name}: {context.accessible_name.name}"

            except Exception:
                pass
