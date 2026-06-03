from __future__ import annotations

from pydantic import BaseModel


class _Image(BaseModel):
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
    from a11y.utils.crawler_settings import select_ocr_candidate_paths

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
    from a11y.utils.crawler_settings import select_ocr_candidate_paths

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


class _PagedImage(BaseModel):
    screenshot_path: str
    url: str = ""
    classification: str = "informative"
    sub_type: str = ""
    is_button: bool = False
    is_text_image: bool = False
    is_complex: bool = False
    is_decorative: bool = False
    is_logo: bool = False
    src: str = ""


def test_select_ocr_fair_per_page_distributes_budget_across_pages():
    """With fair_per_page, a small budget must be spread across pages, not
    monopolised by one page — the multi-page coverage fix."""
    from a11y.utils.crawler_settings import select_ocr_candidate_paths

    images = []
    # Page A has 10 images, page B has 10 images. Same priority (informative).
    for i in range(10):
        images.append(_PagedImage(screenshot_path=f"/a/{i}.png", url="https://x.com/a", src=f"a{i}"))
    for i in range(10):
        images.append(_PagedImage(screenshot_path=f"/b/{i}.png", url="https://x.com/b", src=f"b{i}"))

    # Legacy (unfair): the first page monopolises a small budget.
    legacy_sel, _ = select_ocr_candidate_paths(images, limit=6)
    legacy_pages = {("/a/" in p) for p in legacy_sel}

    # Fair: budget split ~evenly between the two pages.
    fair_sel, fair_skip = select_ocr_candidate_paths(images, limit=6, fair_per_page=True)
    a_count = sum(1 for p in fair_sel if "/a/" in p)
    b_count = sum(1 for p in fair_sel if "/b/" in p)
    assert len(fair_sel) == 6
    assert a_count == 3 and b_count == 3, f"expected even split, got a={a_count} b={b_count}"
    assert len(fair_skip) == 14
