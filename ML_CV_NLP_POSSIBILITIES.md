# ML / CV / NLP Possibilities for ka11y

> Scope: ka11y-node custom checks (24 rules) + ka11y-python pipeline
> Generated: 2026-04-01
> Theme: Where heuristics / regex / DOM inspection hit their ceiling and a learned or perception model can take over

---

## Why current checks plateau

Every custom check in ka11y-node is a **deterministic heuristic**: regex on text, keyword match on class names, pixel threshold on computed styles. These are fast and explainable but they share a fundamental ceiling:

- They cannot read **visual content** (text in images, focus indicator salience, color meaning in charts)
- They cannot understand **semantics** (is this error message actually helpful? does this alt text describe what is shown?)
- They cannot model **intent** (is this drag gesture really requiring drag, or is click also possible?)
- They cannot generalise across **languages** that are not in a hardcoded list

The table below maps each WCAG SC to the ML/CV/NLP technique that would lift that ceiling.

---

## Rule-by-Rule ML/CV/NLP Opportunity

---

### SC 1.1.1 — Non-text Content (alt text quality)
**Current state:** axe-core checks *presence* of alt; ka11y-python uses cosine similarity of alt vs surrounding text
**Ceiling:** Can't tell whether the alt text actually describes what is *visually shown* in the image

#### CV Opportunity — Image Captioning / VQA

```
Image bytes
     │
     ▼
Vision-Language Model (e.g. BLIP-2, LLaVA, GPT-4o vision)
     │
  Generated description
     │
  Semantic similarity (cosine / BERTScore) vs provided alt text
     │
similarity < threshold → alt text does not describe image → FAIL
similarity ≥ threshold → alt text matches visual content → PASS

Also:
  Classify image type:
    decorative (texture, background gradient) → should have alt=""
    functional (button icon, chart, diagram) → must have meaningful alt
    informational (photo, illustration) → must have descriptive alt
```

**Model options:**
| Model | Size | Latency | Accuracy |
|-------|------|---------|----------|
| BLIP-2 (Salesforce) | 3.9 B | ~200ms GPU | High |
| LLaVA-1.6-mistral | 7 B | ~400ms GPU | Very high |
| GPT-4o vision (API) | — | ~1-2s | SOTA |
| moondream2 | 1.8 B | ~80ms CPU | Medium |

**Integration point:** `ka11y-python/ka11y/accessibility/rules/non_text/alttext.py`
Already has `AltTextAuditor` class — add a `VisionEvaluator` step after the existing cosine similarity pass.

---

### SC 1.2.1 — Audio-only: Transcript accuracy
**Current state:** Detects *presence* of a transcript (link, track, figcaption, details)
**Ceiling:** Cannot verify the transcript actually matches what was said

#### NLP + ASR Opportunity

```
<audio src="…">
     │
     ▼
ASR model (Whisper large-v3)
  → auto-generated transcript T_auto
     │
Provided transcript T_human (from nearby <details> / <track>)
     │
Character Error Rate (CER) or Word Error Rate (WER):
  WER = (S + D + I) / N
     │
WER > 20% → transcript significantly diverges → INCOMPLETE
WER ≤ 20% → transcript accurate → PASS
```

**Model options:**
| Model | WER (LibriSpeech) | Languages | Size |
|-------|------------------|-----------|------|
| Whisper large-v3 | 2.7% | 99 | 1.5 GB |
| Whisper medium | 5.1% | 99 | 769 MB |
| Distil-Whisper large-v3 | 3.5% | EN | 756 MB |

**Integration point:** New Python evaluator `audio_transcript_evaluator.py`
Fetch audio URL → run Whisper → align with detected transcript → compute WER.

---

### SC 1.2.2 — Captions (prerecorded) quality
**Current state (ka11y-python):** `CaptionsPrerecordedChecker` uses cosine similarity on VTT text vs video transcript
**Ceiling:** Cosine similarity is bag-of-words — misses temporal alignment, missing cues, poor speaker identification

#### NLP Opportunity — Caption Quality Scoring

