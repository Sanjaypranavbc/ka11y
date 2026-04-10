 # Reviewed ML / CV / NLP Approaches for Remaining and Review-Heavy WCAG Rules

> Baseline source: `COVERAGE.md` dated 2026-03-26
> Repo reconciliation date: 2026-04-10
> Stack assumption: Python (FastAPI + Playwright + existing `ka11y-python` pipeline) plus current Node custom checks

## Scope Notes

- This file is now a reviewed planning document, not a raw brainstorm.
- `COVERAGE.md` is slightly stale relative to the current repo. `1.3.3` is already implemented in `ka11y-python`, and `3.3.7`, `3.3.8`, `1.4.5`, and `2.5.8` already provide reusable foundations.
- The main correction throughout this document is: do not auto-`fail` criteria that depend on semantic completeness, editorial quality, essentiality, or off-page alternatives unless the evidence is strong enough to prove non-conformance.

## Confidence Scale

- `8-10/10`: strong production candidate for direct automation.
- `5-7/10`: useful heuristic, but expect some `needs_review`.
- `1-4/10`: research/supporting signal only; do not market as deterministic coverage.

## Global Corrections Made

- `2.3.2` is not "no flashing at all"; it is "no more than 3 flashes in any 1-second period."
- `1.4.8` is about a mechanism to achieve the presentation. `letter-spacing` is not part of this SC.
- `2.5.5` does not inherit the `2.5.8` spacing exception. Its exceptions are `Equivalent`, `Inline`, `User Agent Control`, and `Essential`.
- `3.2.5` is about context changes that happen without explicit user request. Passive auto-refresh belongs elsewhere.
- `1.2.7` is about provided extended-described media, not a player feature like "pause on description."
- `3.3.9` can pass with password-based login when an alternative or assistive mechanism exists.
- Tool-generated ASR can help triage `1.2.4` and `1.2.9`, but it never proves the site itself provides captions or a live text alternative.

## Japanese Language Analysis

- Repo baseline: Japanese support is already materially present in [JAPANESE_COVERAGE_REPORT.md](/home/pranav/Documents/ka11y/JAPANESE_COVERAGE_REPORT.md) and [COVERAGE_JA.md](/home/pranav/Documents/ka11y/COVERAGE_JA.md).
- Reusable Japanese foundations already in repo:
  - `sensory_auditor.py` already has Japanese/CJK taxonomy and language detection.
  - OCR already supports `ja + en` / PaddleOCR `japan`.
  - `rendered_layout_crawler.py` already has CJK-aware text-spacing overrides.
  - Node custom checks already include many JP heuristics for auth, help, transcripts, breadcrumbs, link purpose, and error patterns.
- Main implementation rule: do not build ad hoc per-check Japanese regexes everywhere. Add shared JP text-normalization, tokenization, synonym, and media-label utilities, then reuse them across rule families.

### Japanese Readiness by Family

| Family | JP impact | How to tackle |
| --- | --- | --- |
| `NEXT-MEDIA` | Medium | Add Japanese media labels and transcript/caption/sign-language lexicons: `字幕`, `キャプション`, `ライブ字幕`, `書き起こし`, `文字起こし`, `音声解説`, `音声ガイド`, `手話`, `日本手話`, `JSL`, `解説版`. Keep media-quality judgment mostly language-agnostic after discovery. |
| `NEXT-NLP` | High | English token/word-boundary logic will fail on Japanese. Use `lang=ja` plus CJK density detection, NFKC normalization, SudachiPy/fugashi or spaCy Japanese tokenization, and multilingual embeddings rather than English-only models. |
| `NEXT-CROSS` | Medium-High | Normalize full-width/half-width characters, kana/romanized variants, and common UI synonyms like `ログイン` / `サインイン`, `検索` / `さがす`, `ヘルプ` / `サポート` / `お問い合わせ`. Prefer destination/action identity over text similarity alone. |
| `NEXT-LAYOUT` | High | Preserve existing CJK spacing behavior. Handle `ruby`, vertical writing, shorter readable line lengths, and avoid importing Latin typography assumptions directly into Japanese checks. |
| `NEXT-FLOW` | Medium | Expand JP auth/help/error/confirmation keywords and watch for Japanese enterprise UI patterns such as OTP, postal-code autofill, furigana fields, address normalization, and multi-step registration forms. |
| `NEXT-TIME` / `NEXT-INTERACT` / `P-CRAWL` | Low | Mostly language-agnostic. Japanese work is mainly around labels/messages emitted to users and around recognizing JP warning/help text when the rule depends on visible messaging. |

### Japanese-Specific Gaps for These Reviewed Rules

| Rule group | Japanese-specific risk | Recommended tactic |
| --- | --- | --- |
| `1.2.3` to `1.2.9` | Discovery misses JP transcript/caption/sign-language labels | Centralize JP media-keyword detection and support separate described/transcript pages, not just adjacent text. |
| `1.3.6`, `3.1.3`, `3.1.4`, `3.1.5` | English word boundaries and readability formulas are unreliable | Use JP tokenization, glossary markers like `用語集`, `注釈`, `説明`, and easy-language markers like `やさしい日本語`, `ふりがな`, `読み仮名`, `ルビ`. |
| `3.2.3`, `3.2.4` | Text-only matching breaks on JP synonyms and mixed-script labels | Normalize NFKC, compare route/action identity first, then compare normalized labels with multilingual embeddings. |
| `3.3.5`, `3.3.6`, `3.3.9` | Help/auth/review language is often highly domain-specific in Japanese | Extend lexicons for `確認`, `見直し`, `修正`, `やり直し`, `お問い合わせ`, `サポート`, `認証`, `二段階認証`, `ワンタイムパスワード`, `画像認証`, `パズル認証`. |
| `1.4.8`, `2.4.10` | Latin presentation assumptions produce false positives on Japanese text | Keep CJK spacing exceptions, add `ruby` and `writing-mode` handling, and use the SC's `40`-character guidance for CJK text blocks. |

