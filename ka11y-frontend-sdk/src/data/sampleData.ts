import { AuditResult } from "@/types/audit";

/**
 * Empty initial state — shown before any audit has been run.
 * Real data is populated once an audit job completes.
 */
export const emptyAuditResult: AuditResult = {
  job_id: "",
  status: "pending",
  url: "",
  generated_at: "",
  total: 0,
  violations_count: 0,
  needs_review_count: 0,
  passes_count: 0,
  violations: [],
  needs_review: [],
  passes: [],
  warnings: [],
};