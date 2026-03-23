"""
ka11y/api/v1/combined/constants.py
====================================
Static WCAG metadata: names, levels, suggested fixes, and Python severity map.
"""

from __future__ import annotations

from typing import Dict

_WCAG_NAMES: Dict[str, str] = {
    "1.1.1": "Non-text Content",
    "1.2.1": "Audio-only and Video-only (Prerecorded)",
    "1.2.2": "Captions (Prerecorded)",
    "1.2.3": "Audio Description or Media Alternative (Prerecorded)",
    "1.3.1": "Info and Relationships",
    "1.3.2": "Meaningful Sequence",
    "1.3.3": "Sensory Characteristics",
    "1.3.4": "Orientation",
    "1.3.5": "Identify Input Purpose",
    "1.4.1": "Use of Color",
    "1.4.2": "Audio Control",
    "1.4.3": "Contrast (Minimum)",
    "1.4.4": "Resize Text",
    "1.4.5": "Images of Text",
    "1.4.10": "Reflow",
    "1.4.11": "Non-text Contrast",
    "1.4.12": "Text Spacing",
    "1.4.13": "Content on Hover or Focus",
    "2.1.1": "Keyboard",
    "2.1.2": "No Keyboard Trap",
    "2.1.4": "Character Key Shortcuts",
    "2.2.1": "Timing Adjustable",
    "2.2.2": "Pause, Stop, Hide",
    "2.3.1": "Three Flashes or Below Threshold",
    "2.4.1": "Bypass Blocks",
    "2.4.2": "Page Titled",
    "2.4.3": "Focus Order",
    "2.4.4": "Link Purpose (In Context)",
    "2.4.5": "Multiple Ways",
    "2.4.6": "Headings and Labels",
    "2.4.7": "Focus Visible",
    "2.4.11": "Focus Not Obscured (Minimum)",
    "2.4.12": "Focus Not Obscured (Enhanced)",
    "2.4.13": "Focus Appearance",
    "2.5.1": "Pointer Gestures",
    "2.5.2": "Pointer Cancellation",
    "2.5.3": "Label in Name",
    "2.5.4": "Motion Actuation",
    "2.5.7": "Dragging Movements",
    "2.5.8": "Target Size (Minimum)",
    "3.1.1": "Language of Page",
    "3.1.2": "Language of Parts",
    "3.2.1": "On Focus",
    "3.2.2": "On Input",
    "3.2.3": "Consistent Navigation",
    "3.2.4": "Consistent Identification",
    "3.2.6": "Consistent Help",
    "3.3.1": "Error Identification",
    "3.3.2": "Labels or Instructions",
    "3.3.3": "Error Suggestion",
    "3.3.4": "Error Prevention (Legal, Financial, Data)",
    "3.3.7": "Redundant Entry",
    "3.3.8": "Accessible Authentication (Minimum)",
    "4.1.1": "Parsing",
    "4.1.2": "Name, Role, Value",
    "4.1.3": "Status Messages",
}

_WCAG_LEVEL: Dict[str, str] = {
    # Level A
    "1.1.1": "A", "1.2.1": "A", "1.2.2": "A", "1.2.3": "A",
    "1.3.1": "A", "1.3.2": "A", "1.3.3": "A",
    "1.4.1": "A", "1.4.2": "A",
    "2.1.1": "A", "2.1.2": "A", "2.1.4": "A",
    "2.2.1": "A", "2.2.2": "A",
    "2.3.1": "A",
    "2.4.1": "A", "2.4.2": "A", "2.4.3": "A", "2.4.4": "A",
    "2.5.1": "A", "2.5.2": "A", "2.5.3": "A", "2.5.4": "A",
    "3.1.1": "A",
    "3.2.1": "A", "3.2.2": "A",
    "3.3.1": "A", "3.3.2": "A", "3.3.7": "A",
    "4.1.1": "A", "4.1.2": "A",
    # Level AA
    "1.2.4": "AA", "1.2.5": "AA",
    "1.3.4": "AA", "1.3.5": "AA",
    "1.4.3": "AA", "1.4.4": "AA", "1.4.5": "AA",
    "1.4.10": "AA", "1.4.11": "AA", "1.4.12": "AA", "1.4.13": "AA",
    "2.4.5": "AA", "2.4.6": "AA", "2.4.7": "AA",
    "2.4.11": "AA", "2.4.12": "AA", "2.4.13": "AA",
    "2.5.7": "AA", "2.5.8": "AA",
    "3.1.2": "AA",
    "3.2.3": "AA", "3.2.4": "AA", "3.2.6": "AA",
    "3.3.3": "AA", "3.3.4": "AA", "3.3.8": "AA",
    "4.1.3": "AA",
}

