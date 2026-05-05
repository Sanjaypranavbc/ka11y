from typing import List, Dict
from ..models import ElementContext, RuleVerdict, VerdictStatus
from ..router.rule_target_router import RuleTargetRouter
from .policies.base_policy import WCAGPolicy


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
                continue

            try:
                verdict = policy.evaluate(element)
                # Filter out NOT_APPLICABLE to keep report clean
                if verdict.status != VerdictStatus.NOT_APPLICABLE:
                    verdicts.append(verdict)
            except Exception as e:
                verdicts.append(
                    RuleVerdict(
                        rule_id=policy.rule_id,
                        wcag_sc=policy.wcag_sc,
                        status=VerdictStatus.NEEDS_REVIEW,
                        confidence=0.1,
                        reason_code="engine_fault",
                        human_reason=f"Evaluation failed due to an internal error: {str(e)}",
                        evidence={},
                        element=element,
                    )
                )

        return verdicts
