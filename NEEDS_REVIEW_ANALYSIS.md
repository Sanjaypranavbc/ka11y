# Needs Review — Complete Code Analysis & Scoring Model

**Date:** 2026-06-02 · **Audience:** product + client stakeholders + engineering
**Question being answered:** *"Needs Review is higher than Violations/Passes — so why do clients need this platform?"*

---

## 0. TL;DR

`Needs Review` is **not** a defect or a sign of a weak engine. It is the platform
**refusing to guess** on the parts of WCAG that are genuinely **not 100% machine-decidable**,
while still pinpointing the exact element + evidence a human needs. Cheap axe-only
tools hide these as silent **passes** (legal risk) or noisy **fails** (alert fatigue).
We surface them as a scoped, evidence-backed worklist.

As of this release the workflow is closed end-to-end:

- Every `needs_review` item is labelled **"Manual Review Required"** and counted in the score.
- A reviewer sets each item to **Pass** or **Violation**.
- The score (counts of **Violations / Needs Review / Passes**) **auto-updates** — items
  move out of *Needs Review* into *Pass*/*Violation* and the pass-rate recomputes.

So the high `Needs Review` number is a **starting backlog that shrinks as the team works**,
not a permanent state.

---

## 1. Where `Needs Review` comes from (code-level)

There are exactly **two** producers.

### 1.1 axe-core `incomplete` → `needs_review`  (usually the bulk)
axe-core returns three buckets: `violations`, `passes`, **`incomplete`**. The
`incomplete` bucket is axe saying *"a rule applied but I could not reach a verdict."*
We map it **one finding per node**:

- Node engine: `ka11y-node/src/utils/axeResultMapper.js:480` (`status: 'needs_review'`).
- Unified engine (P6): `ka11y-python/ka11y/crawler/axe_runner.py` → `map_axe_results` (`incomplete → needs_review`).

**The dominant rule is `color-contrast`.** axe marks contrast *incomplete* (not fail)
whenever it cannot resolve the effective background: a background **image**, CSS
**gradient**, **overlapping**/translucent layers, or text over **video**. On a
marketing site where most text sits on hero images/gradients, this alone can emit
**dozens of `needs_review` nodes per page** — which is exactly why the count looks
"high." Other frequently-incomplete axe rules: `aria-*` state rules on custom
widgets, `scrollable-region-focusable`, `link-in-text-block`.

