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
        // 1. Gather all elements including Shadow DOM
        function getAllElements(root) {
            let elms = [];
            const children = root.children;
            if (!children) return elms;
            for (let i = 0; i < children.length; i++) {
                const child = children[i];
                elms.push(child);
                if (child.shadowRoot) {
                    elms = elms.concat(getAllElements(child.shadowRoot));
                }
                elms = elms.concat(getAllElements(child));
            }
            return elms;
        }

        const allNodes = getAllElements(document.body);
        
        // Filter elements of interest
        const elements = allNodes.filter(el => {
            const t = el.tagName.toLowerCase();
            return ['a', 'button', 'input', 'select', 'textarea', 'img', 'svg'].includes(t) ||
                   el.hasAttribute('role') || el.hasAttribute('tabindex') ||
                   (window.getComputedStyle(el).backgroundImage !== 'none' && el.hasAttribute('aria-label'));
        });

        // 2. Helpers
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
            let current = el.parentElement || (el.getRootNode && el.getRootNode().host);
            while (current && current !== document.documentElement) {
                tags.push(current.tagName);
                roles.push(current.getAttribute('role') || '');
                current = current.parentElement || (current.getRootNode && current.getRootNode().host);
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

        function isVisuallyHidden(el, style, bbox) {
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return true;
            if (bbox.width === 0 || bbox.height === 0) return true;
            if (style.clip === 'rect(0px, 0px, 0px, 0px)') return true;
            return false;
        }
        
        function getResolvedBackground(el) {
            let current = el;
            while (current && current.nodeType === 1) {
                const bg = window.getComputedStyle(current).backgroundColor;
                const match = bg.match(/rgba?\([^,]+, [^,]+, [^,]+, ([^)]+)\)/);
                if (!match || parseFloat(match[1]) > 0) {
                    if (bg !== 'rgba(0, 0, 0, 0)') return bg;
                }
                current = current.parentElement || (current.getRootNode && current.getRootNode().host);
            }
            return 'rgb(255, 255, 255)';
        }

        const results = [];
        elements.forEach((el, index) => {
            if (!el.id) {
                el.id = `ka11y-auto-${index}`;
            }
            const style = window.getComputedStyle(el);
            const bbox = getEffectiveBBox(el);
            
            if (isVisuallyHidden(el, style, bbox)) return;
            // Ignore aria-hidden logic is handled in SemanticsEngine, we still extract it 
            // if it might be focusable, but generally we let rules decide based on properties.

            const ancestry = getAncestry(el);
            
            const rawAriaLabel = el.getAttribute('aria-label');
            const rawAlt = el.getAttribute('alt');
            const rawTitle = el.getAttribute('title');
            
            let rawSrc = el.getAttribute('src');
            if (el.tagName === 'VIDEO') rawSrc = el.getAttribute('poster');
            else if (el.tagName === 'SVG') rawSrc = null;

            let htmlSnippet = el.outerHTML || '';
            if (el.tagName === 'SVG' && htmlSnippet.length > 250) {
                htmlSnippet = htmlSnippet.slice(0, 247) + '...';
            } else {
                htmlSnippet = htmlSnippet.slice(0, 400);
            }
            
            const controls = (el.getAttribute('aria-controls') || '').split(/\s+/).filter(Boolean);
            const owns = (el.getAttribute('aria-owns') || '').split(/\s+/).filter(Boolean);

            results.push({
                element_id: el.id,
                tag_name: el.tagName.toLowerCase(),
                role: el.getAttribute('role'),
                html_snippet: htmlSnippet,
                bbox: bbox,
                computed_styles: {
                    'color': style.color,
                    'background-color': style.backgroundColor,
                    'font-size': style.fontSize,
                    'font-weight': style.fontWeight,
                    'opacity': style.opacity,
                    'display': style.display
                },
                resolved_bg: getResolvedBackground(el),
                has_bg_image: style.backgroundImage !== 'none' && style.backgroundImage !== 'initial',
                ancestor_tags: ancestry.tags,
                ancestor_roles: ancestry.roles,
                is_focusable: el.tabIndex >= 0 || ['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName),
                tab_index: el.tabIndex,
                raw_aria_label: rawAriaLabel,
                raw_alt: rawAlt,
                raw_title: rawTitle,
                text_content: el.innerText || '',
                visible_label_text: getVisibleLabelText(el),
                src: rawSrc,
                controls_elements: controls,
                owns_elements: owns
            });
        });
        
        // Compute Adjacent Spacing for 2.5.8 natively
        const interactives = results.filter(r => r.is_focusable);
        for (let i = 0; i < interactives.length; i++) {
            let r = interactives[i];
            let minGap = 9999;
            for (let j = 0; j < interactives.length; j++) {
                if (i === j) continue;
                let other = interactives[j];
                let dx = Math.max(0, Math.max(r.bbox.x - (other.bbox.x + other.bbox.width), other.bbox.x - (r.bbox.x + r.bbox.width)));
                let dy = Math.max(0, Math.max(r.bbox.y - (other.bbox.y + other.bbox.height), other.bbox.y - (r.bbox.y + r.bbox.height)));
                let dist = Math.max(dx, dy);
                if (dist < minGap) minGap = dist;
            }
            r.adjacent_spacing_px = minGap === 9999 ? 0 : minGap;
        }

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
                ancestor_tags=[t.lower() for t in data['ancestor_tags'] if t],
                ancestor_roles=[r.lower() for r in data['ancestor_roles'] if r],
                parent_tags=[t.lower() for t in data['ancestor_tags'][:2] if t],
                parent_roles=[r.lower() for r in data['ancestor_roles'][:2] if r],
                controls_elements=data.get('controls_elements', []),
                owns_elements=data.get('owns_elements', [])
            )

            bbox = BoundingBox(**data['bbox'])
            visual = VisualContext(
                is_visible=True,
                opacity=float(data['computed_styles'].get('opacity', 1.0).replace(' ', '') or 1.0),
                bounding_box=bbox,
                computed_styles=data['computed_styles'],
                visible_label_text=data.get('visible_label_text'),
                src=data.get('src'),
                resolved_background_color=data.get('resolved_bg', 'rgb(255, 255, 255)'),
                has_bg_image=data.get('has_bg_image', False)
            )

            interaction = InteractionContext(
                is_focusable=data['is_focusable'],
                tab_index=data['tab_index'],
                effective_clickable_bbox=bbox,
                clickable_area_px=bbox.area,
                adjacent_spacing_px=data.get('adjacent_spacing_px', 0.0)
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
