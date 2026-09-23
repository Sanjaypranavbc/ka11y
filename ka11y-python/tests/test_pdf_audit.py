"""WCAG PDF techniques on linked PDF documents (Phase 3 WP-10)."""

import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import NameObject, TextStringObject

from ka11y.accessibility.rules.documents.pdf_audit import (
    audit_linked_pdfs,
    audit_pdf_bytes,
    discover_pdf_links,
    evaluate_pdf,
    inspect_pdf,
)


def _pdf(pages=1, title=None, lang=None, outline=False):
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    if title:
        w.add_metadata({"/Title": title})
    if lang:
        w._root_object[NameObject("/Lang")] = TextStringObject(lang)
    if outline:
        w.add_outline_item("Start", 0)
    buf = io.BytesIO(); w.write(buf)
    return buf.getvalue()


def _facts(**over):
    base = dict(pages=1, encrypted=False, title="", display_doc_title=False, lang="", marked=False, has_struct_tree=False,
                has_outlines=False, has_page_labels=False, text="", text_len=0, scanned_pages=0, link_annots=0, link_annots_untagged=0,
                link_annots_no_contents=0, pages_with_annots=0, pages_with_tabs=0, pagination_pages=0, widget_annots=0,
                struct=dict(nodes=0, types={}, figures=0, figures_no_alt=0, tables=0, tables_no_rows=0, tables_no_th=0, link_tags=0,
                            link_tags_no_alt=0, headings=0, lists=0, lang_elems=0, expansions=0),
                form=dict(count=0, no_tu=0, no_ft=0, required=0, required_unmarked=0, validation=0, submit=False, names=[]))
    base.update(over)
    return base


def _v(verdicts, t):
    return next(x for x in verdicts if x["technique"] == t)


def test_inspect_reads_metadata_language_and_outlines():
    f = inspect_pdf(_pdf(pages=7, title="Annual report", lang="en-GB", outline=True))
    assert f["pages"] == 7 and f["title"] == "Annual report" and f["lang"] == "en-GB" and f["has_outlines"] is True
    assert f["marked"] is False and f["has_struct_tree"] is False


def test_untagged_pdf_fails_every_structure_technique():
    v = evaluate_pdf(inspect_pdf(_pdf(pages=2)))
    for t in ("PDF1", "PDF6", "PDF9", "PDF11", "PDF21", "PDF3"):
        assert _v(v, t)["status"] == "fail" and "not tagged" in _v(v, t)["reason"]
    assert _v(v, "PDF18")["status"] == "fail" and _v(v, "PDF16")["status"] == "fail"


def test_long_untitled_document_without_bookmarks_fails_pdf2():
    v = evaluate_pdf(inspect_pdf(_pdf(pages=8)))
    assert _v(v, "PDF2")["status"] == "fail"
    v2 = evaluate_pdf(inspect_pdf(_pdf(pages=8, outline=True)))
    assert _v(v2, "PDF2")["status"] == "pass"


def test_tagged_facts_with_figures_and_tables():
    st = dict(nodes=50, types={}, figures=3, figures_no_alt=1, tables=2, tables_no_rows=0, tables_no_th=1, link_tags=2,
              link_tags_no_alt=2, headings=4, lists=1, lang_elems=0, expansions=0)
    v = evaluate_pdf(_facts(pages=4, marked=True, has_struct_tree=True, struct=st, title="T", display_doc_title=True, lang="en",
                            link_annots=2, link_annots_untagged=0, link_annots_no_contents=2, pages_with_annots=1, pages_with_tabs=0))
    assert _v(v, "PDF1")["status"] == "fail" and "1 of 3" in _v(v, "PDF1")["reason"]
    assert _v(v, "PDF6")["status"] == "needs_review"
    assert _v(v, "PDF9")["status"] == "pass" and _v(v, "PDF21")["status"] == "pass"
    assert _v(v, "PDF11")["status"] == "pass" and _v(v, "PDF13")["status"] == "needs_review"
    assert _v(v, "PDF3")["status"] == "fail"
    assert _v(v, "PDF18")["status"] == "pass"


def test_scanned_pages_and_bullets_and_forms():
    st = dict(nodes=5, types={}, figures=0, figures_no_alt=0, tables=0, tables_no_rows=0, tables_no_th=0, link_tags=0,
              link_tags_no_alt=0, headings=1, lists=0, lang_elems=0, expansions=0)
    text = "Intro\n• one\n• two\n• three\nName: ______ Date: ______ Signature: ______"
    v = evaluate_pdf(_facts(pages=2, marked=True, has_struct_tree=True, struct=st, text=text, text_len=len(text), scanned_pages=1))
    assert _v(v, "PDF7")["status"] == "fail" and _v(v, "PDF21")["status"] == "fail" and _v(v, "PDF23")["status"] == "fail"
    form = dict(count=3, no_tu=1, no_ft=0, required=2, required_unmarked=1, validation=1, submit=False, names=["a", "b", "c"])
    v2 = evaluate_pdf(_facts(marked=True, has_struct_tree=True, struct=st, form=form))
    assert _v(v2, "PDF10")["status"] == "fail" and _v(v2, "PDF12")["status"] == "pass"
    assert _v(v2, "PDF5")["status"] == "needs_review" and _v(v2, "PDF15")["status"] == "needs_review" and _v(v2, "PDF22")["status"] == "needs_review"
    assert _v(v2, "PDF23")["status"] == "pass"


def test_language_mismatch_flags_pdf16():
    de = "Der die und das ist nicht mit ein eine den " * 10
    v = evaluate_pdf(_facts(lang="en", text=de, text_len=len(de)))
    assert _v(v, "PDF16")["status"] == "needs_review"


def test_findings_carry_sc_and_rule_ids():
    fs = audit_pdf_bytes(_pdf(pages=1, title="x"), "https://ex.com/a.pdf", "https://ex.com/")
    ids = {f["rule_id"] for f in fs}
    assert "python_pdf_pdf18" in ids and "python_pdf_pdf1" in ids
    f18 = next(f for f in fs if f["rule_id"] == "python_pdf_pdf18")
    assert f18["wcag_sc"] == "2.4.2" and f18["element"]["page_url"] == "https://ex.com/"


def test_discovery_and_end_to_end(tmp_path):
    html = '<a href="/docs/guide.PDF">Guide</a><a href="https://other.com/x.pdf">ext</a><a href="/docs/guide.PDF#p2">dup</a>'
    p = tmp_path / "p.html"; p.write_text(html, encoding="utf-8")
    snaps = {"https://ex.com/": str(p)}
    links = discover_pdf_links(snaps, "https://ex.com/")
    assert len(links) == 2 and links[0][0] == "https://ex.com/docs/guide.PDF"
    data = _pdf(pages=1, title="Guide", lang="en")
    fs = audit_linked_pdfs(snaps, "https://ex.com/", fetch=lambda u: data if u.endswith("guide.PDF") else None)
    assert fs and all(f["element"]["html"].startswith('<a href="https://ex.com/docs/guide.PDF') for f in fs)
