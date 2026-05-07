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

        # WCAG 2.4.13 requires the focus indicator to satisfy *both* a minimum
        # area (≥ 2 CSS pixels perimeter, approximated here by thickness) and
        # a contrast ratio of at least 3:1 between focused/unfocused states.
        # The previous implementation only failed when *both* dimensions were
        # insufficient, so a 0.5px ring at 5:1 contrast incorrectly passed.
        contrast = element.interaction.focus_ring_contrast
        thickness = element.interaction.focus_ring_thickness_px

        if thickness is not None and thickness < MIN_FOCUS_THICKNESS_PX:
            return self._fail(
                element,
                "thin_focus_indicator",
                f"Focus indicator thickness ({thickness}px) is below the "
                f"{MIN_FOCUS_THICKNESS_PX}px minimum.",
                reason_params={
                    "thickness_px": str(thickness),
                    "min_px": str(MIN_FOCUS_THICKNESS_PX),
                },
            )

        if contrast is None:
            return self._needs_review(
                element,
                "unmeasured_focus_contrast",
                "Focus indicator contrast could not be measured. Manual review required.",
                reason_params={
                    "thickness_px": str(thickness) if thickness is not None else "unknown",
                },
            )

        if contrast < MIN_FOCUS_CONTRAST:
            return self._fail(
                element,
                "low_contrast_focus",
                f"Focus indicator contrast ({contrast}:1) is below the "
                f"{MIN_FOCUS_CONTRAST}:1 minimum.",
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
