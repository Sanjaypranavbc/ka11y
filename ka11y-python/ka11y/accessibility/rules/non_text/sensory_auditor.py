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
       (imperative commands: "Click the round button" / declarative guidance:
        "Required fields are marked in red" / Japanese equivalents:
        "赤いボタンをクリックしてください").
    2. For each instructional sentence, check whether it references ONLY
       a sensory property (colour, shape, size, position, orientation, sound,
       brightness, texture) with no non-sensory identifier (a real label, a
       named button text, a quoted string, etc.).
    3. If sensory-only → FAILED; if sensory + non-sensory label → PASSED;
       if no sensory reference → PASSED (not relevant to this rule).

Language support:
    English  — spaCy en_core_web_sm  (or regex fallback)
    Japanese — spaCy ja_core_news_sm (or regex fallback)
    CJK text is detected automatically; word-boundary-safe regex is used
    for Japanese so that \b does not break on CJK characters.

Fixes over v1:
    - All module-level regex patterns defined before first use (no forward refs)
    - `brightness` and `texture` added as sensory categories (EN + JA)
    - `title` attribute included in text-source iteration
    - `_QUOTED_RE` extended to match Japanese quotation marks 「」 『』
    - Language detected per-element via `lang=` attribute or CJK heuristic
    - Japanese taxonomy: SENSORY_WORDS_JA, GENERIC_UI_NOUNS_JA, STOP_WORDS_JA
    - Japanese instruction detection via _INSTRUCTION_PATTERN_JA (no \b)
    - Japanese per-category regexes without word boundaries
    - Japanese sentence splitting on 。！？
    - Japanese meaningful-label check via remaining CJK content words
    - spaCy loader preserves parser pipe for Japanese (tokenization dependency)
    - _tokenize_sentences gains lang param + catches exceptions with regex fallback
    - _violations_133 / _violations_133_regex unified lang-aware path

Output:
    audit_sensory_report.csv  (written to output_dir)
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from ka11y.crawler.sensory_crawler import SensoryElementData

# ─────────────────────────────────────────────────────────────────────────────
# English sensory word taxonomy
# ─────────────────────────────────────────────────────────────────────────────

