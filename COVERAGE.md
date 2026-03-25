# ka11y WCAG Coverage Report

## Executive Summary

This report is based on direct source inspection of `ka11y-node` and `ka11y-python`, the installed local `axe-core` rule inventory, and the latest validation artifacts already present in the repository. The key correction versus the earlier report is that coverage is now counted from criteria that are actually emitted by the current pipelines, not from metadata catalogs alone.

- `ka11y-node` currently emits **45** unique WCAG 2.2 success criteria at maximum (`AAA`) scope.
- `ka11y-python` currently emits **16** unique WCAG 2.2 success criteria through `combined/findings.py` and `combined/stages.py`.
- The combined project emits **52 / 87** WCAG 2.2 success criteria, which is **59.8%** overall coverage.
- Coverage remains strong in Level A and AA, but Level AAA is still narrow: **5 / 30** criteria (**16.7%**).
- The most important correctness caveat is that the Python constants file contains metadata for more criteria than the Python pipeline actually emits, so metadata breadth must not be mistaken for implemented coverage.

## Validation Basis

| Evidence source | Status | Notes |
| --- | --- | --- |
| Node test suite | Verified | `164` tests passed in `ka11y-node/junit.xml` |
| Python test suite | Verified | `515` tests passed in `ka11y-python/tests/report/ka11y_test_report.html` |
| Evidence loop | Verified | `0` bugs after `1` attempt in `ka11y-node/logs/evidence-report.md` |
| Installed axe-core inventory | Verified | Local install is `axe-core 4.11.1`, exposing `102` reachable rules for the configured tags |
| Counting method | Verified | Coverage numbers are based on SCs actually emitted by the Node mapper and Python findings converters |

## Counting Rules and Caveats

| Topic | Decision | Why it matters |
| --- | --- | --- |
| Unit of coverage | WCAG 2.2 success criteria only | Prevents best-practice-only rules from inflating compliance coverage |
| Best-practice rules | Counted separately unless they are explicitly fallback-mapped to a WCAG SC by the Node mapper | Reflects what the current API actually emits in flat findings |
| Python metadata vs implementation | Count from emitted findings, not from `combined/constants.py` alone | `constants.py` lists more SC metadata than `findings.py` currently converts into output |
| Node version basis | Count from the installed local `axe-core 4.11.1` rule inventory | The installed package can differ from the looser semver declared in `package.json` |
| Requested WCAG level | Runtime behaviour is level-gated, but Node keeps `best-practice` enabled at all levels | This means some fallback-mapped SCs can appear even in a lower requested level |

## Coverage Totals by Level

| Level | Total SC | Node | Python | Overlap | Combined covered | Missing | Combined coverage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 31 | 24 | 5 | 4 | 25 | 6 | 80.6% |
| AA | 26 | 17 | 10 | 5 | 22 | 4 | 84.6% |
| AAA | 30 | 4 | 1 | 0 | 5 | 25 | 16.7% |
| Total | 87 | 45 | 16 | 9 | 52 | 35 | 59.8% |

## Coverage by Principle

| Principle | Total SC | Node | Python | Combined | Combined coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| Perceivable | 29 | 13 | 9 | 17 | 58.6% |
| Operable | 34 | 20 | 5 | 22 | 64.7% |
| Understandable | 21 | 9 | 2 | 10 | 47.6% |
| Robust | 3 | 3 | 0 | 3 | 100.0% |

## Stack Contribution Breakdown

| Category | Count | Criteria |
| --- | ---: | --- |
| Overlap between Node and Python | 9 | `1.1.1`, `1.3.4`, `1.4.3`, `1.4.4`, `1.4.12`, `2.2.2`, `2.5.3`, `2.5.8`, `3.3.2` |
| Node-only coverage | 36 | `1.2.1`, `1.2.2`, `1.3.1`, `1.3.2`, `1.3.5`, `1.4.1`, `1.4.2`, `1.4.6`, `2.1.1`, `2.1.2`, `2.1.4`, `2.2.1`, `2.2.4`, `2.4.1`, `2.4.2`, `2.4.3`, `2.4.4`, `2.4.5`, `2.4.6`, `2.4.7`, `2.4.8`, `2.4.9`, `2.4.13`, `2.5.2`, `2.5.7`, `3.1.1`, `3.1.2`, `3.2.1`, `3.2.2`, `3.2.6`, `3.3.3`, `3.3.4`, `3.3.8`, `4.1.1`, `4.1.2`, `4.1.3` |
| Python-only coverage | 7 | `1.4.5`, `1.4.10`, `1.4.11`, `1.4.13`, `2.4.11`, `2.4.12`, `3.3.1` |

