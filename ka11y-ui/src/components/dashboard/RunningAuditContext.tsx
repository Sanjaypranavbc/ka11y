"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { redirectToLogin } from "@/lib/auth";
import type { WcagAuditResponse } from "@/lib/wcagAudit";
import {
  RUNNING_AUDIT_KEY,
  RUNNING_AUDIT_PATH,
  isActive,
  isLockedPath,
  readStoredRunningAudit,
  writeStoredRunningAudit,
  type JobStage,
  type RunningAudit,
  type StoredRunningAudit,
} from "@/lib/runningAudit";

// ── localStorage as an external store ──────────────────────────────────────
// The persisted job is read through useSyncExternalStore: the server (and
// the hydration pass) see null, the client sees the stored run right after
// hydration, and other tabs' writes arrive through the `storage` event.
const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedStored: StoredRunningAudit | null = null;

function subscribeStored(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === null || e.key === RUNNING_AUDIT_KEY) cb();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

function getStoredSnapshot(): StoredRunningAudit | null {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(RUNNING_AUDIT_KEY);
  } catch {
    raw = null;
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedStored = raw ? readStoredRunningAudit() : null;
  }
  return cachedStored;
}

function writeStored(value: StoredRunningAudit | null): void {
  writeStoredRunningAudit(value);
  listeners.forEach((cb) => cb());
}

const noopSubscribe = () => () => {};

const POLL_MS = 3000;
// The server (KA11Y_JOB_TIMEOUT_SECONDS, 30 min) decides when a job is
// actually dead; wait just past that rather than guessing per depth.
const TIMEOUT_MS = 1_860_000;
// Consecutive failed polls before giving up on an unreachable API, so a
// dead backend cannot keep the rest of the app locked forever.
const MAX_CONSECUTIVE_ERRORS = 20;

interface RunningAuditValue {
  /** The audit this browser started, or null. Terminal states stay here until `dismiss()`. */
  running: RunningAudit | null;
  /** True once localStorage has been read (before that nothing is locked). */
  hydrated: boolean;
  /** Other screens are locked while this is true. */
  isLocked: boolean;
  start(job: StoredRunningAudit): void;
  /** POST /cancel on the running job. Resolves false if the API refused. */
  cancel(): Promise<boolean>;
  /** Forget a finished (completed / failed / cancelled / unknown) run. */
  dismiss(): void;
}

const RunningAuditContext = createContext<RunningAuditValue | null>(null);

/**
 * Owns the run/poll loop for the audit started in this browser (see
 * lib/runningAudit.ts). Mounted at the root layout so the loop keeps going
 * while the user is on another tab or the admin console, and rehydrates from
 * localStorage after a refresh. Must sit inside AuditDataProvider: a
 * completed run's result is handed to it so the dashboard tabs update even
 * when the New Audit page was not mounted at the time.
 */
