# Language Coverage Analysis Report

- Generated: 2026-04-15
- Workbook updated in place: `a11y_coverage_report.xlsx`
- Scoring model: language support was scored across capability areas; automation was scored per WCAG rule and weighted across all 87 criteria.
- Workbook constraint: no existing English summary cells were present, so English values were written to `Reason Sheet` and this report without restructuring the existing sheets.

## 1. Executive Summary

- Overall Japanese coverage: 50% (`Partially Covered`)
- Overall English coverage: 75% (`Covered`)
- Overall automated coverage: 44.0% (`Partially Covered`)
- Strongest evidence areas:
  - Full Japanese rule-metadata overlay: 87/87 rule entries present and non-empty in i18n/locales/ja.yml.
  - Node locale plumbing is wired and tested: lang is sanitized, axe locale is configured, and flat findings localize criterion labels and reasons.
  - Japanese-aware Python parsing exists in sensory_auditor.py and label_in_name_auditor.py, with passing targeted tests for CJK handling.
- Biggest gaps:
  - Japanese image handling is partially complete: `alttext.py` contains Japanese action/logo keywords but `_SOCIAL_BRAND_NAMES` requires specific string formats.
  - Media quality automation (WCAG 1.2.1 Gate 5) in `quality_engine.py` is entirely Anglo-centric. It hardcodes NLTK's English POS tagger, English audio event keywords (`_AUDIO_EVENT_KEYWORDS`), and English speaker patterns (`_SPEAKER_PATTERNS`), breaking Japanese transcript evaluation.
  - `media_auditor.py` handles Japanese transcript link keywords, but `_MEDIA_ALT_KEYWORDS` (used to exempt media alternatives) only contains English strings ("audio version", "video alternative").
  - Japanese routing is inconsistent because create_rule_url_only_handler() hardcodes lang="en" for URL-only rule endpoints.
- Risk areas:
  - 2.4.3 and 2.4.6 rely on fallback/proxy mappings rather than direct rule engines.
  - Python findings often localize criterion labels but not the underlying free-text reasons.
  - Target-size reporting has a schema regression even though the core measurements largely work.

## 2. Japanese Coverage Findings

### Language selection and routing
- Status: Partially Covered
- Percentage: 50%
- Area: detection
- Files: `a11y-node/src/controllers/accessibility.controller.js; a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/api/v1/combined/runner.py`
- Function / Class: `AccessibilityController.analyze/analyseUrlFlat/analyseUrl; create_rule_url_only_handler; _run_job`
- Evidence: Node controllers sanitize and forward lang into analysis calls, and combined jobs set _lang_ctx before running child tasks. But create_rule_url_only_handler() forces lang="en" for URL-only rule endpoints.
- Why this counts: The main combined flow is language-aware, but one routed entry point still bypasses Japanese selection by hardcoding English.
- Confidence: High
- Notes: High risk for Japanese if stakeholders use per-rule /analyse-url endpoints instead of the combined flow.

### Locale mapping and fallback
- Status: Covered
- Percentage: 100%
- Area: fallback
- Files: `a11y-node/src/utils/rulesLoader.js; a11y-python/a11y/i18n/loader.py; i18n/rules.yml; i18n/locales/ja.yml`
- Function / Class: `getRules; getLocaleData; load_rules`
- Evidence: Both Node and Python loaders merge shared i18n/rules.yml with locale overlays and fall back to English. The Japanese locale file contains non-empty entries for all 87 base rules.
- Why this counts: Locale lookup, merge logic, and English fallback are fully implemented and backed by complete Japanese rule metadata.
- Confidence: High
- Notes: No missing or blank Japanese rule entries were found in the current locale file audit.

### Localized prompt and reason templates
- Status: Partially Covered
- Percentage: 50%
- Area: prompts
- Files: `config/universal.yml; a11y-node/src/custom-checks/sharedAssets.js; a11y-python/a11y/accessibility/rules/media/media_auditor.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py`
- Function / Class: `renderReasonTemplate; renderLocalizedText; MediaAuditor; AltTextAccessibilityAuditor`
- Evidence: config/universal.yml stores en/ja keyword lists and reason_templates for multiple Node custom checks, and sharedAssets renders them by lang. Python auditors still emit many hard-coded English reasons.
- Why this counts: Template-based localization exists, but only for part of the stack. Reason generation is not consistently localized across Python auditors.
- Confidence: Medium
- Notes: This directly limits Japanese reporting quality even when localized criterion labels are available.

