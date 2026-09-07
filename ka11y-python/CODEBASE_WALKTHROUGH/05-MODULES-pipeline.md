# 4. Module-by-Module Breakdown — Group 3: Rendered-State Decision Pipeline (`accessibility/pipeline/`)

> **⚠ Correction, established while writing `07-MODULES-api.md`:** this
> entire subsystem is **fully implemented but currently orphaned** — nothing
> in the live request path calls it. `api/v1/combined/stages.py` imports
> `pipeline_stage._run_pipeline_stage`, wraps it in a same-named local
> function (`stages.py:86-126`) that records stage lifecycle around it, and
> that wrapper is **never invoked** anywhere. The actual orchestrator every
> `/api/v1/combined/*` and `/api/v1/pipeline/` request goes through
> (`_run_python_stages`) only runs `_stage_image_audit` and
> `_stage_media_audit_universal`; its own docstring says outright *"The
> pipeline stage (`_run_pipeline_stage`) has been removed — it is out of
> scope for this run configuration"* (`stages.py:724-725`). Verified via
> `grep -rn "_run_pipeline_stage" ka11y/` — the only references are the
> definition here, the dead wrapper, and that comment. **In the running
> service today, WCAG 1.1.1 / 1.4.3 / 1.4.5 / 1.4.6 / 1.4.11 coverage comes
> entirely from `accessibility/rules/non_text/alttext.py` +
> `contrast_analyser.py`** (`06-MODULES-rules.md`), a separate,
> independently-implemented codepath that happens to cover the same five
> criteria. See `07-MODULES-api.md` (D) for the full trace and
> `13-EXTENSIBILITY.md` for what re-wiring this would take.

Below is documented as designed/written, since that's what the code says and
it's a coherent, testable subsystem on its own — just keep the box above in
mind throughout.

A generic, config-driven decision framework: extract semantic/visual/
interaction evidence about a DOM element once, route it to the WCAG success
criteria it's applicable to, evaluate each against a per-criterion "policy"
class, and format the result into the legacy finding schema the rest of the
report expects. Designed for five criteria (1.1.1, 1.4.3, 1.4.5, 1.4.6,
1.4.11) — see `01-OVERVIEW-AND-ENTRYPOINT.md`'s correction note for the
larger set of criteria (2.5.3, 2.2.2, 2.5.8, 1.4.12, 1.4.4, 1.4.10, 1.3.4,
1.4.13, 2.4.11, 2.4.12) whose *routing* still exists elsewhere but whose
*policies* were removed from this codebase.

---

## `ka11y/accessibility/pipeline/models.py` (121 lines)

**Purpose**: the shared Pydantic vocabulary every other file in this group
imports — the pipeline's "on-the-wire" data contract.

**Imports**: `enum.Enum`; `typing.Any/Dict/List/Optional`;
`pydantic.BaseModel/Field`. No internal imports (this is the pipeline's own
foundation layer).

**Enums**:
- `SectionType(str, Enum)` (lines 6-18): `HEADER, FOOTER, NAVIGATION,
  MAIN_CONTENT, FORM_REGION, DATA_TABLE, ARTICLE_CARD, MODAL_DIALOG, HERO,
  MEDIA_CARD, GENERIC, UNKNOWN` — the macro page-region an element lives in.
- `VerdictStatus(str, Enum)` (lines 21-25): `PASS, FAIL, NEEDS_REVIEW,
  NOT_APPLICABLE`.
- `AccessibleNameSource(str, Enum)` (lines 28-35): `ARIA_LABEL,
  ARIA_LABELLEDBY, NATIVE_LABEL, ALT_ATTRIBUTE, TEXT_CONTENT,
  TITLE_ATTRIBUTE, NONE` — which W3C accname-1.2 source produced the name.

**Models**:
- `BoundingBox(BaseModel)` (lines 38-46): `x, y, width, height: float`;
  `area` computed property (`width * height`).
- `AccessibleName(BaseModel)` (lines 49-53): `name`, `source`, `is_visible`.
- `VisualContext(BaseModel)` (lines 55-68): `is_visible`, `opacity`,
  `bounding_box`, `computed_styles: Dict[str,str]`, `ocr_text`,
  `cv_classification` (e.g. `"logo"`/`"decorative"`/`"complex"`),
  `background_type`, `resolved_background_color`, `has_bg_image`,
  `rendered_contrast`, `is_obscured_by_floating_element`,
  `visible_label_text`, `src`.
- `SemanticContext(BaseModel)` (lines 71-87): `tag_name`, `role`,
  `section_type`, `ancestor_tags`/`ancestor_roles` (full ancestry),
  `parent_tags`/`parent_roles` (immediate ancestors only), `is_required`,
  `is_disabled`, `controlled_by`, `controls_elements`, `owns_elements`,
  `described_by_text`, `is_in_data_table`, `is_in_labeled_control`,
  `is_video_context`.
