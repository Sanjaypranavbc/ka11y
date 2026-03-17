import { useState, useMemo } from "react";
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
};

export function ViolationsTab({ violations }: ViolationsTabProps) {
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string[]>([]);
  const [scFilter, setScFilter] = useState<string[]>([]);
  const [modalData, setModalData] = useState<AuditViolation | null>(null);

  const allSeverities = ["critical", "high", "medium", "low"];
  const allSources = ["axe", "python"];
  const allScs = useMemo(() => [...new Set(violations.map((v) => v.wcag_sc))].sort(), [violations]);

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
  };

  const clearFilters = () => {
    setSearch("");
    setSeverityFilter([]);
    setSourceFilter([]);
    setScFilter([]);
  };

  const hasFilters = search || severityFilter.length || sourceFilter.length || scFilter.length;

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search reason or HTML..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 h-8 text-xs"
        />

        {/* Severity filters */}
        <div className="flex gap-1">
          {allSeverities.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(severityFilter, s, setSeverityFilter)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                severityFilter.includes(s) ? severityColors[s] : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Source filters */}
        <div className="flex gap-1">
          {allSources.map((s) => (
            <button
              key={s}
              onClick={() => toggleFilter(sourceFilter, s, setSourceFilter)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium border transition-colors",
                sourceFilter.includes(s) ? sourceColors[s] : "bg-muted text-muted-foreground border-border"
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {/* WCAG SC filter - show as scrollable row */}
        <div className="flex gap-1 flex-wrap">
          {allScs.slice(0, 8).map((sc) => (
            <button
              key={sc}
              onClick={() => toggleFilter(scFilter, sc, setScFilter)}
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
        Showing {filtered.length} of {violations.length} violations
      </p>

      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
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
            {filtered.slice(0, 50).map((v, i) => (
              <TableRow key={i} className="hover:bg-muted/30">
                <TableCell>
                  <Badge className={cn("text-[10px]", severityColors[v.severity])}>{v.severity}</Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn("text-[10px]", sourceColors[v.source])}>{v.source}</Badge>
                </TableCell>
                <TableCell className="font-mono text-xs">{v.wcag_sc}</TableCell>
                <TableCell className="text-xs">{v.criterion_name}</TableCell>
                <TableCell>
                  <Badge variant={v.level === "A" ? "default" : "outline"} className="text-[10px]">{v.level}</Badge>
                </TableCell>
                <TableCell>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-xs text-muted-foreground cursor-help">
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
                  <Button variant="ghost" size="sm" onClick={() => setModalData(v)} className="h-6 text-[10px]">
                    <Wrench className="h-3 w-3" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

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