### Japanese-aware parsing and OCR
- Status: Partially Covered
- Percentage: 50%
- Area: parsing
- Files: `a11y-python/a11y/text_detector/ocrbase.py; a11y-python/a11y/text_detector/paddleocrbase.py; a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py; a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py`
- Function / Class: `get_ocr_reader; _detect_lang; _label_in_name; _check_1_1_1_logo/_check_1_1_1_button`
- Evidence: EasyOCR/PaddleOCR add ja support, sensory_auditor includes CJK detection and Japanese vocabularies, and label_in_name_auditor uses CJK substring matching. But alttext.py still relies on English-only logo/action words for several image paths.
- Why this counts: Japanese-aware parsing exists in several subsystems, but image-text and media handling still have material language-specific gaps.
- Confidence: High
- Notes: Four targeted alt-text tests currently fail on Japanese-specific expectations.

### Validation logic
- Status: Partially Covered
- Percentage: 50%
- Area: validation
- Files: `a11y-python/a11y/accessibility/rules/forms/form_auditor.py; a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py; a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py; a11y-python/a11y/accessibility/rules/media/quality_engine.py`
- Function / Class: `FormAccessibilityAuditor.generate_audit_report; LabelInNameAuditor.generate_audit_report; MediaAuditor._run_quality_checks`
- Evidence: Form, sensory, label-in-name, target-size, and text-spacing validators are wired and mostly tested. Media quality validation is blocked by missing dependencies, and Japanese image validation still fails focused tests.
- Why this counts: Core validation paths exist, but the current checkout cannot claim strong end-to-end validation for all language-sensitive rules.
- Confidence: High
- Notes: Missing nltk/faster_whisper blocks transcript quality checks in the current environment.

### Reporting and localized labels
- Status: Covered
- Percentage: 75%
- Area: reporting
- Files: `a11y-node/src/utils/axeResultMapper.js; a11y-python/a11y/api/v1/combined/findings.py; a11y-python/a11y/api/v1/combined/report.py`
- Function / Class: `mapResultsFlat; mapCustomResultsFlat; _make_finding; _build_report`
- Evidence: Node mapResultsFlat/mapCustomResultsFlat localize criterion names, suggested fixes, and Japanese failure-summary cleanup. Python combined findings use _lang_ctx with get_wcag_names/get_suggested_fixes and _build_report emits lang in the final JSON.
- Why this counts: Localized labels and metadata are wired. Japanese reporting is still partial because some underlying Python reason strings remain English-only.
- Confidence: High
- Notes: Criterion names localize cleanly; free-text reasons do not always.

### Export / API output
- Status: Partially Covered
- Percentage: 50%
- Area: export
- Files: `a11y-python/a11y/api/v1/combined/report.py; a11y-python/a11y/api/v1/rules/metadata.py`
- Function / Class: `_build_report; get_wcag_rules`
- Evidence: The platform exports JSON/API results with a lang field and localized labels, but no first-party Excel export path with localized coverage summaries exists in the product code audited here.
- Why this counts: JSON/API export is wired, but localized stakeholder-export/report logic is only partial in the codebase itself.
- Confidence: Medium
- Notes: This workbook update was performed externally because the repository does not contain a native XLSX coverage-export implementation.

### Automated tests
- Status: Partially Covered
- Percentage: 50%
- Area: tests
- Files: `a11y-node/tests/services/accessibility.service.flat.test.js; a11y-node/tests/utils/axeResultMapper.custom-flat.test.js; a11y-node/tests/custom-checks/sharedAssets.test.js; a11y-python/tests/test_alt_text_auditor.py; a11y-python/tests/test_media_auditor.py; a11y-python/tests/test_target_size_auditor.py`
- Function / Class: `Jest targeted localization suites; pytest targeted language-sensitive suites`
- Evidence: Targeted Node localization tests passed (25/25). Targeted Python language-sensitive suites passed 451 tests but failed 19, concentrated in media quality, alt-text Japanese paths, target-size CSV schema, and one image-audit-stage warning path.
- Why this counts: There is real automated test evidence, but the current Python failures materially limit confidence in Japanese and media-related coverage claims.
- Confidence: High
- Notes: The failures are concentrated in exactly the language-sensitive paths that most affect Japanese support claims.

### Rule-processing orchestration
- Status: Partially Covered
- Percentage: 50%
- Area: rule automation
- Files: `a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/api/v1/combined/runner.py`
- Function / Class: `RULE_FLAGS; _run_job; _merge_findings`
- Evidence: RULE_FLAGS wires Python rule stages, _run_job merges Node and Python findings, and _merge_findings prefers richer Python evidence when the same element appears in both paths.
- Why this counts: The orchestration layer is implemented and active, but language-specific routing and some rule stages still have partial execution quality.
- Confidence: High
- Notes: This is the main source of valid automation evidence for the 55 rules still listed as automated.

