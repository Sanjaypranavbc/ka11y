from abc import ABC, abstractmethod
from ...models import TargetElement, RuleVerdict, VerdictStatus

class WCAGPolicy(ABC):
    rule_id: str
    wcag_sc: str
    
    @abstractmethod
    def evaluate(self, element: TargetElement) -> RuleVerdict:
        """Evaluate the element context and return a verdict."""
        pass

    def _pass(self, el: TargetElement, code: str, msg: str, evidence: dict = None) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.PASS,
            confidence=1.0,
            reason_code=code,
            human_reason=msg,
            evidence=evidence or {},
            element=el
        )

    def _fail(self, el: TargetElement, code: str, msg: str, evidence: dict = None, confidence: float = 0.9) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.FAIL,
            confidence=confidence,
            reason_code=code,
            human_reason=msg,
            evidence=evidence or {},
            element=el
        )

    def _needs_review(self, el: TargetElement, code: str, msg: str, evidence: dict = None, confidence: float = 0.5) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.NEEDS_REVIEW,
            confidence=confidence,
            reason_code=code,
            human_reason=msg,
            evidence=evidence or {},
            element=el
        )

    def _not_applicable(self, el: TargetElement, code: str, msg: str) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.NOT_APPLICABLE,
            confidence=1.0,
            reason_code=code,
            human_reason=msg,
            evidence={},
            element=el
        )
