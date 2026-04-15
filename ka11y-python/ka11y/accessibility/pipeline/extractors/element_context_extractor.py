import json
from typing import List, Dict, Any, Optional
from playwright.async_api import Page
from ..models import (
    ElementContext, SemanticContext, VisualContext, 
    InteractionContext, BoundingBox, AccessibleName, AccessibleNameSource,
    SectionType
)
from ..analyzers.section_analyzer import SectionAnalyzer

class ElementContextExtractor:
    """
    Injects a unified JS payload into the page to extract a complete, 
    flattened array of node contexts, then parses them into Pydantic models.
    """

    _UNIFIED_EXTRACTION_JS = r"""() => {
        const results = [];
        const elements = document.querySelectorAll('a, button, input, select, textarea, [role], img, svg, [tabindex]');
        
        function getEffectiveBBox(el) {
            let target = el;
            if (el.tagName === 'INPUT' && (el.type === 'radio' || el.type === 'checkbox')) {
                const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                if (label) target = label;
            }
            const rect = target.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
        }

        function getAncestry(el) {
            const tags = [];
            const roles = [];
            let current = el.parentElement;
            while (current && current !== document.documentElement) {
                tags.push(current.tagName);
                roles.push(current.getAttribute('role') || '');
                current = current.parentElement;
            }
            return { tags, roles };
        }

        function getVisibleLabelText(el) {
            if (['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) {
                const label = el.closest('label') || document.querySelector(`label[for="${el.id}"]`);
                if (label) return (label.innerText || label.textContent || '').trim();
            }
            return null;
        }

        elements.forEach((el, index) => {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;

            const ancestry = getAncestry(el);
            const bbox = getEffectiveBBox(el);
            
            const rawAriaLabel = el.getAttribute('aria-label');
            const rawAlt = el.getAttribute('alt');
            const rawTitle = el.getAttribute('title');

            results.push({
                element_id: el.id || `ka11y-auto-${index}`,
                tag_name: el.tagName.toLowerCase(),
                role: el.getAttribute('role'),
                html_snippet: el.outerHTML.slice(0, 300),
                bbox: bbox,
                computed_styles: {
                    'color': style.color,
                    'background-color': style.backgroundColor,
                    'font-size': style.fontSize,
                    'font-weight': style.fontWeight,
                    'opacity': style.opacity
                },
                ancestor_tags: ancestry.tags,
                ancestor_roles: ancestry.roles,
                is_focusable: el.tabIndex >= 0 || ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName),
                tab_index: el.tabIndex,
                raw_aria_label: rawAriaLabel,
                raw_alt: rawAlt,
                raw_title: rawTitle,
                text_content: el.innerText || '',
                visible_label_text: getVisibleLabelText(el)
            });
        });
        return results;
    }"""

    @classmethod
    async def extract_contexts(cls, page: Page) -> List[ElementContext]:
        raw_data: List[Dict[str, Any]] = await page.evaluate(cls._UNIFIED_EXTRACTION_JS)
        contexts: List[ElementContext] = []

        for data in raw_data:
            section_type = SectionAnalyzer.analyze(
                ancestor_tags=data['ancestor_tags'],
                ancestor_roles=data['ancestor_roles']
            )

            semantics = SemanticContext(
                tag_name=data['tag_name'],
                role=data['role'],
                section_type=section_type,
                ancestor_roles=[r for r in data['ancestor_roles'] if r],
                parent_roles=[r for r in data['ancestor_roles'][:2] if r] # Closer ones
            )

            bbox = BoundingBox(**data['bbox'])
            visual = VisualContext(
                is_visible=True,
                opacity=float(data['computed_styles'].get('opacity', 1.0).replace(' ', '') or 1.0),
                bounding_box=bbox,
                computed_styles=data['computed_styles'],
                visible_label_text=data.get('visible_label_text')
            )

            interaction = InteractionContext(
                is_focusable=data['is_focusable'],
                tab_index=data['tab_index'],
                effective_clickable_bbox=bbox,
                clickable_area_px=bbox.area
            )

            acc_name = None
            if data.get('raw_aria_label'):
                acc_name = AccessibleName(name=data['raw_aria_label'], source=AccessibleNameSource.ARIA_LABEL, is_visible=False)
            elif data.get('raw_alt') is not None:
                acc_name = AccessibleName(name=data['raw_alt'], source=AccessibleNameSource.ALT_ATTRIBUTE, is_visible=False)
            elif data.get('raw_title'):
                acc_name = AccessibleName(name=data['raw_title'], source=AccessibleNameSource.TITLE_ATTRIBUTE, is_visible=False)
            elif data.get('text_content'):
                acc_name = AccessibleName(name=data['text_content'].strip(), source=AccessibleNameSource.TEXT_CONTENT, is_visible=True)

            contexts.append(ElementContext(
                element_id=data['element_id'],
                html_snippet=data['html_snippet'],
                semantics=semantics,
                visual=visual,
                interaction=interaction,
                accessible_name=acc_name
            ))

        return contexts
