export type WcagLevel = "A" | "AA" | "AAA";

export type FindingStatus = "pass" | "fail" | "incomplete" | "not_applicable" | string;
export type CriterionStatus =
  | "pass"
  | "fail"
  | "needs_review"
  | "not_applicable"
  | "not_checked"
  | "manual_only"
  | string;

export interface WcagElementRef {
  html: string | null;
  selector: string | null;
  target: string[] | null;
  bounding_box: unknown;
  detail: string | null;
}

export interface WcagFinding {
  ruleId: string;
  status: FindingStatus;
  impact: string | null;
  reason: string;
  helpUrl: string;
  elements: WcagElementRef[];
}

export interface WcagCriterion {
  sc: string;
  name: string;
  level: WcagLevel;
  principle: string;
  status: CriterionStatus;
  reason?: string;
  sources: string[];
  findings: WcagFinding[];
}

// Matches ka11y-python/ka11y/api/v1/combined/report.py _build_report()'s
// summary block — the shape the combined-audit backend actually returns.
export interface WcagStatusCounts {
  violations: number;
  needs_review: number;
  passes: number;
}

export interface WcagAuditSummary {
  total_findings: number;
  violations: number;
  needs_review: number;
  passes: number;
  manual_review_required?: number;
  score: number | null;
  by_severity?: Record<string, number>;
  by_level?: Record<string, WcagStatusCounts>;
  by_wcag_sc?: Record<string, WcagStatusCounts>;
  by_source?: Record<string, WcagStatusCounts>;
  by_page?: Record<string, WcagStatusCounts>;
  page_count?: number;
}

export interface WcagReportPage {
  page_url: string;
  summary: {
    total_findings: number;
    violations: number;
    needs_review: number;
    passes: number;
    score: number | null;
  };
  violations: unknown[];
  needs_review: unknown[];
  passes: unknown[];
}

// Matches report.py _build_report()'s `pages_scanned` — every page either
// engine's crawl visited, success or failed, independent of whether it
// produced any findings (unlike `pages`, which only lists pages with data).
export interface WcagPageScan {
  page_url: string;
  status: "success" | "failed";
  violations: number;
  needs_review: number;
  passes: number;
  error: string | null;
}

export interface WcagAuditResponse {
  url: string;
  wcagVersion?: string;
  analyzedAt?: string;
  summary?: WcagAuditSummary;
  // node-shape findings (fallback path in the derivers)
  criteria?: WcagCriterion[];
  // combined-audit flat findings arrays (primary path in the derivers)
  violations?: unknown[];
  passes?: unknown[];
  needs_review?: unknown[];
  pages?: WcagReportPage[];
  pages_scanned?: WcagPageScan[];
}

/* ─── Row shapes consumed by the Violations / Needs Review tables ─── */

export interface ViolationRow {
  id: string;
  title: string;
  description: string;
  sc: string;
  criterion: string;
  level: WcagLevel;
  tag: string;
  elementTitle: string;
  elementFile: string;
  elementOcr: string;
  imageUrls: string[];
  fixGuide: string;
  pageUrl: string;
}

export type ReviewStatus = "pass" | "violation" | "pending";

export interface ReviewRow {
  id: string;
  status: ReviewStatus;
  reasonTitle: string;
  reasonDescription: string;
  sc: string;
  criterion: string;
  level: WcagLevel;
  tag: string;
  elementFilename: string;
  imageUrls: string[];
  foreground: string;
  background: string;
  ocrText: string;
  helpUrl: string;
  pageUrl: string;
}

export interface PassRow {
  id: string;
  reasonTitle: string;
  reasonDescription: string;
  sc: string;
  criterion: string;
  level: WcagLevel;
  tag: string;
  elementFilename: string;
  imageUrls: string[];
  foreground: string;
  background: string;
  ocrText: string;
  helpUrl: string;
  pageUrl: string;
}

/* ─── Helpers ─── */

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function extractTag(html: string | null | undefined): string {
  if (!html) return "—";
  const match = html.match(/^<\s*([a-zA-Z0-9-]+)/);
  return match ? match[1] : "—";
}