### Japanese Implementation Strategy

1. Add shared JP text utilities instead of duplicating regexes:
   - Unicode normalization via `unicodedata.normalize("NFKC", text)`
   - full-width/half-width normalization
   - kana/romanized variant handling for high-value UI terms
   - optional `ruby` stripping plus base-text extraction

2. Build one Japanese lexical package reused across checks:
   - media labels
   - help/support labels
   - auth/captcha/OTP labels
   - confirmation/review/undo labels
   - glossary/definition markers
   - easy-language markers

3. Use Japanese-aware NLP only where text semantics actually matter:
   - `3.1.3`, `3.1.4`, `3.1.5`, `1.3.6`, `3.2.4`
   - prefer multilingual embeddings plus deterministic filters
   - avoid English readability formulas for Japanese

4. Keep CJK typography logic centralized:
   - preserve the current text-spacing exception model
   - add explicit handling for `ruby`, `rt`, and `writing-mode: vertical-rl`
   - do not apply Latin-style word-spacing expectations to Japanese

5. Expand test coverage before claiming JP-ready support for new rules:
   - full Japanese fixture pages
   - mixed JP/EN pages
   - forms with `必須`, `任意`, postal code/address autofill, furigana
   - auth with `ログイン`, `サインイン`, OTP, CAPTCHA
   - transcript/caption/sign-language media pages

### Japanese Rule Triage

- Best near-term Japanese additions:
  - `2.5.5`, `1.4.9`, `2.3.1`, `2.3.2`, `3.3.7`
  - Reason: these are mostly language-agnostic or already have the needed JP foundations.

- Medium Japanese effort:
  - `3.2.3`, `3.2.4`, `3.3.9`, `2.4.10`, `1.4.8`
  - Reason: the checks are feasible, but label normalization and Japanese UI conventions matter.

- High Japanese effort / review-heavy:
  - `1.2.3` to `1.2.9`, `1.3.6`, `3.1.3`, `3.1.4`, `3.1.5`, `3.3.5`, `3.3.6`
  - Reason: these depend on Japanese semantics, editorial intent, or content completeness, not just page structure.

### Japanese Workflow

```text
Detect page/media language
  -> if lang=ja or CJK density is high, switch to JP pipeline
  -> normalize Unicode (NFKC), width variants, and ruby/base text
  -> apply shared JP lexicons and JP-aware tokenization where semantics matter
  -> keep layout/CV/numeric checks language-agnostic where possible
  -> emit PASS / FAIL only for high-confidence evidence
  -> otherwise emit NEEDS_REVIEW with JP-specific evidence attached
```

## Rule-by-Rule Review

## NEXT-MEDIA

### 1.2.3 - Audio Description or Media Alternative (Prerecorded)
- Verdict: Partly correct, but the original draft over-failed. The SC allows either audio description or a full media alternative.
- Recommended approach: detect prerecorded synchronized media, collect description tracks and linked transcript/media-alternative assets, then use ASR plus vision-language scene summaries only to estimate whether important visual-only information exists.
- Workflow diagram:
```text
Detect prerecorded synchronized media
  -> find AD tracks / described version / transcript assets
  -> estimate visual-only moments with ASR + scene summaries
  -> compare site-provided alternative against those moments
  -> explicit strong coverage = PASS
  -> strong uncovered visual-only info with no alternative = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: auto-`pass` only when there is an explicit described version or a labeled full transcript/media alternative with strong coverage; auto-`fail` only when crawl scope is complete and unresolved visual-only content is strongly evidenced; otherwise `needs_review`.
- Edge cases covered: audio description already baked into the main soundtrack, off-page transcript/PDF, videos that are themselves media alternatives for text, third-party iframe players, screen-share demos with important on-screen text.
- Confidence: `4/10`

### 1.2.4 - Captions (Live)
- Verdict: Mostly useful as detection, but the original `pass` logic was too loose. Live captions must be provided by the content, not generated by the scanner.
- Recommended approach: detect live streams, inspect player tracks/manifests for rolling WebVTT or embedded 608/708 captions, and watch the rendered player for an actual live caption region.
- Workflow diagram:
```text
Detect candidate live media
  -> inspect manifest, tracks, and rendered player state
  -> observe short live playback window
  -> captions exposed by content/player = PASS
  -> confirmed live stream with no caption provision = FAIL
  -> ambiguous or inaccessible stream = NEEDS_REVIEW
```
- Output policy: auto-`pass` only when the live player or manifest clearly exposes captions; auto-`fail` only when the stream is confirmed live and no caption provision is detectable after observation; otherwise `needs_review`.
- Edge cases covered: HLS/DASH in-band captions, rolling caption endpoints, access-restricted live players, embedded third-party streams, temporary caption outages, sign-language overlays that do not replace caption requirements.
- Confidence: `3/10`

### 1.2.5 - Audio Description (Prerecorded)
- Verdict: Needs correction. Unlike `1.2.3`, a text alternative is not enough here; the media must provide audio description unless all important visuals are already covered in the main audio.
- Recommended approach: reuse the `1.2.3` media pipeline, but treat transcript-only evidence as insufficient; look for a described audio track, a separate described version, or strong evidence that the main soundtrack already fully narrates the visuals.
- Workflow diagram:
```text
Detect prerecorded video with audio
  -> search for described track or alternate described version
  -> estimate whether important visual-only info exists
  -> no visual-only info or explicit described media = PASS
  -> visual-only info with no described media = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: auto-`pass` only with explicit described media or strong evidence that no visual-only information exists; auto-`fail` only with strong evidence of important undescribed visual content and no described version; otherwise `needs_review`.
