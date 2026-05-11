import logging
from typing import List, Dict
from ..models import ElementContext, RuleVerdict, VerdictStatus
from ..router.rule_target_router import RuleTargetRouter
from .policies.base_policy import WCAGPolicy

logger = logging.getLogger(__name__)


class PolicyError(Exception):
    """Raised by a policy when evaluation cannot complete but the engine
    should continue (returns NEEDS_REVIEW). Anything else propagates as
    a logged engine fault so silent regressions become visible."""


class DecisionEngine:
    """
    Orchestrates the evaluation of pre-contextualized elements against
    applicable WCAG policies.
    """

    def __init__(self, policies: Dict[str, WCAGPolicy]):
        self.policies = policies

    def evaluate_element(self, element: ElementContext) -> List[RuleVerdict]:
        verdicts = []
        applicable_rules = RuleTargetRouter.get_applicable_rules(element)

        for sc in applicable_rules:
            policy = self.policies.get(sc)
            if not policy:
                logger.warning("no policy registered for SC %s", sc)
                continue

            try:
                verdict = policy.evaluate(element)
                # Filter out NOT_APPLICABLE to keep report clean
                if verdict.status != VerdictStatus.NOT_APPLICABLE:
                    verdicts.append(verdict)
            except PolicyError as e:
                verdicts.append(
                    RuleVerdict(
                        rule_id=policy.rule_id,
                        wcag_sc=policy.wcag_sc,
                        status=VerdictStatus.NEEDS_REVIEW,
                        confidence=0.3,
                        reason_code="policy_uncertain",
                        human_reason=f"Policy could not evaluate: {str(e)}",
                        evidence={},
                        element=element,
                    )
                )
            except Exception:
                # Unexpected: log full traceback so the bug is visible.
                logger.exception(
                    "engine fault evaluating SC %s on element %s",
                    policy.wcag_sc,
                    element.element_id,
                )
                verdicts.append(
                    RuleVerdict(
                        rule_id=policy.rule_id,
                        wcag_sc=policy.wcag_sc,
                        status=VerdictStatus.NEEDS_REVIEW,
                        confidence=0.1,
                        reason_code="engine_fault",
                        human_reason="Evaluation failed due to an internal error.",
                        evidence={},
                        element=element,
                    )
                )

        return verdicts
