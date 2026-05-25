"""
Tests for the W3C accname-1.2 priority resolver in
``element_context_extractor._resolve_accessible_name``.

Sprint-1 fix #5: the previous order was aria-label → alt → title →
text-content, which violates accname-1.2 (no aria-labelledby, no native
<label for> for form controls, title above text-content).
"""
from ka11y.accessibility.pipeline.models import AccessibleNameSource
from ka11y.accessibility.pipeline.extractors.element_context_extractor import (
    _resolve_accessible_name,
)


def _payload(**overrides):
    base = {
        "tag_name": "button",
        "html_snippet": "<button></button>",
        "raw_aria_label": None,
        "raw_aria_labelledby": None,
        "raw_alt": None,
        "raw_title": None,
        "text_content": "",
        "visible_label_text": None,
    }
    base.update(overrides)
    return base


# ── Priority order ──────────────────────────────────────────────────────────


def test_aria_labelledby_wins_over_aria_label():
    name = _resolve_accessible_name(
        _payload(raw_aria_labelledby="Submit form", raw_aria_label="ignored")
    )
    assert name.source == AccessibleNameSource.ARIA_LABELLEDBY
    assert name.name == "Submit form"


def test_aria_label_wins_over_native_label():
    name = _resolve_accessible_name(
        _payload(
            tag_name="input",
            html_snippet='<input type="text">',
            raw_aria_label="Search",
            visible_label_text="Query",
        )
    )
    assert name.source == AccessibleNameSource.ARIA_LABEL
    assert name.name == "Search"


def test_native_label_used_for_form_controls_when_no_aria():
    name = _resolve_accessible_name(
        _payload(
            tag_name="input",
            html_snippet='<input type="text">',
            visible_label_text="Email",
            raw_title="ignored",
        )
    )
    assert name.source == AccessibleNameSource.NATIVE_LABEL
    assert name.name == "Email"


def test_native_label_not_used_for_non_form_controls():
    # An <a> with a sibling label-shaped element shouldn't pick up
    # visible_label_text; only inputs/selects/textareas do.
    name = _resolve_accessible_name(
        _payload(
            tag_name="a",
            html_snippet="<a>Continue</a>",
            text_content="Continue",
            visible_label_text="ignored-for-a",
        )
    )
    assert name.source == AccessibleNameSource.TEXT_CONTENT
    assert name.name == "Continue"


def test_alt_used_for_img_when_no_aria_or_label():
    name = _resolve_accessible_name(
        _payload(
            tag_name="img",
            html_snippet='<img src="x.png" alt="Logo">',
            raw_alt="Logo",
            raw_title="ignored",
        )
    )
    assert name.source == AccessibleNameSource.ALT_ATTRIBUTE
    assert name.name == "Logo"


def test_alt_used_for_input_type_image():
    name = _resolve_accessible_name(
        _payload(
            tag_name="input",
            html_snippet='<input type="image" alt="Submit">',
            raw_alt="Submit",
        )
    )
    assert name.source == AccessibleNameSource.ALT_ATTRIBUTE


def test_alt_ignored_for_plain_text_input():
    # <input type="text" alt=...> is invalid HTML and not an accessible name.
    name = _resolve_accessible_name(
        _payload(
            tag_name="input",
            html_snippet='<input type="text">',
            raw_alt="wrongly-set-alt",
        )
    )
    # Falls through — no other source available.
    assert name is None


def test_text_content_beats_title():
    name = _resolve_accessible_name(
        _payload(
            tag_name="button",
            html_snippet="<button>Save</button>",
            text_content="Save",
            raw_title="Tooltip",
        )
    )
    assert name.source == AccessibleNameSource.TEXT_CONTENT


def test_title_used_only_as_last_resort():
    name = _resolve_accessible_name(
        _payload(
            tag_name="a",
            html_snippet='<a href="/x"></a>',
            raw_title="Last resort",
        )
    )
    assert name.source == AccessibleNameSource.TITLE_ATTRIBUTE


def test_no_sources_returns_none():
    name = _resolve_accessible_name(_payload())
    assert name is None


def test_empty_aria_label_does_not_count():
    name = _resolve_accessible_name(_payload(raw_aria_label="", raw_title="kept"))
    assert name.source == AccessibleNameSource.TITLE_ATTRIBUTE


def test_decorative_image_alt_empty_preserved():
    # alt="" is *present and empty* — accname-1.2 distinguishes this from
    # "alt missing". We preserve the empty string so policy_1_1_1 can decide.
    name = _resolve_accessible_name(
        _payload(
            tag_name="img",
            html_snippet='<img src="x.png" alt="">',
            raw_alt="",
        )
    )
    assert name is not None
    assert name.source == AccessibleNameSource.ALT_ATTRIBUTE
    assert name.name == ""