export function RunningAuditProvider({ children }: { children: ReactNode }) {
  const { setAuditData } = useAuditData();
  const stored = useSyncExternalStore(subscribeStored, getStoredSnapshot, () => null);
  const hydrated = useSyncExternalStore(noopSubscribe, () => true, () => false);
  // Live data for the run (stages, status) — null until the first poll or
  // start(). Terminal states stay here after the persisted entry is cleared.
  const [live, setRunning] = useState<RunningAudit | null>(null);
  const errorsRef = useRef(0);

  // The persisted entry wins when the live state is for another job (a run
  // started in a different tab) or absent (just refreshed): its status is
  // unknown until the first poll answers, so it counts as running and the
  // lock + progress bar are in place immediately.
  const running: RunningAudit | null =
    live && (!stored || live.jobId === stored.jobId)
      ? live
      : stored
        ? { ...stored, status: "running", stages: [], currentStage: null, error: null, confirmed: false }
        : null;

  const start = useCallback((job: StoredRunningAudit) => {
    errorsRef.current = 0;
    writeStored(job);
    setRunning({ ...job, status: "queued", stages: [], currentStage: null, error: null, confirmed: true });
  }, []);

  const dismiss = useCallback(() => {
    writeStored(null);
    setRunning(null);
  }, []);

  const jobId = running?.jobId ?? null;
  const active = isActive(running?.status);

  useEffect(() => {
    if (!jobId || !active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const startedAt = running?.startedAt ?? Date.now();
    const finish = (patch: Partial<RunningAudit>) => {
      writeStored(null);
      // Keep the terminal state visible even if the live state was still empty.
      setRunning((cur) =>
        cur && cur.jobId === jobId
          ? { ...cur, ...patch, confirmed: true }
          : ({ ...(running as RunningAudit), ...patch, confirmed: true } as RunningAudit),
      );
    };

    async function poll() {
      try {
        const res = await fetch(`/api/wcag-audit/${encodeURIComponent(jobId as string)}`, { cache: "no-store" });
        const data = await res.json().catch(() => null);
        if (cancelled) return;
        if (res.status === 401) {
          await redirectToLogin();
          return;
        }
        if (res.status === 404) {
          // The server no longer knows this job (restart with a wiped store):
          // nothing to wait for, so release the lock.
          finish({ status: "unknown", error: data?.error ?? null });
          return;
        }
        if (!res.ok) throw new Error(data?.error ?? `HTTP ${res.status}`);
        errorsRef.current = 0;

        const status = String(data.status ?? "running");
        const stages = (data.stages as JobStage[]) ?? [];
        const currentStage = (data.current_stage as string | null) ?? null;

        if (status === "completed") {
          const result = data.result as WcagAuditResponse | null;
          if (result) setAuditData(result, jobId);
          finish({ status: "completed", stages, currentStage, error: null });
          return;
        }
        if (status === "failed" || status === "cancelled") {
          finish({ status, stages, currentStage, error: (data.error as string | null) ?? null });
          return;
        }
        setRunning((cur) =>
          cur && cur.jobId === jobId
            ? { ...cur, status: status === "queued" || status === "pending" ? "queued" : "running", stages, currentStage, confirmed: true }
            : ({ ...(running as RunningAudit), status: "running", stages, currentStage, confirmed: true } as RunningAudit),
        );
        if (Date.now() - startedAt > TIMEOUT_MS) {
          finish({ status: "unknown", error: "still_running" });
          return;
        }
      } catch {
        if (cancelled) return;
        errorsRef.current += 1;
        if (errorsRef.current >= MAX_CONSECUTIVE_ERRORS) {
          finish({ status: "unknown", error: "unreachable" });
          return;
        }
      }
      timer = setTimeout(poll, POLL_MS);
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // `running` is intentionally not a dependency: the loop restarts only when
    // the job or its active/inactive state changes, not on every stage update.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, active, setAuditData]);

  const cancel = useCallback(async (): Promise<boolean> => {
    if (!jobId) return false;
    try {
      const res = await fetch(`/api/v1/combined/${encodeURIComponent(jobId)}/cancel`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (!res.ok) return false;
      writeStored(null);
      setRunning((cur) =>
        cur && cur.jobId === jobId
          ? { ...cur, status: "cancelled", error: null, confirmed: true }
          : ({ ...(running as RunningAudit), status: "cancelled", error: null, confirmed: true } as RunningAudit),
      );
      return true;
    } catch {
      return false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const value: RunningAuditValue = {
    running,
    hydrated,
    isLocked: hydrated && active,
    start,
    cancel,
    dismiss,
  };
  return <RunningAuditContext.Provider value={value}>{children}</RunningAuditContext.Provider>;
}

export function useRunningAudit(): RunningAuditValue {
  const ctx = useContext(RunningAuditContext);
  if (!ctx) throw new Error("useRunningAudit must be used within a RunningAuditProvider");
  return ctx;
}

/**
 * Route lock: while an audit started in this browser is running, every
 * dashboard tab except the running audit's screen and the whole admin
 * console redirect back to that screen (which shows why, via ?locked=1).
 * The sidebar disables the same links; this covers direct URL navigation.
 */
export function AuditLockGuard() {
  const { isLocked } = useRunningAudit();
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    if (isLocked && isLockedPath(pathname)) router.replace(`${RUNNING_AUDIT_PATH}?locked=1`);
  }, [isLocked, pathname, router]);
  return null;
}
