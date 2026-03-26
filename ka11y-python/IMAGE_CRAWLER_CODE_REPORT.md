# Image Crawling Module — Code Report

**Scope:** `crawler.py` (5 passes), `text_detector.py`, `contrast_analyser.py`, `alttext.py`, `findings.py` converters
**Rules active:** 1.1.1, 1.4.3, 1.4.5, 1.4.6, 1.4.11, 4.1.2

---

## Rule: 1.1.1 — Non-text Content

### Failures

**F1 — SVG alt text is incomplete**

```python
# crawler.py:672
alt_text=svg_ctx["ariaLabel"],  # only reads aria-label
```

`aria-labelledby` and the `<title>` element inside the SVG are never read. An SVG with `<title>Search</title>` but no `aria-label` appears as `alt_text=""` → false fail.

**F2 — Font icon functional detection is too narrow**

```python
# crawler.py:741
is_functional = fi_info["inLink"] or fi_info["inButton"]
```

Font icons inside a `<div onclick=...>`, `<span tabindex="0">`, or `[role="link"]` are classified as decorative and never checked for 4.1.2/1.1.1. An icon-only interactive component via JS is missed entirely.

**F3 — Background images with `role="img"` and no label are not flagged**

```python
# crawler.py:849-860
if is_hidden:
    cls, sub = "decorative", "presentational"
elif has_label:
    cls, sub = "informative", "succinct_information"
else:
    cls, sub = "decorative", "decorative"   # ← role="img" without label falls here silently
```

A `<div role="img" style="background-image:url(hero.jpg)">` with no `aria-label` is classified decorative instead of informative, masking a 1.1.1 fail.

**F4 — `seen_srcs` dedup misses same-image-different-context**

```python
# crawler.py
if abs_src in seen_srcs:
    continue
```

The same `img` src used as both an informative image and a decorative image (e.g., a logo in header and footer) is captured once. The second usage (possibly functional with a different role) is silently skipped.

### Suggested Fixtures

| Fixture file / HTML | Expected behaviour | What it exposes |
|---|---|---|
| `<svg><title>Search</title></svg>` (no aria-label) | alt_text = "Search" — pass | F1: title not read |
| `<svg aria-labelledby="lbl"><title id="lbl">Search</title></svg>` | alt_text resolved via labelledby — pass | F1: labelledby not resolved |
| `<span class="fa fa-search" onclick="search()" tabindex="0">` | classified functional → 4.1.2 checked | F2: JS-interactive icon missed |
| `<div role="img" style="background-image:url(hero.jpg)">` (no aria-label) | informative, 1.1.1 fail | F3: bg role="img" silently decorative |
| Same `src` as `<img alt="Logo">` in header AND `<img alt="">` in footer | both captured separately | F4: dedup drops second context |

---

## Rule: 1.4.3 — Minimum Contrast (text in images)

### Failures

**F5 — `is_bold = False` hardcoded throughout**

```python
# text_detector.py:199
is_bold = False
```

Bold text has an AA threshold of 3.0:1 (≥18.5px bold) instead of 4.5:1. Since `is_bold` is never set, a bold heading at ratio 3.8:1 is reported as a fail when it should pass. No font-weight detection from pixel data exists anywhere in the pipeline.

**F6 — Font size from bbox height is DPR-unaware**

```python
# text_detector.py:204-205
bbox_height = abs(clean_bbox[2][1] - clean_bbox[0][1])
font_size_px = max(bbox_height, 8)
```

Screenshots are taken at the browser's native pixel ratio. If a page uses `devicePixelRatio=2` (retina), a 16px CSS font appears as a 32px bbox height → classified as large text → threshold drops to 3.0:1 → false passes for text that actually fails AA. The viewport config does not set `device_scale_factor`.

**F7 — Transparent/alpha-channel PNG backgrounds read as black**

```python
# text_detector.py:196
img = cv2.imread(image_path)  # no flags — discards alpha channel
```

`cv2.imread` without `cv2.IMREAD_UNCHANGED` discards the alpha channel. Transparent regions become black (RGB 0,0,0). Button screenshots with transparent backgrounds produce artificially high or low contrast ratios.

**F8 — Otsu majority-text inversion heuristic fails on text-heavy images**

```python
# contrast_analyser.py:34-37
if np.sum(thresh == 255) > thresh.size / 2:
    mask = cv2.bitwise_not(thresh)
else:
    mask = thresh
```

A button image where text occupies >50% of the pixel area (e.g., a word-mark or a small button with large text) triggers the inversion, labelling background as text and text as background → inverted luminance → wrong ratio.

