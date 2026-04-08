++==++++# ML / CV / NLP Approaches for Missing WCAG Rules

> Source: `/COVERAGE.md` — 34 uncovered success criteria (6 Level A, 4 AA, 24 AAA)
> Stack: Python (FastAPI + Playwright + existing ka11y-python pipeline)
> Date: 2026-04-01

---

## At a Glance

| Technique family | Missing SCs unlocked | Difficulty |
|---|---|---|
| NEXT-MEDIA (ASR + CV + audio analysis) | 1.2.3, 1.2.4, 1.2.5, 1.2.6, 1.2.7, 1.2.8, 1.2.9, 1.4.7, 2.3.1, 2.3.2 | Medium–High |
| NEXT-NLP (text analysis + NLI + readability) | 1.3.3, 1.3.6, 3.1.3, 3.1.4, 3.1.5 | Low–Medium |
| NEXT-MOTION (gesture + animation detection) | 2.5.1, 2.5.4, 2.3.3 | Medium |
| NEXT-FLOW (stateful workflow replay) | 3.3.5, 3.3.6, 3.3.7, 3.3.9 | High |
| NEXT-CROSS (multi-page diffing) | 3.2.3, 3.2.4 | Medium |
| NEXT-LAYOUT (visual + DOM analysis) | 1.4.8, 2.4.10 | Low–Medium |
| NEXT-TIME (session-state monitoring) | 2.2.3, 2.2.5, 2.2.6 | Medium |
| NEXT-INTERACT (deep interaction simulation) | 2.1.3, 2.5.6, 3.2.5 | High |
| P-OCR upgrade | 1.4.9 | Low |
| P-CRAWL upgrade | 2.5.5 | Low |

---

## NEXT-MEDIA — Audio / Video Analysis

---

### 1.2.3 — Audio Description or Media Alternative (Prerecorded) · Level A

**What it requires:** Prerecorded video (synchronized media) must have either a full text alternative OR audio description of all visual-only information.

**Why it's hard without ML:** You can detect `<video>` elements and look for a `<track kind="descriptions">`, but you cannot verify whether the audio description actually covers the visual content.

#### Python Approach

```
<video> element detected
       │
       ▼
Step 1 — Does a descriptions track / text alternative exist?
  <track kind="descriptions"> OR adjacent text block?
  No → FAIL immediately (no alternative provided)
  Yes → proceed to quality check
       │
       ▼
Step 2 — Video frame extraction (every Ns)
  cv2.VideoCapture(url) → sample frames at 2fps
       │
       ▼
Step 3 — Visual scene description
  Vision-language model (BLIP-2 / LLaVA / moondream2):
    for each keyframe → generated_caption
  Detect "visual-only moments":
    frames where audio transcript has silence or no speech
    (Whisper VAD: voice activity detection)
  visual_only_moments = frames with no speech AND new scene content
       │
       ▼
Step 4 — Check if text alternative covers those moments
  Extract descriptions track text
  Semantic similarity (BERTScore) of visual_only_moments captions
  vs descriptions text
  coverage < 0.6 → audio description incomplete → FAIL
```

**Models / tools:**
| Tool | Purpose |
|------|---------|
| `yt-dlp` / `requests` | Fetch video/audio |
| `openai/whisper` | VAD + speech transcript |
| `BLIP-2` / `moondream2` | Keyframe captioning |
| `BERTScore` | Semantic coverage scoring |
| `opencv-python` | Frame sampling |

---

### 1.2.4 — Captions (Live) · Level AA

**What it requires:** Live audio in synchronized media must have real-time captions.

**Why it's hard without ML:** Can only check static DOM for live caption indicators; can't verify a live stream has captions in real time.

#### Python Approach

```
Detect live media:
  <video> with [type*="m3u8"] / HLS / DASH manifest
  OR [data-live], aria-label*="live", class*="live-stream"
       │
       ▼
Check for live caption indicators:
  <track kind="captions"> with src pointing to .vtt?
  WebVTT live-stream endpoint (e.g. rolling timestamp VTT)?
  aria-live="polite|assertive" captions container?
       │
No live caption indicator → FAIL
       │
       ▼
Optional: Connect to HLS stream → extract in-band captions
  (608/708 embedded captions via hls.js or ffmpeg-python)
  Captions present in stream → PASS
  No captions in stream → FAIL
```

**Tools:** `ffmpeg-python` (extract 608/708 in-band captions from HLS), `m3u8` (parse live manifest), `streamlink` (capture live stream)

---

### 1.2.5 — Audio Description (Prerecorded) · Level AA

**What it requires:** All prerecorded video with audio must have audio description of visual content.

Very similar to 1.2.3 — same pipeline, stricter requirement (every video, not just those without a text alternative).

#### Python Approach

```
Same as 1.2.3 Step 2–4, but:
  - Applied to ALL <video> elements (not just those missing a text alt)
  - Threshold is stricter: every visual-only moment must be described
  - No "text alternative instead" exemption
```