- Edge cases covered: integrated description in the main audio, alternate described video versions, talking-head videos with no visual-only meaning, videos with large amounts of on-screen text, training demos and product walkthroughs.
- Confidence: `4/10`

### 1.2.6 - Sign Language (Prerecorded)
- Verdict: The original detection idea was too optimistic. Pose detection can suggest a signer window exists, but not that sign language is correct, complete, synchronized, or in the expected language.
- Recommended approach: search for explicit sign-language variants and labels first, then use CV only as a supporting signal for a likely interpreter window.
- Workflow diagram:
```text
Detect prerecorded synchronized media
  -> search for explicit sign-language labels / alternate versions
  -> use CV only to support likely interpreter-window detection
  -> labeled sign-language version found = PASS
  -> unlabeled signer-like evidence = NEEDS_REVIEW
  -> otherwise = likely FAIL only in controlled scan scope
```
- Output policy: auto-`pass` only when a clearly labeled sign-language version is exposed; keep candidate signer overlays as `needs_review`; avoid hard `fail` unless scan scope is controlled and complete.
- Edge cases covered: separate signer video, picture-in-picture interpreter window, ASL/BSL/JSL language mismatch, presenter gesturing falsely resembling signing, static placeholder interpreter panes.
- Confidence: `2/10`

### 1.2.7 - Extended Audio Description (Prerecorded)
- Verdict: The original section was materially wrong. The requirement is about the provided media version, not whether the player has "pause-on-description capability."
- Recommended approach: detect likely cases where standard description cannot fit into natural pauses, then look for an alternate extended-described version or playback evidence that the video itself pauses to accommodate longer description.
- Workflow diagram:
```text
Detect visual-only segments needing long description
  -> check if natural pauses are insufficient
  -> search for extended-described variant or paused-description playback
  -> explicit extended version / playback evidence = PASS
  -> insufficient evidence either way = NEEDS_REVIEW
```
- Output policy: auto-`pass` only with an explicit extended-described version or clear paused-description playback evidence; otherwise default to `needs_review`.
- Edge cases covered: media that already has enough natural pause time, alternate extended-described versions, videos with constant narration, timeline-controlled training media, long silent visual sequences.
- Confidence: `2/10`

### 1.2.8 - Media Alternative (Prerecorded)
- Verdict: The general direction is right, but coverage scoring must target a site-provided full transcript or media alternative, not a scanner-generated substitute.
- Recommended approach: find transcript pages, details blocks, downloadable docs, or alternate pages, then compare them against ASR plus scene-summary coverage for both audio and visuals.
- Workflow diagram:
```text
Detect prerecorded synchronized media
  -> discover transcript / media-alternative assets
  -> build speech + visual coverage summary
  -> compare site-provided alternative against combined coverage
  -> strong full alternative = PASS
  -> no alternative in crawl scope = FAIL
  -> partial / uncertain coverage = NEEDS_REVIEW
```
- Output policy: auto-`pass` when a labeled full transcript/media alternative exists and coverage is strong; auto-`fail` when no such mechanism exists in crawl scope; otherwise `needs_review`.
- Edge cases covered: off-page transcript links, PDF and DOC transcripts, interactive video outcomes, multilingual transcripts, transcripts that capture dialogue but miss visual state changes.
- Confidence: `5/10`

### 1.2.9 - Audio-only (Live)
- Verdict: Same core issue as `1.2.4`: locally generated streaming ASR does not prove compliance.
- Recommended approach: confirm the media is live and audio-only, then look for a site-provided rolling transcript, caption feed, or synchronized live text region.
- Workflow diagram:
```text
Detect live audio-only stream
  -> search for rolling transcript / live text region
  -> observe whether the text updates with the stream
  -> site-provided real-time text alternative = PASS
  -> confirmed live audio-only with no text provision = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: auto-`pass` only when the page provides a real-time text alternative; auto-`fail` only when live audio-only content is confirmed and no text alternative is detectable after observation; otherwise `needs_review`.
- Edge cases covered: live radio embeds, iframe-based players, caption feeds in a sibling page region, slight transcript latency, hosted social/live-audio platforms.
- Confidence: `3/10`

### 1.4.7 - Low or No Background Audio
- Verdict: Useful idea, but Demucs-style source separation should be treated as evidence, not proof. A normal volume slider is not enough; the user must be able to turn off the background sounds, not just all audio.
- Recommended approach: first classify whether the clip is speech-dominant prerecorded audio, then estimate speech/background separation and dB difference, and separately detect true independent background-audio controls.
- Workflow diagram:
```text
Detect prerecorded speech-dominant audio
  -> separate speech and accompaniment tracks
  -> estimate dB gap and detect independent background-audio controls
  -> >=20 dB gap or true background-off control = PASS
  -> strong intrusive background audio with no control = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: auto-`pass` with strong consistent `>= 20 dB` separation or a real separate background-off control; auto-`fail` only with strong evidence of intrusive background audio and no independent control; otherwise `needs_review`.
