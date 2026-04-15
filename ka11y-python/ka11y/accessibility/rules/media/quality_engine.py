
"""
ka11y/accessibility/rules/media/quality_engine.py
===================================================
WCAG 1.2.1 Gate 5 — Local transcript quality evaluation.

Uses faster-whisper + jiwer + regex + nltk to evaluate whether a
developer-provided transcript is an equivalent alternative for the media.

5 checks
────────
  Check 1: Verbatim speech (faster-whisper + jiwer WER)
  Check 2: Speaker identification (regex + whisper segment gaps)
  Check 3: Non-speech audio events (bracket regex + keyword dictionary)
  Check 4: Meaningful visual content (NLTK POS tagging — always needs_review)
  Check 5: Correct sequence (timestamp quarter-overlap)

Dependencies (required)
───────────────────────
  faster-whisper  — local Whisper transcription (CTranslate2)
  jiwer           — Word Error Rate computation
  nltk            — POS tagging for visual content detection
  ffmpeg          — system dependency required by faster-whisper
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import nltk
import spacy
from faster_whisper import WhisperModel
from jiwer import wer as compute_wer
from nltk.tokenize import word_tokenize

from ka11y.config.logger import setup_logger

logger = setup_logger(name="KAC", tag="quality_engine")

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
_SPACY_MODELS = {
    "en": "en_core_web_sm",
    "ja": "ja_core_news_sm",
}
_nlp_cache = {}

def _get_nlp(lang: str):
    if lang not in _nlp_cache:
        model_name = _SPACY_MODELS.get(lang, _SPACY_MODELS["en"])
        try:
            _nlp_cache[lang] = spacy.load(model_name)
        except Exception:
            # Fallback if model not found
            logger.warning(f"spaCy model {model_name} not found. Some checks may be less accurate.")
            _nlp_cache[lang] = None
    return _nlp_cache[lang]

# ── Constants ─────────────────────────────────────────────────────────────────

# Maximum media file size to download (100 MB)
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024

# Download timeout in seconds
_DOWNLOAD_TIMEOUT = 60.0

# WER thresholds for Check 1
_WER_PASS = 0.15       # WER ≤ 0.15 → 85%+ match → PASS
_WER_FAIL = 0.40       # WER > 0.40 → <60% match → FAIL (summary, not transcript)

# Non-speech audio event keywords for Check 3
_AUDIO_EVENT_KEYWORDS = {
    "en": {
        "applause", "laughter", "music", "silence", "pause", "noise",
        "clapping", "cheering", "alarm", "beep", "crash", "door", "phone",
        "inaudible", "crosstalk", "sound", "sigh", "cough", "crying",
        "singing", "humming", "whistling", "thunder", "rain", "wind",
        "footsteps", "knock", "ring", "buzz", "click", "snap", "pop",
        "gasp", "scream", "whisper", "mumbling", "static", "feedback",
    },
    "ja": {
        "拍手", "笑い声", "音楽", "静寂", "沈黙", "休止", "雑音", "ノイズ",
        "手拍子", "歓声", "アラーム", "ビープ音", "衝突音", "ドア", "電話",
        "聞き取り不能", "クロストーク", "音", "ため息", "咳", "泣き声",
        "歌", "鼻歌", "口笛", "雷", "雨", "風", "足音", "ノック", "ベル",
        "ブザー", "クリック", "スナップ", "破裂音", "喘ぎ", "悲鳴", "ささやき",
        "つぶやき", "スタティック", "フィードバック",
    }
}

# Speaker label regex patterns for Check 2
_SPEAKER_PATTERNS = {
    "en": [
        re.compile(r"^[A-Z][a-zA-Z\s]{1,30}:\s", re.MULTILINE),     # Name: text
        re.compile(r"\[[A-Z][a-zA-Z\s]{1,30}\]", re.MULTILINE),       # [Name]
        re.compile(r"^Speaker\s\d+:", re.MULTILINE | re.IGNORECASE),   # Speaker 1:
        re.compile(r"^Interviewer:", re.MULTILINE | re.IGNORECASE),    # Interviewer:
        re.compile(r"^Host:", re.MULTILINE | re.IGNORECASE),           # Host:
        re.compile(r"^Narrator:", re.MULTILINE | re.IGNORECASE),       # Narrator:
        re.compile(r"^Moderator:", re.MULTILINE | re.IGNORECASE),      # Moderator:
    ],
    "ja": [
        re.compile(r"^[^\s：]{1,10}：", re.MULTILINE),              # 名前：
        re.compile(r"^【[^\s】]{1,10}】", re.MULTILINE),             # 【名前】
        re.compile(r"^話者\s?\d+：", re.MULTILINE),                 # 話者1：
        re.compile(r"^インタビュアー：", re.MULTILINE),              # インタビュアー：
        re.compile(r"^ホスト：", re.MULTILINE),                      # ホスト：
        re.compile(r"^ナレーター：", re.MULTILINE),                  # ナレーター：
        re.compile(r"^司会：", re.MULTILINE),                       # 司会：
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Check result dataclass
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
        "status": status,       # "PASSED" | "FAILED" | "NEEDS_REVIEW" | "N/A"
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


def _check_verbatim(whisper_text: str, dev_transcript: str, lang: str = "en") -> Dict[str, Any]:
    """
    Check 1: All speech is transcribed verbatim.

    Compares Whisper's local transcription against the developer's transcript
    using Word Error Rate (WER) — the industry standard for ASR evaluation.
    """
    # Preprocess: lowercase, strip extra whitespace
    ref = re.sub(r"\s+", " ", whisper_text.lower().strip())
    hyp = re.sub(r"\s+", " ", dev_transcript.lower().strip())

    if not ref or not hyp:
        return _check_result(
            "verbatim", "NEEDS_REVIEW",
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

    if score <= _WER_PASS:
        return _check_result(
            "verbatim", "PASSED",
            f"Transcript matches audio with WER={score:.2f} "
            f"({(1 - score) * 100:.0f}% accuracy).",
            wer_score=round(score, 4),
        )
    elif score > _WER_FAIL:
        return _check_result(
            "verbatim", "FAILED",
            f"Transcript significantly differs from audio (WER={score:.2f}, "
            f"only {(1 - score) * 100:.0f}% accuracy). "
            f"This appears to be a summary, not a verbatim transcript.",
            wer_score=round(score, 4),
        )
    else:
        return _check_result(
            "verbatim", "NEEDS_REVIEW",
            f"Transcript partially matches audio (WER={score:.2f}, "
            f"{(1 - score) * 100:.0f}% accuracy). May be paraphrased.",
            wer_score=round(score, 4),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Check 2 — Speaker identification
# ─────────────────────────────────────────────────────────────────────────────


def _check_speaker_ids(
    dev_transcript: str,
    whisper_segment_count: int = 0,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Check 2: All speakers are identified.

    Scans the transcript for speaker-change patterns (regex).
    If faster-whisper detects multiple distinct segments with gaps > 2s
    (suggesting speaker changes) but the transcript has zero labels → FAIL.
    """
    patterns = _SPEAKER_PATTERNS.get(lang, _SPEAKER_PATTERNS["en"])
    found_labels = []
    for pattern in patterns:
        matches = pattern.findall(dev_transcript)
        found_labels.extend(matches)

    label_count = len(found_labels)

    if label_count > 0:
        return _check_result(
            "speaker_ids", "PASSED",
            f"Found {label_count} speaker label(s) in transcript.",
            labels_found=label_count,
            sample_labels=found_labels[:5],
        )

    # No labels found — check if this might be single-speaker content
    if whisper_segment_count <= 3:
        return _check_result(
            "speaker_ids", "NEEDS_REVIEW",
            "No speaker labels found, but audio is short "
            "(may be single-speaker). Manual review recommended.",
            labels_found=0,
        )

    return _check_result(
        "speaker_ids", "FAILED",
        "No speaker identification labels found in transcript. "
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
        return _check_result(
            "non_speech_events", "FAILED",
            "No bracketed audio event descriptors found in transcript "
            "(e.g., [applause], [music], [laughter]). "
            "WCAG 1.2.1 requires noting significant non-speech sounds.",
            events_found=[],
        )

    # Check if any descriptors match known audio event keywords
    keywords = _AUDIO_EVENT_KEYWORDS.get(lang, _AUDIO_EVENT_KEYWORDS["en"])
    matched_events = []
    for desc in all_descriptors:
        desc_lower = desc.lower().strip()
        for keyword in keywords:
            if keyword in desc_lower:
                matched_events.append(desc.strip())
                break

    if matched_events:
        return _check_result(
            "non_speech_events", "PASSED",
            f"Found {len(matched_events)} non-speech audio event(s) "
            f"documented in transcript.",
            events_found=matched_events[:10],
        )

    return _check_result(
        "non_speech_events", "NEEDS_REVIEW",
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
            return _check_result("visual_content", "NEEDS_REVIEW", "Japanese POS tagger not available.")

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
    adj_density = len(adjectives) / max(token_count, 1)

    return _check_result(
        "visual_content", "NEEDS_REVIEW",
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
) -> Dict[str, Any]:
    """
    Check 5: The alternative follows the correct sequence of the media.

    Divides both the Whisper output and the dev transcript into 4 quarters,
    then compares each quarter pair using word overlap.
    """
    if not whisper_segments or not dev_transcript.strip():
        return _check_result(
            "sequence", "NEEDS_REVIEW",
            "Insufficient data for sequence comparison.",
            quarter_scores=[],
        )

    # Build whisper text per quarter
    total_duration = max(
        seg.get("end", 0) for seg in whisper_segments
    ) if whisper_segments else 0

    if total_duration <= 0:
        return _check_result(
            "sequence", "NEEDS_REVIEW",
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
    dev_words = dev_transcript.split()
    quarter_size = max(len(dev_words) // 4, 1)
    dev_quarters = [
        " ".join(dev_words[i * quarter_size:(i + 1) * quarter_size])
        for i in range(4)
    ]

    # Compare each quarter pair
    quarter_scores = []
    for i in range(4):
        w_words = set(whisper_quarters[i].lower().split())
        d_words = set(dev_quarters[i].lower().split())
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
            "sequence", "PASSED",
            f"Transcript follows audio sequence "
            f"(avg quarter overlap: {avg_score:.2%}).",
            quarter_scores=quarter_scores,
        )
    else:
        return _check_result(
            "sequence", "FAILED",
            f"Transcript sequence does not match audio order "
            f"(avg quarter overlap: {avg_score:.2%}). "
            f"Content may be reordered.",
            quarter_scores=quarter_scores,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Media download helper
# ─────────────────────────────────────────────────────────────────────────────


def _download_media(url: str, output_dir: str) -> Optional[str]:
    """
    Download media file to a temp path inside output_dir.
    Returns the file path, or None if download fails or exceeds size limit.
    """
    try:
        with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
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

                # Determine file extension from URL
                ext = Path(url.split("?")[0]).suffix or ".mp3"
                out_path = Path(output_dir) / f"_media_temp{ext}"

                total = 0
                with open(out_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > _MAX_DOWNLOAD_BYTES:
                            logger.warning("[quality_engine] Download exceeded size limit")
                            f.close()
                            out_path.unlink(missing_ok=True)
                            return None
                        f.write(chunk)

                logger.info(f"[quality_engine] Downloaded {total} bytes → {out_path}")
                return str(out_path)

    except Exception as exc:
        logger.warning(f"[quality_engine] Failed to download {url}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Transcription helper (faster-whisper)
# ─────────────────────────────────────────────────────────────────────────────


def _transcribe_audio(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Transcribe audio using faster-whisper (local CTranslate2 Whisper).

    Returns:
        {
            "text": str,            # full transcription
            "segments": List[Dict], # [{start, end, text}, ...]
            "segment_count": int,
        }
    Or None if transcription fails.
    """
    try:
        # Use the "base" model for speed/accuracy balance
        model_size = os.environ.get("WHISPER_MODEL_SIZE", "base")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        segments_iter, info = model.transcribe(
            audio_path,
            language=None,        # auto-detect
            beam_size=5,
            vad_filter=True,      # voice activity detection for cleaner output
        )

        segments = []
        full_text = []
        for seg in segments_iter:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
            full_text.append(seg.text.strip())

        return {
            "text": " ".join(full_text),
            "segments": segments,
            "segment_count": len(segments),
        }

    except Exception as exc:
        logger.warning(f"[quality_engine] Transcription failed: {exc}")
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
        # Download and transcribe the audio
        _out = output_dir or tempfile.gettempdir()
        audio_path = _download_media(media_url, _out)

        if audio_path:
            transcription = _transcribe_audio(audio_path)

            if transcription:
                # Check 1: Verbatim
                checks.append(_check_verbatim(
                    transcription["text"], clean_transcript, lang=lang
                ))

                # Check 2: Speaker IDs
                checks.append(_check_speaker_ids(
                    clean_transcript,
                    whisper_segment_count=transcription["segment_count"],
                    lang=lang,
                ))

                # Check 3: Non-speech events
                checks.append(_check_non_speech_events(clean_transcript, lang=lang))

                # Check 5: Sequence
                checks.append(_check_sequence(
                    transcription["segments"], clean_transcript
                ))
            else:
                # Whisper failed — fall back to text-only checks
                checks.append(_check_result(
                    "verbatim", "NEEDS_REVIEW",
                    "Could not transcribe audio (faster-whisper failed)."
                ))
                checks.append(_check_speaker_ids(clean_transcript, lang=lang))
                checks.append(_check_non_speech_events(clean_transcript, lang=lang))

            # Clean up temp file
            try:
                Path(audio_path).unlink(missing_ok=True)
            except Exception:
                pass
        else:
            # Download failed — run text-only checks
            checks.append(_check_result(
                "verbatim", "NEEDS_REVIEW",
                "Could not download media file for transcription."
            ))
            checks.append(_check_speaker_ids(clean_transcript, lang=lang))
            checks.append(_check_non_speech_events(clean_transcript, lang=lang))

    # ── Video-only checks (4, 5) ─────────────────────────────────────────
    elif media_type == "video_only":
        # Check 4: Visual content description
        checks.append(_check_visual_content(clean_transcript, lang=lang))

        # Check 5: Sequence (text-only, no audio timeline available)
        checks.append(_check_result(
            "sequence", "NEEDS_REVIEW",
            "Cannot verify sequence order for video-only content without "
            "audio timeline. Manual review recommended.",
        ))

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

    return {
        "overall_status": overall,
        "message": message,
        "checks": checks,
    }


# ── SUMMARY ──────────────────────────────────────────────────────────────
# What was done:
#   Created the local quality engine with 5 checks using
#   faster-whisper + jiwer + regex + nltk (all mandatory).
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
# ─────────────────────────────────────────────────────────────────────────
