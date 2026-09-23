"""Context-driven WCAG 1.1.1 techniques: ARIA10, G82, G196, C9, G73/G74/G95."""

from ka11y.accessibility.rules.non_text.alttext import (
    AltTextAccessibilityAuditor,
    _context_techniques,
    _image_context,
    _src_stem,
)
from ka11y.crawler.models import ImageData


def make_image(**kwargs) -> ImageData:
    d = dict(url="https://example.com", src="https://example.com/img/hero-banner.png", alt_text="",
             classification="informative", screenshot_path="/tmp/img.png", filename="img.png")
    d.update(kwargs)
    return ImageData(**d)


def test_src_stem_normalises_file_names():
    assert _src_stem("https://x.com/img/Hero_Banner-2.png?v=1") == "hero banner 2"


def test_aria10_unresolved_labelledby_fails():
    ok, reason, code = _context_techniques(make_image(labelledby_unresolved=True, alt_text="x"), "x", [], False)
    assert ok is False and code == "labelledby_unresolved" and "ARIA10" in reason


def test_g82_filename_alt_in_sole_link_fails():
    img = make_image(in_link=True, link_sole_content=True, alt_text="hero-banner.png")
    ok, _, code = _context_techniques(img, "hero-banner.png", [], False)
    assert ok is False and code == "filename_alt"
    img2 = make_image(in_link=True, link_sole_content=True, alt_text="hero banner")
    ok2, _, code2 = _context_techniques(img2, "hero banner", [], False)
    assert ok2 is False and code2 == "filename_alt"


def test_g82_descriptive_alt_in_sole_link_passes_through():
    img = make_image(in_link=True, link_sole_content=True, alt_text="Open the pricing page")
    assert _context_techniques(img, "Open the pricing page", [], False) is None


def test_g196_group_sibling_alt_passes_empty_alt():
    img = make_image(group_size=4, group_alt_sibling=True, alt_text="", classification="decorative")
    ok, reason, code = _context_techniques(img, "", [], False)
    assert ok is True and code == "group_alt" and "G196" in reason


def test_c9_background_image_with_text_needs_review():
    img = make_image(element_type="css_background_image", has_own_text_content=False, alt_text="")
    ok, reason, code = _context_techniques(img, "", ["Summer Sale", "50% off"], True)
    assert ok is None and code == "background_image_text" and "C9" in reason


def test_no_context_signal_returns_none():
    assert _context_techniques(make_image(alt_text="A cat"), "A cat", [], False) is None


def test_image_context_collects_surroundings():
    img = make_image(nearby_heading_text="Quarterly results", figcaption_text="Figure 1", in_link=True, link_href="https://example.com/x")
    ctx = _image_context(img)
    assert ctx == {"heading": "Quarterly results", "caption": "Figure 1", "link_href": "https://example.com/x"}


def test_complex_image_credits_adjacent_description_link_g73(tmp_path):
    img = make_image(classification="complex", is_complex=True, alt_text="Sales by region chart",
                     description_link_text="View data table")
    recs = AltTextAccessibilityAuditor().generate_audit_report([img], [], str(tmp_path))
    assert recs[0]["wcag_1_1_1_status"] == "PASSED" and "G73" in recs[0]["wcag_1_1_1_reason"]
    assert recs[0]["image_context"]["description_link"] == "View data table"


def test_complex_image_credits_referenced_prose_g74(tmp_path):
    img = make_image(classification="complex", is_complex=True, alt_text="Chart described below",
                     alt_refers_nearby=True, nearby_text_length=450)
    recs = AltTextAccessibilityAuditor().generate_audit_report([img], [], str(tmp_path))
    assert recs[0]["wcag_1_1_1_status"] == "PASSED" and "G74" in recs[0]["wcag_1_1_1_reason"]


def test_informative_chart_reclassified_as_complex_g95(tmp_path):
    img = make_image(classification="informative", alt_text="Revenue chart", src="https://example.com/revenue-chart.png")
    recs = AltTextAccessibilityAuditor().generate_audit_report([img], [], str(tmp_path))
    assert recs[0]["classification"] == "complex"
    assert recs[0]["wcag_1_1_1_status"] == "INCOMPLETE"