```
VTT caption file
     │
     ▼
1. Temporal density check:
   gap between cues > 3s with audio activity? → missing caption window
     │
2. Semantic completeness (BERTScore F1):
   caption text vs ASR-generated reference
   F1 < 0.85 → captions incomplete
     │
3. Speaker identification:
   audio diarisation (pyannote.audio) → count speakers
   captions label speakers? → check "[Speaker]:" prefix or equivalent
     │
4. Reading speed:
   chars-per-second per cue > 20 (too fast to read) → ISSUE
```

**Models:**
- `pyannote/speaker-diarization-3.1` for speaker counting
- `BERTScore` (microsoft/deberta-xlarge-mnli) for semantic F1
- `Whisper` for reference transcript

---

### SC 1.3.2 — Meaningful Sequence (visual reordering)
**Current state:** CSS `flex-direction` + `order` property inspection
**Ceiling:** Cannot detect visual reordering caused by absolute positioning, negative margins, CSS grid with dense auto-placement

#### CV Opportunity — Visual Reading Order vs DOM Order

```
Puppeteer screenshot of page
     │
     ▼
Layout Analysis Model (e.g. LayoutParser, DocLayNet, DiT)
  → bounding boxes of text blocks in visual order
     │
DOM text extraction in source order
     │
Sequence alignment (Needleman–Wunsch or LCS):
  visual_order_text vs dom_order_text
     │
alignment score < threshold → visual ≠ DOM order → FAIL
```

**Model options:**
| Model | Task | Notes |
|-------|------|-------|
| DiT (Document Image Transformer) | Document layout analysis | Strong on structured pages |
| LayoutParser + Detectron2 | Region detection | Configurable |
| EasyOCR + spatial sort | Simple bbox sort | Fast, no deep model needed |
| GPT-4o vision (bbox extraction) | Zero-shot layout | Most flexible |

**Simpler proxy (no full model needed):**
```python
# Use Puppeteer to get getBoundingClientRect() for all text nodes
# Sort by (top, left) to get visual reading order
# Compare to DOM order via TreeWalker
# Euclidean distance between the two orderings → threshold
```

---

### SC 1.4.1 — Use of Color (information conveyed by color alone)
**Current state:** Checks inline links for non-color visual cues (underline, border, font-weight)
**Ceiling:** Cannot detect color-as-the-only-information in charts, graphs, maps, status indicators, form fields

#### CV Opportunity — Color-only Information Detection

```
Page screenshot
     │
     ▼
Semantic segmentation → identify chart/graph/map regions
     │
For each region:
  Simulate deuteranopia/protanopia color transformation
  (Brettel 1997 or Viénot 1999 LMS transform):
     │
  Re-run region classification on transformed image:
    if class labels / data lines / regions become indistinguishable
    → information was color-only → FAIL
     │
Also: OCR on legend/key → check legend uses symbols/patterns too
```

**Models / tools:**
- `torchvision` + `Pillow` for LMS color blindness simulation (no ML needed for this step)
- `YOLO v9` or `DETR` for chart/graph region detection
- `EasyOCR` for legend text extraction
- `Kolors` or `DALL-E` image description for zero-shot check

**Daltonization transform (can run in Node.js too):**
```js
// Brettel et al. deuteranopia simulation (2×2 matrix on LMS space)
// If color-blind version of a chart looks identical to original
// across the legend colors → likely color-only distinction
```

---

### SC 1.4.5 — Images of Text
**Current state:** Heuristic scoring on src path keywords, alt text length, class names
**Ceiling:** Cannot actually read what is inside the image

#### CV Opportunity — OCR-based Text Detection

```
<img src="…">
     │
     ▼
Scene Text Detector (e.g. CRAFT, DBNet, PaddleOCR detector)
  → text region bounding boxes in image
     │
Text region area / total image area > 15%?
  → image contains substantial text → candidate
     │
Logo/brand check:
  Is detected text a single word matching [A-Z][a-z]+ brand name? → exempt
     │
OCR text (e.g. Tesseract, PaddleOCR) → extracted text T
Is T reproducible as HTML/CSS? → FAIL (image of text)
Is T a logo/watermark? → PASS (logotype exemption)
Is T a chart label? → flag as informational image of text
```

