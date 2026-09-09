# ka11y — Implemented Rule Coverage

Every WCAG 2.2 success criterion in the ka11y catalogue (`i18n/rules.yml`) and which of the
three audit engines implements it.

- **Branch:** `production`
- **Catalogue:** 87 success criteria (WCAG 2.2, Levels A–AAA)
- **Implemented:** **82 of 87** criteria have at least one engine
- **Not implemented:** 5 (all Level AAA)

## Engines

| Engine | Location | Rules | Criteria |
|---|---|---:|---:|
| `custom-checks` | `ka11y-node/src/custom-checks/*.check.js` | 67 | 67 |
| `axe-core` 4.12.1 | `ka11y-node` — tags wcag2a/aa/aaa, wcag21a/aa, wcag22a/aa, best-practice | 103 | 28 |
| `python` | `ka11y-python/ka11y/api/v1/combined/findings.py` | 10 | 10 |
| **Union** | | | **82** |

Each of the 67 custom checks owns exactly one criterion (one `const SC` per file), and all 67
are registered in `custom-checks/index.js` and executed by `runAll()` on every page.

### Coverage by level

| Level | Implemented |
|---|---:|
| A | 31 |
| AA | 26 |
| AAA | 25 |
| **Total** | **82** |

### Criteria covered by all three engines (5)

`1.1.1`, `1.2.1`, `1.2.2`, `1.4.2`, `1.4.6` — everywhere else the engines are complementary, not redundant.

---

## Coverage by principle

### 1. Perceivable — 27/29 covered

| SC | Criterion | Level | Engines | Rule IDs |
|---|---|---|---|---|
| `1.1.1` | Non-text Content | A | custom, axe, python | `custom-background-image-content` `python_1_1_1_alt` `aria-meter-name` `aria-progressbar-name` `image-alt` `input-image-alt` `object-alt` `role-img-alt` `svg-img-alt` |
| `1.2.1` | Audio-only and Video-only (Prerecorded) | A | custom, axe, python | `custom-audio-transcript` `python_1_2_1_media` `audio-caption` |
| `1.2.2` | Captions (Prerecorded) | A | custom, axe, python | `custom-captions-prerecorded` `python_1_2_2_media` `video-caption` |
| `1.2.3` | Audio Description or Media Alternative (Prerecorded) | A | custom, python | `custom-audio-description` `python_1_2_3_media` |
| `1.2.4` | Captions (Live) | AA | custom | `custom-captions-live` |
| `1.2.5` | Audio Description (Prerecorded) | AA | custom | `custom-audio-description-prerecorded` |
| `1.2.6` | Sign Language (Prerecorded) | AAA | — | *not implemented* |
| `1.2.7` | Extended Audio Description (Prerecorded) | AAA | custom | `custom-extended-audio-description` |
| `1.2.8` | Media Alternative (Prerecorded) | AAA | custom | `custom-media-alternative` |
| `1.2.9` | Audio-only (Live) | AAA | custom | `custom-audio-only-live` |
| `1.3.1` | Info and Relationships | A | axe | `aria-hidden-body` `aria-required-children` `aria-required-parent` `definition-list` `dlitem` `list` `listitem` `p-as-heading` `table-fake-caption` `td-has-header` `td-headers-attr` `th-has-data-cells` |
| `1.3.2` | Meaningful Sequence | A | custom | `custom-meaningful-sequence` |
| `1.3.3` | Sensory Characteristics | A | custom | `custom-sensory-characteristics` |
| `1.3.4` | Orientation | AA | custom, axe | `custom-orientation` `css-orientation-lock` |
| `1.3.5` | Identify Input Purpose | AA | axe | `autocomplete-valid` |
| `1.3.6` | Identify Purpose | AAA | custom | `custom-identify-purpose` |
| `1.4.1` | Use of Color | A | custom, axe | `custom-use-of-color` `link-in-text-block` |
| `1.4.2` | Audio Control | A | custom, axe, python | `custom-audio-control` `python_1_4_2_media` `no-autoplay-audio` |
| `1.4.3` | Contrast (Minimum) | AA | axe, python | `python_1_4_3_contrast` `color-contrast` |
| `1.4.4` | Resize Text | AA | axe | `meta-viewport` |
| `1.4.5` | Images of Text | AA | custom, python | `custom-images-of-text` `python_1_4_5_images_of_text` |
| `1.4.6` | Contrast (Enhanced) | AAA | custom, axe, python | `custom-contrast-enhanced` `python_1_4_6_contrast_enhanced` `color-contrast-enhanced` |
| `1.4.7` | Low or No Background Audio | AAA | — | *not implemented* |
| `1.4.8` | Visual Presentation | AAA | custom | `custom-visual-presentation` |
| `1.4.9` | Images of Text (No Exception) | AAA | custom | `custom-images-of-text-no-exception` |
| `1.4.10` | Reflow | AA | custom | `custom-reflow` |
| `1.4.11` | Non-text Contrast | AA | custom, python | `custom-non-text-contrast` `python_1_4_11_non_text_contrast` |
| `1.4.12` | Text Spacing | AA | custom, axe | `custom-text-spacing` `avoid-inline-spacing` |
| `1.4.13` | Content on Hover or Focus | AA | custom | `custom-content-on-hover-focus` |