function truncateHtml(html: string | null | undefined, max = 90): string {
  if (!html) return "—";
  const clean = html.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

/** Turn a captured-crop path/asset ref into a browser-loadable URL.
 * Accepts an /api/v1/assets/{id} path (same-origin, proxied to Python by
 * next.config) or an absolute http(s) URL. A bare filesystem path is NOT
 * loadable and is dropped. */
function assetToUrl(u: unknown): string | null {
  if (typeof u !== "string") return null;
  const s = u.trim();
  if (!s) return null;
  if (/^https?:\/\//i.test(s)) return s;
  if (s.startsWith("/api/")) return s;
  return null;
}

/** Resolve an HTML <img src> (which may be absolute, root-relative, or
 * page-relative) against the page it was found on, so it points at the real
 * origin instead of the dashboard's. */
function htmlSrcToUrl(u: unknown, pageUrl: unknown): string | null {
  if (typeof u !== "string") return null;
  const s = u.trim();
  if (!s || s.startsWith("data:")) return s || null;
  if (/^https?:\/\//i.test(s)) return s;
  if (typeof pageUrl === "string" && pageUrl) {
    try {
      return new URL(s, pageUrl).href;
    } catch {
      /* fall through */
    }
  }
  return null;
}

/** Ordered list of browser-loadable image URLs for a finding's element:
 * the captured crop (asset) first, then the original image parsed from the
 * element HTML. ElementImage tries them in order and only shows the neutral
 * box when every candidate fails. */
function pickImageUrls(el: any): string[] {
  if (!el) return [];
  const out: string[] = [];
  const add = (u: string | null) => {
    if (u && !out.includes(u)) out.push(u);
  };

  // 1. Captured crop / registered asset (most accurate for the finding).
  add(assetToUrl(el.image_src));
  add(assetToUrl(el.image_url));
  add(assetToUrl(el.asset_url));

  // 2. Original image from the element HTML, resolved to an absolute URL.
  // Lazy-loaded <img>s often leave src empty and carry the real URL in
  // srcset / data-src / data-* — try each so those still render.
  const html: string | undefined = el.html;
  if (html) {
    // Direct src / common lazy-load attributes.
    for (const attr of ["src", "data-src", "data-original", "data-lazy-src"]) {
      const m = html.match(
        new RegExp(`<img[^>]*\\s${attr}\\s*=\\s*["']([^"']+)["']`, "i"),
      );
      if (m) add(htmlSrcToUrl(m[1], el.page_url));
    }
    // srcset / data-srcset: take the first URL of the candidate list.
    const ss = html.match(/\s(?:data-)?srcset\s*=\s*["']([^"']+)["']/i);
    if (ss) {
      const first = ss[1].split(",")[0]?.trim().split(/\s+/)[0];
      add(htmlSrcToUrl(first, el.page_url));
    }
    // CSS background-image: url(...) on the element.
    const bg = html.match(/background-image\s*:\s*url\(\s*["']?([^"')]+)["']?\s*\)/i);
    if (bg) add(htmlSrcToUrl(bg[1], el.page_url));
  }
  add(htmlSrcToUrl(el.src, el.page_url));

  return out;
}

function extractColors(text: string): { foreground?: string; background?: string } {
  const fg = text.match(/foreground(?:\s*color)?[:\s]+(#[0-9a-fA-F]{3,8})/i);
  const bg = text.match(/background(?:\s*color)?[:\s]+(#[0-9a-fA-F]{3,8})/i);
  return { foreground: fg?.[1], background: bg?.[1] };
}

/* ─── Adapters: WCAG API response → page row shapes ───
 * Driven entirely by response fields — no site-specific assumptions —
 * so any analysed URL's response adapts the same way. */

export function toViolationRows(data: any): ViolationRow[] {
  const rows: ViolationRow[] = [];
  let rowIndex = 0;

  if (data.violations) {
    for (const finding of data.violations) {
      const el = finding.element || {};
      const selector = el.selector || el.target;
      const selectorStr = Array.isArray(selector) ? selector.join(" ") : (selector || "—");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        title: finding.reason_code || finding.rule_id || "Violation",
        description: finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion_name || finding.reason_code || ""),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementTitle: selectorStr,
        elementFile: finding.rule_id || finding.ruleId || "",
        elementOcr: truncateHtml(el.html),
        imageUrls: pickImageUrls(el),
        fixGuide: finding.helpUrl || "",
        pageUrl: el.page_url || data.url || "",
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "fail") continue;

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            title: finding.reason,
            description: finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.principle,
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementTitle: el?.selector ?? "—",
            elementFile: finding.ruleId,
            elementOcr: truncateHtml(el?.html),
            imageUrls: pickImageUrls(el),
            fixGuide: finding.helpUrl,
            pageUrl: el?.page_url || data.url || "",
          });
        });
      }
    }
  }

  return rows;
}

