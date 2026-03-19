import { useState } from "react";
import { useAudit } from "@/hooks/useAudit";
import { AuditSidebar } from "@/components/audit/AuditSidebar";
import { DashboardHeader } from "@/components/audit/DashboardHeader";
import { DashboardTab } from "@/components/audit/DashboardTab";
import { ViolationsTab } from "@/components/audit/ViolationsTab";
import { NeedsReviewTab } from "@/components/audit/NeedsReviewTab";
import { PassesTab } from "@/components/audit/PassesTab";
import { ImageVisualisationTab } from "@/components/audit/ImageVisualisationTab";
import { SettingsTab } from "@/components/audit/SettingsTab";
import { Skeleton } from "@/components/ui/skeleton";
import { TabValue, StageInfo } from "@/types/audit";
import { AlertTriangle, CheckCircle, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<string, string> = {
  axe_core:        "axe-core WCAG scan",
  image_audit:     "Image alt-text (1.1.1)",
  form_audit:      "Form fields (3.3.1 / 3.3.2)",
  label_in_name:   "Label in name (2.5.3)",
  pause_stop_hide: "Moving content (2.2.2)",
  target_size:     "Target size (2.5.8)",
};

function StageProgress({ stages, currentStage }: { stages: StageInfo[]; currentStage: string }) {
  return (
    <div className="rounded border border-border bg-card p-4 space-y-2.5">
      <p className="text-[9px] font-semibold tracking-[0.18em] uppercase text-muted-foreground">
        Audit Progress
      </p>
      <div className="space-y-1.5">
        {stages.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin text-primary shrink-0" aria-hidden="true" />
            <span>Initialising audit…</span>
          </div>
        ) : (
          stages.map((stage) => (
            <div key={stage.name} className="flex items-center gap-2 text-xs">
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
                  "font-mono",
                  stage.status === "running"   && "text-primary font-medium",
                  stage.status === "completed" && "text-muted-foreground",
                  stage.status === "error"     && "text-destructive",
                )}
              >
                {STAGE_LABELS[stage.name] ?? stage.name}
              </span>
              {stage.status === "completed" && stage.findings_count !== undefined && (
                <span className="text-muted-foreground ml-auto font-mono">
                  {stage.findings_count} findings
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
            <span className="font-mono">{STAGE_LABELS[currentStage] ?? currentStage}</span>
          </div>
        )}
      </div>
    </div>
  );
}

const Index = () => {
  const [activeTab, setActiveTab] = useState<TabValue>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { result, jobStatus, error, runAudit, exportJSON, currentStage, stages, warnings } =
    useAudit();

  const isLoading = jobStatus === "pending" || jobStatus === "running";

  return (
    <div className="h-screen flex bg-background overflow-hidden">
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
          onExportJSON={exportJSON}
          onToggleSidebar={() => setSidebarOpen(true)}
        />

        <main className="flex-1 overflow-y-auto grid-bg" aria-busy={isLoading} aria-live="polite">
          {/* ── Loading ────────────────────────────────────────────── */}
          {isLoading ? (
            <div className="p-5 space-y-3">
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
                <h2 className="text-lg font-semibold text-foreground">Audit Failed</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  {error || "An unknown error occurred."}
                </p>
              </div>
            </div>

          ) : jobStatus === "idle" ? (
            /* ── Empty / welcome ────────────────────────────────────── */
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-4">
                <h1 className="text-5xl font-extrabold tracking-[-0.04em] text-foreground leading-none">
                  ka<span className="text-primary">11</span>y
                </h1>
                <p className="text-sm text-muted-foreground max-w-xs">
                  Enter a URL in the sidebar and run an audit to see accessibility findings.
                </p>
              </div>
            </div>

          ) : (
            /* ── Results ────────────────────────────────────────────── */
            <>
              {warnings && warnings.length > 0 && (
                <div className="mx-5 mt-4 px-3 py-2 rounded border border-serious/30 bg-serious/5 text-xs text-serious font-mono space-y-0.5">
                  <p className="font-semibold uppercase tracking-wider text-[9px]">Warnings</p>
                  {warnings.map((w, i) => (
                    <p key={i}>{w}</p>
                  ))}
                </div>
              )}
              {activeTab === "dashboard"           && <DashboardTab result={result} />}
              {activeTab === "violations"          && <ViolationsTab violations={result.violations} />}
              {activeTab === "needs-review"        && <NeedsReviewTab items={result.needs_review} />}
              {activeTab === "passes"              && <PassesTab passes={result.passes} />}
              {activeTab === "image-visualisation" && <ImageVisualisationTab contrastReport={result.contrast_report} />}
              {activeTab === "settings"            && <SettingsTab />}
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export default Index;