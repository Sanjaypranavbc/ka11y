"""
ka11y/accessibility/rules/sensory/wcag_133_auditor.py
======================================================
WCAG 1.3.3 — Sensory Characteristics Auditor  (Level A)

Rule:
    Instructions provided for understanding and operating content must not
    rely solely on sensory characteristics of components such as shape,
    size, visual location, orientation, or sound.

Approach:
    1. Filter elements to those containing instructional sentences
       (sentences that begin with an imperative verb: click, press, tap, …).
    2. For each instructional sentence, check whether it references ONLY
       a sensory property (colour, shape, size, position, sound) with no
       non-sensory identifier (a real label, a named button text, etc.).
    3. If sensory-only → FAILED; if sensory + non-sensory label → PASSED;
       if no sensory reference → PASSED (not relevant to this rule).

spaCy is used for sentence segmentation and POS tagging.
Model required: en_core_web_sm  (or the lang-appropriate model).
Install: python -m spacy download en_core_web_sm

Output:
    audit_sensory_report.csv  (written to output_dir)

CSV columns:
    page_url, element_tag, element_id, sentence,
    sensory_categories, wcag_1_3_3_status, wcag_1_3_3_violation,
    overall_status, html_snippet
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ka11y.crawler.sensory_crawler import SensoryElementData

# ─────────────────────────────────────────────────────────────────────────────
# Sensory word taxonomy
# ─────────────────────────────────────────────────────────────────────────────

SENSORY_WORDS: Dict[str, Set[str]] = {
    "color": {
        "blue", "red", "green", "yellow", "orange", "purple", "pink",
        "black", "white", "grey", "gray", "cyan", "magenta", "brown",
        "violet", "indigo", "teal", "navy", "maroon", "gold", "silver",
        "coloured", "colored",
    },
    "shape": {
        "round", "rounded", "square", "circular", "circle", "triangular",
        "triangle", "rectangular", "oval", "hexagonal", "diamond",
    },
    "size": {
        "big", "small", "large", "tiny", "huge", "little", "giant",
        "wide", "narrow", "tall", "short", "smaller", "larger",
        "biggest", "smallest",
    },
    "position": {
        "left", "right", "top", "bottom", "above", "below", "upper",
        "lower", "corner", "center", "centre", "middle", "side",
        "adjacent", "beside", "next", "nearby", "underneath", "beneath",
        "leftmost", "rightmost", "topmost",
    },
    "sound": {
        "beep", "chime", "bell", "tone", "sound", "audio", "alarm",
        "buzz", "ring", "ping", "notification",
    },
}

# Flattened set for quick membership tests
ALL_SENSORY: Set[str] = set().union(*SENSORY_WORDS.values())

# Imperative verbs that signal instructional sentences
IMPERATIVE_VERBS: Set[str] = {
    "click", "press", "tap", "select", "choose", "go", "refer",
    "find", "see", "use", "follow", "navigate", "scroll", "drag",
    "hover", "open", "close", "expand", "collapse", "toggle",
    "submit", "enter", "fill", "type", "search", "pick", "hit",
    "push", "check", "uncheck", "enable", "disable",
}

# Generic UI nouns that do NOT count as meaningful (non-sensory) labels
GENERIC_UI_NOUNS: Set[str] = {
    "button", "icon", "link", "item", "element", "option",
    "control", "widget", "field", "area", "section", "menu",
    "panel", "bar", "box", "container",
}

# Common stop-words and imperative verbs to exclude from "meaningful label" checks in regex fallback
STOP_WORDS: Set[str] = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "you", "your", "his", "her", "its", "our", "their", "will", "can",
    "may", "must", "should", "some", "any", "all", "each", "every",
    "a", "an", "of", "to", "in", "on", "at", "by", "is", "are", "was", "were",
    "please", "kindly", "just", "now", "simply", "merely",
}

# Minimum text length to bother analysing
_MIN_TEXT_LEN = 5


# ─────────────────────────────────────────────────────────────────────────────
# spaCy lazy-loader (avoids import overhead when audit is skipped)
# ─────────────────────────────────────────────────────────────────────────────

_nlp = None


def _get_nlp(lang: str = "en"):
    global _nlp
    if _nlp is None:
        try:
            import spacy  # type: ignore

            # Pick the smallest available model; fall back to blank pipeline.
            model_name = "en_core_web_sm" if lang == "en" else f"{lang}_core_news_sm"
            try:
                _nlp = spacy.load(model_name, disable=["ner", "parser"])
                # Enable sentence segmentation via sentencizer (fast)
                if "sentencizer" not in _nlp.pipe_names:
                    _nlp.add_pipe("sentencizer")
            except OSError:
                # Model not installed — use blank pipeline with sentencizer
                _nlp = spacy.blank(lang[:2])
                _nlp.add_pipe("sentencizer")
        except ImportError:
            _nlp = None
    return _nlp


# ─────────────────────────────────────────────────────────────────────────────
# Sentence-level helpers
# ─────────────────────────────────────────────────────────────────────────────


def _tokenize_sentences(text: str, nlp) -> List[Any]:
    """Return spaCy sentence spans for the given text."""
    doc = nlp(text)
    return list(doc.sents)


def _is_instruction(sent) -> bool:
    """
    True if the sentence contains an imperative verb that suggests an instruction.
    We check the first few tokens for a VERB or a known imperative lemma.
    """
    # Common prefixes that don't change the instructional nature
    SKIP_TOKENS = {"please", "kindly", "to", "now", "just"}
    
    count = 0
    for token in sent:
        if token.is_space or token.is_punct:
            continue
        
        text_lower = token.text.lower()
        if text_lower in SKIP_TOKENS:
            continue
            
        # spaCy POS check
        if hasattr(token, "pos_") and token.pos_ == "VERB":
            return True
        # Lemma/Text fallback
        lemma = token.lemma_.lower() if hasattr(token, "lemma_") else text_lower
        if lemma in IMPERATIVE_VERBS or text_lower in IMPERATIVE_VERBS:
            return True
        
        # If we've seen a non-skip, non-verb word in the first few slots, 
        # it's likely not an imperative sentence (e.g., "The button is red").
        count += 1
        if count > 2: 
            break
            
    return False


def _sensory_categories_in_sent(sent) -> List[str]:
    """Return list of sensory category names found in the sentence tokens."""
    found: List[str] = []
    for cat, words in SENSORY_WORDS.items():
        for token in sent:
            text_lower = token.text.lower()
            lemma_lower = token.lemma_.lower() if hasattr(token, "lemma_") else text_lower
            if text_lower in words or lemma_lower in words:
                if cat not in found:
                    found.append(cat)
    return found


def _has_meaningful_label(sent) -> bool:
    """
    Return True if the sentence contains a non-sensory, non-generic noun
    that could serve as a real identifier for the referenced UI element.

    Strategy:
      - Any NOUN/PROPN that is NOT in ALL_SENSORY and NOT in GENERIC_UI_NOUNS
        is considered a meaningful label (e.g. "Submit", "Next step", "Home").
      - Quoted strings (e.g. 'Click "Save draft"') are always meaningful.
    """
    text = sent.text if hasattr(sent, "text") else str(sent)

    # Quoted text → meaningful label present
    if re.search(r'["\u201c\u201d\u2018\u2019].+?["\u201c\u201d\u2018\u2019]', text):
        return True

    if hasattr(sent, "__iter__"):
        for token in sent:
            if hasattr(token, "pos_") and token.pos_ in ("NOUN", "PROPN"):
                lemma = token.lemma_.lower() if hasattr(token, "lemma_") else token.text.lower()
                word  = token.text.lower()
                if word not in ALL_SENSORY and lemma not in ALL_SENSORY:
                    if word not in GENERIC_UI_NOUNS and lemma not in GENERIC_UI_NOUNS:
                        return True

    return False


def _is_sensory_only(sent, sensory_cats: List[str]) -> bool:
    """
    True when:
      - the sentence contains at least one sensory word  AND
      - it does NOT contain any meaningful (non-sensory) label.
    """
    if not sensory_cats:
        return False
    return not _has_meaningful_label(sent)


# ─────────────────────────────────────────────────────────────────────────────
# Per-element violation detector
# ─────────────────────────────────────────────────────────────────────────────


def _violations_133(
    element: SensoryElementData,
    nlp,
) -> List[Tuple[str, str, List[str], str]]:
    """
    Analyse one element's text for WCAG 1.3.3 violations.

    Returns a list of (sentence_text, message, sensory_categories, status)
    for each instructional sentence found in the element.
    Status is either "FAILED" or "PASSED".
    """
    text = element.text
    if not text or len(text) < _MIN_TEXT_LEN:
        return []

    # Also check aria-label text
    texts_to_check = [text]
    if element.aria_label and element.aria_label.strip():
        texts_to_check.append(element.aria_label)

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts_to_check:
        try:
            sents = _tokenize_sentences(src_text, nlp)
        except Exception:
            # Fallback: treat the whole text as one sentence
            sents = [src_text]  # type: ignore

        for sent in sents:
            sent_text = sent.text if hasattr(sent, "text") else str(sent)
            if len(sent_text.strip()) < _MIN_TEXT_LEN:
                continue

            if not _is_instruction(sent):
                continue

            sensory_cats = _sensory_categories_in_sent(sent)
            if not sensory_cats:
                continue

            if _is_sensory_only(sent, sensory_cats):
                cats_str = ", ".join(sensory_cats)
                msg = (
                    f"1.3.3: Instruction relies solely on sensory characteristic(s) "
                    f"[{cats_str}] — \"{sent_text.strip()[:120]}\" — "
                    f"add a non-sensory identifier (e.g. button label or heading text)."
                )
                results.append((sent_text.strip(), msg, sensory_cats, "FAILED"))
            else:
                msg = f"1.3.3: Instruction contains sensory characteristic(s) but also provides a non-sensory identifier."
                results.append((sent_text.strip(), msg, sensory_cats, "PASSED"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class SensoryCharacteristicsAuditor:
    """
    Runs WCAG 1.3.3 checks against a list of SensoryElementData records
    and writes audit_sensory_report.csv to output_dir.
    """

    CSV_FIELDS = [
        "page_url",
        "element_tag",
        "element_id",
        "sentence",
        "sensory_categories",
        "wcag_1_3_3_status",
        "wcag_1_3_3_violation",
        "overall_status",
        "html_snippet",
    ]

    def __init__(self, output_dir: str, lang: str = "en"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lang = lang

    def generate_audit_report(
        self,
        elements: List[SensoryElementData],
    ) -> List[Dict[str, Any]]:
        """
        Audit all elements, write CSV, return list of record dicts.

        Only elements that contain at least one instructional sentence with
        a sensory reference produce a row; others are silently skipped to
        keep the report focused on actionable issues.
        """
        nlp = _get_nlp(self.lang)
        if nlp is None:
            print(
                "[SensoryAuditor] WARNING: spaCy not available. "
                "Falling back to regex-only sentence splitting."
            )

        records: List[Dict[str, Any]] = []

        for el in elements:
            if nlp is not None:
                viols = _violations_133(el, nlp)
            else:
                viols = _violations_133_regex(el)

            if not viols:
                continue  # No instructional sensory text → skip

            for sent_text, msg, cats, status in viols:
                records.append(
                    {
                        "page_url":          el.page_url,
                        "element_tag":       el.tag,
                        "element_id":        el.element_id or "",
                        "sentence":          sent_text[:300],
                        "sensory_categories": ", ".join(cats),
                        "wcag_1_3_3_status": status,
                        "wcag_1_3_3_violation": msg if status == "FAILED" else "",
                        "overall_status":    status,
                        "html_snippet":      el.html[:400],
                    }
                )

        # ── Summary counts ────────────────────────────────────────────────────
        total_elements_checked = len(elements)
        total_violations       = sum(1 for r in records if r["overall_status"] == "FAILED")
        unique_pages           = len({r["page_url"] for r in records if r["overall_status"] == "FAILED"})

        # ── Write CSV ─────────────────────────────────────────────────────────
        csv_path = self.output_dir / "audit_sensory_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({f: "" for f in self.CSV_FIELDS})  # blank spacer

            summary: Dict[str, Any] = {f: "" for f in self.CSV_FIELDS}
            summary.update(
                {
                    "page_url":          "── SUMMARY ──",
                    "element_tag":       f"Elements checked : {total_elements_checked}",
                    "element_id":        f"Violations found : {total_violations}",
                    "sentence":          f"Affected pages : {unique_pages}",
                    "wcag_1_3_3_status": "FAILED" if total_violations > 0 else "PASSED",
                    "overall_status":    "FAILED" if total_violations > 0 else "PASSED",
                }
            )
            writer.writerow(summary)

        print(
            f"[SensoryAuditor] audit_sensory_report.csv → {csv_path}  "
            f"({total_elements_checked} elements | {total_violations} violation(s) | "
            f"{unique_pages} page(s) affected)"
        )
        return records

    # ── Summary helper ────────────────────────────────────────────────────────
    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        total      = sum(1 for r in records if r["overall_status"] == "FAILED")
        pages      = len({r.get("page_url", "") for r in records if r.get("overall_status") == "FAILED"})
        categories: Dict[str, int] = {}
        for r in records:
            if r.get("overall_status") == "FAILED":
                for cat in (r.get("sensory_categories") or "").split(", "):
                    cat = cat.strip()
                    if cat:
                        categories[cat] = categories.get(cat, 0) + 1
        return {
            "total_violations":  total,
            "affected_pages":    pages,
            "by_sensory_category": categories,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Regex-only fallback (no spaCy)
# ─────────────────────────────────────────────────────────────────────────────

_SENT_SPLIT_RE  = re.compile(r"(?<=[.!?])\s+")
_IMPERATIVE_RE  = re.compile(
    r"^\s*(please|kindly|to|now|just)?\s*(" + "|".join(sorted(IMPERATIVE_VERBS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_SENSORY_RE     = re.compile(
    r"\b(" + "|".join(sorted(ALL_SENSORY, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_GENERIC_RE     = re.compile(
    r"\b(" + "|".join(sorted(GENERIC_UI_NOUNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_QUOTED_RE      = re.compile(r'["\u201c\u201d\u2018\u2019].+?["\u201c\u201d\u2018\u2019]')


def _violations_133_regex(
    element: SensoryElementData,
) -> List[Tuple[str, str, List[str], str]]:
    """
    Pure-regex fallback when spaCy is unavailable.
    Less accurate but zero-dependency.
    """
    texts = [element.text or ""]
    if element.aria_label:
        texts.append(element.aria_label)

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts:
        sentences = _SENT_SPLIT_RE.split(src_text)
        for sent_text in sentences:
            sent_text = sent_text.strip()
            if len(sent_text) < _MIN_TEXT_LEN:
                continue

            if not _IMPERATIVE_RE.match(sent_text):
                continue

            sensory_hits = _SENSORY_RE.findall(sent_text)
            if not sensory_hits:
                continue

            # Determine categories
            cats: List[str] = []
            lower = sent_text.lower()
            for cat, words in SENSORY_WORDS.items():
                if any(w in lower for w in words):
                    cats.append(cat)

            # Has meaningful label?
            has_quoted = bool(_QUOTED_RE.search(sent_text))
            # Remove sensory + generic words + imperative verbs + stop words;
            # anything left indicates a non-sensory identifier.
            stripped = _SENSORY_RE.sub("", sent_text)
            stripped = _GENERIC_RE.sub("", stripped)
            stripped = _IMPERATIVE_RE.sub("", stripped)
            
            remaining_words = []
            for w in re.split(r"\W+", stripped):
                w_lower = w.lower()
                if len(w) > 2 and w_lower not in STOP_WORDS and w_lower not in IMPERATIVE_VERBS:
                    remaining_words.append(w)
            
            has_label = has_quoted or bool(remaining_words)

            if cats and not has_label:
                msg = (
                    f"1.3.3: Instruction relies solely on sensory characteristic(s) "
                    f"[{', '.join(cats)}] — \"{sent_text[:120]}\" — "
                    f"add a non-sensory identifier (e.g. button label or heading text)."
                )
                results.append((sent_text, msg, cats, "FAILED"))
            else:
                msg = f"1.3.3: Instruction contains sensory characteristic(s) but also provides a non-sensory identifier."
                results.append((sent_text, msg, cats, "PASSED"))

    return results