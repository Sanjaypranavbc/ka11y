from typing import List, Dict, Any
from playwright.async_api import Page
from ..models import ElementContext, SemanticContext


class SemanticRelationshipEngine:
    """
    Builds semantic graphs between elements. Resolves ARIA pointers
    and native HTML grouping mechanisms to provide complete context.
    """

    # Accepts an array of element IDs and returns an array of resolved-relationship
    # objects (one per input ID, in the same order; null when the ID is not in
    # this frame). Batching all IDs into a single evaluate() call avoids one IPC
    # round-trip per element.
    _RELATIONSHIP_JS = r"""(elementIds) => {
        function resolveOne(elementId) {
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
        }

        return elementIds.map(resolveOne);
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

                # Batch every context's element ID into a single evaluate()
                # call. The JS returns one entry per ID (null when the ID is
                # not present in this frame), so one IPC round-trip resolves
                # the whole page instead of one per element.
                batched = [c for c in contexts if c.element_id]
                if not batched:
                    continue

                results = await frame.evaluate(
                    cls._RELATIONSHIP_JS, [c.element_id for c in batched]
                )
                if not results:
                    continue

                for context, relations in zip(batched, results):
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
