import { Button } from "@/components/ui/button";
import { Download, Menu, ExternalLink } from "lucide-react";

interface DashboardHeaderProps {
  url: string;
  generatedAt: string;
  onExportJSON: () => void;
  onToggleSidebar: () => void;
}

export function DashboardHeader({ url, generatedAt, onExportJSON, onToggleSidebar }: DashboardHeaderProps) {
  return (
    <header className="h-14 border-b border-border bg-card px-4 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        <Button variant="ghost" size="icon" className="md:hidden shrink-0" onClick={onToggleSidebar}>
          <Menu className="h-5 w-5" />
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium text-foreground truncate">{url}</span>
            <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0" />
          </div>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted-foreground hidden sm:block">
          {new Date(generatedAt).toLocaleString()}
        </span>
        <Button variant="outline" size="sm" onClick={onExportJSON}>
          <Download className="h-3.5 w-3.5 mr-1.5" />
          Export JSON
        </Button>
      </div>
    </header>
  );
}
