import { RunTiming } from "@/types/audit";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";
import { TranslationKey } from "@/i18n/translations";

interface Props {
  timing: RunTiming | null;
}

function fmt(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds >= 60) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }
  return `${seconds.toFixed(2)}s`;
}

const STATUS_BAR: Record<string, string> = {
  completed: "hsl(151, 68%, 46%)",
  running: "hsl(213, 94%, 55%)",
  error: "hsl(0, 84%, 58%)",
};

/**
 * Per-stage timing breakdown — the same data the backend appends to
 * logs/run_timings.log, fetched live from GET /combined/{job_id}/timings.
 *
 * Stages are sorted slowest-first (the panel exists to surface where time
 * went). Bars are scaled to the slowest stage, NOT to wall time, because
 * stages overlap (axe-core + the Python branch run concurrently) so their
 * durations do not sum to the wall clock.
 */
export function StageTimingsCard({ timing }: Props) {
  const { t } = useLanguage();
  if (!timing || !timing.stages || timing.stages.length === 0) return null;

  const labelFor = (key: string | null) =>
    key ? (t(`stageFull.${key}` as TranslationKey) || key) : "—";

  const stages = [...timing.stages].sort(
    (a, b) => (b.duration_s ?? -1) - (a.duration_s ?? -1),
  );
  const maxDur = Math.max(1, ...stages.map((s) => s.duration_s ?? 0));

  const totals: { label: string; value: string }[] = [
    { label: t("timing.queueWait"), value: fmt(timing.queue_wait_s) },
    { label: t("timing.runTime"), value: fmt(timing.run_s) },
    { label: t("timing.wallTime"), value: fmt(timing.wall_s) },
  ];

  return (
    <Card className="animate-fade-up delay-600">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" aria-hidden="true" />
          {t("timing.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Run-level totals */}
        <div className="grid grid-cols-3 gap-2">
          {totals.map((m) => (
            <div
              key={m.label}
              className="rounded border border-border bg-background/40 px-3 py-2"
            >
              <div className="text-[9px] uppercase tracking-widest text-muted-foreground font-semibold">
                {m.label}
              </div>
              <div className="text-base font-mono font-semibold tabular-nums text-foreground mt-0.5">
                {m.value}
              </div>
            </div>
          ))}
        </div>

        {/* Per-stage bars */}
        <div className="space-y-2">
          {stages.map((s, i) => {
            const dur = s.duration_s ?? 0;
            const pct = Math.round((dur / maxDur) * 100);
            const color = STATUS_BAR[s.status ?? ""] ?? "hsl(199, 78%, 56%)";
            return (
              <div key={`${s.name}-${i}`} className="space-y-0.5">
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="font-mono truncate text-foreground" title={labelFor(s.name)}>
                    {labelFor(s.name)}
                  </span>
                  <span className="font-mono tabular-nums shrink-0 text-muted-foreground">
                    {s.findings_count !== null && s.findings_count !== undefined && (
                      <span className="hidden sm:inline mr-3 text-muted-foreground/70">
                        {s.findings_count} {t("timing.findings")}
                      </span>
                    )}
                    <span className="text-foreground font-semibold">{fmt(s.duration_s)}</span>
                  </span>
                </div>
                <div
                  className="h-1.5 rounded-full bg-muted/40 overflow-hidden"
                  role="img"
                  aria-label={`${labelFor(s.name)}: ${fmt(s.duration_s)}`}
                >
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${pct}%`, background: color }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        <p className="text-[10px] text-muted-foreground leading-snug">
          {t("timing.hint")}
        </p>
      </CardContent>
    </Card>
  );
}
