import { useState, useMemo, useEffect } from "react";
import { AuditNeedsReview, PageBreakdown } from "@/types/audit";
import { PageScopeBar, ALL_PAGES } from "./PageScopeBar";
import { buildPageOptions, scopedFindings, scopedSummary, ScopeSummary } from "@/lib/page-scope";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SuggestedFixModal } from "./SuggestedFixModal";
import { FindingElementCell } from "./FindingElementCell";
import { AlertTriangle, Wrench, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatCriterionId,
  formatCriterionName,
  formatElementTag,
} from "@/lib/audit-format";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLanguage } from "@/i18n/LanguageContext";

interface NeedsReviewTabProps {
  items: AuditNeedsReview[];
  pages?: PageBreakdown[];
  overall: ScopeSummary;
  pageSize?: number;
}

const severityColors: Record<string, string> = {
  critical: "bg-destructive text-destructive-foreground",
  high: "bg-serious text-serious-foreground",
  medium: "bg-moderate text-moderate-foreground",
  low: "bg-moderate/60 text-foreground",
};

const sourceColors: Record<string, string> = {
  axe: "bg-primary/15 text-primary border-primary/30",
  "axe-core": "bg-primary/15 text-primary border-primary/30",
  accesslint: "bg-purple-100 text-purple-800 border-purple-300",
  python: "bg-accent text-accent-foreground border-accent-foreground/30",
  custom: "bg-serious/15 text-serious border-serious/30",
  unknown: "bg-muted text-muted-foreground border-border",
};

