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
        description: finding.impact ? `Impact: ${capitalize(finding.impact)}` : (finding.criterion || finding.reason_code || ""),
        sc: finding.wcag_sc || "",
        criterion: finding.criterion || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementTitle: selectorStr,
        elementFile: finding.rule_id || finding.ruleId || "",
        elementOcr: truncateHtml(el.html),
        imageUrls: pickImageUrls(el),
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
            imageUrls: pickImageUrls(el),
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
        imageUrls: pickImageUrls(el),
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
            imageUrls: pickImageUrls(el),
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
        imageUrls: pickImageUrls(el),
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
            imageUrls: pickImageUrls(el),
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
