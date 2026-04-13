# Node Custom Rules Review, Fixture Plan, and Universal Config Proposal

Date: 2026-04-13
Scope: `ka11y-node/src/custom-checks`, `ka11y-node/src/utils`, `ka11y-node/src/controllers`, `ka11y-python/ka11y`

## Summary

The Node custom-rule stack already has strong rule coverage, but it is not yet aligned with the Python side in three important areas:

1. `lang` is only partially applied in Node.
2. Japanese behavior is still embedded inside rule code instead of coming from shared config/YAML.
3. Fixture coverage is mostly unit-level and English-biased; there is no reusable EN/JA contract layer for localized reasons, YAML-driven assets, and cross-service parity.

This document focuses on what needs to be fixed next, not on restating the existing rule-by-rule analysis in `ka11y-node/docs/RULE_ANALYSIS.md`.

## Current Findings

### 1. Localization is incomplete in Node custom-rule output

Observed behavior:

- `POST /api/v1/analyse-url-flat` accepts `lang`, but grouped endpoints do not.
- Flat findings localize `suggested_fix`, but `criterion_name` still comes from an English-only startup map.
- Custom-check `reason` strings remain hardcoded English text.

Evidence:

- `ka11y-node/src/controllers/accessibility.controller.js` only accepts `lang` for `analyseUrlFlat`.
- `ka11y-node/src/utils/wcagMetadata.js` builds `WCAG_NAMES` from `getRules('en')` once at startup.
- `ka11y-node/src/utils/axeResultMapper.js` uses `_criterionName()` from the English map, while `_suggestedFix()` reads the requested locale.
- Python already localizes finding names at finding-construction time via `get_wcag_names(_lang)` in `ka11y-python/ka11y/api/v1/combined/findings.py`.

Impact:

- `lang=ja` currently gives mixed-language output: Japanese `suggested_fix`, English `criterion_name`, English custom-rule `reason`.
- Node is not functionally equivalent to the Python i18n path.

### 2. Japanese behavior is not config-driven

Observed behavior:

- Rule heuristics embed Japanese/CJK keywords directly inside the Node rule source.
- The custom-check runner only passes `page`; it does not pass `lang`, config, or rule assets.
- Python already reads shared crawler/language behavior from config helpers such as `get_cjk_langs()`.

Examples of hardcoded Japanese behavior in Node:

- `audio-transcript.check.js`: transcript keywords such as `文字起こし`, `トランスクリプト`, `字幕`
- `multiple-ways.check.js`: `検索`, `サイトマップ`, `目次`
- `consistent-help.check.js`: `お問い合わせ`, `ヘルプセンター`, `チャット`
- `pointer-cancellation.check.js`: Japanese action verbs such as `送信`, `購入`, `削除`
- `pronunciation.check.js`: hardcoded CJK language prefixes and thresholds

Impact:

- Japanese behavior cannot be updated centrally.
- Node and Python can drift even when they are trying to solve the same problem.
- Adding a new language means editing many checks instead of adding one config asset.

### 3. YAML is duplicated and already drifting

Observed behavior:

- Node, Python, and repo-root i18n assets are not a single source of truth.
- Some files match, some already differ.

Repository state observed during this review:

- `i18n/rules.yml` and `ka11y-node/i18n/rules.yml` currently match.
- `ka11y-node/i18n/locales/ja.yml` differs from `i18n/locales/ja.yml`.
- `ka11y-node/i18n/rules.yml` differs from `ka11y-python/i18n/rules.yml`.
- `ka11y-node/i18n/locales/ja.yml` and `ka11y-python/i18n/locales/ja.yml` currently match.

Impact:

- Severity, names, descriptions, and suggested fixes can drift by service.
- Any new Japanese copy or rule metadata can become inconsistent by accident.
- This is the opposite of a universal reusable config.

### 4. Failure reasons are string-only and not reusable

Observed behavior:

- Custom checks emit fully rendered English `reason` strings directly from JS.
- There is no shared `reason_code`, no template key, and no parameter payload.
- The only localization-ready text on the Node side today is WCAG metadata from YAML.

Impact:

- Reason text cannot be translated consistently.
- Assertions become brittle because tests must match English prose.
- Reuse across Node/Python is limited because there is no shared semantic reason contract.

### 5. Flat mapping drops structured evidence from some custom checks

Observed behavior:

- `mapCustomResultsFlat()` only preserves `rule.elements` or `rule.element`.
- Several checks collect `selector`, `target`, `snippet`, `source`, or `mediaQuery`, but those fields are not normalized into the flat finding shape.
- When explicit element data is absent, the mapper falls back to parsing HTML fragments out of `reason`, or to a page-level `<html>` placeholder for `needs_review`.

Examples:

- `orientation.check.js` builds findings with `selector`, `target`, `snippet`, `source`, `mediaQuery`.
- `mapCustomResultsFlat()` does not read those fields.

Impact:

- Failure reasons become the only durable carrier of evidence.
- Some findings lose precise selectors and snippets when converted to flat output.
- Fixture design must cover evidence preservation, not just status and reason text.

### 6. Fixture coverage is missing at the edges

Observed behavior:

