"use client";

import { useEffect, useRef, useState } from "react";

/** Reveals `items` in pages instead of all at once. Renders `pageSize` rows
 * up front; when the returned `sentinelRef` div scrolls into view, reveals
 * `pageSize` more. `resetKey` should change whenever the underlying list is
 * refiltered (e.g. a filter toggle) so the count restarts at `pageSize`. */
export function useInfiniteReveal<T>(items: T[], resetKey: unknown, pageSize = 20) {
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [prevResetKey, setPrevResetKey] = useState(resetKey);
  // Reset synchronously during render (not in an effect) when the filter
  // changes — the same pattern already used for re-syncing derived state
  // elsewhere in this app (see needs-review/page.tsx).
  if (prevResetKey !== resetKey) {
    setPrevResetKey(resetKey);
    setVisibleCount(pageSize);
  }

  const sentinelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisibleCount((c) => c + pageSize);
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [pageSize]);

  return {
    visibleItems: items.slice(0, visibleCount),
    visibleCount: Math.min(visibleCount, items.length),
    hasMore: visibleCount < items.length,
    sentinelRef,
  };
}
