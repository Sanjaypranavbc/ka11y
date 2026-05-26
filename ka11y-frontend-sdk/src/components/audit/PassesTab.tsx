import { useState, useEffect, useMemo } from "react";
import { AuditPass, PageBreakdown } from "@/types/audit";
import { PageScopeBar, ALL_PAGES } from "./PageScopeBar";
import { buildPageOptions, scopedFindings, scopedSummary, ScopeSummary } from "@/lib/page-scope";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { FindingElementCell } from "./FindingElementCell";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  formatCriterionId,
  formatCriterionName,
  formatElementTag,
  formatLevel,
} from "@/lib/audit-format";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useLanguage } from "@/i18n/LanguageContext";

interface PassesTabProps {
  passes: AuditPass[];
  pages?: PageBreakdown[];
  overall: ScopeSummary;
  pageSize?: number;
}

export function PassesTab({ passes, pages, overall, pageSize = 50 }: PassesTabProps) {
  const { t } = useLanguage();
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [levelFilter, setLevelFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({});
  const [scope, setScope] = useState<string>(ALL_PAGES);

  // Page-scoped findings: aggregated for ALL_PAGES, else just the selected page.
  const pageOptions = useMemo(() => buildPageOptions(pages), [pages]);
  const summary = scopedSummary(scope, overall, pages);
  const scoped = useMemo(
    () => scopedFindings(scope, passes, pages, "passes"),
    [scope, passes, pages]
  );

  useEffect(() => {
    setVisibleCounts({});
  }, [pageSize, search, sourceFilter, levelFilter, scFilter, scope]);

  const allSources = useMemo(
    () => [...new Set(scoped.map((p) => p.source).filter(Boolean))].sort(),
    [scoped]
  );
  const allLevels = useMemo(() => {
    const preferred = ["A", "AA", "AAA"];
    const present = [...new Set(scoped.map((p) => p.level).filter(Boolean))] as string[];
    const ordered = preferred.filter((l) => present.includes(l));
    const extras = present.filter((l) => !preferred.includes(l)).sort();
    return [...ordered, ...extras];
  }, [scoped]);
  const allScs = useMemo(
    () => [...new Set(scoped.map((p) => p.wcag_sc).filter(Boolean))].sort(),
    [scoped]
  );

  const filtered = useMemo(() => {
    return scoped.filter((p) => {
      if (sourceFilter.length && !sourceFilter.includes(p.source)) return false;
      if (levelFilter.length && (!p.level || !levelFilter.includes(p.level))) return false;
      if (scFilter.length && (!p.wcag_sc || !scFilter.includes(p.wcag_sc))) return false;
      if (!search) return true;
      const q = search.toLowerCase();
        return (
          p.rule_id.toLowerCase().includes(q) ||
          (p.wcag_sc || "").toLowerCase().includes(q) ||
          (p.criterion_name || "").toLowerCase().includes(q) ||
          p.reason.toLowerCase().includes(q) ||
          (p.element_html || "").toLowerCase().includes(q) ||
          (p.element_selector || "").toLowerCase().includes(q) ||
          (p.image_reference || "").toLowerCase().includes(q) ||
          (p.image_text || "").toLowerCase().includes(q) ||
          (p.image_src || "").toLowerCase().includes(q) ||
          (p.element_tag || "").toLowerCase().includes(q) ||
          (p.element_id || "").toLowerCase().includes(q)
        );
    });
  }, [scoped, search, sourceFilter, levelFilter, scFilter]);

  const grouped = useMemo(
    () =>
      filtered.reduce(
        (acc, p) => {
          (acc[p.source] = acc[p.source] || []).push(p);
          return acc;
        },
        {} as Record<string, AuditPass[]>
      ),
    [filtered]
  );

  const toggleFilter = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const clearFilters = () => {
    setSearch("");
    setSourceFilter([]);
    setLevelFilter([]);
    setScFilter([]);
  };

  const hasFilters = search || sourceFilter.length || levelFilter.length || scFilter.length;

  const toggle = (source: string) => {
    setOpenSections((prev) => ({ ...prev, [source]: !(prev[source] ?? true) }));
  };

  const showMore = (source: string) => {
    setVisibleCounts((prev) => ({ ...prev, [source]: (prev[source] ?? pageSize) + pageSize }));
  };

  const showingText = filtered.length !== scoped.length
    ? t("passes.showingFiltered", { n: filtered.length, all: scoped.length })
    : t("passes.showing", { n: filtered.length });

  return (
    <div className="p-3 sm:p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
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
          placeholder={t("passes.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-72 h-8 text-xs"
        />

        <div role="group" aria-label={t("table.filterSource")} className="w-full sm:w-auto flex gap-1 overflow-x-auto pb-1 sm:pb-0 sm:flex-wrap">
          {allSources.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(sourceFilter, s, setSourceFilter)}
              aria-pressed={sourceFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors shrink-0",
                sourceFilter.includes(s) ? "bg-primary text-primary-foreground border-primary/50" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <div role="group" aria-label={t("table.filterLevel")} className="w-full sm:w-auto flex gap-1 overflow-x-auto pb-1 sm:pb-0 sm:flex-wrap">
          {allLevels.map((lvl) => (
            <button
              key={lvl}
              onClick={() => toggleFilter(levelFilter, lvl, setLevelFilter)}
              aria-pressed={levelFilter.includes(lvl)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors shrink-0",
                levelFilter.includes(lvl) ? "bg-accent text-accent-foreground border-accent-foreground/30" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {lvl}
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

      {Object.keys(grouped).length === 0 && (
        <p className="text-xs text-muted-foreground">{t("passes.noMatch")}</p>
      )}

      {Object.entries(grouped).map(([source, items]) => {
        const isOpen = openSections[source] ?? true;
        const visible = visibleCounts[source] ?? pageSize;
        return (
          <Collapsible key={source} open={isOpen} onOpenChange={() => toggle(source)}>
            <CollapsibleTrigger className="flex flex-wrap items-center gap-2 w-full p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors">
              <ChevronDown className={cn("h-4 w-4 transition-transform", isOpen && "rotate-180")} />
              <span className="text-sm font-medium capitalize">{source}</span>
              <Badge variant="secondary" className="text-[10px] ml-auto">
                {t("passes.badge", { n: items.length })}
              </Badge>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="-mx-3 sm:mx-0 rounded-lg border border-border overflow-hidden mt-2">
                <Table className="w-full [&_th]:h-10 [&_th]:px-2 sm:[&_th]:h-12 sm:[&_th]:px-4 [&_td]:px-2 [&_td]:py-2 sm:[&_td]:px-4 sm:[&_td]:py-3">
                  <TableHeader>
                    <TableRow className="bg-muted/30">
                      <TableHead className="text-xs">{t("table.ruleId")}</TableHead>
                      <TableHead className="text-xs hidden lg:table-cell">{t("table.sc")}</TableHead>
                      <TableHead className="text-xs hidden lg:table-cell">{t("table.criterion")}</TableHead>
                      <TableHead className="text-xs hidden md:table-cell">{t("table.level")}</TableHead>
                      <TableHead className="text-xs hidden lg:table-cell">{t("table.tag")}</TableHead>
                      <TableHead className="text-xs">{t("table.element")}</TableHead>
                      <TableHead className="text-xs">{t("table.reason")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} className="text-xs text-muted-foreground text-center py-8">
                          {t("passes.noMatchSource")}
                        </TableCell>
                      </TableRow>
                    )}
                    {items.slice(0, visible).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{p.rule_id}</TableCell>
                        <TableCell className="font-mono text-xs hidden lg:table-cell">{formatCriterionId(p.wcag_sc)}</TableCell>
                        <TableCell className="text-xs hidden lg:table-cell">{formatCriterionName(p.criterion_name, p.wcag_sc)}</TableCell>
                        <TableCell className="hidden md:table-cell"><Badge variant="outline" className="text-[10px]">{formatLevel(p.level)}</Badge></TableCell>
                        <TableCell className="font-mono text-xs hidden lg:table-cell">{formatElementTag(p.element_tag)}</TableCell>
                        <TableCell>
                          <FindingElementCell
                            elementHtml={p.element_html}
                            elementSelector={p.element_selector}
                            imageReference={p.image_reference}
                            imageSrc={p.image_src}
                            imageText={p.image_text}
                            ruleId={p.rule_id}
                            wcagSc={p.wcag_sc}
                            criterionName={p.criterion_name}
                            reason={p.reason}
                          />
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-xs">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span tabIndex={0} className="cursor-help truncate block max-w-xs">{p.reason}</span>
                            </TooltipTrigger>
                            <TooltipContent className="max-w-sm text-xs">{p.reason}</TooltipContent>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {visible < items.length && (
                <div className="flex justify-center pt-2">
                  <Button variant="outline" size="sm" className="text-xs" onClick={() => showMore(source)}>
                    {t("passes.showMore", { n: items.length - visible })}
                  </Button>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>
        );
      })}
    </div>
  );
}
