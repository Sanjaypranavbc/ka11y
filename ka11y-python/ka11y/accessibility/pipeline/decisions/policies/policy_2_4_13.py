from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus
from ...config.thresholds import MIN_FOCUS_THICKNESS_PX, MIN_FOCUS_CONTRAST


class Policy2413(WCAGPolicy):
    rule_id = "python_2_4_13_focus_appearance"
    wcag_sc = "2.4.13"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        if not element.interaction.is_focusable:
            return self._not_applicable(
                element, "not_focusable", "Element is not keyboard focusable."
            )

        if not element.interaction.has_focus_ring:
            return self._fail(
                element,
                "no_focus_indicator",
                "Element has no visible focus indicator (fails 2.4.7 prerequisite).",
            )

        # If contrast change is significant, we pass it regardless of thickness
        # (e.g., background goes from white to dark grey)
        contrast = element.interaction.focus_ring_contrast

        thickness = element.interaction.focus_ring_thickness_px
        if thickness < MIN_FOCUS_THICKNESS_PX and (not contrast or contrast < 3.0):
            return self._needs_review(
                element,
                "thin_or_low_contrast_focus",
                f"Focus indicator thickness ({thickness}px) is below the {MIN_FOCUS_THICKNESS_PX}px minimum, and contrast change is not prominent. Manual review required.",
                reason_params={
                    "thickness_px": str(thickness),
                    "min_px": str(MIN_FOCUS_THICKNESS_PX),
                },
            )

        if (
            contrast
            and contrast < MIN_FOCUS_CONTRAST
            and thickness < MIN_FOCUS_THICKNESS_PX
        ):
            return self._fail(
                element,
                "low_contrast_focus",
                f"Focus indicator contrast ({contrast}:1) is below the {MIN_FOCUS_CONTRAST}:1 minimum.",
                reason_params={
                    "contrast": str(contrast),
                    "min_contrast": str(MIN_FOCUS_CONTRAST),
                },
            )

        return self._pass(
            element,
            "valid_focus_appearance",
            "Focus indicator is prominent and distinct.",
        )
