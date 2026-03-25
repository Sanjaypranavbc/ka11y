import { Button } from "@/components/ui/button";
import { Download, Menu, ExternalLink, Moon, Sun } from "lucide-react";

interface DashboardHeaderProps {
  url: string;
  generatedAt: string;
  onExportJSON: () => void;
  onToggleSidebar: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export function DashboardHeader({
  url,
  generatedAt,
  onExportJSON,
  onToggleSidebar,
  isDarkMode,
  onToggleTheme,
}: DashboardHeaderProps) {
  const ts = generatedAt ? new Date(generatedAt).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }) : null;

  return (
    <header className="h-12 border-b border-border bg-background/95 backdrop-blur-sm px-3 sm:px-4 flex items-center justify-between shrink-0 gap-2 sm:gap-4">
      <div className="flex items-center gap-3 min-w-0">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
          onClick={onToggleSidebar}
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </Button>

        {/* Audited URL */}
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="hidden sm:inline text-[9px] font-semibold tracking-[0.16em] uppercase text-muted-foreground shrink-0">
            target
          </span>
          <span className="text-xs font-mono text-foreground truncate max-w-[44vw] sm:max-w-[38vw]">{url}</span>
          <ExternalLink className="h-2.5 w-2.5 text-muted-foreground/50 shrink-0" aria-hidden="true" />
        </div>
      </div>

      <div className="flex items-center gap-4 shrink-0">
        {ts && (
          <span className="text-[10px] font-mono text-muted-foreground hidden sm:block">
            {ts}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={onToggleTheme}
          aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
          className="h-7 text-[10px] font-mono uppercase border-border text-muted-foreground hover:text-foreground hover:border-primary/50 px-2 sm:px-3"
        >
          {isDarkMode ? <Sun className="h-3 w-3 sm:mr-1.5" aria-hidden="true" /> : <Moon className="h-3 w-3 sm:mr-1.5" aria-hidden="true" />}
          <span className="hidden sm:inline">{isDarkMode ? "Light" : "Dark"}</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onExportJSON}
          className="h-7 text-[10px] font-mono tracking-wider uppercase border-border text-muted-foreground hover:text-foreground hover:border-primary/50 px-2 sm:px-3"
        >
          <Download className="h-3 w-3 sm:mr-1.5" aria-hidden="true" />
          <span className="hidden sm:inline">Export</span>
        </Button>
      </div>
    </header>
  );
}
