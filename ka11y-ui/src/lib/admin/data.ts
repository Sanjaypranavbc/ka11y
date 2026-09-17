/**
 * Admin console data model + sample dataset.
 *
 * The console is built against this typed model so the UI does not care where
 * the numbers come from. `loadAdminOverview()` is the single seam to swap for a
 * real fetch (e.g. GET /api/v1/audits/history + a stats endpoint) later; today
 * it resolves the sample data below, with timestamps anchored to "now" so the
 * relative-time labels behave like a live feed.
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
}

const MINUTE = 60_000;

function ago(now: number, ms: number): string {
  return new Date(now - ms).toISOString();
}

export function buildSampleOverview(now: number = Date.now()): AdminOverviewData {
  const jobs: AuditJob[] = [
    {
      id: "WC-8F21",
      targetHost: "kao.com",
      targetUrl: "https://kao.com",
      pages: 128,
      fails: 342,
      status: "completed",
      depth: 3,
      createdAt: ago(now, 31 * MINUTE),
      startedAt: ago(now, 31 * MINUTE),
      completedAt: ago(now, 0.2 * MINUTE),
      user: "admin@kao.com",
      organization: "Kao Corporation",
      conformance: "WCAG 2.2 AA",
      severity: { critical: 48, serious: 102, moderate: 124, minor: 68 },
      passed: 1286,
      needsReview: 18,
      pageList: [
        { url: "https://kao.com/", fails: 12, status: "failed" },
        { url: "https://kao.com/products", fails: 31, status: "failed" },
        { url: "https://kao.com/sustainability", fails: 0, status: "passed" },
        { url: "https://kao.com/careers", fails: 4, status: "needsReview" },
        { url: "https://kao.com/news/2026", fails: 27, status: "failed" },
      ],
      failList: [
        { id: "f1", criterion: "1.1.1", title: "Images must have alternative text", severity: "critical", occurrences: 48 },
        { id: "f2", criterion: "1.4.3", title: "Text must have sufficient colour contrast", severity: "serious", occurrences: 71 },
        { id: "f3", criterion: "2.4.4", title: "Links must have discernible text", severity: "serious", occurrences: 31 },
        { id: "f4", criterion: "1.3.1", title: "Form elements must have labels", severity: "moderate", occurrences: 124 },
        { id: "f5", criterion: "2.4.1", title: "Page must have a skip link", severity: "minor", occurrences: 68 },
      ],
      reports: [
        { id: "r1", format: "pdf", label: "Full report (PDF)", sizeBytes: 2_411_000, createdAt: ago(now, 0.1 * MINUTE), href: "#" },
        { id: "r2", format: "csv", label: "Findings export (CSV)", sizeBytes: 188_000, createdAt: ago(now, 0.15 * MINUTE), href: "#" },
        { id: "r3", format: "json", label: "Raw results (JSON)", sizeBytes: 1_204_000, createdAt: ago(now, 0.2 * MINUTE), href: "#" },
      ],
      logs: [
        { at: ago(now, 31 * MINUTE), level: "info", message: "Crawler worker initialized (depth=3, wcag_level=AA)" },
        { at: ago(now, 30 * MINUTE), level: "info", message: "Discovered 128 pages from sitemap and links" },
        { at: ago(now, 12 * MINUTE), level: "warn", message: "3 pages responded slowly (> 8s); retried once" },
        { at: ago(now, 0.3 * MINUTE), level: "info", message: "Audit completed: 342 fails, 18 needs review, 1,286 passed" },
        { at: ago(now, 0.1 * MINUTE), level: "info", message: "PDF report uploaded to S3" },
      ],
      events: [
        { code: "JOB_COMPLETED", at: ago(now, 0.2 * MINUTE), message: "Audit completed successfully" },
        { code: "REPORT_GENERATED", at: ago(now, 0.1 * MINUTE), message: "PDF report uploaded to S3" },
        { code: "JOB_STARTED", at: ago(now, 31 * MINUTE), message: "Crawler worker initialized" },
      ],
      s3Href: "#",
      reportHref: "#",
      csvHref: "#",
    },
    {
      id: "WC-8F20",
      targetHost: "example.jp",
      targetUrl: "https://example.jp",
      pages: 76,
      fails: 119,
      status: "running",
      depth: 2,
      createdAt: ago(now, 4 * MINUTE),
      startedAt: ago(now, 4 * MINUTE),
      completedAt: null,
      user: "yuki@kao.com",
      organization: "Kao Corporation",
      conformance: "WCAG 2.2 AA",
      severity: { critical: 14, serious: 37, moderate: 46, minor: 22 },
      passed: 611,
      needsReview: 9,
      pageList: [
        { url: "https://example.jp/", fails: 9, status: "failed" },
        { url: "https://example.jp/about", fails: 0, status: "passed" },
      ],
      failList: [
        { id: "f1", criterion: "1.1.1", title: "Images must have alternative text", severity: "critical", occurrences: 14 },
        { id: "f2", criterion: "1.4.3", title: "Text must have sufficient colour contrast", severity: "serious", occurrences: 37 },
      ],
      reports: [{ id: "r1", format: "csv", label: "Partial findings (CSV)", sizeBytes: 64_000, createdAt: ago(now, 0.5 * MINUTE), href: "#" }],
      logs: [
        { at: ago(now, 4 * MINUTE), level: "info", message: "Crawler worker initialized (depth=2, wcag_level=AA)" },
        { at: ago(now, 0.8 * MINUTE), level: "info", message: "Crawled 76 / 90 pages" },
      ],
      events: [
        { code: "REPORT_GENERATED", at: ago(now, 0.5 * MINUTE), message: "CSV report uploaded to S3" },
        { code: "JOB_STARTED", at: ago(now, 4 * MINUTE), message: "Crawler worker initialized" },
      ],
      s3Href: "#",
      reportHref: "#",
      csvHref: "#",
    },
    {
      id: "WC-8F19",
      targetHost: "brand-site.com",
      targetUrl: "https://brand-site.com",
      pages: 54,
      fails: 87,
      status: "needsReview",
      depth: 2,
      createdAt: ago(now, 21 * MINUTE),
      startedAt: ago(now, 21 * MINUTE),
      completedAt: ago(now, 9 * MINUTE),
      user: "mika@kao.com",
      organization: "Kao Corporation",
      conformance: "WCAG 2.2 AA",
      severity: { critical: 6, serious: 25, moderate: 38, minor: 18 },
      passed: 402,
      needsReview: 41,
      pageList: [
        { url: "https://brand-site.com/", fails: 3, status: "needsReview" },
        { url: "https://brand-site.com/campaign", fails: 22, status: "failed" },
      ],
      failList: [
        { id: "f1", criterion: "1.4.11", title: "Non-text contrast", severity: "serious", occurrences: 25 },
        { id: "f2", criterion: "2.5.8", title: "Target size (minimum)", severity: "moderate", occurrences: 38 },
      ],
      reports: [{ id: "r1", format: "pdf", label: "Full report (PDF)", sizeBytes: 1_020_000, createdAt: ago(now, 8 * MINUTE), href: "#" }],
      logs: [
        { at: ago(now, 21 * MINUTE), level: "info", message: "Crawler worker initialized (depth=2, wcag_level=AA)" },
        { at: ago(now, 9 * MINUTE), level: "warn", message: "41 findings need manual review" },
      ],
      events: [
        { code: "NEEDS_REVIEW", at: ago(now, 9 * MINUTE), message: "41 findings need manual review" },
        { code: "JOB_STARTED", at: ago(now, 21 * MINUTE), message: "Crawler worker initialized" },
      ],
      s3Href: "#",
      reportHref: "#",
      csvHref: "#",
    },
    {
      id: "WC-8F18",
      targetHost: "shop.com",
      targetUrl: "https://shop.com",
      pages: 0,
      fails: 0,
      status: "failed",
      depth: 1,
      createdAt: ago(now, 45 * MINUTE),
      startedAt: ago(now, 45 * MINUTE),
      completedAt: ago(now, 44 * MINUTE),
      user: "admin@kao.com",
      organization: "Kao Corporation",
      conformance: "WCAG 2.2 AA",
      severity: { critical: 0, serious: 0, moderate: 0, minor: 0 },
      passed: 0,
      needsReview: 0,
      pageList: [],
      failList: [],
      reports: [],
      logs: [
        { at: ago(now, 45 * MINUTE), level: "info", message: "Crawler worker initialized (depth=1, wcag_level=AA)" },
        { at: ago(now, 44 * MINUTE), level: "error", message: "Connection timeout after 30s; retrying (1/3)" },
        { at: ago(now, 2 * MINUTE), level: "error", message: "Connection timeout after 30s; retrying (2/3)" },
      ],
      events: [
        { code: "JOB_FAILED", at: ago(now, 44 * MINUTE), message: "Connection timeout" },
        { code: "JOB_STARTED", at: ago(now, 45 * MINUTE), message: "Crawler worker initialized" },
      ],
      s3Href: "#",
      reportHref: "#",
      csvHref: "#",
    },
    {
      id: "WC-8F17",
      targetHost: "corporate.io",
      targetUrl: "https://corporate.io",
      pages: 203,
      fails: 521,
      status: "completed",
      depth: 4,
      createdAt: ago(now, 139 * MINUTE),
      startedAt: ago(now, 139 * MINUTE),
      completedAt: ago(now, 119 * MINUTE),
      user: "kenji@kao.com",
      organization: "Kao Corporation",
      conformance: "WCAG 2.2 AA",
      severity: { critical: 77, serious: 160, moderate: 191, minor: 93 },
      passed: 2044,
      needsReview: 26,
      pageList: [
        { url: "https://corporate.io/", fails: 8, status: "failed" },
        { url: "https://corporate.io/investors", fails: 44, status: "failed" },
        { url: "https://corporate.io/contact", fails: 0, status: "passed" },
      ],
      failList: [
        { id: "f1", criterion: "4.1.2", title: "Name, role, value", severity: "critical", occurrences: 77 },
        { id: "f2", criterion: "1.3.1", title: "Info and relationships", severity: "moderate", occurrences: 191 },
      ],
      reports: [
        { id: "r1", format: "pdf", label: "Full report (PDF)", sizeBytes: 3_950_000, createdAt: ago(now, 118 * MINUTE), href: "#" },
        { id: "r2", format: "csv", label: "Findings export (CSV)", sizeBytes: 402_000, createdAt: ago(now, 118 * MINUTE), href: "#" },
      ],
      logs: [
        { at: ago(now, 139 * MINUTE), level: "info", message: "Crawler worker initialized (depth=4, wcag_level=AA)" },
        { at: ago(now, 119 * MINUTE), level: "info", message: "Audit completed: 521 fails, 26 needs review, 2,044 passed" },
      ],
      events: [
        { code: "JOB_COMPLETED", at: ago(now, 119 * MINUTE), message: "Audit completed successfully" },
        { code: "JOB_STARTED", at: ago(now, 139 * MINUTE), message: "Crawler worker initialized" },
      ],
      s3Href: "#",
      reportHref: "#",
      csvHref: "#",
    },
  ];

  return {
    generatedAt: new Date(now).toISOString(),
    currentUser: { name: "Pranav", email: "admin@kao.com", role: "Admin" },
    stats: {
      totalUsers: 248,
      totalUsersTrend: { value: "18", direction: "up" },
      totalAudits: 1842,
      totalAuditsTrend: { value: "12%", direction: "up" },
      totalFails: 42_774,
      totalFailsTrend: { value: "8%", direction: "up" },
      systemHealth: "healthy",
    },
    auditStatus: [
      { status: "completed", count: 1542 },
      { status: "running", count: 152 },
      { status: "failed", count: 87 },
      { status: "cancelled", count: 61 },
    ],
    severity: [
      { severity: "critical", count: 18_412 },
      { severity: "serious", count: 12_734 },
      { severity: "moderate", count: 7_641 },
      { severity: "minor", count: 3_987 },
    ],
    recentAudits: jobs,
    activity: [
      { id: "a1", kind: "auditCompleted", at: ago(now, 12_000), jobId: "WC-8F21", params: { pages: 128, fails: 342 }, important: true },
      { id: "a2", kind: "reportGenerated", at: ago(now, 31_000), jobId: "WC-8F20", params: { format: "CSV" }, important: true },
      { id: "a3", kind: "workerStarted", at: ago(now, 48_000), jobId: "WC-8F20", params: {}, important: false },
      { id: "a4", kind: "failedJob", at: ago(now, 2 * MINUTE), jobId: "WC-8F18", params: {}, important: true },
      { id: "a5", kind: "userLogin", at: ago(now, 5 * MINUTE), params: { email: "admin@kao.com", provider: "Google OAuth" }, important: false },
    ],
    notifications: [
      { id: "n1", title: "Audit WC-8F21 completed", at: ago(now, 12_000), read: false },
      { id: "n2", title: "Audit WC-8F18 failed: connection timeout", at: ago(now, 2 * MINUTE), read: false },
      { id: "n3", title: "41 findings on WC-8F19 need review", at: ago(now, 9 * MINUTE), read: true },
    ],
  };
}

/**
 * Single seam for real data. Resolves on the next tick so the UI already
 * exercises its loading state; replace the body with a fetch when the
 * endpoints exist.
 */
let sampleAnchor: number | null = null;

export async function loadAdminOverview(): Promise<AdminOverviewData> {
  // Anchor the sample timestamps once per session so "12s ago" keeps ageing
  // like real events would instead of resetting on every refresh.
  sampleAnchor ??= Date.now();
  return buildSampleOverview(sampleAnchor);
}

export const SEVERITY_ORDER: Severity[] = ["critical", "serious", "moderate", "minor"];