## Confidence Summary

Confidence is not the WCAG importance of a rule. It is a practical estimate of how completely and reliably the current automation covers that criterion.

| Confidence | Meaning |
| --- | --- |
| High | The implementation is direct, repeatable, and close to the criterion intent. |
| Medium | The implementation is useful but partly heuristic, context-dependent, or only covers common patterns. |
| Low | The implementation is a narrow proxy or only covers one slice of the criterion. |
| Not covered | No current Node or Python emitter outputs this SC. |

| Level | High | Medium | Low | Covered |
| --- | ---: | ---: | ---: | ---: |
| A | 13 | 9 | 3 | 25 |
| AA | 10 | 11 | 1 | 22 |
| AAA | 2 | 2 | 1 | 5 |
| Total | 25 | 22 | 5 | 52 |

## Node Coverage Composition

| Source family | Unique SC touched | Notes |
| --- | ---: | --- |
| Direct axe WCAG-tagged rules | 26 | Backed by numeric `wcag***` tags in local `axe-core 4.11.1` |
| Fallback-mapped best-practice rules | 8 | Only `2.4.3` and `2.4.6` are fallback-only; the rest overlap direct coverage |
| Custom Node checks | 19 | File-discovered checks in `src/custom-checks/*.check.js` |
| Pure best-practice rules not counted toward WCAG coverage | 8 | `aria-text`, `empty-table-header`, `frame-tested`, `hidden-content`, `label-title-only`, `landmark-complementary-is-top-level`, `landmark-main-is-top-level`, `scope-attr-valid` |

## Python Coverage Composition

| Source family | Unique SC touched | Criteria | Why it matters |
| --- | ---: | --- | --- |
| Image/OCR emitters | 4 | `1.1.1`, `1.4.3`, `1.4.5`, `1.4.11` | alt text, text contrast, images of text, non-text contrast |
| Rendered layout evaluators | 7 | `1.3.4`, `1.4.4`, `1.4.10`, `1.4.12`, `1.4.13`, `2.4.11`, `2.4.12` | Playwright-driven layout, zoom, hover, focus, and obscuration checks |
| Form emitters | 2 | `3.3.1`, `3.3.2` | error identification and labels/instructions |
| Input/timing emitters | 3 | `2.2.2`, `2.5.3`, `2.5.8` | pause/stop/hide, label in name, target size |

## Runtime Coverage by Requested Scan Level

| Requested level | Node reachable SC | Combined reachable SC | Reachable level mix | Caveat |
| --- | ---: | ---: | --- | --- |
| A | 26 | 27 | Node `24 A / 2 AA / 0 AAA`, Combined `25 A / 2 AA / 0 AAA` | Node A still surfaces `1.4.4` and `2.4.6` through always-on best-practice fallback mappings. |
| AA | 41 | 47 | Node `24 A / 17 AA / 0 AAA`, Combined `25 A / 22 AA / 0 AAA` | AA behaves as expected; no AAA criteria are emitted in the combined output. |
| AAA | 45 | 52 | Node `24 A / 17 AA / 4 AAA`, Combined `25 A / 22 AA / 5 AAA` | AAA adds `1.4.6`, `2.2.4`, `2.4.8`, `2.4.9`, and `2.4.12` to the combined footprint. |

## High-Value Backdrops Identified During Recheck

| Backdrop | Impact | Recommendation |
| --- | --- | --- |
| Python metadata is broader than Python emitters | Earlier coverage summaries can overstate Python implementation depth | Treat `combined/findings.py` plus `combined/stages.py` as the source of truth for emitted Python coverage |
| Node level gating includes `best-practice` at every level | Lower-level scans can still surface fallback-mapped higher-level semantics or cross-level proxies | Keep this behaviour documented, or filter fallback-mapped findings after mapping if strict conformance-level purity is required |
| Some Node AAA coverage is narrow in scope | `2.2.4` is currently represented by `meta-refresh-no-exceptions`, which is only one interruption pattern | Keep the rule counted, but label it `Low` confidence and do not oversell it as full AAA interruption coverage |
| Fallback-only SCs exist in Node | `2.4.3` and `2.4.6` rely on best-practice mapping, not direct numeric WCAG tags | These are useful, but should be treated as proxy coverage in product messaging |