- `InteractionContext(BaseModel)` (lines 90-98): `is_focusable`,
  `tab_index`, `effective_clickable_bbox`, `adjacent_spacing_px`,
  `has_focus_ring`, `focus_ring_thickness_px`, `focus_ring_contrast`,
  `clickable_area_px`.
- `ElementContext(BaseModel)` (lines 101-108): the unit every policy
  evaluates — `element_id`, `xpath`, `html_snippet`, `semantics: SemanticContext`,
  `visual: VisualContext`, `interaction: InteractionContext`,
  `accessible_name: Optional[AccessibleName]`.
- `RuleVerdict(BaseModel)` (lines 111-120): `rule_id`, `wcag_sc`, `status:
  VerdictStatus`, `confidence: float`, `reason_code`, `human_reason`,
  `reason_params: Dict[str,Any]`, `evidence: Dict[str,Any]`,
  `element: ElementContext` (the verdict carries its whole source element,
  so downstream formatting never needs to re-look-up the element by ID).

**Side effects**: none. **Used elsewhere**: every other pipeline file.

---

## `ka11y/accessibility/pipeline/config/thresholds.py` (26 lines)

**Purpose**: hardcoded WCAG numeric thresholds, isolated from policy logic
so they're easy to audit/adjust in one place.

**Constants**: contrast (`CONTRAST_NORMAL_AA=4.5`, `CONTRAST_LARGE_AA=3.0`,
`CONTRAST_NORMAL_AAA=7.0`, `CONTRAST_LARGE_AAA=4.5`, `LARGE_TEXT_PT=18.0`,
`LARGE_TEXT_BOLD_PT=14.0` — WCAG 1.4.3/1.4.6); target size
(`MIN_TARGET_SIZE_PX=24.0`, `MIN_TARGET_SPACING_PX=24.0` — WCAG 2.5.8, **not
currently consumed by any policy in this codebase** since the target-size
auditor was removed — see the correction note); alt text
(`MIN_ICON_ALT_LENGTH=4`, `GENERIC_ALT_STRINGS = {"image", "picture",
"photo", "icon", "graphic", "spacer", "logo"}` — WCAG 1.1.1); focus
appearance (`MIN_FOCUS_THICKNESS_PX=1.0`, `MIN_FOCUS_CONTRAST=3.0` — WCAG
2.4.13, also currently unconsumed); exemption sets
(`EXEMPT_ROLES_FROM_TARGET_SIZE`, `EXEMPT_FROM_CONTRAST = {"logo",
"decorative", "inactive_ui_component"}`).

**Side effects**: none. **Used elsewhere**: `policy_1_1_1.py` (alt
thresholds), `policy_1_4_6.py` (AAA contrast thresholds), `contrast_engine.py`
(AA thresholds).

---

## `ka11y/accessibility/pipeline/analyzers/section_analyzer.py` (56 lines)

**Purpose**: classify an element's macro page-region from its DOM ancestry.

**Imports**: `typing.List`; `..models.SectionType`.

**Class `SectionAnalyzer`**:
- `_LANDMARK_MAP` (lines 12-27): maps native tags (`header`, `footer`,
  `nav`, `main`, `form`, `table`, `article`) and ARIA roles (`banner`,
  `contentinfo`, `navigation`, `search`, `grid`, `dialog`, `alertdialog`)
  to `SectionType` values (many-to-one — e.g. both `header` and `banner`
  map to `SectionType.HEADER`).
- `analyze(cls, ancestor_tags, ancestor_roles) -> SectionType` (classmethod,
  lines 29-55): walks the ancestor lists in parallel (closest ancestor
  first) via `itertools.zip_longest(fillvalue="")` — deliberately not plain
  `zip`, because a length mismatch between the two lists (an ancestor with
  no `role` attribute) would otherwise silently truncate the walk early and
  miss a landmark further up (inline comment, lines 38-40). At each level,
  checks `role` first (more specific than a bare tag name), falling back to
  `tag`; returns the **first** match found (closest ancestor wins). Returns
  `SectionType.UNKNOWN` if nothing in `_LANDMARK_MAP` is found in the whole
  ancestry.

**Side effects**: none. **Used elsewhere**:
`extractors/element_context_extractor.py`'s `extract_contexts`.

---

## `ka11y/accessibility/pipeline/extractors/element_context_extractor.py` (370 lines)

**Purpose**: the primary in-browser data-gathering step — injects one large
JS payload per frame that walks the live DOM (including shadow roots),
computes bounding boxes/computed styles/ARIA attributes/ancestry for every
element of interest, then parses the results into typed `ElementContext`
Pydantic models on the Python side, resolving the W3C accname-1.2 accessible-
name precedence chain along the way.

**Imports**: `json` (unused directly but imported — likely vestigial),
`typing.*`; `playwright.async_api.Page`; `..models.*` (the whole model set);
`..analyzers.section_analyzer.SectionAnalyzer`.

**Module-level constants**: `_FORM_CONTROL_TAGS = {"input", "select",
"textarea"}`, `_ALT_BEARING_TAGS = {"img", "area"}` (lines 17-18).

