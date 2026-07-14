"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard, LegendItem } from "@/components/dashboard/ChartCard";
import { topFailingCriteria, type WcagLevel } from "@/lib/dashboardData";

const LEVEL_COLOR: Record<WcagLevel, string> = {
  A: "var(--color-level-a)",
  AA: "var(--color-level-aa)",
  AAA: "var(--color-level-aaa)",
};

const DATA = topFailingCriteria
  .slice()
  .sort((a, b) => b.count - a.count)
  .map((row) => ({
    name: `${row.code} ${row.label}`,
    count: row.count,
    fill: LEVEL_COLOR[row.level],
  }));

export function TopFailingCriteriaChart() {
  return (
    <ChartCard
      title="Top Failing WCAG Criteria"
      legend={
        <>
          <LegendItem color={LEVEL_COLOR.A} label="Level A" />
          <LegendItem color={LEVEL_COLOR.AA} label="Level AA" />
          <LegendItem color={LEVEL_COLOR.AAA} label="Level AAA" />
        </>
      }
    >
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={DATA} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid horizontal={false} stroke="var(--color-gray-40)" strokeDasharray="3 3" />
            <XAxis
              type="number"
              domain={[0, 20]}
              ticks={[0, 5, 10, 15, 20]}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--color-gray-60)", fontSize: 12 }}
            />
            <YAxis
              type="category"
              dataKey="name"
              tickLine={false}
              axisLine={false}
              width={190}
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
            <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false}>
              {DATA.map((d) => (
                <Cell key={d.name} fill={d.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
