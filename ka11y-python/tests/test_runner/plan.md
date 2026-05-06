# Ground Truth Plans: WCAG 1.4.3 · 1.4.6 · 1.4.11

---

## Rule Summary

**WCAG 1.4.3 — Contrast (Minimum)**
Text and images of text must have a contrast ratio of at least **4.5:1** for normal text and **3.0:1** for large text.

**Large text definition (WCAG 2.1):**
- ≥ 24 px (regular weight), OR
- ≥ 18.66 px AND bold (`font-weight` 700/800/900/bold/bolder)

**Exemptions — always emit `pass` via `contrast_exempt` reason:**
- `cv_classification = "logo"` (logotype)
- `cv_classification = "decorative"` (purely decorative text)
- `semantics.is_disabled = True` (inactive UI)

**Verdict values emitted by `Policy143` (`VerdictStatus` str enum):**

| Value | Meaning |
|---|---|
| `"pass"` | Contrast meets or exceeds threshold |
| `"fail"` | Contrast below threshold |
| `"needs_review"` | Background is transparent — cannot compute statically |
| `"not_applicable"` | Element carries no text at all |

**Ground-truth scope:** Only `pass` and `fail` cases. `needs_review` (transparent bg) and `not_applicable` (no-text elements) are excluded from the dataset — these branches exist in the policy but cannot produce a deterministic pass/fail verdict for accuracy measurement.

---

## Auditor Interface

The 1.4.3 runner calls `Policy143` directly — no browser, no crawler, no OCR process.

```python
from ka11y.accessibility.pipeline.decisions.policies.policy_1_4_3 import Policy143
from ka11y.accessibility.pipeline.models import (
    ElementContext, SemanticContext, VisualContext,
    InteractionContext, BoundingBox, AccessibleName, AccessibleNameSource,
)

verdict = Policy143().evaluate(element_context)

# verdict.status       → VerdictStatus enum; compare as "pass" / "fail"
# verdict.reason_code  → "contrast_exempt" | "contrast_sufficient" | "contrast_insufficient"
# verdict.evidence     → {"foreground", "background", "contrast_ratio", "required_threshold", "is_large_text"}
```

**Contrast engine used internally:**
```
L = 0.2126*R_lin + 0.7152*G_lin + 0.0722*B_lin
ratio = (max(L1,L2) + 0.05) / (min(L1,L2) + 0.05)   [rounded to 2 dp]
```

Policy path for `"needs_review"`:
```python
if "rgba" in bg_color and bg_color.endswith(", 0)"):
    return self._needs_review(...)
```
Synthetic cases use solid `rgb(...)` strings, so this path is never triggered by the ground truth.

---

## Ground Truth JSON Schema

**File:** `tests/test_runner/ground_truth_1_4_3.json`

```json
{
  "meta": {
    "rule": "1.4.3",
    "rule_name": "Contrast (Minimum)",
    "source_url": "synthetic",
    "scraped_at": "2026-04-28",
    "total_cases": 22,
    "description": "Synthetic element-wise ground truth for WCAG 1.4.3 accuracy testing.
Each case provides exact CSS color values and element properties to deterministically
cover every decision branch of Policy143. All contrast ratios pre-verified against
ContrastEngine.calculate_ratio()."
  },
  "cases": [/* see Case Catalogue below */]
}
```

### Per-case schema

```json
{
  "id": "c143-01",
  "description": "Human-readable description",
  "dom_attributes": {
    "tag_name":         "p",
    "role":             null,
    "html_snippet":     "<p style=\"color: rgb(0, 0, 0)\">Sample text</p>",
    "text_content":     "Sample text",
    "aria_label":       null,
    "is_disabled":      false,
    "cv_classification": null
  },
  "visual_attributes": {
    "fg_color":     "rgb(0, 0, 0)",
    "bg_color":     "rgb(255, 255, 255)",
    "font_size":    "16px",
    "font_weight":  "400",
    "has_bg_image": false
  },
  "ocr_result": null,
  "expected": {
    "wcag_1_4_3_status": "pass",
    "contrast_ratio":    21.0,
    "threshold":         4.5,
    "is_large_text":     false,
    "reason":            "Black on white — maximum contrast, 21.0:1 ≥ 4.5:1"
  }
}
```

### Field → `ElementContext` mapping

| JSON field | `ElementContext` destination | Notes |
|---|---|---|
| `dom_attributes.tag_name` | `SemanticContext.tag_name` | |
| `dom_attributes.role` | `SemanticContext.role` | |
| `dom_attributes.html_snippet` | `ElementContext.html_snippet` | Struct only — not used by Policy143 |
| `dom_attributes.text_content` | `AccessibleName(name=..., source=TEXT_CONTENT)` | Yields `accessible_name` |
| `dom_attributes.aria_label` | `AccessibleName(name=..., source=ARIA_LABEL)` | Takes priority over `text_content` |
| `dom_attributes.is_disabled` | `SemanticContext.is_disabled` | `True` → exempt PASS |
| `dom_attributes.cv_classification` | `VisualContext.cv_classification` | `"logo"/"decorative"` → exempt PASS |
| `visual_attributes.fg_color` | `VisualContext.computed_styles["color"]` | Fed to `ContrastEngine` |
| `visual_attributes.bg_color` | `VisualContext.resolved_background_color` | Fed to `ContrastEngine` |
| `visual_attributes.font_size` | `VisualContext.computed_styles["font-size"]` | Used by `_is_large_text()` |
| `visual_attributes.font_weight` | `VisualContext.computed_styles["font-weight"]` | Used by `_is_large_text()` |
| `visual_attributes.has_bg_image` | `VisualContext.has_bg_image` | Context annotation only |
| `ocr_result.has_text` | Gate for setting `VisualContext.ocr_text` | |
| `ocr_result.detected_text` | `VisualContext.ocr_text` | Activates OCR text path in policy |
| `expected.wcag_1_4_3_status` | Compared to `verdict.status` | `"pass"` or `"fail"` |
| `expected.contrast_ratio` | Reference only — not compared by runner | Pre-verified value |
| `expected.threshold` | Reference only | 4.5 or 3.0 |
| `expected.is_large_text` | Reference only | |