**Model pipeline:**
| Stage | Tool | Latency |
|-------|------|---------|
| Text detection | PaddleOCR (DBNet) | ~50ms |
| OCR | PaddleOCR / Tesseract | ~100ms |
| Logo classification | CLIP zero-shot | ~30ms |
| Total | — | ~200ms per image |

**Already referenced in ka11y-node source:**
> `"OCR-level verification available via the Python pipeline."` (images-of-text check pass message)
This is the Python pipeline hook — `ka11y-python` can receive image URLs and run PaddleOCR.

---

### SC 2.1.4 — Character Key Shortcuts (intent detection)
**Current state:** Regex on `accesskey`, inline handler text, inline script
**Ceiling:** Cannot detect shortcuts in external scripts, framework event systems, or custom key-dispatch patterns

#### NLP Opportunity — Code Semantic Analysis

```
Inline script text / bundled JS (if accessible)
     │
     ▼
Code tokenization (tree-sitter or Babel AST)
     │
Pattern extraction:
  EventListener calls → extract event type + handler body
  Handler body → static analysis for key comparisons:
    event.key === 'x' / event.keyCode === 65 / etc.
     │
Modifier guard detection via AST (not regex proximity):
  Check if key comparison is inside an if-branch that also
  checks ctrlKey / altKey / metaKey
     │
No guard in AST path → ISSUE (high confidence, no false positives
from proximity mismatch)
```

**Tools:**
- `@babel/parser` + `@babel/traverse` (already available in Node ecosystem)
- `tree-sitter` for language-agnostic parsing
- No ML model needed — static AST analysis is already "smarter than regex"

---

### SC 2.4.5 — Multiple Ways (navigation mechanism quality)
**Current state:** Counts presence of search/nav/breadcrumb/sitemap/TOC
**Ceiling:** Cannot assess whether the mechanisms actually work or are meaningful

#### NLP Opportunity — Navigation Utility Classification

```
Extracted nav link texts (all <nav> / [role=navigation] links)
     │
     ▼
Text classifier (fine-tuned BERT or zero-shot via CLIP/GPT-4):
  Classes: [functional_nav | placeholder_nav | duplicate_nav]
     │
functional: links point to distinct sections → counts as a way
placeholder: all links say "Section 1", "Link 2" → doesn't count
duplicate: same links as main nav → doesn't count as a second way
```

---

### SC 2.4.7 — Focus Visible (focus indicator salience)
**Current state:** Detects style changes (outline, shadow, border, bg, color)
**Ceiling:** A 1px dotted grey outline technically passes the CSS check but is visually invisible to most users

#### CV Opportunity — Perceptual Salience of Focus Indicator

```
Puppeteer screenshot (unfocused state)
Puppeteer screenshot (focused state)
     │
     ▼
Pixel-diff (sharp / pixelmatch):
  diff image = |focused - unfocused|
     │
Salient region detection:
  connected component analysis on diff image
  → focus indicator bounding box
     │
Perceptual metrics:
  1. Area: indicator_pixels / element_pixels ≥ 2% → OK
  2. Contrast: APCA or WCAG contrast of indicator color vs bg
  3. Salience: Itti–Koch saliency map — is the focus indicator
     in a salient region of the diff? → human-visible
     │
salience score < threshold → focus indicator too subtle → ISSUE
```

**Tools:**
- `sharp` (already in Node ecosystem) for pixel diff
- `pixelmatch` npm package for structural similarity
- WCAG contrast formula (already implemented in focus-appearance.check.js)
- `opencv-python` for connected component labelling (Python side)

**Key advantage over current approach:**
Current check passes a `1px dotted rgba(0,0,0,0.3)` outline (technically has outline, technically changed). CV diff would correctly flag this as non-salient.

---

### SC 2.4.9 — Link Purpose (semantic generic detection)
**Current state:** Regex against 30+ hardcoded generic patterns in EN + JA
**Ceiling:** "Proceed", "Explore", "Discover" — not in the list. Non-EN languages beyond Japanese. Contextually generic ("More" for the 5th carousel item).

#### NLP Opportunity — Semantic Generic Link Classifier

