import { useEffect, useState } from "react";
import { useAudit } from "@/hooks/useAudit";
import { AuditSidebar } from "@/components/audit/AuditSidebar";
import { DashboardHeader } from "@/components/audit/DashboardHeader";
import { DashboardTab } from "@/components/audit/DashboardTab";
import { ViolationsTab } from "@/components/audit/ViolationsTab";
import { NeedsReviewTab } from "@/components/audit/NeedsReviewTab";
import { PassesTab } from "@/components/audit/PassesTab";
import { ImageVisualisationTab } from "@/components/audit/ImageVisualisationTab";
import { SettingsTab, ThemePreference } from "@/components/audit/SettingsTab";
import { WcagRulesTab } from "@/components/audit/WcagRulesTab";
import { RuleEvaluatorTab } from "@/components/audit/RuleEvaluatorTab";
import { Skeleton } from "@/components/ui/skeleton";
import { TabValue, StageInfo } from "@/types/audit";
import { AlertTriangle, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageContext";
import { TranslationKey } from "@/i18n/translations";

const MAX_ROWS_STORAGE_KEY = "ka11y_max_rows";
const THEME_STORAGE_KEY = "ka11y_theme";

function StageProgress({ stages, currentStage }: { stages: StageInfo[]; currentStage: string }) {
  const { t } = useLanguage();
  return (
    <div className="rounded border border-border bg-card p-4 space-y-2.5">
      <p className="text-[9px] font-semibold tracking-[0.18em] uppercase text-muted-foreground">
        {t("progress.title")}
      </p>
      <div className="space-y-1.5">
        {stages.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" aria-hidden="true" />
            <span>{t("progress.initialising")}</span>
          </div>
        ) : (
          stages.map((stage) => (
            <div key={stage.name} className="flex items-center gap-2 text-xs min-w-0">
              {stage.status === "running" && (
                <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" aria-hidden="true" />
              )}
              {stage.status === "completed" && (
                <CheckCircle className="h-3 w-3 text-success shrink-0" aria-hidden="true" />
              )}
              {stage.status === "error" && (
                <XCircle className="h-3 w-3 text-destructive shrink-0" aria-hidden="true" />
              )}
              <span
                className={cn(
                  "font-mono truncate",
                  stage.status === "running"   && "text-primary font-medium",
                  stage.status === "completed" && "text-muted-foreground",
                  stage.status === "error"     && "text-destructive",
                )}
              >
                {t((`stageFull.${stage.name}`) as TranslationKey) || stage.name}
              </span>
              {stage.status === "completed" && stage.findings_count !== undefined && (
                <span className="text-muted-foreground ml-auto font-mono hidden sm:inline">
                  {stage.findings_count} {t("progress.findings")}
                </span>
              )}
              {stage.status === "error" && stage.error && (
                <span className="text-destructive/70 text-[10px] ml-auto truncate max-w-[140px]" title={stage.error}>
                  {stage.error}
                </span>
              )}
            </div>
          ))
        )}
        {/* Show next pending stage hint */}
        {currentStage && stages.every((s) => s.status !== "running") && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" aria-hidden="true" />
            <span className="font-mono">{t((`stageFull.${currentStage}`) as TranslationKey) || currentStage}</span>
          </div>
        )}
      </div>
    </div>
  );
}