- Edge cases covered: podcast intro music, stereo ambience, multi-speaker overlap, auto-ducked background tracks, music beds that stop during speech, master-volume controls that do not satisfy the criterion.
- Confidence: `4/10`

### 2.3.1 - Three Flashes or Below Threshold
- Verdict: Strong candidate for CV automation. This is one of the better fits for frame analysis.
- Recommended approach: record rendered content at a reliable frame rate, analyze luminance and red-transition changes in sliding windows, and align the implementation to Harding/FPA-style thresholds instead of ad hoc luma deltas alone.
- Workflow diagram:
```text
Record rendered content at stable FPS
  -> detect luminance/red flash candidates per region
  -> apply general-flash and red-flash thresholds
  -> no threshold breach = PASS
  -> threshold breach = FAIL
  -> poor capture fidelity = NEEDS_REVIEW
```
- Output policy: auto-`pass` when no region breaches the general flash or red flash thresholds; auto-`fail` when the thresholds are exceeded; use `needs_review` only when capture fidelity is insufficient.
- Edge cases covered: animated GIFs, CSS keyframes, canvas/WebGL effects, autoplay video ads, carousels, HDR/color-space issues, cross-origin video capture limits.
- Confidence: `7/10`

### 2.3.2 - Three Flashes
- Verdict: Needs a wording correction, but the same analysis family is appropriate. This SC still uses the `> 3 flashes in 1 second` threshold; it is not a ban on all flashing.
- Recommended approach: reuse the `2.3.1` capture pipeline, but apply the stricter AAA rule without the "below threshold" escape.
- Workflow diagram:
```text
Record rendered content at stable FPS
  -> count flashes in every 1-second window
  -> >3 flashes in any window = FAIL
  -> otherwise = PASS
  -> poor capture fidelity = NEEDS_REVIEW
```
- Output policy: auto-`pass` when nothing flashes more than 3 times in any 1-second period; auto-`fail` when it does; `needs_review` only when capture fidelity is insufficient.
- Edge cases covered: lightning-style full-screen flashes, small flashing widgets, looping animations, embedded media, repeated red flash content.
- Confidence: `8/10`

## NEXT-NLP

### 1.3.3 - Sensory Characteristics
- Verdict: This is no longer just a proposal. The repo already has `sensory_crawler.py` and `sensory_auditor.py`, and that is the right baseline.
- Recommended approach: keep the current instruction-focused text extraction, sensory term detection, and nearby non-sensory disambiguation, then use NLP only to reduce false positives rather than replace the rules with a pure NLI model.
- Workflow diagram:
```text
Extract instructional text candidates
  -> detect sensory-only terms (color/shape/position/sound)
  -> check for stable non-sensory identifier nearby
  -> sensory-only instruction = FAIL
  -> sensory hint plus stable identifier = PASS
  -> missing surrounding context = NEEDS_REVIEW
```
- Output policy: auto-`fail` when the instruction relies only on color/shape/position/sound; auto-`pass` when the same instruction also includes a stable identifier such as visible text or programmatic label; use `needs_review` where surrounding context is incomplete.
- Edge cases covered: multilingual instructions, quoted control names, "the Submit button on the right" style mixed guidance, required fields identified by color alone, placeholder-based instructions.
- Confidence: `8/10`

### 1.3.6 - Identify Purpose
- Verdict: The draft over-promised. This SC is broader than "label your icons" and current platform support is incomplete, so a full conformance check is not realistic.
- Recommended approach: treat this as a bundle of useful proxies only: landmark semantics, consistent region naming, autocomplete coverage for known personal-data fields, and likely unlabeled icon-purpose candidates.
- Workflow diagram:
```text
Inventory icons, regions, and inputs
  -> infer purpose proxies from labels, semantics, and known mappings
  -> purpose clearly exposed by supported proxy = positive signal
  -> likely hidden/unlabeled purpose = NEEDS_REVIEW candidate
  -> do not claim full SC-wide PASS/FAIL
```
- Output policy: emit `needs_review` candidates rather than claiming full `pass/fail` coverage for the SC as a whole.
- Edge cases covered: ambiguous icons, brand marks vs functional icons, composite widgets, page-specific region semantics, same icon used for different actions in different contexts.
- Confidence: `3/10`

### 3.1.3 - Unusual Words
- Verdict: Good candidate extraction idea, but poor candidate for deterministic conformance. "Unusual" and "restricted" are deeply audience- and domain-dependent.
- Recommended approach: detect jargon/idiom candidates with frequency lists plus domain heuristics, then look for local definitions, glossaries, or expansion mechanisms.
- Workflow diagram:
```text
Extract substantive prose
  -> detect jargon / idiom / rare-word candidates
  -> search for definitions, glossary links, or local expansion
  -> definition found = positive signal
  -> unexplained candidate term = NEEDS_REVIEW
```
- Output policy: prefer `needs_review` candidates; do not auto-`fail` an entire page solely from corpus rarity.
- Edge cases covered: product names, proper nouns, quoted technical text, code samples, multilingual pages, education/training sites where jargon is intentionally taught.
- Confidence: `4/10`

