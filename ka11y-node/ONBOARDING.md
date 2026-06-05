# ka11y-node — Developer Onboarding

> **Audience:** an experienced Node.js developer who is **new to web accessibility / WCAG**.
> This document is the single starting point. It explains (1) the accessibility
> concepts you need, (2) what the Node service does and how it fits the wider
> product, (3) exactly which WCAG rules we cover vs. delegate vs. can't automate,
> and (4) a complete, copy‑pasteable tutorial for adding a new rule end‑to‑end.
>
> Deeper references live in `docs/` (`RULE_ANALYSIS.md`, `DEVELOPMENT.md`,
> `axe_core_manual_guide.md`). This doc links to them where relevant — it does
> not duplicate them.

---

## 0. TL;DR (read this first)

- `ka11y-node` is a stateless **Express API** that takes a URL (or raw HTML),
  renders it in **Puppeteer (headless Chromium)**, and returns accessibility
  findings as JSON.
- It runs **three rule engines** against each page:
  1. **axe‑core** — the industry‑standard DOM rule engine (~100 rules).
  2. **AccessLint** (`@accesslint/core`) — a second engine injected alongside axe for extra coverage.
  3. **32 hand‑written "custom checks"** (`src/custom-checks/*.check.js`) — for the
     WCAG criteria axe/AccessLint **cannot** do (media, pointer gestures, cognitive, focus appearance…).
- This service does **not** run on its own in production. A **Python service**
  (`ka11y-python`) is the orchestrator: it crawls the site, calls this Node API
  over HTTP (`POST /api/v1/analyse-url-flat`), runs its own image/CV/OCR/media
  stages in parallel, then **merges + de‑duplicates** everything into one report.
- Your day‑to‑day work as the Node dev: maintain axe wiring, and **own the 32
  custom checks** — fix false positives/negatives, add new ones, keep them
  localized (English + Japanese) and tested.

```
Browser / Frontend (a11y-frontend-sdk)
            │  HTTPS
            ▼
   ka11y-python  (orchestrator: crawl, snapshot, merge, report, persistence)
       │   │
       │   └── runs Python stages: image_audit, media_audit, rendered_layout,
       │        forms, pause_stop_hide, sensory, pipeline (contrast/focus/2.5.3/2.5.8)
       │
       │  HTTP POST /api/v1/analyse-url-flat   ◀── YOU ARE HERE
       ▼
   ka11y-node  (Express + Puppeteer)
       ├── axe-core              (DOM rules)
       ├── AccessLint core       (extra DOM rules)
       └── 32 custom checks      (the hard SCs)
```

---

## 1. Accessibility / WCAG in 5 minutes

You don't need to be an a11y expert, but you need this vocabulary because it's
everywhere in the code.

- **WCAG** = *Web Content Accessibility Guidelines*. The international standard
  (we target **WCAG 2.2**) for making web content usable by people with
  disabilities (blind/low‑vision, deaf, motor, cognitive…).
- **Success Criterion (SC)** = one testable requirement, identified by a dotted
  number like **`1.1.1`**, **`2.4.7`**, **`4.1.2`**. There are ~87 SCs in WCAG 2.2.
  In our code an SC id is always a string `"X.Y.Z"`. This is the **primary key**
  that ties everything together across both engines and both services.
- **Conformance level** = each SC is **A** (must), **AA** (should, the common
  legal target), or **AAA** (gold standard). The API accepts `level: "A" | "AA" | "AAA"`.
- A few SCs you'll see constantly:
  - `1.1.1` Non‑text Content (images need alt text)
  - `1.4.3` Contrast (Minimum)
  - `2.1.1` Keyboard
  - `2.4.7` Focus Visible
  - `4.1.2` Name, Role, Value (the big ARIA one)
