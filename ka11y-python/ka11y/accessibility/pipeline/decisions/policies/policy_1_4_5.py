from .base_policy import WCAGPolicy
from ...models import TargetElement, RuleVerdict, VerdictStatus

class Policy145(WCAGPolicy):
    rule_id = "python_1_4_5_images_of_text"
    wcag_sc = "1.4.5"

    def evaluate(self, element: TargetElement) -> RuleVerdict:
        # Exemptions: Logos, Decorative, and Essential presentation (Charts/Complex)
        exempt_classes = ["logo", "decorative", "complex", "chart"]
        if element.visual.cv_classification in exempt_classes:
            return self._not_applicable(element, "exemption_applies", f"Exemption applies for classification: {element.visual.cv_classification}")

        # If OCR found significant text, it might be an image-of-text
        if element.visual.ocr_text and len(element.visual.ocr_text.strip()) > 3:
            snippet = element.visual.ocr_text[:30]
            return self._needs_review(
                element, 
                "potential_image_of_text", 
                f"Image contains text ('{snippet}...'). Verify if this can be replaced with real CSS-styled text.",
                confidence=0.8
            )

        return self._pass(element, "no_text_detected", "No significant text detected within the image.")