---

## Case Catalogue (22 Cases)

All contrast ratios are pre-verified against `ContrastEngine.calculate_ratio()`.

### Group A — Exempt Elements (→ `pass` via `contrast_exempt`)

These must carry some accessible text (else policy returns `not_applicable` before reaching the exempt check).

| # | ID | Tag | Accessible text | Exemption reason | Expected |
|---|---|---|---|---|---|
| 1 | `c143-01` | `img` | aria_label="Kao logo" | `cv_classification="logo"` | **pass** |
| 2 | `c143-02` | `span` | text_content="★" | `cv_classification="decorative"` | **pass** |
| 3 | `c143-03` | `button` | text_content="Submit" | `is_disabled=true` | **pass** |

> Colors in exempt cases still have fg/bg set (e.g., low contrast) to confirm the exemption fires before contrast evaluation.

---

### Group B — Normal Text, 16 px regular — threshold 4.5:1

| # | ID | fg_color | bg_color | Ratio | Status | Notes |
|---|---|---|---|---|---|---|
| 4 | `c143-04` | `rgb(0, 0, 0)` | `rgb(255, 255, 255)` | **21.00** | **pass** | Maximum contrast |
| 5 | `c143-05` | `rgb(89, 89, 89)` | `rgb(255, 255, 255)` | **7.00** | **pass** | AAA-quality dark gray |
| 6 | `c143-06` | `rgb(118, 118, 118)` | `rgb(255, 255, 255)` | **4.54** | **pass** | Borderline pass (#767676) |
| 7 | `c143-07` | `rgb(119, 119, 119)` | `rgb(255, 255, 255)` | **4.48** | **fail** | Borderline fail (#777777) |
| 8 | `c143-08` | `rgb(170, 170, 170)` | `rgb(255, 255, 255)` | **2.32** | **fail** | Clearly insufficient (#AAAAAA) |
| 9 | `c143-09` | `rgb(0, 0, 238)` | `rgb(255, 255, 255)` | **9.40** | **pass** | Blue link (#0000EE) |
| 10 | `c143-10` | `rgb(204, 0, 0)` | `rgb(255, 255, 255)` | **5.89** | **pass** | Brand red (#CC0000) |
| 11 | `c143-11` | `rgb(255, 102, 102)` | `rgb(255, 255, 255)` | **2.86** | **fail** | Light red (#FF6666) |
| 12 | `c143-12` | `rgb(136, 136, 136)` | `rgb(204, 204, 204)` | **2.21** | **fail** | Gray-on-gray (#888 on #CCC) |

---

### Group C — Large Text, ≥ 24 px regular — threshold 3.0:1

Note: #949494 (3.03:1) would **fail** at normal text threshold (4.5) but **passes** at the large text threshold (3.0). This is the key coverage case for branch C.

| # | ID | fg_color | bg_color | font_size | Ratio | Status |
|---|---|---|---|---|---|---|
| 13 | `c143-13` | `rgb(148, 148, 148)` | `rgb(255, 255, 255)` | `24px` | **3.03** | **pass** |
| 14 | `c143-14` | `rgb(187, 187, 187)` | `rgb(255, 255, 255)` | `24px` | **1.92** | **fail** |

---

### Group D — Bold Large Text, ≥ 18.66 px + bold — threshold 3.0:1

`_is_large_text()` condition: `font_weight in ("bold","bolder","700","800","900") AND size_px >= 18.66`

| # | ID | fg_color | bg_color | font_size | font_weight | Ratio | Status |
|---|---|---|---|---|---|---|---|
| 15 | `c143-15` | `rgb(89, 89, 89)` | `rgb(255, 255, 255)` | `19px` | `700` | **7.00** | **pass** |
| 16 | `c143-16` | `rgb(148, 148, 148)` | `rgb(255, 255, 255)` | `19px` | `700` | **3.03** | **pass** |
| 17 | `c143-17` | `rgb(187, 187, 187)` | `rgb(255, 255, 255)` | `19px` | `700` | **1.92** | **fail** |

---

### Group E — Dark / Inverted Theme

| # | ID | fg_color | bg_color | Ratio | Status | Notes |
|---|---|---|---|---|---|---|
| 18 | `c143-18` | `rgb(255, 255, 255)` | `rgb(0, 51, 102)` | **12.61** | **pass** | White on navy #003366 |
| 19 | `c143-19` | `rgb(204, 204, 204)` | `rgb(51, 51, 51)` | **7.87** | **pass** | Light gray on dark #CCC/#333 |
| 20 | `c143-20` | `rgb(136, 136, 136)` | `rgb(245, 245, 245)` | **3.25** | **fail** | Gray button text on near-white #888/#F5F5F5 |

---

### Group F — Text-over-Image (OCR path)

These cases simulate a `<div>` or `<section>` with a background image where:
- DOM carries no accessible text (`text_content=null`, `aria_label=null`)
- OCR detected text in the rendered screenshot → `ocr_result.detected_text` → `VisualContext.ocr_text`
- `fg_color` = element's CSS `color` property (text overlay colour)
- `bg_color` = `resolved_background_color` (sampled solid colour from the image region)
- `has_bg_image = true`

Policy flow: `ocr_text` is non-null → element is not `not_applicable` → proceeds to contrast check.

| # | ID | fg_color | bg_color (sampled) | OCR detected text | Ratio | Status |
|---|---|---|---|---|---|---|
| 21 | `c143-21` | `rgb(255, 255, 255)` | `rgb(20, 40, 80)` | `"Welcome to Kao Corporation"` | **14.49** | **pass** |
| 22 | `c143-22` | `rgb(200, 200, 200)` | `rgb(150, 150, 150)` | `"Innovation at Kao"` | **1.77** | **fail** |

---

## Runner Design

**File:** `tests/test_runner/runner_1_4_3.py`

### Comparison to `runner.py` (1.1.1)

| Aspect | 1.1.1 runner | 1.4.3 runner |
|---|---|---|
| Input object | `ImageData` | `ElementContext` |
| Auditor class | `AltTextAccessibilityAuditor` | `Policy143` |
| Auditor call | `.generate_audit_report(images_data=..., ocr_results=...)` | `.evaluate(element_context)` |
| Return | `List[Dict]` → index `[0]["wcag_1_1_1_status"]` | `RuleVerdict` → `.status` |
| OCR injection | `_MockOCRResult` passed in `ocr_results` list | `VisualContext.ocr_text = detected_text` |
| Status values | `"PASSED"` / `"FAILED"` (uppercase) | `"pass"` / `"fail"` (matches `VerdictStatus` enum) |
| Ground truth file | `ground_truth_1_1_1.json` | `ground_truth_1_4_3.json` |
| Report output | `runner_report.json` | `runner_report_1_4_3.json` |

### `_build_element_context(case)` — builder pseudocode

```python
def _build_element_context(case: Dict) -> ElementContext:
    dom = case["dom_attributes"]
    vis = case["visual_attributes"]
    ocr = case.get("ocr_result")          # None or {has_text, detected_text}

    # 1. Accessible name: aria_label takes priority over text_content
    acc_name = None
    if dom.get("aria_label"):
        acc_name = AccessibleName(
            name=dom["aria_label"],
            source=AccessibleNameSource.ARIA_LABEL,
            is_visible=False,
        )
    elif dom.get("text_content"):
        acc_name = AccessibleName(
            name=dom["text_content"],
            source=AccessibleNameSource.TEXT_CONTENT,
            is_visible=True,
        )

    # 2. OCR text — only for text-over-image cases
    ocr_text = None
    if ocr and ocr.get("has_text"):
        ocr_text = ocr.get("detected_text")

    # 3. VisualContext — carries all three colour/size inputs for Policy143
    visual = VisualContext(
        is_visible=True,
        bounding_box=BoundingBox(x=0, y=0, width=200, height=24),
        computed_styles={
            "color":       vis["fg_color"],
            "font-size":   vis["font_size"],
            "font-weight": vis["font_weight"],
        },
        resolved_background_color=vis["bg_color"],
        cv_classification=dom.get("cv_classification"),   # "logo"|"decorative"|null
        ocr_text=ocr_text,
        has_bg_image=vis.get("has_bg_image", False),
    )

    # 4. SemanticContext
    semantics = SemanticContext(
        tag_name=dom["tag_name"],
        role=dom.get("role"),
        is_disabled=dom.get("is_disabled", False),
    )

    # 5. InteractionContext — defaults only, not used by Policy143
    interaction = InteractionContext(
        is_focusable=False,
        tab_index=-1,
        adjacent_spacing_px=0.0,
    )

    return ElementContext(
        element_id=case["id"],
        html_snippet=dom.get("html_snippet", ""),
        semantics=semantics,
        visual=visual,
        interaction=interaction,
        accessible_name=acc_name,
    )
```

### `run_single(case)` return schema

```python
{
    "id":                str,    # case["id"]
    "description":       str,    # case["description"]
    "expected_status":   str,    # "pass" | "fail"
    "actual_status":     str,    # verdict.status (VerdictStatus enum value)
    "match":             bool,
    "reason_code":       str,    # verdict.reason_code
    "contrast_ratio":    float,  # verdict.evidence.get("contrast_ratio")
    "threshold":         float,  # verdict.evidence.get("required_threshold")
    "is_large_text":     bool,   # verdict.evidence.get("is_large_text")
    "fg_color":          str,    # case["visual_attributes"]["fg_color"]
    "bg_color":          str,    # case["visual_attributes"]["bg_color"]
    "has_ocr":           bool,   # ocr_result is not None
}
```

### Accuracy threshold

`90.0 %` — runner exits with code 1 if `correct/total < 0.90`.

### CLI usage (mirrors 1.1.1)

```bash
python -m tests.test_runner.runner_1_4_3
python -m tests.test_runner.runner_1_4_3 --threshold 95
```

---

## Full Decision Branch Coverage Map

```
Policy143.evaluate()
├── no text (accessible_name=None AND ocr_text=None AND visible_label_text=None)
│   └── NOT_APPLICABLE  ← EXCLUDED from ground truth
│
├── cv_classification in ("logo","decorative") OR is_disabled=True
│   └── PASS (contrast_exempt)
│       ├── c143-01  logo
│       ├── c143-02  decorative
│       └── c143-03  disabled
│
├── "rgba" bg ending ", 0)"  (fully transparent)
│   └── NEEDS_REVIEW         ← EXCLUDED from ground truth
│
├── is_large_text = False  (< 24px regular, < 18.66px bold)  → threshold 4.5
│   ├── ratio ≥ 4.5  → PASS
│   │   ├── c143-04  black/white  21.00
│   │   ├── c143-05  #595959/white  7.00
│   │   ├── c143-06  #767676/white  4.54 (border)
│   │   ├── c143-09  #0000EE/white  9.40
│   │   ├── c143-10  #CC0000/white  5.89
│   │   ├── c143-18  white/#003366  12.61
│   │   └── c143-19  #CCC/#333  7.87
│   └── ratio < 4.5  → FAIL
│       ├── c143-07  #777777/white  4.48 (border)
│       ├── c143-08  #AAAAAA/white  2.32
│       ├── c143-11  #FF6666/white  2.86
│       ├── c143-12  #888/#CCC  2.21
│       └── c143-20  #888/#F5F5F5  3.25
│
├── is_large_text = True, font_size ≥ 24px regular  → threshold 3.0
│   ├── ratio ≥ 3.0  → PASS  →  c143-13  #949494/white  3.03
│   └── ratio < 3.0  → FAIL  →  c143-14  #BBBBBB/white  1.92
│
├── is_large_text = True, font_size ≥ 18.66px bold  → threshold 3.0
│   ├── ratio ≥ 3.0  → PASS  →  c143-15  #595959/white  7.00
│   │                          c143-16  #949494/white  3.03
│   └── ratio < 3.0  → FAIL  →  c143-17  #BBBBBB/white  1.92
│
└── text via ocr_text (text-over-image, accessible_name=None)
    ├── ratio ≥ 4.5  → PASS  →  c143-21  white/rgb(20,40,80)  14.49
    └── ratio < 4.5  → FAIL  →  c143-22  #C8C8C8/#969696  1.77
```

---

## Delivery Checklist

- [ ] Create `tests/test_runner/ground_truth_1_4_3.json` — 22 synthetic cases per this plan
- [ ] Create `tests/test_runner/runner_1_4_3.py` — standalone runner (no browser, no crawler, no live OCR)
- [ ] Runner `main()` saves `tests/test_runner/runner_report_1_4_3.json`
- [ ] Verify all 22 ratios with `ContrastEngine.calculate_ratio()` match the `expected.contrast_ratio` fields before committing (use the inline verification script in runner `__main__`)
- [ ] `python -m tests.test_runner.runner_1_4_3` exits 0 on ≥ 90 % accuracy
- [ ] Add to CI: `python -m tests.test_runner.runner_1_4_3 --threshold 90`

---

---

# Ground Truth Plan: WCAG 1.4.6 Contrast (Enhanced)

## Rule Summary

**WCAG 1.4.6 — Contrast (Enhanced) — Level AAA**
Stricter version of 1.4.3. Text and images of text must have a contrast ratio of at least **7.0:1** for normal text and **4.5:1** for large text.

**Large text definition:** same as 1.4.3 — ≥ 24 px regular OR ≥ 18.66 px bold.

**AAA vs AA threshold comparison:**

| Text type | 1.4.3 AA threshold | 1.4.6 AAA threshold |
|---|---|---|
| Normal | 4.5:1 | 7.0:1 |
| Large | 3.0:1 | 4.5:1 |

Note: AAA large threshold (4.5) equals AA normal threshold. Colours that pass AA normal but fail AAA normal (e.g. 5–6:1 range) are the most distinctive 1.4.6 cases.

---

## Auditor Interface

`Policy146` extends `Policy143`. It calls `super().evaluate()` first, then re-applies AAA thresholds to the same ratio.

```python
from ka11y.accessibility.pipeline.decisions.policies.policy_1_4_6 import Policy146

verdict = Policy146().evaluate(element_context)
# verdict.reason_code:
#   "contrast_exempt"               — exempt pass (logo/decorative/disabled)
#   "contrast_enhanced_sufficient"  — AAA pass
#   "contrast_enhanced_insufficient"— AAA fail
# verdict.evidence keys: foreground, background, contrast_ratio,
#                        required_threshold (overwritten to 7.0 or 4.5), is_large_text
```

**Critical implementation detail — exempt path flow:**

```
super().evaluate() returns:
  ├── status="not_applicable" or "needs_review" → Policy146 returns it unchanged
  ├── status="pass", evidence={}   (contrast_exempt)
  │     → `if not evidence: return verdict`  ← early return, no AAA re-evaluation
  │       note: returned verdict still carries rule_id="python_1_4_3_contrast"
  │             this is current behaviour, not a bug in the ground truth
  └── status="pass"/"fail", evidence non-empty  (contrast_sufficient/insufficient)
        → Policy146 overwrites required_threshold with AAA value and re-evaluates
```

This means exempt cases return `pass` from the 1.4.3 pass path — the ground truth expected value is still `"pass"`.

---

## Ground Truth JSON Schema

**File:** `tests/test_runner/ground_truth_1_4_6.json`

Schema is identical to `ground_truth_1_4_3.json`. Only differences:
- `meta.rule = "1.4.6"`
- `meta.rule_name = "Contrast (Enhanced)"`
- `expected.wcag_1_4_6_status` instead of `wcag_1_4_3_status`
- `expected.threshold` values are 7.0 or 4.5

---

## Case Catalogue (23 Cases)

All ratios pre-verified against `ContrastEngine.calculate_ratio()`.

### Group A — Exempt Elements (→ `pass` via `contrast_exempt`)

Same exemption logic as 1.4.3. Exempt elements must carry some text or the policy returns `not_applicable` before reaching this branch.

| # | ID | Tag | Accessible text | Exemption | Ratio | Expected |
|---|---|---|---|---|---|---|
| 1 | `c146-01` | `img` | aria_label="Kao logo" | cv_classification="logo" | 4.54 (low; irrelevant) | **pass** |
| 2 | `c146-02` | `span` | text_content="★" | cv_classification="decorative" | 2.32 (low; irrelevant) | **pass** |
| 3 | `c146-03` | `button` | text_content="Submit" | is_disabled=true | 3.25 (low; irrelevant) | **pass** |

> The fg/bg colours in exempt cases are deliberately low-contrast to confirm the exemption fires *before* the AAA threshold check.

---

### Group B — Normal Text, 16 px regular — threshold 7.0:1

Key zone: ratios 4.5–7.0 pass AA (1.4.3) but **fail AAA (1.4.6)**. These are the most valuable cases for 1.4.6 specifically.

| # | ID | fg_color | bg_color | Ratio | AA (1.4.3) | AAA (1.4.6) | Expected |
|---|---|---|---|---|---|---|---|
| 4 | `c146-04` | `rgb(0, 0, 0)` | `rgb(255, 255, 255)` | **21.00** | pass | pass | **pass** |
| 5 | `c146-05` | `rgb(51, 51, 51)` | `rgb(255, 255, 255)` | **12.63** | pass | pass | **pass** |
| 6 | `c146-06` | `rgb(89, 89, 89)` | `rgb(255, 255, 255)` | **7.00** | pass | **PASS — exact AAA boundary** | **pass** |
| 7 | `c146-07` | `rgb(90, 90, 90)` | `rgb(255, 255, 255)` | **6.90** | pass | fail | **fail** |
| 8 | `c146-08` | `rgb(118, 118, 118)` | `rgb(255, 255, 255)` | **4.54** | pass | fail | **fail** |
| 9 | `c146-09` | `rgb(0, 0, 238)` | `rgb(255, 255, 255)` | **9.40** | pass | pass | **pass** |
| 10 | `c146-10` | `rgb(204, 0, 0)` | `rgb(255, 255, 255)` | **5.89** | pass | fail | **fail** |
| 11 | `c146-11` | `rgb(255, 255, 255)` | `rgb(0, 51, 102)` | **12.61** | pass | pass | **pass** |

---

### Group C — Large Text, ≥ 24 px regular — threshold 4.5:1 (AAA large)

AAA large threshold (4.5) = AA normal threshold. Cases c146-13 to c146-14 are the "passes AA large but fails AAA large" zone.

| # | ID | fg_color | bg_color | font_size | Ratio | AA large (3.0) | AAA large (4.5) | Expected |
|---|---|---|---|---|---|---|---|
| 12 | `c146-12` | `rgb(89, 89, 89)` | `rgb(255, 255, 255)` | `24px` | **7.00** | pass | pass | **pass** |
| 13 | `c146-13` | `rgb(118, 118, 118)` | `rgb(255, 255, 255)` | `24px` | **4.54** | pass | **PASS — exact AAA large boundary** | **pass** |
| 14 | `c146-14` | `rgb(119, 119, 119)` | `rgb(255, 255, 255)` | `24px` | **4.48** | pass | fail | **fail** |
| 15 | `c146-15` | `rgb(148, 148, 148)` | `rgb(255, 255, 255)` | `24px` | **3.03** | pass | fail | **fail** |

---

### Group D — Bold Large Text, ≥ 18.66 px + bold — threshold 4.5:1 (AAA large)

| # | ID | fg_color | bg_color | font_size | font_weight | Ratio | Expected |
|---|---|---|---|---|---|---|---|
| 16 | `c146-16` | `rgb(89, 89, 89)` | `rgb(255, 255, 255)` | `19px` | `700` | **7.00** | **pass** |
| 17 | `c146-17` | `rgb(118, 118, 118)` | `rgb(255, 255, 255)` | `19px` | `700` | **4.54** | **pass** (exact boundary) |
| 18 | `c146-18` | `rgb(119, 119, 119)` | `rgb(255, 255, 255)` | `19px` | `700` | **4.48** | **fail** |
| 19 | `c146-19` | `rgb(148, 148, 148)` | `rgb(255, 255, 255)` | `19px` | `700` | **3.03** | **fail** |

---

### Group E — Dark / Inverted Theme

| # | ID | fg_color | bg_color | Ratio | Expected |
|---|---|---|---|---|---|
| 20 | `c146-20` | `rgb(204, 204, 204)` | `rgb(51, 51, 51)` | **7.87** | **pass** |
| 21 | `c146-21` | `rgb(136, 136, 136)` | `rgb(245, 245, 245)` | **3.25** | **fail** |

---

### Group F — Text-over-Image (OCR path)

Same setup as 1.4.3: `accessible_name=null`, `ocr_result.detected_text` set, `has_bg_image=true`.

| # | ID | fg_color | bg_color (sampled) | OCR text | Ratio | Expected |
|---|---|---|---|---|---|---|
| 22 | `c146-22` | `rgb(255, 255, 255)` | `rgb(20, 40, 80)` | `"Welcome to Kao Corporation"` | **14.49** | **pass** |
| 23 | `c146-23` | `rgb(200, 200, 200)` | `rgb(150, 150, 150)` | `"Innovation at Kao"` | **1.77** | **fail** |

---

## Runner Design

**File:** `tests/test_runner/runner_1_4_6.py`

Identical structure to `runner_1_4_3.py`. Only changes:

| Aspect | 1.4.3 runner | 1.4.6 runner |
|---|---|---|
| Policy class | `Policy143` | `Policy146` |
| GT file | `ground_truth_1_4_3.json` | `ground_truth_1_4_6.json` |
| Status field | `expected.wcag_1_4_3_status` | `expected.wcag_1_4_6_status` |
| Report file | `runner_report_1_4_3.json` | `runner_report_1_4_6.json` |
| Reason codes | `contrast_sufficient` / `contrast_insufficient` | `contrast_enhanced_sufficient` / `contrast_enhanced_insufficient` |

`_build_element_context(case)` is **identical** — no changes needed, same JSON schema, same ElementContext construction.

### Accuracy threshold

`90.0 %` — same as 1.4.3.

---

## Full Decision Branch Coverage Map

```
Policy146.evaluate()
├── super() → not_applicable or needs_review  → returned unchanged
│
├── super() → pass, evidence={}  (contrast_exempt: logo/decorative/disabled)
│   → early return, no AAA re-eval
│       ├── c146-01  logo
│       ├── c146-02  decorative
│       └── c146-03  disabled
│
├── is_large_text = False  → AAA threshold 7.0
│   ├── ratio ≥ 7.0  → PASS (contrast_enhanced_sufficient)
│   │   ├── c146-04  black/white     21.00
│   │   ├── c146-05  #333/white      12.63
│   │   ├── c146-06  #595959/white    7.00  ← exact boundary
│   │   ├── c146-09  #0000EE/white    9.40
│   │   └── c146-11  white/#003366   12.61
│   └── ratio < 7.0  → FAIL (contrast_enhanced_insufficient)
│       ├── c146-07  #5A5A5A/white    6.90  ← just below boundary (passes AA)
│       ├── c146-08  #767676/white    4.54  (passes AA, fails AAA)
│       ├── c146-10  #CC0000/white    5.89  (passes AA, fails AAA)
│       └── c146-21  #888/#F5F5F5    3.25
│
├── is_large_text = True, ≥ 24px regular  → AAA large threshold 4.5
│   ├── ratio ≥ 4.5  → PASS
│   │   ├── c146-12  #595959/white   7.00
│   │   └── c146-13  #767676/white   4.54  ← exact boundary
│   └── ratio < 4.5  → FAIL
│       ├── c146-14  #777777/white   4.48  ← just below (passes AA large 3.0)
│       └── c146-15  #949494/white   3.03  (passes AA large, fails AAA large)
│
├── is_large_text = True, ≥ 18.66px bold  → AAA large threshold 4.5
│   ├── ratio ≥ 4.5  → PASS
│   │   ├── c146-16  #595959 bold    7.00
│   │   └── c146-17  #767676 bold    4.54  ← exact boundary
│   └── ratio < 4.5  → FAIL
│       ├── c146-18  #777777 bold    4.48
│       └── c146-19  #949494 bold    3.03
│
└── text via ocr_text (text-over-image)
    ├── ratio ≥ 7.0  → PASS  →  c146-22  white/dark image  14.49
    └── ratio < 7.0  → FAIL  →  c146-23  light gray/gray    1.77
```

---

## Delivery Checklist — 1.4.6

- [ ] Create `tests/test_runner/ground_truth_1_4_6.json` — 23 synthetic cases
- [ ] Create `tests/test_runner/runner_1_4_6.py` — copy runner_1_4_3.py, swap Policy143 → Policy146, update field names
- [ ] Verify all 23 ratios against `ContrastEngine.calculate_ratio()` match `expected.contrast_ratio`
- [ ] Runner `main()` saves `tests/test_runner/runner_report_1_4_6.json`
- [ ] `python -m tests.test_runner.runner_1_4_6` exits 0 on ≥ 90 % accuracy
- [ ] Add to CI: `python -m tests.test_runner.runner_1_4_6 --threshold 90`

---

---

# Ground Truth Plan: WCAG 1.4.11 Non-text Contrast

## Rule Summary

**WCAG 1.4.11 — Non-text Contrast — Level AA**
The visual presentation of UI components and graphical objects must have a contrast ratio of at least **3.0:1** against adjacent colour(s).

Applies to:
- **UI components** — buttons, inputs, checkboxes, sliders, focus indicators
- **Graphical objects** — icons, charts, diagram elements that convey meaning

**Exemptions:**
- Inactive / disabled components (contrast not required)
- Decorative graphics (no information conveyed)

---

## Critical Implementation Note

**`Policy1411` as currently implemented does not emit `fail` for active UI components.** The policy correctly routes elements (identifies what needs checking and what is exempt), but defers the actual boundary contrast measurement to visual/screenshot analysis.

Current verdict map:

```
Policy1411.evaluate()
├── NOT a UI component AND NOT cv_classification="icon"
│   └── not_applicable   (routing only — correct)
│
├── is_disabled = True
│   └── pass  "inactive_exempt"  (correct — disabled exempt under WCAG)
│
├── Active UI, bg-color AND border-top-color both transparent/rgba(0,0,0,0)
│   └── needs_review  "no_explicit_boundary"  (cannot compute without visual context)
│
└── Active UI, has SOME bg-color OR border-top-color
    └── needs_review  "boundary_contrast_review"
        ← ALL active components land here regardless of actual colour values
        ← reason: real boundary contrast requires screenshot/CV overlay extraction
        ← wired up in contrast_analyser.analyze_ui_component() but NOT called from Policy1411
```

**Implication for ground truth:**
- `not_applicable` and `pass` (disabled) verdicts CAN be tested deterministically
- `needs_review` verdicts test routing accuracy (which elements reach which branch)
- There are **no `fail` verdicts** in the current policy — genuine pass/fail would require wiring `analyze_ui_component()` into the policy first

Ground truth for 1.4.11 therefore tests **routing correctness**, not contrast measurement. The accuracy threshold applies to routing verdicts matching expected routing verdicts.

---

## Auditor Interface

```python
from ka11y.accessibility.pipeline.decisions.policies.policy_1_4_11 import Policy1411

verdict = Policy1411().evaluate(element_context)
# verdict.status values:
#   "not_applicable"  — not a UI component or icon
#   "pass"            — disabled/inactive exempt
#   "needs_review"    — active UI (always, until visual engine wired in)
#
# verdict.reason_code values:
#   "not_ui_component"         — not_applicable
#   "inactive_exempt"          — pass
#   "no_explicit_boundary"     — needs_review (no bg + no border in computed_styles)
#   "boundary_contrast_review" — needs_review (has some bg or border)
```

**UI component detection logic in the policy:**
```python
is_ui_component = (
    element.interaction.is_focusable
    or element.semantics.tag_name in ("input", "button", "select", "textarea")
)
if not is_ui_component and element.visual.cv_classification != "icon":
    → not_applicable
```

**Transparent boundary detection:**
```python
bg_color    = styles.get("background-color", "rgba(0, 0, 0, 0)")
border_color = styles.get("border-top-color", "rgba(0, 0, 0, 0)")
if bg_color.endswith(", 0)") and border_color.endswith(", 0)"):
    → needs_review "no_explicit_boundary"
else:
    → needs_review "boundary_contrast_review"
```

---

## Ground Truth JSON Schema

**File:** `tests/test_runner/ground_truth_1_4_11.json`

Same outer structure (`meta` + `cases` array). Per-case schema differs for 1.4.11:

```json
{
  "id": "c1411-01",
  "description": "Plain paragraph — not a UI component",
  "dom_attributes": {
    "tag_name":         "p",
    "role":             null,
    "html_snippet":     "<p>Some body text</p>",
    "text_content":     "Some body text",
    "aria_label":       null,
    "is_disabled":      false,
    "cv_classification": null
  },
  "interaction": {
    "is_focusable": false,
    "tab_index":    -1
  },
  "computed_styles": {
    "background-color":  "rgba(0, 0, 0, 0)",
    "border-top-color":  "rgba(0, 0, 0, 0)"
  },
  "expected": {
    "wcag_1_4_11_status": "not_applicable",
    "reason_code":        "not_ui_component",
    "reason":             "Plain text element — not interactive, not an icon"
  }
}
```

### Field → `ElementContext` mapping (1.4.11-specific)

| JSON field | `ElementContext` destination | Policy1411 usage |
|---|---|---|
| `dom_attributes.tag_name` | `SemanticContext.tag_name` | Part of `is_ui_component` check |
| `dom_attributes.is_disabled` | `SemanticContext.is_disabled` | → `pass` (inactive_exempt) |
| `dom_attributes.cv_classification` | `VisualContext.cv_classification` | `"icon"` → treated as UI component |
| `interaction.is_focusable` | `InteractionContext.is_focusable` | Part of `is_ui_component` check |
| `interaction.tab_index` | `InteractionContext.tab_index` | Passed through |
| `computed_styles["background-color"]` | `VisualContext.computed_styles["background-color"]` | Transparent boundary check |
| `computed_styles["border-top-color"]` | `VisualContext.computed_styles["border-top-color"]` | Transparent boundary check |

---

## Case Catalogue (15 Cases)

### Group A — Not a UI Component (→ `not_applicable`)

Elements that are neither focusable, nor `input/button/select/textarea`, nor cv_classification="icon".

| # | ID | Tag | is_focusable | cv_classification | Expected | reason_code |
|---|---|---|---|---|---|---|
| 1 | `c1411-01` | `p` | false | null | **not_applicable** | `not_ui_component` |
| 2 | `c1411-02` | `div` | false | null | **not_applicable** | `not_ui_component` |
| 3 | `c1411-03` | `img` | false | `"informative"` | **not_applicable** | `not_ui_component` |

> Case c1411-03: `img` with cv_classification="informative" (not "icon") → not_applicable. Contrast that with Group D case c1411-13 where cv_classification="icon".

---

### Group B — Disabled UI Components (→ `pass` via `inactive_exempt`)

Must be a UI component (tag or focusable), then `is_disabled=True` fires first.

| # | ID | Tag | is_focusable | is_disabled | bg-color | border | Expected | reason_code |
|---|---|---|---|---|---|---|---|---|
| 4 | `c1411-04` | `button` | true | **true** | `rgb(200,200,200)` | `rgb(150,150,150)` | **pass** | `inactive_exempt` |
| 5 | `c1411-05` | `input` | true | **true** | `rgba(0,0,0,0)` | `rgb(180,180,180)` | **pass** | `inactive_exempt` |
| 6 | `c1411-06` | `select` | true | **true** | `rgb(240,240,240)` | `rgba(0,0,0,0)` | **pass** | `inactive_exempt` |

> Both bg and border are irrelevant for disabled cases — the disabled check fires before boundary colour inspection.

---

### Group C — Active UI, No Explicit Boundary (→ `needs_review` / `no_explicit_boundary`)

Active UI component where BOTH `background-color` and `border-top-color` are transparent (ending in `, 0)`).

| # | ID | Tag | is_focusable | bg-color | border-top-color | Expected | reason_code |
|---|---|---|---|---|---|---|---|
| 7 | `c1411-07` | `button` | true | `rgba(0, 0, 0, 0)` | `rgba(0, 0, 0, 0)` | **needs_review** | `no_explicit_boundary` |
| 8 | `c1411-08` | `a` (link) | true | `rgba(0, 0, 0, 0)` | `rgba(0, 0, 0, 0)` | **needs_review** | `no_explicit_boundary` |
| 9 | `c1411-09` | `div` | true (tabindex=0) | `rgba(0, 0, 0, 0)` | `rgba(0, 0, 0, 0)` | **needs_review** | `no_explicit_boundary` |

---

### Group D — Active UI, Has Explicit Boundary (→ `needs_review` / `boundary_contrast_review`)

Active UI component with at least one non-transparent colour in `background-color` OR `border-top-color`.
This group covers the full range of element types — including the icon path and the "has bg but no border" vs "has border but no bg" sub-cases.

| # | ID | Tag | is_focusable | cv_classification | bg-color | border-top-color | Expected | reason_code |
|---|---|---|---|---|---|---|---|---|
| 10 | `c1411-10` | `button` | true | null | `rgb(0, 120, 212)` | `rgba(0,0,0,0)` | **needs_review** | `boundary_contrast_review` |
| 11 | `c1411-11` | `input` | true | null | `rgba(0,0,0,0)` | `rgb(100, 100, 100)` | **needs_review** | `boundary_contrast_review` |
| 12 | `c1411-12` | `select` | true | null | `rgb(240, 240, 240)` | `rgb(180, 180, 180)` | **needs_review** | `boundary_contrast_review` |
| 13 | `c1411-13` | `div` | false | `"icon"` | `rgb(50, 50, 50)` | `rgba(0,0,0,0)` | **needs_review** | `boundary_contrast_review` |
| 14 | `c1411-14` | `textarea` | true | null | `rgb(255, 255, 255)` | `rgb(170, 170, 170)` | **needs_review** | `boundary_contrast_review` |
| 15 | `c1411-15` | `div` | true (tabindex=0) | null | `rgb(230, 230, 230)` | `rgba(0,0,0,0)` | **needs_review** | `boundary_contrast_review` |

> c1411-13: `cv_classification="icon"` on a non-focusable `div` — this is the ONLY path where a non-focusable, non-input/button element IS treated as a UI component (via the icon cv_classification check).

---

## Runner Design

**File:** `tests/test_runner/runner_1_4_11.py`

### Key differences from runner_1_4_3.py

| Aspect | 1.4.3 runner | 1.4.11 runner |
|---|---|---|
| Policy class | `Policy143` | `Policy1411` |
| GT file | `ground_truth_1_4_3.json` | `ground_truth_1_4_11.json` |
| Input colours | `visual_attributes.fg_color` + `bg_color` | `computed_styles["background-color"]` + `computed_styles["border-top-color"]` |
| Status field | `expected.wcag_1_4_3_status` | `expected.wcag_1_4_11_status` |
| Status values | `"pass"` / `"fail"` | `"pass"` / `"needs_review"` / `"not_applicable"` |
| OCR path | Yes | No |
| Contrast engine | Used by policy | **NOT used** (policy defers to needs_review) |

### `_build_element_context(case)` logic — 1.4.11 specifics

```python
def _build_element_context(case: Dict) -> ElementContext:
    dom = case["dom_attributes"]
    inter = case["interaction"]
    styles = case["computed_styles"]

    acc_name = None
    if dom.get("aria_label"):
        acc_name = AccessibleName(name=dom["aria_label"],
                                  source=AccessibleNameSource.ARIA_LABEL, is_visible=False)
    elif dom.get("text_content"):
        acc_name = AccessibleName(name=dom["text_content"],
                                  source=AccessibleNameSource.TEXT_CONTENT, is_visible=True)

    visual = VisualContext(
        is_visible=True,
        bounding_box=BoundingBox(x=0, y=0, width=100, height=36),
        computed_styles={
            "background-color":  styles["background-color"],
            "border-top-color":  styles["border-top-color"],
            "color":             "rgb(0, 0, 0)",     # default; not used by Policy1411
            "font-size":         "16px",
            "font-weight":       "400",
        },
        resolved_background_color="rgb(255, 255, 255)",  # not used by Policy1411
        cv_classification=dom.get("cv_classification"),
    )

    semantics = SemanticContext(
        tag_name=dom["tag_name"],
        role=dom.get("role"),
        is_disabled=dom.get("is_disabled", False),
    )

    interaction = InteractionContext(
        is_focusable=inter["is_focusable"],
        tab_index=inter.get("tab_index", -1),
        adjacent_spacing_px=0.0,
    )

    return ElementContext(
        element_id=case["id"],
        html_snippet=dom.get("html_snippet", ""),
        semantics=semantics,
        visual=visual,
        interaction=interaction,
        accessible_name=acc_name,
    )
```

### `run_single(case)` return schema — 1.4.11

```python
{
    "id":               str,
    "description":      str,
    "expected_status":  str,   # "pass" | "needs_review" | "not_applicable"
    "actual_status":    str,   # verdict.status
    "match":            bool,
    "reason_code":      str,   # verdict.reason_code
    "expected_reason_code": str,  # case["expected"]["reason_code"] (double-check routing)
}
```

Note: matching both `status` AND `reason_code` in the report gives full routing confidence.

### Accuracy threshold

`100 %` — since 1.4.11 routing is entirely deterministic (no contrast math, no ambiguity), anything below 100 % indicates a routing bug.

---

## Full Decision Branch Coverage Map — 1.4.11

```
Policy1411.evaluate()
│
├── not UI component AND cv_classification ≠ "icon"
│   └── not_applicable  "not_ui_component"
│       ├── c1411-01  <p>        is_focusable=False, cv_class=null
│       ├── c1411-02  <div>      is_focusable=False, cv_class=null
│       └── c1411-03  <img>      is_focusable=False, cv_class="informative"
│
├── is_disabled = True
│   └── pass  "inactive_exempt"
│       ├── c1411-04  <button>   disabled, solid bg
│       ├── c1411-05  <input>    disabled, transparent bg
│       └── c1411-06  <select>   disabled, transparent border
│
├── bg AND border BOTH end in ", 0)"  (both transparent)
│   └── needs_review  "no_explicit_boundary"
│       ├── c1411-07  <button>   focusable, no visual styling
│       ├── c1411-08  <a>        focusable, unstyled link
│       └── c1411-09  <div tabindex=0>  custom widget, no styling
│
└── at least one of bg/border is non-transparent
    └── needs_review  "boundary_contrast_review"
        ├── c1411-10  <button>   solid bg only (no border)
        ├── c1411-11  <input>    border only (no bg)
        ├── c1411-12  <select>   both bg and border
        ├── c1411-13  <div>      cv_class="icon", solid bg   ← icon path
        ├── c1411-14  <textarea> bg + visible border
        └── c1411-15  <div tabindex=0>  focusable div, bg only
```

---

## Future: Wiring Real Contrast for 1.4.11

When `analyze_ui_component()` is connected to `Policy1411`, the policy will emit `pass` and `fail` for boundary contrast. At that point:
- Ground truth cases in Groups C and D will need `expected.wcag_1_4_11_status` updated from `"needs_review"` to `"pass"` or `"fail"`
- New `expected.contrast_ratio` and `expected.threshold` fields will be added
- The accuracy threshold can drop from 100 % routing to 90 % contrast

This plan documents the cases to re-use — only the expected values change.

---

## Delivery Checklist — 1.4.11

- [ ] Create `tests/test_runner/ground_truth_1_4_11.json` — 15 cases per this plan
- [ ] Create `tests/test_runner/runner_1_4_11.py` — standalone runner, no contrast engine calls
- [ ] Runner report compares BOTH `status` AND `reason_code` for full routing confidence
- [ ] Runner `main()` saves `tests/test_runner/runner_report_1_4_11.json`
- [ ] `python -m tests.test_runner.runner_1_4_11` exits 0 on **100 %** routing accuracy
- [ ] Add to CI: `python -m tests.test_runner.runner_1_4_11 --threshold 100`
- [ ] When `Policy1411` is upgraded to emit real pass/fail: update expected values in ground truth and lower threshold to 90 %
