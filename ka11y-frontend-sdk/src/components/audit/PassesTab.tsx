import { useState } from "react";
import { AuditPass } from "@/types/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface PassesTabProps {
  passes: AuditPass[];
}

export function PassesTab({ passes }: PassesTabProps) {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({ axe: true, python: true });
  const [visibleCounts, setVisibleCounts] = useState<Record<string, number>>({});

  const grouped = passes.reduce(
    (acc, p) => {
      (acc[p.source] = acc[p.source] || []).push(p);
      return acc;
    },
    {} as Record<string, AuditPass[]>
  );

  const toggle = (source: string) => {
    setOpenSections((prev) => ({ ...prev, [source]: !prev[source] }));
  };

  const showMore = (source: string) => {
    setVisibleCounts((prev) => ({ ...prev, [source]: (prev[source] ?? 50) + 50 }));
  };

  return (
    <div className="p-5 space-y-4 grid-bg min-h-full animate-fade-up delay-0">
      {Object.entries(grouped).map(([source, items]) => {
        const visible = visibleCounts[source] ?? 50;
        return (
          <Collapsible key={source} open={openSections[source]} onOpenChange={() => toggle(source)}>
            <CollapsibleTrigger className="flex items-center gap-2 w-full p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors">
              <ChevronDown className={cn("h-4 w-4 transition-transform", openSections[source] && "rotate-180")} />
              <span className="text-sm font-medium capitalize">{source}</span>
              <Badge variant="secondary" className="text-[10px] ml-auto">{items.length} passes</Badge>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="rounded-lg border border-border overflow-hidden mt-2">
                <Table>
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
                    {items.slice(0, visible).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono text-xs">{p.rule_id}</TableCell>
                        <TableCell className="font-mono text-xs">{p.wcag_sc}</TableCell>
                        <TableCell className="text-xs">{p.criterion_name}</TableCell>
                        <TableCell><Badge variant="outline" className="text-[10px]">{p.level}</Badge></TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-xs truncate">{p.reason}</TableCell>
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