**Differentiation from 1.2.3:** Run same visual analysis pipeline, but the pass condition requires `<track kind="descriptions">` present AND coverage ≥ 0.75 (vs 0.6 for 1.2.3).

---

### 1.2.6 — Sign Language (Prerecorded) · Level AAA

**What it requires:** Prerecorded synchronized media must provide sign language interpretation.

#### Python Approach

```
For each <video>:
  Check for sign language window:
    Picture-in-picture overlay?
    Adjacent <video> with signer?
    [aria-label*="sign language"] / [aria-label*="BSL"] / [aria-label*="ASL"]
    class*="sign-language" / class*="interpreter"
       │
  None found → FAIL
       │
  Optional CV verification:
    Sample frames from candidate sign-language video
    Pose estimation (MediaPipe Holistic / OpenPose):
      Detect hand + body keypoints moving expressively
      Hand velocity variance > threshold → active signing detected
      → PASS
    No hand movement → signer video is static/placeholder → FAIL
```

**Models:** `mediapipe` (hand + pose landmarks), `opencv-python` (frame diff for motion), `youtube-dl` (extract video)

---

### 1.2.7 — Extended Audio Description (Prerecorded) · Level AAA

**What it requires:** When audio description cannot fit into natural pauses, the video must pause to allow extended description.

#### Python Approach

```
From 1.2.5 pipeline, flag videos where:
  Visual-only moments are > 3s AND
  No corresponding natural speech pause in audio track
  (Whisper silence detection: gap < 1.5s before/after the moment)
       │
  These require "extended" audio description (video must pause)
  Check: Does video player have pause-on-description capability?
    data-extended-ad / class*="extended-description"?
    No → INCOMPLETE (manual verification required)
```

**Realistic output:** `incomplete` status with flagged timestamps — full verification requires live playback testing.

---

### 1.2.8 — Media Alternative (Prerecorded) · Level AAA

**What it requires:** All prerecorded synchronized media must have a full text alternative.

#### Python Approach

```
For each <video> with audio:
  Whisper ASR → full speech transcript T_speech
  Scene captioning (BLIP-2 at 1fps) → visual narrative T_visual
  Merge: full_transcript = interleave(T_speech, T_visual)
       │
  Check adjacent text in DOM:
    <details>, linked transcript, aria-describedby
    BERTScore(dom_text, full_transcript) > 0.70 → PASS
    < 0.70 or no text → FAIL
```

---

### 1.2.9 — Audio-only (Live) · Level AAA

**What it requires:** Live audio-only content must have a real-time text alternative.

#### Python Approach

```
Detect live audio streams:
  <audio> with HLS/DASH src OR [type*="stream"]
  OR radio/podcast live embed (iframe patterns)
       │
Check for live text alternative:
  Adjacent [aria-live] container?
  Rolling WebVTT live endpoint?
  Web Speech API usage in inline scripts?
       │
No live text alternative → FAIL
       │
Optional: Connect to audio stream → run Whisper Streaming
  (whisper-live / faster-whisper streaming mode)
  Transcription latency < 5s → PASS (real-time alternative)
```

**Tools:** `faster-whisper` with streaming input, `pyaudio` for stream capture

---

### 1.4.7 — Low or No Background Audio · Level AAA

**What it requires:** Pre-recorded speech audio must have no background music/noise, OR the background must be ≥ 20dB lower than the speech, OR users can turn it off.

#### Python / Audio ML Approach

```
For each <audio> element:
  Download audio → load with librosa
       │
  Source Separation:
    Demucs (Facebook) or Spleeter:
      separate audio into vocals + accompaniment tracks
       │
  Measure RMS energy:
    speech_rms = RMS(vocals_track)
    bg_rms = RMS(accompaniment_track)
    dB_diff = 20 * log10(speech_rms / bg_rms)
       │
  dB_diff >= 20 → background sufficiently low → PASS
  dB_diff < 20 → FAIL
       │
  Check for background audio control:
    [aria-label*="background music off"] /
    volume slider / mute button for BG track
    → PASS if control exists
```

**Models:**
| Model | Purpose |
|-------|---------|
| `demucs` (facebook/demucs) | Music source separation |
| `spleeter` (Deezer) | Faster source separation |
| `librosa` | RMS / dB measurement |

---

### 2.3.1 — Three Flashes or Below Threshold · Level A

**What it requires:** No content must flash more than 3 times per second, or the flash must be below the general flash / red flash thresholds (PEAT tool basis).

#### Python / CV Approach