### 1.2 Python heuristic checks that *intentionally* defer
Our deeper Python auditors (which cover SC axe doesn't touch at all) emit
`needs_review` when the signal is present but a deterministic verdict isn't
defensible. Each has an i18n reason string (`i18n/rules.yml`) and a `reason_code`.
From `ka11y/api/v1/combined/findings.py`:

| WCAG SC | Check (file ref) | Why it can't auto-decide | What the human confirms |
|--------|------------------|--------------------------|--------------------------|
| **1.1.1** | alt-text (`findings.py:485`) | An `alt` exists but only a person knows if it conveys the image's *meaning* | Is the alt text accurate/meaningful? |
| **1.4.3 / 1.4.6** | contrast-over-image via OCR (`findings.py:681,796`) | OCR locates text-in-image; exact glyph vs local-background ratio is below auto-confidence | Is the in-image text readable? |
| **1.4.5 / images-of-text** (`findings.py:876`) | We detect text rendered as an image; whether it's "essential" (logo) is contextual | Is text-as-image justified? |
| **1.4.11** non-text contrast (`findings.py:958`) | Control/boundary contrast can't be measured when the boundary is implicit | Does the control have a 3:1 boundary? |
| **2.2.2** moving content (`findings.py:1114`) | Motion detected but its *duration* (the ≤5s threshold) isn't machine-measurable | Does it auto-stop / have a pause control? |
| **1.4.12** text spacing (`findings.py:1313,1326`) | Fixed height + `overflow:hidden` *may* clip on spacing override — risk, not proof | Does text clip when spacing is increased? |
| **1.2.1 / 1.2.2 / 1.2.3 / 1.2.5** media (`findings.py:1503,1530`) | A track/transcript exists but *coverage & accuracy* need human judgement | Do captions/descriptions actually match? |
| **1.4.4 / 1.4.10 / 1.3.4 / 1.4.13 / 2.4.11** rendered-layout (`_rendered_rule_to_findings`, `findings.py:1242`) | Reflow/resize/orientation/hover checks flag layout *risk* a person should eyeball | Does the page hold up at that viewport/zoom? |
| **4.1.2** name/role/value (`findings.py:564`) | Custom widget exposes *some* ARIA but completeness is contextual | Are name/role/state correct for AT? |
| **(any)** criterion-aware fallback (`findings.py:1242`, `needs_review_unknown`) | SC selected for audit but no deterministic rule fired | Manual check against the SC |

> Mechanically: `findings._is_incomplete_reason()` (`findings.py:162`) routes any
> auditor reason starting `INCOMPLETE` to `needs_review`, and `reason_code`s like
> `needs_review_unknown`, `needs_review_warning`, `needs_review_info` carry the
> localized explanation (`i18n/rules.yml:108–246`).

---

## 2. Why this is a **strength**, not a weakness

Automated accessibility testing has a hard ceiling: independent studies (and WCAG's
own "Accessibility Conformance Testing" taskforce) put the share of WCAG success
criteria that are **fully** machine-testable at roughly **30–40%**. Every honest
tool faces the other ~60%. There are only three things a tool can do with them:

1. **Silently pass them** (what axe-only / "0 violations!" tools effectively do) →
   the client ships inaccessible pages and finds out in a **demand letter**.
2. **Hard-fail them** → huge false-positive noise, teams stop trusting the tool.
3. **Surface them as scoped, evidence-backed "Manual Review Required"** → honest,
   actionable. **This is what ka11y does.**

So a high `Needs Review` count is the platform doing the **valuable, hard** part —
covering the SC competitors quietly skip (AAA contrast, media quality, cognitive,
reflow, motion) and handing the reviewer a precise, pre-investigated list instead
of "go read WCAG and check the whole site yourself."

**Client value, concretely:**
- **Coverage**: ka11y evaluates ~3–4× the SC of an axe-only scan (all of axe's A/AA
  *plus* AAA, media 1.2.x, 1.4.x enhanced, 2.5.x, cognitive 3.x via the Node custom checks).
- **Evidence per item**: each `needs_review` is tied to a specific element with a
  selector, HTML snippet, and (for image/contrast) a **screenshot/OCR crop** — review
  is minutes, not a from-scratch manual audit.
- **It shrinks**: the manual-review workflow folds decisions back into the score, so
  the backlog burns down and the *next* crawl of unchanged elements can inherit a
  decision rather than re-asking (roadmap).
- **Deterministic majority still automated**: clear violations and clear passes are
  decided automatically; `Needs Review` is only the irreducible judgement set.

---

## 3. The scoring model (as implemented)

"Score" = the three counts shown in the demo: **Violations**, **Needs Review**, **Passes**.

- `ka11y/api/v1/combined/report.py:_build_report` computes the automated baseline.
  Pass-rate = `passes / (passes + violations)` (0–100; `null` when nothing
  pass/fail was decided). `summary.manual_review_required` = the `needs_review` count.
- Every finding gets a stable `finding_id` (`report._finding_signature`) and
  `needs_review` items get `manual_review: true`.
- **Review action:** `POST /api/v1/combined/{run_id}/findings/{finding_id}/review`
  with `{"status": "pass" | "violation", "note": "..."}` (status `needs_review` re-opens it).
  Stored durably in `finding_reviews` (SQLite).
- **Effective score:** `report.apply_reviews()` overlays decisions on read
  (`GET /combined/{run_id}`): a reviewed item moves to Pass/Violation, `Needs Review`
  decrements, and the pass-rate + per-page scores recompute. The original automated
  numbers are preserved under `summary.automated`; `summary.reviews` reports
  `{reviewed, pending, as_pass, as_violation}`.

```
Automated:   Violations 12 | Needs Review 40 | Passes 88 | Score 88.0%
            └─ reviewer marks 25 needs_review (5 violation, 20 pass) ─┐
Effective:   Violations 17 | Needs Review 15 | Passes 108| Score 86.4%
```

API surface:
- `GET  /api/v1/combined/{run_id}` → report with **effective** summary + per-finding `review_status`.
- `POST /api/v1/combined/{run_id}/findings/{finding_id}/review` → set/clear a decision.
- `GET  /api/v1/combined/{run_id}/reviews` → all decisions for the run.

---

## 4. Heuristic / partial checks — coverage you asked to pin down

For the stakeholder question *"which WCAG SC would be covered, and what specific
checks would be performed"* for the heuristic (non-deterministic) checks — that is
exactly **§1.2's table** above. Every heuristic check names: the **SC**, the
**concrete signal it computes**, **why** it defers, and **what the reviewer
verifies**. These are the items that arrive as **Needs Review / Manual Review
Required** and that the §3 workflow lets a reviewer resolve into the score.

Nothing in this set silently passes or silently fails: a heuristic check either
produces a deterministic verdict (when it can) or a scoped `needs_review` with
evidence (when it can't).
