"""
ka11y/accessibility/audit.py
============================
Unified WCAG Accessibility Auditor.

Merges output from all three pipeline stages:
  1. Crawler  (ImageData list  — classification, alt text, flags)
  2. Classifier (already embedded in ImageData via ClassifyAssets)
  3. Text Detector (TextDetectionResult list — OCR text, contrast violations)

Produces a single audit_report.csv in output_dir covering EVERY crawled image,
including decorative images and images with missing alt text.

WCAG criteria checked
---------------------
  WCAG 1.1.1  Non-text Content  — all images (informative, functional, decorative)
  WCAG 4.1.2  Name, Role, Value — functional images only (logo / icon / button)

Usage (explicit call from route or CLI)
---------------------------------------
    from ka11y.accessibility.audit import AccessibilityAuditor

    auditor = AccessibilityAuditor()
    report_df = auditor.generate_audit_report(
        images_data=crawler.images_data,      # List[ImageData]
        ocr_results=detector.results,         # List[TextDetectionResult]
        output_dir=crawler.output_dir,        # str path
    )
"""

from __future__ import annotations

import re
import csv
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="audit")


# ---------------------------------------------------------------------------
# WCAG constants
# ---------------------------------------------------------------------------

_EMPTY_OR_GENERIC: set[str] = {
    "",
    "image",
    "img",
    "photo",
    "picture",
    "graphic",
    "figure",
    "icon",
    "untitled",
    "placeholder",
    "null",
    "none",
    "n/a",
    "na",
    "image of",
    "photo of",
    "picture of",
    "graphic of",
    "spacer",
    "decoration",
    "decorative",
}

# Social/brand icon names — must be paired with "icon" to be acceptable
_SOCIAL_BRAND_NAMES: set[str] = {
    "facebook",
    "twitter",
    "x",
    "instagram",
    "youtube",
    "linkedin",
    "tiktok",
    "pinterest",
    "snapchat",
    "whatsapp",
    "telegram",
    "line",
    "wechat",
    "note",
    "github",
    "gitlab",
    "reddit",
    "threads",
}

# Acceptable action/purpose words for buttons
_BUTTON_ACTION_WORDS: set[str] = {
    "menu",
    "close",
    "open",
    "search",
    "back",
    "forward",
    "next",
    "prev",
    "previous",
    "submit",
    "send",
    "cancel",
    "confirm",
    "ok",
    "yes",
    "no",
    "save",
    "delete",
    "edit",
    "add",
    "remove",
    "upload",
    "download",
    "share",
    "print",
    "copy",
    "paste",
    "cut",
    "undo",
    "redo",
    "refresh",
    "reload",
    "home",
    "settings",
    "help",
    "info",
    "more",
    "less",
    "expand",
    "collapse",
    "toggle",
    "play",
    "pause",
    "stop",
    "mute",
    "unmute",
    "fullscreen",
    "exit fullscreen",
    "zoom in",
    "zoom out",
    "like",
    "dislike",
    "comment",
    "reply",
    "follow",
    "unfollow",
    "subscribe",
    "unsubscribe",
    "login",
    "logout",
    "sign in",
    "sign out",
    "sign up",
    "register",
    "checkout",
    "cart",
    "bag",
    "wishlist",
    "filter",
    "sort",
    "view",
    "hide",
    "show",
    "skip",
    "navigate",
    "go to",
    "load more",
    "read more",
    "see more",
    "see all",
    "cookies settings",
    "accept all cookies",
    "reject all",
    "accept cookies",
    "decline cookies",
    "manage cookies",
    "cookie preferences",
    "previous slide",
    "next slide",
    "go to slide",
    "new window",
    "opens in new tab",
}