- **Finding status** in our system is one of:
  - `fail` — a definite violation.
  - `pass` — verified OK.
  - `incomplete` — "needs human review" (a heuristic fired but we can't be 100% sure).
    Most custom checks lean on `incomplete` because many SCs are not fully automatable.
- **"Covered" ≠ "solved".** Automated tools can only catch a *subset* of WCAG
  problems. Industry consensus is that automation reliably catches ~30–40% of
  issues; the rest need human review. Our job is to maximize trustworthy
  automated coverage and clearly mark the rest as `incomplete`/manual.

---

## 2. The Node service — architecture & request flow

### 2.1 Layers (classic layered Express app)

| Layer | File(s) | Responsibility |
|-------|---------|----------------|
| **Entry / wiring** | `server.js` | Express app, security headers, CORS, routes, DI of services→controllers. Exports `app` (tests import it; `app.listen` only runs when executed directly). |
| **Controllers** | `src/controllers/*.controller.js` | HTTP concerns only: validate input, map errors→status codes, call a service. No business logic. |
| **Services** | `src/services/accessibility.service.js`, `rules.service.js` | The real work: Puppeteer lifecycle, SSRF guard, axe/AccessLint injection, custom‑check orchestration, crawling, result mapping. |
| **Engines** | `src/custom-checks/`, `axe-core` (npm), `@accesslint/core` (npm) | The actual rule logic. |
| **Mapping / utils** | `src/utils/*` | `axeResultMapper.js` (axe→our shape + SC mapping), `crawl.js` (bounded BFS), `stageTimings.js`, `canonicalUrl.js`, `logger.js`, `rulesLoader.js`, `sharedConfigLoader.js`. |
| **Config** | `src/config/app.config.js`, `swagger.config.js` | Env‑driven config + OpenAPI/Swagger. |

### 2.2 HTTP endpoints (`server.js`)

All under `/api/v1` (legacy unversioned aliases also exist for `/health`, `/rules*`):

| Method + path | Purpose |
|---------------|---------|
| `GET  /health` | Liveness/readiness probe (used by Python's health check). |
| `POST /analyze-accessibility` | Audit **raw HTML** (body `{ html, successCriteriaId?, lang? }`). Great for unit testing a rule against a snippet. |
| `POST /analyse-url` | Crawl one **URL**, return findings **grouped by SC**. |
| `POST /analyse-url-flat` | **★ The production endpoint Python calls.** Crawl a URL (optionally bounded‑BFS multiple pages), return a **flat, element‑wise** findings array. |
| `POST /rules/:successCriteriaId/analyse-url` | Audit a URL for a **single SC** (runs only that SC's axe rules + custom check). |
| `GET  /rules`, `GET /rules/wcag`, `GET /rules-guide[/:ruleId]` | Rule catalogue / metadata (localized). |
| `GET  /api-docs` | Swagger UI — try requests live here. |

### 2.3 What happens inside `analyse-url-flat` (the hot path)

`accessibility.service.js → analyseUrlFlat()` for each page:

1. **SSRF guard** — resolve the hostname, reject private/loopback/reserved IPs
   (`_assertPublicUrl`), and install a Puppeteer request interceptor that also
   blocks **redirect‑time** hops to private IPs (`_installSsrfInterceptor`).
2. **Navigate** with Puppeteer; optionally **bounded BFS** to `maxDepth`/`maxPages`
   (or audit exactly the `discoveredUrls` list Python's crawler already found —
   the preferred "snapshot‑fed" mode).
3. **Inject** `axe.min.js` **and** the AccessLint IIFE bundle into the page; set the axe locale.
4. **Run axe** (`axe.run`, scoped to the `runOnly` tags for the requested level).
5. **Run custom checks** (`runAll(page, { lang, timeoutMs })`) — static phase then
   interactive phase (see §4).
6. **Map + merge**: `mapResultsFlat(axeResults)` + `mapCustomResultsFlat(customResults)`
   → one flat array of element‑wise findings, filtered by level and optional SC.
7. Return `{ url, findings, timings? }`.

Each finding carries its `successCriteriaId`, status, impact, a **localized**
`reason`, and the offending element(s).

---

## 3. The three engines

### 3.1 axe‑core (`axe-core` npm package)
- The workhorse. Injected into the live page, run with WCAG **tag filters**
  (`_tagsForLevel`: `wcag2a`, `wcag21a`, `wcag22a`, `wcag2aa`, … + `best-practice`).
- Locale‑aware: `_configureAxeLocale` loads axe's bundled locale JSON (de, ja, fr, …)
  so axe's own messages come back translated.
- We **don't** show axe's raw output — `axeResultMapper.js` converts each axe rule
  result into our finding shape and attaches the WCAG **SC id** (derived from the
  rule's `wcagN.N.N` tags via `extractSuccessCriteriaId` / `_normalizeCriterionId`).

### 3.2 AccessLint (`@accesslint/core`)
- A second DOM engine injected alongside axe (loaded from its `index.iife.js`
  because of its `package.json` `exports` restrictions — see the workaround in
  `accessibility.service.js`). It adds rules axe doesn't have.
- Its rule→SC→level mapping is documented in **`al_rules.txt`** and applied via
  **`al_map.js`**. Results are folded in through `mapResults(axe, criteria, accessLintResults)`.

### 3.3 Custom checks (`src/custom-checks/*.check.js`) — **your main asset**
- **32 bespoke checks** for the SCs axe/AccessLint can't handle. Each is a small
  module that runs DOM/heuristic logic inside `page.evaluate(...)` and returns a
  normalized result. **This is where you'll spend most of your time.** Full anatomy in §5.

---

## 4. Static vs. interactive custom checks

Checks declare a **mode** (`MODE` export, or inferred from `LEGACY_META` in
`src/custom-checks/index.js`):

- **`static`** (27 checks) — read‑only DOM inspection. Safe to run **in parallel**
  (`Promise.allSettled`). They don't change page state.
- **`interactive`** (5 checks) — they **drive** the page (move keyboard focus, tab
  through elements, dispatch events). They must run **sequentially** because they
  mutate focus/keyboard state, and they share a single pre‑computed focusable‑element
  set (`discoverPageElements` + `FOCUSABLE_SELECTOR`) for speed.

`runAll()` runs **static first, then interactive**, with a **split time budget**
(60% static / 40% interactive) so a slow interactive phase can't forfeit completed
static findings. Per‑check failures are isolated — one throwing check becomes an
`incomplete` "execution failed" finding, never a crashed request.

---

## 5. Anatomy of a custom check (the contract)

Every `*.check.js` module **must** export `run` plus a few constants. Reference
example: `src/custom-checks/use-of-color.check.js`.

```js
'use strict';
const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC       = '1.4.1';                         // the WCAG SC this check covers
const RULE_ID  = 'custom-use-of-color';           // stable id, always 'custom-…'
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/use-of-color';
const MODE     = 'static';                         // 'static' | 'interactive'
const FALLBACK_DESCRIPTION = 'Color must not be the only visual means…';

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);       // { config, lang, page }
  // 1) Gather evidence INSIDE the page (runs in the browser, not Node):
  const data = await page.evaluate(() => {
    /* DOM heuristics … return plain serializable data */
    return { violations: [/* … */], checkedCount: 0 };
  });
  // 2) Decide status in Node and build a LOCALIZED reason:
  if (data.violations.length === 0) {
    return {
      successCriteriaId: SC,
      rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION,
                impact: null, status: 'pass',
                reason: renderLocalizedText(
                  { en: '{count} link(s) checked — all OK.', ja: 'リンク {count} 件を確認しました。' },
                  { count: data.checkedCount }, ctx, '…'),
                helpUrl: HELP_URL }],
    };
  }
  return {
    successCriteriaId: SC,
    rules: [{ ruleId: RULE_ID, description: FALLBACK_DESCRIPTION,
              impact: 'serious', status: 'fail',
              reason: renderLocalizedText({ en: '…', ja: '…' }, { /* params */ }, ctx, '…'),
              elements: data.violations.slice(0, 80),   // element‑wise evidence
              helpUrl: HELP_URL }],
  };
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
```

### The return shape (memorize this)

```js
{
  successCriteriaId: "1.4.1",            // string "X.Y.Z" (or "best-practice")
  rules: [
    {
      ruleId:      "custom-use-of-color",
      description: "…short rule description…",
      impact:      "serious" | "moderate" | "minor" | null,
      status:      "pass" | "fail" | "incomplete",
      reason:      "…LOCALIZED human-readable explanation…",
      elements:    [ { html, element_id, target, tag, … } ],   // optional, for fail/incomplete
      helpUrl:     "https://www.w3.org/WAI/WCAG22/Understanding/…"
    }
  ]
}
```

`mapCustomResultsFlat()` later flattens this into per‑element findings for the
combined report, so always populate `elements` (with a `target`/selector) when you
can — that's what drives the "highlight the offending node" UI.

### Key rules / conventions
- **Never hardcode user‑facing English.** Every `reason` goes through
  `renderLocalizedText({ en, ja }, params, ctx, fallback)` (or
  `renderReasonTemplate(checkKey, code, …)` which pulls from `i18n/rules.yml`).
  We ship English + Japanese; missing locale falls back to `en`. This is a
  hard project rule across both engines.
- **Tunables come from shared config**, not magic numbers — read them via
  `getNumberConfig` / `getKeywordList` (backed by `config/universal.yml`, loaded
  through `sharedConfigLoader.js`). Keep language‑specific keyword lists in config, not inline.
- **Prefer `incomplete` over a shaky `fail`.** False positives erode trust faster
  than misses. Definite violations → `fail`; heuristic suspicions → `incomplete`.
- **All DOM work happens in `page.evaluate`** and must return plain serializable
  data (no DOM nodes cross the boundary). Cap how much you scan (e.g. `MAX_LINKS`)
  for performance on large pages.

---

## 6. Coverage — what Node owns, what Python owns, what nobody can automate

> Per your request this is framed as **Node‑owned SCs + Python delegation**, not a
> full 87‑row matrix. The authoritative per‑rule deep dive (heuristics, known
> gaps, fixtures) is **`docs/RULE_ANALYSIS.md`**; the manual‑only list is
> **`docs/WCAG _Criteria Requiring _Manual Intervention.md`**.

### 6.1 Node‑owned SCs

**A. Covered by axe‑core + AccessLint** (standard machine‑checkable DOM rules — you
rarely touch these, you just keep the wiring/locale working). Includes, e.g.:
`1.1.1` (img‑alt), `1.3.1`, `1.4.4`, `2.4.2` (title), `2.4.4`, `3.1.1` (page lang),
`4.1.2` (name/role/value) and many more A/AA rules. See `al_rules.txt` for the
AccessLint half and `docs/axe_core_manual_guide.md` for the axe half.

**B. Covered by the 32 custom checks** (this is *your* surface area):

| SC | Check file | Mode |
|----|-----------|------|
| 1.1.1 | `background-image-content.check.js` (CSS bg images carrying meaning) | static |
| 1.2.1 | `audio-transcript.check.js` | static |
| 1.2.2 | `captions-prerecorded.check.js` | static |
| 1.2.3 | `audio-description.check.js` | static |
| 1.2.4 | `captions-live.check.js` | static |
| 1.3.2 | `meaningful-sequence.check.js` | static |
| 1.3.4 | `orientation.check.js` | static |
| 1.4.1 | `use-of-color.check.js` | static |
| 1.4.2 | `audio-control.check.js` | static |
| 1.4.5 | `images-of-text.check.js` | static |
| 2.1.2 | `keyboard-trap.check.js` | interactive |
| 2.1.4 | `character-key-shortcuts.check.js` | static |
| 2.4.5 | `multiple-ways.check.js` | static |
| 2.4.7 | `focus-visible.check.js` | interactive |
| 2.4.8 | `location.check.js` | static |
| 2.4.9 | `link-purpose.check.js` | static |
| 2.4.13 | `focus-appearance.check.js` | interactive |
| 2.5.1 | `pointer-gestures.check.js` (+ deep audit in `src/audits/wcag-2.5.1/`) | static |
| 2.5.2 | `pointer-cancellation.check.js` | static |
| 2.5.4 | `motion-actuation.check.js` (+ deep audit in `src/audits/wcag-2.5.4/`) | static |
| 2.5.7 | `dragging-movements.check.js` | static |
| 3.1.2 | `language-of-parts.check.js` | static |
| 3.1.6 | `pronunciation.check.js` | static |
| 3.2.1 | `on-focus.check.js` | interactive |
| 3.2.2 | `on-input.check.js` | interactive |
| 3.2.6 | `consistent-help.check.js` | static |
| 3.3.3 | `error-suggestion.check.js` | static |
| 3.3.4 | `error-prevention.check.js` | static |
| 3.3.7 | `redundant-entry.check.js` | static |
| 3.3.8 | `accessible-auth.check.js` | static |
| 4.1.1 | `html-parsing.check.js` | static |
| 4.1.3 | `status-messages.check.js` | static |

**Total: 32 custom checks (27 static + 5 interactive).**

### 6.2 Delegated to Python (`ka11y-python`) — **not** Node's job

The Python orchestrator runs parallel stages that need CV/OCR, audio/video
transcription, full‑page rendering math, or cross‑page state. **Do not** try to
reimplement these in Node — by design they live in Python:

| Python stage | Roughly owns SCs |
|--------------|------------------|
| `image_audit` (OCR / vision) | `1.1.1` (alt *quality*), `1.4.5` (text‑in‑image), `1.4.11` (non‑text contrast) |
| `media_audit` (Deepgram transcription/diarization) | `1.2.1`–`1.2.3` deep verification |
| `rendered_layout_audit` | `1.4.3`/`1.4.6` (dynamic contrast), `1.4.4` resize, `1.4.10` reflow, `1.4.13`, `2.5.8` target size |
| `pipeline` (always on) | `2.5.3` label‑in‑name, `2.5.8`, `1.1.1`, focus, contrast decisioning |
| `form_audit` | `3.3.1`, `3.3.2`, `1.3.5` |
| `pause_stop_hide` | `2.2.2` |
| `text_spacing` | `1.4.12` |
| `sensory_audit` | `1.3.3`, `2.3.1` |
| language stage | `3.1.3`, `3.2.3`, `3.2.4`, navigation `2.4.10`–`2.4.12` |

**Overlap is intentional.** Both engines sometimes fire on the same SC (e.g.
`1.1.1`, `1.4.5`, `1.4.3`). The combined runner **de‑duplicates by `(SC, element)`
key** and applies an **override rule** (the engine with the higher‑confidence
finding wins) — see `ka11y-python/.../combined/runner.py::_merge…`. So when you add
or change a Node finding, be aware Python may also be producing one for the same node.

### 6.3 Genuinely uncovered / manual‑only

Some SCs **cannot** be reliably automated by anyone and are reported as
`incomplete`/manual (full list in `docs/WCAG _Criteria Requiring _Manual
Intervention.md`). Examples: `2.3.1` Three Flashes (needs flicker analysis),
`2.4.3` Focus Order (needs human task‑flow judgment), `1.4.4` Resize Text (manual
zoom), `2.4.6` Headings & Labels descriptiveness. For these we surface a
"needs human review" finding rather than a pass/fail — that *is* the coverage.

---

## 7. ★ How to wire a NEW rule — end‑to‑end tutorial

We'll add a brand‑new custom check for **WCAG 2.4.6 — Headings and Labels** (a
static heuristic: flag empty headings and duplicate sibling heading text). Replace
the SC/logic with your real rule; the **wiring steps are identical for any new check.**

### Step 0 — Decide it belongs in Node
Ask: *can this be determined from the rendered DOM without OCR / audio / layout
math / cross‑page state?* If yes → Node custom check. If it needs vision, media,
or rendered‑layout measurement → it's a **Python** stage (talk to the Python dev).
2.4.6 is pure DOM → Node. 

### Step 1 — Create the check module
`src/custom-checks/headings-and-labels.check.js`:

```js
'use strict';
const { getSharedRuleContext, renderLocalizedText } = require('./sharedAssets');

const SC       = '2.4.6';
const RULE_ID  = 'custom-headings-and-labels';
const HELP_URL = 'https://www.w3.org/WAI/WCAG22/Understanding/headings-and-labels';
const MODE     = 'static';
const FALLBACK_DESCRIPTION = 'Headings and labels must describe topic or purpose';

function _t(ctx, en, ja, params = {}) {
  return renderLocalizedText({ en, ja }, params, ctx, en);
}

async function run(page, context = {}) {
  const ctx = getSharedRuleContext(context);

  const data = await page.evaluate(() => {
    const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'));
    const empties = [];
    const dupes   = [];
    const seen    = new Map();

    for (const h of headings) {
      const text = (h.textContent || '').replace(/\s+/g, ' ').trim();
      const target = h.id ? [`#${CSS.escape(h.id)}`] : [h.tagName.toLowerCase()];
      if (!text) {
        empties.push({ html: h.outerHTML.slice(0, 150), element_id: h.id || null, target, tag: h.tagName });
        continue;
      }
      const key = `${h.tagName}:${text.toLowerCase()}`;
      if (seen.has(key)) {
        dupes.push({ html: h.outerHTML.slice(0, 150), element_id: h.id || null, target, tag: h.tagName, text });
      } else {
        seen.set(key, true);
      }
    }
    return { empties, dupes, checkedCount: headings.length };
  });

  const problems = [...data.empties, ...data.dupes];

  if (problems.length === 0) {
    return { successCriteriaId: SC, rules: [{
      ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: null, status: 'pass',
      reason: _t(ctx,
        '{count} heading(s) checked — none empty and no duplicate sibling headings.',
        '見出し {count} 件を確認しました。空の見出しや重複した見出しはありません。',
        { count: data.checkedCount }),
      helpUrl: HELP_URL,
    }]};
  }

  return { successCriteriaId: SC, rules: [{
    ruleId: RULE_ID, description: FALLBACK_DESCRIPTION, impact: 'moderate', status: 'incomplete',
    reason: _t(ctx,
      '{empty} empty heading(s) and {dupe} duplicate heading(s) found. Verify each heading describes its section. Empty headings convey no structure to screen-reader users.',
      '空の見出しが {empty} 件、重複した見出しが {dupe} 件見つかりました。各見出しがセクションの内容を説明しているか確認してください。',
      { empty: data.empties.length, dupe: data.dupes.length }),
    elements: problems.slice(0, 50),
    helpUrl: HELP_URL,
  }]};
}

