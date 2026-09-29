/**
 * Crawl depth rules shared by the New Audit form and the /api/wcag-audit
 * route: 0 = only the entered page, 1 = plus the pages it links to,
 * 2 = one level further. The Python API enforces the same range.
 *
 * Kept free of imports so `node --test` can load it directly.
 */

export const CRAWL_DEPTHS = [0, 1, 2] as const;
export type CrawlDepth = (typeof CRAWL_DEPTHS)[number];

export const MIN_CRAWL_DEPTH: CrawlDepth = 0;
export const MAX_CRAWL_DEPTH: CrawlDepth = 2;
export const DEFAULT_CRAWL_DEPTH: CrawlDepth = 0;

export const CRAWL_DEPTH_ERROR = "Crawl depth must be 0, 1 or 2.";

export function isCrawlDepth(value: unknown): value is CrawlDepth {
  return CRAWL_DEPTHS.includes(value as CrawlDepth);
}

/**
 * Depth from a request body: missing (undefined/null) means the default, any
 * other value must already be one of the allowed integers. Strings, decimals
 * and out-of-range numbers are rejected (null), never coerced or clamped.
 */
export function parseCrawlDepth(value: unknown): CrawlDepth | null {
  if (value === undefined || value === null) return DEFAULT_CRAWL_DEPTH;
  return isCrawlDepth(value) ? value : null;
}

/** One step up (+1) or down (-1), held inside 0–2. */
export function stepCrawlDepth(depth: CrawlDepth, delta: 1 | -1): CrawlDepth {
  const next = Math.min(MAX_CRAWL_DEPTH, Math.max(MIN_CRAWL_DEPTH, depth + delta));
  return next as CrawlDepth;
}

export function canIncreaseCrawlDepth(depth: CrawlDepth): boolean {
  return depth < MAX_CRAWL_DEPTH;
}

export function canDecreaseCrawlDepth(depth: CrawlDepth): boolean {
  return depth > MIN_CRAWL_DEPTH;
}

/**
 * The spinbutton's keyboard model: ArrowUp/ArrowDown step by one, Home/End
 * jump to the limits. Returns null for keys the stepper does not handle, so
 * Tab and everything else keep their default behaviour.
 */
export function crawlDepthForKey(depth: CrawlDepth, key: string): CrawlDepth | null {
  switch (key) {
    case "ArrowUp":
      return stepCrawlDepth(depth, 1);
    case "ArrowDown":
      return stepCrawlDepth(depth, -1);
    case "Home":
      return MIN_CRAWL_DEPTH;
    case "End":
      return MAX_CRAWL_DEPTH;
    default:
      return null;
  }
}
