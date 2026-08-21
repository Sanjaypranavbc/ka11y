"""
ka11y/accessibility/rules/media/quality_engine.py
===================================================
WCAG 1.2.1 Gate 5 — Transcript quality evaluation.

Uses Deepgram API + jiwer + regex + nltk to evaluate whether a
developer-provided transcript is an equivalent alternative for the media.

5 checks
────────
  Check 1: Verbatim speech (Deepgram Nova-2 + jiwer WER)
  Check 2: Speaker identification (regex + Deepgram diarization)
  Check 3: Non-speech audio events (bracket regex + keyword dictionary)
  Check 4: Meaningful visual content (NLTK POS tagging — always needs_review)
  Check 5: Correct sequence (timestamp quarter-overlap)

Dependencies (required)
───────────────────────
  deepgram-sdk  — Deepgram API client for transcription + diarization
  jiwer         — Word Error Rate computation
  nltk          — POS tagging for visual content detection
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import hashlib
from datetime import datetime
import httpx
import nltk
import spacy
from jiwer import wer as compute_wer
from nltk.tokenize import word_tokenize

from ka11y.config.logger import setup_logger
from ka11y.utils import not_implemented

logger = setup_logger(name="KAC", tag="quality_engine")


@not_implemented(
    reason=(
        "vision-model verification for transcript-to-video equivalence is "
        "reserved for a future implementation"
    )
)
def _verify_visual_equivalence_with_vision_model(
    *,
    media_url: str,
    transcript_text: str,
    lang: str = "en",
) -> Dict[str, Any]:
    """Reserved hook for future multimodal verification of video-only content."""


# ── Ensure required NLTK data is downloaded at import time ────────────────────
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)
try:
    nltk.data.find("taggers/averaged_perceptron_tagger_eng")
except LookupError:
    nltk.download("averaged_perceptron_tagger_eng", quiet=True)

# ── Load spaCy models ─────────────────────────────────────────────────────────
# Candidate spaCy models per language, tried in order. Japanese prefers the
# large model — that is what the Docker image installs (`spacy download
# ja_core_news_lg`) — and falls back to the small one if only it is present.
# English uses en_core_web_sm (also installed in the image).
_SPACY_MODELS = {
    "en": ("en_core_web_sm",),
    "ja": ("ja_core_news_lg", "ja_core_news_sm"),
}
_nlp_cache = {}


def _get_nlp(lang: str):
    if lang not in _nlp_cache:
        candidates = _SPACY_MODELS.get(lang, _SPACY_MODELS["en"])
        nlp = None
        for model_name in candidates:
            try:
                nlp = spacy.load(model_name)
                break
            except Exception:
                continue
        if nlp is None:
            logger.warning(
                f"No spaCy model available for lang='{lang}' "
                f"(tried {', '.join(candidates)}). Some checks may be less accurate."
            )
        _nlp_cache[lang] = nlp
    return _nlp_cache[lang]


# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum media file size to download (100 MB)
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

# Download timeout in seconds
_DOWNLOAD_TIMEOUT = 60.0

# WER thresholds for Check 1
# < 15%: Excellent (Pass)
# 15-40%: Moderate (Needs Review)
# > 40%: Poor (Fail)
_WER_PASS_THRESHOLD = 0.15
_WER_FAIL_THRESHOLD = 0.40


def _save_transcript_locally(text: str, media_url: str, output_dir: str = ""):
    """Save the raw Deepgram transcript to a local file for audit verification."""
    try:
        # Create storage path: output/transcripts/
        base_dir = Path(output_dir) if output_dir else Path.cwd()
        storage_dir = base_dir / "output" / "transcripts"
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: timestamp_md5(url).txt
        url_hash = hashlib.md5(media_url.encode()).hexdigest()[:10]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{url_hash}.txt"
        file_path = storage_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"Source URL: {media_url}\n")
            f.write(f"Audit Date: {datetime.now().isoformat()}\n")
            f.write("-" * 40 + "\n")
            f.write(text)

        logger.info(f"[quality_engine] Saved raw transcript to {file_path}")
        return str(file_path)
    except Exception as exc:
        logger.warning(f"[quality_engine] Failed to save transcript locally: {exc}")
        return None
_WER_PASS = 0.15  # WER ≤ 0.15 → 85%+ match → PASS
_WER_FAIL = 0.40  # WER > 0.40 → <60% match → FAIL (summary, not transcript)

# Non-speech audio event keywords for Check 3
_AUDIO_EVENT_KEYWORDS = {
    "en": {
        "applause",
        "laughter",
        "music",
        "silence",
        "pause",
        "noise",
        "clapping",
        "cheering",
        "alarm",
        "beep",
        "crash",
        "door",
        "phone",
        "inaudible",
        "crosstalk",
        "sound",
        "sigh",
        "cough",
        "crying",
        "singing",
        "humming",
        "whistling",
        "thunder",
        "rain",
        "wind",
        "footsteps",
        "knock",
        "ring",
        "buzz",
        "click",
        "snap",
        "pop",
        "gasp",
        "scream",
        "whisper",
        "mumbling",
        "static",
        "feedback",
    },
    "ja": {
        "拍手",
        "笑い声",
        "音楽",
        "静寂",
        "沈黙",
        "休止",
        "雑音",
        "ノイズ",
        "手拍子",
        "歓声",
        "アラーム",
        "ビープ音",
        "衝突音",
        "ドア",
        "電話",
        "聞き取り不能",
        "クロストーク",
        "音",
        "ため息",
        "咳",
        "泣き声",
        "歌",
        "鼻歌",
        "口笛",
        "雷",
        "雨",
        "風",
        "足音",
        "ノック",
        "ベル",
        "ブザー",
        "クリック",
        "スナップ",
        "破裂音",
        "喘ぎ",
        "悲鳴",
        "ささやき",
        "つぶやき",
        "スタティック",
        "フィードバック",
    },
}

# Speaker label regex patterns for Check 2
_SPEAKER_PATTERNS = {
    "en": [
        re.compile(r"^[A-Z][a-zA-Z\s]{1,30}:\s", re.MULTILINE),  # Name: text
        re.compile(r"\[[A-Z][a-zA-Z\s]{1,30}\]", re.MULTILINE),  # [Name]
        re.compile(r"^Speaker\s\d+:", re.MULTILINE | re.IGNORECASE),  # Speaker 1:
        re.compile(r"^Interviewer:", re.MULTILINE | re.IGNORECASE),  # Interviewer:
        re.compile(r"^Host:", re.MULTILINE | re.IGNORECASE),  # Host:
        re.compile(r"^Narrator:", re.MULTILINE | re.IGNORECASE),  # Narrator:
        re.compile(r"^Moderator:", re.MULTILINE | re.IGNORECASE),  # Moderator:
    ],
    "ja": [
        re.compile(r"^[^\s：]{1,10}：", re.MULTILINE),  # 名前：
        re.compile(r"^【[^\s】]{1,10}】", re.MULTILINE),  # 【名前】
        re.compile(r"^話者\s?\d+：", re.MULTILINE),  # 話者1：
        re.compile(r"^インタビュアー：", re.MULTILINE),  # インタビュアー：
        re.compile(r"^ホスト：", re.MULTILINE),  # ホスト：
        re.compile(r"^ナレーター：", re.MULTILINE),  # ナレーター：
        re.compile(r"^司会：", re.MULTILINE),  # 司会：
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Check result model
# ─────────────────────────────────────────────────────────────────────────────


def _check_result(
    check_name: str,
    status: str,
    message: str,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a standardized check result dict."""
    return {
        "check": check_name,
        "status": status,  # "PASSED" | "FAILED" | "NEEDS_REVIEW" | "N/A"
        "message": message,
        **extra,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transcript preparation
# ─────────────────────────────────────────────────────────────────────────────


def _prepare_transcript(text: str, source_type: str) -> str:
    """
    Clean raw transcript text based on its source format.

    - "link"        : Assume HTML — strip tags
    - "track" / VTT : Strip timestamp lines and VTT headers
    - "inline"      : Pass through as-is
    - "aria_describedby" : Pass through as-is
    """
    if source_type == "link":
        # Strip HTML tags
        return re.sub(r"<[^>]+>", " ", text).strip()

    if source_type == "track":
        # Strip VTT/SRT headers and timestamp lines
        lines = text.split("\n")
        clean = []
        for line in lines:
            line = line.strip()
            # Skip VTT header
            if line.startswith("WEBVTT"):
                continue
            # Skip timestamp lines (00:00:00.000 --> 00:00:00.000)
            if re.match(r"\d{2}:\d{2}", line):
                continue
            # Skip sequence numbers (SRT format)
            if re.match(r"^\d+$", line):
                continue
            if line:
                clean.append(line)
        return " ".join(clean)

    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Check 1 — Verbatim speech
# ─────────────────────────────────────────────────────────────────────────────


def _check_verbatim(
    whisper_text: str, dev_transcript: str, lang: str = "en"
) -> Dict[str, Any]:
    """
    Check 1: All speech is transcribed verbatim.

    Compares Whisper's local transcription against the developer's transcript
    using Word Error Rate (WER) — the industry standard for ASR evaluation.
    """
    # Preprocess: lowercase, strip extra whitespace, and remove dots from acronyms
    def normalize(text):
        text = text.lower().strip()
        # Remove dots from acronyms (e.g., W.C.A.G. -> wcag)
        text = re.sub(r'(?<=\b[a-z])\.(?=[a-z]\b|[a-z]\s|\s|$)', '', text)
        return re.sub(r"\s+", " ", text)

    ref = normalize(whisper_text)
    hyp = normalize(dev_transcript)

    if not ref or not hyp:
        return _check_result(
            "verbatim",
            "NEEDS_REVIEW",
            "Insufficient text for comparison.",
            wer_score=None,
        )

    # For Japanese, we MUST tokenize into words/morphemes before computing WER
    # otherwise jiwer treats the entire string as one word (or fails).
    if lang == "ja":
        nlp = _get_nlp("ja")
        if nlp:
            ref = " ".join([t.text for t in nlp(ref)])
            hyp = " ".join([t.text for t in nlp(hyp)])
        else:
            # Fallback: character-level comparison if spaCy fails
            ref = " ".join(list(ref.replace(" ", "")))
            hyp = " ".join(list(hyp.replace(" ", "")))

    score = compute_wer(ref, hyp)

    # Threshold Explanation for UI
    metric_info = "Metrics: Excellent (<15%), Needs Review (15-40%), Poor (>40%)"

    if score <= _WER_PASS:
        return _check_result(
            "verbatim",
            "PASSED",
            f"Transcript matches audio accurately. (WER: {score:.2%}). {metric_info}",
            wer_score=round(score, 4),
        )
    elif score > _WER_FAIL:
        return _check_result(
            "verbatim",
            "FAILED",
            f"Transcript is highly inaccurate. (WER: {score:.2%}). {metric_info}",
            wer_score=round(score, 4),
        )
    else:
        return _check_result(
            "verbatim",
            "NEEDS_REVIEW",
            f"Transcript partially matches audio. (WER: {score:.2%}). {metric_info}",
            wer_score=round(score, 4),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — Speaker identification
# ─────────────────────────────────────────────────────────────────────────────


def _check_speaker_ids(
    dev_transcript: str,
    whisper_segment_count: int = 0,
    speaker_count: int = 0,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Check 2: All speakers are identified.

    Scans the transcript for speaker-change patterns (regex).
    If Deepgram detects multiple distinct speakers (speaker_count > 1)
    but the transcript has zero labels → FAIL.
    """
    if lang not in _SPEAKER_PATTERNS:
        # Only "en"/"ja" have real pattern tables. Silently falling back to
        # the English patterns here would run Latin-script, capital-letter
        # regexes against a language that may have no case distinction at
        # all (e.g. Korean, Chinese) and never match — reporting correctly
        # labeled speakers as a confident FAILED. Without a pattern table
        # for this language, no automated verdict can be trusted.
        return _check_result(
            "speaker_ids", "NEEDS_REVIEW",
            f"Speaker-label detection is not supported for language '{lang}' "
            "(only English and Japanese pattern tables exist). Manual review required.",
            labels_found=0,
        )
    patterns = _SPEAKER_PATTERNS[lang]
    found_labels = []
    for pattern in patterns:
        matches = pattern.findall(dev_transcript)
        found_labels.extend(matches)

    label_count = len(found_labels)

    if label_count > 0:
        return _check_result(
            "speaker_ids",
            "PASSED",
            f"Found {label_count} speaker label(s) in transcript.",
            labels_found=label_count,
            sample_labels=found_labels[:5],
        )

    # No labels found — check if this might be single-speaker content
    if speaker_count <= 1:
        return _check_result(
            "speaker_ids", "NEEDS_REVIEW",
            "No speaker labels found, but audio only has 1 speaker detected. Manual review recommended.",
            labels_found=0,
        )

    return _check_result(
        "speaker_ids", "FAILED",
        f"No speaker identification labels found in transcript, but Deepgram detected {speaker_count} speakers. "
        "WCAG 1.2.1 requires identifying who is speaking "
        "when multiple speakers are present.",
        labels_found=0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 3 — Non-speech audio events
# ─────────────────────────────────────────────────────────────────────────────


def _check_non_speech_events(dev_transcript: str, lang: str = "en") -> Dict[str, Any]:
    """
    Check 3: All non-speech audio events are noted.

    Extracts text within square brackets [...] and parentheses (...),
    then checks for known audio event keywords.
    """
    # Extract all bracketed/parenthesized content
    # Also include Japanese brackets 【】 and （）
    bracketed = re.findall(r"[\[【]([^\]】]+)[\]】]", dev_transcript)
    parenthesized = re.findall(r"[\(（]([^\)）]+)[\)）]", dev_transcript)
    all_descriptors = bracketed + parenthesized

    if not all_descriptors:
        # This function only sees the developer-provided transcript text —
        # it has no signal about whether the *source audio* actually
        # contains any non-speech events worth noting (that would need
        # audio-event detection, not text analysis). Asserting FAILED
        # unconditionally here treated "no descriptors" as "must have
        # missed some", which tanks an accurate, fully-equivalent
        # transcript of e.g. a plainly-narrated article with no music/
        # sound effects in the source. Without evidence of what the audio
        # actually contains, this is a review item, not a confirmed defect.
        return _check_result(
            "non_speech_events",
            "NEEDS_REVIEW",
            "No bracketed audio event descriptors found in transcript "
            "(e.g., [applause], [music], [laughter]). WCAG 1.2.1 requires "
            "noting significant non-speech sounds — confirm whether the "
            "source audio has any that this transcript is missing.",
            events_found=[],
        )

    if lang not in _AUDIO_EVENT_KEYWORDS:
        # Only "en"/"ja" have real keyword tables — silently falling back to
        # English keywords would never match non-English event descriptors
        # and misreport them as unrecognised.
        return _check_result(
            "non_speech_events",
            "NEEDS_REVIEW",
            f"Found {len(all_descriptors)} bracketed descriptor(s), but "
            f"audio-event keyword matching is not supported for language "
            f"'{lang}' (only English and Japanese keyword lists exist). "
            "Manual review required.",
            events_found=[d.strip() for d in all_descriptors[:10]],
        )

    # Check if any descriptors match known audio event keywords
    keywords = _AUDIO_EVENT_KEYWORDS[lang]
    matched_events = []
    for desc in all_descriptors:
        desc_lower = desc.lower().strip()
        for keyword in keywords:
            if keyword in desc_lower:
                matched_events.append(desc.strip())
                break

    if matched_events:
        return _check_result(
            "non_speech_events",
            "PASSED",
            f"Found {len(matched_events)} non-speech audio event(s) "
            f"documented in transcript.",
            events_found=matched_events[:10],
        )

    return _check_result(
        "non_speech_events",
        "NEEDS_REVIEW",
        f"Found {len(all_descriptors)} bracketed descriptor(s) but none "
        f"match known audio event keywords. Manual review needed.",
        events_found=[d.strip() for d in all_descriptors[:10]],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 4 — Meaningful visual content (video-only)
# ─────────────────────────────────────────────────────────────────────────────


def _check_visual_content(dev_transcript: str, lang: str = "en") -> Dict[str, Any]:
    """
    Check 4: All meaningful visual content is described (video-only).

    Uses POS tagging to detect action verbs and descriptive language.
    """
    if lang == "ja":
        nlp = _get_nlp("ja")
        if not nlp:
            return _check_result(
                "visual_content", "NEEDS_REVIEW", "Japanese POS tagger not available."
            )

        doc = nlp(dev_transcript[:2000])
        action_verbs = [t.text for t in doc if t.pos_ == "VERB"]
        adjectives = [t.text for t in doc if t.pos_ == "ADJ"]
        token_count = len(doc)
    else:
        tokens = word_tokenize(dev_transcript[:2000])  # Limit to avoid slow POS
        tagged = nltk.pos_tag(tokens)

        # Count action verbs (VBG = gerund, VBZ = 3rd person, VBD = past)
        action_verbs = [word for word, tag in tagged if tag.startswith("VB")]
        # Count descriptive adjectives
        adjectives = [word for word, tag in tagged if tag.startswith("JJ")]
        token_count = len(tokens)

    verb_density = len(action_verbs) / max(token_count, 1)

    return _check_result(
        "visual_content",
        "NEEDS_REVIEW",
        f"Transcript contains {len(action_verbs)} action verb(s) and "
        f"{len(adjectives)} adjective(s). Verb density: {verb_density:.2%}. "
        f"Cannot verify visual accuracy without a vision model. "
        f"Manual review required.",
        verb_count=len(action_verbs),
        adjective_count=len(adjectives),
        verb_density=round(verb_density, 4),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Check 5 — Correct sequence
# ─────────────────────────────────────────────────────────────────────────────


def _check_sequence(
    whisper_segments: List[Dict[str, Any]],
    dev_transcript: str,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Check 5: The alternative follows the correct sequence of the media.

    Divides both the Whisper output and the dev transcript into 4 quarters,
    then compares each quarter pair using word overlap.
    """
    if not whisper_segments or not dev_transcript.strip():
        return _check_result(
            "sequence",
            "NEEDS_REVIEW",
            "Insufficient data for sequence comparison.",
            quarter_scores=[],
        )

    # Build whisper text per quarter
    total_duration = (
        max(seg.get("end", 0) for seg in whisper_segments) if whisper_segments else 0
    )

    if total_duration <= 0:
        return _check_result(
            "sequence",
            "NEEDS_REVIEW",
            "Cannot determine audio duration for sequence analysis.",
            quarter_scores=[],
        )

    quarter_duration = total_duration / 4
    whisper_quarters = ["", "", "", ""]
    for seg in whisper_segments:
        start = seg.get("start", 0)
        quarter_idx = min(int(start / quarter_duration), 3)
        whisper_quarters[quarter_idx] += " " + seg.get("text", "")

    # Divide dev transcript into 4 quarters by word count
    if lang == "ja":
        nlp = _get_nlp("ja")
        if nlp:
            dev_words = [t.text for t in nlp(dev_transcript)]
            whisper_quarter_words = [
                [t.text for t in nlp(wq)] for wq in whisper_quarters
            ]
        else:
            dev_words = list(dev_transcript.replace(" ", ""))
            whisper_quarter_words = [
                list(wq.replace(" ", "")) for wq in whisper_quarters
            ]
    else:
        dev_words = dev_transcript.split()
        whisper_quarter_words = [wq.split() for wq in whisper_quarters]

    quarter_size = max(len(dev_words) // 4, 1)
    dev_quarters = [
        " ".join(dev_words[i * quarter_size : (i + 1) * quarter_size]) for i in range(4)
    ]

    # Compare each quarter pair
    quarter_scores = []
    for i in range(4):
        w_words = set(w.lower() for w in whisper_quarter_words[i])
        d_words = set(
            d.lower() for d in dev_words[i * quarter_size : (i + 1) * quarter_size]
        )
        if not w_words or not d_words:
            quarter_scores.append(0.0)
            continue
        overlap = len(w_words & d_words)
        total = len(w_words | d_words)
        score = overlap / total if total else 0.0
        quarter_scores.append(round(score, 4))

    avg_score = sum(quarter_scores) / len(quarter_scores) if quarter_scores else 0

    if avg_score >= 0.30:
        return _check_result(
            "sequence",
            "PASSED",
            f"Transcript follows audio sequence "
            f"(avg quarter overlap: {avg_score:.2%}).",
            quarter_scores=quarter_scores,
        )
    else:
        return _check_result(
            "sequence",
            "FAILED",
            f"Transcript sequence does not match audio order "
            f"(avg quarter overlap: {avg_score:.2%}). "
            f"Content may be reordered.",
            quarter_scores=quarter_scores,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Media download helper
# ─────────────────────────────────────────────────────────────────────────────


def _download_media(url: str, output_dir: str, media_type: str = "audio") -> Optional[str]:
    """
    Download media file to a temp path inside output_dir.
    Returns the file path, or None if download fails or exceeds size limit.
    """
    try:
        # Prevent 403 blocks from CDNs like Wikimedia by spoofing a browser user-agent
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True, headers=headers) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()

                # Check content-length header
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > _MAX_DOWNLOAD_BYTES:
                    logger.warning(
                        f"[quality_engine] Media file too large: "
                        f"{int(content_length)} bytes > {_MAX_DOWNLOAD_BYTES} limit"
                    )
                    return None

                # Determine file extension and final storage path
                ext = Path(url.split("?")[0]).suffix or ".mp3"
                
                base_dir = Path(output_dir) if output_dir else Path.cwd()
                sub_folder = "video" if "video" in media_type.lower() else "audio"
                media_dir = base_dir / "output" / "media" / sub_folder
                media_dir.mkdir(parents=True, exist_ok=True)

                url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{timestamp}_{url_hash}{ext}"
                out_path = media_dir / filename

                total = 0
                with open(out_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > _MAX_DOWNLOAD_BYTES:
                            logger.warning(
                                "[quality_engine] Download exceeded size limit"
                            )
                            f.close()
                            return None
                        f.write(chunk)

                logger.info(f"[quality_engine] Downloaded {total} bytes → {out_path}")
                return str(out_path)

    except Exception as exc:
        logger.warning(f"[quality_engine] Failed to download {url}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Transcription helper (Deepgram API)
# ─────────────────────────────────────────────────────────────────────────────


def _transcribe_audio(audio_path: str, media_url: str = "unknown_url", output_dir: str = "") -> Optional[Dict[str, Any]]:
    """
    Transcribe audio using Deepgram SDK.

    Returns:
        {
            "text": str,            # full transcription
            "segments": List[Dict], # [{start, end, text, speaker}, ...]
            "segment_count": int,
            "speaker_count": int,
        }
    Or None if transcription fails or API key is missing.
    """
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        logger.warning("[quality_engine] DEEPGRAM_API_KEY is not set. Cannot transcribe audio.")
        return None

    try:
        import httpx
        url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&utterances=true&diarize=true&punctuate=true"
        headers = {
            "Authorization": f"Token {api_key}"
        }
        
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        with httpx.Client(timeout=120) as client:
            resp = client.post(url, headers=headers, content=audio_data)
        
        resp.raise_for_status()
        data = resp.json()
        
        results = data.get("results", {})
        utterances = results.get("utterances", [])
        
        transcript_data = None
        if not utterances:
            channels = results.get("channels", [])
            if not channels:
                logger.warning("[quality_engine] Deepgram returned no channels.")
                return None
            alts = channels[0].get("alternatives", [])
            if not alts:
                return None
            text = alts[0].get("transcript", "")
            transcript_data = {
                "text": text,
                "segments": [],
                "segment_count": 0,
                "speaker_count": 0,
            }
        else:
            segments = []
            full_text = []
            unique_speakers = set()

            for u in utterances:
                speaker = u.get("speaker", 0)
                segments.append({
                    "start": u.get("start", 0),
                    "end": u.get("end", 0),
                    "text": u.get("transcript", "").strip(),
                    "speaker": speaker,
                })
                full_text.append(u.get("transcript", "").strip())
                unique_speakers.add(speaker)

            transcript_data = {
                "text": " ".join(full_text),
                "segments": segments,
                "segment_count": len(segments),
                "speaker_count": len(unique_speakers),
            }

        # Save locally for verification
        if transcript_data and transcript_data["text"]:
            _save_transcript_locally(transcript_data["text"], media_url, output_dir) 

        return transcript_data

    except Exception as exc:
        logger.warning(f"[quality_engine] Transcription failed via Deepgram API: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_transcript_quality(
    *,
    media_url: str,
    transcript_text: str,
    transcript_type: str = "link",
    media_type: str = "audio_only",
    output_dir: str = "",
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Gate 5 orchestrator: run all applicable quality checks.

    Parameters
    ----------
    media_url : str
        URL of the audio/video file to transcribe.
    transcript_text : str
        The developer-provided transcript text or URL.
    transcript_type : str
        How the transcript was found: "link", "track", "inline", "aria_describedby"
    media_type : str
        "audio_only" or "video_only" — determines which checks run.
    output_dir : str
        Directory for temporary file downloads.
    lang : str
        Language code ("en", "ja", etc.)

    Returns
    -------
    Dict with overall_status, message, and individual check results.
    """
    # Prepare the transcript text
    clean_transcript = _prepare_transcript(transcript_text, transcript_type)

    if not clean_transcript or len(clean_transcript.strip()) < 10:
        return {
            "overall_status": "NEEDS_REVIEW",
            "message": "Transcript text is too short or empty for quality evaluation.",
            "checks": [],
        }

    checks: List[Dict[str, Any]] = []

    # ── Audio-only checks (1, 2, 3, 5) ───────────────────────────────────
    if media_type == "audio_only":
        # Save media to output/media/
        audio_path = _download_media(media_url, output_dir, media_type=media_type)

        if audio_path:
            transcription = _transcribe_audio(audio_path, media_url=media_url, output_dir=output_dir)

            if transcription:
                # Check 1: Verbatim
                checks.append(
                    _check_verbatim(transcription["text"], clean_transcript, lang=lang)
                )

                # Check 2: Speaker IDs
                checks.append(_check_speaker_ids(
                    clean_transcript,
                    whisper_segment_count=transcription["segment_count"],
                    speaker_count=transcription.get("speaker_count", 0),
                    lang=lang,
                ))

                # Check 3: Non-speech events
                checks.append(_check_non_speech_events(clean_transcript, lang=lang))

                # Check 5: Sequence
                checks.append(
                    _check_sequence(
                        transcription["segments"], clean_transcript, lang=lang
                    )
                )
            else:
                # Deepgram failed — fall back to text-only checks
                checks.append(_check_result(
                    "verbatim", "NEEDS_REVIEW",
                    "Could not transcribe audio (Deepgram failed or key missing)."
                ))
                checks.append(_check_speaker_ids(clean_transcript, lang=lang))
                checks.append(_check_non_speech_events(clean_transcript, lang=lang))

            # Clean up temp file
            # Note: We NO LONGER unlink/delete audio_path as requested.
            pass
        else:
            # Download failed — run text-only checks
            checks.append(
                _check_result(
                    "verbatim",
                    "NEEDS_REVIEW",
                    "Could not download media file for transcription.",
                )
            )
            checks.append(_check_speaker_ids(clean_transcript, lang=lang))
            checks.append(_check_non_speech_events(clean_transcript, lang=lang))

    # ── Video-only checks (4, 5) ─────────────────────────────────────────
    elif media_type == "video_only":
        # Check 4: Visual content description
        checks.append(_check_visual_content(clean_transcript, lang=lang))

        # Check 5: Sequence (text-only, no audio timeline available)
        checks.append(
            _check_result(
                "sequence",
                "NEEDS_REVIEW",
                "Cannot verify sequence order for video-only content without "
                "audio timeline. Manual review recommended.",
            )
        )

    # ── Determine overall status ─────────────────────────────────────────
    statuses = [c["status"] for c in checks]

    if any(s == "FAILED" for s in statuses):
        overall = "FAILED"
        failed_checks = [c["check"] for c in checks if c["status"] == "FAILED"]
        message = f"Quality check(s) failed: {', '.join(failed_checks)}."
    elif all(s == "PASSED" for s in statuses):
        overall = "PASSED"
        message = "All quality checks passed."
    else:
        overall = "NEEDS_REVIEW"
        review_checks = [c["check"] for c in checks if c["status"] == "NEEDS_REVIEW"]
        message = f"Quality check(s) require manual review: {', '.join(review_checks)}."

    # Extract WER for diagnostics
    verbatim_check = next((c for c in checks if c["check"] == "verbatim"), None)
    wer_score = verbatim_check.get("wer_score") if verbatim_check else None

    return {
        "overall_status": overall,
        "message": message,
        "checks": checks,
        "wer_score": wer_score,
        "wer_thresholds": "Excellent < 15%, Moderate 15-40%, Poor > 40%"
    }


def evaluate_captions_quality(
    *,
    media_url: str,
    caption_text: str,
    output_dir: str = "",
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Evaluates 1.2.2 Synchronized Captions against Deepgram ground truth transcript.
    """
    if not caption_text or len(caption_text.strip()) < 5:
        return {
            "overall_status": "NEEDS_REVIEW",
            "message": "Caption text is too short or empty for quality evaluation.",
            "deepgram_transcript": None,
            "wer_score": None,
        }

    audio_path = _download_media(media_url, output_dir, media_type="video")

    if not audio_path:
        return {
            "overall_status": "NEEDS_REVIEW",
            "message": "Could not download media file for transcription.",
            "deepgram_transcript": None,
            "wer_score": None,
        }

    transcription = _transcribe_audio(audio_path, media_url=media_url, output_dir=output_dir)
    
    # Note: We NO LONGER unlink/delete audio_path as requested.
    pass

    if not transcription:
        return {
            "overall_status": "NEEDS_REVIEW",
            "message": "Could not transcribe audio (Deepgram failed or key missing).",
            "deepgram_transcript": None,
            "wer_score": None,
        }

    ground_truth = transcription["text"]
    
    try:
        from jiwer import wer, Compose, ToLowerCase, RemovePunctuation, RemoveWhiteSpace
        import string
        
        # Build simple cleaner if jiwer doesn't provide these specific transforms out of box
        def clean_text(text):
            text = text.lower()
            text = text.translate(str.maketrans('', '', string.punctuation))
            return " ".join(text.split())
            
        gt_clean = clean_text(ground_truth)
        caption_clean = clean_text(caption_text)
        
        if not gt_clean.strip():
            if not caption_clean.strip():
                 status = "PASSED"
                 msg = "No speech detected in audio, and no captions provided."
                 error_rate = 0.0
            else:
                 status = "NEEDS_REVIEW"
                 msg = "No speech detected, but captions exist (possibly sound effects). Manual review recommended."
                 error_rate = None
        else:
            error_rate = wer(gt_clean, caption_clean)

            # Threshold Explanation for UI
            metric_info = "Metrics: Excellent (<15%), Needs Review (15-40%), Poor (>40%)"

            # `<=` to match `_check_verbatim`'s `_WER_PASS` boundary — the
            # two functions previously used different operators (`<` here
            # vs `<=` there) at the *same* documented 15% threshold, so a
            # caption/transcript at exactly 15% WER got PASSED from one
            # check and NEEDS_REVIEW from the other for an identical score.
            if error_rate <= _WER_PASS:
                status = "PASSED"
                msg = f"Captions match audio accurately. (WER: {error_rate:.1%}). {metric_info}"
            elif error_rate > 0.40:
                status = "FAILED"
                msg = f"Captions are highly inaccurate. (WER: {error_rate:.1%}). {metric_info}"
            else:
                status = "NEEDS_REVIEW"
                msg = f"Captions match partially. (WER: {error_rate:.1%}). Manual review recommended. {metric_info}"
            
        return {
            "overall_status": status,
            "message": msg,
            "deepgram_transcript": ground_truth,
            "wer_score": float(error_rate) if error_rate is not None else None
        }
    except Exception as exc:
        logger.error(f"[quality_engine] WER calculation failed: {exc}")
        return {
            "overall_status": "NEEDS_REVIEW",
            "message": "Failed to compute Word Error Rate.",
            "deepgram_transcript": ground_truth,
            "wer_score": None,
        }


# ── SUMMARY ──────────────────────────────────────────────────────────────
# What was done:
#   Created the quality engine with 5 checks using
#   Deepgram API + jiwer + regex + nltk.
#
# Principles applied:
#   - SoC: Each check is an independent function.
#   - KISS: Simple threshold-based pass/fail logic.
#   - DRY: _check_result factory avoids repeated dict construction.
#   - Testability: Each check function can be unit-tested independently.
#
# Edge cases handled:
#   - Media file too large → skip download, run text-only checks
#   - Download failure → run text-only checks
#   - Empty transcript → NEEDS_REVIEW
#   - Audio-only vs Video-only → different checks applied
#   - Missing DEEPGRAM_API_KEY → graceful fallback to text-only checks
# ─────────────────────────────────────────────────────────────────────────
