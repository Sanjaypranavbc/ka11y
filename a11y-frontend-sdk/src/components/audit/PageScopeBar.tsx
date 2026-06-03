import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLanguage } from "@/i18n/LanguageContext";
import { cn } from "@/lib/utils";

// Sentinel value for the aggregated ("All pages") option.
export const ALL_PAGES = "all";

export interface PageOption {
  value: string; // page_url
  label: string; // display label (use formatPageLabel)
}

export type ChipTone = "violations" | "needsReview" | "passes" | "score" | "default";

export interface PageScopeChip {
  label: string;
  // null is allowed for the score chip → rendered as "—" (not scored).
  value: string | number | null;
  tone?: ChipTone;
}

interface PageScopeBarProps {
  /** One entry per crawled page (page_url + display label). */
  pages: PageOption[];
  /** Current scope: ALL_PAGES or a page_url. */
  value: string;
  onChange: (value: string) => void;
  /** Summary stats for the current scope, rendered as a chip row. */
  chips: PageScopeChip[];
}

const TONE_CLASS: Record<ChipTone, string> = {
  violations: "text-destructive",
  needsReview: "text-primary",
  passes: "text-success",
  score: "text-foreground",
  default: "text-foreground",
};

// Compliance-score colour band — mirrors DashboardTab.
// null = "not scored" → muted.
function scoreColor(score: number | null): string {
  if (score == null) return "hsl(215, 16%, 47%)";
  if (score >= 90) return "hsl(151, 68%, 40%)";
  if (score >= 70) return "hsl(45, 100%, 38%)";
  return "hsl(0, 84%, 52%)";
}

/** Turn an absolute page URL into a compact, readable label (path + query). */
export function formatPageLabel(url: string): string {
  try {
    const u = new URL(url);
    const path = `${u.pathname}${u.search}`;
    return path === "/" || path === "" ? u.host : `${u.host}${path}`;
  } catch {
    return url;
  }
}

/**
 * Page-scope selector + per-scope summary bar. Renders nothing for single-page
 * audits (≤ 1 crawled page); only multi-page crawls (max_depth > 0) get the
 * picker so the UI is unchanged for the common single-URL case.
 */
export function PageScopeBar({ pages, value, onChange, chips }: PageScopeBarProps) {
  const { t } = useLanguage();

  if (pages.length <= 1) return null;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card/60 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {t("pageScope.label")}
        </span>
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger
            className="h-9 w-full text-sm sm:w-[min(58vw,30rem)]"
            aria-label={t("pageScope.label")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-80">
            <SelectItem value={ALL_PAGES} className="text-sm font-medium">
              {t("pageScope.allPages")}
            </SelectItem>
            {pages.map((p) => (
              <SelectItem key={p.value} value={p.value} className="font-mono text-xs">
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="hidden shrink-0 text-[11px] text-muted-foreground sm:inline">
          {t("pageScope.pagesCrawled", { n: pages.length })}
        </span>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 sm:justify-end">
        {chips.map((chip) => {
          const tone = chip.tone ?? "default";
          const isScore = tone === "score";
          // Score chip with a null value means "not scored" → render "—".
          const scoreNotScored = isScore && chip.value == null;
          const numeric =
            chip.value == null
              ? null
              : typeof chip.value === "number"
                ? chip.value
                : Number(chip.value);
          return (
            <div key={chip.label} className="flex items-baseline gap-1.5">
              <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {chip.label}
              </span>
              <span
                className={cn("text-base font-bold tabular-nums", !isScore && TONE_CLASS[tone])}
                style={isScore ? { color: scoreColor(numeric) } : undefined}
              >
                {scoreNotScored ? "—" : chip.value}
                {isScore && !scoreNotScored ? "%" : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