module.exports = { run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION };
```

> **Auto‑discovery:** `index.js` reads every `*.check.js` in the folder, so the file
> is picked up automatically — **no manual registration needed** for it to run.
> The registry only needs editing if you want a custom **execution order** or a
> legacy fallback (next step, optional).

### Step 2 — (Optional) declare order/meta in the registry
`src/custom-checks/index.js` keeps `STATIC_ORDER` / `INTERACTIVE_ORDER` for
deterministic ordering and a `LEGACY_META` map for fallback descriptions of checks
that predate the `MODE`/`FALLBACK_DESCRIPTION` exports. Because our new module
**exports `MODE` and `FALLBACK_DESCRIPTION`**, you can skip `LEGACY_META`. If you
want it to run in a specific slot, add `'custom-headings-and-labels'` to
`STATIC_ORDER`; otherwise it sorts alphabetically after the listed ones (fine).

### Step 3 — Make sure the SC maps cleanly (the mapper)
`src/utils/axeResultMapper.js` flattens custom results (`mapCustomResultsFlat`) and
maps SC ids to names/levels/help. The SC `2.4.6` already exists in WCAG metadata, so
nothing to add. **If you introduce an SC the metadata doesn't know yet**, add it to
the WCAG metadata source (`src/utils/wcagMetadata.js` / `wcagCriteriaNames.js`) so
the criterion name and level resolve, and confirm `axeRuleIdsForCriteria` /
`_criterionLevel` return sensible values.

### Step 4 — Localize properly (i18n)
- Inline `{ en, ja }` (as above) is fine for one‑off strings.
- For reusable/templated reasons, add them to **`i18n/rules.yml`** under
  `reason_templates."2.4.6"` and render via
  `renderReasonTemplate('2.4.6', 'empty_heading', params, ctx)`. Locale overrides go
  in `i18n/locales/ja.yml` (and `de.yml`). Run `scripts/sync-i18n.sh` if you touch
  the YAML so locale files stay in sync.
- Any keyword lists / thresholds → `config/universal.yml`, read via
  `getKeywordList` / `getNumberConfig`. **Do not inline language‑specific words.**

### Step 5 — Write tests (Jest)
Unit tests **mock `page.evaluate`** — no real browser needed, so they're fast.
Pattern from `tests/custom-checks/images-of-text.check.test.js`:

`tests/custom-checks/headings-and-labels.check.test.js`:
```js
'use strict';
const { run } = require('../../src/custom-checks/headings-and-labels.check');

