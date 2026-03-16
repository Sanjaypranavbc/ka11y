| #   | WCAG 2.1 Criteria NOT Covered by axe-core |                                        |       |                |                                                                |
|-----|-------------------------------------------|----------------------------------------|-------|----------------|----------------------------------------------------------------|
| 1   | WCAG Criterion                            | Criterion Name                         | Level | Principle      | Why axe-core Cannot Cover It                                   |
| 2   |   Perceivable                             |                                        |       |                |                                                                |
| 3   | 1.2.3                                     | Audio Description or Media Alternative | A     | Perceivable    | Requires human judgment to verify adequacy of descriptions     |
| 4   | 1.2.4                                     | Captions (Live)                        | AA    | Perceivable    | Live captioning cannot be auto-detected or validated by tools  |
| 5   | 1.2.5                                     | Audio Description (Prerecorded)        | AA    | Perceivable    | Requires human review of video content accuracy                |
| 6   | 1.3.2                                     | Meaningful Sequence                    | A     | Perceivable    | Reading order logic requires human contextual understanding    |
| 7   | 1.3.3                                     | Sensory Characteristics                | A     | Perceivable    | Requires human review of content instructions                  |
| 8   | 1.4.3                                     | Contrast (Minimum)                     | AA    | Perceivable    | Partial — axe-core misses dynamic/overlay text contrast        |
| 9   | 1.4.4                                     | Resize Text                            | AA    | Perceivable    | Requires manual browser zoom testing                           |
| 10  | 1.4.5                                     | Images of Text                         | AA    | Perceivable    | Requires human judgment on image content                       |
| 11  | 1.4.10                                    | Reflow                                 | AA    | Perceivable    | Requires testing at 320px viewport manually                    |
| 12  | 1.4.11                                    | Non-text Contrast                      | AA    | Perceivable    | Partial — UI component contrast often requires manual check    |
| 13  | 1.4.13                                    | Content on Hover or Focus              | AA    | Perceivable    | Hover/focus interaction requires manual testing                |
| 14  |   Operable                                |                                        |       |                |                                                                |
| 15  | 2.1.2                                     | No Keyboard Trap                       | A     | Operable       | Requires interactive keyboard testing by a human               |
| 16  | 2.1.4                                     | Character Key Shortcuts                | A     | Operable       | Requires review of implemented keyboard shortcuts              |
| 17  | 2.3.1                                     | Three Flashes or Below Threshold       | A     | Operable       | Requires specialized flicker analysis tools                    |
| 18  | 2.4.3                                     | Focus Order                            | A     | Operable       | Logical focus order requires human interaction testing         |
| 19  | 2.4.5                                     | Multiple Ways                          | AA    | Operable       | Requires evaluating site navigation options holistically       |
| 20  | 2.4.6                                     | Headings and Labels                    | AA    | Operable       | Requires human review of heading/label descriptiveness         |
| 21  | 2.4.7                                     | Focus Visible                          | AA    | Operable       | Partial — custom focus styles need manual verification         |
| 22  | 2.5.1                                     | Pointer Gestures                       | A     | Operable       | Requires testing touch/pointer interactions manually           |
| 23  | 2.5.2                                     | Pointer Cancellation                   | A     | Operable       | Requires manual interaction testing                            |
| 24  | 2.5.3                                     | Label in Name                          | A     | Operable       | Requires comparing visual label to accessible name manually    |
| 25  | 2.5.4                                     | Motion Actuation                       | A     | Operable       | Requires device motion/physical interaction testing            |
| 26  |   Understandable                          |                                        |       |                |                                                                |
| 27  | 3.1.2                                     | Language of Parts                      | AA    | Understandable | Requires human review of multilingual content segments         |
| 28  | 3.2.1                                     | On Focus                               | A     | Understandable | Requires manual interaction to observe focus-triggered changes |
| 29  | 3.2.2                                     | On Input                               | A     | Understandable | Requires manual form interaction testing                       |
| 30  | 3.2.3                                     | Consistent Navigation                  | AA    | Understandable | Requires cross-page human review                               |
| 31  | 3.2.4                                     | Consistent Identification              | AA    | Understandable | Requires cross-page comparison by a human                      |
| 32  | 3.3.1                                     | Error Identification                   | A     | Understandable | Requires triggering form errors and reviewing messages         |
| 33  | 3.3.3                                     | Error Suggestion                       | AA    | Understandable | Requires human judgment on error message quality               |
| 34  | 3.3.4                                     | Error Prevention                       | AA    | Understandable | Requires human review of form submission safeguards            |
| 35  |   Robust                                  |                                        |       |                |                                                                |
| 36  | 4.1.1                                     | Parsing                                | A     | Robust         | Partial — some parsing issues not caught by axe-core           |
| 37  | 4.1.3                                     | Status Messages                        | AA    | Robust         | Requires reviewing dynamic status messages with screen readers |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
