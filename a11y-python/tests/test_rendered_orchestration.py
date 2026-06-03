
import pytest
from a11y.crawler.rendered_layout_crawler import run_all_evaluators

def test_run_all_evaluators_smoke():
    """
    Smoke test for run_all_evaluators to ensure it doesn't crash due to signature mismatches.
    """
    # Minimal raw data that simulates snapshots
    raw_data = [
        {
            "page_url": "https://example.com",
            "baseline": {"scenario": "baseline", "elements": []},
            "reflow_320": {"scenario": "reflow_320", "elements": []},
            "resize_text_200": {"scenario": "resize_text_200", "elements": []},
            "text_spacing_baseline": {"scenario": "text_spacing_baseline", "elements": []},
            "text_spacing_override": {"scenario": "text_spacing_override", "elements": []},
            "focus_scan": [],
            "hover_scan": [],
        }
    ]
    
    # This should not raise "TypeError: evaluate() takes 1 positional argument but 2 were given"
    findings = run_all_evaluators(raw_data, "https://example.com")
    
    assert isinstance(findings, list)
    # Even with empty data, some evaluators might return PASSED records
    assert len(findings) >= 0

if __name__ == "__main__":
    pytest.main([__file__])
