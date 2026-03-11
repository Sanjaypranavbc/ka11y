"""
Alt Text Checker - WCAG 1.1.1 (Non-text Content) & 4.1.2 (Name, Role, Value)
==============================================================================
Checks whether:
  - Informative images: alt text contains OCR-detected text (partial match)
  - Functional images: alt text / accessible name is meaningful (not empty/generic)
Generates a consolidated CSV report with pass/fail status per image.
"""

import re
import json
import pandas as pd
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Heuristic list of acceptable accessible names for functional images
# (logos, icons, buttons). Add more as needed.
FUNCTIONAL_ACCEPTABLE_NAMES: set[str] = {
    # Navigation / UI actions
    "menu", "close", "open", "search", "back", "forward", "next", "prev",
    "previous", "submit", "send", "cancel", "confirm", "ok", "yes", "no",
    "save", "delete", "edit", "add", "remove", "upload", "download",
    "share", "print", "copy", "paste", "cut", "undo", "redo", "refresh",
    "reload", "home", "settings", "help", "info", "more", "less",
    "expand", "collapse", "toggle", "play", "pause", "stop", "mute",
    "unmute", "fullscreen", "exit fullscreen", "zoom in", "zoom out",
    "scroll up", "scroll down", "scroll left", "scroll right",
    "like", "dislike", "comment", "reply", "follow", "unfollow",
    "subscribe", "unsubscribe", "login", "logout", "sign in", "sign out",
    "sign up", "register", "checkout", "cart", "bag", "wishlist",
    "filter", "sort", "view", "hide", "show",
    # Social / brand icons
    "facebook", "twitter", "x", "instagram", "youtube", "linkedin",
    "tiktok", "pinterest", "snapchat", "whatsapp", "telegram", "line",
    "wechat", "note", "github", "gitlab", "reddit",
    # Cookie / consent
    "cookies settings", "accept all cookies", "reject all",
    "accept cookies", "decline cookies",
    # Generic logo / brand patterns (checked via regex below)
    # e.g., "kao", "kao group", "kao logo", etc.
}

# Regex patterns for functional acceptable names (logos, branded icons)
FUNCTIONAL_ACCEPTABLE_PATTERNS: list[re.Pattern] = [
    re.compile(r".+\s+(logo|icon|button|image|img|banner|badge)$", re.IGNORECASE),
    re.compile(r"^(logo|icon|button|banner|badge)\s+.+", re.IGNORECASE),
]