const makePage = (result) => ({ evaluate: jest.fn().mockResolvedValue(result) });

describe('headings-and-labels.check (WCAG 2.4.6)', () => {
  test('passes when no empty/duplicate headings', async () => {
    const page = makePage({ empties: [], dupes: [], checkedCount: 4 });
    const r = await run(page);
    expect(r.successCriteriaId).toBe('2.4.6');
    expect(r.rules[0].status).toBe('pass');
    expect(r.rules[0].ruleId).toBe('custom-headings-and-labels');
  });

  test('incomplete when an empty heading exists', async () => {
    const page = makePage({ empties: [{ html: '<h2></h2>', target: ['h2'], tag: 'H2' }], dupes: [], checkedCount: 3 });
    const r = await run(page);
    expect(r.rules[0].status).toBe('incomplete');
    expect(r.rules[0].elements).toHaveLength(1);
  });

  test('ja locale returns Japanese reason', async () => {
    const page = makePage({ empties: [{ html: '<h2></h2>', target: ['h2'], tag: 'H2' }], dupes: [], checkedCount: 3 });
    const r = await run(page, { lang: 'ja' });
    expect(r.rules[0].reason).toMatch(/見出し/);
  });
});
```
For a fuller integration test, add an HTML fixture under
`tests/fixtures/custom-checks/` and assert against a real Puppeteer page (see
existing fixture‑based tests).

### Step 6 — Run & verify
```bash
npm test                      # full Jest suite + coverage (writes junit.xml)
npx jest headings-and-labels  # just your test