### End-to-end combined execution
- Status: Partially Covered
- Percentage: 50%
- Area: end-to-end
- Files: `a11y-python/a11y/api/v1/combined/runner.py; a11y-python/a11y/api/v1/combined/report.py; a11y-python/tests/test_image_audit_stage.py; a11y-python/tests/test_media_auditor.py`
- Function / Class: `_run_job; _build_report`
- Evidence: combined/runner.py launches Node and Python in parallel and writes combined_report.json, but some Python stages degrade because of missing dependencies and one image-audit-stage warning test still fails.
- Why this counts: The end-to-end execution path exists, but current runtime and test evidence do not justify claiming strong Japanese or full automation coverage across all stages.
- Confidence: High
- Notes: Media quality imports fail in this environment; one image-audit-stage warning propagation test also fails.

### Rule-specific Japanese gaps
- `1.1.1 Non-text Content`: `alttext.py` still requires English `logo`/action words in several image-name branches; targeted Japanese tests fail.
- `1.2.1 Audio-only and Video-only`: Japanese transcript keywords exist, but Gate 5 quality checks do not execute here because `quality_engine.py` cannot import `nltk`/`faster_whisper`.
- `1.4.5 Images of Text`: Japanese/logo exceptions are not consistently preserved in the current image-audit implementation; targeted tests fail.

## 3. English Coverage Findings

### Language selection and routing
- Status: Covered
- Percentage: 100%
- Area: detection
- Files: `a11y-node/src/controllers/accessibility.controller.js; a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/api/v1/combined/runner.py`
- Function / Class: `AccessibilityController.analyze/analyseUrlFlat/analyseUrl; create_rule_url_only_handler; _run_job`
- Evidence: Node controllers sanitize and forward lang into analysis calls, and combined jobs set _lang_ctx before running child tasks. But create_rule_url_only_handler() forces lang="en" for URL-only rule endpoints.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: High risk for Japanese if stakeholders use per-rule /analyse-url endpoints instead of the combined flow.

### Locale mapping and fallback
- Status: Covered
- Percentage: 100%
- Area: fallback
- Files: `a11y-node/src/utils/rulesLoader.js; a11y-python/a11y/i18n/loader.py; i18n/rules.yml; i18n/locales/ja.yml`
- Function / Class: `getRules; getLocaleData; load_rules`
- Evidence: Both Node and Python loaders merge shared i18n/rules.yml with locale overlays and fall back to English. The Japanese locale file contains non-empty entries for all 87 base rules.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: No missing or blank Japanese rule entries were found in the current locale file audit.

### Localized prompt and reason templates
- Status: Partially Covered
- Percentage: 50%
- Area: prompts
- Files: `config/universal.yml; a11y-node/src/custom-checks/sharedAssets.js; a11y-python/a11y/accessibility/rules/media/media_auditor.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py`
- Function / Class: `renderReasonTemplate; renderLocalizedText; MediaAuditor; AltTextAccessibilityAuditor`
- Evidence: config/universal.yml stores en/ja keyword lists and reason_templates for multiple Node custom checks, and sharedAssets renders them by lang. Python auditors still emit many hard-coded English reasons.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: Medium
- Notes: This directly limits Japanese reporting quality even when localized criterion labels are available.

### Japanese-aware parsing and OCR
- Status: Covered
- Percentage: 75%
- Area: parsing
- Files: `a11y-python/a11y/text_detector/ocrbase.py; a11y-python/a11y/text_detector/paddleocrbase.py; a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py; a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py`
- Function / Class: `get_ocr_reader; _detect_lang; _label_in_name; _check_1_1_1_logo/_check_1_1_1_button`
- Evidence: EasyOCR/PaddleOCR add ja support, sensory_auditor includes CJK detection and Japanese vocabularies, and label_in_name_auditor uses CJK substring matching. But alttext.py still relies on English-only logo/action words for several image paths.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: Four targeted alt-text tests currently fail on Japanese-specific expectations.

### Validation logic
- Status: Covered
- Percentage: 75%
- Area: validation
- Files: `a11y-python/a11y/accessibility/rules/forms/form_auditor.py; a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py; a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py; a11y-python/a11y/accessibility/rules/media/quality_engine.py`
- Function / Class: `FormAccessibilityAuditor.generate_audit_report; LabelInNameAuditor.generate_audit_report; MediaAuditor._run_quality_checks`
- Evidence: Form, sensory, label-in-name, target-size, and text-spacing validators are wired and mostly tested. Media quality validation is blocked by missing dependencies, and Japanese image validation still fails focused tests.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: Missing nltk/faster_whisper blocks transcript quality checks in the current environment.

### Reporting and localized labels
- Status: Covered
- Percentage: 100%
- Area: reporting
- Files: `a11y-node/src/utils/axeResultMapper.js; a11y-python/a11y/api/v1/combined/findings.py; a11y-python/a11y/api/v1/combined/report.py`
- Function / Class: `mapResultsFlat; mapCustomResultsFlat; _make_finding; _build_report`
- Evidence: Node mapResultsFlat/mapCustomResultsFlat localize criterion names, suggested fixes, and Japanese failure-summary cleanup. Python combined findings use _lang_ctx with get_wcag_names/get_suggested_fixes and _build_report emits lang in the final JSON.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: Criterion names localize cleanly; free-text reasons do not always.

