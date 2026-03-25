import { useState, useEffect, useMemo } from "react";
import { AuditPass } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatCriterionId, formatCriterionName, formatLevel } from "@/lib/audit-format";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface PassesTabProps {
  passes: AuditPass[];
  pageSize?: number;
}

export function PassesTab({ passes, pageSize = 50 }: PassesTabProps) {
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [levelFilter, setLevelFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({});
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    setVisibleCounts({});
  }, [pageSize, search, sourceFilter, levelFilter, scFilter]);

  const allSources = useMemo(
    () => [...new Set(passes.map((p) => p.source).filter(Boolean))].sort(),
    [passes]
  );
  const allLevels = useMemo(() => {
    const preferred = ["A", "AA", "AAA"];
    const present = [...new Set(passes.map((p) => p.level).filter(Boolean))] as string[];
    const ordered = preferred.filter((l) => present.includes(l));
    const extras = present.filter((l) => !preferred.includes(l)).sort();
    return [...ordered, ...extras];
  }, [passes]);
  const allScs = useMemo(
    () => [...new Set(passes.map((p) => p.wcag_sc).filter(Boolean))].sort(),
    [passes]
  );

  const filtered = useMemo(() => {
    return passes.filter((p) => {
      if (sourceFilter.length && !sourceFilter.includes(p.source)) return false;
      if (levelFilter.length && (!p.level || !levelFilter.includes(p.level))) return false;
      if (scFilter.length && (!p.wcag_sc || !scFilter.includes(p.wcag_sc))) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return (
        p.rule_id.toLowerCase().includes(q) ||
        (p.wcag_sc || "").toLowerCase().includes(q) ||
        (p.criterion_name || "").toLowerCase().includes(q) ||
        p.reason.toLowerCase().includes(q)
      );
    });
  }, [passes, search, sourceFilter, levelFilter, scFilter]);

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

  return (
    <div className="p-3 sm:p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search rule, SC, criterion, reason..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full sm:w-72 h-8 text-xs"
        />

        <div role="group" aria-label="Filter by source" className="flex flex-wrap gap-1">
          {allSources.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(sourceFilter, s, setSourceFilter)}
              aria-pressed={sourceFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                sourceFilter.includes(s) ? "bg-primary text-primary-foreground border-primary/50" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <div role="group" aria-label="Filter by WCAG level" className="flex flex-wrap gap-1">
          {allLevels.map((lvl) => (
            <button
              key={lvl}
              onClick={() => toggleFilter(levelFilter, lvl, setLevelFilter)}
              aria-pressed={levelFilter.includes(lvl)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                levelFilter.includes(lvl) ? "bg-accent text-accent-foreground border-accent-foreground/30" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {lvl}
            </button>
          ))}
        </div>

        <div role="group" aria-label="Filter by WCAG success criterion" className="flex gap-1 flex-wrap">
          {allScs.map((sc) => (
            <button
              key={sc}
              onClick={() => toggleFilter(scFilter, sc, setScFilter)}
              aria-pressed={scFilter.includes(sc)}
              className={cn(
                "px-2 py-1 rounded text-xs font-mono border transition-colors",
                scFilter.includes(sc) ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground border-border"
              )}
            >
              {sc}
            </button>
          ))}
        </div>

        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="text-xs h-7">
            <X className="h-3 w-3 mr-1" /> Clear
          </Button>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        Showing {filtered.length} passes
        {filtered.length !== passes.length && ` (${passes.length} total)`}
      </p>

      {Object.keys(grouped).length === 0 && (
        <p className="text-xs text-muted-foreground">No passes match the current filters.</p>
      )}

      {Object.entries(grouped).map(([source, items]) => {
        const isOpen = openSections[source] ?? true;
        const visible = visibleCounts[source] ?? pageSize;
        return (
          <Collapsible key={source} open={isOpen} onOpenChange={() => toggle(source)}>
            <CollapsibleTrigger className="flex items-center gap-2 w-full p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors">
              <ChevronDown className={cn("h-4 w-4 transition-transform", isOpen && "rotate-180")} />
              <span className="text-sm font-medium capitalize">{source}</span>
              <Badge variant="secondary" className="text-[10px] ml-auto">{items.length} passes</Badge>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="rounded-lg border border-border overflow-hidden mt-2">
                <Table className="min-w-[720px]">
                  <TableHeader>
                    <TableRow className="bg-muted/30">
                      <TableHead className="text-xs">Rule ID</TableHead>
                      <TableHead className="text-xs">SC</TableHead>
                      <TableHead className="text-xs">Criterion</TableHead>
                      <TableHead className="text-xs">Level</TableHead>
                      <TableHead className="text-xs">Reason</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={5} className="text-xs text-muted-foreground text-center py-8">
                          No passes are available for this source.
                        </TableCell>
                      </TableRow>
                    )}
                    {items.slice(0, visible).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{p.rule_id}</TableCell>
                        <TableCell className="font-mono text-xs">{formatCriterionId(p.wcag_sc)}</TableCell>
                        <TableCell className="text-xs">{formatCriterionName(p.criterion_name, p.wcag_sc)}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px]">{formatLevel(p.level)}</Badge></TableCell>
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
                    Show more ({items.length - visible} remaining)
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