```
Puppeteer: record page as video (10s clip)
  page.screencast() OR ffmpeg screen capture
       │
Video frame extraction at 60fps (cv2.VideoCapture)
       │
For each 1-second sliding window:
  Compute per-pixel luminance delta between consecutive frames
  Flash candidate: pixels where luminance change exceeds 10%
    of full range (0.1 × 255 = 25 luma units)
       │
  Count flash pairs per second in a 10° visual angle region:
    (area > 25% of 10° foveal zone at typical viewing distance)
       │
  Flash count > 3 per second → FAIL
       │
  Red flash check:
    Hue shift in candidate region crosses red boundary?
    (Hue in [0°,20°] OR [340°,360°] with saturation > 0.5)
    → Apply red flash threshold (stricter: any red flash × 3 = fail)
```

**Tools:** `opencv-python` (frame analysis), `numpy` (luminance calc), `scipy` (signal counting), `ffmpeg-python` (video capture)

**Reference spec:** W3C "Understanding SC 2.3.1" — Harding FPA thresholds

---

### 2.3.2 — Three Flashes · Level AAA

**What it requires:** No flashing at all (stricter than 2.3.1 — no 3fps allowance).

Same pipeline as 2.3.1 but threshold is **any flash > 3 times/second in any region** (no size exemption).

---

## NEXT-NLP — Language & Semantics

---

### 1.3.3 — Sensory Characteristics · Level A

**What it requires:** Instructions must not rely solely on shape, size, visual location, orientation, or sound to identify content.

**Examples of violations:** "Click the round button", "Use the menu on the left", "Press the big blue submit button"

#### Python / NLP Approach

```
Extract all instructional text from page:
  <p>, <li>, <label>, <legend>, <button> text, aria-label values
  Filter: sentences containing imperative verbs
    (click, press, tap, select, go to, refer to, find, see, use)
       │
       ▼
Named-entity-style pattern matching + NLI:
  Does sentence reference ONLY a sensory property?
    shape: round, square, circular, triangular
    size: big, small, large, tiny
    color: blue, red, green (without non-color context)
    position: left, right, top, bottom, above, below, corner
    sound: when you hear the beep, after the chime
       │
  No accompanying non-sensory identifier?
    (no "the Submit button", no aria-label, no text label match)
       │
  → ISSUE: instruction relies on sensory characteristic alone
       │
NLI verification (DeBERTa-NLI):
  premise: extracted instruction
  hypothesis: "This instruction can be understood without seeing, hearing, or sensing the location/shape"
  entailment score < 0.5 → FAIL
```

**Models:** `spaCy` (imperative detection, NER), `cross-encoder/nli-deberta-v3-small` (NLI quality check), `sentence-transformers` (semantic similarity to sensory-pattern prototypes)

---

### 1.3.6 — Identify Purpose · Level AAA

**What it requires:** The purpose of UI components, icons, and regions can be programmatically determined (beyond ARIA roles — includes landmark regions, icon meanings, purpose of input fields).

#### Python / NLP + CV Approach

```
DOM Analysis:
  Icons: <svg>, <img role="img">, <i class="icon-*">
    Has aria-label / aria-hidden? → OK
    No label → CV icon classification:
      CLIP zero-shot: embed icon image
      Compare to purpose categories:
        [search, home, settings, user, cart, delete, edit,
         share, download, close, menu, notification, ...]
      If recognisable purpose but no label → ISSUE
       │
  Regions: <div>, <section> without landmark role
    Has identifiable content purpose?
    NLP classifier on section heading + first paragraph:
      purpose labels: [navigation, search, main_content,
                       sidebar, footer, advertisement, form]
      purpose identified but no role → flag for review
       │
  Input fields:
    No autocomplete attribute on personal-data fields?
    (Already partially covered by 1.3.5 in axe-core)
    Additional: NLP on label → infer purpose → check autocomplete value match
```

**Models:** `CLIP` (icon purpose classification), `sentence-transformers` (region content purpose), `spaCy` (label semantic parsing)

---

### 3.1.3 — Unusual Words · Level AAA

**What it requires:** A mechanism to identify definitions of words used in an unusual or restricted way, or idioms and jargon.

#### Python / NLP Approach

```
Extract all visible body text
       │
       ▼
Step 1 — Jargon / unusual word detection:
  Word frequency baseline: compare against Common Words corpus
    (British National Corpus / Brown Corpus top 10K words)
  Word NOT in top 10K AND not a proper noun (NER check) → candidate
       │
Step 2 — Idiom detection:
  Idiom lexicon match (Wiktionary idioms list, MAGPIE dataset)
  Phrase in idiom list → candidate
       │
Step 3 — Domain jargon:
  Embed sentence with sentence-transformers
  Classify domain: [medical, legal, technical, financial, general]
  Domain-specific word list for detected domain
  Word in domain jargon list → candidate
       │
Step 4 — Is a definition mechanism provided?
  <abbr title="…"> / <dfn> wrapping the word
  Glossary link nearby: a[href*="glossary"] / a[href*="definition"]
  aria-describedby on element pointing to definition
       │
candidates without definition mechanism → ISSUE
```