export function NeedsReviewTab({ items, pages, overall, pageSize = 50 }: NeedsReviewTabProps) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [modalData, setModalData] = useState<AuditNeedsReview | null>(null);
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [scope, setScope] = useState<string>(ALL_PAGES);

  // Page-scoped findings: aggregated for ALL_PAGES, else just the selected page.
  const pageOptions = useMemo(() => buildPageOptions(pages), [pages]);
  const summary = scopedSummary(scope, overall, pages);
  const scoped = useMemo(
    () => scopedFindings(scope, items, pages, "needs_review"),
    [scope, items, pages]
  );

  const allSeverities = useMemo(() => {
    const preferred = ["critical", "high", "medium", "low"];
    const present = [...new Set(scoped.map((v) => v.severity).filter(Boolean))] as string[];
    const ordered = preferred.filter((s) => present.includes(s));
    const extras = present.filter((s) => !preferred.includes(s)).sort();
    return [...ordered, ...extras];
  }, [scoped]);
  const allSources = useMemo(
    () => [...new Set(scoped.map((v) => v.source).filter(Boolean))].sort(),
    [scoped]
  );
  const allScs = useMemo(
    () => [...new Set(scoped.map((v) => v.wcag_sc).filter(Boolean))].sort() as string[],
    [scoped]
  );

  const filtered = useMemo(() => {
    return scoped.filter((v) => {
      if (severityFilter.length && !severityFilter.includes(v.severity)) return false;
      if (sourceFilter.length && !sourceFilter.includes(v.source)) return false;
      if (scFilter.length && !scFilter.includes(v.wcag_sc)) return false;
      if (!search) return true;
      const q = search.toLowerCase();
        return (
          v.reason.toLowerCase().includes(q) ||
          (v.element_html || "").toLowerCase().includes(q) ||
          (v.element_selector || "").toLowerCase().includes(q) ||
          (v.image_reference || "").toLowerCase().includes(q) ||
          (v.image_text || "").toLowerCase().includes(q) ||
          (v.image_src || "").toLowerCase().includes(q) ||
          (v.rule_id || "").toLowerCase().includes(q) ||
          (v.element_tag || "").toLowerCase().includes(q)
        );
    });
  }, [scoped, search, severityFilter, sourceFilter, scFilter]);

  const toggleFilter = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const clearFilters = () => {
    setSearch("");
    setSeverityFilter([]);
    setSourceFilter([]);
    setScFilter([]);
    setVisibleCount(pageSize);
  };

  useEffect(() => {
    setVisibleCount(pageSize);
  }, [pageSize, search, severityFilter, sourceFilter, scFilter, scope]);

  const hasFilters = search || severityFilter.length || sourceFilter.length || scFilter.length;

  const showingText = filtered.length !== scoped.length
    ? t("needsReview.showingFiltered", { visible: Math.min(visibleCount, filtered.length), total: filtered.length, all: scoped.length })
    : t("needsReview.showing", { visible: Math.min(visibleCount, filtered.length), total: filtered.length });

  return (
    <div className="p-3 sm:p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      <div className="bg-moderate/10 border border-moderate/30 rounded-lg p-4 flex items-start gap-3" role="note">
        <AlertTriangle className="h-5 w-5 text-moderate shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-foreground">
          {t("needsReview.manualNote")}
        </p>
      </div>

      <PageScopeBar
        pages={pageOptions}
        value={scope}
        onChange={setScope}
        chips={[
          { label: t("pageScope.score"), value: summary.score, tone: "score" },
          { label: t("pageScope.violations"), value: summary.violations, tone: "violations" },
          { label: t("pageScope.needsReview"), value: summary.needs_review, tone: "needsReview" },
          { label: t("pageScope.passes"), value: summary.passes, tone: "passes" },
        ]}
      />

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <Input
          placeholder={t("table.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-64 h-8 text-xs"
        />

        <div role="group" aria-label={t("table.filterSeverity")} className="w-full sm:w-auto flex gap-1 overflow-x-auto pb-1 sm:pb-0 sm:flex-wrap">
          {allSeverities.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(severityFilter, s, setSeverityFilter)}
              aria-pressed={severityFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors shrink-0",
                severityFilter.includes(s)
                  ? (severityColors[s] || "bg-primary text-primary-foreground border-primary/50")
                  : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <div role="group" aria-label={t("table.filterSource")} className="w-full sm:w-auto flex gap-1 overflow-x-auto pb-1 sm:pb-0 sm:flex-wrap">
          {allSources.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(sourceFilter, s, setSourceFilter)}
              aria-pressed={sourceFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors shrink-0",
                sourceFilter.includes(s)
                  ? (sourceColors[s] || "bg-primary text-primary-foreground border-primary/50")
                  : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <div role="group" aria-label={t("table.filterSC")} className="w-full sm:w-auto flex gap-1 overflow-x-auto pb-1 sm:pb-0 sm:flex-wrap">
          {allScs.map((sc) => (
            <button
              key={sc}
              onClick={() => toggleFilter(scFilter, sc, setScFilter)}
              aria-pressed={scFilter.includes(sc)}
              className={cn(
                "px-2 py-1 rounded text-xs font-mono border transition-colors shrink-0",
                scFilter.includes(sc) ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {sc}
            </button>
          ))}
        </div>

        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="text-xs h-7 self-start sm:self-auto">
            <X className="h-3 w-3 mr-1" /> {t("table.clear")}
          </Button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">{showingText}</p>

      <div className="-mx-3 sm:mx-0 rounded-lg border border-border overflow-hidden">
        <Table className="w-full [&_th]:h-10 [&_th]:px-2 sm:[&_th]:h-12 sm:[&_th]:px-4 [&_td]:px-2 [&_td]:py-2 sm:[&_td]:px-4 sm:[&_td]:py-3">
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-xs">{t("table.severity")}</TableHead>
              <TableHead className="text-xs hidden md:table-cell">{t("table.source")}</TableHead>
              <TableHead className="text-xs">{t("table.ruleId")}</TableHead>
              <TableHead className="text-xs hidden lg:table-cell">{t("table.sc")}</TableHead>
              <TableHead className="text-xs hidden lg:table-cell">{t("table.criterion")}</TableHead>
              <TableHead className="text-xs hidden lg:table-cell">{t("table.tag")}</TableHead>
              <TableHead className="text-xs">{t("table.reason")}</TableHead>
              <TableHead className="text-xs">{t("table.element")}</TableHead>
              <TableHead className="text-xs">{t("table.fix")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} className="text-xs text-muted-foreground text-center py-8">
                  {t("needsReview.noMatch")}
                </TableCell>
              </TableRow>
            )}
            {filtered.slice(0, visibleCount).map((v, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Badge
                    className={cn(
                      "text-[10px]",
                      v.severity ? (severityColors[v.severity] || "bg-muted text-muted-foreground") : "bg-muted text-muted-foreground"
                    )}
                  >
                    {v.severity ?? "—"}
                  </Badge>
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  {v.detected_by && v.detected_by.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      {v.detected_by.map(engine => (
                        <Badge key={engine} variant="outline" className={cn("text-[10px]", sourceColors[engine] || sourceColors.unknown)}>
                          {engine}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <Badge variant="outline" className={cn("text-[10px]", sourceColors[v.source] || sourceColors.unknown)}>
                      {v.source}
                    </Badge>
                  )}
                </TableCell>
                <TableCell className="font-mono text-xs">{v.rule_id}</TableCell>
                <TableCell className="font-mono text-xs hidden lg:table-cell">{formatCriterionId(v.wcag_sc)}</TableCell>
                <TableCell className="text-xs hidden lg:table-cell">{formatCriterionName(v.criterion_name, v.wcag_sc)}</TableCell>
                <TableCell className="font-mono text-xs hidden lg:table-cell">{formatElementTag(v.element_tag)}</TableCell>
                <TableCell className="text-xs text-muted-foreground max-w-xs">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span tabIndex={0} className="cursor-help truncate block max-w-xs">
                        {v.reason}
                        {v.aiContext && <span className="text-purple-500 font-semibold ml-1">✨ AI</span>}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-sm text-xs">
                      <p>{v.reason}</p>
                      {v.aiContext && (
                        <div className="mt-2 text-purple-200 border-t border-purple-800/50 pt-2 flex flex-col">
                          <span className="font-semibold mb-1 text-purple-300">AccessLint AI Context:</span>
                          {v.aiContext}
                        </div>
                      )}
                    </TooltipContent>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <FindingElementCell
                    elementHtml={v.element_html}
                    elementSelector={v.element_selector}
                    imageReference={v.image_reference}
                    imageSrc={v.image_src}
                    imageText={v.image_text}
                    ruleId={v.rule_id}
                    wcagSc={v.wcag_sc}
                    criterionName={v.criterion_name}
                    reason={v.reason}
                  />
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="sm" onClick={() => setModalData(v)} className="h-6 text-[10px]" aria-label={`View suggested fix for WCAG ${v.wcag_sc}`}>
                    <Wrench className="h-3 w-3" aria-hidden="true" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {visibleCount < filtered.length && (
        <div className="flex justify-center pt-2">
          <Button variant="outline" size="sm" className="text-xs" onClick={() => setVisibleCount((n) => n + pageSize)}>
            {t("needsReview.showMore", { n: filtered.length - visibleCount })}
          </Button>
        </div>
      )}

      {modalData && (
        <SuggestedFixModal
          open={!!modalData}
          onOpenChange={(open) => !open && setModalData(null)}
          wcagSc={modalData.wcag_sc}
          criterionName={modalData.criterion_name}
          suggestedFix={modalData.suggested_fix}
          elementHtml={modalData.element_html}
          elementSelector={modalData.element_selector}
          helpUrl={modalData.help_url}
        />
      )}
    </div>
  );
}
