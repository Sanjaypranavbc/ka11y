import { useState, useMemo, useCallback, useEffect } from "react";
import { AuditViolation } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SuggestedFixModal } from "./SuggestedFixModal";
import { Wrench, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface ViolationsTabProps {
  violations: AuditViolation[];
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
  python: "bg-accent text-accent-foreground border-accent-foreground/30",
  custom: "bg-serious/15 text-serious border-serious/30",
  unknown: "bg-muted text-muted-foreground border-border",
};

export function ViolationsTab({ violations, pageSize = 50 }: ViolationsTabProps) {
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [modalData, setModalData] = useState<AuditViolation | null>(null);
  const [visibleCount, setVisibleCount] = useState(pageSize);

  const allSeverities = useMemo(() => {
    const preferred = ["critical", "high", "medium", "low"];
    const present = [...new Set(violations.map((v) => v.severity).filter(Boolean))] as string[];
    const ordered = preferred.filter((s) => present.includes(s));
    const extras = present.filter((s) => !preferred.includes(s)).sort();
    return [...ordered, ...extras];
  }, [violations]);
  const allSources = useMemo(
    () => [...new Set(violations.map((v) => v.source).filter(Boolean))].sort(),
    [violations]
  );
  const allScs = useMemo(() => [...new Set(violations.map((v) => v.wcag_sc).filter(Boolean))].sort() as string[], [violations]);

  const filtered = useMemo(() => {
    return violations.filter((v) => {
      if (severityFilter.length && !severityFilter.includes(v.severity)) return false;
      if (sourceFilter.length && !sourceFilter.includes(v.source)) return false;
      if (scFilter.length && !scFilter.includes(v.wcag_sc)) return false;
      if (search) {
        const q = search.toLowerCase();
        return v.reason.toLowerCase().includes(q) || v.element_html.toLowerCase().includes(q);
      }
      return true;
    });
  }, [violations, severityFilter, sourceFilter, scFilter, search]);

  const toggleFilter = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
    resetVisibleCount();
  };

  const clearFilters = () => {
    setSearch("");
    setSeverityFilter([]);
    setSourceFilter([]);
    setScFilter([]);
    setVisibleCount(pageSize);
  };

  const resetVisibleCount = useCallback(() => setVisibleCount(pageSize), [pageSize]);

  useEffect(() => {
    setVisibleCount(pageSize);
  }, [pageSize]);

  const hasFilters = search || severityFilter.length || sourceFilter.length || scFilter.length;

  return (
    <div className="p-3 sm:p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search reason or HTML..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); resetVisibleCount(); }}
          className="w-full sm:w-64 h-8 text-xs"
        />

        {/* Severity filters */}
        <div role="group" aria-label="Filter by severity" className="flex flex-wrap gap-1">
          {allSeverities.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(severityFilter, s, setSeverityFilter)}
              aria-pressed={severityFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                severityFilter.includes(s)
                  ? (severityColors[s] || "bg-primary text-primary-foreground border-primary/50")
                  : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Source filters */}
        <div role="group" aria-label="Filter by source" className="flex flex-wrap gap-1">
          {allSources.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(sourceFilter, s, setSourceFilter)}
              aria-pressed={sourceFilter.includes(s)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                sourceFilter.includes(s)
                  ? (sourceColors[s] || "bg-primary text-primary-foreground border-primary/50")
                  : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* WCAG SC filter - show all */}
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
        Showing {Math.min(visibleCount, filtered.length)} of {filtered.length} violations
        {filtered.length !== violations.length && ` (${violations.length} total)`}
      </p>

      <div className="rounded-lg border border-border overflow-hidden">
        <Table className="min-w-[960px]">
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-xs w-20">Severity</TableHead>
              <TableHead className="text-xs w-16">Source</TableHead>
              <TableHead className="text-xs w-16">SC</TableHead>
              <TableHead className="text-xs">Criterion</TableHead>
              <TableHead className="text-xs w-14">Level</TableHead>
              <TableHead className="text-xs">Reason</TableHead>
              <TableHead className="text-xs w-24">Element</TableHead>
              <TableHead className="text-xs w-16">Fix</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.slice(0, visibleCount).map((v, i) => (
              <TableRow key={i} className="hover:bg-muted/30">
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
                <TableCell>
                  <Badge
                    variant="outline"
                    className={cn("text-[10px]", sourceColors[v.source] || sourceColors.unknown)}
                  >
                    {v.source}
                  </Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{v.wcag_sc ?? "—"}</TableCell>
                <TableCell className="text-xs">{v.criterion_name ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant={v.level === "A" ? "default" : "outline"} className="text-[10px]">{v.level ?? "—"}</Badge>
                </TableCell>
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span tabIndex={0} className="text-xs text-muted-foreground cursor-help">
                        {v.reason.length > 80 ? v.reason.slice(0, 80) + "…" : v.reason}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-sm text-xs">{v.reason}</TooltipContent>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <code className="text-[10px] text-muted-foreground bg-muted px-1 py-0.5 rounded truncate block max-w-[120px]">
                    {v.element_html}
                  </code>
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
            Show more ({filtered.length - visibleCount} remaining)
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
          helpUrl={modalData.help_url}
        />
      )}
    </div>
  );
}
