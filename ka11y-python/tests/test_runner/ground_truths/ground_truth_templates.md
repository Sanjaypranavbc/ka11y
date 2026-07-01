# Ka11y Ground Truth JSON Templates

This document provides the standard ground truth JSON templates used within the `ka11y` testing framework for validating rule accuracy. Each template aligns with the required input shapes for `ElementContext` mapping and the expected evaluator output schemas.

## 1.1.1 — Non-text Content
```json
{
  "meta": {
    "rule": "1.1.1",
    "rule_name": "Non-text Content",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Element-wise ground truth for WCAG 1.1.1 audit accuracy testing."
  },
  "cases": [
    {
      "id": "c111-01",
      "description": "Informative image without alt text",
      "dom_attributes": {
        "src": "https://example.com/image.png",
        "alt": null,
        "title": null,
        "aria_label": null,
        "aria_labelledby": null,
        "role": null,
        "aria_hidden": null
      },
      "context": {
        "in_link": false,
        "in_button": false,
        "link_href": null,
        "link_text": null,
        "link_aria_label": null,
        "button_text": null
      },
      "classifier_output": {
        "classification": "informative",
        "sub_type": null,
        "is_decorative": false,
        "is_functional": false,
        "is_logo": false,
        "is_icon": false,
        "is_button": false
      },
      "ocr_result": null,
      "expected": {
        "wcag_1_1_1_status": "FAILED",
        "reason": "Informative image lacks alt text describing its content."
      }
    }
  ]
}
```

## 1.4.3 — Contrast (Minimum)
```json
{
  "meta": {
    "rule": "1.4.3",
    "rule_name": "Contrast (Minimum)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic element-wise ground truth for WCAG 1.4.3 accuracy testing."
  },
  "cases": [
    {
      "id": "c143-01",
      "description": "Standard text with insufficient contrast (AA)",
      "dom_attributes": {
        "tag_name": "p",
        "role": null,
        "html_snippet": "<p style=\"color: rgb(119, 119, 119); background-color: rgb(255, 255, 255)\">Sample text</p>",
        "text_content": "Sample text",
        "aria_label": null,
        "is_disabled": false,
        "cv_classification": null
      },
      "visual_attributes": {
        "fg_color": "rgb(119, 119, 119)",
        "bg_color": "rgb(255, 255, 255)",
        "font_size": "16px",
        "font_weight": "400",
        "has_bg_image": false
      },
      "ocr_result": null,
      "expected": {
        "wcag_1_4_3_status": "fail",
        "contrast_ratio": 4.48,
        "threshold": 4.5,
        "is_large_text": false,
        "reason": "Contrast is 4.48:1, failing the 4.5:1 AA requirement."
      }
    }
  ]
}
```

## 1.4.6 — Contrast (Enhanced)
```json
{
  "meta": {
    "rule": "1.4.6",
    "rule_name": "Contrast (Enhanced)",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic element-wise ground truth for WCAG 1.4.6 accuracy testing."
  },
  "cases": [
    {
      "id": "c146-01",
      "description": "Text passing AA but failing AAA contrast",
      "dom_attributes": {
        "tag_name": "p",
        "role": null,
        "html_snippet": "<p style=\"color: rgb(118, 118, 118); background-color: rgb(255, 255, 255)\">Sample text</p>",
        "text_content": "Sample text",
        "aria_label": null,
        "is_disabled": false,
        "cv_classification": null
      },
      "visual_attributes": {
        "fg_color": "rgb(118, 118, 118)",
        "bg_color": "rgb(255, 255, 255)",
        "font_size": "16px",
        "font_weight": "400",
        "has_bg_image": false
      },
      "ocr_result": null,
      "expected": {
        "wcag_1_4_6_status": "fail",
        "contrast_ratio": 4.54,
        "threshold": 7.0,
        "is_large_text": false,
        "reason": "Contrast is 4.54:1, which fails the 7.0:1 AAA requirement."
      }
    }
  ]
}
```

## 1.4.11 — Non-text Contrast
```json
{
  "meta": {
    "rule": "1.4.11",
    "rule_name": "Non-text Contrast",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Tests routing accuracy for interactive elements and boundaries."
  },
  "cases": [
    {
      "id": "c1411-01",
      "description": "Active UI component needing boundary contrast review",
      "dom_attributes": {
        "tag_name": "button",
        "role": "button",
        "html_snippet": "<button style=\"background-color: rgb(200, 200, 200)\">Submit</button>",
        "text_content": "Submit",
        "aria_label": null,
        "is_disabled": false,
        "cv_classification": null
      },
      "interaction": {
        "is_focusable": true,
        "tab_index": 0
      },
      "computed_styles": {
        "background-color": "rgb(200, 200, 200)",
        "border-top-color": "rgba(0, 0, 0, 0)"
      },
      "expected": {
        "wcag_1_4_11_status": "needs_review",
        "reason_code": "boundary_contrast_review",
        "reason": "Active UI component with explicit background requires visual boundary check."
      }
    }
  ]
}
```

## 1.4.5 — Images of Text
```json
{
  "meta": {
    "rule": "1.4.5",
    "rule_name": "Images of Text",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Synthetic ground truth for WCAG 1.4.5 Images of Text."
  },
  "cases": [
    {
      "id": "c145-01",
      "description": "Informative banner with significant text",
      "dom_attributes": {
        "tag_name": "img",
        "alt": "Promotional banner"
      },
      "visual": {
        "cv_classification": "informative",
        "ocr_text": "SUMMER SALE 50% OFF"
      },
      "expected": {
        "status": "needs_review",
        "reason_code": "potential_image_of_text"
      }
    }
  ]
}
```

## 4.1.2 — Name, Role, Value
*(Note: As a standard structure complementing the suite for naming/roles)*
```json
{
  "meta": {
    "rule": "4.1.2",
    "rule_name": "Name, Role, Value",
    "source_url": "synthetic",
    "scraped_at": "YYYY-MM-DD",
    "total_cases": 1,
    "description": "Tests validation of programmatic names and roles for UI components."
  },
  "cases": [
    {
      "id": "c412-01",
      "description": "Custom UI component missing an accessible name",
      "dom_attributes": {
        "tag_name": "div",
        "role": "button",
        "html_snippet": "<div role=\"button\" tabindex=\"0\"></div>",
        "text_content": "",
        "aria_label": null,
        "is_disabled": false,
        "cv_classification": null
      },
      "interaction": {
        "is_focusable": true,
        "tab_index": 0
      },
      "expected": {
        "status": "fail",
        "reason_code": "missing_accessible_name",
        "reason": "Element with role 'button' lacks a programmatic accessible name."
      }
    }
  ]
}
```
