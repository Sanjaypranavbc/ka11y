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
  /** Distinct pages carrying at least one violation for this key. Only
   * populated on summary.by_wcag_sc; absent on older reports. */
  pages_affected?: number;
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
  elementAlt: string;
  elementOcr: string;
  imageUrls: string[];
  fixGuide: string;
  /** Who this blocks and how — only produced by the LLM enrichment step, and
   * only for high/critical findings, so it is empty on most rows. */
  userImpact: string;
  helpUrl: string;
  pageUrl: string;
  /** True when a person set this verdict on a needs_review item
   * (`verdict_source: "manual"`); `reviewNote` then holds the audit-trail
   * message plus the reviewer's own note. */
  reviewed: boolean;
  reviewNote: string;
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
  altText: string;
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
  altText: string;
  ocrText: string;
  helpUrl: string;
  pageUrl: string;
  reviewed: boolean;
  reviewNote: string;
}

/* ─── Helpers ─── */

/** "Reviewed by user and manually changed to Pass." + the reviewer's note. */
function pickReviewNote(finding: { review_message?: string | null; review_note?: string | null }): string {
  return [finding.review_message, finding.review_note].filter(Boolean).join(" ");
}

function capitalize(value: string): string {
  // Only upper-case a first word that is plain letters. `dynamic_reason` often
  // opens with the offending identifier itself — a filename, attribute or
  // selector ("img-slogan-en.svg contains…") — and force-capitalising that
  // shows the reader a name that does not exist on their page. Authored
  // rules.yml reasons already start with a capital, and severity words
  // ("serious") are plain letters, so both keep the old behaviour.
  const firstWord = value.split(/\s/, 1)[0];
  if (!/^[a-z]+$/.test(firstWord)) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function extractTag(html: string | null | undefined): string {
  if (!html) return "—";
  const match = html.match(/^<\s*([a-zA-Z0-9-]+)/);
  return match ? match[1] : "—";
}

/** Backend reasons (i18n/rules.yml) are authored as ordered sentences:
 * what broke → who it affects → what to do. The Reason cell renders the first
 * sentence as its heading and the remainder as supporting detail. */
function splitReason(reason: string): { head: string; rest: string } {
  const text = reason.trim();
  // Japanese (and Chinese) sentences end in 。！？ with no following space and
  // no capital letter, so the Latin rule below never matched them: `head` took
  // the WHOLE reason and the table rendered an entire paragraph in bold. Split
  // on the CJK terminators first, before falling back to the Latin rule.
  const cjk = text.match(/^[\s\S]*?[。！？]/);
  if (cjk && cjk[0].length < text.length) {
    return { head: cjk[0], rest: text.slice(cjk[0].length).trim() };
  }
  // Split only on a sentence end followed by a capitalised word, so decimals
  // ("4.76"), SC ids ("1.4.3") and 'e.g. "…"' stay intact.
  const parts = text.split(/(?<=[.!?])\s+(?=[A-Z])/);
  const head = parts[0] || text;
  const rest = parts.slice(1).join(" ");
  // A single long sentence has nothing to promote to a heading — bolding the
  // whole thing renders the cell as one heavy paragraph. `dynamic_reason` is
  // usually exactly that (one sentence, under 60 words), and a few authored
  // rules.yml reasons are too, so demote anything past heading length to plain
  // body text instead. The cutoff sits well above a normal head (~64 chars).
  if (!rest && head.length > 120) return { head: "", rest: head };
  return { head, rest };
}

/** The reason/fix fields a finding may carry, from either engine. All optional:
 * the `dynamic_*` pair exists only after enrichment, and Node/axe findings
 * carry neither `reason_code` nor `suggested_fix`. */
interface EnrichableFinding {
  reason?: string | null;
  suggested_fix?: string | null;
  dynamic_reason?: string | null;
  dynamic_suggested_fix?: string | null;
}

/** Reason text to display. `dynamic_reason` is the per-element explanation
 * written by the Gemini enrichment step (see ka11y-python/enrich_audit.py),
 * which cites the finding's own values — the real filename, the OCR'd text,
 * the measured contrast ratio. It is absent whenever enrichment was skipped
 * (no GEMINI_API_KEY, an API failure, or a Node/axe finding, which is never
 * enriched), so the static rules.yml reason stays the fallback. */
function pickReason(finding: EnrichableFinding): string {
  return finding.dynamic_reason || finding.reason || "";
}

/** Fix text to display, dynamic first — same fallback rule as pickReason. */
function pickFix(finding: EnrichableFinding): string {
  return finding.dynamic_suggested_fix || finding.suggested_fix || "";
}

/** Name of the captured image file backing a finding.
 * The backend ships it as `element.image_reference` (the crawler's own
 * `img_<hash>.png` / `svg_<hash>.png` filename). Falls back to the basename of
 * the captured-crop path. NEVER the rule id — that is the check that ran, not
 * a file, and showing it made every row of a rule look like the same asset. */
function pickImageFilename(el: any): string {
  if (!el) return "";
  const ref = el.image_reference;
  if (typeof ref === "string" && ref.trim()) return ref.trim();
  const src = el.image_src;
  if (typeof src === "string" && src.trim() && !src.startsWith("/api/")) {
    const base = src.split(/[\\/]/).pop();
    if (base) return base.split("?")[0];
  }
  return "";
}

/** Text OCR actually read out of the captured image (`element.image_text`).
 * Returns "" when the finding has none — most rules are not image rules, and
 * labelling an element's alt attribute as "OCR" (the old behaviour) put text
 * next to the picture that flatly contradicted it. Callers hide the row when
 * this is empty rather than printing an empty "OCR:" label. */
function pickOcrText(el: any, max = 90): string {
  const text = el?.image_text;
  if (typeof text !== "string" || !text.trim()) return "";
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

/** The element's own alt attribute, parsed from the finding's element HTML.
 * This is what the alt-text rules are actually about, so it is shown under its
 * own label instead of being passed off as OCR output. Empty string when the
 * element has no alt attribute (which is itself the finding, in that case). */
function pickAltText(el: any, max = 90): string {
  const html: string | undefined = el?.html;
  if (!html) return "";
  // Require the attribute to start a token, so `data-alt` / `xlink:alt` on the
  // element are not mistaken for the real alt attribute (`\balt` matches both).
  const m = html.match(/(?:^|[\s"'])alt\s*=\s*["']([^"']*)["']/i);
  if (!m) return "";
  const clean = m[1].replace(/\s+/g, " ").trim();
  if (!clean) return "";
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

      const reason = splitReason(pickReason(finding) || finding.reason_code || finding.rule_id || "Violation");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        title: capitalize(reason.head),
        description: reason.rest,
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementTitle: selectorStr,
        elementFile: pickImageFilename(el),
        elementAlt: pickAltText(el),
        elementOcr: pickOcrText(el),
        imageUrls: pickImageUrls(el),
        fixGuide: pickFix(finding),
        userImpact: finding.user_impact || "",
        helpUrl: finding.help_url || "",
        pageUrl: el.page_url || data.url || "",
        reviewed: Boolean(finding.reviewed),
        reviewNote: pickReviewNote(finding),
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "fail") continue;

        // Split here too, not just in the `violations` branch above: the whole
        // reason landing in `title` renders an entire paragraph in bold.
        const reason = splitReason(pickReason(finding) || finding.ruleId || "Violation");

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            title: capitalize(reason.head),
            description: reason.rest || (finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.principle),
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementTitle: el?.selector ?? "—",
            elementFile: pickImageFilename(el),
            elementAlt: pickAltText(el),
            elementOcr: pickOcrText(el),
            imageUrls: pickImageUrls(el),
            fixGuide: pickFix(finding),
            userImpact: finding.user_impact || "",
            helpUrl: finding.helpUrl,
            pageUrl: el?.page_url || data.url || "",
            reviewed: false,
            reviewNote: "",
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

      const reason = splitReason(pickReason(finding) || finding.reason_code || finding.rule_id || "Pass");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        reasonTitle: capitalize(reason.head),
        reasonDescription: reason.rest || el.detail || "",
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: pickImageFilename(el),
        imageUrls: pickImageUrls(el),
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        altText: pickAltText(el),
        ocrText: pickOcrText(el),
        helpUrl: finding.help_url || "",
        pageUrl: el.page_url || data.url || "",
        reviewed: Boolean(finding.reviewed),
        reviewNote: pickReviewNote(finding),
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "pass") continue;

        // Same split as the `passes` branch above — an unsplit reason renders
        // the whole paragraph in bold.
        const reason = splitReason(pickReason(finding) || finding.ruleId || "Pass");

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          const colors = extractColors(finding.reason);
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            reasonTitle: capitalize(reason.head),
            reasonDescription: reason.rest || el?.detail || (finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.name),
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementFilename: pickImageFilename(el),
            imageUrls: pickImageUrls(el),
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            altText: pickAltText(el),
            ocrText: pickOcrText(el),
            helpUrl: finding.helpUrl,
            pageUrl: el?.page_url || data.url || "",
            reviewed: false,
            reviewNote: "",
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

      const reason = splitReason(pickReason(finding) || finding.reason_code || finding.rule_id || "Needs Review");

      rows.push({
        id: finding.finding_id || `${finding.wcag_sc}-${finding.rule_id}-${rowIndex++}`,
        status: "pending",
        reasonTitle: capitalize(reason.head),
        reasonDescription: reason.rest || el.detail || "",
        sc: finding.wcag_sc || "",
        criterion: finding.criterion_name || "",
        level: (finding.level || "A") as WcagLevel,
        tag: extractTag(el.html),
        elementFilename: pickImageFilename(el),
        imageUrls: pickImageUrls(el),
        foreground: colors.foreground ?? "—",
        background: colors.background ?? "—",
        altText: pickAltText(el),
        ocrText: pickOcrText(el),
        helpUrl: finding.help_url || "",
        pageUrl: el.page_url || data.url || "",
      });
    }
  } else if (data.criteria) {
    for (const criterion of data.criteria) {
      for (const finding of criterion.findings) {
        if (finding.status !== "incomplete") continue;

        // Same split as the `needs_review` branch above — an unsplit reason
        // renders the whole paragraph in bold.
        const reason = splitReason(pickReason(finding) || finding.ruleId || "Needs Review");

        const elements = finding.elements.length > 0 ? finding.elements : [null];
        elements.forEach((el: any) => {
          const colors = extractColors(finding.reason);
          rows.push({
            id: `${criterion.sc}-${finding.ruleId}-${rowIndex++}`,
            status: "pending",
            reasonTitle: capitalize(reason.head),
            reasonDescription: reason.rest || el?.detail || (finding.impact ? `Impact: ${capitalize(finding.impact)}` : criterion.name),
            sc: criterion.sc,
            criterion: criterion.name,
            level: criterion.level,
            tag: extractTag(el?.html),
            elementFilename: pickImageFilename(el),
            imageUrls: pickImageUrls(el),
            foreground: colors.foreground ?? "—",
            background: colors.background ?? "—",
            altText: pickAltText(el),
            ocrText: pickOcrText(el),
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
  /** How many distinct pages this criterion fails on — distinguishes
   * "47 problems on one page" from "one problem across 47 pages". */
  pagesAffected: number;
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
      pagesAffected: counts.pages_affected ?? 0,
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
  /** Written by the Gemini enrichment step; absent when it was skipped. */
  dynamic_reason?: string | null;
  dynamic_suggested_fix?: string | null;
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
    "Fail",
    ["WCAG SC", "Severity", "Level", "Reason", "Suggested Fix", ...(multiPage ? ["Page URL"] : [])],
    violations.map((f) => [
      f.wcag_sc ?? "",
      f.severity ?? "",
      f.level ?? "",
      f.dynamic_reason || f.reason || f.reason_code || "",
      f.dynamic_suggested_fix || f.suggested_fix || "",
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
      f.dynamic_reason || f.reason || f.reason_code || "",
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
