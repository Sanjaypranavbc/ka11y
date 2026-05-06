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
        let currentFieldset = el.parentElement;
        while (currentFieldset && currentFieldset !== document.documentElement) {
            if (currentFieldset.tagName === 'FIELDSET') {
                const legend = currentFieldset.querySelector('legend');
                if (legend) {
                    groupName = (legend.innerText || legend.textContent || '').trim();
                    break;
                }
            }
            currentFieldset = currentFieldset.parentElement || (currentFieldset.getRootNode && currentFieldset.getRootNode().host);
        }

        let nativeLabelText = null;
        const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
        if (label) {
            nativeLabelText = (label.innerText || label.textContent || '').trim();
        }

        let isInLabeledControl = false;
        const parentControl = el.closest('button, a, [role="button"], [role="link"], [role="menuitem"]');
        if (parentControl) {
            // A control is labeled if it has an aria label, or if it has text nodes inside it 
            // (other than this exact image's alt text if it had one).
            const hasAria = parentControl.hasAttribute('aria-label') || parentControl.hasAttribute('aria-labelledby');
            const hasText = (parentControl.innerText || parentControl.textContent || '').trim().length > 0;
            const hasTitle = parentControl.hasAttribute('title');
            isInLabeledControl = hasAria || hasText || hasTitle;
        }
        
        // Detect video component wrappers
        const isVideoContext = !!el.closest('video, [class*="video" i], [class*="player" i], [data-video-id]');

        return {
            described_by_text: describedByText,
            group_name: groupName,
            native_label_text: nativeLabelText,
            is_in_data_table: !!el.closest('table:not([role="presentation"])'),
            is_in_labeled_control: isInLabeledControl,
            is_video_context: isVideoContext
        };
    }"""

    @classmethod
    async def enrich_semantics(cls, page: Page, contexts: List[ElementContext]) -> None:
        """
        Mutates the ElementContext list in place, attaching resolved semantic
        relationships to each element's SemanticContext.
        """
        for frame in page.frames:
            try:
                if (
                    frame.url == "about:blank"
                    and not await frame.locator("body").count()
                ):
                    continue

                # To minimize IPC calls, we could run the script for an array of IDs in the frame.
                # However, we only care about contexts that actually exist in this frame.
                # Since we don't have frame IDs on contexts, we'll just try to evaluate for all contexts.
                # A more optimized approach is to batch evaluate in JS.
                for context in contexts:
                    if not context.element_id:
                        continue

                    relations = await frame.evaluate(
                        cls._RELATIONSHIP_JS, context.element_id
                    )
                    if not relations:
                        continue

                    context.semantics.described_by_text = relations.get(
                        "described_by_text"
                    )
                    context.semantics.is_in_data_table = relations.get(
                        "is_in_data_table", False
                    )
                    context.semantics.is_in_labeled_control = relations.get(
                        "is_in_labeled_control", False
                    )
                    context.semantics.is_video_context = relations.get(
                        "is_video_context", False
                    )

                    group_name = relations.get("group_name")
                    if group_name and context.accessible_name:
                        context.accessible_name.name = (
                            f"{group_name}: {context.accessible_name.name}"
                        )
            except Exception:
                pass
