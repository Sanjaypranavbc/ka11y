import type { WcagAuditResponse } from "@/lib/wcagAudit";

/** Stored verdict values: `violation` is a fail; `needs_review` re-opens. */
export type Verdict = "pass" | "violation" | "needs_review";

export interface VerdictResponse {
  job_id: string;
  finding_id: string;
  status: Verdict;
  reviewed: boolean;
  verdict_source: "manual" | "engine";
  review_status: "pass" | "violation" | null;
  review_message: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
}

/**
 * Persist a manual verdict for one needs_review finding
 * (`POST /api/v1/combined/{jobId}/findings/{findingId}/review`, proxied
 * same-origin by next.config.ts). The reviewer is the signed-in user; the
 * server derives it, so nothing identifying is sent from here.
 */
export async function submitVerdict(
  jobId: string,
  findingId: string,
  status: Verdict,
  note?: string,
): Promise<VerdictResponse> {
  const res = await fetch(
    `/api/v1/combined/${encodeURIComponent(jobId)}/findings/${encodeURIComponent(findingId)}/review`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(note ? { status, note } : { status }),
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || data?.error || `Verdict was not saved (HTTP ${res.status})`);
  }
  return (await res.json()) as VerdictResponse;
}

/** Re-read the report so every dashboard page sees the verdict applied
 * (the item moves to Fail or Passes with its review note). */
export async function refetchAudit(jobId: string): Promise<WcagAuditResponse | null> {
  const res = await fetch(`/api/wcag-audit/${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!res.ok) return null;
  const data = await res.json().catch(() => null);
  return (data?.result as WcagAuditResponse | undefined) ?? null;
}
