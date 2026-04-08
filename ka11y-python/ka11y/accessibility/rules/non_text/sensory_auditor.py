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
        "colour", "color", "coloured", "colored", "highlighted",
    },
    "shape": {
        "round", "rounded", "square", "circular", "circle", "triangular",
        "triangle", "rectangular", "oval", "hexagonal", "diamond",
        "star", "star-shaped", "pill-shaped",
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
        "leftmost", "rightmost", "topmost", "down", "up", "under",
        "over", "inside", "outside",
    },
    "orientation": {
        "horizontal", "vertical", "landscape", "portrait", "clockwise",
        "counterclockwise", "upward", "downward",
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
    "push", "check", "uncheck", "enable", "disable", "tick",
    "mark", "focus", "locate", "identify",
}

# Generic UI nouns that do NOT count as meaningful (non-sensory) labels
GENERIC_UI_NOUNS: Set[str] = {
    "button", "icon", "link", "item", "element", "option",
    "control", "widget", "field", "area", "section", "menu",
    "panel", "bar", "box", "container", "form", "checkbox",
    "radio", "radiobutton", "dropdown", "select", "listbox", "textbox",
    "textfield", "input", "tab", "arrow", "step", "card", "dialog",
}

# Common stop-words to exclude from string-based "meaningful label" checks.
STOP_WORDS: Set[str] = {
    "the", "and", "for", "with", "from", "that", "this", "these", "those",
    "you", "your", "his", "her", "its", "our", "their", "will", "can",
    "may", "must", "should", "some", "any", "all", "each", "every",
    "a", "an", "of", "to", "in", "on", "at", "by", "is", "are", "was", "were",
    "please", "kindly", "just", "now", "simply", "merely", "be", "been",
    "being", "as", "if", "when", "then", "there", "here", "shown", "show",
    "displayed", "display", "indicated", "indicate", "marked", "mark",
    "located", "positioned", "placed", "highlighted", "required", "optional",
}

# Minimum text length to bother analysing
_MIN_TEXT_LEN = 5


# ─────────────────────────────────────────────────────────────────────────────
# spaCy lazy-loader (avoids import overhead when audit is skipped)
# ─────────────────────────────────────────────────────────────────────────────

_nlp_cache: Dict[str, Any] = {}


def _get_nlp(lang: str = "en"):
    lang_key = (lang or "en")[:2]
    if lang_key in _nlp_cache:
        return _nlp_cache[lang_key]

    nlp = None
    try:
        import spacy  # type: ignore

        model_name = "en_core_web_sm" if lang_key == "en" else f"{lang_key}_core_news_sm"
        try:
            nlp = spacy.load(model_name, disable=["ner", "parser"])
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")
        except OSError:
            nlp = None
    except ImportError:
        nlp = None

    _nlp_cache[lang_key] = nlp
    return nlp


# ─────────────────────────────────────────────────────────────────────────────
# Sentence-level helpers
# ─────────────────────────────────────────────────────────────────────────────


def _tokenize_sentences(text: str, nlp) -> List[Any]:
    """Return spaCy sentence spans for the given text."""
    doc = nlp(text)
    return list(doc.sents)


