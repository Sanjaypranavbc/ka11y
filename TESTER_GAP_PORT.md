# Tester Branch — Gap Port from `pranav-v2`

**Date:** 2026-07-23  
**Branch:** `tester`  
**File Modified:** `ka11y-python/ka11y/crawler/optimized/engine.py`  
**Analyst / Implementer:** Antigravity

---

## Background

The `tester` branch replaced `pranav-v2`'s `AsyncImageCrawler` (`crawler/crawler.py`, 1 179 lines) with a new `optimized/engine.py` (2 200+ lines). The overlay screenshot logic was correctly ported (`OVERLAY_CONTAINER_JS` ≡ `classifier.get_visual_container()`), but three critical behaviours from `pranav-v2` were missing, causing images inside carousels/reels and lazy-loaded images to not be captured.

---

## Gaps Identified

### Gap 1 — Carousel / Reel Click Passes

| | pranav-v2 | tester (before) |
|---|---|---|
| **Where** | `AsyncImageCrawler._reveal_hidden_images()` | ❌ absent |
| **What** | Playwright Python loop clicks tabs, accordions, dropdowns, modals, carousel "next" buttons, load-more buttons before image scan | `SCROLL_JS` only scrolled — no interactive clicks |
| **Effect of missing** | Carousel slide 2–N images never load their `src`; EXTRACT_JS sees empty/placeholder src | Images from reels/carousels not captured |

**pranav-v2 selector groups (exact):**

```python
groups = {
    "tabs":       '[role="tab"], .tab, [data-toggle="tab"], .nav-link',
    "accordions": '[data-toggle="collapse"], .accordion-toggle, .accordion-button, details summary',
    "dropdowns":  '[data-toggle="dropdown"], .dropdown-toggle',
    "modals":     '[data-toggle="modal"]',
    "carousels":  '.carousel-control-next, .slick-next, [data-slide="next"]',
    "load_more":  ".load-more, [data-load-more]",
}
# Click cap: 8 per group | Wait after each click: 400 ms
# Deduplicate by outerHTML.slice(0, 100)
```

---

### Gap 2 — IntersectionObserver / `lazyload` Event Dispatch

| | pranav-v2 | tester (before) |
|---|---|---|
| **Where** | End of `AsyncImageCrawler._trigger_lazy_loading()` | ❌ absent |
| **What** | Creates one `IntersectionObserver` per `img[data-src]` / `img[data-lazy-src]` / `img[data-original]` element, fires `lazyload` event on each, waits 1 000 ms | No event dispatch after scroll |
| **Effect of missing** | Lazy-load libraries (lazysizes, LazyLoad.js, etc.) never swap `data-src → src` | Images remain blank placeholders at extraction time |

**pranav-v2 code (exact):**

```python
await page.evaluate("""() => {
    const imgs = document.querySelectorAll("img[data-src],img[data-lazy-src],img[data-original]");
    imgs.forEach(img => {
        const obs = new IntersectionObserver(entries => {
            entries.forEach(e => e.target.dispatchEvent(new Event("lazyload")));
            obs.disconnect();
        });
        obs.observe(img);
    });
}""")
await page.wait_for_timeout(1000)
```

---

### Gap 3 — Full `_resolve_src` Fallback Chain

| | pranav-v2 | tester (before) |
|---|---|---|
| **Where** | `AsyncImageCrawler._resolve_src()` | `EXTRACT_JS` img block, line 1429 |
| **What** | Walks 8 attributes in priority order; skips `data:` URIs at every step | Single expression `el.currentSrc \|\| attr(el, "src")` |
| **Effect of missing** | Any image whose primary `src` is a 1×1 GIF placeholder but carries a real URL in `data-src` / `data-lazy-src` etc. gets recorded with a null/placeholder src | Image not downloaded / screenshotted |

**pranav-v2 priority order (exact):**

```
src / currentSrc
  → data-src
  → data-lazy-src
  → data-original
  → data-lazy
  → data-url
  → srcset        (first candidate, comma-split → whitespace-split → [0])
  → data-srcset   (same parsing)
```

`data:` URIs skipped at every step.

---

## Changes Made

**Only one file was modified:** `ka11y-python/ka11y/crawler/optimized/engine.py`

### Edit 1 — New `REVEAL_JS` constant (after `SCROLL_JS`)

Added a pure-JS async block that replicates pranav-v2's `_reveal_hidden_images()` + the post-scroll IntersectionObserver block from `_trigger_lazy_loading()`:

