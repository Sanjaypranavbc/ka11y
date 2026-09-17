"use client";

import { useCallback, useEffect, useState } from "react";
import { useAdminConsole } from "@/components/admin/AdminShell";

export type ResourceState = "loading" | "ready" | "error";

/**
 * Loads one admin resource and refetches it, silently, every time the
 * console's live `version` moves (change event from the API) or when the
 * caller's `deps` change. The first load and explicit retries show the
 * loading state; background refreshes keep the current data on screen.
 */
export function useAdminResource<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const { version } = useAdminConsole();
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<ResourceState>("loading");
  const [attempt, setAttempt] = useState(0);

  // `loader` is intentionally not a dependency: callers pass inline closures
  // and list what they close over in `deps` instead.
  useEffect(() => {
    let cancelled = false;
    loader()
      .then((next) => {
        if (cancelled) return;
        setData(next);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus((s) => (s === "ready" ? s : "error"));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, attempt, ...deps]);

  const retry = useCallback(() => {
    setStatus("loading");
    setAttempt((n) => n + 1);
  }, []);

  return { data, status, retry };
}
