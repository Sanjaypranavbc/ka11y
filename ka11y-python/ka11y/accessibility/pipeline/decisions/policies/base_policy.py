from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ...models import ElementContext, RuleVerdict, VerdictStatus

class WCAGPolicy(ABC):
    rule_id: str
    wcag_sc: str

    @abstractmethod
    def evaluate(self, element: ElementContext) -> RuleVerdict:
        """Evaluate the element context and return a verdict."""
        pass

    def _pass(self, el: ElementContext, code: str, msg: str, evidence: dict = None, reason_params: Optional[Dict[str, Any]] = None) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.PASS,
            confidence=1.0,
            reason_code=code,
            human_reason=msg,
            reason_params=reason_params or {},
            evidence=evidence or {},
            element=el
        )

    def _fail(self, el: ElementContext, code: str, msg: str, evidence: dict = None, confidence: float = 0.9, reason_params: Optional[Dict[str, Any]] = None) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.FAIL,
            confidence=confidence,
            reason_code=code,
            human_reason=msg,
            reason_params=reason_params or {},
            evidence=evidence or {},
            element=el
        )

    def _needs_review(self, el: ElementContext, code: str, msg: str, evidence: dict = None, confidence: float = 0.5, reason_params: Optional[Dict[str, Any]] = None) -> RuleVerdict:
        return RuleVerdict(
            rule_id=self.rule_id,
            wcag_sc=self.wcag_sc,
            status=VerdictStatus.NEEDS_REVIEW,
            confidence=confidence,
            reason_code=code,
            human_reason=msg,
            reason_params=reason_params or {},
            evidence=evidence or {},
            element=el
        )

    def _not_applicable(self, el: ElementContext, code: str, msg: str) -> RuleVerdict:
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
