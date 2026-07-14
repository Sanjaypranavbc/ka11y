"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { ChartCard, LegendItem } from "@/components/dashboard/ChartCard";
import { summaryTotals } from "@/lib/dashboardData";

const DATA = [
  { name: "Violations", value: summaryTotals.violations, color: "var(--color-status-violation)" },
  { name: "Needs Review", value: summaryTotals.needsReview, color: "var(--color-status-review)" },
  { name: "Passes", value: summaryTotals.passes, color: "var(--color-status-pass)" },
];

export function ViolationsPieChart() {
  return (
    <ChartCard
      title="Findings Overview"
      legend={DATA.map((d) => (
        <LegendItem key={d.name} color={d.color} label={d.name} />
      ))}
    >
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={DATA}
              dataKey="value"
              nameKey="name"
              innerRadius={0}
              outerRadius="90%"
              stroke="var(--background)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {DATA.map((d) => (
                <Cell key={d.name} fill={d.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                borderRadius: 10,
                border: "none",
                boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                fontSize: 14,
                padding: "10px 14px",
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
