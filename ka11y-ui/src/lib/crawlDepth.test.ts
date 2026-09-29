import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  CRAWL_DEPTHS,
  DEFAULT_CRAWL_DEPTH,
  canDecreaseCrawlDepth,
  canIncreaseCrawlDepth,
  crawlDepthForKey,
  isCrawlDepth,
  parseCrawlDepth,
  stepCrawlDepth,
} from "./crawlDepth.ts";

describe("crawl depth", () => {
  it("allows only 0, 1 and 2 and defaults to 0", () => {
    assert.deepEqual([...CRAWL_DEPTHS], [0, 1, 2]);
    assert.equal(DEFAULT_CRAWL_DEPTH, 0);
  });

  it("increments by one and stops at 2", () => {
    assert.equal(stepCrawlDepth(0, 1), 1);
    assert.equal(stepCrawlDepth(1, 1), 2);
    assert.equal(stepCrawlDepth(2, 1), 2);
  });

  it("decrements by one and stops at 0", () => {
    assert.equal(stepCrawlDepth(2, -1), 1);
    assert.equal(stepCrawlDepth(1, -1), 0);
    assert.equal(stepCrawlDepth(0, -1), 0);
  });

  it("disables decrease at 0 (the default) and increase at 2", () => {
    assert.equal(canDecreaseCrawlDepth(DEFAULT_CRAWL_DEPTH), false);
    assert.equal(canIncreaseCrawlDepth(0), true);
    assert.equal(canDecreaseCrawlDepth(1), true);
    assert.equal(canIncreaseCrawlDepth(1), true);
    assert.equal(canIncreaseCrawlDepth(2), false);
    assert.equal(canDecreaseCrawlDepth(2), true);
  });

  it("handles ArrowUp/ArrowDown within 0-2 and Home/End at the limits", () => {
    assert.equal(crawlDepthForKey(0, "ArrowUp"), 1);
    assert.equal(crawlDepthForKey(2, "ArrowUp"), 2);
    assert.equal(crawlDepthForKey(1, "ArrowDown"), 0);
    assert.equal(crawlDepthForKey(0, "ArrowDown"), 0);
    assert.equal(crawlDepthForKey(1, "Home"), 0);
    assert.equal(crawlDepthForKey(1, "End"), 2);
  });

  it("ignores other keys, including typed digits, so focus and Tab still work", () => {
    for (const key of ["3", "1", "-", ".", "a", "Tab", "Enter", "PageUp"]) {
      assert.equal(crawlDepthForKey(1, key), null, key);
    }
  });

  it("treats a missing depth as 0 and keeps an explicit 0", () => {
    assert.equal(parseCrawlDepth(undefined), 0);
    assert.equal(parseCrawlDepth(null), 0);
    assert.equal(parseCrawlDepth(0), 0);
    assert.equal(parseCrawlDepth(2), 2);
  });

  it("rejects typed or pasted values outside 0-2 instead of coercing them", () => {
    for (const value of [3, -1, 1.5, "abc", "1", "", NaN, Infinity, true, [1], {}]) {
      assert.equal(parseCrawlDepth(value), null, String(value));
      assert.equal(isCrawlDepth(value), false, String(value));
    }
  });
});
