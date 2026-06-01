import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from wordfreq import word_frequency

from ka11y.crawler.navigation import navigate_with_resilience
from ka11y.crawler.browser_pool import leased_context
from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="unusual_words")

MIN_TERM_LENGTH = 4
MAX_CONTEXT_DISTANCE = 2

EXPLANATION_PATTERNS = [
    r"{term}\s+is\s+(?:a|an|the)",
    r"{term}\s+refers\s+to",
    r"{term}\s+means",
    r"{term}\s*,\s+(?:a|an|the)",
    r"{term}\s*\((.*?)\)",
    r"(?:a|an|the)\s+(.*?)\s+called\s+{term}",
    r"{term}\s+stands\s+for",
    r"{term}\s+can\s+be\s+defined\s+as",
]

# NLP Models Singletons
_nlp = None
_keybert = None

def get_nlp_models():
    global _nlp, _keybert
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    if _keybert is None:
        from sentence_transformers import SentenceTransformer
        from keybert import KeyBERT
        embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        _keybert = KeyBERT(model=embedding_model)
    return _nlp, _keybert

@dataclass
class Candidate:
    term: str
    category: str
    confidence: float
    frequency_score: float
    occurrences: int
    explained: bool
    explanation_method: str | None
    context: str
    needs_human_review: bool

async def fetch_page(context, url: str) -> tuple[str, str]:
    page = await context.new_page()
    try:
        await navigate_with_resilience(page, url)
        await page.wait_for_timeout(2000)
        html = await page.content()
        title = await page.title()
        return html, title
    except Exception as e:
        logger.error(f"Error fetching page {url}: {e}")
        return "", ""
    finally:
        await page.close()

def extract_content(html: str):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "footer", "nav", "aside", "iframe"]):
        tag.decompose()

    blocks = []
    for el in soup.find_all(["p", "li", "article", "section", "main", "td", "th", "div"]):
        text = el.get_text(" ", strip=True)
        if len(text.split()) >= 5:
            blocks.append(text)
    full_text = "\n".join(blocks)
    return {
        "soup": soup,
        "blocks": blocks,
        "full_text": full_text,
    }

def extract_candidate_terms(text: str):
    nlp_model, keybert_model = get_nlp_models()
    doc = nlp_model(text)
    candidates = set()

    # noun chunks
    for chunk in doc.noun_chunks:
        phrase = chunk.text.strip()
        if len(phrase) >= MIN_TERM_LENGTH:
            candidates.add(phrase)

    # named entities
    for ent in doc.ents:
        if len(ent.text) >= MIN_TERM_LENGTH:
            candidates.add(ent.text)

    # YAKE keywords
    import yake
    kw_extractor = yake.KeywordExtractor(
        lan="en",
        n=3,
        top=50,
    )
    try:
        keywords = kw_extractor.extract_keywords(text)
        for kw, score in keywords:
            if len(kw) >= MIN_TERM_LENGTH:
                candidates.add(kw)
    except Exception:
        pass

    # KeyBERT phrases
    try:
        keywords = keybert_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 3),
            stop_words="english",
            top_n=50,
        )
        for kw, score in keywords:
            if len(kw) >= MIN_TERM_LENGTH:
                candidates.add(kw)
    except Exception:
        pass

    return sorted(candidates), doc

def should_skip(term: str):
    term = term.strip()
    if len(term) < MIN_TERM_LENGTH:
        return True
    if len(term.split()) > 6:
        return True
    if re.match(r"^[0-9]+$", term):
        return True
    # common English word
    if word_frequency(term.lower(), "en") > 1e-3:
        return True
    return False

def technicality_score(term: str):
    score = 0.0
    term_lower = term.lower()
    freq = word_frequency(term_lower, "en")

    # rarity
    if freq < 1e-6:
        score += 0.35
    elif freq < 1e-5:
        score += 0.25
    elif freq < 1e-4:
        score += 0.15

    # acronym
    if re.match(r"^[A-Z]{2,}$", term):
        score += 0.25

    # phrase
    if len(term.split()) >= 2:
        score += 0.15

    # technical morphology
    suffixes = [
        "ization",
        "isation",
        "ology",
        "metry",
        "omics",
        "graphy",
        "scopy",
        "ware",
        "protocol",
        "framework",
        "architecture",
    ]
    for suf in suffixes:
        if term_lower.endswith(suf):
            score += 0.20
            break

    # long term
    if len(term) > 15:
        score += 0.10

    return round(min(score, 1.0), 3)

