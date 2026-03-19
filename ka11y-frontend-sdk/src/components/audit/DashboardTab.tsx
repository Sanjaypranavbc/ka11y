import { AuditResult } from "@/types/audit";
import { ContrastReportSection } from "./ContrastReportSection";
import { MetricCard } from "./MetricCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Legend, Tooltip,
} from "recharts";
import { BarChart3, AlertTriangle, HelpCircle, CheckCircle2, Activity } from "lucide-react";

interface DashboardTabProps {
  result: AuditResult;
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

export function DashboardTab({ result }: DashboardTabProps) {
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
    const axe = { name: "axe", violations: 0, needs_review: 0, passes: 0 };
    const python = { name: "python", violations: 0, needs_review: 0, passes: 0 };
    result.violations.forEach((v) => (v.source === "axe" ? axe : python).violations++);
    result.needs_review.forEach((v) => (v.source === "axe" ? axe : python).needs_review++);
    result.passes.forEach((v) => (v.source === "axe" ? axe : python).passes++);
    return [axe, python];
  })();

  // WCAG Level breakdown
  const wcagLevels = (() => {
    const levels: Record<string, { violations: number; needs_review: number; passes: number }> = {};
    ["A", "AA"].forEach((l) => (levels[l] = { violations: 0, needs_review: 0, passes: 0 }));
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

  return (
    <div className="space-y-5 p-5 grid-bg min-h-full">
      {/* Metric cards — staggered reveal */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Total Findings",  value: result.total,              variant: "default"  as const, icon: <Activity className="h-5 w-5" />,     delay: "delay-0"   },
          { label: "Violations",      value: result.violations_count,   variant: "critical" as const, icon: <AlertTriangle className="h-5 w-5" />, delay: "delay-75"  },
          { label: "Needs Review",    value: result.needs_review_count, variant: "serious"  as const, icon: <HelpCircle className="h-5 w-5" />,    delay: "delay-150" },
          { label: "Passes",          value: result.passes_count,       variant: "success"  as const, icon: <CheckCircle2 className="h-5 w-5" />,  delay: "delay-225" },
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
            <CardTitle className="text-sm font-medium">Violations by Severity</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={severityChartConfig} className="h-64" role="img" tabIndex={0} aria-label={`Pie chart: ${severityData.map((d) => `${d.name} ${d.value}`).join(", ")}`}>
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
            <CardTitle className="text-sm font-medium">Findings by Source</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={sourceChartConfig} className="h-64" role="img" tabIndex={0} aria-label="Bar chart showing violations, needs review, and passes broken down by axe and python sources">
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
          <CardTitle className="text-sm font-medium">WCAG Level Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartContainer config={sourceChartConfig} className="h-48">
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
          <CardTitle className="text-sm font-medium">Top Failing WCAG Criteria</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topCriteria} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis type="number" className="text-xs" />
                <YAxis dataKey="name" type="category" width={200} className="text-xs" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {topCriteria.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.level === "A" ? "hsl(213, 94%, 55%)" : "hsl(199, 78%, 56%)"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex gap-5 mt-2 justify-center" aria-hidden="true">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <div className="w-2.5 h-2.5" style={{ background: "hsl(213, 94%, 55%)" }} /> Level A
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <div className="w-2.5 h-2.5" style={{ background: "hsl(199, 78%, 56%)" }} /> Level AA
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Contrast report — rendered only when OCR produced contrast data */}
      {result.contrast_report && result.contrast_report.images.length > 0 && (
        <ContrastReportSection report={result.contrast_report} />
      )}
    </div>
  );
}