### Export / API output
- Status: Covered
- Percentage: 75%
- Area: export
- Files: `a11y-python/a11y/api/v1/combined/report.py; a11y-python/a11y/api/v1/rules/metadata.py`
- Function / Class: `_build_report; get_wcag_rules`
- Evidence: The platform exports JSON/API results with a lang field and localized labels, but no first-party Excel export path with localized coverage summaries exists in the product code audited here.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: Medium
- Notes: This workbook update was performed externally because the repository does not contain a native XLSX coverage-export implementation.

### Automated tests
- Status: Covered
- Percentage: 75%
- Area: tests
- Files: `a11y-node/tests/services/accessibility.service.flat.test.js; a11y-node/tests/utils/axeResultMapper.custom-flat.test.js; a11y-node/tests/custom-checks/sharedAssets.test.js; a11y-python/tests/test_alt_text_auditor.py; a11y-python/tests/test_media_auditor.py; a11y-python/tests/test_target_size_auditor.py`
- Function / Class: `Jest targeted localization suites; pytest targeted language-sensitive suites`
- Evidence: Targeted Node localization tests passed (25/25). Targeted Python language-sensitive suites passed 451 tests but failed 19, concentrated in media quality, alt-text Japanese paths, target-size CSV schema, and one image-audit-stage warning path.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: The failures are concentrated in exactly the language-sensitive paths that most affect Japanese support claims.

### Rule-processing orchestration
- Status: Covered
- Percentage: 75%
- Area: rule automation
- Files: `a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/api/v1/combined/runner.py`
- Function / Class: `RULE_FLAGS; _run_job; _merge_findings`
- Evidence: RULE_FLAGS wires Python rule stages, _run_job merges Node and Python findings, and _merge_findings prefers richer Python evidence when the same element appears in both paths.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: This is the main source of valid automation evidence for the 55 rules still listed as automated.

### End-to-end combined execution
- Status: Covered
- Percentage: 75%
- Area: end-to-end
- Files: `a11y-python/a11y/api/v1/combined/runner.py; a11y-python/a11y/api/v1/combined/report.py; a11y-python/tests/test_image_audit_stage.py; a11y-python/tests/test_media_auditor.py`
- Function / Class: `_run_job; _build_report`
- Evidence: combined/runner.py launches Node and Python in parallel and writes combined_report.json, but some Python stages degrade because of missing dependencies and one image-audit-stage warning test still fails.
- Why this counts: English is the base/default path for these components, so it remains stronger than Japanese where the same implementation is shared.
- Confidence: High
- Notes: Media quality imports fail in this environment; one image-audit-stage warning propagation test also fails.

### English-specific caveats
- English remains the strongest execution path because both Node and Python default to `en`, but media Gate 5 still fails in this environment and proxy-only automation remains a real limitation for several criteria.

## 4. Automated Coverage Findings

