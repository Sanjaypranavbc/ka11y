import { Button } from "@/components/ui/button";
import { Download, Menu, ExternalLink, Moon, Sun } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";
import { Lang } from "@/i18n/translations";
import { cn } from "@/lib/utils";

interface DashboardHeaderProps {
  url: string;
  generatedAt: string;
  reportLang?: string;
  activeRun?: { url: string; lang: string; submitted_at: string } | null;
  onExportJSON: () => void;
  onToggleSidebar: () => void;
  isDarkMode: boolean;
  onToggleTheme: () => void;
}

export function DashboardHeader({
  url,
  generatedAt,
  reportLang,
  activeRun,
  onExportJSON,
  onToggleSidebar,
  isDarkMode,
  onToggleTheme,
}: DashboardHeaderProps) {
  const { t, lang, setLang } = useLanguage();

  const displayUrl = activeRun?.url || url;
  const displayTime = activeRun?.submitted_at || generatedAt;
  const isRunning = !!activeRun;

  const ts = displayTime ? new Date(displayTime).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  }) : null;

  return (
    <header className="min-h-12 border-b border-border bg-background/95 backdrop-blur-sm px-3 sm:px-4 py-2 flex items-center justify-between shrink-0 gap-2 sm:gap-4 flex-wrap">
      <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
          onClick={onToggleSidebar}
          aria-label={t("header.openNav")}
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </Button>

        {/* Audited URL */}
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="hidden sm:inline text-[9px] font-semibold tracking-[0.16em] uppercase text-muted-foreground shrink-0">
            {t("header.target")}
          </span>
          <span className={cn(
            "text-xs font-mono truncate max-w-[48vw] sm:max-w-[38vw]",
            isRunning ? "text-primary animate-pulse" : "text-foreground"
          )}>
            {displayUrl}
          </span>
          {!isRunning && <ExternalLink className="hidden sm:block h-2.5 w-2.5 text-muted-foreground/50 shrink-0" aria-hidden="true" />}
        </div>

        {/* Report Language Badge */}
        {(reportLang || activeRun?.lang) && (
          <div className="flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded bg-muted border border-border">
            <span className="text-[8px] font-bold uppercase text-muted-foreground leading-none">
              {t("header.reportLanguage")}
            </span>
            <span className="text-[9px] font-black uppercase text-foreground leading-none">
              {activeRun?.lang || reportLang}
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 ml-auto">
        {ts && (
          <span className="text-[10px] font-mono text-muted-foreground hidden sm:block">
            {ts}
          </span>
        )}

        {/* UI Language switcher */}
        <div
          className="flex rounded-md overflow-hidden border border-border text-[10px] font-semibold"
          role="group"
          aria-label="UI Language"
        >
          {(["en", "ja"] as Lang[]).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => setLang(code)}
              aria-pressed={lang === code}
              className={cn(
                "px-2 py-1 transition-colors cursor-pointer uppercase",
                lang === code
                  ? "bg-primary text-primary-foreground"
                  : "bg-input text-muted-foreground hover:text-foreground",
              )}
            >
              {code}
            </button>
          ))}
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={onToggleTheme}
          aria-label={isDarkMode ? t("header.toLightMode") : t("header.toDarkMode")}
          title={isDarkMode ? t("header.toLightMode") : t("header.toDarkMode")}
          className="h-7 text-[10px] font-mono uppercase border-border text-muted-foreground hover:text-foreground hover:border-primary/50 px-2 sm:px-3"
        >
          {isDarkMode ? <Sun className="h-3 w-3 sm:mr-1.5" aria-hidden="true" /> : <Moon className="h-3 w-3 sm:mr-1.5" aria-hidden="true" />}
          <span className="hidden sm:inline">{isDarkMode ? t("header.light") : t("header.dark")}</span>
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={onExportJSON}
          disabled={isRunning || !url}
          className="h-7 text-[10px] font-mono tracking-wider uppercase border-border text-muted-foreground hover:text-foreground hover:border-primary/50 px-2 sm:px-3"
        >
          <Download className="h-3 w-3 sm:mr-1.5" aria-hidden="true" />
          <span className="hidden sm:inline">{t("header.export")}</span>
        </Button>
      </div>
    </header>
  );
}