export function toPassesRows(data: any): PassRow[] {
  const rows: PassRow[] = [];
  let rowIndex = 0;

  if (data.passes) {
    for (const finding of data.passes) {
      const el = finding.element || {};
      const colors = extractColors(finding.reason_code || finding.rule_id || "");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        reasonTitle: finding.reason_code || finding.rule_id || "Pass",
        reasonDescription: el.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion_name || "")),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: finding.rule_id || finding.ruleId || "",
        imageUrls: pickImageUrls(el),
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        ocrText: truncateHtml(el.html),
        helpUrl: finding.helpUrl || "",
        pageUrl: el.page_url || data.url || "",
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "pass") continue;

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          const colors = extractColors(finding.reason);
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            reasonTitle: finding.reason,
            reasonDescription: el?.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.name),
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementFilename: finding.ruleId,
            imageUrls: pickImageUrls(el),
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            ocrText: truncateHtml(el?.html),
            helpUrl: finding.helpUrl,
            pageUrl: el?.page_url || data.url || "",
          });
        });
      }
    }
  }

  return rows;
}

export function toNeedsReviewRows(data: any): ReviewRow[] {
  const rows: ReviewRow[] = [];
  let rowIndex = 0;

  if (data.needs_review) {
    for (const finding of data.needs_review) {
      const el = finding.element || {};
      const colors = extractColors(finding.reason_code || finding.rule_id || "");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        status: "pending",
        reasonTitle: finding.reason_code || finding.rule_id || "Needs Review",
        reasonDescription: el.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion_name || "")),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: finding.rule_id || finding.ruleId || "",
        imageUrls: pickImageUrls(el),
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        ocrText: truncateHtml(el.html),
        helpUrl: finding.helpUrl || "",
        pageUrl: el.page_url || data.url || "",
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "incomplete") continue;

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          const colors = extractColors(finding.reason);
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            status: "pending",
            reasonTitle: finding.reason,
            reasonDescription: el?.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.name),
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementFilename: finding.ruleId,
            imageUrls: pickImageUrls(el),
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            ocrText: truncateHtml(el?.html),
            helpUrl: finding.helpUrl,
            pageUrl: el?.page_url || data.url || "",
          });
        });
      }
    }
  }

  return rows;
}

/* ─── Dashboard overview selectors ───
 * Read straight off the real report shape (report.py _build_report()):
 * summary.{violations,needs_review,passes,score,by_level,by_wcag_sc} and
 * the per-page `pages` array. No site-specific assumptions. */

export interface DashboardSummary {
  violations: number;
  needsReview: number;
  passes: number;
  score: number | null;
}

export function getDashboardSummary(data: WcagAuditResponse): DashboardSummary {
  const s = data.summary;
  return {
    violations: s?.violations ?? (data.violations?.length ?? 0),
    needsReview: s?.needs_review ?? (data.needs_review?.length ?? 0),
    passes: s?.passes ?? (data.passes?.length ?? 0),
    score: s?.score ?? null,
  };
}

export interface LevelBreakdownRow {
  level: WcagLevel;
  violations: number;
  needsReview: number;
  passes: number;
}

const DASHBOARD_LEVELS: WcagLevel[] = ["A", "AA", "AAA"];

export function getLevelBreakdown(data: WcagAuditResponse): LevelBreakdownRow[] {
  const byLevel = data.summary?.by_level ?? {};
  return DASHBOARD_LEVELS.map((level) => {
    const counts = byLevel[level];
    return {
      level,
      violations: counts?.violations ?? 0,
      needsReview: counts?.needs_review ?? 0,
      passes: counts?.passes ?? 0,
    };
  });
}

export interface TopFailingCriterion {
  code: string;
  label: string;
  level: WcagLevel;
  count: number;
}

/** Findings carry their own `level` and `criterion_name`; the summary's
 * by_wcag_sc bucket only has counts, so pull the display metadata from the
 * first finding seen for each SC. */
function scMetadata(data: WcagAuditResponse): Record<string, { level: WcagLevel; label: string }> {
  const meta: Record<string, { level: WcagLevel; label: string }> = {};
  const collect = (findings: unknown[] | undefined) => {
    for (const raw of findings ?? []) {
      const f = raw as { wcag_sc?: string; level?: WcagLevel; criterion_name?: string };
      if (f.wcag_sc && !meta[f.wcag_sc]) {
        meta[f.wcag_sc] = { level: f.level ?? "A", label: f.criterion_name || f.wcag_sc };
      }
    }
  };
  collect(data.violations);
  collect(data.needs_review);
  collect(data.passes);
  return meta;
}

