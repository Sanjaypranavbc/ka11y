# contrast_analyser.py

import cv2
import numpy as np
from typing import Tuple, Dict, Any, List, Union

# -------------------------
# Color space utilities
# -------------------------


def srgb_to_linear(channel: np.ndarray) -> np.ndarray:
    return np.where(
        channel <= 0.04045, channel / 12.92, np.power((channel + 0.055) / 1.055, 2.4)
    )


# -------------------------
# Segmentation
# -------------------------


def segment_text_region(region: np.ndarray) -> np.ndarray:
    """
    Segment text vs background using Otsu + luminance-based polarity detection.
    Returns mask: 255 = text, 0 = background
    """
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # --- NEW: determine correct polarity using luminance ---
    # Assume two candidates:
    # 1. thresh == 0 is text
    # 2. thresh == 255 is text

    mask_candidate_1 = thresh  # text = white (255)
    mask_candidate_2 = cv2.bitwise_not(thresh)  # text = black (0 → 255)

    def compute_separation(mask):
        rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB) / 255.0

        linear = np.zeros_like(rgb)
        for i in range(3):
            linear[:, :, i] = srgb_to_linear(rgb[:, :, i])

        luminance = (
            0.2126 * linear[:, :, 0]
            + 0.7152 * linear[:, :, 1]
            + 0.0722 * linear[:, :, 2]
        )

        text_pixels = luminance[mask == 255]
        bg_pixels = luminance[mask == 0]

        if len(text_pixels) == 0 or len(bg_pixels) == 0:
            return 0

        return abs(np.mean(text_pixels) - np.mean(bg_pixels))

    sep1 = compute_separation(mask_candidate_1)
    sep2 = compute_separation(mask_candidate_2)

    # Choose mask with stronger separation
    if sep2 > sep1:
        return mask_candidate_2
    else:
        return mask_candidate_1


# -------------------------
# Luminance + contrast
# -------------------------


def calculate_luminance_contrast(
    region: np.ndarray, mask: np.ndarray
) -> Tuple[float, float, float]:

    rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB) / 255.0

    linear = np.zeros_like(rgb)
    for i in range(3):
        linear[:, :, i] = srgb_to_linear(rgb[:, :, i])

    luminance = (
        0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]
    )

    text_pixels = luminance[mask == 255]
    bg_pixels = luminance[mask == 0]

    if len(text_pixels) == 0 or len(bg_pixels) == 0:
        return None, None, None

    # 🔑 Determine text polarity
    text_is_light = np.mean(text_pixels) > np.mean(bg_pixels)

    if text_is_light:
        # White / light text
        text_L = float(np.percentile(text_pixels, 90))
        bg_L = float(np.percentile(bg_pixels, 10))
    else:
        # Dark text
        text_L = float(np.percentile(text_pixels, 10))
        bg_L = float(np.percentile(bg_pixels, 90))

    lighter = max(text_L, bg_L)
    darker = min(text_L, bg_L)

    contrast_ratio = (lighter + 0.05) / (darker + 0.05)

    return text_L, bg_L, contrast_ratio


# -------------------------
# Average colors (reporting only)
# -------------------------


