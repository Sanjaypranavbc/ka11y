from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SectionType(str, Enum):
    HEADER = "header"
    FOOTER = "footer"
    NAVIGATION = "navigation"
    MAIN_CONTENT = "main_content"
    FORM_REGION = "form_region"
    DATA_TABLE = "data_table"
    ARTICLE_CARD = "article_card"
    MODAL_DIALOG = "modal_dialog"
    HERO = "hero"
    MEDIA_CARD = "media_card"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class VerdictStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"


class AccessibleNameSource(str, Enum):
    ARIA_LABEL = "aria-label"
    ARIA_LABELLEDBY = "aria-labelledby"
    NATIVE_LABEL = "native_label"
    ALT_ATTRIBUTE = "alt_attribute"
    TEXT_CONTENT = "text_content"
    TITLE_ATTRIBUTE = "title_attribute"
    NONE = "none"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


class AccessibleName(BaseModel):
    name: str
    source: AccessibleNameSource
    is_visible: bool


class VisualContext(BaseModel):
    is_visible: bool
    opacity: float = 1.0
    bounding_box: BoundingBox
    computed_styles: Dict[str, str] = Field(default_factory=dict)
    ocr_text: Optional[str] = None
    cv_classification: Optional[str] = None  # e.g., "logo", "decorative", "complex"
    background_type: str = "solid"  # "solid", "gradient", "image", "mixed"
    resolved_background_color: str = "rgb(255, 255, 255)"
    has_bg_image: bool = False
    rendered_contrast: Optional[float] = None
    is_obscured_by_floating_element: bool = False
    visible_label_text: Optional[str] = None
    src: Optional[str] = None


class SemanticContext(BaseModel):
    tag_name: str
    role: Optional[str] = None
    section_type: SectionType = SectionType.UNKNOWN
    ancestor_tags: List[str] = Field(default_factory=list)
    ancestor_roles: List[str] = Field(default_factory=list)
    parent_tags: List[str] = Field(default_factory=list)
    parent_roles: List[str] = Field(default_factory=list)
    is_required: bool = False
    is_disabled: bool = False
    controlled_by: Optional[str] = None
    controls_elements: List[str] = Field(default_factory=list)
    owns_elements: List[str] = Field(default_factory=list)
    described_by_text: Optional[str] = None
    is_in_data_table: bool = False
    # True when a data-table cell has a programmatically determinable header
    # association: it is a <th>, carries a `headers=` attribute, or its
    # row/column contains a <th>. Used by Policy 1.3.1 to distinguish a
    # genuinely associated cell from one that merely sits inside a <table>.
    has_table_header_association: bool = False
    is_in_labeled_control: bool = False
    is_video_context: bool = False


class InteractionContext(BaseModel):
    is_focusable: bool = False
    tab_index: int = -1
    effective_clickable_bbox: Optional[BoundingBox] = None
    adjacent_spacing_px: float = 0.0
    has_focus_ring: bool = False
    focus_ring_thickness_px: float = 0.0
    focus_ring_contrast: Optional[float] = None
    clickable_area_px: float = 0.0


class ElementContext(BaseModel):
    element_id: str
    xpath: Optional[str] = None
    html_snippet: str
    semantics: SemanticContext
    visual: VisualContext
    interaction: InteractionContext
    accessible_name: Optional[AccessibleName] = None


class RuleVerdict(BaseModel):
    rule_id: str
    wcag_sc: str
    status: VerdictStatus
    confidence: float
    reason_code: str
    human_reason: str
    reason_params: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    element: ElementContext