### 3.1.4 - Abbreviations
- Verdict: Reasonable automation target if heavily filtered. The original idea is sound, but raw all-caps regexes will be noisy.
- Recommended approach: detect abbreviations in prose, ignore units/dates/code, then check for `<abbr>`, first-use expansion, glossary entries, or explicit nearby definitions.
- Workflow diagram:
```text
Extract prose tokens
  -> detect likely abbreviations after filtering noise
  -> look for <abbr>, first-use expansion, or glossary support
  -> clear expansion present = PASS
  -> clear unexplained abbreviation in prose = FAIL
  -> ambiguous token = NEEDS_REVIEW
```
- Output policy: auto-`fail` only on clear unexplained abbreviations in normal prose; use `needs_review` for ambiguous cases.
- Edge cases covered: acronyms that are ordinary words, code snippets, legal references, all-caps headings, screen-reader-only expansions, locale-specific abbreviations.
- Confidence: `6/10`

### 3.1.5 - Reading Level
- Verdict: The original formula-only `fail` rule was too strong. Readability formulas are triage signals, not conformance proof.
- Recommended approach: score only substantial prose blocks, exclude navigation and boilerplate, then combine readability signals with detection of easy-read/plain-language/simplified alternatives.
- Workflow diagram:
```text
Extract substantial prose blocks
  -> compute readability ensemble
  -> look for simplified / easy-read alternative
  -> complex text plus clear simplified alternative = PASS
  -> high reading level with no alternative = NEEDS_REVIEW
```
- Output policy: use high reading-grade scores primarily to raise `needs_review`; auto-`pass` is safer when a clear simplified alternative exists; auto-`fail` should be avoided without manual confirmation.
- Edge cases covered: legal or medical content, proper names and titles, tables and lists, mixed-language text, short pages, OCR/syllable-count errors.
- Confidence: `4/10`

## NEXT-MOTION

### 2.5.1 - Pointer Gestures
- Verdict: Useful direction, but "gesture library detected" is not enough. The actual requirement is a single-pointer alternative for multi-point or path-based gestures.
- Recommended approach: detect gesture-capable widgets through JS/event analysis, then exercise the widget to find whether the same outcome is available with a tap/click/button or another single-pointer method.
- Workflow diagram:
```text
Detect gesture-capable widget
  -> identify required multi-point or path gesture
  -> test for equivalent single-pointer action
  -> equivalent single-pointer action works = PASS
  -> gesture required and no equivalent found = FAIL
  -> unclear widget behavior = NEEDS_REVIEW
```
- Output policy: auto-`fail` only when a multi-point/path gesture is clearly required and no single-pointer alternative is found; otherwise `needs_review`.
- Edge cases covered: pinch-to-zoom maps, drawing/signature pads, swipe carousels, drag-only controls, browser-native pinch zoom that is not authored functionality, canvas widgets.
- Confidence: `5/10`

### 2.5.4 - Motion Actuation
- Verdict: The API scan is useful, but the original section incorrectly treated `prefers-reduced-motion` as a motion-actuation disable mechanism.
- Recommended approach: detect actual use of motion/orientation events, then verify both a non-motion UI alternative and a way to disable motion-triggered activation.
- Workflow diagram:
```text
Detect motion/orientation-driven functionality
  -> map action triggered by device movement
  -> test for equivalent UI control and disable mechanism
  -> both present = PASS
  -> motion action with missing alternative or disable = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: auto-`fail` when motion-triggered functionality is found without an equivalent control or disable mechanism; otherwise `needs_review` unless the alternative is clearly exercised.
- Edge cases covered: shake-to-undo, tilt controls, platform permission prompts, sensor APIs guarded by feature flags, dead code paths, games where motion is essential.
- Confidence: `5/10`

### 2.3.3 - Animation from Interactions
- Verdict: Good fit for rendered testing. The core idea is right once narrowed to motion animation, not every visual change.
- Recommended approach: detect motion-triggered transforms or animated movement on hover/focus/click/drag, then rerun interactions under `prefers-reduced-motion: reduce` or an in-page disable setting and compare the rendered behavior.
- Workflow diagram:
```text
Detect interaction-triggered motion
  -> rerun under reduced-motion or in-page disable control
  -> motion suppressed for non-essential effect = PASS
  -> non-essential motion still runs = FAIL
  -> essentiality or behavior unclear = NEEDS_REVIEW
```
- Output policy: auto-`pass` when motion is disabled under reduced-motion or equivalent control; auto-`fail` when non-essential motion still runs; use `needs_review` for essential-motion cases.
- Edge cases covered: color-only transitions that are out of scope, drag inertia, parallax, focus indicators, non-essential hover flourish, mandatory spatial feedback in editors/games.
- Confidence: `7/10`

## NEXT-FLOW

### 3.3.7 - Redundant Entry
- Verdict: Strong approach and high leverage. This should extend the existing Node static rule, not replace it.
- Recommended approach: use Playwright to complete multi-step processes with seeded data, semantically match repeated fields across steps, and check whether the previously entered value is auto-populated or selectable.
- Workflow diagram:
```text
Fill step-1 data in a multi-step process
  -> advance to next step / repeated form
  -> semantically match repeated fields
  -> auto-populated or selectable reuse = PASS
  -> same required data re-entered without exception = FAIL
```
- Output policy: auto-`fail` when the same required data is requested again in the same process without auto-population or selection support, unless an exception applies; auto-`pass` when reuse is built in.
- Edge cases covered: security re-entry such as password confirmation, intentionally invalidated information, cross-domain checkout flows, address-book selection, read-only summaries that do not require re-entry.
- Confidence: `8/10`

### 3.3.5 - Help
- Verdict: The original "no help mechanism found -> fail" logic was too strict. This SC is about help being available where it is needed for completion, not every form having a help icon.
- Recommended approach: target complex tasks first, detect context-specific help around fields and process steps, and use semantic similarity only as a relevance hint.
- Workflow diagram:
```text
Detect complex task or process step
  -> find nearby contextual help, hints, or expandable guidance
  -> help clearly task-specific = PASS
  -> complex task with no contextual help signal = NEEDS_REVIEW / possible FAIL
  -> simple task = out of primary target set
