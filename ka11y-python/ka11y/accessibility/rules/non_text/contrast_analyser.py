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
    Segment text vs background using Otsu + heuristic inversion.
    Returns mask: 255 = text, 0 = background
    """
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)

    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Heuristic: text occupies less area than background
    if np.sum(thresh == 255) > thresh.size / 2:
        mask = cv2.bitwise_not(thresh)
    else:
        mask = thresh

    return mask


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
      Large text  = ≥24px regular  OR  ≥18.5px bold
      AA  normal  : 4.5:1
      AA  large   : 3.0:1
      AAA normal  : 7.0:1
      AAA large   : 4.5:1
    """
    if is_ui_component:  # ← add early return
        return {
            "contrast_ratio": round(ratio, 2),
            "AA_ui_component": ratio >= 3.0,
            "is_ui_component": True,
        }
    is_large = (font_size_px >= 24) or (is_bold and font_size_px >= 18.5)

    aa_threshold  = 3.0 if is_large else 4.5
    aaa_threshold = 4.5 if is_large else 7.0

    return {
        "contrast_ratio": round(ratio, 2),
        "AA_passes": ratio >= aa_threshold,
        "AAA_passes": ratio >= aaa_threshold,
        "is_large_text": is_large,
        "aa_threshold_used": aa_threshold,
    }

# -------------------------
# MAIN ENTRY
# -------------------------


def analyze_text_region(
    image: Union[str, np.ndarray], bbox: List[Tuple[int, int]], font_size_px: float = 16, is_bold: bool = False
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
        compliance = check_wcag_compliance(ratio, font_size_px=font_size_px, is_bold=is_bold)

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
