# WCAG 2.5.4 Motion Actuation — Audit Module

## Automation Limitations

Unlike 2.5.1 (Pointer Gestures), SC 2.5.4 **cannot be fully automated** because:

1. Playwright runs in a desktop browser context — it cannot simulate device shake,
   tilt, or gyroscope input. Physical device testing is required.

2. Motion event listeners may be registered after our `addInitScript` patch
   detaches (e.g. listeners added inside isolated worker realms or via
   re-initialised iframes). The runtime + monkey-patch pair catches the
   common cases but cannot guarantee 100% capture.

3. The "disable control" requirement is UX-contextual — a settings page at a
   different URL may provide the disable option, which a per-page crawl won't see.

## What This Module Does

- **Detects** motion API usage via 5 layers:
  1. Runtime property scan (`window.ondevicemotion` / `ondeviceorientation`)
  2. `addEventListener` monkey-patch injected before any page script runs
     (catches React/Vue/Angular sensor listeners that never set `window.on*`)
  3. Inline script keyword scan
  4. External script body fetch + keyword scan
  5. Library fingerprinting (`shake.js`, `gyroscape`, `hammer.js` motion mode,
     iOS 13+ `DeviceMotionEvent.requestPermission`)
- **Classifies** whether the motion is likely essential — gated on an explicit
  `data-wcag-motion-essential="true"` opt-in; soft signals (fitness, VR, WebGL,
  `Schema.org` `VideoGame`) are reported but never auto-exempt
- **Checks** for disable controls on the current page (motion-adjacent
  toggles/checkboxes/switches; "Accessibility" landmarks must also mention a
  motion keyword in the same subtree before counting as evidence)
- **Verifies UI alternatives** by requiring an action-verb-labelled control
  (Undo / Refresh / Reset / 元に戻す …) whose ancestor container *also*
  mentions a motion keyword
- **Runs a custom axe-core rule** with `evaluate→true=pass` semantics
- **Generates** a manual verification checklist for human auditors

## Confidence Levels

| Level | Meaning |
|---|---|
| high | `ondevicemotion`/`ondeviceorientation` property handler **or** `addEventListener('devicemotion', …)` registration captured at runtime |
| medium | Pattern match in inline script source or fetched external script body |
| low | External script URL contains motion-related keyword only |
| none | No motion API usage found anywhere |

## Result Interpretation

All results are `manualReviewRequired: true`. Use the generated checklist
to test on a real iOS/Android device before reporting as a violation.