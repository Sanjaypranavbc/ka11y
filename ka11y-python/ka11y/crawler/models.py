# crawler/models.py
from typing import Optional, List
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# WCAG violation record — matches the README output table format
# ─────────────────────────────────────────────────────────────────────────────
class WcagViolation(BaseModel):
    rule: str  # "1.1.1"
    level: str  # "A" | "AA" | "AAA"
    violation: str  # human-readable description
    suggestion: str  # fix suggestion
    element: str  # html_snippet (truncated)


# ─────────────────────────────────────────────────────────────────────────────
# Core image record (classification + file paths)
# ─────────────────────────────────────────────────────────────────────────────
class ImageData(BaseModel):
    url: str
    src: str
    alt_text: str = ""
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


# ─────────────────────────────────────────────────────────────────────────────
# Rich per-element metadata — captures everything WCAG rule-checkers need.
# Saved as JSON sidecar + master metadata.json per crawl run.
# ─────────────────────────────────────────────────────────────────────────────
class ImageMetadata(BaseModel):

    # ── Identity ─────────────────────────────────────────────────────────────
    image_hash: str = ""  # md5 of abs_src → links to screenshot
    page_url: str = ""
    src: str = ""  # resolved absolute URL
    tag_name: str = ""  # img | input | svg | canvas | i

    # ── Dimensions ───────────────────────────────────────────────────────────
    natural_width: int = 0
    natural_height: int = 0
    rendered_width: float = 0.0
    rendered_height: float = 0.0
    aspect_ratio: float = 0.0

    # ── WCAG 1.1.1 — Non-text Content ────────────────────────────────────────
    # alt=None  → attribute MISSING (WCAG violation)
    # alt=""    → explicit empty (intentionally decorative, valid)
    # alt="…"   → descriptive text
    alt: Optional[str] = None
    title_attr: Optional[str] = None
    aria_label: Optional[str] = None
    aria_labelledby: Optional[str] = None
    aria_describedby: Optional[str] = None
    aria_hidden: Optional[str] = None
    role: Optional[str] = None
    longdesc: Optional[str] = None  # obsolete but still audited

    # ── WCAG 1.4.5 — Images of Text ──────────────────────────────────────────
    contains_text: bool = False  # set by OCR module after crawl

    # ── WCAG 2.1.1 — Keyboard Accessibility ──────────────────────────────────
    tabindex: Optional[str] = None
    has_onclick: bool = False
    cursor_style: Optional[str] = None  # "pointer" → likely interactive

    # ── WCAG 2.4.4 — Link Purpose (In Context) ───────────────────────────────
    in_link: bool = False
    link_href: Optional[str] = None
    link_text: Optional[str] = None  # visible text of the <a> element
    link_aria_label: Optional[str] = None
    link_title: Optional[str] = None

    # ── Button context ────────────────────────────────────────────────────────
    in_button: bool = False
    button_text: Optional[str] = None
    button_aria_label: Optional[str] = None

    # ── Document structure context ────────────────────────────────────────────
    in_figure: bool = False
    figcaption_text: Optional[str] = None
    nearest_heading: Optional[str] = None  # h1–h6 ancestor or nearest sibling
    surrounding_text: Optional[str] = None  # visible text of parent element

    # ── Source / responsive-image attributes ─────────────────────────────────
    srcset: Optional[str] = None
    sizes: Optional[str] = None
    loading: Optional[str] = None  # lazy | eager | auto
    decoding: Optional[str] = None  # sync | async | auto
    data_src: Optional[str] = None
    crossorigin: Optional[str] = None
    usemap: Optional[str] = None  # image map reference

    # ── Computed CSS (relevant to accessibility) ──────────────────────────────
    css_display: Optional[str] = None
    css_visibility: Optional[str] = None
    css_opacity: Optional[str] = None
    css_object_fit: Optional[str] = None
    css_position: Optional[str] = None
    css_overflow: Optional[str] = None

    # ── Raw element code (for rule engines & report output) ──────────────────
    html_snippet: str = ""  # element.outerHTML[:800]
    parent_tag: str = ""
    parent_class: str = ""
    parent_id: str = ""
    parent_html: str = ""  # parent.outerHTML[:400]

    # ── Classification (mirrors ImageData) ───────────────────────────────────
    classification: str = ""
    sub_type: Optional[str] = None
    screenshot_path: str = ""
    filename: str = ""

    # ── Pre-computed WCAG violations ─────────────────────────────────────────
    wcag_violations: List[WcagViolation] = []

    # ─────────────────────────────────────────────────────────────────────────
    def compute_violations(self) -> "ImageMetadata":
        """
        Detect WCAG violations from captured metadata and populate
        wcag_violations. Call after all fields are set.

        Rules checked here (image-specific subset):
          1.1.1  Non-text Content
          2.1.1  Keyboard
          2.4.4  Link Purpose
          4.1.2  Name, Role, Value
        """
        v: list[WcagViolation] = []
        el = self.html_snippet or f'<{self.tag_name} src="{self.src[:60]}">'

        is_presentational = self.aria_hidden == "true" or self.role in (
            "presentation",
            "none",
        )

        # ── 1.1.1 alt attribute completely missing ────────────────────────
        if (
            not is_presentational
            and self.alt is None
            and not self.aria_label
            and not self.aria_labelledby
        ):
            v.append(
                WcagViolation(
                    rule="1.1.1",
                    level="A",
                    violation="Missing alt attribute",
                    suggestion='Add a descriptive alt attribute. Use alt="" if purely decorative.',
                    element=el,
                )
            )

        # ── 1.1.1 functional image with empty/missing accessible name ─────
        if self.in_link or self.in_button or self.has_onclick:
            has_name = bool(
                (self.alt and self.alt.strip())
                or self.aria_label
                or self.aria_labelledby
                or self.link_text
                or self.button_text
            )
            if not has_name:
                v.append(
                    WcagViolation(
                        rule="1.1.1",
                        level="A",
                        violation="Functional image has no accessible name",
                        suggestion=(
                            "Add alt text that describes the function, not the appearance. "
                            'e.g. alt="Submit form" for a submit button image.'
                        ),
                        element=el,
                    )
                )

        # ── 2.1.1 clickable image not keyboard reachable ──────────────────
        if (
            (self.has_onclick or self.cursor_style == "pointer")
            and not self.in_link
            and not self.in_button
        ):
            bad_tabindex = self.tabindex is None or self.tabindex == "-1"
            if bad_tabindex:
                v.append(
                    WcagViolation(
                        rule="2.1.1",
                        level="A",
                        violation="Interactive image not reachable by keyboard",
                        suggestion=(
                            'Wrap in a <button> or <a>, or add tabindex="0" and '
                            "a keydown handler (Enter/Space) to the element."
                        ),
                        element=el,
                    )
                )

        # ── 2.4.4 link with no discernible purpose ────────────────────────
        if self.in_link:
            link_name = (
                (self.alt and self.alt.strip())
                or self.link_text
                or self.link_aria_label
                or self.aria_label
            )
            if not link_name:
                v.append(
                    WcagViolation(
                        rule="2.4.4",
                        level="A",
                        violation="Link purpose cannot be determined from context",
                        suggestion=(
                            "Add descriptive alt text to the image, or add "
                            "aria-label to the <a> element."
                        ),
                        element=el,
                    )
                )

        # ── 4.1.2 interactive element with no accessible name ─────────────
        if self.in_button:
            btn_name = (
                (self.alt and self.alt.strip()) or self.aria_label or self.button_text
            )
            if not btn_name:
                v.append(
                    WcagViolation(
                        rule="4.1.2",
                        level="A",
                        violation="Button has no accessible name",
                        suggestion="Add aria-label to the <button>, or alt text to the image inside it.",
                        element=el,
                    )
                )

        self.wcag_violations = v
        return self
