import type { ContrastReport } from "@/lib/auditImages";

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

export interface WcagAuditSummary {
  total: number;
  checked: number;
  passed: number;
  failed: number;
  needsReview: number;
  notChecked: number;
  notApplicable: number;
  manualOnly: number;
}

export interface WcagAuditResponse {
  url: string;
  wcagVersion: string;
  analyzedAt: string;
  summary: WcagAuditSummary;
  // node-shape findings (fallback path in the derivers)
  criteria?: WcagCriterion[];
  // combined-audit flat findings arrays (primary path in the derivers)
  violations?: unknown[];
  passes?: unknown[];
  needs_review?: unknown[];
  // per-image contrast data that drives the Image Visualiser page
  contrast_report?: ContrastReport | null;
  image_audit_report?: ContrastReport | null;
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
  fixGuide: string;
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
  foreground: string;
  background: string;
  ocrText: string;
  helpUrl: string;
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
  foreground: string;
  background: string;
  ocrText: string;
  helpUrl: string;
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
        description: finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion || finding.reason_code || ""),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementTitle: selectorStr,
        elementFile: finding.rule_id || finding.ruleId || "",
        elementOcr: truncateHtml(el.html),
        fixGuide: finding.helpUrl || "",
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
            fixGuide: finding.helpUrl,
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
        reasonDescription: el.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion || "")),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: finding.rule_id || finding.ruleId || "",
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        ocrText: truncateHtml(el.html),
        helpUrl: finding.helpUrl || "",
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
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            ocrText: truncateHtml(el?.html),
            helpUrl: finding.helpUrl,
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
        reasonDescription: el.detail ?? (finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion || "")),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: finding.rule_id || finding.ruleId || "",
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        ocrText: truncateHtml(el.html),
        helpUrl: finding.helpUrl || "",
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
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            ocrText: truncateHtml(el?.html),
            helpUrl: finding.helpUrl,
          });
        });
      }
    }
  }

  return rows;
}
