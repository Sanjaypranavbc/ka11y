import { PageBreakdown } from "@/types/audit";
import { ALL_PAGES, PageOption, formatPageLabel } from "@/components/audit/PageScopeBar";

export interface ScopeSummary {
  // null = "not scored" (no pass-or-fail findings) → render as "—".
  score: number | null;
  violations: number;
  needs_review: number;
  passes: number;
  total: number;
}

/** Dropdown options (one per crawled page) for the PageScopeBar. */
export function buildPageOptions(pages?: PageBreakdown[]): PageOption[] {
  if (!pages) return [];
  return pages.map((p) => ({ value: p.page_url, label: formatPageLabel(p.page_url) }));
}

/**
 * Findings for the active scope: the flat (aggregated) list for ALL_PAGES, else
 * the per-page list from the backend's `pages` breakdown.
 */
export function scopedFindings<T>(
  scope: string,
  flat: T[],
  pages: PageBreakdown[] | undefined,
  key: "violations" | "needs_review" | "passes",
): T[] {
  if (scope === ALL_PAGES || !pages) return flat;
  const page = pages.find((p) => p.page_url === scope);
  return page ? (page[key] as unknown as T[]) : [];
}

/** Summary stats for the active scope (aggregated overall, or one page). */
export function scopedSummary(
  scope: string,
  overall: ScopeSummary,
  pages: PageBreakdown[] | undefined,
): ScopeSummary {
  if (scope === ALL_PAGES || !pages) return overall;
  const page = pages.find((p) => p.page_url === scope);
  if (!page) return overall;
  return {
    score: page.summary.score,
    violations: page.summary.violations,
    needs_review: page.summary.needs_review,
    passes: page.summary.passes,
    total: page.summary.total_findings,
  };
}