export function getTopFailingCriteria(data: WcagAuditResponse, limit = 8): TopFailingCriterion[] {
  const byScRaw = data.summary?.by_wcag_sc ?? {};
  const meta = scMetadata(data);

  return Object.entries(byScRaw)
    .map(([code, counts]) => ({
      code,
      label: meta[code]?.label || code,
      level: meta[code]?.level ?? "A",
      count: counts.violations,
    }))
    .filter((c) => c.count > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

export interface DashboardPageFinding {
  pageName: string;
  url: string;
  score: number | null;
  findings: number;
  violations: number;
  needsReview: number;
  passes: number;
}

export function derivePageName(pageUrl: string, index: number): string {
  try {
    const u = new URL(pageUrl);
    const segment = u.pathname.replace(/\/+$/, "").split("/").filter(Boolean).pop();
    if (!segment) return "Home Page";
    const words = segment.replace(/\.[a-z0-9]+$/i, "").replace(/[-_]+/g, " ");
    return words.replace(/\b\w/g, (c) => c.toUpperCase()) || `Page ${index + 1}`;
  } catch {
    return `Page ${index + 1}`;
  }
}

export function getDashboardPageFindings(data: WcagAuditResponse): DashboardPageFinding[] {
  return (data.pages ?? []).map((page, index) => ({
    pageName: derivePageName(page.page_url, index),
    url: page.page_url,
    score: page.summary.score,
    findings: page.summary.total_findings,
    violations: page.summary.violations,
    needsReview: page.summary.needs_review,
    passes: page.summary.passes,
  }));
}

/** Every page either engine's crawl visited (success or failed), for the
 * per-page filter dropdown on the Violations / Needs Review / Passes tables.
 * Falls back to `[]` for older cached responses that predate this field. */
export function getScannedPages(data: WcagAuditResponse): WcagPageScan[] {
  return data.pages_scanned ?? [];
}

/* ─── CSV export ───
 * Raw finding fields (wcag_sc, criterion_name, level, severity, reason,
 * suggested_fix, element.page_url) come straight from report.py's
 * _build_report() / findings.py — same fields the row adapters above read,
 * just unformatted for a flat export. */

interface WcagRawFinding {
  wcag_sc?: string;
  criterion_name?: string;
  level?: string;
  severity?: string | null;
  reason?: string;
  reason_code?: string;
  suggested_fix?: string | null;
  element?: { page_url?: string | null } | null;
}

function csvEscape(value: unknown): string {
  const str = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
}

function csvSection(title: string, headers: string[], rows: unknown[][]): string {
  const lines = [
    title,
    headers.map(csvEscape).join(","),
    ...rows.map((row) => row.map(csvEscape).join(",")),
  ];
  return lines.join("\n");
}

/** Builds a single CSV (Violations / Needs Review / Passes sections, in that
 * order) from the real audit report. Adds a "Page URL" column to every
 * section only when the audit covered more than one page — a single-page
 * audit's CSV stays exactly as narrow as the requested column set. */
export function buildFindingsCsv(data: WcagAuditResponse): string {
  const multiPage = getScannedPages(data).length > 1;
  const pageUrlOf = (f: WcagRawFinding) => f.element?.page_url || data.url || "";

  const violations = (data.violations ?? []) as WcagRawFinding[];
  const needsReview = (data.needs_review ?? []) as WcagRawFinding[];
  const passes = (data.passes ?? []) as WcagRawFinding[];

  const violationsSection = csvSection(
    "Violations",
    ["WCAG SC", "Severity", "Level", "Reason", "Suggested Fix", ...(multiPage ? ["Page URL"] : [])],
    violations.map((f) => [
      f.wcag_sc ?? "",
      f.severity ?? "",
      f.level ?? "",
      f.reason ?? f.reason_code ?? "",
      f.suggested_fix ?? "",
      ...(multiPage ? [pageUrlOf(f)] : []),
    ]),
  );

  const needsReviewSection = csvSection(
    "Needs Review",
    ["WCAG SC", "Criterion", "Level", "Reason", ...(multiPage ? ["Page URL"] : [])],
    needsReview.map((f) => [
      f.wcag_sc ?? "",
      f.criterion_name ?? "",
      f.level ?? "",
      f.reason ?? f.reason_code ?? "",
      ...(multiPage ? [pageUrlOf(f)] : []),
    ]),
  );

  const passesSection = csvSection(
    "Passes",
    ["WCAG SC", "Criterion", "Level", ...(multiPage ? ["Page URL"] : [])],
    passes.map((f) => [
      f.wcag_sc ?? "",
      f.criterion_name ?? "",
      f.level ?? "",
      ...(multiPage ? [pageUrlOf(f)] : []),
    ]),
  );

  return [violationsSection, "", needsReviewSection, "", passesSection].join("\n");
}