**Tools / data:**
| Resource | Purpose |
|---------|---------|
| `nltk.corpus.words` | Common word baseline |
| `spaCy` NER | Exclude proper nouns from "unusual" |
| MAGPIE idiom dataset | Idiom detection |
| `sentence-transformers` | Domain classification |
| Wiktionary API | Definition lookup verification |

---

### 3.1.4 — Abbreviations · Level AAA

**What it requires:** A mechanism to identify the expanded form or meaning of abbreviations.

#### Python / NLP Approach

```
Extract all visible text
       │
Abbreviation detection (regex + NLP):
  ALLCAPS 2-5 chars: WHO, HTML, WCAG, API
  Mixed case with periods: U.S., e.g., i.e., et al.
  Known abbreviation patterns (spaCy EntityRuler)
       │
For each abbreviation found:
  Is it wrapped in <abbr title="…">? → PASS
  Is it preceded by expanded form in same sentence?
    "World Health Organization (WHO)" → PASS
  Is there a glossary link?
    a[href*="glossary"][text contains abbreviation] → PASS
       │
Neither → ISSUE
```

**Tools:** `spaCy` (abbreviation detection with custom EntityRuler), `re` (regex patterns), abbreviation dataset from Wikipedia

---

### 3.1.5 — Reading Level · Level AAA

**What it requires:** When text requires reading ability beyond lower secondary education, supplemental content or a simplified version is available.

#### Python / NLP Approach

```
Extract all paragraph / article text
       │
       ▼
Readability scoring (multiple metrics, ensemble):
  Flesch-Kincaid Grade Level: 0.39 × (words/sentences) + 11.8 × (syllables/words) − 15.59
  Gunning Fog Index: 0.4 × ((words/sentences) + 100 × (complex_words/words))
  SMOG Grade: 3 + √(polysyllabic_count × 30/sentences)
       │
  Average grade level > 9 (lower secondary school) → complex text
       │
Check for simplified alternative:
  [lang] alternate version link?
  "Easy Read" / "Plain English" / "Simplified" link nearby?
  aria-describedby pointing to simpler text?
       │
Complex text without alternative → FAIL
       │
Advanced: ML-based readability (CommonLit / RACE dataset fine-tune):
  Fine-tuned BERT on readability scores → direct grade prediction
  More accurate than formula for technical/domain text
```

**Tools:** `textstat` (Python readability library — implements FK, Fog, SMOG, Coleman-Liau, ARI), `spaCy` (syllable counting, sentence segmentation), `transformers` (fine-tuned readability model)

```python
import textstat
grade = textstat.flesch_kincaid_grade(text)
fog   = textstat.gunning_fog(text)
smog  = textstat.smog_index(text)
avg   = (grade + fog + smog) / 3
if avg > 9:
    # flag as requiring supplemental content
```

---

## NEXT-MOTION — Gesture & Animation

---

### 2.5.1 — Pointer Gestures · Level A

**What it requires:** All functionality using multi-point gestures (pinch, swipe, two-finger) or path-based gestures must have a single-pointer alternative (tap, click).

#### Python Approach

```
Static analysis (JS scanning):
  Scan inline scripts + external scripts (if bundled):
    Detect: Hammer.js / gesture event APIs:
      'pinch', 'pan', 'swipe', 'rotate' event listeners
      touch-action: pinch-zoom in CSS
      GestureEvent / PointerEvent with isPrimary check
       │
  Library detection:
    import Hammer from 'hammerjs' → flag
    new Hammer(el) → scan for .on('pinch|swipe|rotate|pan')
    use-gesture (React): usePinch / useSwipe / useDrag
    Interact.js: gesturable({ onmove })
       │
For each gesture detected:
  Is there a single-pointer equivalent (button/link for same action)?
  nearby button with same action keyword in label?
  aria-controls pointing to same target?
       │
No alternative → FAIL
```

**CV extension (for canvas-based gesture interfaces):**
```
Screenshot + interaction map:
  CLIP zero-shot: "Does this interface require multi-finger gesture?"
  Classify: yes → flag for manual review
```

---

### 2.5.4 — Motion Actuation · Level A

**What it requires:** Functionality triggered by device motion (shake, tilt) must have a UI alternative AND users can disable motion actuation.

#### Python Approach

```
Scan inline scripts for motion/orientation APIs:
  DeviceMotionEvent / DeviceOrientationEvent listeners
  window.addEventListener('devicemotion', ...)
  window.addEventListener('deviceorientation', ...)
  Gyroscope / Accelerometer (Generic Sensor API)
       │
Found → check for:
  1. UI alternative (button/link doing same action)
     pattern: if motion action = "shake to undo"
              look for undo button / Ctrl+Z equivalent
  2. Disable mechanism:
     "Disable motion" toggle / OS accessibility settings respected
     prefers-reduced-motion media query used in same code context
       │
Motion detected:
  No UI alternative → FAIL
  No disable mechanism → FAIL
  Both present → PASS
```