**Function `_resolve_accessible_name(data: Dict) -> Optional[AccessibleName]`**
(lines 21-91) — implements the W3C accname-1.2 precedence order, documented
in its own docstring and re-confirmed in an inline comment at the call site
(lines 345-352):
1. `aria-labelledby` (if the raw JS resolved referenced text) — highest
   priority, marked `is_visible=True` (the referenced text is itself
   visible content).
2. `aria-label` — `is_visible=False` (an attribute value, not rendered text).
3. Native `<label for>`/wrapping-`<label>` association — **only** for
   `_FORM_CONTROL_TAGS` (`input`/`select`/`textarea`).
4. `alt` attribute — only meaningful for `img`/`area`, or `input` when its
   `type` (parsed from the HTML snippet via a small regex, lines 34-37) is
   specifically `"image"`.
5. Visible text content (button/link text).
6. `title` attribute — last resort.
Returns `None` if nothing matched (genuinely nameless). Empty-string
sources (e.g. `alt=""`) are preserved as a *present-but-empty* name rather
than treated as absent, so downstream policies can tell "decorative
(intentionally empty)" apart from "missing" (docstring lines 26-29).

**Class `ElementContextExtractor`**:
- `_UNIFIED_EXTRACTION_JS` (lines 100-281) — the injected extraction
  script, structured as:
  - `getAllElements(root)`: recursively collects every element under
    `document.body`, descending into `shadowRoot`s (shadow-DOM aware).
  - Filters to elements of interest: `a/button/input/select/textarea/img/svg`
    tags, or anything with a `role`/`tabindex` attribute, or a
    background-image element that also carries `aria-label`.
  - `getEffectiveBBox(el)`: for a radio/checkbox `<input>`, uses its
    associated `<label>`'s bounding box instead of the tiny native control's
    own box (the clickable target is really the label).
  - `getAncestry(el)`: walks `parentElement` (falling back through shadow
    hosts via `getRootNode().host`) collecting tag names and `role`
    attributes up to `document.documentElement`.
  - `getVisibleLabelText(el)`: for form controls, resolves the associated
    `<label>`'s text.
  - `isVisuallyHidden(el, style, bbox)`: `display:none`,
    `visibility:hidden`, `opacity:0`, zero-size bbox, or the classic
    `clip: rect(0px,0px,0px,0px)` screen-reader-only hiding trick.
  - `getResolvedBackground(el)`: walks up the ancestor chain looking for the
    first ancestor with a non-transparent `background-color`, defaulting to
    white if none found (parses the alpha channel out of the `rgba(...)`
    computed style string).
  - Main loop: assigns a synthetic `id` (`ka11y-auto-{index}`) to any
    element lacking one (needed so the later `SemanticRelationshipEngine`
    pass can re-find the same element by ID); skips visually-hidden
    elements; resolves `aria-labelledby` by concatenating the referenced
    elements' visible text (with a shadow-DOM `getRootNode().getElementById`
    fallback); resolves `src` (special-cased for `<video>` → its `poster`
    attribute, and `<svg>` → always `null`); truncates the HTML snippet
    (400 chars generally, 250 for SVG, to avoid enormous inline SVG markup
    bloating the payload); collects `aria-controls`/`aria-owns` as ID lists.
  - **Adjacent-spacing computation** (lines 264-278): for every focusable
    element pair, computes the minimum gap (`dx`/`dy` via the standard
    "distance between two axis-aligned rectangles" formula, then
    `dist = max(dx, dy)`) and records each element's `adjacent_spacing_px`
    as its minimum distance to any other focusable element — computed
    natively in JS "for 2.5.8" per the inline comment (though, per the
    correction note above, no policy currently consumes this field — the
    2.5.8 target-size policy was removed).
- `extract_contexts(cls, page) -> List[ElementContext]` (classmethod, lines
  283-369, async) — the public entry point:
  1. Iterates every `page.frames`, skipping empty `about:blank` frames.
  2. Runs `_UNIFIED_EXTRACTION_JS` in each frame via `frame.evaluate`.
  3. For each raw record: computes `section_type` via `SectionAnalyzer.analyze`;
     builds `SemanticContext` (lowercasing tag/role lists, splitting
     `parent_tags`/`parent_roles` as just the first two ancestry entries);
     builds `VisualContext` (parsing `opacity` defensively — strips spaces,
     defaults to `1.0`); builds `InteractionContext`; resolves the
     accessible name via `_resolve_accessible_name`; assembles the final
     `ElementContext`.
  4. **Any exception per-frame is silently swallowed** (lines 365-367,
     comment: "cross-origin frame evaluation errors or closed contexts") —
     one broken frame doesn't abort extraction for the rest of the page.

**Side effects**: runs JS in every frame of the page (read-only DOM
inspection, no mutation).