| Rule | Status | Automation % | Area | Files | Function / Class | Evidence | Notes |
|---|---|---:|---|---|---|---|---|
| 1.1.1 Non-text Content | Covered | 75% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; AltTextAccessibilityAuditor.generate_audit_report; _make_finding | SC is wired through run_image_audit; the Python image audit emits 1.1.1/1.4.5/1.4.11/4.1.2 records and combined findings localize criterion labels. | Japanese alt-text tests fail for logo/action terms in tests/test_alt_text_auditor.py (logo, button, and image-name paths). |
| 1.2.1 Audio-only and Video-only | Partially Covered | 50% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/media/media_auditor.py; a11y-python/a11y/accessibility/rules/media/quality_engine.py | RULE_FLAGS; MediaAuditor.generate_audit_report; _run_quality_checks | SC is wired through run_media_audit; transcript detection runs in Gates 1-4, and Gate 5 quality checks import quality_engine.py for deeper validation. | Gate 5 quality checks fail in the current environment because quality_engine.py imports nltk and faster_whisper; labeled-alternative keywords are English-only. |
| 1.2.2 Captions (Prerecorded) | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Track presence is detectable, but caption timing and wording are not verified automatically. |
| 1.3.1 Info and Relationships | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | If a page uses visual tricks to look like a table but lacks the code, it requires human review. |
| 1.3.2 Meaningful Sequence | Covered | 75% | A | a11y-node/src/custom-checks/meaningful-sequence.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Sequence coverage is heuristic rather than a full keyboard walkthrough. |
| 1.3.3 Sensory Characteristics | Partially Covered | 50% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | tests/test_sensory_auditor.py passes, but the rule is still regex/NLP heuristic, not full semantic understanding. |
| 1.3.4 Orientation | Covered | 75% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/orientation.py; a11y-node/src/custom-checks/orientation.check.js | RULE_FLAGS; rendered evaluator; check; _run_job | Orientation evidence is collected from rendered-layout checks and Node-side custom checks, then merged in the combined runner. | Some specific mobile-device hardware locks cannot be simulated on a server. |
| 1.3.5 Identify Input Purpose | Covered | 100% | AA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Relies entirely on standard HTML implementation. |
| 1.4.1 Use of Color | Covered | 75% | A | a11y-node/src/custom-checks/use-of-color.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Links drawn inside a graphical canvas are not readable. |
| 1.4.2 Audio Control | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Highly obfuscated background audio injections might evade detection. |
| 1.4.3 Contrast (Minimum) | Partially Covered | 50% | AA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js; a11y-python/a11y/accessibility/rules/non_text/alttext.py | AccessibilityService.analyseUrlFlat; mapResultsFlat; AltTextAccessibilityAuditor.generate_audit_report | Node runs axe contrast rules while the Python image audit adds OCR-backed contrast/image evidence where text is rendered inside images. | OCR-backed contrast depends on detectable text regions and remains weak on complex gradients/backgrounds. |
| 1.4.4 Resize text | Partially Covered | 50% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/resize_text.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; rendered evaluator; _run_job | SC is routed through run_resize_text_audit and executed inside the rendered-layout pipeline before being merged into combined output. | Resize-text audits are rendered-layout heuristics rather than a browser-native zoom oracle. |
| 1.4.5 Images of Text | Partially Covered | 50% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; AltTextAccessibilityAuditor.generate_audit_report; _make_finding | SC is wired through run_image_audit; the Python image audit emits 1.1.1/1.4.5/1.4.11/4.1.2 records and combined findings localize criterion labels. | Japanese logo/CJK image-text cases and one complex-chart OCR exemption fail in tests/test_alt_text_auditor.py. |
| 1.4.6 Contrast (Enhanced) | Covered | 75% | AAA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js; a11y-python/a11y/accessibility/rules/non_text/alttext.py | AccessibilityService.analyseUrlFlat; mapResultsFlat; AltTextAccessibilityAuditor.generate_audit_report | Node runs axe contrast rules while the Python image audit adds OCR-backed contrast/image evidence where text is rendered inside images. | Same limitations as standard contrast. |
| 1.4.10 Reflow | Partially Covered | 50% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/reflow.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Hidden overflowing text on parent elements can occasionally mask internal breaks. |
| 1.4.11 Non-text Contrast | Partially Covered | 25% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/non_text/alttext.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Coverage is limited to machine-segmentable controls/images; complex graphics remain difficult to score automatically. |
| 1.4.12 Text Spacing | Covered | 75% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/input_modalities/text_spacing_auditor.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; generate_audit_report; _run_job | SC is wired through run_text_spacing_audit and merged into the combined report; targeted text-spacing tests pass. | Rendered-layout tests pass, but no dedicated Japanese end-to-end text-spacing test was found. |
| 1.4.13 Content on Hover or Focus | Partially Covered | 50% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/hover_focus_content.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Focus-only popovers that behave entirely differently than mouse hovers can be under-modeled. |
| 2.1.1 Keyboard | Partially Covered | 50% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | No full keyboard traversal auditor exists; coverage is mostly axe/static focus signals. |
| 2.1.2 No Keyboard Trap | Covered | 75% | A | a11y-node/src/custom-checks/keyboard-trap.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Closed or highly customized shadow components limit deep tracking. |
| 2.1.4 Character Key Shortcuts | Covered | 75% | A | a11y-node/src/custom-checks/character-key-shortcuts.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Shortcuts tied deeply into complex frameworks like React can be invisible to initial scans. |
| 2.2.1 Timing Adjustable | Partially Covered | 25% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Evidence is limited to meta refresh/redirect signals; JavaScript timers are not comprehensively observed. |
| 2.2.2 Pause, Stop, Hide | Partially Covered | 50% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/timing/pause_stop_hide_auditor.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; generate_audit_report; _run_job | Pause/stop/hide is routed through a dedicated Python auditor and merged into the combined report. | Pause/stop/hide logic exists, but custom JavaScript animations can evade automated detection. |
| 2.2.4 Interruptions | Partially Covered | 25% | AAA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Evidence is limited to static interruption signals, not full runtime interruption behavior. |
| 2.4.1 Bypass Blocks | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Relies on correct semantic HTML coding practices. |
| 2.4.2 Page Titled | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | None. |
| 2.4.3 Focus Order | Partially Covered | 50% | A | a11y-node/src/utils/axeResultMapper.js; a11y-node/src/services/accessibility.service.js | RULE_SC_FALLBACK; AccessibilityService.analyseUrlFlat | The SC is inferred from fallback mappings over best-practice/focus signals rather than from a dedicated end-to-end rule engine. | Mapped mainly through fallback focus-order/tabindex signals, not a full tab-order validator. |
| 2.4.4 Link Purpose (In Context) | Partially Covered | 50% | A | a11y-node/src/custom-checks/link-purpose.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Meaningful link purpose in context still requires human judgment beyond current heuristics. |
| 2.4.5 Multiple Ways | Covered | 75% | AA | a11y-node/src/custom-checks/multiple-ways.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Single-page detection cannot prove site-wide alternate navigation paths. |
| 2.4.6 Headings and Labels | Partially Covered | 50% | AA | a11y-node/src/utils/axeResultMapper.js; a11y-node/src/services/accessibility.service.js | RULE_SC_FALLBACK; AccessibilityService.analyseUrlFlat | The SC is inferred from fallback mappings over best-practice/focus signals rather than from a dedicated end-to-end rule engine. | Coverage is mostly heading heuristics, not full label quality or semantic clarity checks. |
| 2.4.7 Focus Visible | Covered | 75% | AA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Delayed animations can hide the outline during our capture window. |
| 2.4.8 Location | Covered | 75% | AAA | a11y-node/src/custom-checks/location.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Breadcrumb/location cues are detectable, but purely visual state indicators are out of scope. |
| 2.4.9 Link Purpose (Link Only) | Covered | 75% | AAA | a11y-node/src/custom-checks/link-purpose.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Phrase heuristics help, but hidden/contextual cues still need review. |
| 2.4.11 Focus Not Obscured (Minimum) | Partially Covered | 50% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/focus_not_obscured_minimum.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Rendered overlap detection exists, but obscuration remains heuristic in dynamic layouts. |
| 2.4.12 Focus Not Obscured (Enhanced) | Partially Covered | 50% | AAA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rendered/evaluators/focus_not_obscured_enhanced.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Same rendered-layout limitations as 2.4.11, with stricter thresholds. |
| 2.4.13 Focus Appearance | Covered | 75% | AA | a11y-node/src/custom-checks/focus-appearance.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Complex shadow implementations can occasionally confuse our pixel boundaries. |
| 2.5.2 Pointer Cancellation | Covered | 75% | A | a11y-node/src/custom-checks/pointer-cancellation.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Obfuscated framework click listeners evade raw code inspection. |
| 2.5.3 Label in Name | Covered | 75% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; LabelInNameAuditor.generate_audit_report; _run_job | SC is wired through run_label_in_name_audit, and the auditor contains explicit CJK detection/sub-string logic with passing Japanese tests. | CJK substring matching tests pass, but /analyse-url rule handlers in run_router.py hardcode lang=en for URL-only rule routes. |
| 2.5.7 Dragging Movements | Covered | 75% | AA | a11y-node/src/custom-checks/dragging-movements.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Completely custom dragging scripts lack predictable signatures. |
| 2.5.8 Target Size (Minimum) | Covered | 75% | AA | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/input_modalities/target_size_auditor.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; generate_audit_report; _run_job | SC is wired through run_target_size_audit and most targeted tests pass. | Target-size logic largely works, but tests/test_target_size_auditor.py still fails one CSV schema check. |
| 3.1.1 Language of Page | Covered | 100% | A | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | None. |
| 3.1.2 Language of Parts | Covered | 100% | AA | a11y-node/src/services/accessibility.service.js; a11y-node/src/utils/axeResultMapper.js | AccessibilityService.analyseUrlFlat; _tagsForLevel; mapResultsFlat | Node runs axe-core with WCAG tag filters and localizes flat findings by lang; targeted Jest tests confirm locale application and Japanese label mapping. | Requires manual QA to ensure language shifts are actually tagged. |
| 3.1.6 Pronunciation | Covered | 75% | AAA | a11y-node/src/custom-checks/pronunciation.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Pronunciation coverage is Japanese-aware, but only for ruby/furigana patterns visible in the DOM. |
| 3.2.1 On Focus | Covered | 75% | A | a11y-node/src/custom-checks/on-focus.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Silent single-page app visual shifts might look like redirects to the scanner. |
| 3.2.2 On Input | Covered | 75% | A | a11y-node/src/custom-checks/on-input.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Server-side only submissions without navigation evade detection. |
| 3.2.6 Consistent Help | Covered | 75% | AA | a11y-node/src/custom-checks/consistent-help.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Consistency claims need multi-page evidence; single-page scans only provide partial proof. |
| 3.3.1 Error Identification | Partially Covered | 50% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/forms/form_auditor.py; a11y-python/a11y/api/v1/combined/findings.py | RULE_FLAGS; generate_audit_report / evaluator; _make_finding | SC is wired through RULE_FLAGS to a dedicated Python auditor/evaluator, and the findings layer localizes criterion labels through the shared i18n loader. | Form auditor checks programmatic associations, not actual submitted error wording or server-side behavior. |
| 3.3.2 Labels or Instructions | Covered | 75% | A | a11y-python/a11y/api/v1/rules/run_router.py; a11y-python/a11y/accessibility/rules/forms/form_auditor.py; a11y-python/a11y/api/v1/combined/runner.py | RULE_FLAGS; FormAccessibilityAuditor.generate_audit_report; _run_job | SC is wired through run_form_audit; the form auditor checks labels, required indicators, and programmatic error association before findings are merged into the combined report. | Japanese required-marker heuristics exist and pass tests, but instruction quality still needs review. |
| 3.3.3 Error Suggestion | Covered | 75% | AA | a11y-node/src/custom-checks/error-suggestion.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Evidence relies on keyword/template heuristics; dynamic tooltip validations are hard to trigger automatically. |
| 3.3.4 Error Prevention (Legal, Financial) | Covered | 75% | AA | a11y-node/src/custom-checks/error-prevention.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Keyword heuristics cover transaction/legal cues but not every application state. |
| 3.3.7 Redundant Entry | Covered | 75% | A | a11y-node/src/custom-checks/redundant-entry.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Redundancy detection is heuristic and backend data reuse is not observable from the frontend. |
| 3.3.8 Accessible Authentication | Covered | 75% | AA | a11y-node/src/custom-checks/accessible-auth.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Third-party CAPTCHA or auth iframes remain opaque to DOM-level checks. |
| 4.1.1 Parsing | Covered | 100% | A | a11y-node/src/custom-checks/html-parsing.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Not a replacement for full W3C HTML validation. |
| 4.1.2 Name, Role, Value | Covered | 75% | A | a11y-node/src/services/accessibility.service.js; a11y-python/a11y/accessibility/rules/non_text/alttext.py; a11y-python/a11y/api/v1/combined/runner.py | AccessibilityService.analyseUrlFlat; _check_4_1_2; _run_job | General 4.1.2 coverage comes from axe-core in Node, while functional-image accessible-name checks come from the Python image audit and are merged in the combined runner. | Strong axe coverage exists, but the Japanese logo-name path in the Python image audit still fails a targeted alt-text test. |
| 4.1.3 Status Messages | Covered | 75% | AA | a11y-node/src/custom-checks/status-messages.check.js; a11y-node/src/custom-checks/sharedAssets.js; config/universal.yml | check; runAll; renderReasonTemplate/getKeywordList | A Node custom check runs through runAll(page, { lang }); sharedAssets resolves en/ja assets from universal.yml, and targeted Jest coverage exists for localized behavior. | Localized status-message heuristics exist, but silent runtime updates may still be missed. |

