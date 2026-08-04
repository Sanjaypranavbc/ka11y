"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard, LegendItem } from "@/components/dashboard/ChartCard";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { LevelBreakdownRow } from "@/lib/wcagAudit";

export function WcagLevelBarChart({ breakdown }: { breakdown: LevelBreakdownRow[] }) {
  const { t } = useLanguage();
  const DATA = breakdown.map((row) => ({
    level: t.dashboardPage.charts.level(row.level),
    Violations: row.violations,
    "Needs Review": row.needsReview,
    Passes: row.passes,
  }));
  const maxCount = Math.max(1, ...breakdown.map((row) => row.violations + row.needsReview + row.passes));

  return (
    <ChartCard
      title={t.dashboardPage.charts.wcagLevelBreakdown}
      legend={
        <>
          <LegendItem color="var(--color-status-violation)" label={t.dashboardPage.charts.violations} />
          <LegendItem color="var(--color-status-review)" label={t.dashboardPage.charts.needsReview} />
          <LegendItem color="var(--color-status-pass)" label={t.dashboardPage.charts.passes} />
        </>
      }
    >
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={DATA} barGap={4}>
            <CartesianGrid vertical={false} stroke="var(--color-gray-40)" strokeDasharray="3 3" />
            <XAxis
              dataKey="level"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--color-gray-60)", fontSize: 13 }}
            />
            <YAxis
              domain={[0, maxCount]}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--color-gray-60)", fontSize: 12 }}
            />
            <Tooltip
              cursor={{ fill: "var(--color-gray-10)" }}
              contentStyle={{
                borderRadius: 10,
                border: "none",
                boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                fontSize: 14,
                padding: "10px 14px",
              }}
            />
            <Bar dataKey="Violations" fill="var(--color-status-violation)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Needs Review" fill="var(--color-status-review)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="Passes" fill="var(--color-status-pass)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
