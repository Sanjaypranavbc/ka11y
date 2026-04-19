"""
ka11y/accessibility/rendered/models.py
=======================================
Pydantic models for rendered-layout snapshots, focus traversal, and
rule audit records.  All models are shared across evaluators.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ── Geometry ──────────────────────────────────────────────────────────────────


class Rect(BaseModel):
    """CSS pixel bounding rectangle (getBoundingClientRect values)."""

    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0

    @property
    def area(self) -> float:
        return self.width * self.height

    @classmethod
    def empty(cls) -> "Rect":
        return cls()


# ── Element snapshot ──────────────────────────────────────────────────────────


class ElementSnapshot(BaseModel):
    """Captured state of one DOM element at a given scenario."""

    element_id: Optional[str] = None
    selector: str = ""
    tag: str = ""
    text: str = ""
    html_snippet: str = ""

    rect: Rect = Field(default_factory=Rect.empty)
    client_width: float = 0.0
    client_height: float = 0.0
    scroll_width: float = 0.0
    scroll_height: float = 0.0

    overflow_x: str = "visible"
    overflow_y: str = "visible"
    position: str = "static"

    has_overflow_x_scroll: bool = False

    visible: bool = True
    focusable: bool = False
    fixed_or_sticky: bool = False
    z_index: int = 0

    page_url: str = ""

    # Extra computed style fields
    font_size: str = ""
    line_height: str = ""
    display: str = ""
    visibility: str = "visible"
    opacity: float = 1.0

    # Whether text is likely clipped
    text_clipped: bool = False

    # CSS transform (used to detect JS-based orientation-lock hacks)
    transform: str = "none"


# ── Page snapshot ─────────────────────────────────────────────────────────────


class PageSnapshot(BaseModel):
    """Captured state of a full page at a given scenario."""

    scenario: str
    page_url: str
    viewport_width: int
    viewport_height: int
    document_scroll_width: float = 0.0
    document_scroll_height: float = 0.0
    body_scroll_width: float = 0.0
    body_scroll_height: float = 0.0

    has_horizontal_scroll: bool = False

    # Orientation-specific page-level signals
    body_overflow_x: str = "visible"   # computed style of document.body
    body_transform: str = "none"        # CSS transform on document.body
    screen_orientation: str = "unknown" # screen.orientation.type from browser

    elements: List[ElementSnapshot] = Field(default_factory=list)

    # Raw page-level data collected by JS
    raw: Dict[str, Any] = Field(default_factory=dict)


# ── Scenario snapshot ─────────────────────────────────────────────────────────


class ScenarioSnapshot(BaseModel):
    """Paired baseline + scenario snapshots for diff-based analysis."""

    scenario: str
    baseline: Optional[PageSnapshot] = None
    modified: Optional[PageSnapshot] = None
    error: Optional[str] = None


# ── Focus traversal ───────────────────────────────────────────────────────────


class FocusStep(BaseModel):
    """One step in keyboard-Tab focus traversal."""

    step_index: int
    tag: str = ""
    element_id: Optional[str] = None
    selector: str = ""
    html_snippet: str = ""
    page_url: str = ""

    rect: Rect = Field(default_factory=Rect.empty)

    # Overlay detection
    covering_elements: List[Dict[str, Any]] = Field(default_factory=list)
    fully_obscured: bool = False
    partially_obscured: bool = False
    obscuration_ratio: float = 0.0  # 0.0 – 1.0


# ── Hover/focus interaction ───────────────────────────────────────────────────


class HoverInteractionResult(BaseModel):
    """Result of hovering or focusing a candidate trigger element."""

    trigger_tag: str = ""
    trigger_id: Optional[str] = None
    trigger_html: str = ""
    page_url: str = ""

    popup_appeared: bool = False
    popup_html: str = ""
    popup_rect: Optional[Rect] = None

    # Behaviour checks
    dismissible_by_escape: Optional[bool] = None  # None = not tested
    pointer_can_move_over: Optional[bool] = None
    persists_until_removed: Optional[bool] = None

    # Certainty
    certain: bool = False


# ── Rule audit record ─────────────────────────────────────────────────────────


class RuleAuditRecord(BaseModel):
    """
    Normalised output from a single evaluator check.
    Matches the auditor contract expected by combined.py converters:
      <rule_key>_status    = "FAILED" | "PASSED" | "NEEDS_REVIEW" | "N/A"
      <rule_key>_violation = human-readable reason
      html_snippet, element_id, tag
    """

    rule_key: str  # e.g. "wcag_1_4_4"
    status: str = "N/A"  # FAILED | PASSED | NEEDS_REVIEW | N/A
    violation: str = ""
    html_snippet: str = ""
    element_id: Optional[str] = None
    selector: Optional[str] = None
    tag: str = ""
    page_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict matching the combined.py converter contract."""
        return {
            f"{self.rule_key}_status": self.status,
            f"{self.rule_key}_violation": self.violation,
            "html_snippet": self.html_snippet,
            "element_id": self.element_id,
            "selector": self.selector,
            "tag": self.tag,
            "page_url": self.page_url,
        }
