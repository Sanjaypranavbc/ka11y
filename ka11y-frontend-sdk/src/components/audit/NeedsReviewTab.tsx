import { useState, useMemo } from "react";
import { AuditNeedsReview } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SuggestedFixModal } from "./SuggestedFixModal";
import { AlertTriangle, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";

interface NeedsReviewTabProps {
  items: AuditNeedsReview[];
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

export function NeedsReviewTab({ items }: NeedsReviewTabProps) {
  const [search, setSearch] = useState("");
  const [modalData, setModalData] = useState<AuditNeedsReview | null>(null);

  const filtered = useMemo(() => {
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((v) => v.reason.toLowerCase().includes(q) || v.element_html.toLowerCase().includes(q));
  }, [items, search]);

  return (
    <div className="p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      <div className="bg-moderate/10 border border-moderate/30 rounded-lg p-4 flex items-start gap-3" role="note">
        <AlertTriangle className="h-5 w-5 text-moderate shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-foreground">
          These items require manual verification — automated tools could not determine pass/fail.
        </p>
      </div>

      <Input
        placeholder="Search..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-64 h-8 text-xs"
      />

      <p className="text-xs text-muted-foreground">
        Showing {filtered.length} of {items.length} items
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
            {filtered.map((v, i) => (
              <TableRow key={i}>
                <TableCell><Badge className={cn("text-[10px]", v.severity ? severityColors[v.severity] : "bg-muted text-muted-foreground")}>{v.severity ?? "—"}</Badge></TableCell>
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