## Missing Rules Summary

| Level | Missing count | Missing criteria |
| --- | ---: | --- |
| A | 6 | `1.2.3` Audio Description or Media Alternative (Prerecorded), `1.3.3` Sensory Characteristics, `2.3.1` Three Flashes or Below Threshold, `2.5.1` Pointer Gestures, `2.5.4` Motion Actuation, `3.3.7` Redundant Entry |
| AA | 4 | `1.2.4` Captions (Live), `1.2.5` Audio Description (Prerecorded), `3.2.3` Consistent Navigation, `3.2.4` Consistent Identification |
| AAA | 25 | `1.2.6` Sign Language (Prerecorded), `1.2.7` Extended Audio Description (Prerecorded), `1.2.8` Media Alternative (Prerecorded), `1.2.9` Audio-only (Live), `1.3.6` Identify Purpose, `1.4.7` Low or No Background Audio, `1.4.8` Visual Presentation, `1.4.9` Images of Text (No Exception), `2.1.3` Keyboard (No Exception), `2.2.3` No Timing, `2.2.5` Re-authenticating, `2.2.6` Timeouts, `2.3.2` Three Flashes, `2.3.3` Animation from Interactions, `2.4.10` Section Headings, `2.5.5` Target Size, `2.5.6` Concurrent Input Mechanisms, `3.1.3` Unusual Words, `3.1.4` Abbreviations, `3.1.5` Reading Level, `3.1.6` Pronunciation, `3.2.5` Change on Request, `3.3.5` Help, `3.3.6` Error Prevention (All), `3.3.9` Accessible Authentication (Enhanced) |

## Coverage Growth Opportunities

| Technique family | Missing SC unlocked | Why this is efficient |
| --- | ---: | --- |
| `NEXT-MEDIA` | 10 | One media analysis pipeline can cover prerecorded alternatives, live captions, flash checks, and background-audio rules. |
| `NEXT-NLP` | 6 | Language, sensory-instruction, and readability checks cluster naturally around text parsing. |
| `NEXT-FLOW` | 4 | Stateful workflow replay would unlock redundant-entry, help, error-prevention, and enhanced authentication checks. |
| `NEXT-MOTION` | 3 | Gesture, motion, and interaction-animation gaps are all runtime instrumentation problems. |
| `NEXT-TIME` | 3 | Timeout and interruption handling can be addressed by a dedicated session-state monitor. |
| `NEXT-INTERACT` | 3 | Keyboard-no-exception, concurrent input, and change-on-request all need deeper interaction simulation. |
| `NEXT-CROSS` | 2 | Cross-page diffing covers navigation and identification consistency efficiently. |
| `NEXT-LAYOUT` | 2 | Outline and presentation heuristics can add section headings and visual-presentation coverage. |
| `P-OCR` upgrade | 1 | Tightening the current OCR exception model would likely unlock `1.4.9`. |
| `P-CRAWL` target-size upgrade | 1 | The existing target-size crawler can be extended from AA (`24x24`) to AAA (`44x44`). |

## Complete Rule Inventory

