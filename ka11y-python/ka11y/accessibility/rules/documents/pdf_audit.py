"""
ka11y/accessibility/rules/documents/pdf_audit.py
=================================================
WCAG PDF techniques for PDF documents linked from crawled pages (Phase 3, WP-10).

Discovery: every ``<a href="…pdf">`` in the rendered HTML snapshots (same site as
the audited page, deduplicated, capped). Each document is downloaded once
(public hosts only, size cap) and inspected with ``pypdf``.

Techniques (rule ids are ``python_pdf_<technique>``, one finding per technique
per document):

  PDF18 title metadata + DisplayDocTitle     PDF16 catalog /Lang
  PDF2  outlines (bookmarks)                 PDF17 page labels
  PDF14 pagination artifacts (headers/footers)
  PDF7  scanned pages without a text layer
  PDF1 / PDF4 figures need /Alt or /ActualText (or be artifacts)
  PDF6  table structure (Table > TR > TH/TD) PDF9  heading tags
  PDF21 list structure for bullet/number text PDF11 / PDF13 link annotations + Link tags with text/Alt
  PDF3  tab order (/Tabs /S) and structure order
  PDF19 /Lang on passages in another language PDF8 /E expansions for abbreviations
  PDF10 / PDF12 form field labels (/TU) and name/role/value (/T /FT /V)
  PDF5  required fields indicated            PDF15 submit action
  PDF22 field validation scripts (review)    PDF23 flattened forms

An untagged PDF (no /MarkInfo /Marked or no /StructTreeRoot) fails every
structure technique at once with a single explanation.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="pdf-audit")

_MAX_PDFS = 5
_MAX_BYTES = 15_000_000
_TIMEOUT_S = 15.0
_MAX_STRUCT_NODES = 20000
_BCP47_RE = re.compile(r"^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{1,8})*$")
_BULLET_LINE_RE = re.compile(r"^\s*(?:[•·●○■□▪‣◦\-–—*]|\(?\d{1,2}[.)]|[a-z][.)])\s+\S", re.M)
_BLANK_RE = re.compile(r"_{4,}|\[\s*\]|☐")
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,5}\b")

# technique → (primary SC, description)
_TECH: Dict[str, Tuple[str, str]] = {
    "PDF18": ("2.4.2", "document title"),
    "PDF16": ("3.1.1", "document language"),
    "PDF2": ("2.4.5", "bookmarks"),
    "PDF17": ("2.4.8", "page labels"),
    "PDF14": ("2.4.8", "running headers/footers"),
    "PDF7": ("1.4.5", "text layer"),
    "PDF1": ("1.1.1", "figure alternatives"),
    "PDF4": ("1.1.1", "decorative figures as artifacts"),
    "PDF6": ("1.3.1", "table structure"),
    "PDF9": ("1.3.1", "headings"),
    "PDF21": ("1.3.1", "lists"),
    "PDF11": ("2.4.4", "link tags"),
    "PDF13": ("2.4.4", "link text / Alt"),
    "PDF3": ("2.4.3", "tab and reading order"),
    "PDF19": ("3.1.2", "language of passages"),
    "PDF8": ("3.1.4", "abbreviation expansions"),
    "PDF10": ("3.3.2", "form field labels"),
    "PDF12": ("4.1.2", "form field name/role/value"),
    "PDF5": ("3.3.2", "required fields"),
    "PDF15": ("3.2.2", "submit button"),
    "PDF22": ("3.3.1", "field validation"),
    "PDF23": ("2.1.1", "interactive form fields"),
}
_STRUCTURE_TECHS = ("PDF1", "PDF4", "PDF6", "PDF9", "PDF21", "PDF11", "PDF13", "PDF3", "PDF19", "PDF8")


# ── discovery / download ─────────────────────────────────────────────────────

def discover_pdf_links(html_snapshots: Dict[str, str], root_url: str, *, limit: int = _MAX_PDFS) -> List[Tuple[str, str]]:
    """Return ``[(pdf_url, linking_page_url)]`` for same-site PDF links in the snapshots."""
    from ka11y.utils.html_soup import make_soup

    root_host = (urlsplit(root_url).netloc or "").lower().lstrip("www.")
    out: List[Tuple[str, str]] = []
    seen: set = set()
    for page_url, path in list(html_snapshots.items())[:60]:
        try:
            soup = make_soup(Path(path).read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            url = urljoin(page_url, href)
            base = url.split("#")[0].split("?")[0]
            if not base.lower().endswith(".pdf"):
                continue
            host = (urlsplit(url).netloc or "").lower().lstrip("www.")
            if host != root_host or url in seen:
                continue
            seen.add(url)
            out.append((url, page_url))
            if len(out) >= limit:
                return out
    return out


def fetch_pdf(url: str, *, timeout: float = _TIMEOUT_S, max_bytes: int = _MAX_BYTES) -> Optional[bytes]:
    try:
        from ka11y.crawler._ssrf_guard import _host_is_blocked

        host = urlsplit(url).hostname or ""
        if not host or _host_is_blocked(host):
            return None
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": "ka11y-audit/1.0"}) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return None
                buf = bytearray()
                for chunk in resp.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        return None
        return bytes(buf) if buf[:5] == b"%PDF-" else None
    except Exception:
        return None


# ── inspection ───────────────────────────────────────────────────────────────

def _obj(x):
    try:
        return x.get_object()
    except Exception:
        return x


def _name(x) -> str:
    try:
        return str(_obj(x))
    except Exception:
        return ""


def _walk_struct(root, stats: Dict[str, Any], rolemap: Dict[str, str]) -> None:
    """Depth-first walk of the structure tree collecting element facts."""
    stack = [(root, 0)]
    while stack and stats["nodes"] < _MAX_STRUCT_NODES:
        node, depth = stack.pop()
        node = _obj(node)
        if isinstance(node, list):
            for k in node:
                stack.append((k, depth))
            continue
        if not isinstance(node, dict):
            continue
        stats["nodes"] += 1
        s = _name(node.get("/S")) if "/S" in node else ""
        s = rolemap.get(s, s)
        if s:
            stats["types"][s] += 1
            if s in ("/Figure", "/Formula"):
                alt = str(_obj(node.get("/Alt")) or "").strip() if "/Alt" in node else ""
                actual = str(_obj(node.get("/ActualText")) or "").strip() if "/ActualText" in node else ""
                if not alt and not actual:
                    stats["figures_no_alt"] += 1
                stats["figures"] += 1
            if s == "/Table":
                kids = _obj(node.get("/K"))
                kid_types = Counter()
                for k in (kids if isinstance(kids, list) else [kids]):
                    k = _obj(k)
                    if isinstance(k, dict):
                        kt = rolemap.get(_name(k.get("/S")), _name(k.get("/S")))
                        kid_types[kt] += 1
                        if kt in ("/TR", "/THead", "/TBody", "/TFoot"):
                            rows = _obj(k.get("/K"))
                            for r in (rows if isinstance(rows, list) else [rows]):
                                r = _obj(r)
                                if isinstance(r, dict):
                                    rt = rolemap.get(_name(r.get("/S")), _name(r.get("/S")))
                                    kid_types[rt] += 1
                                    if rt == "/TR":
                                        cells = _obj(r.get("/K"))
                                        for c in (cells if isinstance(cells, list) else [cells]):
                                            c = _obj(c)
                                            if isinstance(c, dict):
                                                kid_types[rolemap.get(_name(c.get("/S")), _name(c.get("/S")))] += 1
                stats["tables"] += 1
                if not kid_types.get("/TR"):
                    stats["tables_no_rows"] += 1
                elif not kid_types.get("/TH"):
                    stats["tables_no_th"] += 1
            if s == "/Link":
                stats["link_tags"] += 1
                if "/Alt" not in node:
                    stats["link_tags_no_alt"] += 1
            if s.startswith("/H") and (s == "/H" or s[2:].isdigit()):
                stats["headings"] += 1
            if s == "/L":
                stats["lists"] += 1
            if "/Lang" in node:
                stats["lang_elems"] += 1
            if "/E" in node:
                stats["expansions"] += 1
        if "/K" in node:
            stack.append((node.get("/K"), depth + 1))


def inspect_pdf(data: bytes) -> Dict[str, Any]:
    """Return raw facts about the document (no verdicts)."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    root = _obj(reader.trailer["/Root"])
    facts: Dict[str, Any] = {"pages": len(reader.pages), "encrypted": bool(reader.is_encrypted)}
    meta = None
    try:
        meta = reader.metadata
    except Exception:
        pass
    title = ""
    try:
        title = (meta.title or "") if meta else ""
    except Exception:
        title = ""
    if not title:
        try:
            xmp = reader.xmp_metadata
            dc = getattr(xmp, "dc_title", None) or {}
            title = next(iter(dc.values()), "") if isinstance(dc, dict) else ""
        except Exception:
            pass
    facts["title"] = str(title or "").strip()
    vp = _obj(root.get("/ViewerPreferences")) if "/ViewerPreferences" in root else None
    facts["display_doc_title"] = bool(vp and _obj(vp.get("/DisplayDocTitle")) is True)
    facts["lang"] = str(_obj(root.get("/Lang")) or "").strip() if "/Lang" in root else ""
    mi = _obj(root.get("/MarkInfo")) if "/MarkInfo" in root else None
    facts["marked"] = bool(mi and _obj(mi.get("/Marked")) is True)
    st = _obj(root.get("/StructTreeRoot")) if "/StructTreeRoot" in root else None
    facts["has_struct_tree"] = bool(st)
    outlines = _obj(root.get("/Outlines")) if "/Outlines" in root else None
    facts["has_outlines"] = bool(outlines and ("/First" in outlines or _obj(outlines.get("/Count")) not in (None, 0)))
    facts["has_page_labels"] = "/PageLabels" in root
    stats: Dict[str, Any] = {"nodes": 0, "types": Counter(), "figures": 0, "figures_no_alt": 0, "tables": 0, "tables_no_rows": 0,
                             "tables_no_th": 0, "link_tags": 0, "link_tags_no_alt": 0, "headings": 0, "lists": 0, "lang_elems": 0, "expansions": 0}
    if st:
        rolemap = {}
        try:
            rm = _obj(st.get("/RoleMap")) if "/RoleMap" in st else None
            if rm:
                rolemap = {str(k): _name(v) for k, v in rm.items()}
        except Exception:
            pass
        try:
            _walk_struct(st.get("/K"), stats, rolemap)
        except Exception as exc:
            logger.debug("pdf struct walk stopped: %s", exc)
    facts["struct"] = stats

    # pages: text, images, annotations, tabs, pagination artifacts
    text_all: List[str] = []
    scanned_pages = 0
    link_annots = 0
    link_annots_untagged = 0
    link_annots_no_contents = 0
    pages_with_annots = 0
    pages_with_tabs = 0
    pagination_pages = 0
    widget_annots = 0
    for i, page in enumerate(reader.pages[:200]):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text_all.append(text)
        try:
            res = _obj(page.get("/Resources")) or {}
            xo = _obj(res.get("/XObject")) if "/XObject" in res else {}
            has_image = any(_name(_obj(v).get("/Subtype")) == "/Image" for v in (xo or {}).values())
        except Exception:
            has_image = False
        if has_image and len(text.strip()) < 20:
            scanned_pages += 1
        try:
            annots = _obj(page.get("/Annots")) if "/Annots" in page else []
        except Exception:
            annots = []
        if annots:
            pages_with_annots += 1
            if "/Tabs" in page and _name(page.get("/Tabs")) == "/S":
                pages_with_tabs += 1
            for a in annots:
                a = _obj(a)
                if not isinstance(a, dict):
                    continue
                sub = _name(a.get("/Subtype"))
                if sub == "/Link":
                    link_annots += 1
                    if "/StructParent" not in a:
                        link_annots_untagged += 1
                    if "/Contents" not in a:
                        link_annots_no_contents += 1
                elif sub == "/Widget":
                    widget_annots += 1
        try:
            raw = page.get_contents()
            content = raw.get_data() if raw is not None else b""
            if b"/Pagination" in content or b"/Artifact" in content and b"/Header" in content:
                pagination_pages += 1
        except Exception:
            pass
    facts.update({
        "text": "\n".join(text_all), "text_len": sum(len(t) for t in text_all), "scanned_pages": scanned_pages,
        "link_annots": link_annots, "link_annots_untagged": link_annots_untagged, "link_annots_no_contents": link_annots_no_contents,
        "pages_with_annots": pages_with_annots, "pages_with_tabs": pages_with_tabs, "pagination_pages": pagination_pages,
        "widget_annots": widget_annots,
    })

    # forms
    fields: Dict[str, Any] = {}
    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}
    form = {"count": len(fields), "no_tu": 0, "no_ft": 0, "required": 0, "required_unmarked": 0, "validation": 0, "submit": False, "names": []}
    for name, f in list(fields.items())[:500]:
        f = _obj(f)
        if not isinstance(f, dict):
            continue
        tu = str(_obj(f.get("/TU")) or "").strip() if "/TU" in f else ""
        ft = _name(f.get("/FT")) if "/FT" in f else ""
        if not tu:
            form["no_tu"] += 1
        if not ft or "/T" not in f:
            form["no_ft"] += 1
        try:
            ff = int(_obj(f.get("/Ff")) or 0)
        except Exception:
            ff = 0
        if ff & 2:
            form["required"] += 1
            if not re.search(r"required|mandatory|\*|必須", tu + " " + str(name)):
                form["required_unmarked"] += 1
        if "/AA" in f:
            form["validation"] += 1
        a = _obj(f.get("/A")) if "/A" in f else None
        if a and _name(a.get("/S")) == "/SubmitForm":
            form["submit"] = True
        form["names"].append(str(name)[:40])
    if not form["submit"]:
        # submit buttons often live on widget annotations rather than the field dict
        for page in reader.pages[:200]:
            try:
                for a in (_obj(page.get("/Annots")) if "/Annots" in page else []):
                    a = _obj(a)
                    act = _obj(a.get("/A")) if isinstance(a, dict) and "/A" in a else None
                    if act and _name(act.get("/S")) == "/SubmitForm":
                        form["submit"] = True
                        break
            except Exception:
                pass
            if form["submit"]:
                break
    facts["form"] = form
    return facts


