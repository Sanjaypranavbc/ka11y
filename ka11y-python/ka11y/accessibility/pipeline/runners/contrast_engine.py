import re
from typing import Tuple, Dict, Any
from ..config.thresholds import CONTRAST_NORMAL_AA, CONTRAST_LARGE_AA

class ContrastEngine:
    """Computes WCAG 2.1 relative luminance and contrast ratios."""

    @staticmethod
    def parse_rgb(color_str: str) -> Tuple[int, int, int]:
        """Parses rgb(a) or hex into 0-255 RGB tuples."""
        # Handle hex
        if color_str.startswith('#'):
            h = color_str.lstrip('#')
            if len(h) == 3:
                h = ''.join([c*2 for c in h])
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        
        # Handle rgb(a)
        numbers = re.findall(r'\d+', color_str)
        if len(numbers) >= 3:
            return int(numbers[0]), int(numbers[1]), int(numbers[2])
        return (0, 0, 0)

    @staticmethod
    def relative_luminance(r: int, g: int, b: int) -> float:
        """Calculates relative luminance per WCAG 2.1 specs."""
        def channel_lum(c: int) -> float:
            c_srgb = c / 255.0
            if c_srgb <= 0.03928:
                return c_srgb / 12.92
            return ((c_srgb + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)

    @classmethod
    def calculate_ratio(cls, fg_color: str, bg_color: str) -> float:
        """Calculates contrast ratio between two colors."""
        fg_rgb = cls.parse_rgb(fg_color)
        bg_rgb = cls.parse_rgb(bg_color)
        
        l1 = cls.relative_luminance(*fg_rgb)
        l2 = cls.relative_luminance(*bg_rgb)
        
        bright = max(l1, l2)
        dark = min(l1, l2)
        return round((bright + 0.05) / (dark + 0.05), 2)

    @classmethod
    def evaluate_1_4_3(cls, fg_color: str, bg_color: str, is_large_text: bool) -> Dict[str, Any]:
        """Returns structured evidence for WCAG 1.4.3 AA."""
        ratio = cls.calculate_ratio(fg_color, bg_color)
        threshold = CONTRAST_LARGE_AA if is_large_text else CONTRAST_NORMAL_AA
        
        return {
            "ratio": ratio,
            "threshold": threshold,
            "is_large_text": is_large_text,
            "passes": ratio >= threshold
        }
