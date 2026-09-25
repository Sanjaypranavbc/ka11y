"""
ka11y/accessibility/technique_map.py
====================================
Tag audit findings with the WCAG **Situation(s)** and **Technique(s)** that
test their success criterion.

The data comes from ``ka11y/data/wcag-technique-map.json``, generated from the
``WCAG_Testing_Report_CodeCoverage.xlsx`` workbook by
``scripts/build_technique_map.py`` (run that and commit the JSON whenever the
workbook changes). Nothing here reads the spreadsheet.

Matching
--------
A finding is matched to techniques in tiers; the first tier that yields
anything wins and is recorded as ``technique_match``. Every tier is specific
to the check that produced the finding — there is deliberately no "every
technique of the SC" or "every technique of the engine" fallback, because a
1.1.1 alt-text failure is not evidence about the fifteen other 1.1.1
techniques.

``exact``
    The check named the technique itself: Node custom checks tag issues with
    ``technique: 'G88'`` (forwarded by axeResultMapper as ``technique_id``),
    and the Python PDF rules encode it in the rule id (``python_pdf_pdf1``).
``reason`` / ``issue``
    ``data/rule-techniques.json`` narrows the rule by the finding's
    ``reason_code`` (Python auditors: ``missing_alt`` → H37) or by the issue
    type the Node check reported (``issue_type: 'horizontal-scroll'`` → C32…).
``rule``
    The rule's check-level entry in ``data/rule-techniques.json`` — the
    technique(s) that check implements, hand-maintained and reviewable.
``evidence``
    Techniques whose *Code Evidence* in the workbook cites this rule's source
    file (``custom-page-titled``, ``document-title``, …).
``none``
    Nothing above applies. Empty lists; the rule is unmapped and should be
    added to ``rule-techniques.json``.

Sub-rule ids (``custom-resize-text-units``, ``custom-structure-semantics-review``)
try their own entry first and then their base rule's.

The result is always a list: several techniques commonly apply to one
situation, and picking one would be arbitrary. ``situations`` is the union of
the matched techniques' situations, in workbook order.

Fields written on a finding::

    "technique_match": "rule",
    "techniques": [
        {"id": "G88", "name": "Providing descriptive titles for Web pages",
         "situations": ["Sufficient"], "cover": "Implemented"},
        ...
    ],
    "situations": ["Sufficient"]

``strip_technique_fields`` / ``strip_failure_techniques`` remove those fields
again for the frontend-facing response (see combined/routes.py): failing and
needs-review findings must not carry technique data to the UI, passing ones may.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "wcag-technique-map.json"
_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "rule-techniques.json"

#: Finding keys this module writes (and the frontend boundary strips).
TECHNIQUE_FIELDS: Tuple[str, ...] = (
    "techniques", "situations", "technique_match", "technique_id", "issue_type",
)

_PDF_RULE_RE = re.compile(r"^python_pdf_([a-z0-9]+)$")
_SUFFIX_RE = re.compile(r"^(.*)-[a-z0-9]+$")


def _base_rule_ids(rule_id: str) -> List[str]:
    """``custom-resize-text-units`` → [itself, ``custom-resize-text``, ``custom-resize``, …]
    (the first that has an entry wins; ``custom-`` alone never matches)."""
    out = [rule_id]
    cur = rule_id
    while True:
        m = _SUFFIX_RE.match(cur)
        if not m or m.group(1) in ("custom", "python"):
            break
        cur = m.group(1)
        out.append(cur)
    return out


class TechniqueTable:
    """In-memory index over the generated map plus the hand-maintained rule
    table. One instance per (map, rule-table) pair."""

    def __init__(self, doc: Dict[str, Any], rules: Optional[Dict[str, Any]] = None):
        self.meta = {k: v for k, v in doc.items() if k != "by_sc"}
        self.by_sc: Dict[str, List[Dict[str, Any]]] = doc.get("by_sc") or {}
        self.rules: Dict[str, Dict[str, Any]] = (rules or {}).get("rules") or {}
        self._by_id: Dict[str, Tuple[str, Dict[str, Any]]] = {}
        for sc, entries in self.by_sc.items():
            for e in entries:
                self._by_id.setdefault(str(e.get("id", "")).upper(), (sc, e))

    def techniques_for_sc(self, sc: Optional[str]) -> List[Dict[str, Any]]:
        return list(self.by_sc.get(sc or "", []))

    def find(self, technique_id: Optional[str], sc: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Entry for *technique_id*, preferring the one filed under *sc*."""
        if not technique_id:
            return None
        tid = str(technique_id).strip().upper()
        if sc:
            for e in self.by_sc.get(sc, []):
                if str(e.get("id", "")).upper() == tid:
                    return e
        hit = self._by_id.get(tid)
        return hit[1] if hit else None

    def _resolve(self, ids: Iterable[str], sc: Optional[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tid in ids:
            e = self.find(tid, sc)
            if e is not None and e not in out:
                out.append(e)
        return out

    def rule_entry(self, rule_id: str) -> Optional[Dict[str, Any]]:
        for rid in _base_rule_ids(rule_id):
            if rid in self.rules:
                return self.rules[rid]
        return None

    # ── matching ─────────────────────────────────────────────────────────────

    def match(self, finding: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        sc = finding.get("wcag_sc")
        rule_id = str(finding.get("rule_id") or "")

        exact = self.find(_exact_id(finding), sc)
        if exact is not None:
            return "exact", [exact]

        entry = self.rule_entry(rule_id) if rule_id else None
        if entry:
            reason = str(finding.get("reason_code") or "")
            ids = (entry.get("by_reason_code") or {}).get(reason)
            if ids:
                hit = self._resolve(ids, sc)
                if hit:
                    return "reason", hit
            issue = str(finding.get("issue_type") or "")
            ids = (entry.get("by_issue_type") or {}).get(issue)
            if ids:
                hit = self._resolve(ids, sc)
                if hit:
                    return "issue", hit
            ids = entry.get("techniques") or []
            if ids:
                hit = self._resolve(ids, sc)
                if hit:
                    return "rule", hit
            if "techniques" in entry:
                # Explicitly mapped to nothing (no WCAG technique exists).
                return "none", []

        if rule_id and sc:
            candidates = self.techniques_for_sc(sc)
            for rid in _base_rule_ids(rule_id):
                by_rule = [e for e in candidates if rid in (e.get("rules") or ())]
                if by_rule:
                    return "evidence", by_rule
        return "none", []


def _exact_id(finding: Dict[str, Any]) -> Optional[str]:
    tid = finding.get("technique_id")
    if tid:
        return str(tid)
    m = _PDF_RULE_RE.match(str(finding.get("rule_id") or ""))
    return m.group(1).upper() if m else None


def _situations_of(entry: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for s in [entry.get("situation"), *(entry.get("also_situations") or [])]:
        if s and s not in out:
            out.append(s)
    return out


def _public(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The subset of a map entry that goes on a finding (evidence stays internal)."""
    return {
        "id": entry.get("id"),
        "name": entry.get("name"),
        "situations": _situations_of(entry),
        "cover": entry.get("cover"),
    }


@lru_cache(maxsize=4)
def _load(path: str, rules_path: str) -> TechniqueTable:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    rules: Dict[str, Any] = {}
    if rules_path:
        with open(rules_path, encoding="utf-8") as fh:
            rules = json.load(fh)
    return TechniqueTable(doc, rules)


def load_table(path: Optional[Path] = None, rules_path: Optional[Path] = None) -> TechniqueTable:
    """The technique table (map + rule table), cached per file pair."""
    return _load(str(path or _DATA_PATH), str(rules_path or _RULES_PATH))


def annotate_finding(finding: Dict[str, Any], table: Optional[TechniqueTable] = None) -> Dict[str, Any]:
    """Write ``techniques`` / ``situations`` / ``technique_match`` on *finding*
    (in place; returns it). Applies to every status — pass, fail, needs_review."""
    table = table or load_table()
    how, entries = table.match(finding)
    techniques = [_public(e) for e in entries]
    situations: List[str] = []
    for t in techniques:
        for s in t["situations"]:
            if s not in situations:
                situations.append(s)
    finding["technique_match"] = how
    finding["techniques"] = techniques
    finding["situations"] = situations
    return finding


def annotate_findings(findings: Iterable[Dict[str, Any]], table: Optional[TechniqueTable] = None) -> None:
    table = table or load_table()
    for f in findings:
        annotate_finding(f, table)


# ── frontend boundary ────────────────────────────────────────────────────────

def strip_technique_fields(finding: Dict[str, Any]) -> Dict[str, Any]:
    """A shallow copy of *finding* without the technique/situation fields."""
    return {k: v for k, v in finding.items() if k not in TECHNIQUE_FIELDS}


def _keeps_techniques(finding: Dict[str, Any]) -> bool:
    # Only automated passes keep their tags. A needs_review item a human marked
    # as "pass" is still an unconfirmed automated result, so it is stripped too.
    return finding.get("status") == "pass"


def _strip_list(findings: Any) -> Any:
    if not isinstance(findings, list):
        return findings
    return [f if (not isinstance(f, dict) or _keeps_techniques(f)) else strip_technique_fields(f) for f in findings]


def strip_failure_techniques(report: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Copy of a built report where every non-pass finding (fail, needs_review)
    has lost its technique/situation fields, in the flat lists and in the
    per-page arrays. Passing findings are shared, not copied. The input is
    left untouched so the hot-cache / stored report keeps the full data."""
    if not isinstance(report, dict):
        return report
    out = dict(report)
    for key in ("violations", "needs_review", "passes"):
        if key in out:
            out[key] = _strip_list(out[key])
    pages = out.get("pages")
    if isinstance(pages, list):
        new_pages = []
        for page in pages:
            if isinstance(page, dict):
                page = dict(page)
                for key in ("violations", "needs_review", "passes"):
                    if key in page:
                        page[key] = _strip_list(page[key])
            new_pages.append(page)
        out["pages"] = new_pages
    return out