- Two shipped rules have no dedicated Jest files: `orientation.check.js` and `pronunciation.check.js`.
- Existing Japanese coverage is mostly "source contains JP keyword" tests, not functional fixture tests.
- There are no API-level fixtures asserting:
  - localized `criterion_name`
  - localized `reason`
  - YAML/config-driven behavior
  - cross-service Node/Python parity

Impact:

- The highest-risk language/config behaviors are not protected.
- Future attempts to move Japanese assets into config can regress silently.

### 7. `custom-pronunciation` is under-specified in the loader

Observed behavior:

- `pronunciation.check.js` exports no `MODE`, `DESCRIPTION`, or `FALLBACK_DESCRIPTION`.
- It is not present in the legacy metadata tables in `src/custom-checks/index.js`.
- Loader fallback therefore makes it implicitly `static` with a generic fallback description on failure.

Impact:

- Execution ordering is implicit instead of declared.
- Failure messages for loader/execution fallback are less precise than other custom rules.

## What the Fixture Plan Must Cover

The fixture strategy should be layered.

### Layer 1: Rule-unit fixtures

Goal:

- Validate rule logic with stable, isolated inputs.
- Stop relying on "source contains Japanese keyword" as the main JP test.

Coverage:

- direct `run(page, context)` unit tests
- explicit pass/fail/needs-review expectations
- explicit `reason_code`, rendered `reason`, and evidence expectations once the reason contract exists

### Layer 2: Mapper-contract fixtures

Goal:

- Validate `mapCustomResultsFlat()` and grouped output mapping.

Coverage:

- element preservation
- selector/snippet preservation
- localized `criterion_name`
- localized `suggested_fix`
- localized rendered `reason`
- stable fallback behavior for unknown SC and missing evidence

### Layer 3: API fixtures

Goal:

- Validate end-to-end behavior through the controller/service boundary.

Coverage:

- `lang=en` and `lang=ja`
- grouped and flat endpoints
- YAML parse fallback behavior
- invalid language fallback behavior

### Layer 4: Cross-service parity fixtures

Goal:

- Ensure Node and Python consume the same universal config and i18n assets.

Coverage:

- same `criterion_name`
- same `suggested_fix`
- same language lists such as CJK languages
- same reason template keys for equivalent result families

## English Fixture Plan

Recommended fixture folders:

```text
ka11y-node/tests/fixtures/custom-rules/en/
ka11y-node/tests/fixtures/shared/
ka11y-node/tests/fixtures/expected/en/
```

Recommended English fixture scenarios:

| Area | Fixture | Expected assertions |
| --- | --- | --- |
| Audio transcript | page with `<audio>` and no transcript asset | `status=needs_review/incomplete`, stable reason key, evidence includes audio selector |
| Multiple ways | page with only one nav mechanism | `status=needs_review`, suggestion references missing mechanisms |
| Consistent help | page with footer help link and page without help | pass and needs-review branches both covered |
| Error suggestion | page with visible invalid message but no correction guidance | fail with normalized reason params |
| Orientation | manifest lock, inline script lock, CSS media hide, viewport lock | fail vs needs-review split preserved with evidence |
| Pronunciation | English page with no CJK, English page with `lang=ja` subsection | not-applicable vs section-level detection |
| Redundant entry | multi-step form with duplicate personal-data fields | fail and needs-review branches with selector evidence |

Minimum English assertions per fixture:

- `rule_id`
- `wcag_sc`
- `status`
- `reason_code`
- rendered `reason`
- `criterion_name`
- `suggested_fix`
- `element` or structured evidence

## Japanese Fixture Plan

Recommended fixture folders:

```text
ka11y-node/tests/fixtures/custom-rules/ja/
ka11y-node/tests/fixtures/expected/ja/
```

Recommended Japanese fixture scenarios:

| Area | Fixture | Expected assertions |
| --- | --- | --- |
| Audio transcript | transcript link labeled `文字起こし` or `トランスクリプト` | pass when config keywords match; fail/needs-review when missing |
| Multiple ways | `検索`, `サイトマップ`, `目次`, Japanese nav | detection uses config-provided JP labels, not hardcoded regex |
| Consistent help | `お問い合わせ`, `サポート`, chat widget labels | pass and needs-review branches |
| Error suggestion | Japanese validation copy such as `入力してください`, `有効なメールアドレス` | fail only when guidance is missing, not when text is merely non-English |
| Error prevention | Japanese commerce/registration flow with `確認`, `申込`, `注文` | high-risk flow detection remains correct through config |
| Location | breadcrumb / current-page markers in Japanese | pass and fail branches |
| Pronunciation | `lang=ja` page with no ruby, partial ruby, sufficient ruby | fail, needs-review, and pass coverage |
| Mixed-language page | English page with explicit `[lang="ja"]` subsection | section-level Japanese behavior without changing whole-page output language |

Japanese-specific contract assertions:

- `lang=ja` localizes:
  - `criterion_name`
  - `suggested_fix`
  - rendered `reason`
- `lang=en` on the same Japanese fixture keeps English copy but still uses Japanese-aware detection behavior
- JP behavior comes from YAML/config assets, not source-string regex literals