# Alt text values that are considered MISSING / insufficient
EMPTY_OR_GENERIC_ALT: set[str] = {
    "", "image", "img", "photo", "picture", "graphic", "figure",
    "untitled", "placeholder", "null", "none", "n/a", "na",
    "image of", "photo of", "picture of",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, strip punctuation/extra whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_functional_alt_acceptable(alt: str) -> bool:
    """
    Returns True when an alt / accessible-name for a functional image
    is considered meaningful under WCAG 4.1.2.
    """
    if not alt or _normalise(alt) in EMPTY_OR_GENERIC_ALT:
        return False

    norm = _normalise(alt)

    # Direct hit in acceptable set
    if norm in FUNCTIONAL_ACCEPTABLE_NAMES:
        return True

    # Pattern match (e.g., "Kao Logo", "Back Button")
    for pattern in FUNCTIONAL_ACCEPTABLE_PATTERNS:
        if pattern.match(alt.strip()):
            return True

    # Any non-empty, non-generic string that describes an action/label is
    # considered acceptable (heuristic: must be ≥ 2 chars & not purely numeric)
    if len(norm) >= 2 and not norm.isdigit():
        return True

    return False


def _ocr_texts_for_image(ocr_results: list[dict], image_filename: str) -> list[str]:
    """
    Extract all detected text strings for a given filename from OCR JSON results.
    Matching is done on the basename only (case-insensitive).
    """
    target = Path(image_filename).name.lower()
    for entry in ocr_results:
        if Path(entry.get("filename", "")).name.lower() == target:
            if entry.get("has_text") and entry.get("detections"):
                return [d["text"] for d in entry["detections"] if d.get("text")]
    return []


def _informative_alt_check(alt_text: str, detected_texts: list[str]) -> tuple[bool, str]:
    """
    WCAG 1.1.1 check for informative images.
    Returns (passed: bool, reason: str).

    Rule: at least ONE OCR-detected word (length ≥ 3) must appear in the alt text.
    If there are no detected texts, we fall back to checking alt is non-generic.
    """
    if not detected_texts:
        # No OCR text found → can't verify; pass if alt is non-empty & non-generic
        if alt_text and _normalise(alt_text) not in EMPTY_OR_GENERIC_ALT:
            return True, "No OCR text detected; alt text is non-empty"
        return False, "No OCR text detected and alt text is empty/generic"

    combined_ocr = " ".join(detected_texts)
    norm_alt = _normalise(alt_text or "")
    norm_ocr = _normalise(combined_ocr)

    # Extract meaningful words (length ≥ 3) from OCR
    ocr_words = [w for w in norm_ocr.split() if len(w) >= 3]

    if not ocr_words:
        # All OCR tokens are very short (e.g., single chars); treat as decoration
        if alt_text and _normalise(alt_text) not in EMPTY_OR_GENERIC_ALT:
            return True, "OCR words too short to match; alt text is non-empty"
        return False, "OCR words too short and alt text is empty/generic"

    matched = [w for w in ocr_words if w in norm_alt]
    if matched:
        return True, f"OCR word(s) found in alt text: {matched}"

    return False, f"No OCR word found in alt text. OCR words: {ocr_words[:5]}"


def _functional_alt_check(
    alt_text: str,
    aria_label: Optional[str],
    role: Optional[str],
) -> tuple[bool, str]:
    """
    WCAG 4.1.2 check for functional images.
    Accessible name is resolved via: alt → aria-label → role (fallback).
    """
    # Resolve accessible name (priority: aria-label > alt > title)
    accessible_name = (
        aria_label.strip() if aria_label and str(aria_label) != "nan" else
        alt_text.strip() if alt_text and str(alt_text) != "nan" else
        ""
    )

    if _is_functional_alt_acceptable(accessible_name):
        source = "aria-label" if (aria_label and str(aria_label) != "nan") else "alt"
        return True, f"Accessible name '{accessible_name}' is meaningful (from {source})"

    return False, (
        f"Functional image has missing/generic accessible name: '{accessible_name}'. "
        f"aria-label='{aria_label}', role='{role}'"
    )


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_alt_text(
    csv_path: str,
    ocr_json_path: str,
    output_csv_path: str = "alt_text_report.csv",
) -> pd.DataFrame:
    """
    Parameters
    ----------
    csv_path        : Path to the alt-text CSV produced by the crawler.
    ocr_json_path   : Path to the OCR JSON output file.
    output_csv_path : Where to save the final report CSV.

    Returns
    -------
    DataFrame with one row per image, containing audit columns.
    """
    # -- Load inputs --------------------------------------------------------
    df = pd.read_csv(csv_path)
    with open(ocr_json_path, "r", encoding="utf-8") as f:
        ocr_data = json.load(f)

    ocr_results: list[dict] = ocr_data.get("results", [])

    # -- Normalise column names ---------------------------------------------
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = {"src", "alt_text", "classification"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    # Optional metadata columns (may not always be present)
    aria_col   = "aria_label"   if "aria_label"   in df.columns else None
    role_col   = "role"         if "role"          in df.columns else None
    title_col  = "title"        if "title"         in df.columns else None
    fname_col  = "screenshot_path" if "screenshot_path" in df.columns else None

    # -- Build report rows --------------------------------------------------
    records = []

    for _, row in df.iterrows():
        src             = str(row.get("src", ""))
        alt_text        = str(row.get("alt_text", "")) if pd.notna(row.get("alt_text")) else ""
        classification  = str(row.get("classification", "")).strip().lower()
        aria_label      = str(row.get(aria_col, "")) if aria_col else ""
        role            = str(row.get(role_col, ""))  if role_col else ""
        title           = str(row.get(title_col, "")) if title_col else ""
        screenshot_path = str(row.get(fname_col, "")) if fname_col else ""

        # Derive filename for OCR lookup
        filename = Path(screenshot_path).name if screenshot_path else Path(src).name

        # Detected texts from OCR
        detected_texts = _ocr_texts_for_image(ocr_results, filename)
        detected_text_joined = " | ".join(detected_texts) if detected_texts else ""

        # ---- Run WCAG check -----------------------------------------------
        if classification == "decorative":
            # Decorative images should have empty alt=""
            passed = (alt_text == "" or alt_text.lower() in {"", "nan"})
            wcag_criterion = "WCAG 1.1.1"
            reason = (
                "Decorative image has empty alt (correct)"
                if passed else
                f"Decorative image should have empty alt, found: '{alt_text}'"
            )

        elif classification == "informative":
            wcag_criterion = "WCAG 1.1.1"
            passed, reason = _informative_alt_check(alt_text, detected_texts)

        elif classification == "functional":
            wcag_criterion = "WCAG 4.1.2"
            passed, reason = _functional_alt_check(alt_text, aria_label, role)

        else:
            # Unknown classification → basic non-empty check
            wcag_criterion = "WCAG 1.1.1"
            passed = bool(alt_text) and _normalise(alt_text) not in EMPTY_OR_GENERIC_ALT
            reason = "Unknown classification; checked alt is non-empty"

        records.append({
            "filename":          filename,
            "src":               src,
            "classification":    classification,
            "wcag_criterion":    wcag_criterion,
            "status":            "PASSED" if passed else "FAILED",
            "source_alt_text":   alt_text,
            "aria_label":        aria_label,
            "role":              role,
            "title":             title,
            "detected_text":     detected_text_joined,
            "reason":            reason,
        })

    report_df = pd.DataFrame(records)

    # -- Summary stats ------------------------------------------------------
    total   = len(report_df)
    passed  = (report_df["status"] == "PASSED").sum()
    failed  = (report_df["status"] == "FAILED").sum()

    print("=" * 60)
    print("ALT TEXT AUDIT REPORT")
    print("=" * 60)
    print(f"Total images checked : {total}")
    print(f"PASSED               : {passed}  ({passed/total*100:.1f}%)")
    print(f"FAILED               : {failed}  ({failed/total*100:.1f}%)")
    print()

    by_criterion = report_df.groupby(["wcag_criterion", "status"]).size().unstack(fill_value=0)
    print("By WCAG criterion:")
    print(by_criterion.to_string())
    print()

    by_class = report_df.groupby(["classification", "status"]).size().unstack(fill_value=0)
    print("By classification:")
    print(by_class.to_string())
    print("=" * 60)

    # -- Save report --------------------------------------------------------
    report_df.to_csv(output_csv_path, index=False)
    print(f"\nReport saved → {output_csv_path}")

    return report_df


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    report = check_alt_text(
        csv_path="crawled_images/kao_com_0311_1700/images_with_alt_text.csv",
        ocr_json_path="crawled_images/kao_com_0311_1700/text_detected/text_detection_report.json",
        output_csv_path="./output.csv",
    )
    print(report.to_string(index=False))