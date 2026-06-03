import re
from typing import Tuple, Dict, Any
from ..config.thresholds import CONTRAST_NORMAL_AA, CONTRAST_LARGE_AA


# (r, g, b, alpha) where alpha is 0..1
RGBA = Tuple[int, int, int, float]
RGB = Tuple[int, int, int]


# Floating-point and integer channels both allowed; we cast to int after
# clamping to 0-255. The previous parser used ``r"\d+"`` which split the
# alpha "0.5" of ``rgba(255,0,0,0.5)`` into ``["0", "5"]`` — collapsing the
# colour to (0, 5, *) and silently producing the wrong contrast ratio.
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class ContrastEngine:
    """Computes WCAG 2.1 relative luminance and contrast ratios.

    Handles ``rgba(...)`` foregrounds by Porter-Duff-compositing the
    foreground over the resolved background colour before computing
    luminance. Hex shorthands (``#abc``, ``#abcd``) and the 8-digit
    ``#RRGGBBAA`` form are also supported.
    """

    @staticmethod
    def parse_color(color_str: str) -> RGBA:
        """Parses hex / ``rgb(...)`` / ``rgba(...)`` into ``(r, g, b, alpha)``.

        ``alpha`` is a float in ``[0, 1]``. Unparseable input yields opaque
        black so downstream maths stays well-defined; callers needing to
        distinguish "missing" from "black" should check the input first.
        """
        if not color_str:
            return 0, 0, 0, 1.0

        s = color_str.strip().lower()

        # Hex variants: #rgb, #rgba, #rrggbb, #rrggbbaa
        if s.startswith("#"):
            h = s.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            elif len(h) == 4:
                h = "".join(c * 2 for c in h)
            if len(h) == 8:
                r, g, b, a8 = (int(h[i : i + 2], 16) for i in (0, 2, 4, 6))
                return r, g, b, a8 / 255.0
            if len(h) == 6:
                r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
                return r, g, b, 1.0
            return 0, 0, 0, 1.0

        # rgb()/rgba()/named. Pull every numeric token in order. The fourth
        # token (if present) is alpha; the rest are RGB channels.
        tokens = _NUMBER_RE.findall(s)
        if len(tokens) >= 4:
            r, g, b = (int(round(float(t))) for t in tokens[:3])
            a = float(tokens[3])
            return _clamp_byte(r), _clamp_byte(g), _clamp_byte(b), max(0.0, min(1.0, a))
        if len(tokens) >= 3:
            r, g, b = (int(round(float(t))) for t in tokens[:3])
            return _clamp_byte(r), _clamp_byte(g), _clamp_byte(b), 1.0
        return 0, 0, 0, 1.0

    @staticmethod
    def composite_over(fg: RGBA, bg: RGB) -> RGB:
        """Porter-Duff 'source over destination' compositing in the sRGB
        gamma-encoded space, matching how browsers paint pixels before the
        viewer's eye sees them. WCAG 2.x contrast is measured on those
        rendered pixels, so compositing in display space (not linear light)
        is the correct simplification."""
        fr, fg_, fb, fa = fg
        br, bg_, bb = bg
        if fa >= 1.0:
            return fr, fg_, fb
        if fa <= 0.0:
            return br, bg_, bb
        r = int(round(fr * fa + br * (1.0 - fa)))
        g = int(round(fg_ * fa + bg_ * (1.0 - fa)))
        b = int(round(fb * fa + bb * (1.0 - fa)))
        return _clamp_byte(r), _clamp_byte(g), _clamp_byte(b)

    @classmethod
    def parse_rgb(cls, color_str: str) -> RGB:
        """Back-compat shim: 3-tuple drop-alpha view of :func:`parse_color`."""
        r, g, b, _ = cls.parse_color(color_str)
        return r, g, b

    @staticmethod
    def relative_luminance(r: int, g: int, b: int) -> float:
        """Calculates relative luminance per WCAG 2.1 specs."""

        def channel_lum(c: int) -> float:
            c_srgb = c / 255.0
            if c_srgb <= 0.03928:
                return c_srgb / 12.92
            return ((c_srgb + 0.055) / 1.055) ** 2.4

        return (
            0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)
        )

    @classmethod
    def calculate_ratio(cls, fg_color: str, bg_color: str) -> float:
        """Calculates contrast ratio between two colors.

        If either colour carries alpha, the foreground is composited over
        the background first; if the background itself is semi-transparent,
        an opaque white is assumed below it (the conservative default browsers
        use when no document-level background can be resolved).
        """
        fg_rgba = cls.parse_color(fg_color)
        bg_rgba = cls.parse_color(bg_color)

        # Resolve background to a solid colour first.
        if bg_rgba[3] < 1.0:
            bg_rgb = cls.composite_over(bg_rgba, (255, 255, 255))
        else:
            bg_rgb = bg_rgba[:3]

        # Composite foreground over solid background.
        fg_rgb = cls.composite_over(fg_rgba, bg_rgb)

        l1 = cls.relative_luminance(*fg_rgb)
        l2 = cls.relative_luminance(*bg_rgb)

        bright = max(l1, l2)
        dark = min(l1, l2)
        return round((bright + 0.05) / (dark + 0.05), 2)

    @classmethod
    def evaluate_1_4_3(
        cls, fg_color: str, bg_color: str, is_large_text: bool
    ) -> Dict[str, Any]:
        """Returns structured evidence for WCAG 1.4.3 AA."""
        ratio = cls.calculate_ratio(fg_color, bg_color)
        threshold = CONTRAST_LARGE_AA if is_large_text else CONTRAST_NORMAL_AA

        return {
            "ratio": ratio,
            "threshold": threshold,
            "is_large_text": is_large_text,
            "passes": ratio >= threshold,
        }


def _clamp_byte(n: int) -> int:
    if n < 0:
        return 0
    if n > 255:
        return 255
    return n
