from typing import List
from ..models import SectionType

class SectionAnalyzer:
    """
    Evaluates the DOM ancestry of an element to determine its macro-context.
    Relies on native HTML5 semantics and ARIA landmarks.
    """

    # Mapping of native tags and ARIA roles to our strict SectionType enum
    _LANDMARK_MAP = {
        "header": SectionType.HEADER,
        "banner": SectionType.HEADER,
        "footer": SectionType.FOOTER,
        "contentinfo": SectionType.FOOTER,
        "nav": SectionType.NAVIGATION,
        "navigation": SectionType.NAVIGATION,
        "main": SectionType.MAIN_CONTENT,
        "form": SectionType.FORM_REGION,
        "search": SectionType.FORM_REGION,
        "table": SectionType.DATA_TABLE,
        "grid": SectionType.DATA_TABLE,
        "dialog": SectionType.MODAL_DIALOG,
        "alertdialog": SectionType.MODAL_DIALOG,
        "article": SectionType.ARTICLE_CARD,
    }

    @classmethod
    def analyze(cls, ancestor_tags: List[str], ancestor_roles: List[str]) -> SectionType:
        """
        Takes an ordered list of ancestors (closest to furthest) and returns
        the most specific semantic section type.
        """
        # Walk up the tree. The first matching landmark defines the immediate section.
        for tag, role in zip(ancestor_tags, ancestor_roles):
            # Check role first as it is more specific
            if role:
                r = role.lower()
                if r in cls._LANDMARK_MAP:
                    return cls._LANDMARK_MAP[r]
            
            if tag:
                t = tag.lower()
                if t in cls._LANDMARK_MAP:
                    return cls._LANDMARK_MAP[t]

        return SectionType.UNKNOWN