```
link accessible name
     │
     ▼
Zero-shot text classifier (e.g. BART-MNLI, DeBERTa-MNLI):
  hypothesis: "This text describes the link destination specifically"
  labels: [descriptive, generic, ambiguous]
     │
OR: Sentence embedding similarity (e.g. all-MiniLM-L6-v2):
  embed link text
  compare to centroid of known-generic embeddings:
    ["click here", "read more", "more", "details", "learn more", …]
  cosine similarity > 0.75 → likely generic → ISSUE
     │
Language-agnostic: works in FR/DE/ES/ZH/KO/AR automatically
```

**Models:**
| Model | Size | Language | Latency |
|-------|------|----------|---------|
| `all-MiniLM-L6-v2` | 80 MB | Multilingual-ish | ~5ms/text |
| `paraphrase-multilingual-MiniLM-L12-v2` | 470 MB | 50+ languages | ~10ms |
| `facebook/bart-large-mnli` | 400 MB | EN | ~50ms |
| GPT-4o (zero-shot) | API | All | ~500ms |

**Training data (available):**
- WCAG failure examples from W3C techniques (H30, F84, F89)
- Scraped known-bad and known-good link texts from web audits

---

### SC 2.5.2 — Pointer Cancellation (interaction intent)
**Current state:** Keyword match in inline handler text for "action" words
**Ceiling:** Semantically equivalent actions written differently (`window.open(url)` detected but `router.push(path)` may not be)

#### NLP Opportunity — Code Intent Classification

```
Inline event handler text
     │
     ▼
Code-aware LLM (CodeBERT, CodeT5, or GPT-4 with code prompt):
  Prompt: "Does this mousedown handler perform an irreversible
           action (navigation, form submit, data mutation, network
           request) that a user cannot cancel?"
  Output: yes / no / uncertain
     │
yes → check for cancellation path → ISSUE if missing
```

**Simpler proxy using AST:**
```
AST parse handler → extract all function calls
  → check against known action APIs:
    fetch(), XMLHttpRequest, history.push/replace,
    window.location, document.cookie, localStorage.set,
    any custom method named send/submit/save/delete/update/create
```

---

### SC 2.5.7 — Dragging Movements (drag detection from visual behavior)
**Current state:** CSS attribute + library class markers
**Ceiling:** Custom canvas-based drag (D&D in `<canvas>`), pointer-event-based drag with no attributes, WebGL interactive elements

#### CV Opportunity — Interaction Affordance Detection

```
Page screenshot
     │
     ▼
Visual affordance classifier (fine-tuned ViT or CLIP):
  Detect visual drag affordance cues:
    - Drag handle icon (⠿ ≡ ⋮⋮ grid dots)
    - Reorder arrows
    - "Drag to reorder" label text
    - Dashed border / grab cursor hint
     │
  Detected → check for single-pointer alternative nearby
     │
Also: Cursor CSS detection:
  getComputedStyle(el).cursor === 'grab' || 'grabbing' || 'move'
  → draggable candidate (solvable in JS, no ML needed)
```

**Quick win (no model needed):**
```js
// Add to dragging-movements.check.js:
const DRAG_CURSORS = ['grab', 'grabbing', 'move', 'col-resize', 'row-resize'];
const hasDragCursor = DRAG_CURSORS.includes(window.getComputedStyle(el).cursor);
```

---

### SC 3.1.6 — Pronunciation (ruby coverage quality)
**Current state:** Counts kanji inside vs outside `<ruby>` → coverage ratio
**Ceiling:** Coverage % tells you quantity, not quality. Wrong readings, missing readings for ambiguous kanji (熟字訓), proper nouns not annotated.

#### NLP Opportunity — Japanese Ruby Quality Evaluation

```
Text node with kanji
     │
     ▼
Japanese morphological analyser (MeCab / SudachiPy / Fugashi):
  → tokenize → get reading for each token
     │
Compare predicted reading vs provided <ruby>/<rt> reading:
  Edit distance / exact match
     │
Mismatch → ruby annotation is incorrect → ISSUE (wrong guidance)
     │
Missing ruby for:
  - Named entities (NER model: person names, place names, org names)
  - Technical jargon (domain classifier)
  These require ruby more urgently than common kanji
```