```
- Output policy: prefer `needs_review`; auto-`pass` is reasonable when rich task-specific help is present, but auto-`fail` should be reserved for obviously complex tasks with no contextual assistance.
- Edge cases covered: simple forms that do not need extra help, inline hint text, delayed tooltips, FAQs that are generic but not task-specific, help tucked behind expandable disclosure widgets.
- Confidence: `3/10`

### 3.3.6 - Error Prevention (All)
- Verdict: The general idea is useful, but "no confirm page found -> fail" is too blunt. Reversible, checked, or confirmable can be implemented in several different ways.
- Recommended approach: submit test flows in safe environments, observe whether the process includes review, reversible undo/cancel, or robust checking/confirmation before final commit.
- Workflow diagram:
```text
Submit safe test flow
  -> inspect for review, reversible undo/cancel, or confirmation/checking
  -> any allowed protection clearly present = PASS
  -> state-changing submit with none present = FAIL
  -> uncertain server-side behavior = NEEDS_REVIEW
```
- Output policy: auto-`pass` when one of the allowed protections is clearly exercised; auto-`fail` only for high-confidence state-changing submissions that show none of them; otherwise `needs_review`.
- Edge cases covered: search forms, draft autosave, editable review pages, post-submit undo toasts, server-side confirmation email flows, profile updates that remain editable.
- Confidence: `4/10`

### 3.3.9 - Accessible Authentication (Enhanced)
- Verdict: Good candidate to build on top of the existing Node `3.3.8` checker, but the original wording was too aggressive about passwords and too fuzzy about OTP flows.
- Recommended approach: extend current auth detection to include object-recognition and user-supplied media recognition failures, then separately detect assistive mechanisms such as password managers, copy/paste, autofill, passkeys, magic links, or third-party auth.
- Workflow diagram:
```text
Detect authentication flow
  -> search for cognitive/object-recognition blockers
  -> search for assistive mechanisms and non-cognitive alternatives
  -> auth possible without object recognition and with assistive support = PASS
  -> blocker present with no acceptable mechanism = FAIL
  -> OTP/TOTP or edge flow ambiguity = NEEDS_REVIEW
```
- Output policy: auto-`pass` when authentication can be completed without object recognition and with a non-cognitive method or assistive mechanism; auto-`fail` for CAPTCHA/object-recognition or paste/autofill blocking without an alternative/mechanism; use `needs_review` for OTP/TOTP flows.
- Edge cases covered: email/SMS codes with autofill, passkeys, OAuth, password reveal plus paste support, bank-grid cards, one-time codes that must be transcribed, audio CAPTCHA that still fails Enhanced.
- Confidence: `6/10`

## NEXT-CROSS

### 3.2.3 - Consistent Navigation
- Verdict: Good multi-page automation target.
- Recommended approach: crawl several pages per template cluster, extract repeated navigation regions, and compare the relative order of shared navigation items rather than doing naive full-list equality.
- Workflow diagram:
```text
Crawl comparable pages in same template family
  -> extract repeated navigation regions
  -> compare relative order of shared items
  -> same relative order = PASS
  -> unexpected reordering = FAIL
  -> personalized/template-divergent nav = NEEDS_REVIEW
```
- Output policy: auto-`fail` when repeated navigation changes order unexpectedly across comparable pages; auto-`pass` when shared items stay in the same relative order; use `needs_review` for personalized or template-divergent areas.
- Edge cases covered: current-page item omitted or disabled, responsive hamburger vs desktop menus, footer navigation, user-specific menu items, locale or campaign variants, process-step navigation that is not global navigation.
- Confidence: `7/10`

### 3.2.4 - Consistent Identification
- Verdict: Good candidate, but pure sentence-embedding clustering is too risky. Similar language does not always mean same function, and same function is better proven through destination/action fingerprints.
- Recommended approach: group repeated controls by destination, role, action signature, icon hash, or stable component identity first, then compare accessible names and visible labels.
- Workflow diagram:
```text
Crawl comparable pages
  -> group same-function controls by action/destination identity
  -> compare accessible names and visible labels within each group
  -> stable identification across group = PASS
  -> same function with inconsistent identification = FAIL
  -> weak grouping confidence = NEEDS_REVIEW
```
- Output policy: auto-`fail` only when the same function is strongly evidenced and identified inconsistently; otherwise `needs_review`.
- Edge cases covered: locale wording differences, same text with different actions, icon-only buttons, search/cart/account controls, CTA copy changes in marketing pages.
- Confidence: `5/10`

## NEXT-LAYOUT

### 1.4.8 - Visual Presentation
- Verdict: The original section needed major correction. This SC is about a mechanism that lets users achieve the presentation, not only the page's default computed style, and `letter-spacing` is not part of it.
- Recommended approach: test whether blocks of text can be restyled to user-selected foreground/background colors, left alignment instead of full justification, line spacing of at least `1.5`, paragraph spacing of at least `1.5` lines, and width no more than `80` characters (`40` for CJK text).
- Workflow diagram:
```text
Identify substantial text blocks
  -> apply user-style overrides or built-in presentation controls
  -> verify color, alignment, spacing, and width targets can be achieved
  -> targets achievable = PASS
  -> author styling blocks them = FAIL
  -> mixed/incomplete support = NEEDS_REVIEW