const Index = () => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabValue>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [maxRows, setMaxRows] = useState<number>(() => {
    const raw = localStorage.getItem(MAX_ROWS_STORAGE_KEY);
    const parsed = raw ? parseInt(raw, 10) : 50;
    return Number.isNaN(parsed) ? 50 : Math.max(10, Math.min(500, parsed));
  });
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
    return "system";
  });
  const [systemPrefersDark, setSystemPrefersDark] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)").matches : false
  );
  const { result, jobStatus, error, runAudit, exportJSON, currentStage, stages, warnings, activeRun } =
    useAudit();

  const isLoading = jobStatus === "pending" || jobStatus === "running";

  const handleMaxRowsChange = (value: number) => {
    const clamped = Math.max(10, Math.min(500, value));
    setMaxRows(clamped);
    localStorage.setItem(MAX_ROWS_STORAGE_KEY, String(clamped));
  };

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemPrefersDark(mediaQuery.matches);
    const applyTheme = () => {
      setSystemPrefersDark(mediaQuery.matches);
      const shouldUseDark =
        themePreference === "dark" ||
        (themePreference === "system" && mediaQuery.matches);
      document.documentElement.classList.toggle("dark", shouldUseDark);
      document.documentElement.style.colorScheme = shouldUseDark ? "dark" : "light";
    };

    applyTheme();
    localStorage.setItem(THEME_STORAGE_KEY, themePreference);

    if (themePreference !== "system") return;
    const onMediaChange = () => applyTheme();
    mediaQuery.addEventListener("change", onMediaChange);
    return () => mediaQuery.removeEventListener("change", onMediaChange);
  }, [themePreference]);

  const isDarkMode = themePreference === "dark" || (themePreference === "system" && systemPrefersDark);

  const handleToggleTheme = () => {
    setThemePreference((prev) => {
      const resolvedDark = prev === "dark" || (prev === "system" && systemPrefersDark);
      return resolvedDark ? "light" : "dark";
    });
  };

  return (
    <div className="h-dvh min-h-screen flex bg-background overflow-hidden">
      <AuditSidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onRunAudit={runAudit}
        jobStatus={jobStatus}
        currentStage={currentStage}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <DashboardHeader
          url={result.url}
          generatedAt={result.generated_at}
          reportLang={result.lang}
          activeRun={activeRun}
          onExportJSON={exportJSON}
          onToggleSidebar={() => setSidebarOpen(true)}
          isDarkMode={isDarkMode}
          onToggleTheme={handleToggleTheme}
        />

        <main className="flex-1 overflow-y-auto grid-bg" aria-busy={isLoading} aria-live="polite">
          {/* ── WCAG Rules tab is always available regardless of audit state ── */}
          {activeTab === "wcag-rules" ? (
            <WcagRulesTab />
          ) : isLoading ? (
            <div className="p-3 sm:p-5 space-y-3">
              <StageProgress stages={stages} currentStage={currentStage} />
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {[...Array(4)].map((_, i) => (
                  <Skeleton key={i} className="h-24" />
                ))}
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <Skeleton className="h-72" />
                <Skeleton className="h-72" />
              </div>
              <Skeleton className="h-48" />
            </div>

          ) : jobStatus === "failed" ? (
            /* ── Error ─────────────────────────────────────────────── */
            <div className="flex items-center justify-center h-full">
              <div role="alert" className="text-center space-y-3">
                <AlertTriangle className="h-12 w-12 text-destructive mx-auto" aria-hidden="true" />
                <h2 className="text-lg font-semibold text-foreground">{t("state.auditFailed")}</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  {error || t("state.unknownError")}
                </p>
              </div>
            </div>

          ) : jobStatus === "idle" ? (
            /* ── Empty / welcome ────────────────────────────────────── */
            activeTab === "rule-evaluator" ? (
              <RuleEvaluatorTab />
            ) : activeTab === "settings" ? (
              <SettingsTab
                maxRows={maxRows}
                onMaxRowsChange={handleMaxRowsChange}
                themePreference={themePreference}
                onThemePreferenceChange={setThemePreference}
              />
            ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-4">
                <h1 className="text-5xl font-extrabold tracking-[-0.04em] text-foreground leading-none">
                  ka<span className="text-primary">11</span>y
                </h1>
                <p className="text-sm text-muted-foreground max-w-xs">
                  {t("state.welcomeHint")}
                </p>
              </div>
            </div>
            )

          ) : (
            /* ── Results ────────────────────────────────────────────── */
            <>
              {warnings && warnings.length > 0 && (
                <div className="mx-3 sm:mx-5 mt-4 px-3 py-2 rounded border border-serious/30 bg-serious/5 text-xs text-serious font-mono space-y-0.5">
                  <p className="font-semibold uppercase tracking-wider text-[9px]">{t("state.warnings")}</p>
                  {warnings.map((w, i) => (
                    <p key={i}>{w}</p>
                  ))}
                </div>
              )}
              {activeTab === "dashboard"           && <DashboardTab result={result} />}
              {activeTab === "violations"          && <ViolationsTab violations={result.violations} pageSize={maxRows} />}
              {activeTab === "needs-review"        && <NeedsReviewTab items={result.needs_review} pageSize={maxRows} />}
              {activeTab === "passes"              && <PassesTab passes={result.passes} pageSize={maxRows} />}
              {activeTab === "image-visualisation" && (
                <ImageVisualisationTab
                  contrastReport={result.contrast_report}
                  imageAuditReport={result.image_audit_report}
                />
              )}
              {activeTab === "rule-evaluator"      && <RuleEvaluatorTab />}
              {activeTab === "settings"            && (
                <SettingsTab
                  maxRows={maxRows}
                  onMaxRowsChange={handleMaxRowsChange}
                  themePreference={themePreference}
                  onThemePreferenceChange={setThemePreference}
                />
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export default Index;
