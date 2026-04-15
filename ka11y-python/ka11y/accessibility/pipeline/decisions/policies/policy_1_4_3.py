import re
from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus
from ...runners.contrast_engine import ContrastEngine

class Policy143(WCAGPolicy):
    rule_id = "python_1_4_3_contrast"
    wcag_sc = "1.4.3"

    def _is_large_text(self, styles: dict) -> bool:
        """WCAG defines large text as >= 18pt (24px) or >= 14pt (18.66px) and bold."""
        font_size_str = styles.get("font-size", "16px")
        font_weight_str = str(styles.get("font-weight", "400"))
        
        # Extract pixel value
        match = re.search(r"([\d.]+)", font_size_str)
        if not match:
            return False
        
        size_px = float(match.group(1))
        is_bold = font_weight_str in ("bold", "bolder", "700", "800", "900")
        
        if is_bold and size_px >= 18.66:
            return True
        if size_px >= 24.0:
            return True
        return False

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        if not element.accessible_name and not element.visual.ocr_text and not element.visual.visible_label_text:
            return self._not_applicable(element, "no_text", "Element contains no text.")

        # Exemptions: Logos, Inactive UI, Decorative
        if element.visual.cv_classification in ("logo", "decorative") or element.semantics.is_disabled:
            return self._pass(element, "contrast_exempt", "Logos, decorative, or disabled elements are exempt from contrast requirements.")

        styles = element.visual.computed_styles
        fg_color = styles.get("color", "rgb(0,0,0)")
        bg_color = element.visual.resolved_background_color
        
        # Handle transparent backgrounds (if resolver failed to find solid)
        if "rgba" in bg_color and bg_color.endswith(", 0)"):
            return self._needs_review(element, "transparent_bg", "Background is transparent. Cannot compute text contrast statically.")

        is_large = self._is_large_text(styles)
        result = ContrastEngine.evaluate_1_4_3(fg_color, bg_color, is_large)

        evidence = {
            "foreground": fg_color,
            "background": bg_color,
            "contrast_ratio": result["ratio"],
            "required_threshold": result["threshold"],
            "is_large_text": is_large
        }

        if result["passes"]:
            return self._pass(element, "contrast_sufficient", f"Contrast {result['ratio']}:1 meets the {result['threshold']}:1 minimum.", evidence)
        
        return self._fail(element, "contrast_insufficient", f"Contrast {result['ratio']}:1 fails the {result['threshold']}:1 minimum requirement.", evidence)
