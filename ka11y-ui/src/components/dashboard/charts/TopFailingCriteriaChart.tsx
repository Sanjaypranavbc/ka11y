"use client";

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartCard, LegendItem } from "@/components/dashboard/ChartCard";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { TopFailingCriterion, WcagLevel } from "@/lib/wcagAudit";

const LEVEL_COLOR: Record<WcagLevel, string> = {
  A: "var(--color-level-a)",
  AA: "var(--color-level-aa)",
  AAA: "var(--color-level-aaa)",
};

export function TopFailingCriteriaChart({ criteria }: { criteria: TopFailingCriterion[] }) {
  const { t } = useLanguage();
  const DATA = criteria.map((row) => ({
    name: `${row.code} ${row.label}`,
    count: row.count,
    fill: LEVEL_COLOR[row.level],
  }));
  const maxCount = Math.max(1, ...criteria.map((row) => row.count));

  return (
    <ChartCard
      title={t.dashboardPage.charts.topFailingCriteria}
      legend={
        <>
          <LegendItem color={LEVEL_COLOR.A} label={t.dashboardPage.charts.level("A")} />
          <LegendItem color={LEVEL_COLOR.AA} label={t.dashboardPage.charts.level("AA")} />
          <LegendItem color={LEVEL_COLOR.AAA} label={t.dashboardPage.charts.level("AAA")} />
        </>
      }
    >
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={DATA} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid horizontal={false} stroke="var(--color-gray-40)" strokeDasharray="3 3" />
            <XAxis
              type="number"
              domain={[0, maxCount]}
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