**F9 — SVG images are skipped by OCR entirely**

```python
# text_detector.py:347
image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
```

Pass 3 in the crawler saves inline SVGs as `.svg` files. These never enter the OCR pipeline → no 1.4.3 findings for SVG icons even if they contain visible `<text>` labels.

**F10 — EasyOCR bbox vertex ordering assumption breaks on rotated text**

```python
# text_detector.py:204
bbox_height = abs(clean_bbox[2][1] - clean_bbox[0][1])
```

EasyOCR returns a 4-point polygon `[top-left, top-right, bottom-right, bottom-left]`. For rotated/skewed text, `clean_bbox[0][1]` (TL y) and `clean_bbox[2][1]` (BR y) converge → bbox height near-zero → floored to 8px → misclassified as normal small text with the tightest AA threshold.

### Suggested Fixtures

| Fixture | Expected outcome | What it exposes |
|---|---|---|
| `bold_text_3_8_ratio.png` — bold 20px text, ratio 3.8:1 | pass AA bold | F5: hardcoded is_bold=False → false fail |
| `retina_screenshot.png` — 2× DPR, 32px bbox for 16px CSS text | normal text threshold 4.5:1 | F6: classified as large text, threshold 3.0:1 → false pass |
| `transparent_button.png` — RGBA PNG, white text on transparent bg | correct fg/bg extraction | F7: alpha dropped → black background → wrong ratio |
| `text_heavy_button.png` — text covers 70% of button area | correct polarity (text=fg) | F8: Otsu inverts → text labelled as background |
| `icon_with_text.svg` — inline SVG with `<text>` element | OCR runs, 1.4.3 finding emitted | F9: SVG extension skipped entirely |
| `rotated_label.png` — text at 15° rotation | font_size from actual glyph height | F10: near-zero bbox height → 8px floor → wrong threshold |

---

## Rule: 1.4.5 — Images of Text

### Failures

**F11 — `is_text_image` from classifier is never cross-referenced with OCR result**

The `AltTextAccessibilityAuditor` uses the `is_text_image` flag from `ImageData` which comes from the ML classifier. If the classifier misses text (artistic font, very small text), `is_text_image=False` → the 1.4.5 check is skipped entirely. The OCR pipeline may later detect text in the same image, but the two results are never compared — the discrepancy is silently ignored.

**F12 — Logo exception is applied by storage path, not content**

Images stored under `/logos/` receive a 1.4.5 logo exception without verifying whether the image uses custom typography or is a plain text wordmark. A plain-font company name incorrectly stored in `logos/` is never flagged.

### Suggested Fixtures

| Fixture | Expected outcome | What it exposes |
|---|---|---|
| `artistic_font_text.png` — decorative script font with readable words | 1.4.5 fail (image of text detected) | F11: classifier misses it, OCR finds it, no cross-reference |
| `logos/plain_arial_wordmark.png` — company name in Arial (no custom type) | 1.4.5 fail (logo exception should not apply) | F12: path-based logo exception |
| Same image: classifier says no-text, OCR returns 3 high-confidence detections | 1.4.5 fail emitted | F11: discrepancy never surfaced |

---

## Rule: 1.4.6 — Contrast Enhanced (AAA)

### Failures

All failures from 1.4.3 (F5–F10) apply directly because `_contrast_enhanced_to_findings` reads from the same `dom_compliance` / `ci` data.

**F13 — DPR misclassification produces wrong AAA threshold for large text**

```python
# findings.py:458
threshold = 4.5 if is_large else 7.0
```

`is_large` inherits the same DPR-unaware font size (F6). A 16px CSS font on a 2× DPR screenshot is classified as large text → AAA threshold is 4.5:1 instead of the correct 7.0:1 → false passes at ratios between 4.5 and 7.0.

### Suggested Fixtures

| Fixture | Expected outcome | What it exposes |
|---|---|---|
| `large_text_5_ratio.png` — 26px text, ratio 5.0:1 | fail AAA normal (7.0:1), pass AAA large (4.5:1) | Correct threshold selection |
| Retina version of same image at 2× DPR | same verdict as 1× | F13: DPR inflates bbox → wrong AAA threshold |

---

## Rule: 1.4.11 — Non-text Contrast

### Failures

**F14 — Checks cropped screenshot, not the component-in-page-context ratio**

WCAG 1.4.11 requires the boundary of a UI component to have 3:1 contrast against the **adjacent page background**. The crawler screenshots the button/icon in isolation (cropped). The contrast measured is the button's internal content vs its own background pixel; the surrounding page context is absent. A white button on a white page with a light border cannot be evaluated correctly from a cropped screenshot alone.