# Report CSV columns (order preserved)
_REPORT_COLUMNS = [
    "filename",
    "src",
    "url",
    "classification",
    "sub_type",
    "is_logo",
    "is_icon",
    "is_button",
    "is_functional",
    "is_decorative",
    "alt_text",
    "title",
    "has_ocr_text",
    "detected_text",
    "contrast_violations_count",
    "wcag_1_1_1_status",
    "wcag_4_1_2_status",
    "wcag_1_4_5_status",
    "wcag_1_4_11_status",
    "overall_status",
    "wcag_1_1_1_reason",
    "wcag_4_1_2_reason",
    "wcag_1_4_5_reason",
    "wcag_1_4_11_reason",
    "screenshot_path",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = str(text).lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _is_empty(value) -> bool:
    return str(value).strip().lower() in {"nan", "none", "", "null"}


def _ocr_for_file(
    ocr_results: list,
    filename: str,
) -> tuple[bool, list[str], int]:
    """
    Lookup OCR results for a given filename.
    Returns (has_text, detected_texts, contrast_violations_count).
    Uses TextDetectionResult objects from text_detector.
    """
    target = Path(filename).name.lower()
    for r in ocr_results:
        # r is a TextDetectionResult (Pydantic model)
        r_name = Path(r.filename).name.lower()
        if r_name == target:
            texts = [d.text for d in r.detections if d.text and d.text.strip()]
            return r.has_text, texts, r.contrast_violations_count
    return False, [], 0


def _ocr_result_for_file(ocr_results: list, filename: str):
    """Return the full TextDetectionResult for a given filename, or None."""
    target = Path(filename).name.lower()
    for r in ocr_results:
        if Path(r.filename).name.lower() == target:
            return r
    return None


# ---------------------------------------------------------------------------
# WCAG 1.1.1 checks
# ---------------------------------------------------------------------------


def _check_1_1_1_decorative(alt: str) -> tuple[bool, str]:
    """Decorative images MUST have alt='' (empty string)."""
    if alt == "" or _is_empty(alt):
        return True, "PASS [1.1.1] Decorative image correctly has empty alt"
    return (
        False,
        f"FAIL [1.1.1] Decorative image must have alt=\"\" (empty). Found: '{alt}'",
    )


def _check_1_1_1_missing_alt(sub_type: str) -> tuple[bool, str]:
    """Missing alt attribute entirely — WCAG violation for any image."""
    return (
        False,
        "FAIL [1.1.1] Alt attribute is completely missing — "
        "every <img> must have an alt attribute (WCAG violation).",
    )


def _check_1_1_1_informative(alt: str, detected_texts: list[str]) -> tuple[bool, str]:
    """
    Informative: alt must convey visible text detected by OCR.
    At least one OCR word (>=3 chars) must appear in the alt text.
    """
    norm_alt = _norm(alt or "")

    if not alt or norm_alt in _EMPTY_OR_GENERIC:
        return False, "FAIL [1.1.1] Alt text is empty or generic"

    if not detected_texts:
        return (
            True,
            "PASS [1.1.1] No OCR text detected; alt is non-empty "
            "(manual review recommended)",
        )

    norm_ocr = _norm(" ".join(detected_texts))
    ocr_words = [w for w in norm_ocr.split() if len(w) >= 3]

    if not ocr_words:
        return True, "PASS [1.1.1] OCR tokens too short to match; alt is non-empty"

    matched = [w for w in ocr_words if w in norm_alt]
    if matched:
        return True, f"PASS [1.1.1] OCR word(s) found in alt: {matched}"

    return (
        False,
        f"FAIL [1.1.1] OCR words {ocr_words[:5]} not found in alt text '{alt}'",
    )


def _check_1_1_1_logo(alt: str) -> tuple[bool, str]:
    """
    Logo: alt MUST include the word 'logo' (or 'home' for linked logos).
    W3C WAI: format is '[Brand name] logo'.
    """
    if not alt or _is_empty(alt) or _norm(alt) in _EMPTY_OR_GENERIC:
        return False, "FAIL [1.1.1] Logo has empty/missing alt text"

    norm = _norm(alt)
    if re.search(r"\blogo\b", norm) or re.search(r"\bhome\b", norm):
        return True, f"PASS [1.1.1] Logo alt includes 'logo'/'home': '{alt}'"

    return (
        False,
        f"FAIL [1.1.1] Logo alt must include the word 'logo' "
        f"(e.g. 'Kao logo'). Found: '{alt}'. "
        f"Screen readers need 'logo' to announce the image purpose.",
    )


def _check_1_1_1_icon(alt: str) -> tuple[bool, str]:
    """
    Icon: alt must describe the ACTION or include 'icon'.
    Social brand icons require '<Brand> icon' — brand name alone is insufficient.
    """
    if not alt or _is_empty(alt) or _norm(alt) in _EMPTY_OR_GENERIC:
        return False, "FAIL [1.1.1] Icon has empty/missing alt text"

    norm = _norm(alt)

    if norm in _SOCIAL_BRAND_NAMES:
        return (
            False,
            f"FAIL [1.1.1] Social icon alt '{alt}' must include 'icon' "
            f"(e.g. '{alt} icon'). Brand name alone is not sufficient per WCAG 1.1.1.",
        )

    has_qualifier = bool(re.search(r"\b(icon|logo|button|link)\b", norm))
    is_action = norm in _BUTTON_ACTION_WORDS or any(
        w in _BUTTON_ACTION_WORDS for w in norm.split()
    )

    if has_qualifier or is_action:
        return True, f"PASS [1.1.1] Icon alt describes purpose: '{alt}'"

    if len(norm) >= 2 and not norm.isdigit():
        return (
            True,
            f"PASS [1.1.1] Icon alt is non-empty: '{alt}' "
            f"(verify it describes the action, not the appearance)",
        )

    return False, f"FAIL [1.1.1] Icon alt '{alt}' does not describe purpose"


def _check_1_1_1_button(alt: str) -> tuple[bool, str]:
    """Button: alt must describe the action/purpose of the control."""
    if not alt or _is_empty(alt) or _norm(alt) in _EMPTY_OR_GENERIC:
        return False, "FAIL [1.1.1] Button has empty/missing accessible name"

    norm = _norm(alt)

    if norm in _BUTTON_ACTION_WORDS:
        return True, f"PASS [1.1.1] Button alt describes action: '{alt}'"

    matched = [w for w in norm.split() if w in _BUTTON_ACTION_WORDS]
    if matched:
        return (
            True,
            f"PASS [1.1.1] Button alt contains action word(s) {matched}: '{alt}'",
        )

    if len(norm) >= 2 and not norm.isdigit():
        return (
            True,
            f"PASS [1.1.1] Button alt is non-empty: '{alt}' "
            f"(verify it describes the button action)",
        )

    return False, f"FAIL [1.1.1] Button alt '{alt}' is not descriptive"


# ---------------------------------------------------------------------------
# WCAG 4.1.2 check
# ---------------------------------------------------------------------------


def _check_4_1_2(alt: str, sub_type: str) -> tuple[bool, str]:
    """
    WCAG 4.1.2: functional image must have a programmatically determinable
    accessible name. Uses alt (aria-label/title resolution already happened
    in the crawler/classifier via element.evaluate context).

    Logo  → name must include 'logo'.
    Icon  → brand-only name is insufficient.
    Button → any non-empty, non-generic name is acceptable.
    """
    name = (alt or "").strip()

    if not name or _norm(name) in _EMPTY_OR_GENERIC:
        return (
            False,
            f"FAIL [4.1.2] No accessible name found. alt='{alt}'",
        )

    norm = _norm(name)

    if sub_type == "logos":
        if re.search(r"\blogo\b", norm) or re.search(r"\bhome\b", norm):
            return True, f"PASS [4.1.2] Logo accessible name includes 'logo': '{name}'"
        return (
            False,
            f"FAIL [4.1.2] Logo accessible name '{name}' must include 'logo'.",
        )

    if sub_type == "icons" and norm in _SOCIAL_BRAND_NAMES:
        return (
            False,
            f"FAIL [4.1.2] Icon accessible name '{name}' is brand name only "
            f"— must say '{name} icon'.",
        )

    return True, f"PASS [4.1.2] Accessible name is present and meaningful: '{name}'"


# ---------------------------------------------------------------------------
# WCAG 1.4.5 check — Images of Text
# ---------------------------------------------------------------------------


def _check_1_4_5(
    classification: str,
    sub_type: str,
    is_logo: bool,
    has_ocr_text: bool,
) -> tuple[bool | None, str]:
    """
    WCAG 1.4.5: Images of Text — if an image contains text, real text should
    be used instead unless the presentation is essential (logos are exempt).

    Returns:
        (True, reason)   — PASS: no text detected, or logo exception applies
        (False, reason)  — FAIL: text detected in non-logo image
        (None, reason)   — N/A: decorative images are exempt
    """
    if classification == "decorative":
        return None, "N/A — decorative images are not evaluated for 1.4.5"

    # Logo / logotype exception (WCAG Note: logotypes are considered essential)
    if is_logo or sub_type == "logos":
        return (
            True,
            "PASS [1.4.5] Logo/logotype exception — customised branding text is exempt",
        )

    if not has_ocr_text:
        return True, "PASS [1.4.5] No text detected in image"

    # Text detected in a non-logo image — violation
    return (
        False,
        "FAIL [1.4.5] Image contains text — replace with real CSS-styled text. "
        "Only logos and essential-presentation images are exempt.",
    )


# ---------------------------------------------------------------------------
# WCAG 1.4.11 check — Non-text Contrast
# ---------------------------------------------------------------------------


def _check_1_4_11(
    is_button: bool,
    is_icon: bool,
    sub_type: str,
    has_ocr_text: bool,
    ocr_result,
) -> tuple[bool | None, str]:
    """
    WCAG 1.4.11: Non-text Contrast — UI components (buttons, icons used as
    controls) must have a contrast ratio of at least 3:1 against adjacent colours.

    We repurpose the OCR contrast data for button/icon images: if EasyOCR
    detected text inside the image the measured contrast_ratio is used as a
    proxy for the component's visual boundary contrast.

    Returns:
        (True, reason)   — PASS: meets 3:1 minimum
        (False, reason)  — FAIL: below 3:1 minimum
        (None, reason)   — N/A/INCOMPLETE: not a UI component, or no contrast data
    """
    is_ui_component = is_button or is_icon or sub_type in ("buttons", "icons")
    if not is_ui_component:
        return None, "N/A — 1.4.11 applies to UI components (buttons/icons)"

    if not has_ocr_text or ocr_result is None:
        return (
            None,
            "INCOMPLETE [1.4.11] No OCR contrast data available — manual check required",
        )

    # Find the minimum contrast ratio across all detected regions
    min_ratio: float | None = None
    for det in ocr_result.detections:
        ci = det.contrast_info or {}
        compliance = ci.get("compliance") or {}
        ratio = compliance.get("contrast_ratio")
        if ratio is not None:
            if min_ratio is None or ratio < min_ratio:
                min_ratio = ratio

    if min_ratio is None:
        return (
            None,
            "INCOMPLETE [1.4.11] Contrast data unavailable — manual check required",
        )

    ratio_str = f"{min_ratio:.2f}:1"
    if min_ratio < 3.0:
        return (
            False,
            f"FAIL [1.4.11] Non-text contrast ratio {ratio_str} is below the "
            f"3:1 minimum required for UI components.",
        )

    return (
        True,
        f"PASS [1.4.11] Non-text contrast ratio {ratio_str} meets the 3:1 minimum.",
    )


# ---------------------------------------------------------------------------
# Main auditor class
# ---------------------------------------------------------------------------


class AltTextAccessibilityAuditor:
    """
    Merges ImageData (crawler + classifier) with TextDetectionResult (OCR)
    and runs WCAG 1.1.1 + 4.1.2 checks for every crawled image.
    """

    def generate_audit_report(
        self,
        images_data: list,  # List[ImageData]
        ocr_results: list,  # List[TextDetectionResult]
        output_dir: str,
    ) -> list[dict]:
        """
        Parameters
        ----------
        images_data : crawler.images_data  (List[ImageData] Pydantic models)
        ocr_results : detector.results     (List[TextDetectionResult])
        output_dir  : crawler.output_dir   (report saved here as audit_report.csv)

        Returns
        -------
        List[dict]  — one dict per image (same rows written to CSV)
        """
        logger.info(
            f"Generating audit report — {len(images_data)} images, "
            f"{len(ocr_results)} OCR results"
        )

        records: list[dict] = []

        for img in images_data:
            # ── Pull fields from ImageData ───────────────────────────────
            filename = str(img.filename or "")
            src = str(img.src or "")
            url = str(img.url or "")
            alt_text = img.alt_text if img.alt_text is not None else ""
            title = str(img.title or "")
            classification = str(img.classification or "").strip().lower()
            sub_type = str(img.sub_type or "").strip().lower()
            is_logo = bool(img.is_logo)
            is_icon = bool(img.is_icon)
            is_button = bool(img.is_button)
            is_functional = bool(img.is_functional)
            is_decorative = bool(img.is_decorative)
            screenshot_path = str(img.screenshot_path or "")

            # ── OCR lookup by filename ───────────────────────────────────
            has_ocr_text, detected_texts, contrast_count = _ocr_for_file(
                ocr_results, filename
            )
            detected_joined = " | ".join(detected_texts)
            ocr_result = _ocr_result_for_file(ocr_results, filename)

            # ── Determine functional sub_type for WCAG checks ────────────
            # sub_type from classifier: "logos" | "icons" | "buttons" | "images"
            # Fallback via boolean flags for any edge cases
            if not sub_type or sub_type == "images":
                if is_logo:
                    sub_type = "logos"
                elif is_button:
                    sub_type = "buttons"
                elif is_icon:
                    sub_type = "icons"

            # ── WCAG checks ──────────────────────────────────────────────
            wcag_4_1_2_pass = None
            wcag_4_1_2_reason = "N/A — not a functional image"

            # Handle missing_alt as a special decorative sub-type
            if sub_type == "missing_alt" or (
                classification == "decorative" and alt_text is None
            ):
                wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_missing_alt(sub_type)

            elif classification == "decorative":
                wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_decorative(alt_text)

            elif classification == "informative":
                wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_informative(
                    alt_text, detected_texts
                )

            elif classification == "functional":
                if sub_type == "logos":
                    wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_logo(alt_text)
                elif sub_type == "icons":
                    wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_icon(alt_text)
                else:  # buttons / images
                    wcag_1_1_1_pass, wcag_1_1_1_reason = _check_1_1_1_button(alt_text)

                wcag_4_1_2_pass, wcag_4_1_2_reason = _check_4_1_2(alt_text, sub_type)

            elif classification == "complex":
                # Complex images need long descriptions; check alt is non-empty
                wcag_1_1_1_pass = (
                    bool(alt_text) and _norm(alt_text) not in _EMPTY_OR_GENERIC
                )
                wcag_1_1_1_reason = (
                    f"PASS [1.1.1] Complex image has alt: '{alt_text}'"
                    if wcag_1_1_1_pass
                    else "FAIL [1.1.1] Complex image (chart/diagram) must have "
                    "a meaningful alt or long description"
                )

            else:
                wcag_1_1_1_pass = (
                    bool(alt_text) and _norm(alt_text) not in _EMPTY_OR_GENERIC
                )
                wcag_1_1_1_reason = (
                    f"PASS [1.1.1] Alt is non-empty: '{alt_text}'"
                    if wcag_1_1_1_pass
                    else "FAIL [1.1.1] Alt empty/generic (unknown classification)"
                )

            # ── WCAG 1.4.5 (Images of Text) ──────────────────────────────
            wcag_1_4_5_pass, wcag_1_4_5_reason = _check_1_4_5(
                classification, sub_type, is_logo, has_ocr_text
            )

            # ── WCAG 1.4.11 (Non-text Contrast) ─────────────────────────
            wcag_1_4_11_pass, wcag_1_4_11_reason = _check_1_4_11(
                is_button, is_icon, sub_type, has_ocr_text, ocr_result
            )

            # Overall: all definitive checks must pass (None = N/A, skip)
            checks = [wcag_1_1_1_pass]
            if wcag_4_1_2_pass is not None:
                checks.append(wcag_4_1_2_pass)
            if wcag_1_4_5_pass is False:
                checks.append(False)
            if wcag_1_4_11_pass is False:
                checks.append(False)
            overall = "PASSED" if all(checks) else "FAILED"

            records.append(
                {
                    "filename": filename,
                    "src": src,
                    "url": url,
                    "classification": classification,
                    "sub_type": sub_type,
                    "is_logo": is_logo,
                    "is_icon": is_icon,
                    "is_button": is_button,
                    "is_functional": is_functional,
                    "is_decorative": is_decorative,
                    "alt_text": alt_text,
                    "title": title,
                    "has_ocr_text": has_ocr_text,
                    "detected_text": detected_joined,
                    "contrast_violations_count": contrast_count,
                    "wcag_1_1_1_status": "PASSED" if wcag_1_1_1_pass else "FAILED",
                    "wcag_4_1_2_status": (
                        "PASSED"
                        if wcag_4_1_2_pass is True
                        else "FAILED" if wcag_4_1_2_pass is False else "N/A"
                    ),
                    "wcag_1_4_5_status": (
                        "PASSED"
                        if wcag_1_4_5_pass is True
                        else "FAILED" if wcag_1_4_5_pass is False else "N/A"
                    ),
                    "wcag_1_4_11_status": (
                        "PASSED"
                        if wcag_1_4_11_pass is True
                        else "FAILED" if wcag_1_4_11_pass is False else "N/A"
                    ),
                    "overall_status": overall,
                    "wcag_1_1_1_reason": wcag_1_1_1_reason,
                    "wcag_4_1_2_reason": wcag_4_1_2_reason,
                    "wcag_1_4_5_reason": wcag_1_4_5_reason,
                    "wcag_1_4_11_reason": wcag_1_4_11_reason,
                    "screenshot_path": screenshot_path,
                }
            )

        # ── Save CSV ─────────────────────────────────────────────────────
        report_path = str(Path(output_dir) / "audit_report.csv")
        with open(report_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(records)

        # ── Console summary ───────────────────────────────────────────────
        self._print_summary(records, report_path)

        return records

    # ── Summary printer ──────────────────────────────────────────────────────

    def _print_summary(self, records: list[dict], report_path: str):
        total = len(records)
        passed = sum(1 for r in records if r["overall_status"] == "PASSED")
        failed = sum(1 for r in records if r["overall_status"] == "FAILED")

        sep = "=" * 70
        print(f"\n{sep}")
        print("  KA11Y — UNIFIED WCAG ACCESSIBILITY AUDIT REPORT")
        print(f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Report    : {report_path}")
        print(sep)
        print(f"  Total images audited : {total}")
        print(
            f"  PASSED               : {passed}  ({passed/total*100:.1f}%)"
            if total
            else "  No images."
        )
        print(
            f"  FAILED               : {failed}  ({failed/total*100:.1f}%)"
            if total
            else ""
        )
        print()

        # Per-criterion
        wcag_111 = [r for r in records if r["wcag_1_1_1_status"] != "N/A"]
        wcag_412 = [r for r in records if r["wcag_4_1_2_status"] != "N/A"]
        wcag_145 = [
            r for r in records if r.get("wcag_1_4_5_status") not in ("N/A", None)
        ]
        wcag_1411 = [
            r
            for r in records
            if r.get("wcag_1_4_11_status") not in ("N/A", "INCOMPLETE", None)
        ]
        p111 = sum(1 for r in wcag_111 if r["wcag_1_1_1_status"] == "PASSED")
        f111 = sum(1 for r in wcag_111 if r["wcag_1_1_1_status"] == "FAILED")
        p412 = sum(1 for r in wcag_412 if r["wcag_4_1_2_status"] == "PASSED")
        f412 = sum(1 for r in wcag_412 if r["wcag_4_1_2_status"] == "FAILED")
        p145 = sum(1 for r in wcag_145 if r.get("wcag_1_4_5_status") == "PASSED")
        f145 = sum(1 for r in wcag_145 if r.get("wcag_1_4_5_status") == "FAILED")
        p1411 = sum(1 for r in wcag_1411 if r.get("wcag_1_4_11_status") == "PASSED")
        f1411 = sum(1 for r in wcag_1411 if r.get("wcag_1_4_11_status") == "FAILED")

        print(
            f"  WCAG 1.1.1 (Non-text Content) : {p111} PASSED / {f111} FAILED ({len(wcag_111)} applicable)"
        )
        print(
            f"  WCAG 4.1.2 (Name/Role/Value)  : {p412} PASSED / {f412} FAILED ({len(wcag_412)} applicable)"
        )
        print(
            f"  WCAG 1.4.5 (Images of Text)   : {p145} PASSED / {f145} FAILED ({len(wcag_145)} applicable)"
        )
        print(
            f"  WCAG 1.4.11 (Non-text Contr.) : {p1411} PASSED / {f1411} FAILED ({len(wcag_1411)} with data)"
        )
        print()

        # By classification
        from collections import Counter

        cls_pass = Counter(
            r["classification"] for r in records if r["overall_status"] == "PASSED"
        )
        cls_fail = Counter(
            r["classification"] for r in records if r["overall_status"] == "FAILED"
        )
        all_cls = sorted(set(list(cls_pass.keys()) + list(cls_fail.keys())))
        print("  By classification:")
        print(f"  {'Classification':<20} {'PASSED':>8} {'FAILED':>8} {'TOTAL':>8}")
        print(f"  {'-'*46}")
        for cls in all_cls:
            p = cls_pass.get(cls, 0)
            f = cls_fail.get(cls, 0)
            print(f"  {cls:<20} {p:>8} {f:>8} {p+f:>8}")
        print()

        # OCR / contrast summary
        with_ocr = sum(1 for r in records if r["has_ocr_text"])
        with_contrast = sum(1 for r in records if r["contrast_violations_count"] > 0)
        print(f"  Images with OCR text detected  : {with_ocr}")
        print(f"  Images with contrast violations: {with_contrast}")
        print()

        # Failed images list
        failed_rows = [r for r in records if r["overall_status"] == "FAILED"]
        if failed_rows:
            print("  Failed images:")
            print(
                f"  {'Filename':<35} {'Classification':<15} {'Sub-type':<12} {'Alt text':<25} {'1.1.1':>6} {'4.1.2':>6}"
            )
            print(f"  {'-'*105}")
            for r in failed_rows:
                alt_preview = (r["alt_text"] or "")[:24]
                print(
                    f"  {r['filename']:<35} "
                    f"{r['classification']:<15} "
                    f"{r['sub_type']:<12} "
                    f"{alt_preview:<25} "
                    f"{r['wcag_1_1_1_status']:>6} "
                    f"{r['wcag_4_1_2_status']:>6}"
                )
        else:
            print("  All images passed!")

        print(sep)
        logger.info(
            f"Audit complete — {total} images, {passed} passed, {failed} failed. "
            f"Report: {report_path}"
        )
