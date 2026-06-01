import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ka11y.accessibility.rules.language import unusual_words
from ka11y.api.v1.combined.findings import _unusual_words_to_findings

def test_should_skip():
    # Very short
    assert unusual_words.should_skip("abc") is True
    # Too long
    assert unusual_words.should_skip("this is a very long phrase that should be skipped") is True
    # Digits
    assert unusual_words.should_skip("12345") is True
    # Common English words (high word frequency)
    assert unusual_words.should_skip("about") is True
    assert unusual_words.should_skip("would") is True
    # Rarity (should not skip)
    assert unusual_words.should_skip("cryptocurrency") is False

def test_technicality_score():
    # Rarity score + suffixes + length
    score = unusual_words.technicality_score("unusualology")
    assert score > 0.0

def test_sentence_window():
    sentences = [
        "First sentence.",
        "Second sentence with cryptography in it.",
        "Third sentence.",
        "Fourth sentence."
    ]
    window = unusual_words.sentence_window(sentences, "cryptography", radius=1)
    assert len(window) == 1
    assert "First sentence" not in window[0]
    assert "Second sentence with cryptography in it. Third sentence." in window[0]

def test_detect_inline_explanation():
    sentences1 = [
        "A widget stands for a small gadget or component."
    ]
    explained, method, context = unusual_words.detect_inline_explanation("widget", sentences1)
    assert explained is True
    assert method == "inline_explanation"

    sentences2 = [
        "This page describes a widget."
    ]
    explained, method, context = unusual_words.detect_inline_explanation("widget", sentences2)
    assert explained is False

def test_detect_definition_mechanism():
    indexed_data = {
        "defs": [("dfn", "widget")],
        "links": ["definition of widget"],
        "aria": []
    }
    explained, method = unusual_words.detect_definition_mechanism("widget", indexed_data)
    assert explained is True
    assert method == "dfn"

def test_categorize_term():
    assert unusual_words.categorize_term("HTML") == "abbreviation"
    assert unusual_words.categorize_term("machine learning") == "technical_phrase"
    assert unusual_words.categorize_term("laryngitis") == "unusual_word"

def test_findings_converter_pass():
    report = {
        "status": "PASS",
        "reason": "All good",
        "details": {}
    }
    findings = _unusual_words_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "pass"
    assert findings[0]["wcag_sc"] == "3.1.3"
    assert findings[0]["rule_id"] == "python_3_1_3_unusual_words"

def test_findings_converter_review():
    report = {
        "status": "NEEDS_REVIEW",
        "reason": "Unexplained words",
        "details": {
            "findings": [
                {
                    "term": "cryptography",
                    "category": "technical_phrase",
                    "confidence": 0.8,
                    "frequency_score": 1e-7,
                    "occurrences": 3,
                    "explained": False,
                    "explanation_method": None,
                    "context": "cryptography is used...",
                    "needs_human_review": True
                }
            ]
        }
    }
    findings = _unusual_words_to_findings(report, "https://example.com")
    assert len(findings) == 1
    assert findings[0]["status"] == "needs_review"
    assert "cryptography" in findings[0]["reason"]

@pytest.mark.asyncio
async def test_analyze_wcag_313_runs_with_mocked_nlp():
    # Mock leased_context and fetch_page
    with patch("ka11y.accessibility.rules.language.unusual_words.leased_context") as mock_lease:
        mock_ctx = AsyncMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>This is some cryptography content.</body></html>")
        mock_page.title = AsyncMock(return_value="Cryptography")
        mock_ctx.new_page = AsyncMock(return_value=mock_page)
        mock_lease.return_value.__aenter__.return_value = mock_ctx

        # Mock extract_candidate_terms to return a fixed candidate without spaCy loading
        mock_doc = MagicMock()
        mock_doc.sents = [MagicMock(text="This is some cryptography content.")]
        with patch("ka11y.accessibility.rules.language.unusual_words.extract_candidate_terms", return_value=(["cryptography"], mock_doc)):
            res = await unusual_words.analyze_wcag_313("https://example.com")
            # Should run successfully
            assert res["status"] in ("PASS", "NEEDS_REVIEW")