### 2. Operable — 31/34 covered

| SC | Criterion | Level | Engines | Rule IDs |
|---|---|---|---|---|
| `2.1.1` | Keyboard | A | axe | `frame-focusable-content` `scrollable-region-focusable` `server-side-image-map` |
| `2.1.2` | No Keyboard Trap | A | custom | `custom-keyboard-trap` |
| `2.1.3` | Keyboard (No Exception) | AAA | custom, axe | `custom-keyboard-no-exception` `scrollable-region-focusable` |
| `2.1.4` | Character Key Shortcuts | A | custom | `custom-character-key-shortcuts` |
| `2.2.1` | Timing Adjustable | A | axe | `meta-refresh` |
| `2.2.2` | Pause, Stop, Hide | A | custom, axe | `custom-pause-stop-hide` `blink` `marquee` |
| `2.2.3` | No Timing | AAA | — | *not implemented* |
| `2.2.4` | Interruptions | AAA | axe | `meta-refresh-no-exceptions` |
| `2.2.5` | Re-authenticating | AAA | — | *not implemented* |
| `2.2.6` | Timeouts | AAA | — | *not implemented* |
| `2.3.1` | Three Flashes or Below Threshold | A | custom | `custom-three-flashes` |
| `2.3.2` | Three Flashes | AAA | custom | `custom-three-flashes-no-exception` |
| `2.3.3` | Animation from Interactions | AAA | custom | `custom-animation-from-interactions` |
| `2.4.1` | Bypass Blocks | A | axe | `bypass` |
| `2.4.2` | Page Titled | A | axe | `document-title` |
| `2.4.3` | Focus Order | A | custom | `custom-focus-order` |
| `2.4.4` | Link Purpose (In Context) | A | axe | `area-alt` `link-name` |
| `2.4.5` | Multiple Ways | AA | custom | `custom-multiple-ways` |
| `2.4.6` | Headings and Labels | AA | custom | `custom-headings-and-labels` |
| `2.4.7` | Focus Visible | AA | custom | `custom-focus-visible` |
| `2.4.8` | Location | AAA | custom | `custom-location` |
| `2.4.9` | Link Purpose (Link Only) | AAA | custom, axe | `custom-link-purpose` `identical-links-same-purpose` |
| `2.4.10` | Section Headings | AAA | custom | `custom-section-headings` |
| `2.4.11` | Focus Not Obscured (Minimum) | AA | custom | `custom-focus-not-obscured` |
| `2.4.12` | Focus Not Obscured (Enhanced) | AAA | custom | `custom-focus-not-obscured-enhanced` |
| `2.4.13` | Focus Appearance | AA | custom | `custom-focus-appearance` |
| `2.5.1` | Pointer Gestures | A | custom | `custom-pointer-gestures` |
| `2.5.2` | Pointer Cancellation | A | custom | `custom-pointer-cancellation` |
| `2.5.3` | Label in Name | A | axe | `label-content-name-mismatch` |
| `2.5.4` | Motion Actuation | A | custom | `custom-motion-actuation` |
| `2.5.5` | Target Size | AAA | custom | `custom-target-size-enhanced` |
| `2.5.6` | Concurrent Input Mechanisms | AAA | custom | `custom-concurrent-input-mechanisms` |
| `2.5.7` | Dragging Movements | AA | custom | `custom-dragging-movements` |
| `2.5.8` | Target Size (Minimum) | AA | axe | `target-size` |

### 3. Understandable — 21/21 covered

