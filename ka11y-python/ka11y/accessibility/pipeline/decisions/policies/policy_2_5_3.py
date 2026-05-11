import re
from .base_policy import WCAGPolicy
from ...models import ElementContext, RuleVerdict, VerdictStatus

# Replace any non-alphanumeric / non-CJK character with whitespace so we can
# tokenise on whitespace boundaries. The previous version stripped all
# punctuation including spaces, which made "Sign In" indistinguishable from
# "Signin" \u2014 letting "signin" match inside "signinbeta" and silently passing
# WCAG 2.5.3 mismatches.
_NON_TOKEN_RE = re.compile(r"[^a-z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+")


def _tokenise(s: str) -> list[str]:
    """Lowercase, then split on any non-alphanumeric / non-CJK run. Empty
    strings are dropped."""
    return [tok for tok in _NON_TOKEN_RE.sub(" ", s.lower()).split() if tok]


def _is_contiguous_subsequence(needle: list[str], haystack: list[str]) -> bool:
    """True when *needle* appears as a contiguous run of tokens in *haystack*.
    Empty needle never matches."""
    if not needle or len(needle) > len(haystack):
        return False
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if haystack[i : i + n] == needle:
            return True
    return False


class Policy253(WCAGPolicy):
    rule_id = "python_2_5_3_label_in_name"
    wcag_sc = "2.5.3"

    def evaluate(self, element: ElementContext) -> RuleVerdict:
        # Only applies to elements with a visible text label AND an accessible name
        visible_text = element.visual.visible_label_text
        if not visible_text or not element.accessible_name:
            return self._not_applicable(
                element,
                "no_visible_label",
                "Element has no visible text label or no accessible name to compare.",
            )

        full_name = element.accessible_name.name
        visible_tokens = _tokenise(visible_text)
        full_tokens = _tokenise(full_name)

        if not visible_tokens:
            return self._not_applicable(
                element,
                "empty_visible_label",
                "Visible label is empty or symbols-only.",
            )

        # WCAG 2.5.3: visible label tokens must appear as a contiguous run
        # within the accessible-name tokens, in order. Token-level matching
        # avoids the substring false-positives that whole-string matching
        # produces (e.g. "signin" inside "signinbeta").
        if _is_contiguous_subsequence(visible_tokens, full_tokens):
            return self._pass(
                element,
                "label_contained",
                f"Visible label '{visible_text}' is correctly contained in accessible name '{full_name}'.",
            )

        return self._fail(
            element,
            "label_mismatch",
            f"Visible label '{visible_text}' is not found within accessible name '{full_name}'. "
            "This breaks speech-to-text navigation.",
        )
