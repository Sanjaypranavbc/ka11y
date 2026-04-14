from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Image:
    screenshot_path: str
    classification: str = ""
    sub_type: str = ""
    is_button: bool = False
    is_text_image: bool = False
    is_complex: bool = False
    is_decorative: bool = False
    is_logo: bool = False
    src: str = ""


def test_select_ocr_candidate_paths_dedupes_duplicate_decorative_assets_by_src():
    from ka11y.utils.crawler_settings import select_ocr_candidate_paths

    images = [
        _Image(
            screenshot_path="/tmp/hero-a.png",
            classification="decorative",
            is_decorative=True,
            src="https://example.com/hero.png",
        ),
        _Image(
            screenshot_path="/tmp/hero-b.png",
            classification="decorative",
            is_decorative=True,
            src="https://example.com/hero.png",
        ),
        _Image(
            screenshot_path="/tmp/button.png",
            classification="functional",
            sub_type="buttons",
            is_button=True,
            src="https://example.com/button.png",
        ),
    ]

    selected, skipped = select_ocr_candidate_paths(images, limit=10)

    assert "/tmp/button.png" in selected
    assert len([path for path in selected if "hero-" in path]) == 1
    assert skipped == []


def test_select_ocr_candidate_paths_keeps_distinct_functional_contexts():
    from ka11y.utils.crawler_settings import select_ocr_candidate_paths

    images = [
        _Image(
            screenshot_path="/tmp/button-a.png",
            classification="functional",
            sub_type="buttons",
            is_button=True,
            src="https://example.com/shared-icon.svg",
        ),
        _Image(
            screenshot_path="/tmp/button-b.png",
            classification="functional",
            sub_type="buttons",
            is_button=True,
            src="https://example.com/shared-icon.svg",
        ),
    ]

    selected, skipped = select_ocr_candidate_paths(images, limit=10)

    assert selected == ["/tmp/button-a.png", "/tmp/button-b.png"]
    assert skipped == []