**Models:**
| Tool | Task | Notes |
|------|------|-------|
| `fugashi` (MeCab wrapper) | Tokenization + reading | Fast, common in Python NLP |
| `SudachiPy` | Tokenization + normalization | Better for neologisms |
| `BERT-Japanese` (cl-tohoku) | Named entity recognition | For proper noun detection |

**Integration point:** `ka11y-python` already has NLTK — add `fugashi` or `sudachipy` for Japanese reading verification.

---

### SC 3.2.6 — Consistent Help (cross-page consistency)
**Current state:** Single-page scan only — detects help mechanisms but cannot verify they are in the same position across pages
**Ceiling:** The actual WCAG requirement is *cross-page* consistency

#### ML Opportunity — Multi-page Layout Similarity

```
Screenshots of N pages from same domain
     │
     ▼
For each page, detect help mechanism bounding box:
  Object detection model (DETR / YOLO) fine-tuned on:
    help buttons, chat widgets, contact links
     │
Cluster bounding box positions (k-means or DBSCAN):
  All help elements in same region (header/footer)? → consistent
  Help element moves around? → inconsistent → FAIL
     │
Also: DOM position fingerprint (no screenshot needed):
  Extract XPath / CSS path to help element on each page
  Jaccard similarity of paths across pages → consistency score
```

---

### SC 3.3.3 — Error Suggestion (message quality)
**Current state:** Regex for suggestion keywords + terse pattern blacklist
**Ceiling:** "Oops! That's not right." — passes regex (no terse pattern match) but provides zero correction guidance

#### NLP Opportunity — Error Message Quality Scoring

```
Error message text
     │
     ▼
NLI model (natural language inference):
  premise: error message text
  hypothesis: "This message tells the user how to correct their input"
  entailment score → quality score 0-1
     │
score < 0.6 → no correction guidance → ISSUE
score 0.6–0.8 → partial guidance → INCOMPLETE
score > 0.8 → good suggestion → PASS

Examples:
  "Invalid email" → entailment 0.1 → FAIL
  "Please enter a valid email like name@example.com" → entailment 0.92 → PASS
  "Oops! That's not right." → entailment 0.05 → FAIL (regex misses this)
```

**Models:**
| Model | Size | Task |
|-------|------|------|
| `cross-encoder/nli-deberta-v3-small` | 184 MB | NLI, fast |
| `facebook/bart-large-mnli` | 400 MB | NLI, accurate |
| `microsoft/deberta-v3-base` (fine-tuned) | 180 MB | Custom classifier |

**Training data:**
- WCAG 3.3.3 technique examples (G83, G84, G85)
- Web form error message corpus (scrape + label by accessibility experts)

---

### SC 3.3.4 — Error Prevention (safeguard intent classification)
**Current state:** Keyword match for "financial", "legal", "destructive" form context
**Ceiling:** "Make a contribution" = financial; "Terminate subscription" = destructive — missed without matching keyword

#### NLP Opportunity — Form Intent Classification

```
Form context: submit button text + form headings + surrounding text
     │
     ▼
Zero-shot text classifier:
  Labels: [financial_transaction, legal_agreement, data_deletion,
           account_modification, informational_only]
     │
  financial_transaction / legal_agreement / data_deletion → require safeguard check
  informational_only → no safeguard needed
```

**Models:**
- `facebook/bart-large-mnli` zero-shot (no fine-tuning needed)
- `sentence-transformers` similarity to prototype sentences:
  - "This form collects payment" → financial
  - "This action permanently deletes data" → destructive

---

### SC 3.3.7 — Redundant Entry (semantic field equivalence)
**Current state:** Autocomplete token matching + label keyword groups + Jaccard similarity
**Ceiling:** "Billing Address" ≡ "Payment Address" ≡ "Address for Invoice" — same semantic meaning, different strings, won't match keyword groups

#### NLP Opportunity — Semantic Field Equivalence

