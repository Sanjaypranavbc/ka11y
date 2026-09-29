/**
 * Shared model of "the audit this browser is running".
 *
 * The run/poll loop lives in RunningAuditContext (mounted at the root
 * layout), not in the New Audit page, so it survives navigation to other
 * dashboard tabs or the admin console. The job id is persisted in
 * localStorage so a full refresh — or a new tab of the same browser — picks
 * the run back up by asking the API for its current status.
 */

export type RunningStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "unknown";

export interface JobStage {
  name: string;
  status: string;
  findings_count?: number;
}

export interface RunningAudit {
  jobId: string;
  url: string;
  depth: number;
  email: string;
  /** ms since epoch when the run was submitted from this browser. */
  startedAt: number;
  status: RunningStatus;
  stages: JobStage[];
  currentStage: string | null;
  error: string | null;
  /** False for the placeholder rebuilt from localStorage before the first
   * poll answers; true once start() or a poll response set the status. */
  confirmed: boolean;
}

/** The subset persisted across navigation / refresh. */
export interface StoredRunningAudit {
  jobId: string;
  url: string;
  depth: number;
  email: string;
  startedAt: number;
}

export const RUNNING_AUDIT_KEY = "kao:running-audit";
export const RUNNING_AUDIT_PATH = "/dashboard/new-audit";

export function isActive(status: RunningStatus | null | undefined): boolean {
  return status === "queued" || status === "running";
}

/**
 * Routes that are locked while an audit runs: every dashboard tab except
 * the running audit's own screen, and the whole admin console. Login,
 * register and API routes stay reachable so the user can never be trapped.
 */
export function isLockedPath(pathname: string): boolean {
  if (pathname.startsWith("/admin")) return true;
  if (pathname.startsWith("/dashboard")) return pathname !== RUNNING_AUDIT_PATH;
  return false;
}

// Mirrors ka11y-python/ka11y/api/v1/combined/constants.py STAGE_WEIGHTS —
// the only two stages the backend actually tracks lifecycle for.
const STAGE_WEIGHTS: Record<string, number> = { image_audit: 62, media_audit: 38 };
const STAGE_WEIGHT_TOTAL = Object.values(STAGE_WEIGHTS).reduce((a, b) => a + b, 0);

/**
 * Real progress from the backend's own stage lifecycle (poll response), not
 * a local timer. A stage only counts once the API reports it completed or
 * errored; the final jump to 100 is gated on job status "completed" so
 * post-stage report building is not shown as done early.
 */
export function computeRealProgress(stages: JobStage[], jobStatus: string | null): number {
  if (jobStatus === "completed") return 100;
  const done = stages.reduce((sum, s) => {
    if (s.status === "completed" || s.status === "error") return sum + (STAGE_WEIGHTS[s.name] ?? 0);
    return sum;
  }, 0);
  return Math.min(95, Math.round((done / STAGE_WEIGHT_TOTAL) * 100));
}

export function readStoredRunningAudit(): StoredRunningAudit | null {
  try {
    const raw = localStorage.getItem(RUNNING_AUDIT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredRunningAudit>;
    if (!parsed || typeof parsed.jobId !== "string" || !parsed.jobId) return null;
    return {
      jobId: parsed.jobId,
      url: typeof parsed.url === "string" ? parsed.url : "",
      depth: typeof parsed.depth === "number" ? parsed.depth : 0,
      email: typeof parsed.email === "string" ? parsed.email : "",
      startedAt: typeof parsed.startedAt === "number" ? parsed.startedAt : Date.now(),
    };
  } catch {
    return null;
  }
}

export function writeStoredRunningAudit(value: StoredRunningAudit | null): void {
  try {
    if (value) localStorage.setItem(RUNNING_AUDIT_KEY, JSON.stringify(value));
    else localStorage.removeItem(RUNNING_AUDIT_KEY);
  } catch {
    // localStorage unavailable: the run still works for this page's lifetime.
  }
}
