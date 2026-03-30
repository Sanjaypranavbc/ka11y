# Rule-wise Code Analysis

- Generated at (UTC): `2026-03-28 15:52:04Z`
- Scope: `ka11y-node` + `ka11y-python`
- Method: static source analysis (file-level metrics + SC extraction)

## Summary

- Node custom rule files: **23**
- Node custom SC coverage: **23**
- Node total SC catalog (axe + custom): **47**
- Node axe-only SCs: **24**
- Python rule/evaluator files: **14**
- Python SC coverage: **18**

### Node axe-only SC IDs

1.1.1, 1.2.2, 1.3.1, 1.3.5, 1.4.2, 1.4.3, 1.4.4, 1.4.6, 1.4.12, 2.1.1, 2.2.1, 2.2.2, 2.2.4, 2.4.1, 2.4.2, 2.4.3, 2.4.4, 2.4.6, 2.5.3, 2.5.8, 3.1.1, 3.1.2, 3.3.2, 4.1.2

## ka11y-node Custom Checks

| Rule File | Mode | SC IDs | LOC (code/total) | Functions | Decisions |
|---|---:|---|---:|---:|---:|
| `ka11y-node/src/custom-checks/accessible-auth.check.js` | `static` | 3.3.8 (Accessible Authentication (Minimum)) | 111/141 | 8 | 14 |
| `ka11y-node/src/custom-checks/audio-transcript.check.js` | `static` | 1.2.1 (Audio-only and Video-only (Prerecorded)) | 80/98 | 3 | 10 |
| `ka11y-node/src/custom-checks/character-key-shortcuts.check.js` | `static` | 2.1.4 (Character Key Shortcuts) | 89/122 | 2 | 26 |
| `ka11y-node/src/custom-checks/consistent-help.check.js` | `static` | 3.2.6 (Consistent Help) | 86/103 | 3 | 11 |
| `ka11y-node/src/custom-checks/dragging-movements.check.js` | `static` | 2.5.7 (Dragging Movements) | 98/129 | 3 | 16 |
| `ka11y-node/src/custom-checks/error-prevention.check.js` | `static` | 3.3.4 (Error Prevention (Legal, Financial, Data)) | 95/124 | 3 | 10 |
| `ka11y-node/src/custom-checks/error-suggestion.check.js` | `static` | 3.3.3 (Error Suggestion) | 105/138 | 2 | 14 |
| `ka11y-node/src/custom-checks/focus-appearance.check.js` | `interactive` | 2.4.13 (Focus Appearance) | 184/238 | 8 | 38 |
| `ka11y-node/src/custom-checks/focus-visible.check.js` | `interactive` | 2.4.7 (Focus Visible) | 131/161 | 6 | 26 |
| `ka11y-node/src/custom-checks/html-parsing.check.js` | `static` | 4.1.1 (Parsing) | 46/57 | 3 | 3 |
| `ka11y-node/src/custom-checks/images-of-text.check.js` | `static` | 1.4.5 (Images of Text) | 123/157 | 2 | 20 |
| `ka11y-node/src/custom-checks/keyboard-trap.check.js` | `interactive` | 2.1.2 (No Keyboard Trap) | 122/168 | 7 | 24 |
| `ka11y-node/src/custom-checks/link-purpose.check.js` | `static` | 2.4.9 (Link Purpose (Link Only)) | 79/99 | 3 | 15 |
| `ka11y-node/src/custom-checks/location.check.js` | `static` | 2.4.8 (Location) | 64/79 | 2 | 1 |
| `ka11y-node/src/custom-checks/meaningful-sequence.check.js` | `static` | 1.3.2 (Meaningful Sequence) | 80/107 | 4 | 16 |
| `ka11y-node/src/custom-checks/multiple-ways.check.js` | `static` | 2.4.5 (Multiple Ways) | 82/96 | 2 | 9 |
| `ka11y-node/src/custom-checks/on-focus.check.js` | `interactive` | 3.2.1 (On Focus) | 80/100 | 5 | 13 |
| `ka11y-node/src/custom-checks/on-input.check.js` | `interactive` | 3.2.2 (On Input) | 96/120 | 7 | 14 |
| `ka11y-node/src/custom-checks/orientation.check.js` | `static` | 1.3.4 (Orientation) | 276/385 | 18 | 92 |
| `ka11y-node/src/custom-checks/pointer-cancellation.check.js` | `static` | 2.5.2 (Pointer Cancellation) | 64/87 | 2 | 15 |
| `ka11y-node/src/custom-checks/pronunciation.check.js` | `static` | 3.1.6 (Pronunciation) | 136/177 | 2 | 18 |
| `ka11y-node/src/custom-checks/status-messages.check.js` | `static` | 4.1.3 (Status Messages) | 107/143 | 4 | 9 |
| `ka11y-node/src/custom-checks/use-of-color.check.js` | `static` | 1.4.1 (Use of Color) | 111/165 | 5 | 21 |

