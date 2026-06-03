# a11y/accessibility/pipeline/config/thresholds.py

# 1.4.3 & 1.4.6: Contrast
CONTRAST_NORMAL_AA = 4.5
CONTRAST_LARGE_AA = 3.0
CONTRAST_NORMAL_AAA = 7.0
CONTRAST_LARGE_AAA = 4.5
LARGE_TEXT_PT = 18.0
LARGE_TEXT_BOLD_PT = 14.0

# 2.5.8: Target Size
MIN_TARGET_SIZE_PX = 24.0
MIN_TARGET_SPACING_PX = 24.0  # Combined target + spacing

# 1.1.1: Alt Text
MIN_ICON_ALT_LENGTH = 4
GENERIC_ALT_STRINGS = {"image", "picture", "photo", "icon", "graphic", "spacer", "logo"}

# 2.4.13: Focus Appearance
MIN_FOCUS_THICKNESS_PX = 1.0  # CSS pixels
MIN_FOCUS_CONTRAST = 3.0

# Exemptions
EXEMPT_ROLES_FROM_TARGET_SIZE = {"inline_link", "ua_controlled_input"}
EXEMPT_FROM_CONTRAST = {"logo", "decorative", "inactive_ui_component"}
