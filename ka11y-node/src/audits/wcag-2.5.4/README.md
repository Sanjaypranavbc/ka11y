# WCAG 2.5.4 Motion Actuation — Audit Module

## Automation Limitations

Unlike 2.5.1 (Pointer Gestures), SC 2.5.4 **cannot be fully automated** because:

1. Playwright runs in a desktop browser context — it cannot simulate device shake,
   tilt, or gyroscope input. Physical device testing is required.

2. Motion event listeners are often registered dynamically. Static JS scanning
   catches most cases but will miss listeners added inside async callbacks or
   lazy-loaded modules.

3. The "disable control" requirement is UX-contextual — a settings page at a
   different URL may provide the disable option, which a per-page crawl won't see.

## What This Module Does

- **Detects** motion API usage via 3 layers (runtime handlers, inline JS, external scripts)
- **Classifies** whether the motion is likely essential (and therefore exempt)
- **Checks** for disable controls on the current page
- **Flags** with confidence levels for manual follow-up
- **Generates** a manual verification checklist for human auditors

## Confidence Levels

| Level | Meaning |
|---|---|
| high | `ondevicemotion` / `ondeviceorientation` handler found at runtime |
| medium | Pattern match in inline script source code |
| low | External script URL contains motion-related keyword only |

## Result Interpretation

All results are `manualReviewRequired: true`. Use the generated checklist
to test on a real iOS/Android device before reporting as a violation.