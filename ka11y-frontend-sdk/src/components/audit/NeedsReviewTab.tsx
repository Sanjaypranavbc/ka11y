import { useState, useMemo, useEffect } from "react";
import { AuditNeedsReview } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SuggestedFixModal } from "./SuggestedFixModal";
import { AlertTriangle, Wrench, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface NeedsReviewTabProps {
  items: AuditNeedsReview[];
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

export function NeedsReviewTab({ items, pageSize = 50 }: NeedsReviewTabProps) {
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [modalData, setModalData] = useState<AuditNeedsReview | null>(null);
  const [visibleCount, setVisibleCount] = useState(pageSize);

  const allSeverities = useMemo(() => {
    const preferred = ["critical", "high", "medium", "low"];
    const present = [...new Set(items.map((v) => v.severity).filter(Boolean))] as string[];
    const ordered = preferred.filter((s) => present.includes(s));
    const extras = present.filter((s) => !preferred.includes(s)).sort();
    return [...ordered, ...extras];
  }, [items]);
  const allSources = useMemo(
    () => [...new Set(items.map((v) => v.source).filter(Boolean))].sort(),
    [items]
  );
  const allScs = useMemo(
    () => [...new Set(items.map((v) => v.wcag_sc).filter(Boolean))].sort() as string[],
    [items]
  );

  const filtered = useMemo(() => {
    return items.filter((v) => {
      if (severityFilter.length && !severityFilter.includes(v.severity)) return false;
      if (sourceFilter.length && !sourceFilter.includes(v.source)) return false;
      if (scFilter.length && !scFilter.includes(v.wcag_sc)) return false;
      if (!search) return true;
      const q = search.toLowerCase();
      return v.reason.toLowerCase().includes(q) || v.element_html.toLowerCase().includes(q);
    });
  }, [items, search, severityFilter, sourceFilter, scFilter]);

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
  }, [pageSize, search, severityFilter, sourceFilter, scFilter]);

  const hasFilters = search || severityFilter.length || sourceFilter.length || scFilter.length;

  return (
    <div className="p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      <div className="bg-moderate/10 border border-moderate/30 rounded-lg p-4 flex items-start gap-3" role="note">
        <AlertTriangle className="h-5 w-5 text-moderate shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-foreground">
          These items require manual verification — automated tools could not determine pass/fail.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search reason or HTML..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 h-8 text-xs"
        />

        <div role="group" aria-label="Filter by severity" className="flex gap-1">
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

        <div role="group" aria-label="Filter by source" className="flex gap-1">
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
        Showing {Math.min(visibleCount, filtered.length)} of {filtered.length} items
        {filtered.length !== items.length && ` (${items.length} total)`}
      </p>

      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-xs">Severity</TableHead>
              <TableHead className="text-xs">Source</TableHead>
              <TableHead className="text-xs">SC</TableHead>
              <TableHead className="text-xs">Criterion</TableHead>
              <TableHead className="text-xs">Reason</TableHead>
              <TableHead className="text-xs">Fix</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
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
                <TableCell className="text-xs text-muted-foreground max-w-xs truncate">{v.reason}</TableCell>
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