```js
// REVEAL_JS (new constant, ~50 lines)
async () => {
    const pause = ms => new Promise(r => setTimeout(r, ms));

    // Gap 1: click carousel / tab / accordion / modal controls
    const groups = {
        tabs:       '[role="tab"], .tab, [data-toggle="tab"], .nav-link',
        accordions: '[data-toggle="collapse"], .accordion-toggle, .accordion-button, details summary',
        dropdowns:  '[data-toggle="dropdown"], .dropdown-toggle',
        modals:     '[data-toggle="modal"]',
        carousels:  '.carousel-control-next, .slick-next, [data-slide="next"]',
        load_more:  '.load-more, [data-load-more]',
    };
    for (const [name, sel] of Object.entries(groups)) {
        let els;
        try { els = Array.from(document.querySelectorAll(sel)); } catch { continue; }
        const seen = new Map();
        for (const el of els) {
            const key = (el.outerHTML || "").slice(0, 100);
            if (!seen.has(key)) seen.set(key, el);
        }
        for (const el of Array.from(seen.values()).slice(0, 8)) {
            try {
                const cs = window.getComputedStyle(el);
                const r  = el.getBoundingClientRect();
                const visible = cs.display !== "none" && cs.visibility !== "hidden"
                    && r.width > 0 && r.height > 0;
                if (!visible) continue;
                el.click();
                await pause(400);   // matches pranav-v2's 400 ms per click
            } catch {}
        }
    }

    // Gap 2: IntersectionObserver + lazyload event dispatch
    const lazyImgs = document.querySelectorAll(
        'img[data-src], img[data-lazy-src], img[data-original]'
    );
    lazyImgs.forEach(img => {
        const obs = new IntersectionObserver(entries => {
            entries.forEach(e => e.target.dispatchEvent(new Event('lazyload')));
            obs.disconnect();
        });
        obs.observe(img);
    });
    await pause(1000);  // matches pranav-v2's 1 000 ms wait
}
```

---

### Edit 2 — Call `REVEAL_JS` in `_attempt_page()`

```diff
         await page.evaluate(SCROLL_JS)
         await page.wait_for_timeout(400)

+        # Gap 1+2: reveal hidden images (carousel clicks + lazyload dispatch).
+        await page.evaluate(REVEAL_JS)
+        await page.wait_for_timeout(500)

         extraction = await page.evaluate(EXTRACT_JS, VIDEO_EMBED_HOSTS)
```

The 500 ms settle mirrors `page.wait_for_timeout(500)` that pranav-v2 calls in `crawl_page()` after both `_trigger_lazy_loading()` and `_reveal_hidden_images()` complete.

---

### Edit 3 — `_resolveSrc` helper in `EXTRACT_JS` img block

```diff
-        const srcAbs = absUrl(el.currentSrc || attr(el, "src") || "");
+        // Gap 3: full src fallback chain, ported from pranav-v2 _resolve_src().
+        const _resolveSrc = (el) => {
+            for (const a of ["src", "data-src", "data-lazy-src",
+                              "data-original", "data-lazy", "data-url"]) {
+                const v = el.currentSrc && a === "src"
+                    ? el.currentSrc   // prefer browser-resolved currentSrc for "src"
+                    : el.getAttribute(a);
+                if (v && !v.startsWith("data:")) return absUrl(v);
+            }
+            for (const a of ["srcset", "data-srcset"]) {
+                const v = el.getAttribute(a);
+                if (v) {
+                    const first = v.trim().split(",")[0].trim().split(/\s+/)[0];
+                    if (first && !first.startsWith("data:")) return absUrl(first);
+                }
+            }
+            return null;
+        };
+        const srcAbs = _resolveSrc(el);
```

---

## Gap Closure Status

| Gap | Status | Parity Notes |
|---|---|---|
| **1. Carousel/reel click passes** | ✅ Closed | Exact selector groups, dedup key, 8-per-group cap, 400 ms wait |
| **2. IntersectionObserver / lazyload dispatch** | ✅ Closed | Exact selector list, per-element observer, `lazyload` event name, 1 000 ms wait |
| **3. `_resolve_src` fallback chain** | ✅ Closed | Exact attribute priority order, `data:` skip at every step, srcset first-candidate parsing |

---

## One Structural Deviation (minor, unavoidable)

pranav-v2's `_reveal_hidden_images()` uses Playwright's **async Python** `await el.is_visible(timeout=800)` for the click guard. `REVEAL_JS` runs inside `page.evaluate()` — a synchronous JS context — so Playwright's async API is unavailable. The equivalent guard uses `getComputedStyle(el)` + `getBoundingClientRect()` checks, which are **functionally identical** for detecting rendered/hidden elements.

---

## Pipeline Sequence (after port)

```
Playwright loads page
  └─ reject_cookies() (if enabled)
  └─ page.evaluate(SCROLL_JS)          ← incremental scroll, lazy-src trigger
  └─ page.wait_for_timeout(400)
  └─ page.evaluate(REVEAL_JS)          ← [NEW] carousel clicks + lazyload dispatch
  └─ page.wait_for_timeout(500)        ← [NEW] settle
  └─ page.evaluate(EXTRACT_JS)         ← DOM walk, now with _resolveSrc fallback
  └─ _capture_assets()                 ← OVERLAY_CONTAINER_JS screenshot or download
  └─ adapter.build_image_data()        ← ImageData records for OCR / audit stages
```

---

## Files Changed

| File | Change |
|---|---|
| `ka11y-python/ka11y/crawler/optimized/engine.py` | +`REVEAL_JS` constant (~52 lines); +2 `await` calls in `_attempt_page()`; `_resolveSrc` helper in `EXTRACT_JS` img block (~18 lines) |

No other files were modified.
