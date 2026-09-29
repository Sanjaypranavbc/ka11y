"use client";

import type { KeyboardEvent } from "react";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import {
  MAX_CRAWL_DEPTH,
  MIN_CRAWL_DEPTH,
  canDecreaseCrawlDepth,
  canIncreaseCrawlDepth,
  crawlDepthForKey,
  stepCrawlDepth,
  type CrawlDepth,
} from "@/lib/crawlDepth";

interface CrawlDepthStepperProps {
  value: CrawlDepth;
  onChange: (depth: CrawlDepth) => void;
}

const STEP_BUTTON =
  "flex h-5 w-6 items-center justify-center text-gray-60 hover:text-gray-100 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:text-gray-60";

/**
 * Crawl depth picker limited to 0–2. The value is not an <input>, so nothing
 * can be typed or pasted and the mouse wheel cannot change it; it follows the
 * WAI-ARIA spinbutton pattern (one tab stop, ArrowUp/ArrowDown step, Home/End
 * jump to the limits). The chevrons are pointer shortcuts for the same steps
 * and are disabled at each limit.
 */
export function CrawlDepthStepper({ value, onChange }: CrawlDepthStepperProps) {
  const { t } = useLanguage();

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next = crawlDepthForKey(value, event.key);
    if (next === null) return;
    // Arrow/Home/End would otherwise scroll the page.
    event.preventDefault();
    if (next !== value) onChange(next);
  }

  return (
    <div className="flex h-12 items-center justify-between rounded-[8px] border border-gray-40 bg-white px-4 focus-within:border-brand-teal">
      <div
        role="spinbutton"
        tabIndex={0}
        aria-label={t.newAudit.crawlDepthAria}
        aria-valuemin={MIN_CRAWL_DEPTH}
        aria-valuemax={MAX_CRAWL_DEPTH}
        aria-valuenow={value}
        onKeyDown={handleKeyDown}
        className="flex h-full flex-1 items-center text-[16px] leading-6 text-gray-100 focus:outline-none"
      >
        {value}
      </div>
      <div className="flex flex-col gap-1">
        {/* Out of the tab order: the spinbutton's arrow keys do the same. */}
        <button
          type="button"
          tabIndex={-1}
          onClick={() => onChange(stepCrawlDepth(value, 1))}
          disabled={!canIncreaseCrawlDepth(value)}
          aria-label={t.newAudit.increaseDepth}
          className={STEP_BUTTON}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M4 10L8 6L12 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <button
          type="button"
          tabIndex={-1}
          onClick={() => onChange(stepCrawlDepth(value, -1))}
          disabled={!canDecreaseCrawlDepth(value)}
          aria-label={t.newAudit.decreaseDepth}
          className={STEP_BUTTON}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M4 6L8 10L12 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