_CONTROL_RE = re.compile(
    r"\b("
    r"button|buttons|icon|icons|link|links|checkbox|checkboxes|radio|radios|"
    r"field|fields|form|forms|menu|menus|tab|tabs|section|sections|item|items|"
    r"option|options|arrow|arrows|dropdown|dropdowns|textbox|textboxes|"
    r"textfield|textfields|input|inputs|card|cards|panel|panels|dialog|dialogs"
    r")\b",
    re.IGNORECASE,
)
_DECLARATIVE_HINT_RE = re.compile(
    r"\b("
    r"marked|shown|displayed|indicated|located|positioned|placed|highlighted|"
    r"circled|underlined|selected|checked|available"
    r")\b",
    re.IGNORECASE,
)
_CONTROL_ACTION_HINT_RE = re.compile(
    r"\b(submits?|opens?|closes?|saves?|cancels?|confirms?|continues?|"
    r"proceeds?|navigates?|takes?)\b",
    re.IGNORECASE,
)
_POSITIONAL_INSTRUCTION_RE = re.compile(
    r"\b(on|to|at|in|under|over|below|above|beside|next to)\s+the\s+"
    r"(left|right|top|bottom|center|centre|middle|upper|lower)\b",
    re.IGNORECASE,
)
_REQUIRED_FIELD_RE = re.compile(r"\b(required|optional)\s+fields?\b", re.IGNORECASE)
_CATEGORY_REGEXES: Dict[str, re.Pattern[str]] = {
    cat: re.compile(
        r"\b(" + "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    for cat, words in SENSORY_WORDS.items()
}


def _sentence_text(sent: Any) -> str:
    return sent.text if hasattr(sent, "text") else str(sent)


def _iter_text_sources(element: SensoryElementData) -> List[str]:
    sources: List[str] = []
    for raw in (
        element.text,
        element.aria_label,
        getattr(element, "placeholder", None),
        getattr(element, "value", None),
    ):
        text = (raw or "").strip()
        if text and text not in sources:
            sources.append(text)
    return sources


def _is_instruction_text(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if _IMPERATIVE_RE.match(text):
        return True
    if _REQUIRED_FIELD_RE.search(text):
        return True
    return bool(
        _CONTROL_RE.search(text)
        and (
            _DECLARATIVE_HINT_RE.search(text)
            or _POSITIONAL_INSTRUCTION_RE.search(text)
            or _CONTROL_ACTION_HINT_RE.search(text)
        )
    )


def _is_instruction(sent) -> bool:
    """
    True if the sentence looks like an instruction.

    Supports both imperative commands ("Click the round button") and
    declarative guidance commonly used in forms ("Required fields are
    marked in red").
    """
    return _is_instruction_text(_sentence_text(sent))


def _sensory_categories_in_text(text: str) -> List[str]:
    return [cat for cat, pattern in _CATEGORY_REGEXES.items() if pattern.search(text)]


def _sensory_categories_in_sent(sent) -> List[str]:
    """Return list of sensory category names found in the sentence text."""
    return _sensory_categories_in_text(_sentence_text(sent))


def _remaining_label_words(text: str) -> List[str]:
    stripped = _PURPOSE_PHRASE_RE.sub(" ", text)
    stripped = _SENSORY_RE.sub(" ", stripped)
    stripped = _GENERIC_RE.sub(" ", stripped)
    stripped = _IMPERATIVE_RE.sub(" ", stripped)

    remaining_words: List[str] = []
    for word in re.split(r"\W+", stripped):
        word_lower = word.lower()
        if not word_lower:
            continue
        if len(word_lower) <= 2 and not word_lower.isdigit():
            continue
        if word_lower in STOP_WORDS:
            continue
        remaining_words.append(word_lower)
    return remaining_words


def _has_meaningful_label_text(text: str) -> bool:
    if _QUOTED_RE.search(text):
        return True
    return bool(_remaining_label_words(text))


def _has_meaningful_label(sent) -> bool:
    """
    Return True if the sentence contains a non-sensory, non-generic noun
    that could serve as a real identifier for the referenced UI element.

    Strategy:
      - Any NOUN/PROPN that is NOT in ALL_SENSORY and NOT in GENERIC_UI_NOUNS
        is considered a meaningful label (e.g. "Submit", "Next step", "Home").
      - Quoted strings (e.g. 'Click "Save draft"') are always meaningful.
    """
    return _has_meaningful_label_text(_sentence_text(sent))


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
    texts_to_check = [
        text for text in _iter_text_sources(element) if len(text.strip()) >= _MIN_TEXT_LEN
    ]
    if not texts_to_check:
        return []

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts_to_check:
        try:
            sents = _tokenize_sentences(src_text, nlp)
        except Exception:
            # Fallback: treat the whole text as one sentence
            sents = [src_text]  # type: ignore

        for sent in sents:
            sent_text = _sentence_text(sent)
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
    r"^\s*(please|kindly|to|now|just)?\s*("
    + "|".join(re.escape(word) for word in sorted(IMPERATIVE_VERBS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
_PURPOSE_PHRASE_RE = re.compile(
    r"\bto\s+(?:continue|proceed|submit|complete|finish|save|confirm|cancel|"
    r"close|open|start|return|go\s+back|move\s+on)\b(?:\s+\w+){0,2}",
    re.IGNORECASE,
)
_SENSORY_RE     = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in sorted(ALL_SENSORY, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _pluralize(word: str) -> str:
    if " " in word:
        return word
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    if len(word) > 1 and word.endswith("y") and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


_GENERIC_TERMS = set(GENERIC_UI_NOUNS)
for _word in list(GENERIC_UI_NOUNS):
    _GENERIC_TERMS.add(_pluralize(_word))

_GENERIC_RE     = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in sorted(_GENERIC_TERMS, key=len, reverse=True)) + r")\b",
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
    texts = [text for text in _iter_text_sources(element) if len(text) >= _MIN_TEXT_LEN]

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts:
        sentences = _SENT_SPLIT_RE.split(src_text)
        for sent_text in sentences:
            sent_text = sent_text.strip()
            if len(sent_text) < _MIN_TEXT_LEN:
                continue

            if not _is_instruction_text(sent_text):
                continue

            cats = _sensory_categories_in_text(sent_text)
            if not cats:
                continue

            has_label = _has_meaningful_label_text(sent_text)

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
