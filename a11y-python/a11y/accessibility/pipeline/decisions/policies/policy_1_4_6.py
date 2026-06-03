from .policy_1_4_3 import Policy143
from ...models import ElementContext, RuleVerdict, VerdictStatus
from ...runners.contrast_engine import ContrastEngine
from ...config.thresholds import CONTRAST_NORMAL_AAA, CONTRAST_LARGE_AAA


class Policy146(Policy143):
    rule_id = "python_1_4_6_contrast_enhanced"
    wcag_sc = "1.4.6"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        # Re-use the entire 1.4.3 logic, just override the thresholds
        verdict = super().evaluate(element)
        if verdict.status in (VerdictStatus.NOT_APPLICABLE, VerdictStatus.NEEDS_REVIEW):
            return verdict

        evidence = verdict.evidence
        if not evidence:
            return verdict

        ratio = evidence["contrast_ratio"]
        is_large = evidence["is_large_text"]

        # AAA Thresholds (1.4.6 Enhanced) — sourced from config, not hardcoded.
        threshold = CONTRAST_LARGE_AAA if is_large else CONTRAST_NORMAL_AAA
        evidence["required_threshold"] = threshold

        if ratio >= threshold:
            return self._pass(
                element,
                "contrast_enhanced_sufficient",
                f"Enhanced contrast {ratio}:1 meets {threshold}:1 minimum.",
                evidence,
            )

        return self._fail(
            element,
            "contrast_enhanced_insufficient",
            f"Enhanced contrast {ratio}:1 fails {threshold}:1 minimum requirement.",
            evidence,
        )