```
Field label / placeholder text from form A: "Billing Address"
Field label / placeholder text from form B: "Payment Address"
     │
     ▼
Sentence embedding (all-MiniLM-L6-v2 or multilingual variant):
  embed both label strings
  cosine similarity > 0.85 → semantically same field → redundancy candidate
     │
Already has reuse control? → OK
Is one field read-only? → OK (display, not re-entry)
→ else ISSUE
```

**Implementation:**
```python
from sentence_transformers import SentenceTransformer, util
model = SentenceTransformer('all-MiniLM-L6-v2')

def fields_are_equivalent(label_a, label_b, threshold=0.85):
    emb_a = model.encode(label_a, convert_to_tensor=True)
    emb_b = model.encode(label_b, convert_to_tensor=True)
    return util.cos_sim(emb_a, emb_b).item() > threshold
```

---

### SC 3.3.8 — Accessible Authentication (CAPTCHA type classification)
**Current state:** CSS class pattern matching for reCAPTCHA / hCaptcha / image CAPTCHA
**Ceiling:** New CAPTCHA providers, custom-styled CAPTCHAs without recognisable class names, visual puzzle CAPTCHAs with no ARIA markup

#### CV Opportunity — CAPTCHA Visual Detection

```
Page screenshot
     │
     ▼
Object detector (DETR / YOLO fine-tuned on CAPTCHA UI patterns):
  Detect: image grid CAPTCHA, slider CAPTCHA, puzzle CAPTCHA,
          text distortion CAPTCHA, checkbox "I'm not a robot"
     │
CAPTCHA type classified:
  image_selection → check for audio alternative (speaker icon)
  slider → check for non-drag alternative
  checkbox_style → check for keyboard operability
     │
No accessible alternative → ISSUE
```

**Training data:**
- Public CAPTCHA screenshot datasets (ICDAR, reCAPTCHA public samples)
- Fine-tune DETR/YOLO on labeled CAPTCHA UI screenshots

---

### SC 4.1.1 — Parsing (broken ARIA reference detection)
**Current state:** Duplicate ID detection only
**Ceiling:** Broken `aria-labelledby`/`aria-describedby` reference to non-existent ID, wrong role on element, ARIA attribute value type mismatch

#### NLP / Rule-based Opportunity (already solvable without ML)

```
Collect all ARIA reference attributes:
  aria-labelledby / aria-describedby / aria-controls /
  aria-owns / aria-activedescendant / aria-flowto
     │
For each referenced ID:
  document.getElementById(id) exists? → OK
  Does not exist → ISSUE (broken reference)
     │
Also:
  ARIA role + permitted attributes check:
    role="button" + aria-checked → invalid (use role="checkbox")
  → Rule-based, no ML needed; can use ARIA spec JSON (aria-query npm package)
```

**NLP extension:**
```
Element text + role → intent classifier:
  Does this element's visible text + structure match its role?
  e.g. <div role="button"> that contains a paragraph of text
  → may be a misapplied role
```

---

### SC 4.1.3 — Status Messages (live region content verification)
**Current state:** Detects live region presence; flags if dynamic contexts exist without them
**Ceiling:** Cannot verify that live region content is actually announced at runtime, or that the message text is meaningful

#### NLP Opportunity — Status Message Meaning Classification

```
Text injected into live region at runtime
(captured via MutationObserver during interaction testing)
     │
     ▼
Text classifier:
  Labels: [success_feedback, error_feedback, progress_update,
           count_update, irrelevant_noise]
     │
irrelevant_noise → live region used incorrectly (too noisy) → ISSUE
count_update with no context → user gets "3" with no meaning → ISSUE
success / error / progress → appropriate use → PASS
```

**MutationObserver integration (Node.js side):**
```js
// Inject before interaction tests:
await page.evaluate(() => {
  window.__liveRegionMutations = [];
  const obs = new MutationObserver(muts => {
    for (const m of muts)
      window.__liveRegionMutations.push(m.target.textContent.trim());
  });
  document.querySelectorAll('[aria-live], [role="status"], [role="alert"]')
    .forEach(el => obs.observe(el, { childList: true, characterData: true, subtree: true }));
});
// After tests:
const mutations = await page.evaluate(() => window.__liveRegionMutations);
// Send to NLP classifier
```

