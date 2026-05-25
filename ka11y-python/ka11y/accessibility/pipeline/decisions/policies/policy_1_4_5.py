import re

from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus

# Strip everything but lowercase alphanumerics for a normalised comparison
# between OCR text and the accessible name. Compiled once at import.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")


def _normalise(s: str) -> str:
    return _NON_ALNUM_RE.sub("", s.lower())


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
                if _normalise(element.visual.ocr_text) == _normalise(
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
