import { AuditResult, RunTiming } from "@/types/audit";
import { ContrastReportSection } from "./ContrastReportSection";
import { StageTimingsCard } from "./StageTimingsCard";
import { MetricCard } from "./MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Legend, Tooltip,
} from "recharts";
import { AlertTriangle, HelpCircle, CheckCircle2, Activity } from "lucide-react";
import { useLanguage } from "@/i18n/LanguageContext";

interface DashboardTabProps {
  result: AuditResult;
  timing?: RunTiming | null;
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "hsl(0, 84%, 60%)",
  high:     "hsl(22, 98%, 56%)",
  medium:   "hsl(45, 100%, 50%)",
  low:      "hsl(199, 78%, 56%)",
};

const SOURCE_COLORS = {
  violations:   "hsl(0, 84%, 58%)",
  needs_review: "hsl(213, 94%, 55%)",
  passes:       "hsl(151, 68%, 46%)",
};

const LEVEL_COLORS: Record<string, string> = {
  A: "hsl(213, 94%, 55%)",
  AA: "hsl(199, 78%, 56%)",
  AAA: "hsl(277, 70%, 62%)",
};

// Compliance-score colour band: green ≥ 90, amber ≥ 70, red below.
function scoreColor(score: number): string {
  if (score >= 90) return "hsl(151, 68%, 46%)";
  if (score >= 70) return "hsl(45, 100%, 45%)";
  return "hsl(0, 84%, 58%)";
}