---

## Cross-cutting ML Infrastructure

### Proposed Pipeline Architecture

```
ka11y-node (Puppeteer checks)
     │
     │  findings with element metadata + screenshots
     ▼
ka11y-python ML layer (FastAPI)
     │
     ├── Vision service    (BLIP-2 / PaddleOCR / pixelmatch)
     │     • alt text quality (1.1.1)
     │     • OCR images of text (1.4.5)
     │     • Focus indicator salience (2.4.7)
     │     • Color-blind simulation (1.4.1)
     │     • CAPTCHA visual detection (3.3.8)
     │
     ├── NLP service       (Sentence-Transformers / DeBERTa / MeCab)
     │     • Link purpose semantic (2.4.9)
     │     • Error suggestion quality (3.3.3)
     │     • Form intent classification (3.3.4)
     │     • Field semantic equivalence (3.3.7)
     │     • Ruby reading verification (3.1.6)
     │
     ├── ASR service       (Whisper)
     │     • Transcript accuracy (1.2.1)
     │     • Caption WER (1.2.2)
     │
     └── AST / Code service (Babel / tree-sitter)
           • Shortcut modifier guard (2.1.4)
           • Pointer action intent (2.5.2)
```

---

## Priority Matrix

| SC | Technique | Impact | Effort | Priority |
|----|-----------|--------|--------|----------|
| 1.4.5 Images of text | PaddleOCR text detection | Very High | Low | **P1** |
| 2.4.9 Link purpose | Sentence embedding classifier | High | Low | **P1** |
| 3.3.3 Error suggestion | NLI quality scorer | High | Low | **P1** |
| 1.1.1 Alt text quality | Vision-language model | Very High | Medium | **P2** |
| 2.4.7 Focus salience | Pixel diff + saliency | High | Medium | **P2** |
| 1.4.1 Color in charts | Color-blind simulation | High | Medium | **P2** |
| 3.3.7 Redundant entry | Sentence embedding similarity | Medium | Low | **P2** |
| 1.2.1 Transcript accuracy | Whisper ASR + WER | High | Medium | **P2** |
| 3.3.4 Form intent | Zero-shot NLI | Medium | Low | **P2** |
| 3.1.6 Ruby quality | MeCab + reading comparison | Medium | Medium | **P3** |
| 1.3.2 Reading order | Layout analysis model | Medium | High | **P3** |
| 2.1.4 Key shortcut AST | Babel AST traversal | Medium | Low | **P3** |
| 3.3.8 CAPTCHA visual | DETR fine-tuned | High | High | **P3** |
| 3.2.6 Cross-page consistency | Multi-page layout similarity | Low | High | **P4** |
| 1.2.2 Caption quality | Pyannote + BERTScore | High | High | **P4** |

---

## Quick Wins (no GPU, no model training needed)

These use pre-trained models or lightweight transforms available as pip/npm packages:

| Check | Technique | Package | Time to implement |
|-------|-----------|---------|-------------------|
| 2.4.9 link-purpose | `all-MiniLM-L6-v2` cosine similarity | `sentence-transformers` | 1 day |
| 3.3.3 error-suggestion | `cross-encoder/nli-deberta-v3-small` | `sentence-transformers` | 1 day |
| 3.3.7 redundant-entry | `all-MiniLM-L6-v2` field label similarity | `sentence-transformers` | 0.5 day |
| 1.4.5 images-of-text | `paddleocr` text region detection | `paddlepaddle` + `paddleocr` | 1 day |
| 2.4.7 focus-visible | `pixelmatch` pixel diff | `pixelmatch` npm | 0.5 day |
| 2.5.7 drag cursor | CSS `cursor: grab/move` check | (pure JS, no model) | 2 hours |
| 2.1.4 shortcuts | `@babel/parser` AST | `@babel/parser` npm | 1 day |
| 1.4.1 color-blind | Brettel LMS matrix transform | (pure math, no model) | 0.5 day |
| 3.1.6 ruby readings | `fugashi` + `ipadic` | `fugashi` pip | 1 day |