def sentence_window(sentences: list[str], term: str, radius: int = 2):
    windows = []
    term_lower = term.lower()
    for i, sent_text in enumerate(sentences):
        if term_lower in sent_text.lower():
            start = max(0, i - radius)
            end = min(len(sentences), i + radius + 1)
            window = " ".join(sentences[start:end])
            windows.append(window)
    return windows

def detect_inline_explanation(term: str, sentences: list[str]):
    windows = sentence_window(sentences, term)
    for window in windows:
        escaped = re.escape(term)
        for pattern in EXPLANATION_PATTERNS:
            regex = pattern.format(term=escaped)
            if re.search(regex, window, re.I):
                return True, "inline_explanation", window[:500]
    if windows:
        return False, None, windows[0][:500]
    return False, None, ""

def detect_definition_mechanism(term: str, indexed_data: dict):
    term_lower = term.lower()
    # abbr / dfn
    for tag_name, text in indexed_data["defs"]:
        if term_lower in text:
            return True, tag_name
    # glossary links
    for text in indexed_data["links"]:
        if term_lower in text:
            return True, "glossary_link"
    # aria-describedby
    for text in indexed_data["aria"]:
        if term_lower in text:
            return True, "aria-describedby"
    return False, None

def categorize_term(term: str):
    if re.match(r"^[A-Z]{2,}$", term):
        return "abbreviation"
    if len(term.split()) >= 2:
        return "technical_phrase"
    return "unusual_word"

async def analyze_wcag_313(start_url) -> dict:
    start_time = time.time()
    
    async with leased_context(
        viewport={
            "width": 1400,
            "height": 900
        }
    ) as context:
        html, title = await fetch_page(context, start_url)

    if not html:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "Unable to fetch start page to extract content.",
            "details": {}
        }

    extracted = extract_content(html)
    soup = extracted["soup"]
    text = extracted["full_text"]

    raw_candidates, doc = extract_candidate_terms(text)
    sentences = [s.text for s in doc.sents]

    # Pre-index DOM elements for definition detection
    indexed_data = {
        "defs": [],
        "links": [],
        "aria": []
    }

    for tag in soup.find_all(["abbr", "dfn"]):
        indexed_data["defs"].append((tag.name, tag.get_text(strip=True).lower()))

    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(k in href for k in ["glossary", "definition", "terms", "lexicon"]):
            indexed_data["links"].append(a.get_text(strip=True).lower())

    for el in soup.find_all(attrs={"aria-describedby": True}):
        indexed_data["aria"].append(el.get_text(" ", strip=True).lower())

    analyzed = []
    for term in raw_candidates:
        if should_skip(term):
            continue

        term_lower = term.lower()
        freq = word_frequency(term_lower, "en")
        occurrences = len(re.findall(re.escape(term), text, re.I))
        score = technicality_score(term)

        explained_inline, method, ctx = detect_inline_explanation(term, sentences)
        explained_glossary, glossary_method = detect_definition_mechanism(term, indexed_data)

        explained = explained_inline or explained_glossary
        explanation_method = method or glossary_method

        confidence = score
        if occurrences >= 3:
            confidence += 0.10
        if occurrences >= 10:
            confidence += 0.10
        if explained:
            confidence *= 0.25

        confidence = round(min(confidence, 1.0), 3)

        candidate = Candidate(
            term=term,
            category=categorize_term(term),
            confidence=confidence,
            frequency_score=freq,
            occurrences=occurrences,
            explained=explained,
            explanation_method=explanation_method,
            context=ctx,
            needs_human_review=confidence >= 0.35,
        )
        analyzed.append(candidate)

    analyzed.sort(key=lambda x: x.confidence, reverse=True)
    findings = [asdict(c) for c in analyzed if c.needs_human_review]
    runtime = round(time.time() - start_time, 2)

    return {
        "status": "PASS" if not findings else "NEEDS_REVIEW",
        "reason": "Unexplained jargon/abbreviations found. Human review is recommended." if findings else "All detected complex terminology is properly explained.",
        "details": {
            "meta": {
                "url": start_url,
                "title": title,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "runtime_seconds": runtime
            },
            "summary": {
                "total_candidates": len(analyzed),
                "human_review_candidates": len(findings),
                "explained_terms": sum(1 for a in analyzed if a.explained),
                "unexplained_terms": sum(1 for a in analyzed if not a.explained),
            },
            "findings": findings
        }
    }