## 5. Side-by-Side Comparison

| Capability | Japanese | English | Automation |
|---|---|---|---|
| Detection / routing | 50% Partially Covered | 100% Covered | 75% Covered |
| Locale mapping | 100% Covered | 100% Covered | 100% Covered |
| Prompt / reason templates | 50% Partially Covered | 50% Partially Covered | 50% Partially Covered |
| Parsing / OCR | 50% Partially Covered | 75% Covered | 50% Partially Covered |
| Validation | 50% Partially Covered | 75% Covered | 50% Partially Covered |
| Reporting / labels | 75% Covered | 100% Covered | 75% Covered |
| Export / API output | 50% Partially Covered | 75% Covered | 50% Partially Covered |
| Fallback handling | 100% Covered | 100% Covered | 100% Covered |
| Tests | 50% Partially Covered | 75% Covered | 50% Partially Covered |
| Rule automation | 50% Partially Covered | 75% Covered | 44.0% Partially Covered |

## 6. Gaps and Missing Coverage

- High: Japanese alt-text/image coverage is overstated by the existing workbook narratives. a11y-python/a11y/accessibility/rules/non_text/alttext.py and tests/test_alt_text_auditor.py show English-only logo/action heuristics and four failing Japanese-focused tests.
- High: WCAG 1.2.1 media quality automation is not reliably executable in the current environment. a11y-python/a11y/accessibility/rules/media/quality_engine.py imports nltk and faster_whisper; targeted pytest slices fail with ModuleNotFoundError.
- High: Per-rule URL-only handlers bypass Japanese routing. a11y-python/a11y/api/v1/rules/run_router.py:create_rule_url_only_handler hardcodes lang="en".
- Medium: Some advertised automation is proxy-only, not criterion-complete. 2.4.3 and 2.4.6 depend on RULE_SC_FALLBACK mappings in a11y-node/src/utils/axeResultMapper.js.
- Medium: Target-size output contract is drifting from tests. tests/test_target_size_auditor.py still fails the expected CSV schema assertion.
- Medium: Image-audit stage warning propagation is not fully stable. tests/test_image_audit_stage.py still fails one warning-surfacing path.
- Low: Many Node custom checks are heuristic keyword scans over a single page or crawl depth. This is valid automation evidence but not full semantic proof of compliance.
- Low: The repository does not contain a native XLSX coverage-export implementation. Workbook updates have to be performed externally rather than through product export code.

