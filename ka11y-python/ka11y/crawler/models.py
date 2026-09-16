# crawler/models.py
from typing import Optional
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# Core image record (classification + file paths)
# ─────────────────────────────────────────────────────────────────────────────
class ImageData(BaseModel):
    url: str
    src: str
    alt_text: Optional[str] = None
    title: str = ""
    classification: str
    sub_type: Optional[str] = None
    is_functional: bool = False
    is_decorative: bool = False
    is_complex: bool = False
    is_text_image: bool = False
    is_logo: bool = False
    is_icon: bool = False
    is_button: bool = False
    file_format: Optional[str] = None
    element_id: str | None = None
    screenshot_path: str
    filename: str
    # Capture status: "ok" | "failed" | "timeout" | "network" | "dom_missing"
    capture_status: str = "ok"
    capture_error: Optional[str] = None
    # WCAG 1.1.1: a decorative image is allowed to omit alt only when it is
    # programmatically hidden from assistive tech. Both signals are captured
    # so the alttext auditor can distinguish "decorative + properly hidden"
    # (PASS) from "decorative classification but exposed to AT" (FAIL).
    aria_hidden: Optional[str] = None
    role: Optional[str] = None

    # ── Page-context capture (WCAG 1.4.11 Non-text Contrast) ─────────────────
    # A padded screenshot around the element (icon/logo elements only — see
    # optimized/engine.py's `_capture_assets`) plus the element's bounding box
    # local to that image, so boundary contrast can be measured against the
    # real surrounding page background instead of the element's own isolated
    # pixels. Absent when the crawler couldn't capture context (edge-of-page
    # elements, capture failures, or element types this isn't wired for yet);
    # `_check_1_4_11` falls back to an OCR-text-in-image proxy in that case.
    full_page_screenshot_path: Optional[str] = None
    page_bbox: Optional[list[tuple[int, int]]] = None

    # ── Accessible-name context (WCAG 1.1.1 / 4.1.2) ─────────────────────────
    # SC 1.1.1 asks whether an equivalent text alternative exists — by ANY valid
    # mechanism, not whether this element carries an `alt` attribute. An image
    # inside a control that already has an accessible name is named by that
    # control, so judging the <img> in isolation reports false violations
    # (`<button aria-label="Search"><img alt=""></button>` is conformant).
    # The crawler already computes all of this per element; these fields carry
    # it through to the auditor.
    element_type: Optional[str] = None  # img | svg_inline | css_background_image | area | …
    alt_present: bool = True  # False = no alt attribute at all (vs alt="")
    in_link: bool = False
    in_button: bool = False
    # The containing link/button exposes its own accessible name (visible text,
    # aria-label, aria-labelledby) independently of this image.
    in_labeled_control: bool = False
    # The element carries its own rendered text (a CSS background behind text is
    # decoration, not the sole carrier of information).
    has_own_text_content: bool = False

    # ── Long-description context (WCAG 1.1.1 complex-image situation) ────────
    figcaption_text: Optional[str] = None
    aria_describedby_text: Optional[str] = None
    has_longdesc: bool = False
    in_figure: bool = False

    def has_long_description(self) -> bool:
        """True when a programmatically associated long description exists."""
        return bool(
            self.has_longdesc
            or (self.aria_describedby_text or "").strip()
            or (self.figcaption_text or "").strip()
        )