```
- Output policy: auto-`pass` only when those overrides can be applied or a built-in presentation control exists; auto-`fail` when author styling prevents users from achieving them; otherwise `needs_review`.
- Edge cases covered: CJK content, user-style override limitations by browser, canvas/PDF text, text images, default styles that already comply but are not user-adjustable, article vs app-shell text blocks.
- Confidence: `5/10`

### 2.4.10 - Section Headings
- Verdict: Reasonable structural heuristic. The original ratio-based idea is acceptable once framed as a content-structure heuristic rather than a universal fail rule.
- Recommended approach: identify substantial topic blocks, detect heading structure for each block, and use topic-shift signals only to raise confidence that a new section exists.
- Workflow diagram:
```text
Segment page into substantial content blocks
  -> detect headings and topic boundaries
  -> blocks consistently headed = PASS
  -> repeated substantial unheaded sections = FAIL
  -> weak topic-boundary confidence = NEEDS_REVIEW
```
- Output policy: auto-`fail` when a clearly multi-section page repeatedly lacks headings for substantial content regions; auto-`pass` when sectioning is explicit; otherwise `needs_review`.
- Edge cases covered: short single-topic pages, dashboards with cards, accordions/tabs, visually hidden headings, endless feeds, pages where landmarks exist but section headings do not.
- Confidence: `6/10`

## NEXT-TIME

### 2.2.3 - No Timing
- Verdict: Very hard to automate correctly. Detecting timers is easy; proving the timing is non-essential is not.
- Recommended approach: use timer detection only to locate candidate timed tasks, then attempt the task with and without time pressure where possible and classify real-time-event exceptions separately.
- Workflow diagram:
```text
Detect timed task candidates
  -> classify likely exception vs authored time limit
  -> exercise flow with and without time pressure where possible
  -> clearly non-essential timing = PASS
  -> clearly required timing with no exception = FAIL
  -> otherwise = NEEDS_REVIEW
```
- Output policy: default to `needs_review`; reserve auto-`fail` for flows where timing is clearly required and no exception applies.
- Edge cases covered: live events, synchronized media, games and auctions, security timeouts, autosaved workflows, forms that can be resumed.
- Confidence: `3/10`

### 2.2.5 - Re-authenticating
- Verdict: Good product value, but operationally hard. Cookie clearing alone is not a faithful proxy for real expiry in many apps.
- Recommended approach: use configurable auth harnesses or controlled environments, preserve in-progress form state, then force a real reauthentication boundary and observe whether the state survives.
- Workflow diagram:
```text
Authenticate and enter substantial data
  -> trigger real reauthentication boundary
  -> reauthenticate and restore flow
  -> in-progress state preserved = PASS
  -> state lost = FAIL
  -> auth harness cannot faithfully reproduce expiry = NEEDS_REVIEW
```
- Output policy: auto-`pass` when state is restored after reauth; auto-`fail` when the data is lost; otherwise `needs_review`.
- Edge cases covered: SSO redirects, cross-domain providers, carts stored server-side, autosaved drafts, CSRF token renewal, logout vs idle expiry.
- Confidence: `4/10`

### 2.2.6 - Timeouts
- Verdict: The original static scan was too weak for direct `fail`. Many real timeout behaviors are server-driven.
- Recommended approach: combine static timeout-signal detection with runtime observation of warnings, expiry modals, data-preservation behavior, and the `> 20 hours` preservation exception.
- Workflow diagram:
```text
Detect timeout signals
  -> observe runtime warning, expiry, and preservation behavior
  -> warning/preservation or >20h preservation = PASS
  -> actual data-loss timeout with no warning = FAIL
  -> timeout evidence incomplete = NEEDS_REVIEW
```
- Output policy: auto-`pass` when warning/preservation is clearly present; auto-`fail` when an actual data-loss timeout occurs without warning and without long preservation; otherwise `needs_review`.
- Edge cases covered: absolute vs idle timeout, save-draft behavior, background-tab throttling, kiosk workflows, server-side expiries invisible in JS, long-form applications.
- Confidence: `4/10`

## NEXT-INTERACT

### 2.1.3 - Keyboard (No Exception)
- Verdict: The original section mostly duplicated `2.1.1`. The real AAA delta is that path-dependent functionality also needs a keyboard-accessible way.
- Recommended approach: identify path-dependent and pointer-only widgets first, then verify keyboard equivalents for those components in addition to normal keyboard traversal checks.
- Workflow diagram:
```text
Inventory path-dependent and pointer-only widgets
  -> test keyboard equivalent for each critical function
  -> keyboard alternative exists for all = PASS
  -> path-dependent function lacks keyboard alternative = FAIL
  -> complex widget behavior unclear = NEEDS_REVIEW
```
- Output policy: auto-`fail` when a path-dependent widget or workflow has no keyboard alternative; auto-`pass` only in controlled interaction scopes; otherwise `needs_review`.
- Edge cases covered: signature pads, drawing canvases, maps, sortable/drag UIs, rich editors, games, widgets that already expose arrow-key or menu alternatives.
- Confidence: `4/10`

### 2.5.6 - Concurrent Input Mechanisms
- Verdict: Reasonable runtime target, but browser emulation still leaves coverage gaps.
- Recommended approach: interact with the same session via touch, keyboard, and mouse in sequence, and detect whether one modality disables or degrades another.
- Workflow diagram:
```text
Use touch, then keyboard, then mouse in same session
  -> check whether any modality disables another
  -> all modalities remain usable = PASS
  -> one modality locks out another = FAIL
  -> emulation/platform limits = NEEDS_REVIEW