**Used elsewhere**: `crawler/universal_page.py`'s
`_extract_pipeline_contexts` (the per-BFS-page call site) and
`pipeline_stage.py`'s `_extract_contexts_for_url` (the single-URL fallback).

---

## `ka11y/accessibility/pipeline/extractors/semantic_relationship_engine.py` (136 lines)

**Purpose**: a second, batched JS pass that resolves *relationships between*
elements (rather than an element's own attributes) — `aria-describedby`
text, fieldset/legend group names, native label text, "is this inside an
already-labeled control," "is this inside a data table," "is this a video
player wrapper."

**Imports**: `typing.*`; `playwright.async_api.Page`;
`..models.ElementContext/SemanticContext`.

**Class `SemanticRelationshipEngine`**:
- `_RELATIONSHIP_JS` (lines 12-78) — takes an **array of element IDs** and
  returns `{id: {relations}}` for every ID that exists in that frame's
  document, in **one round trip** (the docstring/comment explicitly notes
  this replaced a prior N+1-IPC design that called `frame.evaluate()` once
  per element). Per element: resolves `aria-describedby` → concatenated
  referenced text; walks up for the nearest `<fieldset>` ancestor and reads
  its `<legend>` text as a `group_name`; finds a native `<label>`
  association; determines `is_in_labeled_control` by checking whether the
  element sits inside a `button`/`a`/`[role=button|link|menuitem]` ancestor
  that itself has an aria-label, non-empty text, or a `title`; determines
  `is_in_data_table` via `closest('table:not([role="presentation"])')`;
  determines `is_video_context` via a `closest` selector matching `video`,
  class names containing "video"/"player" (case-insensitive), or
  `[data-video-id]`.
- `enrich_semantics(cls, page, contexts) -> None` (classmethod, lines
  80-135, async) — **mutates `contexts` in place**:
  1. Indexes `contexts` by `element_id` into `by_id`.
  2. For each frame, runs `_RELATIONSHIP_JS` once with **all** element IDs
     at once (a frame only returns entries for IDs actually present in its
     own document — cross-frame IDs simply don't appear in that frame's
     result map).
  3. For each returned `(element_id, relations)`: writes `described_by_text`,
     `is_in_data_table`, `is_in_labeled_control`, `is_video_context` onto
     the matching context's `semantics`. If a fieldset `group_name` was
     found and the context has an accessible name, **prepends it**:
     `context.accessible_name.name = f"{group_name}: {name}"` — so a radio
     button named "Small" inside a fieldset legend "Size" becomes "Size:
     Small" for downstream contrast/text checks (though notably this
     mutates the *displayed* name text, which is a slightly unusual side
     effect for what's framed as a "relationship enrichment" pass).
  4. Any per-frame exception is silently swallowed, same pattern as the
     context extractor.

**Side effects**: mutates the `ElementContext` list passed in; runs
read-only JS per frame.

**Used elsewhere**: same two call sites as `element_context_extractor.py`
(`universal_page.py`, `pipeline_stage.py`), always called immediately after
`extract_contexts`.

---

## `ka11y/accessibility/pipeline/router/rule_target_router.py` (56 lines)

**Purpose**: decides which WCAG success criteria are even applicable to a
given `ElementContext`, so the `DecisionEngine` doesn't run every policy
against every element.

**Class `RuleTargetRouter`**:
- `get_applicable_rules(element: ElementContext) -> List[str]` (staticmethod,
  lines 8-55):
  1. **Images/visual media** (`img`/`svg` tag, or `role="img"`) → routes to
     `1.1.1` and `1.4.5`.
  2. **Interactive controls** (`button`/`a`/`input`/`select`/`textarea` tags,
     or `role` in `button/link/checkbox/radio/menuitem/tab/textbox`, or
     `is_focusable`) → routes to `1.4.11`.
  3. **Text elements** — routes to `1.4.3` and `1.4.6` only if the element
     has *rendered* text, defined as: a **visible** accessible name (an
     `aria-label` is explicitly excluded here since `is_visible=False` for
     that source — comment lines 32-36 explains why: contrast requires
     actual painted pixels, and an `aria-label` describes the element
     without rendering anything), or OCR-detected text, or a visible label.
  4. **Order-preserving dedup** (lines 45-55) — explicitly *not*
     `list(set(...))`, because Python's hash randomization made that
     ordering non-deterministic across runs, breaking test snapshots and
     making the `applicable_rules` order unstable for any downstream
     consumer that iterates rule-by-rule; replaced with a manual
     seen-set + list-append loop that preserves first-occurrence order.

**Side effects**: none. **Used elsewhere**: `decisions/engine.py`'s
`DecisionEngine.evaluate_element`.

---

## `ka11y/accessibility/pipeline/decisions/engine.py` (57 lines)

**Purpose**: the orchestrator tying router + policies together.

**Imports**: `logging`; `typing.List/Dict`; `..models.ElementContext/
RuleVerdict/VerdictStatus`; `..router.rule_target_router.RuleTargetRouter`;
`.policies.base_policy.WCAGPolicy`.

**Class `PolicyError(Exception)`** (lines 10-13): a policy raises this to
signal "evaluation couldn't complete, but this is an expected/handled
uncertainty" — the engine catches specifically this type and downgrades to a
`NEEDS_REVIEW` verdict. Any *other* exception type is explicitly **not**
caught here (comment lines 51-52: "silent NEEDS_REVIEW masks real bugs in
policies, so the caller should see the fault") — it propagates up and (per
`pipeline_stage.py`'s outer `try/except`) fails the whole pipeline run for
that request rather than silently degrading.

**Class `DecisionEngine`**:
- `__init__(self, policies: Dict[str, WCAGPolicy])` (lines 22-23): stores
  the `{wcag_sc: policy_instance}` map (built by `pipeline_stage.py`'s
  `_build_policies`).
- `evaluate_element(self, element) -> List[RuleVerdict]` (lines 25-56):
  1. Gets `applicable_rules` from `RuleTargetRouter`.
  2. For each applicable SC: looks up the registered policy (logs a warning
     and skips if none is registered — this is exactly the situation for
     the SCs whose policies were removed, e.g. if `RuleTargetRouter` were
     ever extended to route `2.5.8` again without a matching policy being
     re-added).
  3. Calls `policy.evaluate(element)`; a `PolicyError` becomes a synthetic
     `NEEDS_REVIEW` verdict (`reason_code="policy_uncertain"`, confidence
     0.3); any other exception propagates unhandled.
  4. Verdicts with status `NOT_APPLICABLE` are **dropped** — the caller only
     ever sees PASS/FAIL/NEEDS_REVIEW verdicts, never NOT_APPLICABLE ones.

**Side effects**: none beyond logging. **Used elsewhere**:
`pipeline_stage.py`'s `_evaluate_pages`.

---

## `ka11y/accessibility/pipeline/decisions/policies/base_policy.py` (88 lines)

**Purpose**: the abstract base every policy extends, providing four
verdict-construction helper methods so individual policies don't repeat
`RuleVerdict(...)` boilerplate.

**Class `WCAGPolicy(ABC)`**:
- Class attributes `rule_id: str`, `wcag_sc: str` (declared but unset —
  every concrete policy must set these).
- `evaluate(self, element) -> RuleVerdict` (`@abstractmethod`, lines 10-13).
- `_pass` / `_fail` / `_needs_review` / `_not_applicable` (lines 15-87):
  each builds a `RuleVerdict` with the corresponding `VerdictStatus`, a
  fixed default confidence (`_pass`→1.0, `_fail`→0.9 default/overridable,
  `_needs_review`→0.5 default/overridable, `_not_applicable`→1.0), and the
  given `code`/`msg`/`evidence`/`reason_params`.

**Side effects**: none. **Used elsewhere**: every concrete policy subclass.

---

## `ka11y/accessibility/pipeline/decisions/policies/policy_1_1_1.py` (90 lines) — WCAG 1.1.1 Non-text Content

**Class `Policy111(WCAGPolicy)`**: `rule_id="python_1_1_1_alt"`, `wcag_sc="1.1.1"`.
- Module-level `_DESCRIPTIVE_ALT_RE = re.compile(r"[a-z]{2}|[^\x00-\x7F]")`
  (line 9, hoisted to avoid a per-element regex compile) — matches an alt
  text containing either two consecutive lowercase letters or any non-ASCII
  character (so short CJK/emoji alt text isn't wrongly flagged "terse" by
  its character count alone).
- `evaluate(self, element) -> RuleVerdict` (lines 16-89), in order:
  1. **Decorative exemption**: if CV-classified `"decorative"` or
     `role in ("presentation", "none")` — passes if the accessible name is
     empty/absent, fails ("should have empty alt or no accessible name") if
     it unexpectedly has one.
  2. **Functional redundancy**: if `semantics.is_in_labeled_control` (the
     image sits inside a link/button that already has its own name) —
     passes immediately; a specific alt isn't required (this is the "image
     inside a labeled control" false-positive fix documented at the model
     layer too).
  3. **Missing name**: fails if there's no accessible name at all.
  4. **Generic-string filter**: fails if the lowercased name contains any of
     `GENERIC_ALT_STRINGS` (`"image"`, `"icon"`, `"logo"`, etc. as
     substrings — so alt text like `"stock photo"` or `"company logo"`
     still trips this).
  5. **Logo logic**: if CV-classified `"logo"` — passes if the name mentions
     `logo`/`brand`/`home` (English) or `ロゴ`/`ブランド`/`ホーム` (Japanese),
     else `NEEDS_REVIEW` ("ensure alt text mentions the company name and
     'logo'").
  6. **Icon logic**: if CV-classified `"icon"` and the name is shorter than
     `MIN_ICON_ALT_LENGTH` (4) or fails `_DESCRIPTIVE_ALT_RE` — fails as
     "too short or non-descriptive."
  7. Otherwise passes as `"informative_valid"`.

---

## `ka11y/accessibility/pipeline/decisions/policies/policy_1_4_3.py` (86 lines) — WCAG 1.4.3 Contrast (Minimum)

**Class `Policy143(WCAGPolicy)`**: `rule_id="python_1_4_3_contrast"`, `wcag_sc="1.4.3"`.
- `_is_large_text(self, styles: dict) -> bool` (lines 11-28): parses
  `font-size` (regex-extracts the numeric px value, defaulting to
  `"16px"`) and `font-weight` (bold if `bold`/`bolder`/`700`/`800`/`900`);
  WCAG large text = ≥24px, or ≥18.66px **and** bold.
- `evaluate` (lines 30-85):
  1. `NOT_APPLICABLE` if there's no accessible name, OCR text, or visible
     label at all (nothing to contrast-check).
  2. **Exempt**: logo/decorative CV classification, or a disabled element —
     passes automatically.
  3. Reads `color` (foreground) and `resolved_background_color`
     (background) from the computed styles.
  4. `NEEDS_REVIEW` if the background is transparent (`rgba(...,0)`) — "cannot
     compute text contrast statically."
  5. Otherwise calls `ContrastEngine.evaluate_1_4_3(fg, bg, is_large)` and
     passes/fails based on `result["passes"]`, attaching the full evidence
     dict (`foreground`, `background`, `contrast_ratio`,
     `required_threshold`, `is_large_text`).

---

## `ka11y/accessibility/pipeline/decisions/policies/policy_1_4_5.py` (64 lines) — WCAG 1.4.5 Images of Text

**Class `Policy145(WCAGPolicy)`**: `rule_id="python_1_4_5_images_of_text"`, `wcag_sc="1.4.5"`.
- Module-level `_normalise(s)` (lines 11-12): lowercases and strips
  everything but alphanumerics, for a loose OCR-text-vs-alt-text comparison.
- `evaluate` (lines 19-63):
  1. `NOT_APPLICABLE` for exempt classifications (`logo`, `decorative`,
     `complex`, `chart`) or a video-context element (thumbnails/posters are
     "essential presentations").
  2. If OCR found meaningful text (`len(ocr_text.strip()) > 3`): if the
     normalized OCR text exactly equals the normalized accessible name,
     passes as `"text_matches_alt"` (a deliberate text-alternative,
     technically allowed) — else `NEEDS_REVIEW` with a 30-char OCR snippet
     and confidence 0.8, suggesting the text could likely be replaced with
     real CSS-styled text.
  3. Otherwise passes as `"no_text_detected"`.

---

## `ka11y/accessibility/pipeline/decisions/policies/policy_1_4_6.py` (42 lines) — WCAG 1.4.6 Contrast (Enhanced)

**Class `Policy146(Policy143)`** — **subclasses `Policy143` directly**
(inheritance, not composition) to reuse its entire evaluation logic and only
override the pass/fail threshold: `rule_id="python_1_4_6_contrast_enhanced"`,
`wcag_sc="1.4.6"`.
- `evaluate` (lines 11-41): calls `super().evaluate(element)` first; if the
  result is `NOT_APPLICABLE`/`NEEDS_REVIEW` (or carries no evidence), returns
  it unchanged (those outcomes don't depend on the threshold). Otherwise,
  re-checks the **already-computed** `contrast_ratio` from the parent's
  evidence against the AAA threshold (`CONTRAST_LARGE_AAA`/
  `CONTRAST_NORMAL_AAA` — imported from config, not hardcoded, per the
  inline comment) — so the actual contrast math (`ContrastEngine`) only runs
  once even though two policies (AA and AAA) evaluate the same element.

---

## `ka11y/accessibility/pipeline/decisions/policies/policy_1_4_11.py` (51 lines) — WCAG 1.4.11 Non-text Contrast

**Class `Policy1411(WCAGPolicy)`**: `rule_id="python_1_4_11_non_text_contrast"`,
`wcag_sc="1.4.11"`, `THRESHOLD = 3.0` (declared but not actually used
in the method body below — the policy never reaches a stage where it
computes and compares a ratio against it).
- `evaluate` (lines 13-50):
  1. `NOT_APPLICABLE` unless the element is a UI component (focusable, or
     `input`/`button`/`select`/`textarea`) or CV-classified `"icon"`.
  2. Passes automatically if `is_disabled` (inactive components exempt).
  3. Reads `background-color` and `border-top-color` from computed styles.
  4. `NEEDS_REVIEW` (`"no_explicit_boundary"`) if **both** are fully
     transparent — the component relies on surrounding page context this
     policy can't see.
  5. **Otherwise, always returns `NEEDS_REVIEW`** (`"boundary_contrast_review"`,
     "Visual boundary contrast requires visual context/screenshot
     resolution") — this policy's docstring/inline comment (line 34)
     candidly notes its boundary extraction is "naive" and a "production
     engine needs full visual overlay extraction"; **it never actually
     computes a pass/fail contrast ratio itself** in this codebase — it's
     effectively a stub that always defers to manual review once it
     determines the element is in-scope and has *some* explicit
     boundary color. (Real 1.4.11 pass/fail determination for images
     happens instead in `accessibility/rules/non_text/contrast_analyser.py`
     — see `06-MODULES-rules.md` — which has actual screenshot-based boundary
     measurement; this pipeline policy appears to be an earlier/parallel,
     less-complete implementation for non-image UI components.)

---

## `ka11y/accessibility/pipeline/runners/contrast_engine.py` (155 lines)

**Purpose**: pure WCAG 2.x contrast-ratio math — color parsing, alpha
compositing, relative luminance, ratio calculation. No DOM/browser
dependency; this is the shared, tested math kernel other policies call into.

**Imports**: `re`; `typing.Tuple/Dict/Any`; `..config.thresholds.CONTRAST_NORMAL_AA/
CONTRAST_LARGE_AA`.

**Module-level**: `RGBA`/`RGB` type aliases; `_NUMBER_RE =
re.compile(r"-?\d+(?:\.\d+)?")` (line 15) — a documented bug fix: the
previous parser used `r"\d+"`, which split an alpha value like `"0.5"` in
`rgba(255,0,0,0.5)` into two separate integer tokens `["0","5"]`,
corrupting the parsed color to `(0, 5, *, ...)` and silently producing a
wrong contrast ratio; the new regex matches a full (possibly negative,
possibly decimal) number as one token.

**Class `ContrastEngine`**:
- `parse_color(color_str) -> RGBA` (staticmethod, lines 27-65): handles hex
  (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa` — expanding 3/4-digit shorthand by
  doubling each hex digit) and `rgb()`/`rgba()` functional notation (pulls
  every numeric token in order via `_NUMBER_RE`; a 4th token is alpha, 3 or
  fewer means fully opaque). Unparseable input returns opaque black
  `(0,0,0,1.0)` (documented as a safe, well-defined default — callers
  needing to distinguish "missing" from "actually black" must check the
  input themselves first).
- `composite_over(fg, bg) -> RGB` (staticmethod, lines 67-83): Porter-Duff
  "source over destination" alpha compositing in **gamma-encoded sRGB space**
  (not linear light) — the docstring explains this matches how browsers
  actually paint pixels, which is what WCAG 2.x contrast is measured
  against. Short-circuits for `fa >= 1.0` (fully opaque, returns fg as-is)
  and `fa <= 0.0` (fully transparent, returns bg as-is).
- `parse_rgb(cls, color_str) -> RGB` (classmethod, lines 85-89): "back-compat
  shim" dropping the alpha channel from `parse_color`.
- `relative_luminance(r, g, b) -> float` (staticmethod, lines 91-103): the
  standard WCAG 2.1 formula — each channel is sRGB-decoded (`c/255`, then
  either linear `/12.92` below the `0.03928` knee or the gamma curve
  `((c+0.055)/1.055)**2.4` above it), combined as `0.2126*R + 0.7152*G +
  0.0722*B`.
- `calculate_ratio(cls, fg_color, bg_color) -> float` (classmethod, lines
  105-131): parses both colors; if the background itself has alpha < 1,
  composites it over an assumed opaque white first ("the conservative
  default browsers use when no document-level background can be resolved,"
  docstring lines 110-112); composites the foreground over that resolved
  solid background; computes both luminances; returns
  `round((bright+0.05)/(dark+0.05), 2)` — the standard WCAG contrast-ratio
  formula, rounded to 2 decimal places.
- `evaluate_1_4_3(cls, fg_color, bg_color, is_large_text) -> Dict` (classmethod,
  lines 133-146): wraps `calculate_ratio`, selects the AA threshold
  (`CONTRAST_LARGE_AA` vs `CONTRAST_NORMAL_AA`), returns
  `{ratio, threshold, is_large_text, passes}`.
- Module function `_clamp_byte(n) -> int` (lines 149-154): clamps to
  `[0, 255]` — used throughout `parse_color`/`composite_over` to keep
  computed channel values in valid byte range after rounding.

**Side effects**: none — pure math.

**Used elsewhere**: `policy_1_4_3.py`, `policy_1_4_6.py` (both via
`evaluate_1_4_3`/direct ratio reuse).

---

## `ka11y/accessibility/pipeline/formatters/evidence_formatter.py` (56 lines)

**Purpose**: converts the pipeline's typed `RuleVerdict` objects into the
"legacy" plain-dict finding schema the rest of the report/UI layer expects
(the same shape produced by the Node engine and the other Python rule
auditors) — the seam where this newer, typed subsystem rejoins the older,
dict-based reporting pipeline.

**Imports**: `typing.Dict/Any/List`; `..models.RuleVerdict/VerdictStatus`;
`ka11y.i18n.loader.render_reason` (internal — pulls in the i18n subsystem,
documented in `09-MODULES-text-classifier-i18n.md`).

**Class `EvidenceFormatter`**:
- `to_legacy_findings(verdicts: List[RuleVerdict], lang="en") -> List[Dict]`
  (staticmethod, lines 7-55):
  1. Maps `VerdictStatus` → the lowercase string status
     (`pass`/`fail`/`needs_review`/`not_applicable`) the rest of the system
     uses.
  2. **Localizes** the reason text via `render_reason(wcag_sc, reason_code,
     lang=lang, fallback=human_reason, params=reason_params)` — so the
     policy's English `human_reason` string is only a fallback; the actual
     displayed text comes from the i18n YAML bundle keyed by
     `(wcag_sc, reason_code)`, parameterized with `reason_params`.
  3. Builds the legacy dict: `source: "python"`, `rule_id`, `wcag_sc`,
     `status`, `reason` (the localized text), `confidence_score` (rounded to
     2dp), a nested `element` dict (`html`, `element_id`, `tag`, and
     `image_src` if `visual.src` is set), and a `pipeline_meta` dict
     (`reason_code`, `section` (the raw `SectionType` enum value), `evidence`)
     carrying the richer typed data for debugging without polluting the
     primary finding shape.

**Side effects**: none beyond the i18n lookup (which itself reads cached
YAML — see `09-MODULES-text-classifier-i18n.md`).

**Used elsewhere**: `pipeline_stage.py`'s `_evaluate_pages` — the last step
before pipeline findings are merged into the combined report.

---

## `ka11y/accessibility/pipeline/pipeline_stage.py` (148 lines)

**Purpose**: the pipeline's own entry point / composition function — wires
extractors + router + engine + policies + formatter together into one
callable, and is what `api/v1/combined/stages.py` and `api/v1/pipeline.py`
actually call.

**Imports**: `typing.*`; `ka11y.crawler.browser_pool.leased_context`;
relative imports of every other pipeline submodule documented above;
`ka11y.config.logger.setup_logger`.

**Functions**:
- `_build_policies(*, run_image_audit, run_contrast_audit) -> Dict[str, Any]`
  (lines 20-38): conditionally registers policies — `1.1.1`/`1.4.5` only if
  `run_image_audit`; `1.4.3`/`1.4.6`/`1.4.11` only if `run_contrast_audit`.
  So a caller that only wants contrast checking (or only image checking) can
  skip building/running the other policies at all.
- `_evaluate_pages(pages, policies, lang) -> List[Dict]` (lines 41-70):
  the **multi-page fix** described in its own docstring — previously every
  verdict was stamped with the single entry URL regardless of which BFS
  child page actually produced it, so deep pages' pipeline findings were
  effectively lost (attributed to the wrong page in the UI). Now iterates
  `(page_url, contexts)` pairs, running one shared `DecisionEngine` instance
  across all of them but closing over `page_url` per iteration so each
  `EvidenceFormatter.to_legacy_findings(...)` result gets
  `element["page_url"] = page_url` stamped correctly before being collected.
- `_extract_contexts_for_url(url) -> List[ElementContext]` (lines 73-86,
  async) — the **single-URL fallback**, used when no universal snapshot was
  built (e.g. an image-only audit at `max_depth=0`, per the docstring):
  leases its own pooled browser context, navigates, waits 2s, runs
  `ElementContextExtractor.extract_contexts` then
  `SemanticRelationshipEngine.enrich_semantics` directly — i.e. it
  re-implements a minimal version of what `universal_page.py` does for a
  full crawl, just for the one root URL.
- `_run_pipeline_stage(url, job_id, run_image_audit, run_contrast_audit=True,
  lang="en", snapshot=None) -> List[Dict]` (lines 89-147, async) — the top-level
  entry point:
  1. Builds the active `policies` dict; returns `[]` immediately if empty
     (both audit flags off).
  2. **Multi-page path**: if `snapshot.pipeline_pages` is present and
     non-empty, builds `pages: List[(url, contexts)]` from it directly — no
     additional browser navigation needed, since `universal_page.py` already
     populated this during the BFS crawl.
  3. **Single-page fallback**: otherwise calls `_extract_contexts_for_url(url)`
     and wraps it as a one-entry `pages` list.
  4. Calls `_evaluate_pages(pages, policies, lang)` and returns the result.
  5. **The entire body is wrapped in `try/except Exception`** (lines
     111-147) — any failure anywhere in the pipeline logs
     `logger.exception(...)` and returns `[]` rather than propagating, so a
     pipeline bug degrades to "no pipeline findings" for that run rather
     than failing the whole combined audit.

**Side effects**: (single-URL fallback only) opens a pooled browser context
and navigates; otherwise none — the multi-page path is pure CPU work over
already-collected data.

**Used elsewhere**: `api/v1/combined/stages.py` (the multi-page path, via a
`snapshot` built by `universal_page.py`) and `api/v1/pipeline.py` (likely
the single-URL fallback path for its narrower endpoint — see
`07-MODULES-api.md`).