def get_average_rgb(
    region: np.ndarray, mask: np.ndarray
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:

    b, g, r = cv2.split(region)

    fg_mask = mask == 255
    bg_mask = mask == 0

    fg_rgb = (
        int(np.mean(r[fg_mask])) if np.any(fg_mask) else 255,
        int(np.mean(g[fg_mask])) if np.any(fg_mask) else 255,
        int(np.mean(b[fg_mask])) if np.any(fg_mask) else 255,
    )

    bg_rgb = (
        int(np.mean(r[bg_mask])) if np.any(bg_mask) else 0,
        int(np.mean(g[bg_mask])) if np.any(bg_mask) else 0,
        int(np.mean(b[bg_mask])) if np.any(bg_mask) else 0,
    )

    return fg_rgb, bg_rgb


# -------------------------
# WCAG compliance
# -------------------------


def check_wcag_compliance(
    ratio: float,
    font_size_px: float = 16,
    is_bold: bool = False,
    is_ui_component: bool = False,
) -> Dict[str, Any]:
    """
    WCAG 2.1 AA/AAA thresholds:
      Large text  = ≥24px regular  OR  ≥18.6667px bold (14pt = 14 * 96/72 px)
      AA  normal  : 4.5:1
      AA  large   : 3.0:1
      AAA normal  : 7.0:1
      AAA large   : 4.5:1
      Non-text/UI (1.4.11): 3.0:1 — AA only, WCAG defines no AAA tier for it.
    """
    if is_ui_component:
        return {
            "contrast_ratio": round(ratio, 2),
            "AA_passes": ratio >= 3.0,  # ✅ normalize key name
            # WCAG 1.4.11 (Non-text Contrast) is AA-only — there is no AAA
            # success criterion for it, so "AAA_passes" is not applicable
            # rather than a fabricated pass/fail value.
            "AAA_passes": None,
            "is_ui_component": True,
            "aa_threshold_used": 3.0,
        }
    # Cast to plain Python bool: font_size_px may be np.float64 (from
    # np.linalg.norm in bbox_height_rotated), which makes comparisons return
    # np.bool_ — not JSON-serializable by the standard library encoder.
    is_large = bool((font_size_px >= 24) or (is_bold and font_size_px >= 18.6667))

    aa_threshold = 3.0 if is_large else 4.5
    aaa_threshold = 4.5 if is_large else 7.0

    return {
        "contrast_ratio": round(ratio, 2),
        "AA_passes": bool(ratio >= aa_threshold),
        "AAA_passes": bool(ratio >= aaa_threshold),
        "is_large_text": is_large,
        "aa_threshold_used": aa_threshold,
        "aaa_threshold_used": aaa_threshold,
    }


# -------------------------
# MAIN ENTRY
# -------------------------


def analyze_text_region(
    image: Union[str, np.ndarray],
    bbox: List[Tuple[int, int]],
    font_size_px: float = 16,
    is_bold: bool = False,
) -> Dict[str, Any]:

    try:
        if isinstance(image, str):
            img = cv2.imread(image)
            if img is None:
                return {"error": "Could not load image"}
        else:
            img = image

        pts = np.array(bbox, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)

        pad = 2
        H, W = img.shape[:2]
        x = max(0, x - pad)
        y = max(0, y - pad)
        w = min(W - x, w + 2 * pad)
        h = min(H - y, h + 2 * pad)

        region = img[y : y + h, x : x + w]
        if region.size == 0:
            return {"error": "Empty region"}

        mask = segment_text_region(region)

        text_L, bg_L, ratio = calculate_luminance_contrast(region, mask)
        if text_L is None:
            return {"error": "Segmentation failed"}

        fg_rgb, bg_rgb = get_average_rgb(region, mask)
        # Always scored against the text-size thresholds (never the 3:1
        # is_ui_component shortcut) — WCAG 1.4.3/1.4.6 apply to text based on
        # its own size/weight, not on whether it sits inside a button. The
        # separate 1.4.11 (non-text/UI boundary contrast) approximation is
        # computed independently in alttext.py's `_check_1_4_11`, directly
        # off `contrast_ratio` below, against its own 3:1 threshold.
        compliance = check_wcag_compliance(
            ratio, font_size_px=font_size_px, is_bold=is_bold
        )

        return {
            "region": region,
            "mask": mask,
            "foreground_color": fg_rgb,
            "background_color": bg_rgb,
            "luminance_fg": round(text_L, 4),
            "luminance_bg": round(bg_L, 4),
            "contrast_ratio": round(ratio, 2),
            "compliance": compliance,
        }

    except Exception as e:
        return {"error": str(e)}


# -------------------------
# UI COMPONENT CONTRAST (WCAG 1.4.11)
# -------------------------


def _compute_luminance_map(region: np.ndarray) -> np.ndarray:
    """Convert region to luminance map."""
    rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB) / 255.0

    linear = np.zeros_like(rgb)
    for i in range(3):
        linear[:, :, i] = srgb_to_linear(rgb[:, :, i])

    luminance = (
        0.2126 * linear[:, :, 0] + 0.7152 * linear[:, :, 1] + 0.0722 * linear[:, :, 2]
    )
    return luminance


def analyze_ui_component(
    image: Union[str, np.ndarray],
    bbox: List[Tuple[int, int]],
    context_pad: int = 8,  # 🔑 important for F14
) -> Dict[str, Any]:
    """
    Analyze non-text contrast (WCAG 1.4.11) for UI components.

    Measures contrast between:
      - component region
      - surrounding page background (context)

    Fixes:
      F14 — ensures page context is included
      F15 — actually uses is_ui_component path
    """
    try:
        if isinstance(image, str):
            img = cv2.imread(image)
            if img is None:
                return {"error": "Could not load image"}
        else:
            img = image

        pts = np.array(bbox, dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)

        H, W = img.shape[:2]

        # --- Expand bbox to include surrounding context (F14 fix) ---
        x0 = max(0, x - context_pad)
        y0 = max(0, y - context_pad)
        x1 = min(W, x + w + context_pad)
        y1 = min(H, y + h + context_pad)

        outer = img[y0:y1, x0:x1]
        if outer.size == 0:
            return {"error": "Empty region"}

        # If bbox touches edge → no context → cannot evaluate properly
        if x0 == 0 or y0 == 0 or x1 == W or y1 == H:
            return {
                "needs_review": True,
                "reason": "Insufficient surrounding context for UI contrast evaluation",
            }

        # --- Create masks ---
        mask = np.zeros(outer.shape[:2], dtype=np.uint8)

        inner_x0 = context_pad
        inner_y0 = context_pad
        inner_x1 = inner_x0 + w
        inner_y1 = inner_y0 + h

        mask[inner_y0:inner_y1, inner_x0:inner_x1] = 255

        component_pixels = mask == 255
        surround_pixels = mask == 0

        # --- Luminance ---
        luminance = _compute_luminance_map(outer)

        comp_vals = luminance[component_pixels]
        bg_vals = luminance[surround_pixels]

        if len(comp_vals) == 0 or len(bg_vals) == 0:
            return {"error": "Failed to compute luminance"}

        # Use robust percentiles (avoid noise)
        comp_L = float(np.percentile(comp_vals, 50))
        bg_L = float(np.percentile(bg_vals, 50))

        lighter = max(comp_L, bg_L)
        darker = min(comp_L, bg_L)

        ratio = (lighter + 0.05) / (darker + 0.05)

        # --- WCAG 1.4.11 ---
        compliance = check_wcag_compliance(ratio, is_ui_component=True)  # 🔑 F15 fix

        return {
            "contrast_ratio": round(ratio, 2),
            "luminance_component": round(comp_L, 4),
            "luminance_background": round(bg_L, 4),
            "compliance": compliance,
            "type": "ui_component",
        }

    except Exception as e:
        return {"error": str(e)}