| SC | Criterion | Level | Node | Python | Combined | Confidence | Coverage notes | Plain-English explanation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.1.1 | Non-text Content | A | Yes | Yes | Covered | High | N-AXE + fallback best-practice rules; P-OCR/image audit | Images, icons, and charts need text alternatives. |
| 1.2.1 | Audio-only and Video-only (Prerecorded) | A | Yes | No | Covered | Medium | N-AXE + N-CUSTOM | Pre-recorded audio-only or video-only media needs an equivalent alternative. |
| 1.2.2 | Captions (Prerecorded) | A | Yes | No | Covered | High | N-AXE | Pre-recorded video with sound needs captions. |
| 1.2.3 | Audio Description or Media Alternative (Prerecorded) | A | No | No | Missing | Not covered | NEXT-MEDIA | Pre-recorded video needs audio description or a full text alternative. |
| 1.2.4 | Captions (Live) | AA | No | No | Missing | Not covered | NEXT-MEDIA | Live audio or video needs captions. |
| 1.2.5 | Audio Description (Prerecorded) | AA | No | No | Missing | Not covered | NEXT-MEDIA | Recorded video needs audio description for important visuals. |
| 1.2.6 | Sign Language (Prerecorded) | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Recorded video should provide sign language for spoken content. |
| 1.2.7 | Extended Audio Description (Prerecorded) | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Recorded video should offer extended audio description when needed. |
| 1.2.8 | Media Alternative (Prerecorded) | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Recorded media should have a full text alternative. |
| 1.2.9 | Audio-only (Live) | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Live audio-only content should have a text alternative. |
| 1.3.1 | Info and Relationships | A | Yes | No | Covered | High | N-AXE + fallback best-practice rules | Headings, labels, and tables must be coded so assistive tech can understand them. |
| 1.3.2 | Meaningful Sequence | A | Yes | No | Covered | Medium | N-CUSTOM | Reading order must still make sense when the page is read linearly. |
| 1.3.3 | Sensory Characteristics | A | No | No | Missing | Not covered | NEXT-NLP | Instructions must not depend only on shape, size, color, or position. |
| 1.3.4 | Orientation | AA | Yes | Yes | Covered | High | N-AXE; P-RENDER orientation evaluator | Content should work in portrait and landscape unless essential. |
| 1.3.5 | Identify Input Purpose | AA | Yes | No | Covered | High | N-AXE | Common personal-data fields should expose machine-readable purpose. |
| 1.3.6 | Identify Purpose | AAA | No | No | Missing | Not covered | NEXT-NLP | More UI elements should expose programmatic purpose. |
| 1.4.1 | Use of Color | A | Yes | No | Covered | Medium | N-AXE + N-CUSTOM | Color alone must not carry the message. |
| 1.4.2 | Audio Control | A | Yes | No | Covered | Medium | N-AXE | Auto-playing sound must be stoppable or controllable. |
| 1.4.3 | Contrast (Minimum) | AA | Yes | Yes | Covered | High | N-AXE; P-OCR contrast extraction | Text contrast must reach the minimum readability ratio. |
| 1.4.4 | Resize Text | AA | Yes | Yes | Covered | High | N-AXE + fallback best-practice rules; P-RENDER resize-text evaluator | Text should stay usable when enlarged to 200 percent. |
| 1.4.5 | Images of Text | AA | No | Yes | Covered | Medium | P-OCR images-of-text audit | Use real text instead of text baked into images where possible. |
| 1.4.6 | Contrast (Enhanced) | AAA | Yes | No | Covered | High | N-AXE | Text needs higher-than-AA contrast. |
| 1.4.7 | Low or No Background Audio | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Background audio should be absent or very low behind speech. |
| 1.4.8 | Visual Presentation | AAA | No | No | Missing | Not covered | NEXT-LAYOUT | Users should have strong control over text presentation. |
| 1.4.9 | Images of Text (No Exception) | AAA | No | No | Missing | Not covered | P-OCR upgrade | Avoid images of text except where truly essential. |
| 1.4.10 | Reflow | AA | No | Yes | Covered | High | P-RENDER reflow evaluator | Content should work without two-dimensional scrolling at small viewport or zoom. |
| 1.4.11 | Non-text Contrast | AA | No | Yes | Covered | Low | P-OCR non-text contrast proxy | UI parts and graphics need enough contrast against surrounding colors. |
| 1.4.12 | Text Spacing | AA | Yes | Yes | Covered | High | N-AXE; P-RENDER + static spacing audit | Pages should remain usable when line, letter, and word spacing increase. |
| 1.4.13 | Content on Hover or Focus | AA | No | Yes | Covered | High | P-RENDER hover/focus evaluator | Hover or focus popups must be dismissible and stable. |
| 2.1.1 | Keyboard | A | Yes | No | Covered | High | N-AXE + fallback best-practice rules | All functionality must work with a keyboard. |
| 2.1.2 | No Keyboard Trap | A | Yes | No | Covered | Medium | N-CUSTOM | Keyboard users must be able to move focus away. |
| 2.1.3 | Keyboard (No Exception) | AAA | No | No | Missing | Not covered | NEXT-INTERACT | Everything must work by keyboard with no exceptions. |
| 2.1.4 | Character Key Shortcuts | A | Yes | No | Covered | Medium | N-CUSTOM | Single-key shortcuts need disable, remap, or focus-only behaviour. |
| 2.2.1 | Timing Adjustable | A | Yes | No | Covered | Low | N-AXE | Users need enough time or a way to extend it. |
| 2.2.2 | Pause, Stop, Hide | A | Yes | Yes | Covered | High | N-AXE; timing auditor | Moving or auto-updating content must be pausable or stoppable. |
| 2.2.3 | No Timing | AAA | No | No | Missing | Not covered | NEXT-TIME | Tasks should not depend on time limits. |
| 2.2.4 | Interruptions | AAA | Yes | No | Covered | Low | N-AXE (meta-refresh-no-exceptions); narrow proxy for interruption behaviour | Users should be able to delay or avoid interruptions where possible. |
| 2.2.5 | Re-authenticating | AAA | No | No | Missing | Not covered | NEXT-TIME | Re-authentication should not cause data loss. |
| 2.2.6 | Timeouts | AAA | No | No | Missing | Not covered | NEXT-TIME | Users should be warned about data-loss timeouts. |
| 2.3.1 | Three Flashes or Below Threshold | A | No | No | Missing | Not covered | NEXT-MEDIA | Content must not flash in a seizure-risk pattern. |
| 2.3.2 | Three Flashes | AAA | No | No | Missing | Not covered | NEXT-MEDIA | Content should avoid any unsafe flashing. |
| 2.3.3 | Animation from Interactions | AAA | No | No | Missing | Not covered | NEXT-MOTION | Motion triggered by interaction should be disableable. |
| 2.4.1 | Bypass Blocks | A | Yes | No | Covered | High | N-AXE + fallback best-practice rules | Users need a way to skip repeated blocks. |
| 2.4.2 | Page Titled | A | Yes | No | Covered | High | N-AXE | Each page needs a clear title. |
| 2.4.3 | Focus Order | A | Yes | No | Covered | Low | fallback best-practice rules only | Keyboard focus should move in a sensible order. |
| 2.4.4 | Link Purpose (In Context) | A | Yes | No | Covered | High | N-AXE | Link purpose should be clear from its text or nearby context. |
| 2.4.5 | Multiple Ways | AA | Yes | No | Covered | Medium | N-CUSTOM | More than one way should exist to find a page. |
| 2.4.6 | Headings and Labels | AA | Yes | No | Covered | Medium | fallback best-practice rules only | Headings and labels should describe their purpose clearly. |
| 2.4.7 | Focus Visible | AA | Yes | No | Covered | Medium | N-CUSTOM | The keyboard focus indicator must be visible. |
| 2.4.8 | Location | AAA | Yes | No | Covered | Medium | N-CUSTOM | Users should know where they are within the site structure. |
| 2.4.9 | Link Purpose (Link Only) | AAA | Yes | No | Covered | Medium | N-CUSTOM + N-AXE | Link text alone should make the purpose clear. |
| 2.4.10 | Section Headings | AAA | No | No | Missing | Not covered | NEXT-LAYOUT | Sections should use helpful headings. |
| 2.4.11 | Focus Not Obscured (Minimum) | AA | No | Yes | Covered | High | P-RENDER focus-not-obscured minimum | Focused items should not be fully hidden behind overlays. |
| 2.4.12 | Focus Not Obscured (Enhanced) | AAA | No | Yes | Covered | High | P-RENDER focus-not-obscured enhanced | Focused items should not be obscured at all. |
| 2.4.13 | Focus Appearance | AA | Yes | No | Covered | Medium | N-CUSTOM | Focus indicator size and contrast must be strong enough. |
| 2.5.1 | Pointer Gestures | A | No | No | Missing | Not covered | NEXT-MOTION | Complex gestures need a simple pointer alternative. |
| 2.5.2 | Pointer Cancellation | A | Yes | No | Covered | Low | N-CUSTOM | Pointer actions should not trigger unexpectedly on the down event. |
| 2.5.3 | Label in Name | A | Yes | Yes | Covered | High | N-AXE; label-in-name auditor | Visible label text should also exist in the accessible name. |
| 2.5.4 | Motion Actuation | A | No | No | Missing | Not covered | NEXT-MOTION | Motion-based actions need an alternative and an off switch. |
| 2.5.5 | Target Size | AAA | No | No | Missing | Not covered | P-CRAWL upgrade | Targets should use the larger AAA minimum size. |
| 2.5.6 | Concurrent Input Mechanisms | AAA | No | No | Missing | Not covered | NEXT-INTERACT | Different input methods should remain available together. |
| 2.5.7 | Dragging Movements | AA | Yes | No | Covered | Medium | N-CUSTOM | Drag operations need a simpler non-drag alternative. |
| 2.5.8 | Target Size (Minimum) | AA | Yes | Yes | Covered | High | N-AXE; target-size crawler/auditor | Tap and click targets need minimum size or safe spacing. |
| 3.1.1 | Language of Page | A | Yes | No | Covered | High | N-AXE | The main page language must be declared. |
| 3.1.2 | Language of Parts | AA | Yes | No | Covered | High | N-AXE | Passages in another language should be marked with that language. |
| 3.1.3 | Unusual Words | AAA | No | No | Missing | Not covered | NEXT-NLP | Uncommon words should be explained. |
| 3.1.4 | Abbreviations | AAA | No | No | Missing | Not covered | NEXT-NLP | Abbreviations should be explained. |
| 3.1.5 | Reading Level | AAA | No | No | Missing | Not covered | NEXT-NLP | Content should be readable at lower reading complexity or have support. |
| 3.1.6 | Pronunciation | AAA | No | No | Missing | Not covered | NEXT-NLP | When pronunciation affects meaning, it should be provided. |
| 3.2.1 | On Focus | A | Yes | No | Covered | Medium | N-CUSTOM | Focusing an element should not unexpectedly change context. |
| 3.2.2 | On Input | A | Yes | No | Covered | Medium | N-CUSTOM | Changing a field should not unexpectedly submit or navigate. |
| 3.2.3 | Consistent Navigation | AA | No | No | Missing | Not covered | NEXT-CROSS | Repeated navigation should stay in a consistent order. |
| 3.2.4 | Consistent Identification | AA | No | No | Missing | Not covered | NEXT-CROSS | The same component should be identified consistently across pages. |
| 3.2.5 | Change on Request | AAA | No | No | Missing | Not covered | NEXT-INTERACT | Context changes should happen only when requested. |
| 3.2.6 | Consistent Help | AA | Yes | No | Covered | Medium | N-CUSTOM | Repeated help mechanisms should appear consistently. |
| 3.3.1 | Error Identification | A | No | Yes | Covered | High | form auditor | Input errors must be identified clearly. |
| 3.3.2 | Labels or Instructions | A | Yes | Yes | Covered | High | N-AXE; form auditor | Controls need labels or instructions before use. |
| 3.3.3 | Error Suggestion | AA | Yes | No | Covered | Medium | N-CUSTOM | When possible, tell users how to fix an error. |
| 3.3.4 | Error Prevention (Legal, Financial, Data) | AA | Yes | No | Covered | Medium | N-CUSTOM | Important submissions need review, confirmation, or reversal. |
| 3.3.5 | Help | AAA | No | No | Missing | Not covered | NEXT-FLOW | Context-sensitive help should be available for complex tasks. |
| 3.3.6 | Error Prevention (All) | AAA | No | No | Missing | Not covered | NEXT-FLOW | More workflows should prevent irreversible mistakes. |
| 3.3.7 | Redundant Entry | A | No | No | Missing | Not covered | NEXT-FLOW | Users should not have to re-enter the same data in one process. |
| 3.3.8 | Accessible Authentication (Minimum) | AA | Yes | No | Covered | Medium | N-CUSTOM | Login should not depend only on hard memory or cognitive tests. |
| 3.3.9 | Accessible Authentication (Enhanced) | AAA | No | No | Missing | Not covered | NEXT-FLOW | Authentication should avoid cognitive barriers more strongly. |
| 4.1.1 | Parsing | A | Yes | No | Covered | Medium | N-CUSTOM | Markup should not break because of duplicate IDs or invalid structure. |
| 4.1.2 | Name, Role, Value | A | Yes | No | Covered | High | N-AXE + fallback best-practice rules | Custom controls need correct name, role, state, and value. |
| 4.1.3 | Status Messages | AA | Yes | No | Covered | Medium | N-CUSTOM | Important status updates must reach assistive tech without stealing focus. |
