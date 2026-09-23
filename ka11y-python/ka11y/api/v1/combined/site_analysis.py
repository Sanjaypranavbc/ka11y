"""
ka11y/api/v1/combined/site_analysis.py
=======================================
Cross-page (site-level) checks that a single-page audit cannot make. Runs over
the rendered HTML snapshots the universal crawl saved for every page
(``_jobs[job_id]["html_snapshots"]``: page_url → file path) once a job has
visited two or more pages.

Techniques covered
------------------
* **G61  (3.2.3 Consistent Navigation)** — the relative order of links inside
  navigation regions that repeat across pages must not change.
* **G197 (3.2.4 Consistent Identification)** — a link/control that goes to the
  same place must be named the same way on every page.
* **G127 (2.4.2 Page Titled)** — page titles should identify the site as well
  as the page (a shared site-name segment across titles).
* **G185 / G125 / G126 (2.4.5 Multiple Ways)** — the home page links to (most
  of) the crawled pages, navigation links are shared across pages, or a page
  lists (almost) every crawled page (site map).
* **H30 / G91 (2.4.4 / 2.4.9 Link Purpose)** — internal link text is compared
  with the destination page's title; generic or unrelated text is reported.

Every function is pure and defensive: a malformed snapshot only skips that page.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit

from ka11y.config.logger import setup_logger
from ka11y.utils.html_soup import make_soup
from ka11y.utils.url_canonical import canonicalize_url

from .findings import _make_finding

logger = setup_logger(name="KAC", tag="site-analysis")

_GENERIC_LINK_RE = re.compile(
    r"^(?:click here|here|read more|more|learn more|details|link|this|continue|go|next|previous|prev|"
    r"view|see more|download|こちら|詳細|もっと見る|続きを読む|詳しく|リンク|次へ|前へ)[\s.。:：>»→]*$",
    re.IGNORECASE,
)
_STOP = {"the", "and", "for", "with", "from", "your", "you", "our", "are", "this", "that", "page", "home", "www",
         "com", "org", "net", "html", "htm", "of", "to", "in", "on", "a", "an"}


def _tokens(text: str) -> set:
    t = (text or "").lower()
    latin = set(re.findall(r"[a-z0-9À-ɏ]{3,}", t)) - _STOP
    cjk = set()
    for run in re.findall(r"[぀-ヿ㐀-鿿]{2,}", t):
        for i in range(len(run) - 1):
            cjk.add(run[i:i + 2])
    return latin | cjk


def _norm_url(href: str, base: str) -> Optional[str]:
    try:
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return None
        u = canonicalize_url(urljoin(base, href))
        return u or None
    except Exception:
        return None


def _same_site(a: str, b: str) -> bool:
    try:
        return urlsplit(a).netloc.lower().lstrip("www.") == urlsplit(b).netloc.lower().lstrip("www.")
    except Exception:
        return False


def _acc_name(el) -> str:
    for attr in ("aria-label", "title"):
        v = (el.get(attr) or "").strip()
        if v:
            return v
    img = el.find("img")
    txt = " ".join(el.stripped_strings)
    if not txt and img is not None:
        return (img.get("alt") or "").strip()
    return re.sub(r"\s+", " ", txt).strip()


def extract_page_facts(html: str, page_url: str) -> Dict[str, Any]:
    """Per-page facts used by every cross-page rule."""
    soup = make_soup(html)
    title = re.sub(r"\s+", " ", (soup.title.get_text() if soup.title else "") or "").strip()
    navs: List[Dict[str, Any]] = []
    nav_els = soup.select("nav, [role=navigation]")
    for i, nav in enumerate(nav_els):
        label = (nav.get("aria-label") or nav.get("id") or "").strip().lower() or f"nav#{i}"
        seq: List[str] = []
        for a in nav.select("a[href]"):
            u = _norm_url(a.get("href"), page_url)
            if u and u not in seq:
                seq.append(u)
        if seq:
            navs.append({"label": label, "index": i, "links": seq})
    links: List[Tuple[str, str]] = []
    controls: Dict[str, set] = defaultdict(set)
    for a in soup.select("a[href]"):
        u = _norm_url(a.get("href"), page_url)
        if not u or not _same_site(u, page_url):
            continue
        name = _acc_name(a)
        links.append((u, name))
        if name:
            controls[u].add(name)
    for f in soup.select("form[action]"):
        u = _norm_url(f.get("action"), page_url)
        btn = f.select_one("button, input[type=submit]")
        if u and btn is not None:
            name = _acc_name(btn) or (btn.get("value") or "").strip()
            if name:
                controls[f"form:{u}"].add(name)
    h1 = soup.select_one("h1")
    return {
        "page_url": page_url,
        "title": title,
        "h1": re.sub(r"\s+", " ", h1.get_text()).strip() if h1 else "",
        "navs": navs,
        "links": links,
        "controls": controls,
        "internal_targets": {u for u, _ in links},
    }


def _relative_order_violations(a: List[str], b: List[str]) -> List[Tuple[str, str]]:
    """Pairs of shared links whose order is inverted between sequences a and b."""
    shared = [u for u in a if u in b]
    if len(shared) < 2:
        return []
    pos_b = {u: i for i, u in enumerate(b)}
    out = []
    for i in range(len(shared)):
        for j in range(i + 1, len(shared)):
            if pos_b[shared[i]] > pos_b[shared[j]]:
                out.append((shared[i], shared[j]))
                if len(out) >= 5:
                    return out
    return out


def analyze_site(html_snapshots: Dict[str, str], root_url: str) -> List[Dict[str, Any]]:
    """Return site-level findings for a multi-page crawl (empty for < 2 pages)."""
    pages: List[Dict[str, Any]] = []
    for page_url, path in list(html_snapshots.items())[:60]:
        try:
            html = Path(path).read_text(encoding="utf-8", errors="replace")
            pages.append(extract_page_facts(html, page_url))
        except Exception as exc:
            logger.debug("site analysis: skipping %s (%s)", page_url, exc)
    if len(pages) < 2:
        return []
    findings: List[Dict[str, Any]] = []
    by_url = {canonicalize_url(p["page_url"]) or p["page_url"]: p for p in pages}
    root_key = canonicalize_url(root_url) or root_url

    # ── G61 (3.2.3): navigation order across pages ──────────────────────────
    ref = pages[0]
    nav_inconsistent: List[Dict[str, Any]] = []
    for p in pages[1:]:
        for nav in p["navs"]:
            match = next((n for n in ref["navs"] if n["label"] == nav["label"]), None) or \
                    next((n for n in ref["navs"] if n["index"] == nav["index"]), None)
            if not match:
                continue
            inv = _relative_order_violations(match["links"], nav["links"])
            if inv:
                nav_inconsistent.append({"page": p["page_url"], "nav": nav["label"], "pairs": inv})
    if nav_inconsistent:
        for item in nav_inconsistent[:10]:
            pairs = "; ".join(f"{a.rsplit('/', 1)[-1] or a} before {b.rsplit('/', 1)[-1] or b}" for a, b in item["pairs"][:3])
            findings.append(_make_finding(
                source="python", rule_id="python_3_2_3_consistent_navigation", wcag_sc="3.2.3",
                status="fail", severity="moderate",
                reason=(f"Navigation '{item['nav']}' lists links in a different relative order than on "
                        f"{ref['page_url']} (on the first page: {pairs}). Repeated navigation must keep "
                        "the same relative order on every page (G61)."),
                element_html=f"<nav aria-label=\"{item['nav']}\">", element_tag="nav", page_url=item["page"],
            ))
    else:
        shared_navs = sum(1 for p in pages[1:] for nav in p["navs"] if any(n["label"] == nav["label"] for n in ref["navs"]))
        findings.append(_make_finding(
            source="python", rule_id="python_3_2_3_consistent_navigation", wcag_sc="3.2.3",
            status="pass", severity=None,
            reason=(f"Navigation link order is consistent across {len(pages)} crawled page(s) "
                    f"({shared_navs} repeated navigation region(s) compared, G61)."),
            page_url=root_url,
        ))

    # ── G197 (3.2.4): same destination, different names ─────────────────────
    names_by_target: Dict[str, Counter] = defaultdict(Counter)
    for p in pages:
        for target, names in p["controls"].items():
            for name in names:
                n = re.sub(r"\s+", " ", name).strip()
                if n and len(n) <= 80:
                    names_by_target[target][n.lower()] += 1
    inconsistent = [(t, c) for t, c in names_by_target.items() if len(c) > 1 and not any(_GENERIC_LINK_RE.match(k) for k in c)]
    for target, counter in inconsistent[:10]:
        names = ", ".join(f'"{k}"' for k, _ in counter.most_common(4))
        findings.append(_make_finding(
            source="python", rule_id="python_3_2_4_consistent_identification", wcag_sc="3.2.4",
            status="needs_review", severity="minor",
            reason=(f"The same destination ({target}) is labelled differently across pages: {names}. "
                    "Components with the same function should be identified consistently (G197)."),
            element_html=f'<a href="{target}">', element_tag="a", page_url=root_url,
        ))
    if not inconsistent:
        findings.append(_make_finding(
            source="python", rule_id="python_3_2_4_consistent_identification", wcag_sc="3.2.4",
            status="pass", severity=None,
            reason=(f"{len(names_by_target)} repeated link/control destination(s) carry the same name on every "
                    f"page they appear on ({len(pages)} pages, G197)."),
            page_url=root_url,
        ))

    # ── G127 (2.4.2): site name in titles ───────────────────────────────────
    titles = [p["title"] for p in pages if p["title"]]
    if len(titles) >= 2:
        segs = Counter()
        for t in titles:
            for seg in re.split(r"\s[-|–—:·»›/]\s|[|｜]", t):
                seg = seg.strip()
                if len(seg) >= 3:
                    segs[seg.lower()] += 1
        common = [s for s, c in segs.items() if c >= max(2, int(len(titles) * 0.6))]
        if common:
            missing = [p for p in pages if p["title"] and not any(s in p["title"].lower() for s in common)]
            for p in missing[:10]:
                findings.append(_make_finding(
                    source="python", rule_id="python_2_4_2_site_name_in_title", wcag_sc="2.4.2",
                    status="needs_review", severity="minor",
                    reason=(f'Title "{p["title"][:70]}" lacks the site name segment "{common[0]}" that the other '
                            "pages carry — titles should identify the site as well as the page (G127)."),
                    element_html=f"<title>{p['title'][:80]}</title>", element_tag="title", page_url=p["page_url"],
                ))
            if not missing:
                findings.append(_make_finding(
                    source="python", rule_id="python_2_4_2_site_name_in_title", wcag_sc="2.4.2",
                    status="pass", severity=None,
                    reason=f'All {len(titles)} page titles include the site name "{common[0]}" (G127).',
                    page_url=root_url,
                ))
        else:
            findings.append(_make_finding(
                source="python", rule_id="python_2_4_2_site_name_in_title", wcag_sc="2.4.2",
                status="needs_review", severity="minor",
                reason=(f"No common site-name segment was found across the {len(titles)} page titles — "
                        "consider a \"Page – Site\" pattern so users know which site they are on (G127)."),
                element_html=f"<title>{titles[0][:80]}</title>", element_tag="title", page_url=root_url,
            ))

    # ── G185 / G125 / G126 (2.4.5): multiple ways site-wide ─────────────────
    all_pages = set(by_url.keys())
    home = by_url.get(root_key) or pages[0]
    home_links = {canonicalize_url(u) or u for u in home["internal_targets"]}
    home_cov = len((home_links & all_pages) - {root_key}) / max(1, len(all_pages) - 1)
    nav_sets = [frozenset(u for n in p["navs"] for u in n["links"]) for p in pages if p["navs"]]
    shared_nav = 0.0
    if nav_sets:
        core = set.intersection(*[set(s) for s in nav_sets]) if len(nav_sets) > 1 else set(nav_sets[0])
        shared_nav = len(core) / max(1, max(len(s) for s in nav_sets))
    sitemap_pages = [p["page_url"] for p in pages if len(({canonicalize_url(u) or u for u in p["internal_targets"]} & all_pages) - {canonicalize_url(p["page_url"]) or ""}) >= 0.8 * max(1, len(all_pages) - 1)]
    ways = []
    if home_cov >= 0.8:
        ways.append(f"home page links to {int(home_cov * 100)}% of crawled pages (G185)")
    if shared_nav >= 0.6 and nav_sets:
        ways.append(f"a navigation region shared across pages links related pages (G125)")
    if sitemap_pages:
        ways.append(f"{len(sitemap_pages)} page(s) list nearly every crawled page, acting as a site map (G126)")
    findings.append(_make_finding(
        source="python", rule_id="python_2_4_5_multiple_ways_site", wcag_sc="2.4.5",
        status="pass" if ways else "needs_review", severity=None if ways else "minor",
        reason=(("Site-wide ways to reach pages: " + "; ".join(ways) + ".") if ways else
                (f"Across {len(pages)} crawled pages the home page links to only {int(home_cov * 100)}% of them and no "
                 "shared navigation or site-map page was detected — verify that at least two ways (search, site map, "
                 "navigation, links from the home page) exist to reach each page (G185/G125/G126).")),
        page_url=root_url,
    ))

    # ── H30 / G91 (2.4.4 / 2.4.9): link text vs destination title ──────────
    title_of = {k: (p["title"] or p["h1"]) for k, p in by_url.items()}
    mismatches: List[Dict[str, Any]] = []
    for p in pages:
        seen_pairs = set()
        for target, name in p["links"]:
            key = canonicalize_url(target) or target
            dest = title_of.get(key)
            if not dest or not name or (key, name.lower()) in seen_pairs:
                continue
            seen_pairs.add((key, name.lower()))
            if _GENERIC_LINK_RE.match(name):
                continue  # generic text is reported by the Node link-purpose rules
            if len(name) < 3:
                continue
            nt, dt = _tokens(name), _tokens(dest)
            if not nt or not dt:
                continue
            if nt & dt or name.lower() in dest.lower() or dest.lower().split(" - ")[0].split(" | ")[0].strip() in name.lower():
                continue
            mismatches.append({"page": p["page_url"], "text": name[:60], "target": target, "title": dest[:60]})
            if len(mismatches) >= 15:
                break
        if len(mismatches) >= 15:
            break
    for m in mismatches[:10]:
        findings.append(_make_finding(
            source="python", rule_id="python_2_4_4_link_text_vs_destination", wcag_sc="2.4.4",
            status="needs_review", severity="minor",
            reason=(f'Link text "{m["text"]}" shares no words with the destination page title "{m["title"]}" — '
                    "verify the link text describes where it leads (H30/G91)."),
            element_html=f'<a href="{m["target"]}">{m["text"]}</a>', element_tag="a", page_url=m["page"],
        ))
    if not mismatches:
        checked = sum(len(p["links"]) for p in pages)
        findings.append(_make_finding(
            source="python", rule_id="python_2_4_4_link_text_vs_destination", wcag_sc="2.4.4",
            status="pass", severity=None,
            reason=f"{checked} internal link(s) compared with their destination titles across {len(pages)} pages — "
                   "all descriptive link texts relate to the target page (H30/G91).",
            page_url=root_url,
        ))
    return findings
