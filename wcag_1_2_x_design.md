# WCAG 1.2.x — Time-Based Media: Design & Architecture Document

> **Scope:** WCAG Success Criteria 1.2.1 through 1.2.5  
> **Status:** 1.2.1 — In Progress | 1.2.2–1.2.5 — Planned  
> **Last Updated:** 2026-03-31  
> **Authors:** ka11y-python team

---

## Table of Contents

1. [Overview](#1-overview)
2. [WCAG 1.2.1 — Audio-only and Video-only (Prerecorded)](#2-wcag-121--audio-only-and-video-only-prerecorded)
   - [2.1 What the Rule Requires](#21-what-the-rule-requires)
   - [2.2 Decision Tree (5 Gates)](#22-decision-tree-5-gates)
   - [2.3 Quality Equivalence Checks (Gate 5)](#23-quality-equivalence-checks-gate-5)
   - [2.4 Audio-only vs Video-only Check Matrix](#24-audio-only-vs-video-only-check-matrix)
3. [Tool Evaluation & Comparative Analysis](#3-tool-evaluation--comparative-analysis)
   - [3.1 Speech-to-Text Models](#31-speech-to-text-models)
   - [3.2 Transcript Scoring Methods](#32-transcript-scoring-methods)
   - [3.3 Structural Text Analysis](#33-structural-text-analysis)
   - [3.4 Video Frame Analysis (Multimodal)](#34-video-frame-analysis-multimodal)
4. [Final Technology Stack](#4-final-technology-stack)
   - [4.1 Chosen Stack & Justification](#41-chosen-stack--justification)
   - [4.2 Dependency Map](#42-dependency-map)
   - [4.3 Graceful Degradation Strategy](#43-graceful-degradation-strategy)
5. [Architecture & File Map](#5-architecture--file-map)
   - [5.1 System Flow Diagram](#51-system-flow-diagram)
   - [5.2 File Inventory](#52-file-inventory)
   - [5.3 Function Reference](#53-function-reference)
   - [5.4 Naming Conventions](#54-naming-conventions)
6. [WCAG 1.2.2 — Captions (Prerecorded)](#6-wcag-122--captions-prerecorded)
7. [WCAG 1.2.3 — Audio Description or Media Alternative](#7-wcag-123--audio-description-or-media-alternative)
8. [WCAG 1.2.4 — Captions (Live)](#8-wcag-124--captions-live)
9. [WCAG 1.2.5 — Audio Description (Prerecorded)](#9-wcag-125--audio-description-prerecorded)
10. [References](#10-references)

---

## 1. Overview

WCAG Guideline 1.2 covers **Time-Based Media** — audio, video, and combined audio-video content. The goal is to ensure that users who cannot perceive one modality (hearing or sight) have an equivalent alternative.

The 1.2.x criteria form a layered set of requirements:

| Criterion | Name | Level | Applies To |
|-----------|------|-------|-----------|
| **1.2.1** | Audio-only and Video-only (Prerecorded) | A | Audio-only OR video-only content |
| **1.2.2** | Captions (Prerecorded) | A | Synchronized media (audio + video) |
| **1.2.3** | Audio Description or Media Alternative | A | Synchronized media (video track) |
| **1.2.4** | Captions (Live) | AA | Live synchronized media |
| **1.2.5** | Audio Description (Prerecorded) | AA | Prerecorded synchronized media |

**Key architectural insight:** All 1.2.x criteria share the same crawler (media element detection) and the same quality engine (transcript/caption evaluation). The differences lie in which quality checks apply and what the pass/fail thresholds are. This document is structured so that each new criterion extends the shared infrastructure rather than rebuilding it.

---

## 2. WCAG 1.2.1 — Audio-only and Video-only (Prerecorded)

### 2.1 What the Rule Requires

> *"For prerecorded audio-only and prerecorded video-only media, an alternative is provided that presents equivalent information."*
> — [W3C WCAG 2.1 SC 1.2.1](https://www.w3.org/WAI/WCAG21/Understanding/audio-only-and-video-only-prerecorded.html)

**For audio-only content (e.g., a podcast):**
- A text transcript must be provided.
- The transcript must be verbatim (not a summary).
- All speakers must be identified.
- Non-speech sounds must be noted.

**For video-only content (e.g., a silent instructional animation):**
- Either a text transcript OR an audio track describing the visual content must be provided.
- The alternative must describe all meaningful visual information.

### 2.2 Decision Tree (5 Gates)

The evaluation proceeds through 5 sequential gates. Each gate can terminate the check early with a definitive result.

```
┌─────────────────────────────────────────────────────┐
│                 Media Element Found                  │
└──────────────────────┬──────────────────────────────┘
                       ▼
         ┌─────────────────────────────┐
         │  GATE 1: Is it prerecorded? │
         └──────┬──────────────┬───────┘
                │ No (live)    │ Yes
                ▼              ▼
          ┌──────────┐  ┌───────────────────────────────────┐
          │ SKIP     │  │ GATE 2: Is it synchronized media? │
          │ → 1.2.9  │  │ (has BOTH audio AND video tracks) │
          └──────────┘  └──────┬────────────────────┬───────┘
                               │ Yes                │ No
                               ▼                    ▼
                      ┌──────────────┐  ┌───────────────────────────────────────┐
                      │ SKIP         │  │ GATE 3: Is it a media alternative     │
                      │ → 1.2.2/1.2.3│  │ for text, clearly labeled as such?    │
                      └──────────────┘  └──────┬────────────────────────┬───────┘
                                               │ Yes                   │ No
                                               ▼                      ▼
                                       ┌──────────┐  ┌──────────────────────────────────┐
                                       │ EXEMPT   │  │ GATE 4: Is there a text          │
                                       │ (N/A)    │  │ alternative or audio track       │
                                       └──────────┘  │ provided?                        │
                                                      └──────┬───────────────────┬──────┘
                                                             │ No               │ Yes
                                                             ▼                  ▼
                                                     ┌───────────────┐  ┌───────────────────────┐
                                                     │ FAIL          │  │ GATE 5: Does the      │
                                                     │ (immediately) │  │ alternative present   │
                                                     └───────────────┘  │ equivalent info?      │
                                                                        └───────────┬───────────┘
                                                                                    ▼
                                                                        ┌───────────────────────┐
                                                                        │ Quality Checks 1–5    │
                                                                        │ → PASS / FAIL /       │
                                                                        │   NEEDS_REVIEW        │
                                                                        └───────────────────────┘
```

**Gate details:**

| Gate | Function | Logic | Result if triggered |
|------|----------|-------|-------------------|
| **1** | `_is_prerecorded(item)` | Detects live streaming indicators: `MediaSource` API, `srcObject`, HLS/DASH manifest URLs (`.m3u8`, `.mpd`), `live` attribute | `N/A` — "Live media, 1.2.1 does not apply. See 1.2.9." |
| **2** | `_is_audio_only_or_video_only(item)` | Checks if the element has both audio and video tracks. `<audio>` tags are always audio-only. `<video>` elements are checked for the presence of audio tracks via Playwright | `N/A` — "Synchronized media, 1.2.1 does not apply. See 1.2.2/1.2.3." |
| **3** | `_is_labeled_media_alternative(item)` | Checks if the media is explicitly labeled as an alternative to existing text: `aria-label` containing "alternative"/"version of", nearby text like "Audio version of the above article", parent container with `role="complementary"` referencing a text block | `N/A` — "Media is a clearly labeled alternative for existing text content." |
| **4** | `_find_transcript_link(item)` + `_has_description_track(item)` | Searches nearby `<a>` links for keywords ("transcript", "text version", "text alternative"). Checks for `<track kind="captions/descriptions/subtitles">`. Checks for `<details>` transcript blocks. Checks `aria-describedby` targets | `FAIL` — "No text transcript or audio track provided." |
| **5** | `_run_quality_checks(...)` | Invokes the quality engine (see §2.3) | `PASS` / `FAIL` / `NEEDS_REVIEW` based on check results |

### 2.3 Quality Equivalence Checks (Gate 5)

When Gate 4 confirms that a transcript or alternative exists, Gate 5 evaluates whether it is actually **equivalent** to the media content.

| Check | Name | What It Verifies | Local Method |
|-------|------|-----------------|-------------|
| **1** | Verbatim Speech | All spoken words are transcribed, not summarized | WhisperX transcription → `jiwer` Word Error Rate |
| **2** | Speaker Identification | Every speaker is labeled when multiple people speak | WhisperX speaker diarization (counts speakers in audio) + regex (checks transcript for labels) |
| **3** | Non-Speech Audio Events | Sounds like applause, music, laughter are noted | Regex scan for bracketed descriptors `[applause]`, `[music]` against a keyword dictionary |
| **4** | Meaningful Visual Content | All important visual information is described (video-only) | NLTK POS tagging for action verbs + descriptive nouns. Returns `needs_review` — cannot verify visual accuracy locally |
| **5** | Correct Sequence | The alternative follows the time-order of the media | WhisperX word-level timestamps → quarter-based overlap scoring against transcript word order |

**Scoring thresholds (Check 1 — Verbatim):**

| WER (Word Error Rate) | Meaning | Result |
|----------------------|---------|--------|
| WER ≤ 0.15 | 85%+ of words match | **PASS** |
| 0.15 < WER ≤ 0.40 | 60–85% match — possibly paraphrased | **NEEDS_REVIEW** |
| WER > 0.40 | Less than 60% match — summary, not transcript | **FAIL** |

### 2.4 Audio-only vs Video-only Check Matrix

| Check | Audio-only | Video-only |
|-------|-----------|------------|
| **1. Verbatim Speech** | ✅ Primary — transcribe and compare | ❌ N/A — no audio to transcribe |
| **2. Speaker IDs** | ✅ Required if multiple speakers detected | ❌ N/A — no speech |
| **3. Non-Speech Events** | ✅ Required — sounds must be documented | ❌ N/A — no audio |
| **4. Visual Content** | ❌ N/A — no video frames | ✅ Primary — transcript must describe visuals |
| **5. Sequence** | ✅ Transcript order must match audio timeline | ✅ Description order must match video timeline |

---

## 3. Tool Evaluation & Comparative Analysis

### 3.1 Speech-to-Text Models

We evaluated 5 options for converting audio to text locally.

| Tool | Type | Speed (vs realtime) | Accuracy (WER) | Speaker Diarization | Word Timestamps | Install Size | License |
|------|------|-------------------|-----------------|-------------------|----------------|-------------|---------|
| **openai-whisper** | Local (PyTorch) | 1x (realtime on CPU) | ~10% WER (base) | ❌ No | ❌ Segment-level only | ~1.5 GB | MIT |
| **faster-whisper** | Local (CTranslate2) | **4x faster** than vanilla | Same as Whisper | ❌ No | ❌ Segment-level only | ~1.5 GB | MIT |
| **whisperx** | Local (CTranslate2 + pyannote) | **4x faster** than vanilla | Same as Whisper | ✅ **Yes** (via pyannote.audio) | ✅ **Word-level** | ~2 GB + pyannote models | BSD |
| **vosk** | Local (Kaldi) | 10x faster | ~20% WER | ❌ No | ✅ Word-level | ~50 MB | Apache 2.0 |
| **OpenAI Whisper API** | Cloud | Near-instant | ~5% WER | ❌ No | ✅ Word-level | None (API) | Proprietary |

**Decision: WhisperX**

WhisperX is the clear winner because:
1. **Same speed** as faster-whisper (4x improvement over vanilla Whisper) — it's built on top of faster-whisper.
2. **Same accuracy** as the original Whisper model.
3. **Speaker diarization built-in** — directly solves Check 2 without additional tooling. It uses pyannote.audio to assign speaker labels to each segment.
4. **Word-level timestamps** — enables precise quarter-based sequence checking (Check 5) instead of coarse segment-level alignment.
5. One tool feeds **three checks** (1, 2, 5) natively.

**Trade-off accepted:** Requires a free HuggingFace token and `torch` (already needed for any Whisper variant). pyannote models require accepting a license on HuggingFace (one-time, free).

### 3.2 Transcript Scoring Methods

We evaluated 3 options for measuring how closely a developer's transcript matches the Whisper transcription.

| Tool | Metric | What It Measures | Strengths | Weaknesses |
|------|--------|-----------------|-----------|-----------|
| **difflib.SequenceMatcher** | Similarity Ratio (0.0–1.0) | Longest common subsequence between two word lists | Stdlib — zero install. Simple. | Not designed for speech. Penalizes word reordering even when meaning is preserved |
| **jiwer** | **Word Error Rate (WER)** | (Substitutions + Insertions + Deletions) / Total Reference Words | **Industry standard** for speech recognition evaluation. Handles insertions/deletions properly. Purpose-built for comparing transcripts | Requires `pip install jiwer` (~50 KB) |
| **rapidfuzz** | Levenshtein Distance / Ratio | Character or token-level edit distance | Extremely fast (C-compiled). Good for fuzzy string matching | Designed for short strings (names, addresses), not multi-paragraph transcript comparison |

**Decision: jiwer**

jiwer is purpose-built for exactly this task. Word Error Rate is the internationally recognized metric for evaluating speech-to-text output against a reference transcript (used by Google, Meta, and OpenAI to benchmark their own ASR models). Using the industry-standard metric means our pass/fail thresholds are grounded in established research, not arbitrary.

**WER formula:**
```
WER = (Substitutions + Insertions + Deletions) / Total Words in Reference
```

A WER of 0.15 means 85% of the words matched correctly — accounting for minor transcription differences, filler words, and punctuation variations.

### 3.3 Structural Text Analysis

| Tool | Purpose | Used For | Notes |
|------|---------|----------|-------|
| **re (regex)** | Pattern matching | Check 2 (speaker label patterns in transcript), Check 3 (bracketed sound descriptors) | Stdlib. Deterministic. No alternative needed for structural matching |
| **nltk** | Tokenization, POS tagging, stopword removal | Check 4 (detecting action verbs / descriptive nouns to verify visual content descriptions) | Lightweight (~30 MB with punkt + averaged_perceptron_tagger). Sufficient for POS tagging |
| **spaCy** | Full NLP pipeline — POS, NER, dependency parsing | *Evaluated but not chosen* | en_core_web_sm is ~15 MB, more accurate POS tagging than NLTK. Could be a future upgrade. Overkill for current needs |

**Decision: regex + nltk**

regex handles the structural patterns perfectly (speaker labels follow predictable formats). NLTK provides POS tagging for Check 4 without the overhead of spaCy's full dependency parser.

### 3.4 Video Frame Analysis (Multimodal)

This is the most challenging local check. We evaluated options for verifying that a transcript accurately describes what is visually shown in a video.

| Tool | Type | How It Works | Accuracy | Size | Cost |
|------|------|-------------|----------|------|------|
| **OpenCV + manual review** | Local (no AI) | Extract keyframes at intervals. Flag for human review | N/A (no automated judgment) | ~30 MB | Free |
| **CLIP (OpenAI)** | Local model | Generates vector embeddings for both images and text. Cosine similarity score tells you if a frame "matches" a text description | Medium — good at broad concepts, weak at fine details | ~400 MB | Free |
| **Moondream** | Local VLM | 1.6B parameter vision-language model. Can generate text descriptions of images | Medium-High — can describe scenes but may hallucinate | ~3 GB | Free |
| **LLaVA (via Ollama)** | Local VLM | 7B+ parameter model. Full image understanding and Q&A | High | 4–8 GB RAM | Free |
| **GPT-4V / Gemini** | Cloud LLM | Best-in-class multimodal understanding | Highest | None (API) | $ per call |

**Decision: `needs_review` flag (with CLIP as future upgrade path)**

For the initial implementation, Check 4 returns `needs_review` for video-only content. The local NLP approach (NLTK POS tagging) can detect whether the transcript *contains* descriptive visual language, but cannot verify if the descriptions are *accurate* to the actual video content.

**Future upgrade path:** CLIP is the most promising local multimodal solution. It can score "does this frame semantically match this text?" without generating text or calling an LLM. This would be added as an optional enhancement for Check 4 in a later iteration.

---

## 4. Final Technology Stack

### 4.1 Chosen Stack & Justification

| Component | Tool | Handles | Why Chosen |
|-----------|------|---------|-----------|
| **Transcription + Speakers + Timestamps** | **WhisperX** | Check 1 (verbatim), Check 2 (speaker count), Check 5 (timestamps) | Single tool feeds 3 checks. 4x faster than vanilla Whisper. Built-in speaker diarization via pyannote. Word-level timestamps |
| **Transcript accuracy scoring** | **jiwer** | Check 1 (WER computation) | Industry-standard metric for speech-to-text evaluation. Purpose-built for transcript comparison |
| **Structural pattern matching** | **regex (stdlib)** | Check 2 (speaker labels in transcript), Check 3 (bracketed sound events) | Deterministic, fast, zero dependencies. Speaker labels and sound descriptors follow predictable patterns |
| **NLP text analysis** | **nltk** | Check 4 (action verb / descriptive noun detection) | Lightweight POS tagging. Sufficient for detecting visual narrative patterns |
| **Video frame check** | **`needs_review` flag** | Check 4 (visual accuracy) | Cannot verify visual accuracy locally without a vision model. Flagged for manual review or future CLIP integration |

### 4.2 Dependency Map

```
whisperx
├── faster-whisper (CTranslate2-based Whisper)
│   └── ctranslate2
├── pyannote.audio (speaker diarization)
│   ├── torch
│   └── torchaudio
├── transformers (HuggingFace model loading)
└── ffmpeg (system dependency — audio decoding)

jiwer (standalone — ~50 KB)

nltk
├── punkt (tokenizer)
├── averaged_perceptron_tagger (POS tagger)
└── stopwords (English stopword list)

opencv-python-headless (video frame extraction — optional, for future CLIP)
```

### 4.3 Graceful Degradation Strategy

The quality engine (Gate 5) is **optional**. If WhisperX, jiwer, or NLTK are not installed, the system does not crash. Instead:

| Scenario | Behavior |
|----------|----------|
| WhisperX not installed | All quality checks return `needs_review` — "Quality evaluation requires whisperx. Install with: pip install whisperx" |
| jiwer not installed | Check 1 falls back to `difflib.SequenceMatcher` (less accurate but functional) |
| NLTK not installed | Check 4 returns `needs_review` — "POS tagging requires nltk" |
| ffmpeg not installed | WhisperX fails to load audio → all checks return `needs_review` |
| **DOM checks (Gates 1–4) always run** | These use only Playwright and regex — zero optional dependencies |

---

## 5. Architecture & File Map

### 5.1 System Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  API Request (POST /api/v1/combined)                                │
│  routes.py → runner.py → _run_python_stages()                       │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │  _stage_media_audit()        │
              │  (stages.py)                 │
              └──────┬──────────────┬────────┘
                     │              │
          ┌──────────▼──────┐ ┌────▼──────────────────┐
          │ AsyncMediaCrawler│ │ MediaAuditor           │
          │ (media_crawler)  │ │ (media_auditor)        │
          │                  │ │                        │
          │ • Find <audio>   │ │ • Gate 1: Prerecorded? │
          │ • Find <video>   │ │ • Gate 2: Synchronized?│
          │ • Extract attrs  │ │ • Gate 3: Labeled alt? │
          │ • Extract tracks │ │ • Gate 4: Alt exists?  │
          │ • Extract links  │ │ • Gate 5: Quality?     │
          └──────────────────┘ └────────┬───────────────┘
                                        │ (if Gate 4 passes)
                              ┌─────────▼────────────────┐
                              │ QualityEngine             │
                              │ (quality_engine)          │
                              │                           │
                              │ • WhisperX → transcribe   │
                              │ • jiwer → WER score       │
                              │ • regex → speakers/sounds │
                              │ • nltk → visual NLP       │
                              │ • timestamps → sequence   │
                              └─────────┬─────────────────┘
                                        │
                              ┌─────────▼────────────────┐
                              │ _media_to_findings()      │
                              │ (findings.py)             │
                              │                           │
                              │ Converts to standard JSON │
                              │ → merged into final report│
                              └───────────────────────────┘
```

### 5.2 File Inventory

| # | Action | File Path | Description |
|---|--------|-----------|-------------|
| 1 | **NEW** | `ka11y/crawler/media_crawler.py` | Playwright crawler — `AsyncMediaCrawler` class |
| 2 | **NEW** | `ka11y/accessibility/rules/media/__init__.py` | Package init |
| 3 | **NEW** | `ka11y/accessibility/rules/media/media_auditor.py` | `MediaAuditor` class — Gates 1–4 + Gate 5 orchestration |
| 4 | **NEW** | `ka11y/accessibility/rules/media/quality_engine.py` | `QualityEngine` — Checks 1–5 using WhisperX + jiwer + regex + nltk |
| 5 | **NEW** | `tests/test_media_auditor.py` | pytest suite for all gates and quality checks |
| 6 | **MODIFY** | `ka11y/api/v1/combined/constants.py` | Add severity + suggested fix for 1.2.1 |
| 7 | **MODIFY** | `ka11y/api/v1/combined/findings.py` | Add `_media_to_findings()` converter |
| 8 | **MODIFY** | `ka11y/api/v1/combined/stages.py` | Add `_stage_media_audit()` + wire into gather |
| 9 | **MODIFY** | `ka11y/api/v1/combined/models.py` | Add `run_media_audit: bool = True` |

### 5.3 Function Reference

#### `media_crawler.py` — `AsyncMediaCrawler`

| Function | Returns | Description |
|----------|---------|-------------|
| `crawl()` | `List[Dict]` | Playwright page evaluation — extracts all media elements |
| `save_raw_json()` | `None` | Persists results to `media_raw.json` |

#### `media_auditor.py` — `MediaAuditor`

| Function | Gate | Returns | Description |
|----------|------|---------|-------------|
| `generate_audit_report(items)` | Entry | `List[Dict]` | Loops items, applies gates sequentially |
| `_is_prerecorded(item)` | 1 | `bool` | Checks for live/streaming indicators |
| `_is_audio_only_or_video_only(item)` | 2 | `str` | Returns `"audio_only"`, `"video_only"`, or `"synchronized"` |
| `_is_labeled_media_alternative(item)` | 3 | `bool` | Checks if media is a labeled text alternative |
| `_find_transcript_link(item)` | 4 | `Optional[str]` | Searches nearby links/DOM for transcript |
| `_has_description_track(item)` | 4 | `bool` | Checks for `<track kind="captions/descriptions">` |
| `_run_quality_checks(media_url, transcript_text)` | 5 | `Dict` | Invokes `quality_engine.evaluate_transcript_quality()` |

#### `quality_engine.py` — `QualityEngine`

| Function | Check | Method | Returns |
|----------|-------|--------|---------|
| `evaluate_transcript_quality(audio_url, transcript_text, media_type)` | All | Orchestrator — runs applicable checks based on `media_type` | `QualityReport` dict |
| `_transcribe_audio(audio_path)` | — | WhisperX: loads model, transcribes, returns text + segments + speakers | `TranscriptionResult` |
| `_check_verbatim(whisper_text, dev_transcript)` | 1 | `jiwer.wer()` — Word Error Rate | `CheckResult` |
| `_check_speaker_ids(dev_transcript, speaker_count)` | 2 | Regex patterns + WhisperX speaker count | `CheckResult` |
| `_check_non_speech_events(dev_transcript)` | 3 | Bracket regex + keyword dictionary | `CheckResult` |
| `_check_visual_content(dev_transcript)` | 4 | NLTK POS tagging — action verb density | `CheckResult` |
| `_check_sequence(whisper_segments, dev_transcript)` | 5 | Quarter-based word-level timestamp overlap | `CheckResult` |

### 5.4 Naming Conventions

| Concept | Pattern | Value for 1.2.1 |
|---------|---------|-----------------|
| Crawler class | `Async{Name}Crawler` | `AsyncMediaCrawler` |
| Crawler file | `{name}_crawler.py` | `media_crawler.py` |
| Auditor class | `{Name}Auditor` | `MediaAuditor` |
| Auditor file | `{name}_auditor.py` | `media_auditor.py` |
| Auditor package | `ka11y/accessibility/rules/{category}/` | `media/` |
| Status key | `wcag_{X}_{X}_{X}_status` | `wcag_1_2_1_status` |
| Violation key | `wcag_{X}_{X}_{X}_violation` | `wcag_1_2_1_violation` |
| Rule ID | `python_{X}_{X}_{X}_{name}` | `python_1_2_1_media` |
| Stage name | snake_case | `media_audit` |
| Request toggle | `run_{stage_name}` | `run_media_audit` |
| Finding converter | `_{name}_to_findings()` | `_media_to_findings()` |
| Raw JSON | `{stage}_raw.json` | `media_raw.json` |
| CSV report | `audit_{stage}_report.csv` | `audit_media_report.csv` |

---

## 6. WCAG 1.2.2 — Captions (Prerecorded)

> **Status:** Planned

*This section will be populated when 1.2.2 implementation begins. It will reuse `AsyncMediaCrawler` and extend `MediaAuditor` with caption-specific gates (e.g., checking for `<track kind="captions">` on synchronized media). Quality checks will extend the quality engine to evaluate caption timing accuracy.*

---

## 7. WCAG 1.2.3 — Audio Description or Media Alternative

> **Status:** Planned

*This section will be populated when 1.2.3 implementation begins. It will reuse `AsyncMediaCrawler` and add audio description evaluation — checking whether a `<track kind="descriptions">` exists or whether an extended text alternative covers visual content.*

---

## 8. WCAG 1.2.4 — Captions (Live)

> **Status:** Planned

*This section will be populated when 1.2.4 implementation begins. It requires detecting live media streams and checking for real-time captioning mechanisms (e.g., WebSocket caption feeds, embedded caption services).*

---

## 9. WCAG 1.2.5 — Audio Description (Prerecorded)

> **Status:** Planned

*This section will be populated when 1.2.5 implementation begins. It is an AA-level extension of 1.2.3 — requiring a dedicated audio description track rather than allowing a text alternative as a substitute.*

---

## 10. References

| Resource | URL |
|----------|-----|
| W3C WCAG 2.1 — Understanding 1.2.1 | https://www.w3.org/WAI/WCAG21/Understanding/audio-only-and-video-only-prerecorded.html |
| W3C WCAG 2.1 — Understanding 1.2.2 | https://www.w3.org/WAI/WCAG21/Understanding/captions-prerecorded.html |
| W3C WCAG 2.1 — Understanding 1.2.3 | https://www.w3.org/WAI/WCAG21/Understanding/audio-description-or-media-alternative-prerecorded.html |
| OpenAI Whisper (GitHub) | https://github.com/openai/whisper |
| WhisperX (GitHub) | https://github.com/m-bain/whisperX |
| faster-whisper (GitHub) | https://github.com/SYSTRAN/faster-whisper |
| jiwer — Word Error Rate | https://pypi.org/project/jiwer/ |
| pyannote.audio — Speaker Diarization | https://github.com/pyannote/pyannote-audio |
| CLIP — Contrastive Language-Image Pre-Training | https://github.com/openai/CLIP |
| NLTK — Natural Language Toolkit | https://www.nltk.org/ |