---

### 2.3.3 — Animation from Interactions · Level AAA

**What it requires:** Motion animation triggered by user interaction can be disabled (unless essential).

#### Python Approach

```
Detect animation triggered by interaction:
  CSS: transition / animation on :hover / :focus / :active
  JS: animate() / GSAP / Framer Motion triggered in event handlers
  Web Animations API: el.animate(...)
       │
Check for prefers-reduced-motion respect:
  CSS: @media (prefers-reduced-motion: reduce) { ... }
     does it set animation: none / transition: none?
  JS: window.matchMedia('(prefers-reduced-motion: reduce)').matches
     conditional animation skip
       │
Has CSS animations triggered by interaction
AND no prefers-reduced-motion override → FAIL
       │
CV verification (optional):
  Inject prefers-reduced-motion: reduce via CDP override
  screenshot before/after interaction
  pixelmatch diff > threshold → animation still running → FAIL
```

**CDP override:**
```python
await page.emulate_media_features([
    {"name": "prefers-reduced-motion", "value": "reduce"}
])
# then trigger interactions and screenshot diff
```

---

## NEXT-FLOW — Stateful Workflow Replay

---

### 3.3.7 — Redundant Entry · Level A

**What it requires:** Information previously entered by the user in the same process is either auto-populated or available for selection; users don't have to retype it.

> Note: A custom Node check exists (`redundant-entry.check.js`) but it is static-DOM only. This Python approach covers multi-step DYNAMIC forms.

#### Python Approach

```
Multi-step form detection:
  Step 1: Fill form page 1 with test data
    Name: "Test User", Email: "test@example.com",
    Address: "123 Test St", Phone: "555-0100"
  Submit → navigate to step 2 (or same-page step change)
       │
  Step 2: Check if previously entered fields reappear as inputs:
    DOM scan for input fields matching semantic tokens:
      email, name, address, phone, etc.
    Are they pre-populated with the values from step 1?
      field.value === entered_value → auto-populated → PASS
      field.value === '' and field is required → FAIL (redundant entry)
      field is readonly/display-only → OK (not re-entry)
       │
  Jaccard of required empty fields vs previously entered fields:
    overlap > 0 → redundant entry detected → FAIL

  Check for reuse controls:
    "Same as billing" checkbox auto-populates? → PASS
```

**Key advantage over Node static check:** This actually SUBMITS the form and checks if step 2 re-asks for the same data.

---

### 3.3.5 — Help · Level AAA

**What it requires:** Context-sensitive help is available for complex tasks (not just a generic help link — help must relate to the current task).

#### Python / NLP Approach

```
For each form/task page:
  Extract task context: form heading, field labels, page title
       │
  Detect help content nearby:
    [aria-describedby] on form → text of referenced element
    [aria-details] pointing to detailed explanation
    <details><summary>Help / How to…</summary>…</details>
    tooltip: [title] attributes on complex fields
    help icon: (?)(ℹ) / [aria-label*="help"] buttons nearby
       │
  Is help content relevant to task?
    NLP semantic similarity:
      embed(task_context) vs embed(help_text)
      cosine_similarity > 0.5 → contextually relevant → PASS
      < 0.5 → generic/irrelevant help → INCOMPLETE
       │
  No help mechanism found at all → FAIL
```

---

### 3.3.6 — Error Prevention (All) · Level AAA

**What it requires:** All form submissions (not just financial/legal/destructive as in 3.3.4) must be reversible, verifiable, or confirmable.

#### Python Approach

Same pipeline as Node's `error-prevention.check.js` but:
- Applied to **every** form submission, not just high-risk
- Playwright-powered: actually submit form → check for:
  - Confirmation step
  - Success page with "undo" / "cancel" option
  - Confirmation email with cancellation link
  - Inline review summary before final submit

```python
# After form submission:
has_confirm = await page.query_selector('[aria-label*="confirm"], [class*="confirm-step"]')
has_undo    = await page.query_selector('a:has-text("Undo"), button:has-text("Cancel")')
has_summary = await page.query_selector('[class*="order-summary"], [class*="review"]')
```

---

### 3.3.9 — Accessible Authentication (Enhanced) · Level AAA

**What it requires:** Authentication does not rely on cognitive function tests OR object/image recognition — even if an alternative is offered. Stricter than 3.3.8 (which allows image CAPTCHA if audio alternative exists).

#### Python Approach

```
Extends Node's accessible-auth.check.js:
  Any CAPTCHA type detected → FAIL (no alternatives accepted)
  Any image recognition test → FAIL
  Any cognitive test (math, riddle, puzzle) → FAIL
       │
Only allowed auth mechanisms:
  - Password field with copy-paste allowed (no cognitive memory test)
  - WebAuthn / passkey (biometric, device-based)
  - Email magic link
  - SMS/TOTP code (arguably cognitive — flag as needs_review)
       │
CV check for image recognition tests:
  Screenshot → CLIP zero-shot:
    "Does this UI require identifying objects in images?"
    confidence > 0.7 → FAIL
```

