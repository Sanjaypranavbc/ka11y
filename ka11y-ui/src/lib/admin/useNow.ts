"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A clock that ticks every `intervalMs`, exposed as an external store so the
 * server snapshot is `null` (no hydration mismatch) and consumers render a
 * neutral placeholder until the client clock resolves.
 */
export function useNow(intervalMs: number): number | null {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const id = window.setInterval(onChange, intervalMs);
      return () => window.clearInterval(id);
    },
    [intervalMs],
  );
  const getSnapshot = useCallback(() => Math.floor(Date.now() / intervalMs) * intervalMs, [intervalMs]);
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
