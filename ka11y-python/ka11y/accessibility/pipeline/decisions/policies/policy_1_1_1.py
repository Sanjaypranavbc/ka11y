import re
from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus
from ...config.thresholds import GENERIC_ALT_STRINGS, MIN_ICON_ALT_LENGTH

# Hoisted module-level so we don't pay the regex compile cost per element.
# The pattern matches an icon alt that contains either two consecutive
# lowercase letters OR any non-ASCII character (CJK / emoji / etc.).
_DESCRIPTIVE_ALT_RE = re.compile(r"[a-z]{2}|[^\x00-\x7F]")


class Policy111(WCAGPolicy):
    rule_id = "python_1_1_1_alt"
    wcag_sc = "1.1.1"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        # 1. Handle Decorative Exemption
        if (
            element.visual.cv_classification == "decorative"
            or element.semantics.role in ("presentation", "none")
        ):
            if not element.accessible_name or not element.accessible_name.name.strip():
                return self._pass(
                    element,
                    "decorative_valid",
                    "Decorative image correctly has no accessible name.",
                )
            return self._fail(
                element,
                "decorative_invalid",
                "Decorative image should have an empty alt attribute or no accessible name.",
            )

        # 2. Handle Functional redundancy (Crucial for FP reduction)
        # If image is inside a link/button that already has a name, the image is decorative.
        if element.semantics.is_in_labeled_control:
            return self._pass(
                element,
                "functional_redundant",
                "Image is part of a labeled control; specific alt is not required.",
            )

        # 3. Check for Missing Name
        if not element.accessible_name or not element.accessible_name.name.strip():
            return self._fail(
                element,
                "missing_alt",
                "Informative image is missing an accessible name (alt text).",
            )

        name = element.accessible_name.name.lower().strip()

        # 4. Filter Generic strings
        if any(g in name for g in GENERIC_ALT_STRINGS):
            return self._fail(
                element, "generic_alt", f"Alt text '{name}' is uninformative."
            )

        # 5. Logo Logic
        if element.visual.cv_classification == "logo":
            if any(
                k in name
                for k in ["logo", "brand", "home", "ロゴ", "ブランド", "ホーム"]
            ):
                return self._pass(
                    element,
                    "logo_valid",
                    f"Logo alt text correctly identifies the brand or destination: '{name}'",
                )
            return self._needs_review(
                element,
                "logo_review",
                "Logo detected; ensure alt text mentions the company name and 'logo'.",
            )

        # 6. Icon Logic
        if element.visual.cv_classification == "icon":
            if len(name) < MIN_ICON_ALT_LENGTH or not _DESCRIPTIVE_ALT_RE.search(name):
                return self._fail(
                    element,
                    "icon_terse",
                    f"Icon alt '{name}' is too short or non-descriptive.",
                )

        return self._pass(
            element,
            "informative_valid",
            f"Image has a descriptive accessible name: '{name}'",
        )