---

## NEXT-CROSS — Multi-page Consistency

---

### 3.2.3 — Consistent Navigation · Level AA

**What it requires:** Navigation that repeats across pages appears in the same relative order each time.

#### Python Approach

```
Crawl N pages from same domain (3–5 pages minimum):
  Playwright: follow internal links from homepage
       │
For each page, extract navigation structure:
  <nav> / [role="navigation"] → ordered list of link texts + hrefs
  fingerprint: [('Home', '/'), ('About', '/about'), ('Contact', '/contact')]
       │
Compare fingerprints across pages:
  Ordered sequence similarity (LCS or Kendall-τ rank correlation):
    same links in same order → consistent
    links reordered → FAIL (order changed)
    links added/removed beyond a threshold → FAIL (structure changed)
       │
Threshold: allow new page-specific items appended/prepended
  but core nav items must stay in same relative order
       │
Also: visual position check (via bounding boxes):
  nav bounding box in header/footer: consistent position across pages?
```

**Implementation:**
```python
from scipy.stats import kendalltau

def nav_consistency(pages_nav_orders):
    base = pages_nav_orders[0]
    for other in pages_nav_orders[1:]:
        shared = [item for item in base if item in other]
        base_ranks  = [base.index(i) for i in shared]
        other_ranks = [other.index(i) for i in shared]
        tau, _ = kendalltau(base_ranks, other_ranks)
        if tau < 0.9:  # high correlation required
            return "FAIL"
    return "PASS"
```

---

### 3.2.4 — Consistent Identification · Level AA

**What it requires:** Components with the same functionality are identified consistently (same label/name) across pages.

#### Python Approach

```
Crawl N pages → extract interactive components:
  buttons, links, inputs, icons with aria-label
  key: (accessible_name, role, function_guess)
       │
Group by visual/functional similarity across pages:
  Cluster by sentence-embedding similarity of accessible names
  (all-MiniLM-L6-v2):
    components with embedding cosine > 0.85 → same functional group
       │
Within each group:
  Do all instances share the same accessible name?
    YES → consistent → PASS
    NO (e.g. "Search" on one page, "Find" on another, "Go" on third)
       → FAIL (same function, different names)
       │
Also: icon identity check
  Same icon SVG path hash across pages but different aria-labels
  → inconsistent identification → FAIL
```

---

## NEXT-LAYOUT — Visual Structure Analysis

---

### 1.4.8 — Visual Presentation · Level AAA

**What it requires:** Users can select foreground/background colors, text is not justified, line spacing is ≥ 1.5, columns ≤ 80 chars wide, and text is not justified both sides.

#### Python Approach (mostly computed-style, minimal ML)

```
Playwright → page.evaluate() for each text block:

1. Text justification:
   getComputedStyle(el).textAlign === 'justify' → FAIL

2. Line height:
   parseFloat(lineHeight) / parseFloat(fontSize) < 1.5 → FAIL

3. Column width:
   element width in pixels / approximate char width (fontSize * 0.6)
   > 80 chars in container → FAIL

4. Letter spacing:
   getComputedStyle(el).letterSpacing changed from normal → flag

5. Foreground/background selectability:
   Check if page overrides user stylesheets:
     Inject user stylesheet via CDP:
       body { color: red !important; background: yellow !important; }
     Screenshot: are colors actually overridden?
     If page's own CSS wins → not user-controllable → FAIL
```

**CDP user stylesheet injection:**
```python
await page.add_style_tag(content="""
  * { color: red !important; background: yellow !important; }
""")
screenshot_after = await page.screenshot()
# pixel-diff original vs after — if diff minimal → page blocks user styles
```

---

### 2.4.10 — Section Headings · Level AAA

**What it requires:** Section headings are used to organise content (pages with multiple logical sections must use heading elements to delineate them).

#### Python / NLP Approach

```
Extract page structure:
  All block-level containers with > 200 chars text content
  (article, section, div, main sub-sections)
       │
For each content block:
  Does it have a preceding heading (h1–h6)?
  OR an aria-label / aria-labelledby on the container?
       │
Count: content_blocks_without_heading / total_content_blocks
ratio > 0.3 → sections not consistently headed → FAIL
       │
NLP enhancement:
  For blocks without heading:
    Extract first sentence → classify as new topic?
      Sentence embedding similarity to previous section < 0.4
      → clearly new topic but no heading → ISSUE
```

---

## NEXT-TIME — Session-State Monitoring

---

### 2.2.3 — No Timing · Level AAA

**What it requires:** Timing is not an essential component of the event or activity (except non-interactive synchronized media and real-time events).

