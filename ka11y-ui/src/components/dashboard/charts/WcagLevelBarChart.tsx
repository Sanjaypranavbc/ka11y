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
import { wcagLevelBreakdown } from "@/lib/dashboardData";

const DATA = wcagLevelBreakdown.map((row) => ({
  level: `Level ${row.level}`,
  Violations: row.violations,
  "Needs Review": row.needsReview,
  Passes: row.passes,
}));

export function WcagLevelBarChart() {
  return (
    <ChartCard
      title="WCAG Level Breakdown"
      legend={
        <>
          <LegendItem color="var(--color-status-violation)" label="Violations" />
          <LegendItem color="var(--color-status-review)" label="Needs Review" />
          <LegendItem color="var(--color-status-pass)" label="Passes" />
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
              domain={[0, 250]}
              ticks={[0, 50, 100, 150, 200, 250]}
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