# ── verdicts ─────────────────────────────────────────────────────────────────

def _detect_lang(text: str) -> Optional[str]:
    """Very small stop-word language guess (en/de/fr/es/ja) for PDF16/PDF19."""
    sample = text[:20000].lower()
    if len(re.findall(r"[぀-ヿ]", sample)) > 40:
        return "ja"
    words = re.findall(r"[a-zà-ÿ']+", sample)
    if len(words) < 30:
        return None
    stop = {
        "en": {"the", "and", "of", "to", "in", "is", "that", "for", "with", "this"},
        "de": {"der", "die", "und", "das", "ist", "nicht", "mit", "ein", "eine", "den"},
        "fr": {"le", "la", "les", "des", "et", "est", "une", "pour", "dans", "que"},
        "es": {"el", "la", "los", "las", "que", "en", "un", "una", "por", "con"},
    }
    scores = {l: sum(1 for w in words if w in s) for l, s in stop.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 5 and scores[best] >= 2 * sorted(scores.values())[-2] else None


def evaluate_pdf(facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map facts to per-technique verdicts: ``{technique, status, reason}``."""
    v: List[Dict[str, Any]] = []
    add = lambda t, status, reason: v.append({"technique": t, "status": status, "reason": reason})
    n = facts["pages"]
    st = facts["struct"]
    tagged = facts["marked"] and facts["has_struct_tree"] and st["nodes"] > 0

    # PDF18 title
    if facts["title"] and facts["display_doc_title"]:
        add("PDF18", "pass", f'Document title "{facts["title"][:60]}" is set and DisplayDocTitle is on (PDF18).')
    elif facts["title"]:
        add("PDF18", "needs_review", f'Document title "{facts["title"][:60]}" is set but ViewerPreferences/DisplayDocTitle is not true — readers show the file name instead (PDF18).')
    else:
        add("PDF18", "fail", "No document title in the Info dictionary or XMP metadata (PDF18).")
    # PDF16 lang
    lang = facts["lang"]
    if lang and _BCP47_RE.match(lang):
        guess = _detect_lang(facts["text"])
        if guess and guess != lang.lower().split("-")[0]:
            add("PDF16", "needs_review", f'Catalog /Lang is "{lang}" but the text looks like "{guess}" (PDF16).')
        else:
            add("PDF16", "pass", f'Catalog /Lang is "{lang}" (PDF16).')
    elif lang:
        add("PDF16", "fail", f'Catalog /Lang "{lang}" is not a valid BCP 47 tag (PDF16).')
    else:
        add("PDF16", "fail", "No /Lang entry in the document catalog — screen readers cannot pick the right voice (PDF16).")
    # PDF2 outlines
    if facts["has_outlines"]:
        add("PDF2", "pass", "Document has bookmarks (/Outlines) (PDF2).")
    elif n > 5:
        add("PDF2", "fail", f"{n}-page document has no bookmarks (/Outlines) (PDF2).")
    else:
        add("PDF2", "pass", f"Short document ({n} page(s)) — bookmarks not required (PDF2).")
    # PDF17 page labels
    if n > 3:
        add("PDF17", "pass" if facts["has_page_labels"] else "needs_review",
            "Page labels (/PageLabels) are defined (PDF17)." if facts["has_page_labels"] else f"{n}-page document has no /PageLabels — page numbers announced by readers may not match printed numbers (PDF17).")
    else:
        add("PDF17", "pass", "Short document — page labels not required (PDF17).")
    # PDF14 pagination artifacts
    if n > 3:
        add("PDF14", "pass" if facts["pagination_pages"] else "needs_review",
            f"Pagination artifacts (running headers/footers) found on {facts['pagination_pages']} page(s) (PDF14)." if facts["pagination_pages"] else "No pagination artifacts (running headers/footers marked as /Artifact) detected (PDF14).")
    else:
        add("PDF14", "pass", "Short document — running headers/footers not required (PDF14).")
    # PDF7 scanned
    if facts["scanned_pages"]:
        add("PDF7", "fail", f"{facts['scanned_pages']} of {n} page(s) are images with no text layer — a scanned PDF must be OCR'd so the text is real (PDF7).")
    else:
        add("PDF7", "pass", "Every page has a text layer (PDF7).")

    if not tagged:
        why = "PDF is not tagged (no /MarkInfo /Marked true or empty structure tree) — no structure, alternatives, headings, tables, lists or link tags are available to assistive technology."
        for t in _STRUCTURE_TECHS:
            add(t, "fail", f"{why} ({t})")
    else:
        fig = st["figures"]
        if fig == 0:
            add("PDF1", "pass", "No Figure elements (PDF1).")
            add("PDF4", "pass", "No Figure elements (PDF4).")
        elif st["figures_no_alt"]:
            add("PDF1", "fail", f"{st['figures_no_alt']} of {fig} Figure element(s) have no /Alt or /ActualText (PDF1).")
            add("PDF4", "needs_review", f"{st['figures_no_alt']} Figure(s) without /Alt — if decorative they must be marked as artifacts instead of tagged as Figure (PDF4).")
        else:
            add("PDF1", "pass", f"All {fig} Figure element(s) carry /Alt or /ActualText (PDF1).")
            add("PDF4", "pass", "Decorative images are not exposed as Figures without alternatives (PDF4).")
        if st["tables"] == 0:
            add("PDF6", "pass", "No table structures (PDF6)." if "|" not in facts["text"] else "No Table tags; verify visually aligned columns are not untagged tables (PDF6).")
        elif st["tables_no_rows"]:
            add("PDF6", "fail", f"{st['tables_no_rows']} of {st['tables']} Table element(s) contain no TR rows (PDF6).")
        elif st["tables_no_th"]:
            add("PDF6", "needs_review", f"{st['tables_no_th']} of {st['tables']} table(s) have rows but no TH header cells (PDF6).")
        else:
            add("PDF6", "pass", f"{st['tables']} table(s) are tagged with TR/TH/TD (PDF6).")
        if st["headings"]:
            add("PDF9", "pass", f"{st['headings']} heading tag(s) present (PDF9).")
        elif facts["text_len"] > 1500 or n > 2:
            add("PDF9", "fail", "No H/H1–H6 heading tags in a multi-page or long document (PDF9).")
        else:
            add("PDF9", "pass", "Short document without headings (PDF9).")
        bullets = len(_BULLET_LINE_RE.findall(facts["text"]))
        if st["lists"]:
            add("PDF21", "pass", f"{st['lists']} list structure(s) tagged (PDF21).")
        elif bullets >= 3:
            add("PDF21", "fail", f"{bullets} bullet/numbered lines found but no L/LI list structure (PDF21).")
        else:
            add("PDF21", "pass", "No list-like text without list tags (PDF21).")
        if facts["link_annots"] == 0:
            add("PDF11", "pass", "No link annotations (PDF11).")
            add("PDF13", "pass", "No link annotations (PDF13).")
        else:
            if facts["link_annots_untagged"]:
                add("PDF11", "fail", f"{facts['link_annots_untagged']} of {facts['link_annots']} link annotation(s) are not connected to a Link structure element (/StructParent) (PDF11).")
            else:
                add("PDF11", "pass", f"All {facts['link_annots']} link annotation(s) are tagged as Link (PDF11).")
            if st["link_tags"] and st["link_tags_no_alt"] and facts["link_annots_no_contents"]:
                add("PDF13", "needs_review", f"{st['link_tags_no_alt']} Link tag(s) have no /Alt and their annotations no /Contents — verify the link text describes the destination (PDF13).")
            else:
                add("PDF13", "pass", "Link tags carry /Alt or annotation contents (PDF13).")
        if facts["pages_with_annots"]:
            add("PDF3", "pass" if facts["pages_with_tabs"] == facts["pages_with_annots"] else "fail",
                f"/Tabs /S set on all {facts['pages_with_annots']} page(s) with annotations (PDF3)." if facts["pages_with_tabs"] == facts["pages_with_annots"]
                else f"{facts['pages_with_annots'] - facts['pages_with_tabs']} page(s) with links/fields lack /Tabs /S — tab order does not follow the structure (PDF3).")
        else:
            add("PDF3", "pass", "No interactive annotations; reading order follows the structure tree (PDF3).")
        guess = _detect_lang(facts["text"])
        if st["lang_elems"]:
            add("PDF19", "pass", f"{st['lang_elems']} structure element(s) declare their own /Lang (PDF19).")
        elif guess and lang and guess != lang.lower().split("-")[0]:
            add("PDF19", "needs_review", f'Text looks like "{guess}" while the document language is "{lang}" and no element carries /Lang (PDF19).')
        else:
            add("PDF19", "pass", "No passages in another language detected (PDF19).")
        acr = Counter(_ACRONYM_RE.findall(facts["text"]))
        repeated = [a for a, c in acr.items() if c >= 3 and a not in {"PDF", "HTML", "URL", "ISO", "USA", "THE", "AND"}]
        if st["expansions"]:
            add("PDF8", "pass", f"{st['expansions']} element(s) carry /E expansions (PDF8).")
        elif repeated:
            add("PDF8", "needs_review", f"Acronyms used repeatedly ({', '.join(repeated[:5])}) with no /E expansion entries (PDF8).")
        else:
            add("PDF8", "pass", "No repeated unexplained acronyms (PDF8).")

    # forms
    form = facts["form"]
    if form["count"] == 0:
        blanks = len(_BLANK_RE.findall(facts["text"]))
        if blanks >= 3 or facts["widget_annots"] == 0 and re.search(r"\b(signature|sign here|date:|name:)\b", facts["text"], re.I) and blanks:
            add("PDF23", "fail", f"Form-like blanks ({blanks}) but no interactive form fields — the form cannot be filled with a keyboard (PDF23).")
        else:
            add("PDF23", "pass", "Not a form (PDF23).")
        for t in ("PDF10", "PDF12", "PDF5", "PDF15", "PDF22"):
            add(t, "pass", f"No form fields ({t}).")
    else:
        add("PDF23", "pass", f"{form['count']} interactive form field(s) (PDF23).")
        add("PDF10", "fail" if form["no_tu"] else "pass",
            f"{form['no_tu']} of {form['count']} field(s) have no /TU tooltip label (PDF10)." if form["no_tu"] else f"All {form['count']} field(s) have /TU labels (PDF10).")
        add("PDF12", "fail" if form["no_ft"] else "pass",
            f"{form['no_ft']} field(s) lack a name (/T) or type (/FT) (PDF12)." if form["no_ft"] else "All fields expose name, type and value (PDF12).")
        if form["required"]:
            add("PDF5", "needs_review" if form["required_unmarked"] else "pass",
                f"{form['required_unmarked']} of {form['required']} required field(s) do not say 'required' in their label (PDF5)." if form["required_unmarked"] else f"All {form['required']} required field(s) are labelled as required (PDF5).")
        else:
            add("PDF5", "pass", "No required fields (PDF5).")
        add("PDF15", "pass" if form["submit"] else "needs_review",
            "Form has a SubmitForm action (PDF15)." if form["submit"] else "No SubmitForm action found — verify how the form is submitted (PDF15).")
        add("PDF22", "needs_review" if form["validation"] else "pass",
            f"{form['validation']} field(s) run validation scripts — verify their messages identify the error in text (PDF22)." if form["validation"] else "No field validation scripts (PDF22).")
    return v


# ── findings ─────────────────────────────────────────────────────────────────

def audit_pdf_bytes(data: bytes, pdf_url: str, page_url: str) -> List[Dict[str, Any]]:
    from ka11y.api.v1.combined.findings import _make_finding

    facts = inspect_pdf(data)
    out = []
    for verdict in evaluate_pdf(facts):
        sc, _ = _TECH[verdict["technique"]]
        status = verdict["status"]
        out.append(_make_finding(
            source="python",
            rule_id=f"python_pdf_{verdict['technique'].lower()}",
            wcag_sc=sc,
            status=status,
            severity=None if status == "pass" else ("serious" if status == "fail" else "moderate"),
            reason=f"Linked PDF {pdf_url.rsplit('/', 1)[-1][:60]} ({facts['pages']} pages): {verdict['reason']}",
            element_html=f'<a href="{pdf_url}">',
            element_id=pdf_url,
            element_tag="a",
            page_url=page_url,
        ))
    return out


def audit_linked_pdfs(html_snapshots: Dict[str, str], root_url: str, *, fetch=fetch_pdf, limit: int = _MAX_PDFS) -> List[Dict[str, Any]]:
    """Discover, download and audit PDFs linked from the crawled pages."""
    try:
        import pypdf  # noqa: F401
    except Exception:
        logger.warning("pypdf not installed — linked PDF audit skipped")
        return []
    findings: List[Dict[str, Any]] = []
    for pdf_url, page_url in discover_pdf_links(html_snapshots, root_url, limit=limit):
        data = fetch(pdf_url)
        if not data:
            continue
        try:
            findings.extend(audit_pdf_bytes(data, pdf_url, page_url))
        except Exception as exc:
            logger.warning("pdf audit failed for %s: %s", pdf_url, exc)
    return findings
