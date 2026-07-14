import sys
from unittest.mock import Mock
from ka11y.api.v1.combined.findings import _contrast_to_findings
from ka11y.preprocessor.text_helper_models import TextDetectionResult, DetailedDetection

det = DetailedDetection(
    text="MIGNON",
    confidence=0.999,
    bbox=[(0,0), (10,0), (10,10), (0,10)],
    contrast_info={
        "contrast_ratio": 1.0,
        "compliance": {
            "contrast_ratio": 1.0,
            "AA_passes": False,
            "AAA_passes": False,
            "is_ui_component": True,
            "aa_threshold_used": 3.0
        }
    },
    color_info=None
)
result = TextDetectionResult(
    filename="btn_123.png",
    original_path="/app/crawled_images/btn_123.png",
    has_text=True,
    detections=[det],
    category="button_text"
)

findings = _contrast_to_findings([result], "https://example.com")
import json
print(json.dumps(findings, indent=2))