#### Python Approach

```
Monitor page during a timed session:
  Inject session timer monitor:
    setInterval tracking + localStorage/sessionStorage expiry
    meta http-equiv="refresh" detection
       │
  Detect time-limited interactions:
    Countdown timers: [class*="countdown"], [class*="timer"]
    setTimeout navigation (auto-redirect after N seconds)
    Form auto-clear on inactivity
       │
  For each time-limited element:
    Is it an exception? (synchronized media, real-time events)
    Check: page content is live data / streaming → exempt
    Check: form auto-saves / preserves data → PASS
    Check: no save/extend mechanism → FAIL
```

---

### 2.2.5 — Re-authenticating · Level AAA

**What it requires:** When an authenticated session expires, users can re-authenticate without losing data.

#### Python Approach

```
Playwright stateful session test:
  1. Authenticate (fill login form, submit)
  2. Navigate to data entry form (e.g. checkout, draft message)
  3. Fill in substantial data
  4. Manipulate session:
     await page.evaluate("() => { document.cookie = 'session=expired'; }")
     OR await context.clear_cookies()
  5. Submit form → session expired redirect
       │
  On re-authentication page:
    After re-login, are we returned to previous state?
      data still in form fields? → PASS
      data lost, returned to homepage → FAIL
      data lost, form cleared → FAIL
```

---

### 2.2.6 — Timeouts · Level AAA

**What it requires:** Users are warned about timeouts that could cause data loss, unless data is preserved for more than 20 hours.

#### Python Approach

```
Detect potential data-loss timeouts:
  Scan inline JS for:
    setTimeout / setInterval with action patterns:
      clear() / reset() / redirect() / logout() / expire()
    idle detection API usage (IdleDetector)
    sessionStorage / localStorage with expiry logic
       │
  Threshold: timeout duration < 20 hours?
       │
  Warning mechanism present?
    [role="alertdialog"] with timeout warning content?
    "Your session will expire in…" text detected?
    aria-live region announcing countdown?
       │
Timeout detected AND no warning → FAIL
Timeout > 20 hours OR warning present → PASS
```

---

## NEXT-INTERACT — Deep Interaction Simulation

---

### 2.1.3 — Keyboard (No Exception) · Level AAA

**What it requires:** ALL functionality must be keyboard accessible — no exceptions (stricter than 2.1.1 which allows path-dependent exceptions like freehand drawing).

#### Python Approach

Extends Node's keyboard trap check + axe keyboard rules:

```
Enumerate ALL clickable/interactive elements:
  [onclick], [onmousedown], [role=button/link/menuitem],
  canvas event listeners, custom widgets
       │
For each interactive element:
  Can it receive keyboard focus (Tab reachable)?
  Can it be activated with Enter / Space?
  If it's a custom widget: do arrow keys work within it?
       │
Fail conditions:
  tabIndex = -1 AND no keyboard handler → FAIL
  onClick but no onKeyDown/onKeyUp equivalent → FAIL
  Canvas-only interaction (no keyboard API exposed) → FAIL
       │
Also: simulate keyboard-only navigation through full workflow:
  Tab through all focusable elements → activate each → verify result
  Any step requiring pointer → FAIL
```

---

### 2.5.6 — Concurrent Input Mechanisms · Level AAA

**What it requires:** The page does not restrict use of input modalities available on the platform. A user using touch should still be able to switch to keyboard or mouse.

#### Python Approach

```
Inject multi-modal interaction:
  1. Interact via touch (Playwright touchscreen API)
  2. Then interact via keyboard
  3. Then interact via mouse
       │
  Check for input-locking patterns:
    pointer-events: none on keyboard-interactive elements after touch?
    focus() blocked after touch event?
    CSS that hides focus indicators for non-keyboard users?
       │
  Scan inline JS:
    if (isMobile || isTouchDevice) { /* disable keyboard handlers */ }
    navigator.maxTouchPoints > 0 → locks to touch-only → FAIL
       │
  navigator.maxTouchPoints emulation via CDP:
    override to emulate touch device → check if keyboard still works
```

---

### 3.2.5 — Change on Request · Level AAA

**What it requires:** Context changes are initiated only by user request, OR a mechanism to turn off automatic changes is provided.

#### Python Approach

```
Monitor page during passive observation (no user interaction):
  Listen for:
    framenavigated events → URL changed without user action → FAIL
    DOM mutations: large content replacement (> 20% DOM change)
    setInterval → content auto-updates
    meta http-equiv="refresh" → FAIL
    CSS animations that replace content (carousel without pause)
       │
  Check for user-control mechanism:
    Auto-advance carousel: pause button present?
    Auto-redirect: can user disable?
    Live feed: freeze option?
       │
  context_change_without_request AND no control mechanism → FAIL
```

---

## P-OCR Upgrade

---

### 1.4.9 — Images of Text (No Exception) · Level AAA