_SUGGESTED_FIX: Dict[str, str] = {
    "1.1.1": "Add a descriptive alt attribute: <img alt='Description'>. For decorative images use alt=''.",
    "1.3.1": "Use semantic HTML (headings, lists, tables). Add appropriate ARIA landmark roles where needed.",
    "1.3.4": (
        "Do not use CSS that locks orientation (e.g. @media (orientation: landscape) { display: none }). "
        "Remove rotate-device overlays unless the feature is genuinely essential in one orientation."
    ),
    "1.3.5": "Add autocomplete attributes to inputs: <input autocomplete='email'>.",
    "1.4.1": "Do not use colour as the only means to convey information. Add text labels or patterns.",
    "1.4.2": "Provide a mechanism to pause or stop auto-playing audio, or ensure it stops within 3 seconds.",
    "1.4.3": "Ensure text has a contrast ratio of at least 4.5:1 (3:1 for large text ≥ 18pt or bold 14pt).",
    "1.4.4": (
        "Remove CSS that prevents text scaling (e.g. fixed px heights on text containers, "
        "overflow: hidden on parent elements). Ensure content reflows correctly at 200% text size."
    ),
    "1.4.10": (
        "Use responsive CSS layouts (Flexbox/Grid, relative units). Avoid fixed-width containers "
        "that overflow at 320 CSS px. Content must not require horizontal scrolling to read."
    ),
    "1.4.11": "Ensure UI components have at least 3:1 contrast ratio against adjacent colours.",
    "1.4.12": (
        "Do not override line-height, letter-spacing, or word-spacing with !important or "
        "fixed values. Use relative units (em/rem) and avoid fixed-height containers for text."
    ),
    "1.4.13": (
        "Ensure hover/focus-triggered content: (1) can be dismissed via Escape, "
        "(2) does not vanish when the pointer moves toward it, "
        "(3) stays visible until focus/hover is intentionally removed."
    ),
    "2.1.1": "Ensure all functionality is operable via keyboard. Avoid onclick-only handlers and positive tabindex.",
    "2.1.2": "Allow keyboard users to move focus away from any component without requiring unusual key sequences.",
    "2.2.2": "Add a visible Pause/Stop button for any auto-playing content lasting more than 5 seconds.",
    "2.4.1": "Add a skip link as the first focusable element: <a href='#main'>Skip to main content</a>.",
    "2.4.2": "Add a descriptive <title>: <title>Page Name — Site Name</title>.",
    "2.4.3": "Ensure focus order follows a logical reading order. Remove positive tabindex values.",
    "2.4.4": "Replace generic link text ('Click here', 'Read more') with descriptive destination text.",
    "2.4.6": "Use heading levels (h1–h6) hierarchically. Provide visible labels for form groups.",
    "2.4.7": "Ensure all focusable elements have a clearly visible focus indicator (outline or border).",
    "2.4.11": (
        "Ensure sticky/fixed headers, footers, and banners do not completely cover focused elements. "
        "Add scroll-padding-top equal to the sticky header height, or use scroll-margin-top on "
        "focusable elements. Test keyboard navigation with all overlays visible."
    ),
    "2.4.12": (
        "Ensure no author-created content (sticky bars, cookie banners, chat widgets) overlaps "
        "the focused element at all. Use scroll-padding / scroll-margin so the focused element "
        "is fully visible clear of all fixed overlays."
    ),
    "2.5.3": "Ensure the accessible name (aria-label) contains the visible label text verbatim.",
    "2.5.8": "Increase the target to at least 24×24 CSS px, or add padding to reach that size.",
    "3.1.1": "Add a lang attribute to <html>: <html lang='en'>.",
    "3.1.2": "Add lang to inline content in another language: <span lang='fr'>Bonjour</span>.",
    "3.2.3": "Keep navigation menus in the same order across all pages.",
    "3.3.1": "Associate error messages with inputs using aria-describedby or aria-errormessage.",
    "3.3.2": "Add a visible <label> or aria-label to every form input. Do not rely on placeholder text alone.",
    "4.1.1": "Remove duplicate id attributes — each id must be unique within a page.",
    "4.1.2": "Give every interactive element an accessible name, role, and value using native HTML or ARIA.",
    "4.1.3": "Wrap status messages in a live region: <div role='status' aria-live='polite'>...</div>.",
}

_PYTHON_SEVERITY: Dict[str, str] = {
    "1.1.1": "critical",
    "1.3.4": "medium",
    "1.4.3": "high",
    "1.4.4": "high",
    "1.4.10": "high",
    "1.4.12": "high",
    "1.4.13": "medium",
    "2.2.2": "high",
    "2.4.11": "high",
    "2.4.12": "high",
    "2.5.3": "high",
    "2.5.8": "medium",
    "3.3.1": "high",
    "3.3.2": "high",
}