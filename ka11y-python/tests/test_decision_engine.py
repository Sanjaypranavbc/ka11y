"""
Tests for DecisionEngine exception policy.

Locks in Sprint 1 / step 1 of the refactor plan: only `PolicyError` is
converted into a `NEEDS_REVIEW` verdict. Anything else (AttributeError,
TypeError, mis-typed enum compare, etc.) must propagate so that policy
bugs surface in CI/logs instead of being silently rebadged as a low-
confidence review item.
"""

import pytest

from ka11y.accessibility.pipeline.decisions.engine import (
    DecisionEngine,
    PolicyError,
)
from ka11y.accessibility.pipeline.decisions.policies.base_policy import WCAGPolicy
from ka11y.accessibility.pipeline.models import (
    AccessibleName,
    AccessibleNameSource,
    BoundingBox,
    ElementContext,
    InteractionContext,
    RuleVerdict,
    SemanticContext,
    VerdictStatus,
    VisualContext,
)


def _make_element(tag: str = "button") -> ElementContext:
    return ElementContext(
        element_id="el-1",
        html_snippet=f"<{tag}>x</{tag}>",
        semantics=SemanticContext(tag_name=tag),
        visual=VisualContext(
            is_visible=True,
            bounding_box=BoundingBox(x=0, y=0, width=24, height=24),
        ),
        interaction=InteractionContext(is_focusable=True),
        accessible_name=AccessibleName(
            name="x", source=AccessibleNameSource.TEXT_CONTENT, is_visible=True
        ),
    )


class _PassPolicy(WCAGPolicy):
    rule_id = "rule_test"
    wcag_sc = "1.4.3"

    def evaluate(self, element):
        return self._pass(element, "ok", "ok")


class _PolicyErrorPolicy(WCAGPolicy):
    rule_id = "rule_test"
    wcag_sc = "1.4.3"

    def evaluate(self, element):
        raise PolicyError("missing background colour")


class _BrokenPolicy(WCAGPolicy):
    rule_id = "rule_test"
    wcag_sc = "1.4.3"

    def evaluate(self, element):
        # Simulates the real bugs the engine used to mask:
        # enum-vs-string compares, None derefs, AttributeError, etc.
        raise AttributeError("simulated policy bug")


def test_policy_error_is_converted_to_needs_review():
    engine = DecisionEngine({"1.4.3": _PolicyErrorPolicy()})
    verdicts = engine.evaluate_element(_make_element())

    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.status == VerdictStatus.NEEDS_REVIEW
    assert v.reason_code == "policy_uncertain"
    assert "missing background colour" in v.human_reason


def test_unexpected_exception_propagates():
    """Engine must not swallow non-PolicyError exceptions: doing so was
    masking real policy bugs as confidence=0.1 NEEDS_REVIEW verdicts."""
    engine = DecisionEngine({"1.4.3": _BrokenPolicy()})
    with pytest.raises(AttributeError, match="simulated policy bug"):
        engine.evaluate_element(_make_element())


def test_passing_policy_produces_verdict():
    engine = DecisionEngine({"1.4.3": _PassPolicy()})
    verdicts = engine.evaluate_element(_make_element())

    assert len(verdicts) == 1
    assert verdicts[0].status == VerdictStatus.PASS


def test_not_applicable_is_filtered_out():
    class _NA(WCAGPolicy):
        rule_id = "rule_test"
        wcag_sc = "1.4.3"

        def evaluate(self, element):
            return self._not_applicable(element, "na", "na")

    engine = DecisionEngine({"1.4.3": _NA()})
    assert engine.evaluate_element(_make_element()) == []