SENSORY_WORDS: Dict[str, Set[str]] = {
    "color": {
        "blue",
        "red",
        "green",
        "yellow",
        "orange",
        "purple",
        "pink",
        "black",
        "white",
        "grey",
        "gray",
        "cyan",
        "magenta",
        "brown",
        "violet",
        "indigo",
        "teal",
        "navy",
        "maroon",
        "gold",
        "silver",
        "colour",
        "color",
        "coloured",
        "colored",
        "highlighted",
    },
    "shape": {
        "round",
        "rounded",
        "square",
        "circular",
        "circle",
        "triangular",
        "triangle",
        "rectangular",
        "oval",
        "hexagonal",
        "diamond",
        "star",
        "star-shaped",
        "pill-shaped",
    },
    "size": {
        "big",
        "small",
        "large",
        "tiny",
        "huge",
        "little",
        "giant",
        "wide",
        "narrow",
        "tall",
        "short",
        "smaller",
        "larger",
        "biggest",
        "smallest",
    },
    "position": {
        "left",
        "right",
        "top",
        "bottom",
        "above",
        "below",
        "upper",
        "lower",
        "corner",
        "center",
        "centre",
        "middle",
        "side",
        "adjacent",
        "beside",
        "next",
        "nearby",
        "underneath",
        "beneath",
        "leftmost",
        "rightmost",
        "topmost",
        "down",
        "up",
        "under",
        "over",
        "inside",
        "outside",
    },
    "orientation": {
        "horizontal",
        "vertical",
        "landscape",
        "portrait",
        "clockwise",
        "counterclockwise",
        "upward",
        "downward",
    },
    "sound": {
        "beep",
        "chime",
        "bell",
        "tone",
        "sound",
        "audio",
        "alarm",
        "buzz",
        "ring",
        "ping",
        "notification",
    },
    "brightness": {
        "bright",
        "dark",
        "light",
        "dim",
        "shiny",
        "glowing",
        "faded",
        "vivid",
        "dull",
        "luminous",
        "darker",
        "lighter",
        "brighter",
    },
    "texture": {
        "rough",
        "smooth",
        "bumpy",
        "soft",
        "hard",
        "glossy",
        "matte",
        "textured",
        "patterned",
        "striped",
        "dotted",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Japanese sensory word taxonomy
# ─────────────────────────────────────────────────────────────────────────────

SENSORY_WORDS_JA: Dict[str, Set[str]] = {
    "color": {
        "赤",
        "青",
        "緑",
        "黄",
        "橙",
        "紫",
        "ピンク",
        "黒",
        "白",
        "灰色",
        "グレー",
        "金",
        "銀",
        "茶色",
        "水色",
        "藍",
        "紺",
        "赤い",
        "青い",
        "緑色",
        "黄色",
        "黄色い",
        "白い",
        "黒い",
        "色",
        "カラー",
        "色付き",
        "着色",
        "オレンジ",
        "ライトブルー",
    },
    "shape": {
        "丸",
        "丸い",
        "円",
        "円形",
        "四角",
        "四角い",
        "長方形",
        "三角",
        "三角形",
        "楕円",
        "星形",
        "ハート形",
        "形",
        "形状",
        "正方形",
        "六角形",
        "ひし形",
    },
    "size": {
        "大きい",
        "小さい",
        "巨大",
        "細い",
        "太い",
        "長い",
        "短い",
        "広い",
        "狭い",
        "大きな",
        "小さな",
        "サイズ",
        "大",
        "小",
        "大型",
        "小型",
        "大きめ",
        "小さめ",
    },
    "position": {
        "左",
        "右",
        "上",
        "下",
        "中央",
        "中心",
        "隣",
        "横",
        "上部",
        "下部",
        "左側",
        "右側",
        "真ん中",
        "そば",
        "近く",
        "内側",
        "外側",
        "左上",
        "右上",
        "左下",
        "右下",
        "手前",
        "奥",
        "前",
        "後ろ",
        "端",
        "角",
        "隅",
    },
    "orientation": {
        "横向き",
        "縦向き",
        "水平",
        "垂直",
        "時計回り",
        "反時計回り",
        "横",
        "縦",
        "斜め",
        "傾き",
    },
    "sound": {
        "ビープ",
        "チャイム",
        "音",
        "通知音",
        "アラーム",
        "ベル",
        "着信音",
        "サウンド",
        "音声",
        "ブザー",
        "効果音",
    },
    "brightness": {
        "明るい",
        "暗い",
        "光る",
        "輝く",
        "鮮やか",
        "くすんだ",
        "明度",
        "輝度",
        "明るめ",
        "暗め",
        "ぼんやり",
    },
    "texture": {
        "滑らか",
        "粗い",
        "ざらざら",
        "つるつる",
        "光沢",
        "マット",
        "テクスチャ",
        "縞模様",
        "水玉",
        "格子",
    },
}

# Flattened sets for quick membership tests
ALL_SENSORY_EN: Set[str] = set().union(*SENSORY_WORDS.values())
ALL_SENSORY_JA: Set[str] = set().union(*SENSORY_WORDS_JA.values())
ALL_SENSORY: Set[str] = ALL_SENSORY_EN  # backward-compat alias

# ─────────────────────────────────────────────────────────────────────────────
# English instruction vocabulary
# ─────────────────────────────────────────────────────────────────────────────

IMPERATIVE_VERBS: Set[str] = {
    "click",
    "press",
    "tap",
    "select",
    "choose",
    "go",
    "refer",
    "find",
    "see",
    "use",
    "follow",
    "navigate",
    "scroll",
    "drag",
    "hover",
    "open",
    "close",
    "expand",
    "collapse",
    "toggle",
    "submit",
    "enter",
    "fill",
    "type",
    "search",
    "pick",
    "hit",
    "push",
    "check",
    "uncheck",
    "enable",
    "disable",
    "tick",
    "mark",
    "focus",
    "locate",
    "identify",
}

GENERIC_UI_NOUNS: Set[str] = {
    "button",
    "icon",
    "link",
    "item",
    "element",
    "option",
    "control",
    "widget",
    "field",
    "area",
    "section",
    "menu",
    "panel",
    "bar",
    "box",
    "container",
    "form",
    "checkbox",
    "radio",
    "radiobutton",
    "dropdown",
    "select",
    "listbox",
    "textbox",
    "textfield",
    "input",
    "tab",
    "arrow",
    "step",
    "card",
    "dialog",
}

STOP_WORDS: Set[str] = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "you",
    "your",
    "his",
    "her",
    "its",
    "our",
    "their",
    "will",
    "can",
    "may",
    "must",
    "should",
    "some",
    "any",
    "all",
    "each",
    "every",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "is",
    "are",
    "was",
    "were",
    "please",
    "kindly",
    "just",
    "now",
    "simply",
    "merely",
    "be",
    "been",
    "being",
    "as",
    "if",
    "when",
    "then",
    "there",
    "here",
    "shown",
    "show",
    "displayed",
    "display",
    "indicated",
    "indicate",
    "marked",
    "mark",
    "located",
    "positioned",
    "placed",
    "highlighted",
    "required",
    "optional",
}

# ─────────────────────────────────────────────────────────────────────────────
# Japanese instruction vocabulary
# ─────────────────────────────────────────────────────────────────────────────

GENERIC_UI_NOUNS_JA: Set[str] = {
    "ボタン",
    "アイコン",
    "リンク",
    "項目",
    "要素",
    "オプション",
    "コントロール",
    "ウィジェット",
    "フィールド",
    "エリア",
    "セクション",
    "メニュー",
    "パネル",
    "バー",
    "ボックス",
    "コンテナ",
    "フォーム",
    "チェックボックス",
    "ラジオボタン",
    "ドロップダウン",
    "テキストボックス",
    "入力欄",
    "タブ",
    "矢印",
    "ステップ",
    "カード",
    "ダイアログ",
    "モーダル",
    "スイッチ",
    "スライダー",
    "トグル",
    "アコーディオン",
    "セレクトボックス",
}

STOP_WORDS_JA: Set[str] = {
    "の",
    "に",
    "は",
    "を",
    "が",
    "で",
    "て",
    "と",
    "も",
    "な",
    "い",
    "た",
    "か",
    "ら",
    "れ",
    "さ",
    "り",
    "る",
    "ます",
    "です",
    "ある",
    "いる",
    "する",
    "なる",
    "から",
    "まで",
    "より",
    "ため",
    "こと",
    "もの",
    "ところ",
    "とき",
    "ように",
    "ください",
    "して",
    "でき",
    "あり",
    "これ",
    "それ",
    "あの",
    "この",
    "その",
    "など",
    "という",
    "ており",
    "てい",
}

# Minimum text length to bother analysing
_MIN_TEXT_LEN = 5
_MIN_TEXT_LEN_CJK = 2  # CJK characters carry more meaning per character

# ─────────────────────────────────────────────────────────────────────────────
# CJK / language detection helpers
# ─────────────────────────────────────────────────────────────────────────────

_CJK_CHAR_RE = re.compile(r"[\u3000-\u9fff\uff00-\uffef\u3400-\u4dbf]")


def _is_cjk_text(text: str) -> bool:
    """Return True when ≥15% of characters are CJK (Japanese/Chinese/Korean)."""
    if not text:
        return False
    cjk = sum(1 for c in text if _CJK_CHAR_RE.match(c))
    return cjk / max(len(text), 1) >= 0.15


def _detect_lang(element: SensoryElementData) -> str:
    """
    Return a 2-character language code for the element.

    Priority:
      1. element.lang attribute (set by crawler from closest lang= ancestor)
      2. CJK character-density heuristic across all text fields
      3. Default: 'en'
    """
    lang = (getattr(element, "lang", None) or "").strip().lower()
    if lang:
        return lang[:2]
    all_text = " ".join(
        filter(
            None,
            [
                element.text,
                element.aria_label,
                getattr(element, "title", None),
            ],
        )
    )
    if _is_cjk_text(all_text):
        return "ja"
    return "en"


# ─────────────────────────────────────────────────────────────────────────────
# ALL module-level regex patterns — defined here so every function below can
# reference them at call time without forward-reference issues.
# ─────────────────────────────────────────────────────────────────────────────

# ── English patterns (use \b word boundaries) ────────────────────────────────

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

# English sentence splitter
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# English imperative: start-of-sentence instruction signal
_IMPERATIVE_RE = re.compile(
    r"^\s*(please|kindly|to|now|just)?\s*("
    + "|".join(
        re.escape(word) for word in sorted(IMPERATIVE_VERBS, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)

# Purposive phrase ("to continue processing", "to submit the form")
_PURPOSE_PHRASE_RE = re.compile(
    r"\bto\s+(?:continue|proceed|submit|complete|finish|save|confirm|cancel|"
    r"close|open|start|return|go\s+back|move\s+on)\b(?:\s+\w+){0,2}",
    re.IGNORECASE,
)

# English sensory word (used when stripping before label check)
_SENSORY_RE = re.compile(
    r"\b("
    + "|".join(re.escape(w) for w in sorted(ALL_SENSORY_EN, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Quoted text — English straight/curly quotes AND Japanese 「」 『』
_QUOTED_RE = re.compile(
    r"(?:"
    r'["\u201c\u201d\u2018\u2019].+?["\u201c\u201d\u2018\u2019]'  # English/curly
    r"|"
    r"[\u300c\u300e].+?[\u300d\u300f]"  # Japanese 「」『』
    r")"
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
for _w in list(GENERIC_UI_NOUNS):
    _GENERIC_TERMS.add(_pluralize(_w))

_GENERIC_RE = re.compile(
    r"\b("
    + "|".join(
        re.escape(word) for word in sorted(_GENERIC_TERMS, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)

# English per-category regexes (with \b word boundaries)
_CATEGORY_REGEXES: Dict[str, re.Pattern[str]] = {
    cat: re.compile(
        r"\b("
        + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        + r")\b",
        re.IGNORECASE,
    )
    for cat, words in SENSORY_WORDS.items()
}

# ── Japanese patterns (NO \b — word boundaries do not work for CJK) ──────────

# Japanese sentence splitter: split on Japanese full-stop punctuation
_SENT_SPLIT_JA_RE = re.compile(r"(?<=[。！？])\s*")

# ── Japanese instruction patterns split into two separate regexes ─────────────
#
# Detection vs. stripping are in tension for words like 確認 (confirm) or
# 送信 (submit) which are ALSO common button-label nouns.
#
# _INSTRUCTION_SIGNAL_JA — broad, used only to DETECT that a sentence is
#   instructional.  Includes bare action nouns (確認, 選択, …) so that
#   "確認してください" fires even when re.search finds just the noun first.
#
# _INSTRUCTION_STRIP_JA  — conservative, used inside _has_meaningful_label_text_ja
#   to STRIP instruction tokens before checking what meaningful label words
#   remain.  Requires a verb suffix for ambiguous action nouns so that a bare
#   "確認" (= "Confirm" button label) is NOT stripped and can serve as a label.

_INSTRUCTION_SIGNAL_JA = re.compile(
    r"("
    r"してください|して下さい|しましょう|してみてください|してみて|"
    r"クリック(?:して|する|してください|します|しろ)?|"
    r"タップ(?:して|する|してください|します)?|"
    r"押して(?:ください|みて)?|押す|"
    r"選択(?:して|する|してください|します)?|"
    r"入力(?:して|する|してください|します)?|"
    r"検索(?:して|する|してください|します)?|"
    r"スクロール(?:して|する|してください)?|"
    r"ドラッグ(?:して|する|してください)?|"
    r"移動(?:して|する|してください)?|"
    r"開いて(?:ください)?|開く|"
    r"閉じて(?:ください)?|閉じる|"
    r"送信(?:して|する|してください)?|"
    r"確認(?:して|する|してください)?|"
    r"記入(?:して|する|してください)?|"
    r"チェック(?:して|する|してください)?|"
    r"有効(?:に)?(?:して|する)|無効(?:に)?(?:して|する)|"
    r"必須(?:項目|フィールド|入力|欄)?|"
    r"必要(?:です|な(?:項目|情報|フィールド|入力)?)?|"
    r"マークされた?|示された?|表示された?|強調された?"
    r")",
)

_INSTRUCTION_STRIP_JA = re.compile(
    r"("
    r"してください|して下さい|しましょう|してみてください|してみて|"
    # Unambiguous action verbs — optional verb suffix (never standalone UI labels)
    r"クリック(?:して|する|してください|します|しろ)?|"
    r"タップ(?:して|する|してください|します)?|"
    r"押して(?:ください|みて)?|"  # te-form only; bare 押す can mean a push-label
    # Action verbs that also serve as UI labels — REQUIRE verb suffix to strip
    r"選択(?:して|する|してください|します)|"
    r"入力(?:して|する|してください|します)|"
    r"検索(?:して|する|してください|します)|"
    r"スクロール(?:して|する|してください)|"
    r"ドラッグ(?:して|する|してください)|"
    r"移動(?:して|する|してください)|"
    r"開いて(?:ください)?|"  # te-form only
    r"閉じて(?:ください)?|"  # te-form only
    r"送信(?:して|する|してください)|"  # require suffix
    r"確認(?:して|する|してください)|"  # require suffix (bare 確認 = "Confirm" label)
    r"記入(?:して|する|してください)|"
    r"チェック(?:して|する|してください)|"
    r"有効(?:に)?(?:して|する)|無効(?:に)?(?:して|する)|"
    r"必須(?:項目|フィールド|入力|欄)?|"
    r"必要(?:です|な(?:項目|情報|フィールド|入力)?)?|"
    r"マークされた?|示された?|表示された?|強調された?"
    r")",
)

# Keep a unified alias used in is_instruction_text_ja
_INSTRUCTION_PATTERN_JA = _INSTRUCTION_SIGNAL_JA

# Japanese sensory word matcher (no word boundaries)
_SENSORY_JA_RE = re.compile(
    "("
    + "|".join(re.escape(w) for w in sorted(ALL_SENSORY_JA, key=len, reverse=True))
    + ")",
)

# Japanese generic UI noun matcher (no word boundaries)
_GENERIC_JA_RE = re.compile(
    "("
    + "|".join(re.escape(w) for w in sorted(GENERIC_UI_NOUNS_JA, key=len, reverse=True))
    + ")",
)

# Japanese stop-word matcher (no word boundaries)
_STOP_WORDS_JA_RE = re.compile(
    "("
    + "|".join(re.escape(w) for w in sorted(STOP_WORDS_JA, key=len, reverse=True))
    + ")",
)

# Japanese per-category regexes (no \b)
_CATEGORY_REGEXES_JA: Dict[str, re.Pattern[str]] = {
    cat: re.compile(
        "("
        + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
        + ")",
    )
    for cat, words in SENSORY_WORDS_JA.items()
}


# ─────────────────────────────────────────────────────────────────────────────
# spaCy lazy-loader
# ─────────────────────────────────────────────────────────────────────────────

_nlp_cache: Dict[str, Any] = {}
_sudachi_tokenizer: Any = None


def _get_sudachi_tokenizer():
    """Lazy-load and cache the SudachiPy tokenizer for Japanese POS analysis."""
    global _sudachi_tokenizer
    if _sudachi_tokenizer is not None:
        return _sudachi_tokenizer
    try:
        import sudachipy  # type: ignore

        # Create once and cache. Dictionary().create() is expensive as it loads
        # system-wide dictionary files from disk.
        _sudachi_tokenizer = sudachipy.Dictionary().create()
        return _sudachi_tokenizer
    except Exception:
        return None


def _get_nlp(lang: str = "en"):
    """
    Load and cache a spaCy model for the given language.

    English  — en_core_web_sm  (parser disabled; sentencizer added)
    Japanese — ja_core_news_lg preferred (94%+ POS accuracy on web text),
               falls back to ja_core_news_sm; parser kept for tokenisation
    Others   — {lang}_core_news_sm with parser disabled
    """
    lang_key = (lang or "en")[:2]
    if lang_key in _nlp_cache:
        return _nlp_cache[lang_key]

    nlp = None
    try:
        import spacy  # type: ignore

        if lang_key == "en":
            disable = ["ner", "parser"]
            try:
                nlp = spacy.load("en_core_web_sm", disable=disable)
            except OSError:
                nlp = None
        elif lang_key == "ja":
            # Japanese needs tok2vec + morphologizer + parser for word segmentation.
            # Prefer the large model (higher POS accuracy); fall back to small.
            disable = ["ner"]
            for model_name in ("ja_core_news_lg", "ja_core_news_sm"):
                try:
                    nlp = spacy.load(model_name, disable=disable)
                    break
                except OSError:
                    continue
        else:
            disable = ["ner", "parser"]
            try:
                nlp = spacy.load(f"{lang_key}_core_news_sm", disable=disable)
            except OSError:
                nlp = None

        if nlp is not None:
            # Add a sentencizer only when no sentence-boundary component exists
            has_senter = any(p in nlp.pipe_names for p in ("sentencizer", "senter"))
            if not has_senter:
                nlp.add_pipe("sentencizer")
    except ImportError:
        nlp = None

    _nlp_cache[lang_key] = nlp
    return nlp


# ─────────────────────────────────────────────────────────────────────────────
# Sentence tokenisation helpers
# ─────────────────────────────────────────────────────────────────────────────


def _split_sentences_regex(text: str, lang: str = "en") -> List[str]:
    """Split *text* into sentences using pure regex (no spaCy required)."""
    if lang == "ja" or _is_cjk_text(text):
        parts = _SENT_SPLIT_JA_RE.split(text)
    else:
        parts = _SENT_SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _tokenize_sentences(text: str, nlp: Any, lang: str = "en") -> List[Any]:
    """
    Return sentence spans / strings for *text*.

    Uses spaCy when available; falls back to regex splitting (via
    _split_sentences_regex) on any failure so the auditor never crashes.
    """
    if nlp is not None:
        try:
            doc = nlp(text)
            sents = list(doc.sents)
            if sents:
                return sents
        except Exception:
            pass
    return _split_sentences_regex(text, lang)


def _sentence_text(sent: Any) -> str:
    return sent.text if hasattr(sent, "text") else str(sent)


# ─────────────────────────────────────────────────────────────────────────────
# Text-source iteration
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """NFKC-normalize text so that half-width katakana (ｶﾀｶﾅ) is converted
    to full-width (カタカナ) before any NLP matching step."""
    return unicodedata.normalize("NFKC", text)


def _iter_text_sources(element: SensoryElementData) -> List[str]:
    """
    Collect all text fields from an element, deduplicated, in priority order:
      visible text → aria-label → title tooltip → placeholder → value
    Text is NFKC-normalized so half-width katakana matches Japanese keyword lists.
    """
    sources: List[str] = []
    for raw in (
        element.text,
        element.aria_label,
        getattr(element, "title", None),  # tooltip — carries instructions
        getattr(element, "placeholder", None),
        getattr(element, "value", None),
    ):
        text = _normalize_text((raw or "").strip())
        if text and text not in sources:
            sources.append(text)
    return sources


# ─────────────────────────────────────────────────────────────────────────────
# Instruction detection
# ─────────────────────────────────────────────────────────────────────────────


def _is_instruction_text_ja(text: str) -> bool:
    """Return True if the Japanese text looks like an instruction."""
    return bool(_INSTRUCTION_PATTERN_JA.search(text))


def _is_instruction_text(text: str, lang: str = "en") -> bool:
    """
    Return True if *text* looks like an instruction (imperative or declarative).

    Supports both imperative commands ("Click the round button") and
    declarative guidance ("Required fields are marked in red"), plus
    Japanese instruction patterns when lang='ja' or CJK chars are detected.
    """
    text = text.strip()
    if not text:
        return False

    if lang == "ja" or _is_cjk_text(text):
        return _is_instruction_text_ja(text)

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


def _is_instruction(sent: Any, lang: str = "en") -> bool:
    return _is_instruction_text(_sentence_text(sent), lang)


# ─────────────────────────────────────────────────────────────────────────────
# Sensory category detection
# ─────────────────────────────────────────────────────────────────────────────


def _sensory_categories_in_text(text: str, lang: str = "en") -> List[str]:
    """
    Return list of sensory category names present in *text*.

    For Japanese / CJK text: uses the \b-free Japanese regexes first, then
    also checks English regexes for code-mixed content (e.g. "右の blue ボタン").
    """
    if lang == "ja" or _is_cjk_text(text):
        cats_ja = [cat for cat, pat in _CATEGORY_REGEXES_JA.items() if pat.search(text)]
        cats_en = [
            cat
            for cat, pat in _CATEGORY_REGEXES.items()
            if pat.search(text) and cat not in cats_ja
        ]
        return cats_ja + cats_en
    return [cat for cat, pat in _CATEGORY_REGEXES.items() if pat.search(text)]


def _sensory_categories_in_sent(sent: Any, lang: str = "en") -> List[str]:
    return _sensory_categories_in_text(_sentence_text(sent), lang)


# ─────────────────────────────────────────────────────────────────────────────
# Meaningful-label detection
# ─────────────────────────────────────────────────────────────────────────────


def _remaining_label_words(text: str) -> List[str]:
    """
    English: strip purposive phrases, sensory words, generic UI nouns, and
    imperative verbs; return any non-stop-word tokens that remain.
    A non-empty return means a non-sensory identifier is present.
    """
    stripped = _PURPOSE_PHRASE_RE.sub(" ", text)
    stripped = _SENSORY_RE.sub(" ", stripped)
    stripped = _GENERIC_RE.sub(" ", stripped)
    stripped = _IMPERATIVE_RE.sub(" ", stripped)

    remaining: List[str] = []
    for word in re.split(r"\W+", stripped):
        wl = word.lower()
        if not wl:
            continue
        if len(wl) <= 2 and not wl.isdigit():
            continue
        if wl in STOP_WORDS:
            continue
        remaining.append(wl)
    return remaining


def _has_meaningful_label_text_ja(text: str) -> bool:
    """
    Japanese: return True when a non-sensory, non-generic identifier exists.

    Tries SudachiPy morpheme-level POS filtering first (more accurate);
    falls back to the regex-strip approach when SudachiPy is unavailable.

    Example (PASS):  「送信」ボタンをクリック  → 送信 remains
    Example (FAIL):  赤いボタンをクリックして  → nothing meaningful remains
    """
    if _QUOTED_RE.search(text):
        return True

    tokenizer_obj = _get_sudachi_tokenizer()
    if tokenizer_obj:
        try:
            morphemes = tokenizer_obj.tokenize(text)
            for m in morphemes:
                pos0 = m.part_of_speech()[0]
                if pos0 not in ("名詞", "動詞", "形容詞", "形容動詞"):
                    continue
                surface = m.surface()
                if _SENSORY_JA_RE.search(surface):
                    continue
                if _GENERIC_JA_RE.search(surface):
                    continue
                if _STOP_WORDS_JA_RE.search(surface):
                    continue
                if _INSTRUCTION_STRIP_JA.search(surface):
                    continue
                if _CJK_CHAR_RE.search(surface) or re.search(r"[a-zA-Z]{3,}", surface):
                    return True
            return False
        except Exception:
            pass

    # Regex fallback when SudachiPy is not installed or fails
    stripped = _SENSORY_JA_RE.sub("", text)
    stripped = _GENERIC_JA_RE.sub("", stripped)
    stripped = _STOP_WORDS_JA_RE.sub("", stripped)
    stripped = _INSTRUCTION_STRIP_JA.sub("", stripped)
    stripped = re.sub(r"[\s。、！？・「」『』（）【】〔〕…—\-～＝＋]+", "", stripped)
    return bool(_CJK_CHAR_RE.search(stripped)) or bool(
        re.search(r"[a-zA-Z]{3,}", stripped)
    )


def _has_meaningful_label_text(text: str, lang: str = "en") -> bool:
    """
    Return True when *text* contains a non-sensory, non-generic noun that
    could serve as a real identifier for the referenced UI element.

    Quoted strings are always treated as meaningful regardless of language.
    """
    if _QUOTED_RE.search(text):
        return True
    if lang == "ja" or _is_cjk_text(text):
        return _has_meaningful_label_text_ja(text)
    return bool(_remaining_label_words(text))


def _has_meaningful_label(sent: Any, lang: str = "en") -> bool:
    return _has_meaningful_label_text(_sentence_text(sent), lang)


def _is_sensory_only(sent: Any, sensory_cats: List[str], lang: str = "en") -> bool:
    """
    True when the sentence has ≥1 sensory word AND no meaningful non-sensory label.
    (sensory_cats is assumed non-empty at call site.)
    """
    return not _has_meaningful_label(sent, lang)


# ─────────────────────────────────────────────────────────────────────────────
# Per-element violation detector (spaCy path)
# ─────────────────────────────────────────────────────────────────────────────


# Tags / roles whose accessible names count as page-level "labelled controls"
# the user can find by name — so a sensory token that IS a labelled name is
# not a sensory-only reference.
_FOCUSABLE_TAGS_FOR_NAME_CORPUS = {
    "button", "a", "input", "select", "textarea", "option",
}
_FOCUSABLE_ROLES_FOR_NAME_CORPUS = {
    "button", "link", "checkbox", "radio", "menuitem", "tab", "switch", "option",
}
_NAME_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _extract_sensory_tokens(text: str, lang: str = "en") -> Set[str]:
    """Return the set of sensory keywords that actually matched ``text``.

    Used to cross-check a flagged sentence against the page's labelled-control
    names: if every sensory token in the instruction is also the literal name
    of a focusable element on the same page, the instruction is *not*
    sensory-only ("Press the Red button" is fine if a button is labelled
    "Red").
    """
    tokens: Set[str] = set()

    def _add(matches: Iterable[Any]) -> None:
        for m in matches:
            if isinstance(m, tuple):
                m = next((x for x in m if x), "")
            if m:
                tokens.add(m.lower())

    if lang == "ja" or _is_cjk_text(text):
        for pat in _CATEGORY_REGEXES_JA.values():
            _add(pat.findall(text))
    for pat in _CATEGORY_REGEXES.values():
        _add(pat.findall(text))
    return tokens


def _build_labelled_name_corpus(
    elements: Iterable["SensoryElementData"],
) -> Set[str]:
    """Lowercased word-token corpus drawn from the labelled names of every
    focusable element seen on the audited pages. A sensory token in a flagged
    sentence is forgiven if every such token appears here."""
    corpus: Set[str] = set()
    for el in elements:
        tag = (getattr(el, "tag", "") or "").lower()
        role = (getattr(el, "role", "") or "").lower()
        if (
            tag not in _FOCUSABLE_TAGS_FOR_NAME_CORPUS
            and role not in _FOCUSABLE_ROLES_FOR_NAME_CORPUS
        ):
            continue
        for src in (
            getattr(el, "aria_label", None),
            getattr(el, "value", None),
            getattr(el, "text", None),
            getattr(el, "title", None),
        ):
            if not src:
                continue
            for tok in _NAME_WORD_RE.findall(src.lower()):
                # For CJK, even single characters carry enough meaning to serve
                # as a label (e.g. "赤" for red button, "上" for up).
                if len(tok) > 1 or (len(tok) == 1 and _is_cjk_text(tok)):
                    corpus.add(tok)
    return corpus


def _violations_133(
    element: SensoryElementData,
    nlp: Any,
    lang: str = "en",
    labelled_names: Optional[Set[str]] = None,
) -> List[Tuple[str, str, List[str], str]]:
    """
    Analyse one element's text for WCAG 1.3.3 violations.

    Returns a list of (sentence_text, message, sensory_categories, status)
    tuples for each instructional sentence found.  Status is "FAILED" or "PASSED".

    When ``labelled_names`` is supplied (a token corpus from
    :func:`_build_labelled_name_corpus`), a sentence that would otherwise be
    flagged as sensory-only is downgraded to ``PASSED`` if every detected
    sensory token also appears in the corpus — meaning the page has a
    focusable element literally named by that token.
    """
    min_len = _MIN_TEXT_LEN_CJK if lang == "ja" else _MIN_TEXT_LEN
    texts_to_check = [
        t for t in _iter_text_sources(element) if len(t.strip()) >= min_len
    ]
    if not texts_to_check:
        return []

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts_to_check:
        sents = _tokenize_sentences(src_text, nlp, lang)

        for sent in sents:
            sent_text = _sentence_text(sent)
            if len(sent_text.strip()) < min_len:
                continue

            if not _is_instruction(sent, lang):
                continue

            sensory_cats = _sensory_categories_in_sent(sent, lang)
            if not sensory_cats:
                continue

            if _is_sensory_only(sent, sensory_cats, lang):
                if labelled_names:
                    sent_tokens = _extract_sensory_tokens(sent_text, lang)
                    if sent_tokens and sent_tokens.issubset(labelled_names):
                        msg = (
                            "1.3.3: Instruction mentions sensory term(s), but the "
                            "term(s) match the labelled name of a focusable control "
                            "on the page — user can locate it by name."
                        )
                        results.append((sent_text.strip(), msg, sensory_cats, "PASSED"))
                        continue
                cats_str = ", ".join(sensory_cats)
                msg = (
                    f"1.3.3: Instruction relies solely on sensory characteristic(s) "
                    f'[{cats_str}] — "{sent_text.strip()[:120]}" — '
                    f"add a non-sensory identifier (e.g. button label or heading text)."
                )
                results.append((sent_text.strip(), msg, sensory_cats, "FAILED"))
            else:
                msg = (
                    "1.3.3: Instruction contains sensory characteristic(s) "
                    "but also provides a non-sensory identifier."
                )
                results.append((sent_text.strip(), msg, sensory_cats, "PASSED"))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Auditor
# ─────────────────────────────────────────────────────────────────────────────


class SensoryCharacteristicsAuditor:
    """
    Runs WCAG 1.3.3 checks against a list of SensoryElementData records
    and writes audit_sensory_report.csv to output_dir.

    Language is detected per-element from the `lang` attribute recorded by
    the crawler (or inferred from CJK character density), so a single audit
    run handles mixed-language pages correctly.
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
        "selector",
        "element_ref_id",
        "frame_path",
        "html_snippet",
    ]

    def __init__(self, output_dir: str, lang: str = "en"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lang = lang  # default language when element has no lang attr

    def generate_audit_report(
        self,
        elements: List[SensoryElementData],
    ) -> List[Dict[str, Any]]:
        """
        Audit all elements, write CSV, return list of record dicts.

        Only elements that contain at least one instructional sentence with
        a sensory reference produce a row; others are silently skipped to
        keep the report focused on actionable issues.

        Language is resolved per element so multilingual pages are handled
        correctly without re-running the auditor.
        """
        records: List[Dict[str, Any]] = []

        # Build a single page-level labelled-name corpus once per audit run.
        # Used by both spaCy and regex paths to forgive instructions like
        # "Press the Red button" when a focusable element is literally
        # named "Red" (e.g. Red Hat product page).
        labelled_names = _build_labelled_name_corpus(elements)

        for el in elements:
            el_lang = _detect_lang(el) or self.lang
            nlp = _get_nlp(el_lang)

            viols = (
                _violations_133(el, nlp, el_lang, labelled_names=labelled_names)
                if nlp is not None
                else _violations_133_regex(el, el_lang, labelled_names=labelled_names)
            )

            if not viols:
                continue

            for sent_text, msg, cats, status in viols:
                records.append(
                    {
                        "page_url": el.page_url,
                        "element_tag": el.tag,
                        "element_id": el.element_id or "",
                        "sentence": sent_text[:300],
                        "sensory_categories": ", ".join(cats),
                        "wcag_1_3_3_status": status,
                        "wcag_1_3_3_violation": msg if status == "FAILED" else "",
                        "overall_status": status,
                        "selector": el.selector or "",
                        "element_ref_id": el.element_ref_id or "",
                        "frame_path": el.frame_path or "",
                        "html_snippet": el.html[:400],
                    }
                )

        total_elements_checked = len(elements)
        total_violations = sum(1 for r in records if r["overall_status"] == "FAILED")
        unique_pages = len(
            {r["page_url"] for r in records if r["overall_status"] == "FAILED"}
        )

        csv_path = self.output_dir / "audit_sensory_report.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
            writer.writeheader()
            writer.writerows(records)
            writer.writerow({f: "" for f in self.CSV_FIELDS})

            summary: Dict[str, Any] = {f: "" for f in self.CSV_FIELDS}
            summary.update(
                {
                    "page_url": "── SUMMARY ──",
                    "element_tag": f"Elements checked : {total_elements_checked}",
                    "element_id": f"Violations found : {total_violations}",
                    "sentence": f"Affected pages : {unique_pages}",
                    "wcag_1_3_3_status": "FAILED" if total_violations > 0 else "PASSED",
                    "overall_status": "FAILED" if total_violations > 0 else "PASSED",
                }
            )
            writer.writerow(summary)

        print(
            f"[SensoryAuditor] audit_sensory_report.csv → {csv_path}  "
            f"({total_elements_checked} elements | {total_violations} violation(s) | "
            f"{unique_pages} page(s) affected)"
        )
        return records

    @staticmethod
    def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = sum(1 for r in records if r["overall_status"] == "FAILED")
        pages = len(
            {
                r.get("page_url", "")
                for r in records
                if r.get("overall_status") == "FAILED"
            }
        )
        categories: Dict[str, int] = {}
        for r in records:
            if r.get("overall_status") == "FAILED":
                for cat in (r.get("sensory_categories") or "").split(", "):
                    cat = cat.strip()
                    if cat:
                        categories[cat] = categories.get(cat, 0) + 1
        return {
            "total_violations": total,
            "affected_pages": pages,
            "by_sensory_category": categories,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pure-regex fallback (no spaCy)
# ─────────────────────────────────────────────────────────────────────────────


def _violations_133_regex(
    element: SensoryElementData,
    lang: str = "en",
    labelled_names: Optional[Set[str]] = None,
) -> List[Tuple[str, str, List[str], str]]:
    """
    Pure-regex fallback when spaCy is unavailable.
    Less accurate (no morphological analysis) but zero-dependency.
    Supports both English and Japanese via _split_sentences_regex.

    See :func:`_violations_133` for the meaning of ``labelled_names``.
    """
    min_len = _MIN_TEXT_LEN_CJK if lang == "ja" else _MIN_TEXT_LEN
    texts = [t for t in _iter_text_sources(element) if len(t) >= min_len]

    results: List[Tuple[str, str, List[str], str]] = []

    for src_text in texts:
        for sent_text in _split_sentences_regex(src_text, lang):
            sent_text = sent_text.strip()
            if len(sent_text) < min_len:
                continue

            if not _is_instruction_text(sent_text, lang):
                continue

            cats = _sensory_categories_in_text(sent_text, lang)
            if not cats:
                continue

            has_label = _has_meaningful_label_text(sent_text, lang)

            if not has_label:
                if labelled_names:
                    sent_tokens = _extract_sensory_tokens(sent_text, lang)
                    if sent_tokens and sent_tokens.issubset(labelled_names):
                        msg = (
                            "1.3.3: Instruction mentions sensory term(s), but the "
                            "term(s) match the labelled name of a focusable control "
                            "on the page — user can locate it by name."
                        )
                        results.append((sent_text, msg, cats, "PASSED"))
                        continue
                msg = (
                    f"1.3.3: Instruction relies solely on sensory characteristic(s) "
                    f"[{', '.join(cats)}] — \"{sent_text[:120]}\" — "
                    f"add a non-sensory identifier (e.g. button label or heading text)."
                )
                results.append((sent_text, msg, cats, "FAILED"))
            else:
                msg = (
                    "1.3.3: Instruction contains sensory characteristic(s) "
                    "but also provides a non-sensory identifier."
                )
                results.append((sent_text, msg, cats, "PASSED"))

    return results