```
- Output policy: auto-`fail` when the page clearly locks users into one modality on a platform that supports several; otherwise `needs_review`.
- Edge cases covered: hybrid laptop/tablet devices, touch-first menus that suppress keyboard access, hover-only affordances after touch, stylus input, responsive breakpoints that swap component implementations.
- Confidence: `4/10`

### 3.2.5 - Change on Request
- Verdict: The original section targeted the wrong problem. This SC is about context changes that happen because of input/focus/change events without explicit request, not passive auto-updates.
- Recommended approach: extend the existing `on-focus` and `on-input` style checks to watch `focus`, `change`, `input`, and selection events, then flag navigation, window changes, major context swaps, or auto-submit that occur without a submit/button request.
- Workflow diagram:
```text
Watch focus/input/change/selection events
  -> detect navigation or major context swap after each event
  -> explicit submit/request causes change = PASS
  -> context change without explicit request = FAIL
  -> ambiguous SPA/local updates = NEEDS_REVIEW
```
- Output policy: auto-`fail` when a form control change causes a context change without explicit request and no disable mechanism exists; auto-`pass` when context changes happen only after explicit request; otherwise `needs_review`.
- Edge cases covered: auto-submitting filters, language selectors, dependent field updates that are not context changes, SPA route swaps, modal openings, quantity controls that only update local state.
- Confidence: `6/10`

## P-OCR UPGRADE

### 1.4.9 - Images of Text (No Exception)
- Verdict: High-confidence extension of the existing OCR pipeline, but the original wording needed one correction: AAA still allows decorative/incidental text and essential presentation. It only removes the AA logotype/customizable escape.
- Recommended approach: reuse the current `1.4.5` image-of-text pipeline, remove the logo/customizable exemption, and keep explicit checks for decorative, incidental, and essential cases.
- Workflow diagram:
```text
Run OCR on informative images
  -> classify detected text as decorative, incidental, essential, or primary content
  -> decorative/incidental/essential = PASS
  -> primary text image with no AAA exception = FAIL
```
- Output policy: auto-`fail` when OCR finds text that is the primary content of an image and the presentation is not essential; auto-`pass` for decorative/incidental/essential cases.
- Edge cases covered: screenshots in documentation, branded wordmarks, scanned forms, product photos with incidental labels, receipts, signs appearing inside photographs.
- Confidence: `8/10`

## P-CRAWL UPGRADE

### 2.5.5 - Target Size (Enhanced)
- Verdict: Strong upgrade path, but the original spacing-exception note was wrong for AAA.
- Recommended approach: reuse the current `2.5.8` target-size crawler, raise the threshold to `44x44`, remove the offset-spacing exception, and add AAA exceptions for `Equivalent`, `Inline`, `User Agent Control`, and `Essential`.
- Workflow diagram:
```text
Crawl interactive targets
  -> measure rendered size
  -> apply AAA exceptions (Equivalent / Inline / UA Control / Essential)
  -> >=44x44 or valid exception = PASS
  -> otherwise = FAIL
```
- Output policy: auto-`fail` when a target is below `44x44` and no AAA exception applies; auto-`pass` otherwise.
- Edge cases covered: inline links and footnotes, help icons embedded in text, equivalent larger control on the same page, native checkbox/radio controls, truly essential tiny targets in specialized interfaces.
- Confidence: `8/10`

## Best Near-Term Bets

| SC | Why it should move first | Confidence |
| --- | --- | --- |
| `2.5.5` | Reuses the mature `2.5.8` crawler with a threshold and exception change | `8/10` |
| `1.4.9` | Reuses the existing OCR/image-of-text foundation with a narrower exception model | `8/10` |
| `3.3.7` | Extends an existing Node rule into a high-value dynamic flow check | `8/10` |
| `2.3.2` | Frame analysis is well-scoped and the AAA rule is simpler than `2.3.1` | `8/10` |
| `2.3.1` | Strong CV fit with high user-impact payoff | `7/10` |
| `2.3.3` | Natural extension of the rendered-layout Playwright scenarios | `7/10` |
| `3.2.3` | Multi-page diffing is practical and high-signal | `7/10` |
| `3.3.9` | Strong leverage from the existing `3.3.8` auth checker | `6/10` |
| `2.4.10` | Mostly structural and low-risk to prototype | `6/10` |
| `3.2.4` | Useful after `3.2.3`, but requires careful identity grouping | `5/10` |

## Defer or Keep Review-First

- `1.2.3`, `1.2.4`, `1.2.5`, `1.2.6`, `1.2.7`, `1.2.8`, `1.2.9`
- `1.3.6`, `3.1.3`, `3.1.5`
- `2.2.3`, `2.2.5`, `2.2.6`
- `2.1.3`, `2.5.6`
- `3.3.5`, `3.3.6`

These are still worth building supporting signals for, but they should be reported as `needs_review`-heavy features unless you control the content environment or accept lower-confidence findings.

## References Checked

- W3C Understanding SC `1.2.3`: <https://www.w3.org/WAI/WCAG22/Understanding/audio-description-or-media-alternative-prerecorded>
- W3C Understanding SC `1.4.8`: <https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation>
- W3C Understanding SC `2.3.1`: <https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html>
- W3C Understanding SC `2.5.5`: <https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced>
- W3C Understanding SC `3.2.5`: <https://www.w3.org/WAI/WCAG22/Understanding/change-on-request.html>
- W3C Understanding SC `3.3.7`: <https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html>
- W3C Understanding SC `3.3.9`: <https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-enhanced>
