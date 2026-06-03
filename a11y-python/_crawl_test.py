"""
Standalone crawler test harness.
Usage: poetry run python _crawl_test.py [url1 url2 ...]
Defaults to a curated list covering simple pages, SPAs, and WAF-protected sites.
"""
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path

SITES = [
    "https://example.com",
    "https://www.w3.org/WAI/demos/bad/before/home.html",
    "https://www.mozilla.org/en-US/",
]


async def run_one(url: str, out_root: Path):
    from a11y.crawler.universal_page import UniversalPageLoader
    from a11y.crawler.crawler import AsyncImageCrawler
    from a11y.crawler.forms_crawler import AsyncFormCrawler
    from a11y.crawler.interactive_crawler import InteractiveElementCrawler
    from a11y.crawler.media_crawler import AsyncMediaCrawler
    from a11y.crawler.moving_content_crawler import MovingContentCrawler
    from a11y.crawler.target_size_crawler import TargetSizeCrawler
    from a11y.crawler.text_spacing_crawler import AsyncTextSpacingCrawler

    domain = url.replace("https://", "").replace("http://", "").replace("/", "_")[:40]
    out_dir = out_root / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {"url": url, "errors": [], "warnings": [], "counts": {}, "timing": {}}
    t0 = time.monotonic()

    # ── 1. Universal snapshot ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  URL: {url}")
    print(f"{'='*60}")
    print("  [1] Universal snapshot...", end=" ", flush=True)
    snap_t = time.monotonic()
    try:
        snapshot = await asyncio.wait_for(
            UniversalPageLoader.load(url=url, output_dir=out_dir, record_har=True),
            timeout=60,
        )
        elapsed = time.monotonic() - snap_t
        print(f"OK ({elapsed:.1f}s)")
        result["counts"]["snapshot_forms"] = len(snapshot.forms)
        result["counts"]["snapshot_interactive"] = len(snapshot.interactive)
        result["counts"]["snapshot_media"] = len(snapshot.media)
        result["counts"]["snapshot_moving"] = len(snapshot.moving_content)
        result["counts"]["snapshot_text_spacing"] = len(snapshot.text_spacing)
        result["counts"]["snapshot_target_sizes"] = len(snapshot.target_sizes)
        result["warnings"].extend(snapshot.warnings)
        result["timing"]["snapshot"] = round(elapsed, 2)
        print(f"     forms={len(snapshot.forms)}  interactive={len(snapshot.interactive)}  "
              f"media={len(snapshot.media)}  moving={len(snapshot.moving_content)}")
        if snapshot.warnings:
            print(f"     ⚠ WARNINGS: {snapshot.warnings}")
    except Exception as e:
        elapsed = time.monotonic() - snap_t
        print(f"FAIL ({elapsed:.1f}s): {e}")
        result["errors"].append(f"snapshot: {e}")
        result["timing"]["snapshot"] = round(elapsed, 2)
        snapshot = None

    # ── 2. Image crawler (with 120s cap) ──────────────────────────────────
    print("  [2] Image crawler (cap=120s)...", end=" ", flush=True)
    img_t = time.monotonic()
    try:
        img_crawler = AsyncImageCrawler(base_url=url, max_depth=0)

        async def _crawl_and_save():
            await img_crawler.crawl_page()
            img_crawler.save_results()

        await asyncio.wait_for(_crawl_and_save(), timeout=120)
        elapsed = time.monotonic() - img_t
        print(f"OK ({elapsed:.1f}s)  images={len(img_crawler.images_data)}")
        result["counts"]["images"] = len(img_crawler.images_data)
        result["timing"]["image_crawler"] = round(elapsed, 2)
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - img_t
        print(f"TIMEOUT ({elapsed:.1f}s) — partial set: {len(img_crawler.images_data)} images")
        result["warnings"].append(f"image_crawler timeout after {elapsed:.0f}s — partial set")
        result["counts"]["images"] = len(img_crawler.images_data)
        result["timing"]["image_crawler"] = round(elapsed, 2)
    except Exception as e:
        elapsed = time.monotonic() - img_t
        print(f"FAIL ({elapsed:.1f}s): {e}")
        traceback.print_exc()
        result["errors"].append(f"image_crawler: {e}")
        result["timing"]["image_crawler"] = round(elapsed, 2)

    # ── 3. Snapshot-backed crawlers ────────────────────────────────────────
    if snapshot is not None:
        for name, klass, snap_field in [
            ("forms", AsyncFormCrawler, snapshot.forms),
            ("interactive", InteractiveElementCrawler, snapshot.interactive),
            ("media", AsyncMediaCrawler, snapshot.media),
            ("moving_content", MovingContentCrawler, snapshot.moving_content),
            ("target_size", TargetSizeCrawler, snapshot.target_sizes),
            ("text_spacing", AsyncTextSpacingCrawler, snapshot.text_spacing),
        ]:
            print(f"  [3:{name}] from_snapshot...", end=" ", flush=True)
            try:
                from_snap_methods = {
                    "forms": lambda: AsyncFormCrawler.from_snapshot(snap_field, url, str(out_dir)),
                    "interactive": lambda: InteractiveElementCrawler.from_snapshot(snap_field, url, str(out_dir)),
                    "media": lambda: AsyncMediaCrawler.from_snapshot(snap_field, url, str(out_dir)),
                    "moving_content": lambda: MovingContentCrawler.from_snapshot(snap_field, url, str(out_dir)),
                    "target_size": lambda: TargetSizeCrawler.from_snapshot(snap_field, url, str(out_dir)),
                    "text_spacing": lambda: AsyncTextSpacingCrawler.from_snapshot(snap_field, url, str(out_dir)),
                }
                inst = from_snap_methods[name]()
                count = len(inst.results)
                print(f"OK  items={count}")
                result["counts"][name] = count
            except Exception as e:
                print(f"FAIL: {e}")
                traceback.print_exc()
                result["errors"].append(f"{name}_from_snapshot: {e}")

    result["timing"]["total"] = round(time.monotonic() - t0, 2)

    # ── Summary ────────────────────────────────────────────────────────────
    status = "✅ PASS" if not result["errors"] else f"❌ FAIL ({len(result['errors'])} errors)"
    print(f"\n  {status}  total={result['timing']['total']}s")
    if result["errors"]:
        for e in result["errors"]:
            print(f"    ERROR: {e}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"    WARN:  {w}")

    (out_dir / "crawl_test_result.json").write_text(json.dumps(result, indent=2))
    return result


async def main():
    urls = sys.argv[1:] or SITES
    out_root = Path("/tmp/a11y_crawl_test")
    out_root.mkdir(exist_ok=True)

    all_results = []
    for url in urls:
        try:
            r = await run_one(url, out_root)
            all_results.append(r)
        except Exception as e:
            print(f"\nFATAL for {url}: {e}")
            traceback.print_exc()
            all_results.append({"url": url, "errors": [str(e)], "warnings": []})

    # Final summary table
    print(f"\n{'='*60}")
    print("  FINAL SUMMARY")
    print(f"{'='*60}")
    for r in all_results:
        status = "PASS" if not r["errors"] else "FAIL"
        nerr = len(r["errors"])
        nwrn = len(r["warnings"])
        total = r.get("timing", {}).get("total", "?")
        print(f"  [{status}]  {r['url'][:55]:55s}  t={total}s  err={nerr}  warn={nwrn}")


if __name__ == "__main__":
    asyncio.run(main())