## 7. Final Verdict

- Japanese is supported in metadata, locale mapping, several Node custom checks, OCR setup, sensory parsing, and label-in-name logic, but it is not fully supported end to end. The current evidence supports `Partially Covered` at 50%.
- English is the true base execution language and is broadly wired across Node and Python. The current evidence supports `Covered` at 75%, not 100%, because several criteria remain only partially automated or environment-dependent.
- Automation claims in the workbook were overstated. Raw rule counts still show 55 rules with some automation path, but weighted effective automation is only 44.0% across all 87 criteria.
- The strongest claims are locale mapping, Japanese rule metadata, Node result localization, and direct structural/axe-backed rules. The weakest claims are Japanese image handling, media quality validation, and proxy-only coverage for some navigation/focus criteria.

## 8. Proof Index

- `a11y-node/src/controllers/accessibility.controller.js` — `analyze; analyseUrlFlat; analyseUrl`
- `a11y-node/src/services/accessibility.service.js` — `_sanitizeLocaleLang; _configureAxeLocale; analyseUrlFlat`
- `a11y-node/src/utils/rulesLoader.js` — `getRules; getLocaleData; getAxeRuleLocales`
- `a11y-node/src/utils/axeResultMapper.js` — `mapResultsFlat; mapCustomResultsFlat; RULE_SC_FALLBACK`
- `a11y-node/src/custom-checks/sharedAssets.js` — `sanitizeLang; getKeywordList; renderReasonTemplate`
- `config/universal.yml` — `language.supported; reason_templates; ja keyword lists`
- `i18n/rules.yml` — `base rule metadata`
- `i18n/locales/ja.yml` — `Japanese overlay metadata`
- `a11y-python/a11y/i18n/loader.py` — `load_rules; get_wcag_names; get_suggested_fixes`
- `a11y-python/a11y/api/v1/rules/metadata.py` — `get_wcag_rules`
- `a11y-python/a11y/api/v1/rules/run_router.py` — `RULE_FLAGS; create_rule_url_only_handler`
- `a11y-python/a11y/api/v1/combined/runner.py` — `_run_job; _merge_findings`
- `a11y-python/a11y/api/v1/combined/findings.py` — `_lang_ctx; _make_finding`
- `a11y-python/a11y/api/v1/combined/report.py` — `_build_report`
- `a11y-python/a11y/text_detector/ocrbase.py` — `get_ocr_reader`
- `a11y-python/a11y/text_detector/paddleocrbase.py` — `get_ocr_reader`
- `a11y-python/a11y/accessibility/rules/non_text/sensory_auditor.py` — `_detect_lang and Japanese sensory taxonomies`
- `a11y-python/a11y/accessibility/rules/input_modalities/label_in_name_auditor.py` — `_contains_cjk; _label_in_name`
- `a11y-python/a11y/accessibility/rules/forms/form_auditor.py` — `_REQUIRED_PATTERN; generate_audit_report`
- `a11y-python/a11y/accessibility/rules/non_text/alttext.py` — `_check_1_1_1_logo; _check_1_1_1_button; _check_4_1_2; _check_1_4_5`
- `a11y-python/a11y/accessibility/rules/media/media_auditor.py` — `_gate_4_find_transcript; generate_audit_report`
- `a11y-python/a11y/accessibility/rules/media/quality_engine.py` — `import-time dependencies and Gate 5 checks`
- `a11y-node/tests/services/accessibility.service.flat.test.js` — `lang=ja locale wiring test`
- `a11y-node/tests/utils/axeResultMapper.custom-flat.test.js` — `Japanese criterion/reason localization tests`
- `a11y-node/tests/custom-checks/sharedAssets.test.js` — `multilingual keyword/template tests`
- `a11y-python/tests/test_alt_text_auditor.py` — `Japanese image-path failures`
- `a11y-python/tests/test_media_auditor.py` — `media dependency failures`
- `a11y-python/tests/test_target_size_auditor.py` — `CSV schema drift`

## Test Evidence Snapshot

- Node targeted localization suites: 25 passed, 0 failed.
- Python targeted language-sensitive suites: 451 passed, 19 failed.
- High-signal Python failures: Japanese alt-text paths (4), media quality/dependency path (13), target-size CSV schema drift (1), image-audit-stage warning propagation (1).