npm run dev                   # start server with auto-reload
# Then exercise it against raw HTML, filtered to your SC:
curl -s localhost:3000/api/v1/analyze-accessibility \
  -H 'Content-Type: application/json' \
  -d '{"html":"<h1>Hi</h1><h2></h2><h2>Hi</h2>","successCriteriaId":"2.4.6"}' | jq
```
You should see a `2.4.6` group with your `custom-headings-and-labels` finding.

### Step 7 — Confirm it flows to the combined report
Nothing extra to do on the Node side: because the finding carries
`successCriteriaId: "2.4.6"`, Python's `analyse-url-flat` consumer picks it up, runs
it through the merge/dedup, and it lands in the final report and the frontend. If
Python *also* has a stage for that SC, check the merge override behavior so you
don't double‑report.

### New‑rule checklist
- [ ] `src/custom-checks/<name>.check.js` exports `run, SC, RULE_ID, HELP_URL, MODE, FALLBACK_DESCRIPTION`
- [ ] `run` returns the `{ successCriteriaId, rules:[{…}] }` shape; status is `pass`/`fail`/`incomplete`
- [ ] All user‑facing text via `renderLocalizedText` / `renderReasonTemplate` (en + ja)
- [ ] Tunables/keywords in `config/universal.yml` / `i18n/*.yml`, not inline
- [ ] Element evidence populated (`elements[]` with `target` selectors)
- [ ] (If new SC) added to `wcagMetadata.js` / `wcagCriteriaNames.js`
- [ ] (Optional) added to `STATIC_ORDER`/`INTERACTIVE_ORDER` in `index.js`
- [ ] Jest unit test (mock `page.evaluate`) incl. a `ja` locale assertion
- [ ] `npm test` green; manual `curl` against `analyze-accessibility` looks right

---

## 8. Local dev, run, test

```bash
# Requirements: Node >=18 (package.json engines; Docker image uses node:20), Chromium auto-downloaded by Puppeteer
npm install                  # installs deps + Chromium

npm run dev                  # nodemon, http://localhost:3000  (Swagger at /api-docs)
npm start                    # production start
npm test                     # Jest + coverage → junit.xml
npm run lint                 # ESLint
npm run accesslint           # eslint w/ jsx-a11y plugin (lints OUR code, separate from the audit engine)

curl localhost:3000/api/v1/health
```

Run the whole product (Node + Python + frontend + docs) via the repo‑root
`docker-compose.yml` (`docker compose up`). Node is the `node` service
(`container_name: ka11y-node`), reachable by Python at `http://node:3000`.

### Tests layout
- `tests/custom-checks/*.test.js` — unit tests per check (mock `page.evaluate`).
- `tests/fixtures/…` — HTML fixtures for integration‑style tests.
- `tests/services/`, `tests/controllers/`, `tests/utils/` — layer tests.
- Coverage + `junit.xml` are produced by `npm test` (CI consumes them; see `.gitlab-ci.yml`).

---

## 9. Configuration & environment

Config is centralized in `src/config/app.config.js` (env‑driven). Common knobs
(see `.env.example`):

| Env var | Default | Meaning |
|---------|---------|---------|
| `PORT` | `3000` | Server port. |
| `BODY_LIMIT` | `10mb` | Max request body size. |
| `AXE_TIMEOUT_MS` | `30000` | Per‑page axe run timeout. |
| `CUSTOM_CHECKS_TIMEOUT_MS` | `30000` | Budget for `runAll` (split 60/40 static/interactive). |
| `FLAT_CRAWL_BUDGET_MS` | — | Overall wall‑clock cap for a multi‑page bounded‑BFS crawl. |
| `FLAT_PER_PAGE_MS` | — | Per‑page time cap inside a crawl. |
| `PUPPETEER_MAX_CONCURRENT` | `3` | Max concurrent Puppeteer pages (read in `accessibility.service.js`). |
| `PUPPETEER_EXECUTABLE_PATH` | — | Override the Chromium binary path. |
| `ALLOWED_ORIGINS` | `localhost:5173,3000` | CORS allow‑list (comma‑separated; read in `server.js`). |
| `NODE_BASE_URL` | `http://localhost:3000` | (Set on the **Python** side to reach this service.) |

Shared cross‑engine tunables/keywords live in repo‑root **`config/universal.yml`**
(loaded by `src/utils/sharedConfigLoader.js`) and i18n strings in
`i18n/rules.yml` + `i18n/locales/*.yml`.

---

## 10. Conventions, gotchas & security

- **SSRF guard is mandatory** and already implemented — every audited URL is
  resolved and checked against private/reserved IP ranges, and redirect hops are
  intercepted. Don't add a code path that fetches a user URL without going through
  `accessibility.service.js`'s guards.
- **Errors never crash the request.** A failing check → `incomplete` finding; a
  failing module load → a `custom-load-failure` finding. Preserve this resilience.
- **Status discipline:** `fail` only for definite violations; otherwise `incomplete`.
- **i18n is non‑negotiable:** no inline English in user‑facing `reason`s.
- **Determinism:** static checks must be side‑effect‑free; only interactive checks
  may touch focus/keyboard, and they run sequentially for a reason.
- **The SC string is the contract** between Node and Python. Get `successCriteriaId`
  right and the rest of the pipeline just works.

---

## 11. Where to go deeper

| Topic | File |
|-------|------|
| Per‑rule heuristics, known gaps, fixtures, recent bug fixes | `docs/RULE_ANALYSIS.md` |
| Service internals, crawling, rule‑integration strategy, SSRF | `docs/DEVELOPMENT.md` |
| axe‑core rule reference | `docs/axe_core_manual_guide.md` |
| Custom‑rule fixture review | `docs/CUSTOM_RULES_FIXTURE_REVIEW.md` |
| Manual‑only WCAG criteria | `docs/WCAG _Criteria Requiring _Manual Intervention.md` |
| AccessLint rule→SC map | `al_rules.txt`, `al_map.js` |
| Quick start / API examples | `README.md`, `GETTING_STARTED.md` |
| Python side (orchestrator, merge, report) | `../ka11y-python/` (`ka11y/api/v1/combined/`) |

Welcome aboard — start by reading `use-of-color.check.js` end‑to‑end, then run
`npm test`, then do the §7 tutorial for real.
