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
import { AuditForm } from "@/components/audit/AuditForm";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { AuditConfig, TabValue } from "@/types/audit";
import { AlertTriangle, Plus } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";
import { AuditProgress } from "@/components/audit/AuditProgress";

const MAX_ROWS_STORAGE_KEY = "ka11y_max_rows";
const THEME_STORAGE_KEY = "ka11y_theme";

const DEFAULT_CONFIG: AuditConfig = {
  url: "",
  max_depth: 0,
  internal_links: true,
  max_pages: 50,
  wcag_level: "AAA",
  lang: "auto",
  run_ocr: true,
  run_image_audit: true,
  run_form_audit: true,
  run_label_in_name_audit: true,
  run_pause_stop_hide_audit: true,
  run_target_size_audit: true,
  run_media_audit: true,
  run_captions_audit: true,
  run_sensory_audit: true,
  run_resize_text_audit: true,
  run_reflow_audit: true,
  run_text_spacing_audit: true,
  run_orientation_audit: true,
  run_hover_focus_content_audit: true,
  run_focus_not_obscured_min_audit: true,
  run_focus_not_obscured_enh_audit: true,
  run_node_audit: true,
};

const Index = () => {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabValue>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [config, setConfig] = useState<AuditConfig>(() => ({
    ...DEFAULT_CONFIG,
    url: localStorage.getItem("ka11y_last_url") ?? "",
  }));
  const [maxRows, setMaxRows] = useState<number>(() => {
    const raw = localStorage.getItem(MAX_ROWS_STORAGE_KEY);
    const parsed = raw ? parseInt(raw, 10) : 50;
    return Number.isNaN(parsed) ? 50 : Math.max(10, Math.min(500, parsed));
  });
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark" || raw === "system") return raw;
    return "dark";
  });
  const [systemPrefersDark, setSystemPrefersDark] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)").matches : false
  );
  const {
    result,
    jobStatus,
    error,
    failure,
    runAudit,
    exportJSON,
    currentStage,
    stages,
    plan,
    stageProgress,
    warnings,
    activeRun,
    timing,
  } = useAudit();

  const isLoading = jobStatus === "pending" || jobStatus === "running";

  // Aggregated summary across all crawled pages — the default "All pages" scope
  // for the per-page selector in the finding tabs.
  const overallSummary = {
    score: result.score,
    violations: result.violations_count,
    needs_review: result.needs_review_count,
    passes: result.passes_count,
    total: result.total,
  };

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
        onNewAudit={() => setAuditDrawerOpen(true)}
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
          onNewAudit={() => setAuditDrawerOpen(true)}
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
              <AuditProgress
                plan={plan}
                stages={stages}
                currentStage={currentStage}
                stageProgress={stageProgress}
                failure={failure}
                jobStatus={jobStatus}
              />
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
            /* ── Error: reuse AuditProgress so the user sees which stage failed,
                 the full traceback accordion, and the partial stage timeline. */
            <div className="p-3 sm:p-5 space-y-3">
              <div role="alert" className="flex items-center gap-2 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="font-semibold">{t("state.auditFailed")}</span>
                <span className="text-muted-foreground">·</span>
                <span className="text-muted-foreground truncate">
                  {failure?.error || error || t("state.unknownError")}
                </span>
              </div>
              <AuditProgress
                plan={plan}
                stages={stages}
                currentStage={currentStage}
                stageProgress={stageProgress}
                failure={failure}
                jobStatus={jobStatus}
              />
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
            <div className="flex items-start justify-center min-h-full p-4 sm:p-8">
              <div className="w-full max-w-lg space-y-6 animate-fade-up">
                <div className="text-center space-y-3 pt-2 sm:pt-6">
                  <div
                    className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-indigo-500 via-primary to-emerald-400 shadow"
                    aria-hidden="true"
                  />
                  <h1 className="text-4xl sm:text-5xl font-extrabold tracking-[-0.04em] text-foreground leading-none">
                    kao <span className="text-primary">a11y</span>
                  </h1>
                  <p className="text-sm text-muted-foreground max-w-xs mx-auto">
                    {t("state.welcomeHint")}
                  </p>
                </div>
                <div className="rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm">
                  <AuditForm
                    config={config}
                    onConfigChange={setConfig}
                    onRunAudit={runAudit}
                    jobStatus={jobStatus}
                    currentStage={currentStage}
                  />
                </div>
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
              {activeTab === "dashboard"           && <DashboardTab result={result} timing={timing} />}
              {activeTab === "violations"          && <ViolationsTab violations={result.violations} pages={result.pages} overall={overallSummary} pageSize={maxRows} />}
              {activeTab === "needs-review"        && <NeedsReviewTab items={result.needs_review} pages={result.pages} overall={overallSummary} pageSize={maxRows} />}
              {activeTab === "passes"              && <PassesTab passes={result.passes} pages={result.pages} overall={overallSummary} pageSize={maxRows} />}
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

      {/* New-audit drawer — re-run / tweak config without leaving the report */}
      <Sheet open={auditDrawerOpen} onOpenChange={setAuditDrawerOpen}>
        <SheetContent side="right" className="w-[min(92vw,30rem)] overflow-y-auto">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Plus className="h-4 w-4 text-primary" aria-hidden="true" />
              {t("sidebar.newAudit")}
            </SheetTitle>
          </SheetHeader>
          <div className="mt-5">
            <AuditForm
              config={config}
              onConfigChange={setConfig}
              onRunAudit={runAudit}
              jobStatus={jobStatus}
              currentStage={currentStage}
              onSubmitted={() => setAuditDrawerOpen(false)}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default Index;
