"""
Run the Universal Page Crawler on any URL and save results.

Usage:
    conda activate work
    cd ka11y
    python run_universal_crawler.py https://example.com
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / "ka11y-python"))

from ka11y.crawler.universal_page import UniversalPageLoader
from ka11y.crawler.snapshot_normalizer import SnapshotNormalizer


async def main(url: str, max_depth: int = 0):
    safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(f"./test_output/{safe_name}_{timestamp}")
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  URL:       {url}")
    print(f"  Depth:     {max_depth}")
    print(f"  Output:    {out}")
    print(f"{'='*60}\n")

    # 1. Crawl
    print("[1/3] Crawling...")
    snapshot = await UniversalPageLoader.load(url=url, output_dir=out, max_depth=max_depth)

    # 2. Save raw
    print("[2/3] Saving raw snapshot...")
    UniversalPageLoader.save_snapshot(snapshot, out)

    # 3. Normalize
    print("[3/3] Normalizing...")
    normalized = SnapshotNormalizer.normalize(snapshot, output_dir=out)
    with open(out / "normalized.json", "w", encoding="utf-8") as f:
        json.dump(normalized.model_dump(), f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Pages crawled:   {normalized.pages_crawled}")
    print(f"  Forms:           {len(normalized.forms)}")
    print(f"  Interactive:     {len(normalized.interactive)}")
    print(f"  Target sizes:    {len(normalized.target_sizes)}")
    print(f"  Moving content:  {len(normalized.moving_content)}")
    print(f"  Media:           {len(normalized.media)}")
    print(f"  Text spacing:    {len(normalized.text_spacing)}")
    print(f"  Sensory:         {len(normalized.sensory)}")
    print(f"  Warnings:        {len(normalized.warnings)}")
    print(f"{'='*60}")
    print(f"\n  📁 Results in: {out}/")
    print(f"     • universal_snapshot_raw.json")
    print(f"     • normalized.json\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_universal_crawler.py <URL> [depth]")
        print("Example: python run_universal_crawler.py https://example.com 0")
        sys.exit(1)

    target = sys.argv[1]
    depth = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    asyncio.run(main(target, depth))
