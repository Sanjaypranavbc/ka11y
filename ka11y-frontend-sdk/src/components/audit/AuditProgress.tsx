import { AlertTriangle, CheckCircle, Loader2, XCircle } from "lucide-react";
import { JobFailure, JobPlan, StageInfo, StageProgressInfo } from "@/types/audit";
import { Progress } from "@/components/ui/progress";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import { useLanguage } from "@/i18n/LanguageContext";
import { TranslationKey } from "@/i18n/translations";

interface Props {
  plan: JobPlan | null;
  stages: StageInfo[];
  currentStage: string;
  stageProgress: StageProgressInfo | null;
  failure: JobFailure | null;
  jobStatus: "idle" | "pending" | "running" | "completed" | "failed";
}

/** Weighted percent-complete. Unknown stages contribute 0 so the bar never jumps back. */
function computeOverallPct(
  plan: JobPlan | null,
  stages: StageInfo[],
  progress: StageProgressInfo | null,
): number {
  if (!plan || plan.weight_total <= 0) return 0;
  const weightFor = (key: string) =>
    plan.stages.find((s) => s.key === key)?.weight ?? 0;

  let done = 0;
  for (const s of stages) {
    if (s.status === "completed" || s.status === "error") {
      done += weightFor(s.name);
    }
  }

  // Add partial credit for the currently running stage using its inner progress.
  if (progress && progress.total > 0) {
    const stillRunning = stages.find(
      (s) => s.name === progress.stage_name && s.status === "running",
    );
    if (stillRunning) {
      const frac = Math.min(1, Math.max(0, progress.current / progress.total));
      done += weightFor(progress.stage_name) * frac;
    }
  }

  return Math.min(100, Math.round((done / plan.weight_total) * 100));
}

export function AuditProgress({
  plan,
  stages,
  currentStage,
  stageProgress,
  failure,
  jobStatus,
}: Props) {
  const { t } = useLanguage();
  const pct = computeOverallPct(plan, stages, stageProgress);
  const isTerminal = jobStatus === "completed" || jobStatus === "failed";

  const labelFor = (key: string) =>
    (t((`stageFull.${key}`) as TranslationKey) || key);

  // Build the merged stage list: plan order wins, but show live status from `stages`.
  const rows = plan
    ? plan.stages.map((planStage) => {
        const live = stages.find((s) => s.name === planStage.key);
        return {
          key: planStage.key,
          weight: planStage.weight,
          status: live?.status ?? ("pending" as const),
          findings_count: live?.findings_count,
          error: live?.error,
        };
      })
    : stages.map((s) => ({
        key: s.name,
        weight: s.weight ?? 1,
        status: s.status,
        findings_count: s.findings_count,
        error: s.error,
      }));

  return (
    <div className="rounded border border-border bg-card p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[9px] font-semibold tracking-[0.18em] uppercase text-muted-foreground">
          {t("progress.title")}
        </p>
        <span className="text-xs font-mono text-muted-foreground tabular-nums">
          {pct}%
        </span>
      </div>

      {/* Outer weighted progress bar */}
      <Progress
        value={pct}
        className={cn(
          "h-2",
          jobStatus === "failed" && "[&>div]:bg-destructive",
        )}
      />

      {/* Inner per-stage progress, only while a stage is actively reporting */}
      {!isTerminal && stageProgress && stageProgress.total > 0 && (
        <div className="space-y-1 pt-1">
          <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
            <span className="truncate">
              {labelFor(stageProgress.stage_name)}
              {stageProgress.phase ? ` · ${stageProgress.phase}` : ""}
            </span>
            <span className="tabular-nums shrink-0 ml-2">
              {stageProgress.current}/{stageProgress.total}
            </span>
          </div>
          <Progress
            value={Math.min(
              100,
              Math.round((stageProgress.current / stageProgress.total) * 100),
            )}
            className="h-1 opacity-80"
          />
        </div>
      )}

      {/* Stage checklist */}
      <div className="space-y-1.5 pt-1">
        {rows.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2
              className="h-3 w-3 animate-spin text-primary shrink-0"
              aria-hidden="true"
            />
            <span>{t("progress.initialising")}</span>
          </div>
        ) : (
          rows.map((row) => {
            const isCurrent = row.status === "running" || row.key === currentStage;
            return (
              <div
                key={row.key}
                className="flex items-center gap-2 text-xs min-w-0"
              >
                {row.status === "running" && (
                  <Loader2
                    className="h-3 w-3 animate-spin text-primary shrink-0"
                    aria-hidden="true"
                  />
                )}
                {row.status === "completed" && (
                  <CheckCircle
                    className="h-3 w-3 text-success shrink-0"
                    aria-hidden="true"
                  />
                )}
                {row.status === "error" && (
                  <XCircle
                    className="h-3 w-3 text-destructive shrink-0"
                    aria-hidden="true"
                  />
                )}
                {row.status === "pending" && (
                  <span
                    className="h-3 w-3 rounded-full border border-border shrink-0"
                    aria-hidden="true"
                  />
                )}
                <span
                  className={cn(
                    "font-mono truncate",
                    row.status === "running" && "text-primary font-medium",
                    row.status === "completed" && "text-muted-foreground",
                    row.status === "error" && "text-destructive",
                    row.status === "pending" && "text-muted-foreground/70",
                  )}
                >
                  {labelFor(row.key)}
                </span>
                {row.status === "completed" && row.findings_count !== undefined && (
                  <span className="text-muted-foreground ml-auto font-mono hidden sm:inline tabular-nums">
                    {row.findings_count} {t("progress.findings")}
                  </span>
                )}
                {row.status === "error" && row.error && (
                  <span
                    className="text-destructive/70 text-[10px] ml-auto truncate max-w-[140px]"
                    title={row.error}
                  >
                    {row.error}
                  </span>
                )}
                {isCurrent && row.status === "running" && stageProgress
                  && stageProgress.stage_name === row.key
                  && stageProgress.total > 0 && (
                    <span className="text-muted-foreground/80 ml-auto font-mono hidden md:inline tabular-nums">
                      {stageProgress.current}/{stageProgress.total}
                    </span>
                  )}
              </div>
            );
          })
        )}
      </div>

      {/* Failure surface — full traceback in a collapsible accordion (user preference) */}
      {failure && (
        <Alert variant="destructive" className="mt-2">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle className="text-xs">
            {failure.stage
              ? `Audit failed in ${labelFor(failure.stage)}`
              : "Audit failed"}
          </AlertTitle>
          <AlertDescription className="text-[11px] font-mono break-all">
            {failure.error}
            {failure.location && (
              <span className="block opacity-70 mt-0.5">
                at {failure.location}
              </span>
            )}
            {failure.traceback && (
              <Accordion type="single" collapsible className="mt-2">
                <AccordionItem value="tb" className="border-0">
                  <AccordionTrigger className="py-1 text-[11px] font-mono hover:no-underline">
                    Show full traceback
                  </AccordionTrigger>
                  <AccordionContent>
                    <pre className="text-[10px] whitespace-pre-wrap break-all leading-snug bg-background/40 rounded p-2 max-h-64 overflow-auto">
                      {failure.traceback}
                    </pre>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            )}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
