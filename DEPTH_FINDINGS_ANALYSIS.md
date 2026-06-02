# Why the same page yields fewer findings as a child than as a root

**Symptom:** Auditing URL *X* alone → 200+ findings. The same *X* visited as a
child page inside a `max_depth>0` crawl → caps out around ~100.

**Date:** 2026-06-02

---

## Root cause: the OCR/image budget is **per-run, shared across all pages**

The image audit produces the bulk of a page's findings for the image-based
criteria — **1.1.1** (text-in-image / alt), **1.4.3** & **1.4.6** (contrast over
images), **1.4.5** (images of text). Those all depend on OCR.

OCR is gated by a single per-run budget:

```python
# stages.py (before the fix)
max_ocr_images = get_max_ocr_images_per_run()          # config: 60
ocr_paths, skipped = select_ocr_candidate_paths(
    image_crawler.images_data,                          # images from ALL pages
    limit=max_ocr_images,
)
```

`select_ocr_candidate_paths` (`crawler_settings.py`) ranks **every image from
every crawled page together** by priority (buttons → text-images → functional →
… → decorative) and keeps only the **top 60 for the whole run**. Everything past
rank 60 goes to `skipped_ocr_paths`, which is **logged and then dropped — no
finding is emitted for a skipped image** (`stages.py:540`).

Consequence:

| Scenario | Images competing for the 60 slots | X's share |
|----------|-----------------------------------|-----------|
| **X audited alone** (`max_depth=0`) | only X's images | up to 60 |
| **X as a child** in an *N*-page crawl | X + all siblings' images | ~60/*N*, and often **0** if X's images rank below sibling pages' images |

So as a child, X's image findings are starved by its siblings, and the page that
produced 200 findings alone produces far fewer — exactly the reported behaviour.

### What is **not** the cause (verified)
- **axe-core (Node):** in snapshot-fed mode it visits *every* discovered URL with
  the *same* per-page budget (`accessibility.service.js`, "no time budget; each
  page capped by perPageMs"). Per-page axe coverage at depth == root.
- **Focus / hover caps** (`max_focus_steps=100`, `max_hover_candidates=12`): these
  are applied **per page** in `rendered_layout_crawler.py`, not per run.
- **Pipeline contexts:** the snapshot's per-page extraction runs the full
  `extract_contexts` + `enrich_semantics` + `batch_evaluate_focus` (same three
  steps as the single-URL path), so 2.5.3 / 2.5.8 / 1.4.x / 2.4.7 coverage is
  equivalent per page.
- **Pipeline merge / manual-review:** untouched by this; they don't drop findings.

### One display caveat (not a per-page loss)
The runner slims the **flat** `report["passes"]` array to 100 for the in-memory
result (`runner.py`). This only trims the flat *array* shown in the UI — the
`summary` counts and the per-page `pages[].passes` arrays are computed from the
full set and are unaffected. If you read the flat passes list on a deep crawl it
will look capped at 100; read `summary.passes` or the per-page view for the true
count.

---

## The fix

The OCR budget now **scales with the number of crawled pages** and is
**distributed fairly** so no page monopolises it.

`crawler_settings.py`:
- `get_max_ocr_images_per_page()` — per-page budget (default 60, falls back to the
  legacy per-run value).
- `get_max_ocr_images_ceiling()` — hard cap on total OCR per run (default 600) to
  bound the cost of a deep crawl.
- `select_ocr_candidate_paths(..., fair_per_page=True)` — after global priority
  ranking, buckets images by source page and takes **one image per page per
  round** (round-robin), so every page contributes its top images.

`stages.py` (image stage):
```python
distinct_pages = len({i.url for i in image_crawler.images_data if i.url}) or 1
if distinct_pages > 1:
    max_ocr_images = min(
        get_max_ocr_images_per_page() * distinct_pages,   # scales with depth
        get_max_ocr_images_ceiling(),                     # cost ceiling
    )
    select_ocr_candidate_paths(..., limit=max_ocr_images, fair_per_page=True)
else:
    max_ocr_images = get_max_ocr_images_per_run()          # single-page: unchanged
```

**Effect by crawl size** (defaults per_page=60, ceiling=600):

| Pages | Old total budget | New total budget | Per-page share |
|-------|------------------|------------------|----------------|
| 1 (root) | 60 | 60 (unchanged) | 60 |
| 5 | 60 (shared) | 300 | ~60 |
| 50 | 60 (shared) | 600 (ceiling) | ~12 |

A child page now gets the same image coverage it would as the root for small/medium
crawls, and a fair, non-starved share on very deep crawls. Single-page behaviour is
byte-for-byte unchanged. All knobs live in `config.yml → crawler.performance`.

### Related depth fixes shipped alongside
- `max_links_per_page` now scales as `max(50, max_pages)` (was a flat 50, which
  throttled child-URL discovery when `max_pages>50`).
- `UniversalPageLoader.load()` now accepts `max_pages`/`internal_links` directly
  (the literal `max_pages=50` was only a fallback, but it was a foot-gun).

### Tuning for maximum parity
To make every child page match its standalone audit exactly, raise the ceiling
(e.g. `max_ocr_images_ceiling: 3000`) so the budget is never the limiter —
at the cost of proportionally more OCR time on deep crawls.
