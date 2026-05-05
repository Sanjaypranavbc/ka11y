from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus


class Policy145(WCAGPolicy):
    rule_id = "python_1_4_5_images_of_text"
    wcag_sc = "1.4.5"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        # Exemptions: Logos, Decorative, and Essential presentation (Charts/Complex/Video)
        exempt_classes = ["logo", "decorative", "complex", "chart"]
        if element.visual.cv_classification in exempt_classes:
            return self._not_applicable(
                element,
                "exemption_applies",
                f"Exemption applies for classification: {element.visual.cv_classification}",
            )

        if element.semantics.is_video_context:
            return self._not_applicable(
                element,
                "video_thumbnail_exempt",
                "Video thumbnails/posters are essential presentations and exempt from Images of Text.",
            )

        # If OCR found significant text, it might be an image-of-text
        if element.visual.ocr_text and len(element.visual.ocr_text.strip()) > 3:
            # Mitigation: If the alt text perfectly matches the OCR text,
            # it indicates a deliberate text alternative, which is technically allowed
            # if the visual presentation is essential.
            if element.accessible_name and element.accessible_name.name:
                import re

                def clean(s):
                    return re.sub(r"[^a-z0-9]", "", s.lower())

                if clean(element.visual.ocr_text) == clean(
                    element.accessible_name.name
                ):
                    return self._pass(
                        element,
                        "text_matches_alt",
                        "Image contains text, but it perfectly matches the alt text fallback. Manual review recommended only if the text could be styled via CSS.",
                    )

            snippet = element.visual.ocr_text[:30]
            return self._needs_review(
                element,
                "potential_image_of_text",
                f"Image contains text ('{snippet}...'). Verify if this can be replaced with real CSS-styled text.",
                confidence=0.8,
            )

        return self._pass(
            element,
            "no_text_detected",
            "No significant text detected within the image.",
        )
