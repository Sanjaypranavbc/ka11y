"use client";

import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";
import { ChartCard, LegendItem } from "@/components/dashboard/ChartCard";
import { sitePerformanceScore } from "@/lib/dashboardData";

const DATA = [{ name: "score", value: sitePerformanceScore, fill: "var(--color-brand-teal)" }];

export function PerformanceGauge() {
  return (
    <ChartCard
      title="Site Performance Score"
      legend={
        <>
          <LegendItem color="var(--color-brand-teal)" label="Pass Percentage" />
          <LegendItem color="var(--color-gray-40)" label="Action Needed" />
        </>
      }
    >
      <div className="relative h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            data={DATA}
            innerRadius="70%"
            outerRadius="100%"
            startAngle={90}
            endAngle={-270}
            barSize={28}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
            <RadialBar
              dataKey="value"
              cornerRadius={999}
              background={{ fill: "var(--color-gray-40)" }}
              isAnimationActive={false}
            />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="text-h1 font-medium text-brand-gray">{sitePerformanceScore}%</span>
        </div>
      </div>
    </ChartCard>
  );
}
