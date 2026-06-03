from typing import Dict, Any, List
from ..models import RuleVerdict, VerdictStatus
from a11y.i18n.loader import render_reason


class EvidenceFormatter:
    @staticmethod
    def to_legacy_findings(
        verdicts: List[RuleVerdict], lang: str = "en"
    ) -> List[Dict[str, Any]]:
        """Converts the new pipeline verdicts to the existing UI-compatible schema."""
        legacy_list = []
        for v in verdicts:
            # Map Internal Status to Legacy Status
            status_map = {
                VerdictStatus.PASS: "pass",
                VerdictStatus.FAIL: "fail",
                VerdictStatus.NEEDS_REVIEW: "needs_review",
                VerdictStatus.NOT_APPLICABLE: "not_applicable",
            }

            localized_reason = render_reason(
                v.wcag_sc,
                v.reason_code,
                lang=lang,
                fallback=v.human_reason,
                params=v.reason_params,
            )

            finding = {
                "source": "python",
                "rule_id": v.rule_id,
                "wcag_sc": v.wcag_sc,
                "status": status_map.get(v.status, "not_applicable"),
                "reason": localized_reason,
                "confidence_score": round(v.confidence, 2),
                # Backward compatibility: element details
                "element": {
                    "html": v.element.html_snippet,
                    "element_id": v.element.element_id,
                    "tag": v.element.semantics.tag_name,
                },
                # Extra metadata for advanced debugging
                "pipeline_meta": {
                    "reason_code": v.reason_code,
                    "section": v.element.semantics.section_type,
                    "evidence": v.evidence,
                },
            }

            if v.element.visual.src:
                finding["element"]["image_src"] = v.element.visual.src

            legacy_list.append(finding)
        return legacy_list