**F15 — `is_ui_component` path in `check_wcag_compliance` is never triggered**

```python
# contrast_analyser.py:135-140
if is_ui_component:
    return {"contrast_ratio": ..., "AA_ui_component": ratio >= 3.0}
```

This path returns `AA_ui_component` (the correct 3:1 threshold) but `text_detector.py` never passes `is_ui_component=True`. The 1.4.11 findings come from `alttext.py` records through a separate auditor path — the pixel analysis in `contrast_analyser.py` is never invoked for non-text contrast checking.

### Suggested Fixtures

| Fixture | Expected outcome | What it exposes |
|---|---|---|
| Full-page screenshot crop: white button (`border: 1px solid #ccc`) on white bg | border ratio ~1.6:1 → fail 1.4.11 | F14: requires page context, cropped screenshot can't detect this |
| `<button style="background:white; border:1px solid #767676; color:black">` | border #767676 on white = 4.6:1 → pass 1.4.11 | Baseline for correct 3:1 check |
| Icon with 2.5:1 boundary contrast against its container | fail 1.4.11 | F15: `is_ui_component` path never called |

---

## Rule: 4.1.2 — Name, Role, Value

### Failures

**F16 — Button alt_text from innerText misses icon-only buttons**

```python
# crawler.py:528
text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().slice(0,80)
```

A button like `<button><svg aria-hidden="true">...</svg></button>` has `innerText=""`, `value=""`, and no `aria-label` → `alt_text=""`. The auditor sees an empty name but has no `element_id` linking it back to the DOM node. Two different icon-only buttons both produce `alt_text=""` — one may mask the other in the report.

**F17 — `aria-labelledby` is never resolved for any element type**

Across all passes (img, svg, font-icon, button), `aria-labelledby` resolution is completely absent. An element with `aria-labelledby="visible-label"` pointing to a valid DOM node is treated as unlabelled → false fail.

**F18 — Empty string vs absent alt treated identically**

```python
# crawler.py:672
alt_text=svg_ctx["ariaLabel"],  # returns "" if attribute absent
```

`alt=""` (intentionally decorative — attribute present but empty) and no `alt` attribute at all (missing — a 1.1.1 fail) both store `alt_text=""` in `ImageData`. The alttext auditor cannot distinguish between the two cases, leading to either false passes (missing alt treated as decorative) or false fails (explicit empty alt treated as missing).

### Suggested Fixtures

| Fixture | Expected outcome | What it exposes |
|---|---|---|
| `<button><svg aria-hidden="true"><use href="#icon-close"/></svg></button>` | 4.1.2 fail — no accessible name | F16: innerText="" |
| `<button aria-labelledby="btn-label">...</button><span id="btn-label">Close</span>` | 4.1.2 pass — name via labelledby | F17: labelledby not resolved → false fail |
| `<img aria-labelledby="caption" src="chart.png">` + `<figcaption id="caption">Title</figcaption>` | 1.1.1 pass — name via labelledby | F17: same gap for img |
| `<img alt="" src="decorative.png">` (explicit empty — decorative) | 1.1.1 pass (decorative intent) | F18: indistinguishable from absent alt |
| `<img src="informative.png">` (no alt attribute at all) | 1.1.1 fail — alt missing | F18: indistinguishable from explicit empty |

---

## Summary

| Rule | Failure IDs | Root Cause Category |
|---|---|---|
| **1.1.1** | F1, F2, F3, F4 | Incomplete attribute crawling, classification gaps |
| **1.4.3** | F5, F6, F7, F8, F9, F10 | OCR / pixel analysis assumptions |
| **1.4.5** | F11, F12 | Classifier ↔ OCR cross-reference gap |
| **1.4.6** | F13 + all 1.4.3 | DPR-unaware font size → wrong AAA threshold |
| **1.4.11** | F14, F15 | Cropped-screenshot architectural limit |
| **4.1.2** | F16, F17, F18 | Incomplete accessible name resolution |

### Priority order for fixtures

1. **F7** — alpha PNG → black background (affects every transparent button/icon, very common)
2. **F8** — Otsu inversion on text-heavy images (affects wordmarks, CTA buttons)
3. **F17** — `aria-labelledby` unresolved (affects entire 1.1.1 / 4.1.2 verdict accuracy)
4. **F6** — DPR-unaware font size (affects any retina/2× screenshot)
5. **F9** — SVG files skipped by OCR (affects all icon-with-text SVGs)
6. **F18** — empty alt vs absent alt ambiguity (affects decorative image pass/fail accuracy)