## ka11y-python Rule Modules

| Rule File | SC IDs | LOC (code/total) | Functions | Classes | Decisions |
|---|---|---:|---:|---:|---:|
| `ka11y-python/ka11y/accessibility/rendered/evaluators/focus_not_obscured_enhanced.py` | 2.4.11 (Focus Not Obscured (Minimum)), 2.4.12 (Focus Not Obscured (Enhanced)) | 83/102 | 1 | 0 | 11 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/focus_not_obscured_minimum.py` | 2.4.11 (Focus Not Obscured (Minimum)) | 84/102 | 1 | 0 | 11 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/hover_focus_content.py` | 1.4.13 (Content on Hover or Focus) | 130/148 | 1 | 0 | 25 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/orientation.py` | 1.3.4 (Orientation) | 101/121 | 1 | 0 | 22 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/reflow.py` | 1.4.10 (Reflow) | 107/126 | 2 | 0 | 13 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/resize_text.py` | 1.4.4 (Resize Text) | 106/126 | 2 | 0 | 19 |
| `ka11y-python/ka11y/accessibility/rendered/evaluators/text_spacing.py` | 1.4.12 (Text Spacing) | 106/125 | 2 | 0 | 21 |
| `ka11y-python/ka11y/accessibility/rules/forms/form_auditor.py` | 1.3.5 (Identify Input Purpose), 3.3.1 (Error Identification), 3.3.2 (Labels or Instructions) | 266/335 | 6 | 1 | 79 |
| `ka11y-python/ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py` | 2.5.3 (Label in Name) | 207/265 | 8 | 1 | 58 |
| `ka11y-python/ka11y/accessibility/rules/input_modalities/target_size_auditor.py` | 2.5.8 (Target Size (Minimum)) | 230/287 | 5 | 1 | 53 |
| `ka11y-python/ka11y/accessibility/rules/input_modalities/text_spacing_auditor.py` | 1.4.12 (Text Spacing) | 90/126 | 4 | 1 | 13 |
| `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py` | 1.1.1 (Non-text Content), 1.4.5 (Images of Text), 1.4.11 (Non-text Contrast), 4.1.2 (Name, Role, Value) | 782/973 | 15 | 1 | 199 |
| `ka11y-python/ka11y/accessibility/rules/non_text/contrast_analyser.py` | 1.4.11 (Non-text Contrast) | 235/360 | 9 | 0 | 39 |
| `ka11y-python/ka11y/accessibility/rules/timing/pause_stop_hide_auditor.py` | 2.2.2 (Pause, Stop, Hide), 2.3.1 (Three Flashes or Below Threshold) | 247/306 | 4 | 1 | 54 |

## Top Complexity Hotspots

| File | Decisions | Code Lines | SC IDs |
|---|---:|---:|---|
| `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py` | 199 | 782 | 1.1.1, 1.4.5, 1.4.11, 4.1.2 |
| `ka11y-node/src/custom-checks/orientation.check.js` | 92 | 276 | 1.3.4 |
| `ka11y-python/ka11y/accessibility/rules/forms/form_auditor.py` | 79 | 266 | 1.3.5, 3.3.1, 3.3.2 |
| `ka11y-python/ka11y/accessibility/rules/input_modalities/label_in_name_auditor.py` | 58 | 207 | 2.5.3 |
| `ka11y-python/ka11y/accessibility/rules/timing/pause_stop_hide_auditor.py` | 54 | 247 | 2.2.2, 2.3.1 |
| `ka11y-python/ka11y/accessibility/rules/input_modalities/target_size_auditor.py` | 53 | 230 | 2.5.8 |
| `ka11y-python/ka11y/accessibility/rules/non_text/contrast_analyser.py` | 39 | 235 | 1.4.11 |
| `ka11y-node/src/custom-checks/focus-appearance.check.js` | 38 | 184 | 2.4.13 |
| `ka11y-node/src/custom-checks/focus-visible.check.js` | 26 | 131 | 2.4.7 |
| `ka11y-node/src/custom-checks/character-key-shortcuts.check.js` | 26 | 89 | 2.1.4 |
