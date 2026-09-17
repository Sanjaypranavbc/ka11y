/**
 * Admin console data model.
 *
 * Everything here is served by the Python API (`GET /api/v1/admin/*`, admin
 * accounts only) from the audit engine's own tables — see
 * ka11y-python/ka11y/api/v1/admin.py. The fetchers live in ./api.ts; this file
 * only holds the shapes the console renders.
 */

export type AuditStatus = "completed" | "running" | "failed" | "cancelled" | "needsReview" | "queued";
export type Severity = "critical" | "serious" | "moderate" | "minor";
export type ActivityKind =
  | "auditCompleted"
  | "reportGenerated"
  | "workerStarted"
  | "failedJob"
  | "userLogin"
  | "needsReview"
  | "auditFailed";

export interface StatTrend {
  /** Absolute or percentage change, already formatted for display (e.g. "18" or "12%"). */
  value: string;
  direction: "up" | "down" | "flat";
}

export interface OverviewStats {
  totalUsers: number;
  totalUsersTrend: StatTrend;
  totalAudits: number;
  totalAuditsTrend: StatTrend;
  totalFails: number;
  totalFailsTrend: StatTrend;
  systemHealth: "healthy" | "degraded";
}

export interface AuditStatusSlice {
  status: Exclude<AuditStatus, "needsReview" | "queued">;
  count: number;
}

export interface SeverityCount {
  severity: Severity;
  count: number;
}

export interface AuditPage {
  url: string;
  fails: number;
  status: "passed" | "needsReview" | "failed";
}

export interface AuditFail {
  id: string;
  criterion: string;
  title: string;
  severity: Severity;
  occurrences: number;
}

export interface AuditReport {
  id: string;
  format: "pdf" | "csv" | "json";
  label: string;
  sizeBytes: number;
  createdAt: string;
  href: string;
}

export interface AuditLogLine {
  at: string;
  level: "info" | "warn" | "error";
  message: string;
}

export interface AuditEvent {
  code: "JOB_STARTED" | "JOB_COMPLETED" | "JOB_FAILED" | "REPORT_GENERATED" | "NEEDS_REVIEW";
  at: string;
  message: string;
}

export interface AuditJob {
  id: string;
  targetHost: string;
  targetUrl: string;
  pages: number;
  fails: number;
  status: AuditStatus;
  depth: number;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  user: string;
  organization: string;
  conformance: "WCAG 2.2 AA";
  severity: Record<Severity, number>;
  passed: number;
  needsReview: number;
  durationMs?: number | null;
  /** Filled by GET /admin/audits/{id}; empty in list responses. */
  pageList: AuditPage[];
  failList: AuditFail[];
  reports: AuditReport[];
  logs: AuditLogLine[];
  events: AuditEvent[];
  s3Href: string;
  reportHref: string;
  csvHref: string;
}

export interface ActivityItem {
  id: string;
  kind: ActivityKind;
  at: string;
  jobId?: string;
  /** Free-form parameters consumed by the localized description templates. */
  params: Record<string, string | number>;
  /** Meaningful events are announced to screen readers; low-level ones are not. */
  important: boolean;
}

export interface AdminNotification {
  id: string;
  title: string;
  at: string;
  read: boolean;
  href?: string;
}

export interface AdminUser {
  name: string;
  email: string;
  role: string;
}

export interface AdminOverviewData {
  generatedAt: string;
  stats: OverviewStats;
  auditStatus: AuditStatusSlice[];
  severity: SeverityCount[];
  recentAudits: AuditJob[];
  activity: ActivityItem[];
  notifications: AdminNotification[];
  currentUser: AdminUser;
  services?: { node: boolean; postgres: boolean };
}

export interface AdminAccount {
  id: string;
  name: string;
  email: string;
  organization: string;
  role: string;
  isAdmin: boolean;
  status: string;
  signInMethods: string[];
  audits: number;
  createdAt: string;
  lastLoginAt: string | null;
}

export interface AdminUsersData {
  users: AdminAccount[];
  allowListed: string[];
  adminEmails: string[];
}

export interface FailingCriterion {
  criterion: string;
  title: string;
  level: string;
  severity: Severity | "unknown";
  occurrences: number;
  needsReview: number;
  runs: number;
  pages: number;
}

export interface AdminReportRow extends AuditReport {
  jobId: string;
  targetUrl: string;
  targetHost: string;
  user: string;
  type: string;
  status: string;
  bucket: string;
  key: string;
}

export interface SystemEvent {
  id: string;
  at: string;
  source: "job" | "crash";
  level: "info" | "warn" | "error";
  code: string;
  message: string;
  jobId: string;
  targetHost: string;
  user: string;
  metadata: Record<string, unknown>;
}

export interface SettingsSection {
  key: "services" | "auth" | "engine" | "storage" | "email" | "ai";
  items: { label: string; value: string }[];
}

export interface AdminSettingsData {
  generatedAt: string;
  sections: SettingsSection[];
}

export const SEVERITY_ORDER: Severity[] = ["critical", "serious", "moderate", "minor"];