**What it requires:** Text must not be presented as images unless it is pure decoration or the visual presentation is essential — **no logotype exception** at AAA.

#### Python Approach (upgrade from existing OCR pipeline)

```
Current 1.4.5 pipeline (AA): exempts logos
       │
1.4.9 upgrade: remove logo exemption
  Same PaddleOCR text detection pipeline BUT:
    logoRe exemption → removed
    If OCR detects text in image AND image is not:
      - Pure decoration (alt="")
      - A photograph where text appears incidentally
      → FAIL (no exceptions)
       │
  Incidental text detection:
    Is the text < 5% of the image area? → incidental (background sign, etc.)
    Is the text the primary content? → image of text → FAIL
```

---

## P-CRAWL Upgrade

---

### 2.5.5 — Target Size · Level AAA

**What it requires:** Touch/click targets are at least **44×44 CSS pixels** (vs the AA minimum of 24×24 in 2.5.8).

#### Python Approach (upgrade from existing target-size auditor)

```
Current 2.5.8 auditor: checks 24×24px with spacing
       │
2.5.5 upgrade: raise threshold to 44×44px
  Same Playwright target-size crawler:
    getBoundingClientRect() for all interactive elements
    width < 44 OR height < 44 → FAIL at AAA
    (inline text links exempt if not essential)
       │
Spacing exemption:
  Adjacent target offset > 22px in all directions?
  → equivalent to having 44px effective target → PASS
```

---

## Priority by Impact & Python Effort

| SC | Level | NEXT family | Python difficulty | High-value reason |
|----|-------|-------------|-------------------|-------------------|
| 2.3.1 Three Flashes | A | NEXT-MEDIA | Medium | Seizure safety — critical |
| 3.3.7 Redundant Entry | A | NEXT-FLOW | Low | Already has static Node check; Python adds dynamic verification |
| 1.3.3 Sensory Characteristics | A | NEXT-NLP | Low | NLP patterns straightforward |
| 3.1.5 Reading Level | AAA | NEXT-NLP | Low | `textstat` = 1 hour integration |
| 3.1.4 Abbreviations | AAA | NEXT-NLP | Low | regex + `<abbr>` check |
| 3.1.3 Unusual Words | AAA | NEXT-NLP | Medium | Jargon corpus needed |
| 2.5.1 Pointer Gestures | A | NEXT-MOTION | Low | JS pattern scan |
| 2.5.4 Motion Actuation | A | NEXT-MOTION | Low | DeviceMotionEvent scan |
| 2.3.3 Animation | AAA | NEXT-MOTION | Low | prefers-reduced-motion check |
| 2.4.10 Section Headings | AAA | NEXT-LAYOUT | Low | DOM structure check + NLP |
| 1.4.8 Visual Presentation | AAA | NEXT-LAYOUT | Low | Computed style checks |
| 1.4.9 Images of Text (No Exception) | AAA | P-OCR | Low | Remove logo exemption from existing |
| 2.5.5 Target Size AAA | AAA | P-CRAWL | Low | Raise threshold in existing auditor |
| 3.2.3 Consistent Navigation | AA | NEXT-CROSS | Medium | Multi-page crawler needed |
| 3.2.4 Consistent Identification | AA | NEXT-CROSS | Medium | Sentence embedding across pages |
| 2.2.6 Timeouts | AAA | NEXT-TIME | Medium | JS scan + session monitoring |
| 1.2.3 Audio Description | A | NEXT-MEDIA | High | Whisper + BLIP-2 required |
| 1.2.5 Audio Description (Prerecorded) | AA | NEXT-MEDIA | High | Same as 1.2.3 |
| 1.4.7 Background Audio | AAA | NEXT-MEDIA | Medium | Demucs source separation |
| 1.3.6 Identify Purpose | AAA | NEXT-NLP | Medium | CLIP + NLP ensemble |
| 3.3.5 Help | AAA | NEXT-FLOW | Medium | NLP relevance scoring |
| 3.3.6 Error Prevention (All) | AAA | NEXT-FLOW | High | Full form submission needed |
| 3.3.9 Accessible Auth (Enhanced) | AAA | NEXT-FLOW | Medium | Extends Node's 3.3.8 |
| 2.2.5 Re-authenticating | AAA | NEXT-TIME | High | Session expiry simulation |
| 1.2.4 Captions (Live) | AA | NEXT-MEDIA | High | Live stream connection |
| 1.2.6 Sign Language | AAA | NEXT-MEDIA | High | MediaPipe pose estimation |
| 2.1.3 Keyboard (No Exception) | AAA | NEXT-INTERACT | High | Full workflow keyboard sim |
| 2.5.6 Concurrent Input | AAA | NEXT-INTERACT | High | Multi-modal interaction test |
| 3.2.5 Change on Request | AAA | NEXT-INTERACT | Medium | Passive monitoring |
