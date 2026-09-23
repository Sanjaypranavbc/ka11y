"""Site-level (cross-page) checks: G61, G197, G127, G185/G125/G126, H30/G91."""

from pathlib import Path

import pytest

from ka11y.api.v1.combined.site_analysis import analyze_site, extract_page_facts


def _page(title, nav_links, body_links="", extra=""):
    nav = "".join(f'<a href="{h}">{t}</a>' for h, t in nav_links)
    return (f"<html><head><title>{title}</title></head><body>"
            f'<nav aria-label="Main">{nav}</nav><main><h1>{title.split(" - ")[0]}</h1>{body_links}{extra}</main></body></html>')


@pytest.fixture
def site(tmp_path: Path):
    root = "https://example.com/"
    home = _page("Home - Acme", [("/", "Home"), ("/about", "About"), ("/contact", "Contact")],
                 '<a href="/about">About us</a><a href="/contact">Contact</a>')
    about = _page("About - Acme", [("/", "Home"), ("/about", "About"), ("/contact", "Contact")])
    contact = _page("Contact - Acme", [("/", "Home"), ("/contact", "Contact"), ("/about", "About")],
                    '<a href="/about">Our story</a>')
    snaps = {}
    for name, url, html in [("home", root, home), ("about", root + "about", about), ("contact", root + "contact", contact)]:
        f = tmp_path / f"{name}.html"; f.write_text(html, encoding="utf-8"); snaps[url] = str(f)
    return root, snaps


def _by_rule(findings, rule):
    return [f for f in findings if f["rule_id"] == rule]


def test_extract_page_facts_reads_title_nav_and_links():
    facts = extract_page_facts(_page("Home - Acme", [("/a", "A"), ("/b", "B")]), "https://example.com/")
    assert facts["title"] == "Home - Acme"
    assert facts["navs"][0]["label"] == "main"
    assert len(facts["navs"][0]["links"]) == 2


def test_inconsistent_nav_order_fails_g61(site):
    root, snaps = site
    f = _by_rule(analyze_site(snaps, root), "python_3_2_3_consistent_navigation")
    assert f and f[0]["status"] == "fail"
    assert f[0]["wcag_sc"] == "3.2.3"
    assert "contact" in f[0]["element"]["page_url"]


def test_inconsistent_link_names_flag_g197(site):
    root, snaps = site
    f = _by_rule(analyze_site(snaps, root), "python_3_2_4_consistent_identification")
    assert f and f[0]["status"] == "needs_review"
    assert "about" in f[0]["reason"].lower()


def test_site_name_in_titles_passes_g127(site):
    root, snaps = site
    f = _by_rule(analyze_site(snaps, root), "python_2_4_2_site_name_in_title")
    assert f and f[0]["status"] == "pass"
    assert "acme" in f[0]["reason"].lower()


def test_multiple_ways_credit_home_links_g185(site):
    root, snaps = site
    f = _by_rule(analyze_site(snaps, root), "python_2_4_5_multiple_ways_site")
    assert f and f[0]["status"] == "pass"
    assert "G185" in f[0]["reason"] or "G125" in f[0]["reason"]


def test_single_page_returns_nothing(tmp_path: Path):
    f = tmp_path / "p.html"; f.write_text("<title>x</title>", encoding="utf-8")
    assert analyze_site({"https://example.com/": str(f)}, "https://example.com/") == []


def test_link_text_unrelated_to_destination_h30(tmp_path: Path):
    root = "https://example.com/"
    a = _page("Pricing plans - Acme", [("/", "Home"), ("/pricing", "Pricing")], '<a href="/pricing">Bananas</a>')
    b = _page("Home - Acme", [("/", "Home"), ("/pricing", "Pricing")])
    snaps = {}
    for name, url, html in [("a", root, a), ("b", root + "pricing", b)]:
        fp = tmp_path / f"{name}.html"; fp.write_text(html, encoding="utf-8"); snaps[url] = str(fp)
    # the "pricing" page title is "Home - Acme" here; link "Bananas" → /pricing shares no words
    f = _by_rule(analyze_site(snaps, root), "python_2_4_4_link_text_vs_destination")
    assert f and any("Bananas" in x["reason"] for x in f)