## Universal Config and YAML Design

### Target architecture

The Node side should follow the Python pattern:

- one config loader
- one i18n loader
- one shared language-asset loader
- reusable across Node and Python

Recommended shared layout at repo root:

```text
config/
  universal.yml
i18n/
  rules.yml
  locales/
    en.yml
    ja.yml
  check-assets/
    base.yml
    ja.yml
    en.yml
```

Responsibilities:

- `config/universal.yml`
  - non-translated behavior config
  - language families
  - thresholds
  - limits
- `i18n/rules.yml`
  - WCAG metadata shared by all services
- `i18n/locales/*.yml`
  - localized names, descriptions, suggested fixes
- `i18n/check-assets/*.yml`
  - per-language heuristic terms and reason templates used by custom checks

### Example universal YAML shape

```yaml
version: 1

language:
  supported: ["en", "ja"]
  cjk_langs: ["ja", "zh", "zh-CN", "zh-TW", "zh-HK", "ko"]

checks:
  pronunciation:
    cjk_ratio_threshold: 0.05
    ruby_min_coverage_pct: 30
    cjk_lang_prefixes: ["ja", "zh", "ko", "zh-hans", "zh-hant", "zh-tw", "zh-cn"]

  audio_transcript:
    transcript_keywords:
      en: ["transcript", "caption", "text version", "audio text"]
      ja: ["文字起こし", "書き起こし", "トランスクリプト", "字幕", "キャプション", "テキスト版"]

  multiple_ways:
    search_keywords:
      en: ["search", "site map", "table of contents"]
      ja: ["検索", "サイトマップ", "目次"]

reason_templates:
  custom-audio-transcript:
    no-audio:
      en: "No <audio> elements found on this page."
      ja: "このページに <audio> 要素はありません。"
    missing-transcript:
      en: "{issue_count} of {audio_count} audio element(s) have no detectable text alternative."
      ja: "{audio_count} 件の audio 要素のうち {issue_count} 件に検出可能なテキスト代替がありません。"
```

### Loader behavior

Node target:

- add `src/utils/universalConfigLoader.js`
- add `src/utils/checkAssetsLoader.js`
- pass `{ lang, config, assets }` into every custom check

Python target:

- keep `load_config()` but point it at the same shared root config path
- keep `ka11y.i18n.loader` but resolve from the shared root i18n path

Environment override suggestion:

- `KA11Y_SHARED_CONFIG_DIR`
- `KA11Y_SHARED_I18N_DIR`

This removes the current per-service copies under `ka11y-node/i18n` and `ka11y-python/i18n`.

## Failure Reason Contract

The next version of custom-rule output should stop treating `reason` as the source of truth.

Recommended rule output shape before mapping:

```json
{
  "ruleId": "custom-audio-transcript",
  "status": "incomplete",
  "impact": "serious",
  "reasonCode": "missing-transcript",
  "reasonParams": {
    "issue_count": 2,
    "audio_count": 3
  },
  "evidence": [
    {
      "selector": "#podcast-player",
      "tag": "audio",
      "html": "<audio id=\"podcast-player\">"
    }
  ],
  "helpUrl": "https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded"
}
```

Then render:

- `criterion_name` from localized WCAG YAML
- `suggested_fix` from localized WCAG YAML
- `reason` from localized reason templates plus `reasonParams`

Benefits:

- stable fixture assertions
- reusable wording across Node and Python
- easy JA/EN localization
- better evidence preservation

## Test Files That Need to Be Added First

Priority additions:

1. `ka11y-node/tests/custom-checks/orientation.check.test.js`
2. `ka11y-node/tests/custom-checks/pronunciation.check.test.js`
3. mapper tests for localized `criterion_name` and localized `reason`
4. API tests for `lang=ja` and `lang=en`
5. config-loader parity tests that load the same YAML assets in Node and Python

Also upgrade the current JP source-string tests into real fixture tests.

Current tests such as:

- "includes Japanese transcript keywords in source heuristics"
- "includes Japanese navigation keywords in source heuristics"

should remain only as light smoke coverage, not as the main JP contract.

## Recommended Implementation Order

1. Create shared root config/i18n assets and loaders.
2. Remove duplicated per-service YAML copies or make them generated mirrors only.
3. Change custom checks to accept `context = { lang, config, assets, templates }`.
4. Introduce `reasonCode` + `reasonParams` + `evidence`.
5. Update mappers so they preserve structured evidence and localize names plus reasons at render time.
6. Add EN and JA fixtures at unit, mapper, API, and cross-service parity layers.

## Definition of Done

The custom-rule stack should be considered fixed when all of the following are true:

- `lang=ja` returns Japanese `criterion_name`, `suggested_fix`, and `reason`
- `lang=en` still uses Japanese-aware heuristics when the page content is Japanese
- Node and Python read the same shared YAML/config assets
- no custom check relies on hardcoded JP regex lists for behavior that belongs in config
- flat findings preserve selectors/snippets/evidence without parsing HTML back out of `reason`
- orientation and pronunciation have dedicated fixture coverage
- EN and JA fixtures exist for both rule logic and API output