| SC | Criterion | Level | Engines | Rule IDs |
|---|---|---|---|---|
| `3.1.1` | Language of Page | A | axe | `html-has-lang` `html-lang-valid` `html-xml-lang-mismatch` |
| `3.1.2` | Language of Parts | AA | custom, axe | `custom-language-of-parts` `valid-lang` |
| `3.1.3` | Unusual Words | AAA | custom | `custom-unusual-words` |
| `3.1.4` | Abbreviations | AAA | custom | `custom-abbreviations` |
| `3.1.5` | Reading Level | AAA | custom | `custom-reading-level` |
| `3.1.6` | Pronunciation | AAA | custom | `custom-pronunciation` |
| `3.2.1` | On Focus | A | custom | `custom-on-focus` |
| `3.2.2` | On Input | A | custom | `custom-on-input` |
| `3.2.3` | Consistent Navigation | AA | custom | `custom-consistent-navigation` |
| `3.2.4` | Consistent Identification | AA | custom | `custom-consistent-identification` |
| `3.2.5` | Change on Request | AAA | custom, axe | `custom-change-on-request` `meta-refresh-no-exceptions` |
| `3.2.6` | Consistent Help | AA | custom | `custom-consistent-help` |
| `3.3.1` | Error Identification | A | custom | `custom-error-identification` |
| `3.3.2` | Labels or Instructions | A | axe | `form-field-multiple-labels` |
| `3.3.3` | Error Suggestion | AA | custom | `custom-error-suggestion` |
| `3.3.4` | Error Prevention (Legal, Financial, Data) | AA | custom | `custom-error-prevention` |
| `3.3.5` | Help | AAA | custom | `custom-help-mechanism` |
| `3.3.6` | Error Prevention (All) | AAA | custom | `custom-error-prevention-all` |
| `3.3.7` | Redundant Entry | A | custom | `custom-redundant-entry` |
| `3.3.8` | Accessible Authentication (Minimum) | AA | custom | `custom-accessible-auth` |
| `3.3.9` | Accessible Authentication (Enhanced) | AAA | custom | `custom-accessible-auth-enhanced` |

### 4. Robust — 3/3 covered

| SC | Criterion | Level | Engines | Rule IDs |
|---|---|---|---|---|
| `4.1.1` | Parsing | A | custom | `custom-html-parsing` |
| `4.1.2` | Name, Role, Value | A | axe, python | `python_4_1_2_name_role_value` `area-alt` `aria-allowed-attr` `aria-braille-equivalent` `aria-command-name` `aria-conditional-attr` `aria-deprecated-role` `aria-hidden-body` `aria-hidden-focus` `aria-input-field-name` `aria-prohibited-attr` `aria-required-attr` `aria-roledescription` `aria-roles` `aria-tab-name` `aria-toggle-field-name` `aria-tooltip-name` `aria-valid-attr-value` `aria-valid-attr` `button-name` `duplicate-id-aria` `frame-title-unique` `frame-title` `input-button-name` `input-image-alt` `label` `link-name` `nested-interactive` `select-name` `summary-name` |
| `4.1.3` | Status Messages | AA | custom | `custom-status-messages` |

---

## Not implemented (5)

| SC | Criterion | Level | Why |
|---|---|---|---|
| `1.2.6` | Sign Language (Prerecorded) | AAA | Requires a human to judge sign-language interpretation. |
| `1.4.7` | Low or No Background Audio | AAA | Requires listening to background audio levels. |
| `2.2.3` | No Timing | AAA | Requires observing whether any time limit exists across a session. |
| `2.2.5` | Re-authenticating | AAA | Requires an authenticated session that expires and resumes. |
| `2.2.6` | Timeouts | AAA | Requires observing timeout warnings and data-retention behaviour. |

All five need human judgement or multi-session state that a single-page crawl cannot observe.

---

## Notes

1. **Coverage is not accuracy.** An engine listed against a criterion means it emits a finding
   for it — not that the check is complete or correct. Several AAA checks are deliberately
   conservative and return `needs_review` rather than a pass or fail.

2. **`auditor_field_map.py` overstates the Python engine.** Its comment claims it lists every
   WCAG SC "currently consumed by a converter in findings.py" and names 20, but only 10 still
   have a converter. The stale 10 — `1.3.3`, `1.4.12`, `2.2.2`, `2.5.8`, `3.3.1`, `3.3.2`, `3.2.3`, `3.2.4`, `3.1.3`, `2.4.10`
   — have zero references in `findings.py`; their stages were removed (see the
   `STAGE_WEIGHTS` comment in `combined/constants.py`). `tests/test_auditor_field_map.py`
   only asserts registry ⊇ findings.py, so stale entries pass silently. Counts in this document
   come from the live converters, not that registry.

3. **`al_rules.txt` / `al_map.js` are orphaned.** They describe a 69-rule AccessLint→WCAG
   mapping covering 22 criteria, but nothing in the codebase imports either file. The live axe
   config selects rules by tag, yielding 103 rules across 28 criteria. Figures here are read
   from `axe-core` 4.12.1 itself via `axe.getRules()`.

4. **Two Python criteria are also reached on capture failure.** `1.4.3` and `1.4.6` emit an
   extra `needs_review` finding when an image capture fails, via
   `_contrast_capture_failed_to_findings`.

---

*Generated from `i18n/rules.yml`, `ka11y-node/src/custom-checks/*.check.js`,*
*`ka11y-python/ka11y/api/v1/combined/findings.py`, and `axe-core` 4.12.1.*