export function DashboardTab({ result, timing }: DashboardTabProps) {
  const isMobile = useIsMobile();
  const { t } = useLanguage();

  // Severity breakdown
  const severityCounts = result.violations.reduce(
    (acc, v) => {
      acc[v.severity] = (acc[v.severity] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
  const severityData = Object.entries(severityCounts).map(([name, value]) => ({
    name: name.charAt(0).toUpperCase() + name.slice(1),
    value,
    fill: SEVERITY_COLORS[name],
  }));

  // Source breakdown
  const sourceData = (() => {
    const sourceNames = [
      ...new Set(
        [...result.violations, ...result.needs_review, ...result.passes]
          .map((f) => f.source || "unknown")
      ),
    ].sort();

    const rows = sourceNames.map((name) => ({
      name,
      violations: 0,
      needs_review: 0,
      passes: 0,
    }));
    const bySource = new Map(rows.map((r) => [r.name, r]));

    result.violations.forEach((v) => {
      const bucket = bySource.get(v.source || "unknown");
      if (bucket) bucket.violations++;
    });
    result.needs_review.forEach((v) => {
      const bucket = bySource.get(v.source || "unknown");
      if (bucket) bucket.needs_review++;
    });
    result.passes.forEach((v) => {
      const bucket = bySource.get(v.source || "unknown");
      if (bucket) bucket.passes++;
    });

    return rows;
  })();

  // WCAG Level breakdown
  const wcagLevels = (() => {
    const levels: Record<string, { violations: number; needs_review: number; passes: number }> = {};
    ["A", "AA", "AAA"].forEach((l) => (levels[l] = { violations: 0, needs_review: 0, passes: 0 }));
    result.violations.forEach((v) => { if (levels[v.level]) levels[v.level].violations++; });
    result.needs_review.forEach((v) => { if (levels[v.level]) levels[v.level].needs_review++; });
    result.passes.forEach((v) => { if (levels[v.level]) levels[v.level].passes++; });
    return Object.entries(levels).map(([level, counts]) => ({ level: `Level ${level}`, ...counts }));
  })();

  // Top failing WCAG criteria
  const topCriteria = (() => {
    const counts: Record<string, { sc: string; name: string; count: number; level: string }> = {};
    result.violations.forEach((v) => {
      const key = v.wcag_sc;
      if (!counts[key]) counts[key] = { sc: v.wcag_sc ?? "?", name: v.criterion_name ?? "", count: 0, level: v.level ?? "" };
      counts[key].count++;
    });
    return Object.values(counts)
      .sort((a, b) => b.count - a.count)
      .slice(0, 8)
      .map((c) => ({ name: `${c.sc} ${c.name}`, value: c.count, level: c.level }));
  })();

  const severityChartConfig = {
    Critical: { label: "Critical", color: SEVERITY_COLORS.critical },
    High: { label: "High", color: SEVERITY_COLORS.high },
    Medium: { label: "Medium", color: SEVERITY_COLORS.medium },
    Low: { label: "Low", color: SEVERITY_COLORS.low },
  };

  const sourceChartConfig = {
    violations: { label: "Violations", color: SOURCE_COLORS.violations },
    needs_review: { label: "Needs Review", color: SOURCE_COLORS.needs_review },
    passes: { label: "Passes", color: SOURCE_COLORS.passes },
  };
  const sourceNamesForLabel = sourceData.map((row) => row.name).join(", ");

  const pageCount = result.pages?.length ?? 0;

  return (
    <div className="space-y-5 p-3 sm:p-5 grid-bg min-h-full">
      {/* Overall compliance score */}
      <Card className="animate-fade-up">
        <CardContent className="flex items-center justify-between gap-4 py-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-widest text-muted-foreground font-semibold">
              {t("dashboard.score")}
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {pageCount > 1
                ? t("dashboard.scoreAcrossPages", { n: pageCount })
                : t("dashboard.scoreHint")}
            </div>
          </div>
          <div className="flex items-baseline gap-1 shrink-0" aria-label={`${t("dashboard.score")}: ${result.score}%`}>
            <span className="text-4xl font-bold tabular-nums" style={{ color: scoreColor(result.score) }}>
              {result.score}
            </span>
            <span className="text-lg font-semibold" style={{ color: scoreColor(result.score) }}>%</span>
          </div>
        </CardContent>
      </Card>

      {/* Metric cards — staggered reveal */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: t("dashboard.totalFindings"),  value: result.total,              variant: "default"  as const, icon: <Activity className="h-5 w-5" />,     delay: "delay-0"   },
          { label: t("dashboard.violations"),     value: result.violations_count,   variant: "critical" as const, icon: <AlertTriangle className="h-5 w-5" />, delay: "delay-75"  },
          { label: t("dashboard.needsReview"),    value: result.needs_review_count, variant: "serious"  as const, icon: <HelpCircle className="h-5 w-5" />,    delay: "delay-150" },
          { label: t("dashboard.passes"),         value: result.passes_count,       variant: "success"  as const, icon: <CheckCircle2 className="h-5 w-5" />,  delay: "delay-225" },
        ].map((m) => (
          <div key={m.label} className={`animate-fade-up ${m.delay}`}>
            <MetricCard label={m.label} value={m.value} variant={m.variant} icon={m.icon} />
          </div>
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 animate-fade-up delay-300">
        {/* Severity Pie */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{t("dashboard.bySeverity")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={severityChartConfig} className="h-56 sm:h-64" role="img" tabIndex={0} aria-label={`Pie chart: ${severityData.map((d) => `${d.name} ${d.value}`).join(", ")}`}>
              <PieChart>
                <Pie data={severityData} cx="50%" cy="50%" innerRadius={50} outerRadius={90} dataKey="value" paddingAngle={2}>
                  {severityData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent />} />
                <Legend formatter={(value) => <span className="text-xs text-muted-foreground">{value}</span>} />
              </PieChart>
            </ChartContainer>
          </CardContent>
        </Card>

        {/* Source Bar */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{t("dashboard.bySource")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer
              config={sourceChartConfig}
              className="h-56 sm:h-64"
              role="img"
              tabIndex={0}
              aria-label={`Bar chart showing violations, needs review, and passes by source: ${sourceNamesForLabel || "none"}`}
            >
              <BarChart data={sourceData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="name" className="text-xs" />
                <YAxis className="text-xs" />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="violations" fill={SOURCE_COLORS.violations} radius={[4, 4, 0, 0]} />
                <Bar dataKey="needs_review" fill={SOURCE_COLORS.needs_review} radius={[4, 4, 0, 0]} />
                <Bar dataKey="passes" fill={SOURCE_COLORS.passes} radius={[4, 4, 0, 0]} />
                <Legend formatter={(value) => <span className="text-xs capitalize">{value.replaceAll("_", " ")}</span>} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      {/* WCAG Level Breakdown */}
      <Card className="animate-fade-up delay-450">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{t("dashboard.levelBreakdown")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartContainer config={sourceChartConfig} className="h-44 sm:h-48">
            <BarChart data={wcagLevels} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis type="number" className="text-xs" />
              <YAxis dataKey="level" type="category" width={70} className="text-xs" />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="violations" fill={SOURCE_COLORS.violations} radius={[0, 4, 4, 0]} />
              <Bar dataKey="needs_review" fill={SOURCE_COLORS.needs_review} radius={[0, 4, 4, 0]} />
              <Bar dataKey="passes" fill={SOURCE_COLORS.passes} radius={[0, 4, 4, 0]} />
              <Legend formatter={(value) => <span className="text-xs capitalize">{value.replace("_", " ")}</span>} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      {/* Top Failing WCAG */}
      <Card className="animate-fade-up delay-600">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{t("dashboard.topFailing")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64 sm:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topCriteria} layout="vertical" margin={{ left: isMobile ? 0 : 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis type="number" className="text-xs" />
                <YAxis dataKey="name" type="category" width={isMobile ? 120 : 200} className="text-xs" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {topCriteria.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={LEVEL_COLORS[entry.level] ?? "hsl(199, 78%, 56%)"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-3 sm:gap-5 mt-2 justify-center flex-wrap" aria-hidden="true">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <div className="w-2.5 h-2.5" style={{ background: LEVEL_COLORS.A }} /> Level A
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <div className="w-2.5 h-2.5" style={{ background: LEVEL_COLORS.AA }} /> Level AA
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <div className="w-2.5 h-2.5" style={{ background: LEVEL_COLORS.AAA }} /> Level AAA
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Findings by Page — only meaningful for multi-page crawls (max_depth > 0) */}
      {(result.pages?.length ?? 0) > 1 && (
        <Card className="animate-fade-up delay-450">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{t("dashboard.byPage")}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-border">
                    <th className="py-1.5 pr-3 font-semibold">{t("dashboard.pageColumn")}</th>
                    <th className="py-1.5 px-2 text-right font-semibold">{t("dashboard.scoreColumn")}</th>
                    <th className="py-1.5 px-2 text-right font-semibold">{t("dashboard.findingsColumn")}</th>
                    <th className="py-1.5 px-2 text-right font-semibold">{t("dashboard.violations")}</th>
                    <th className="py-1.5 px-2 text-right font-semibold">{t("dashboard.needsReview")}</th>
                    <th className="py-1.5 pl-2 text-right font-semibold">{t("dashboard.passes")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.pages!.map((p) => (
                    <tr key={p.page_url} className="border-b border-border/50 last:border-0">
                      <td className="py-1.5 pr-3 max-w-[280px] sm:max-w-[420px] truncate font-mono" title={p.page_url}>
                        <a
                          href={p.page_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-primary hover:underline"
                        >
                          {p.page_url}
                        </a>
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono font-semibold" style={{ color: scoreColor(p.summary.score) }}>
                        {p.summary.score}%
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono font-semibold text-foreground">
                        {p.summary.total_findings}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono" style={{ color: SOURCE_COLORS.violations }}>
                        {p.summary.violations}
                      </td>
                      <td className="py-1.5 px-2 text-right font-mono" style={{ color: SOURCE_COLORS.needs_review }}>
                        {p.summary.needs_review}
                      </td>
                      <td className="py-1.5 pl-2 text-right font-mono" style={{ color: SOURCE_COLORS.passes }}>
                        {p.summary.passes}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stage timings — same data as logs/run_timings.log */}
      <StageTimingsCard timing={timing ?? null} />

      {/* Contrast report — rendered only when OCR produced contrast data */}
      {result.contrast_report && result.contrast_report.images.length > 0 && (
        <ContrastReportSection report={result.contrast_report} />
      )}
    </div>
  );
}
