/**
 * Fetchers for the admin console. All paths go through the `/api/v1/admin/*`
 * rewrite in next.config.ts, so the browser talks to its own origin and the
 * session cookie is sent automatically. A 401 ends the session and returns
 * to /login; a 403 means the account is not on KA11Y_ADMIN_EMAILS.
 */

import { redirectToLogin } from "@/lib/auth";
import type { AdminOverviewData, AuditJob, ExportFormat } from "@/lib/admin/data";

const BASE = "/api/v1/admin";

export class AdminApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function adminFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "same-origin", cache: "no-store" });
  if (res.status === 401) {
    await redirectToLogin("session_expired");
    throw new AdminApiError(401, "session expired");
  }
  if (!res.ok) throw new AdminApiError(res.status, `${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const loadAdminOverview = () => adminFetch<AdminOverviewData>("/overview");
export const loadAuditDetail = (jobId: string) => adminFetch<AuditJob>(`/audits/${encodeURIComponent(jobId)}`);
export const loadAudits = (opts: { limit?: number; offset?: number; status?: string; q?: string } = {}) => {
  const params = new URLSearchParams();
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  if (opts.status) params.set("status", opts.status);
  if (opts.q) params.set("q", opts.q);
  const qs = params.toString();
  return adminFetch<{ jobs: AuditJob[] }>(`/audits${qs ? `?${qs}` : ""}`);
};

/** Download link for one audit's report; the server builds the file on demand. */
export const exportAuditHref = (jobId: string, format: ExportFormat) =>
  `${BASE}/audits/${encodeURIComponent(jobId)}/export?format=${format}`;

/**
 * Live change feed. The API emits `refresh` whenever a job, log line,
 * report, session or crash record changes (2 s granularity). Returns an
 * unsubscribe function. `onState` reports whether the stream is connected so
 * the UI can fall back to interval polling while it is not.
 */
export function subscribeAdminEvents(
  onRefresh: () => void,
  onState: (connected: boolean) => void,
): () => void {
  if (typeof window === "undefined" || typeof EventSource === "undefined") {
    onState(false);
    return () => {};
  }
  const es = new EventSource(`${BASE}/events`, { withCredentials: true });
  es.addEventListener("open", () => onState(true));
  es.addEventListener("refresh", () => onRefresh());
  es.addEventListener("error", () => onState(false)); // EventSource retries on its own
  return () => es.close();
}
