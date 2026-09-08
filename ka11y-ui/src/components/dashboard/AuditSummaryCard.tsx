"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { DashboardSummary } from "@/lib/wcagAudit";

export function AuditSummaryCard({ summary }: { summary: DashboardSummary }) {
  const { t } = useLanguage();

  const total = summary.needsReview + summary.passes + summary.violations;

  const needsReviewPct = total > 0 ? ((summary.needsReview / total) * 100).toFixed(2).replace(/\.00$/, "") : "0";
  const passesPct = total > 0 ? ((summary.passes / total) * 100).toFixed(2).replace(/\.00$/, "") : "0";
  const failPct = total > 0 ? ((summary.violations / total) * 100).toFixed(1).replace(/\.0$/, "") : "0";

  const CHART_DATA = [
    { name: t.dashboardPage.charts.needsReview, value: summary.needsReview, color: "var(--color-status-review)" },
    { name: t.dashboardPage.charts.passes, value: summary.passes, color: "var(--color-status-pass)" },
    { name: t.dashboardPage.charts.violations, value: summary.violations, color: "var(--color-status-violation)" },
  ];

  return (
    <div className="w-full rounded-[16px] bg-gray-10 p-6 flex flex-col gap-6">
      <h2 className="text-[18px] font-medium leading-[26px] text-gray-100">
        {t.dashboardPage.charts.auditSummary}
      </h2>

      <div className="grid grid-cols-1 items-center gap-6 lg:grid-cols-12">
        {/* Left: Donut Chart with total count in center */}
        <div className="relative flex items-center justify-center lg:col-span-4">
          <div className="h-56 w-56 sm:h-64 sm:w-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={CHART_DATA}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={68}
                  outerRadius={95}
                  stroke="none"
                  paddingAngle={2}
                  isAnimationActive={false}
                >
                  {CHART_DATA.map((d) => (
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

          {/* Center text overlay inside Donut */}
          <div className="pointer-events-none absolute flex flex-col items-center justify-center text-center">
            <span className="text-[28px] font-bold leading-tight text-gray-100 sm:text-[32px]">
              {total}
            </span>
            <span className="text-[13px] font-normal leading-4 text-gray-80">
              {t.dashboardPage.charts.totalFindings}
            </span>
          </div>
        </div>

        {/* Right: 3 Stat Cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:col-span-8">

          {/* Needs Review Card */}
          <div className="flex flex-col justify-between rounded-[16px] bg-white p-5 shadow-xs border border-gray-40/30">
            <div className="flex items-center gap-2 text-[14px] font-medium text-gray-100">
              <span className="h-3 w-3 rounded-full bg-[var(--color-status-review)]" />
              {t.dashboardPage.charts.needsReview}
            </div>
            <div className="my-3 flex items-baseline gap-2 flex-wrap">
              <span className="text-[26px] font-bold leading-none text-gray-100">
                {summary.needsReview}
              </span>
              <span className="text-[14px] text-gray-80">
                {t.dashboardPage.charts.items} / {needsReviewPct}%
              </span>
            </div>
            <Link
              href="/dashboard/needs-review"
              className="inline-flex items-center gap-1.5 text-[14px] font-medium text-brand-teal hover:underline"
            >
              {t.dashboardPage.charts.reviewFindings}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>

          {/* Passes Card */}
          <div className="flex flex-col justify-between rounded-[16px] bg-white p-5 shadow-xs border border-gray-40/30">
            <div className="flex items-center gap-2 text-[14px] font-medium text-gray-100">
              <span className="h-3 w-3 rounded-full bg-[var(--color-status-pass)]" />
              {t.dashboardPage.charts.passes}
            </div>
            <div className="my-3 flex items-baseline gap-2 flex-wrap">
              <span className="text-[26px] font-bold leading-none text-gray-100">
                {summary.passes}
              </span>
              <span className="text-[14px] text-gray-80">
                {t.dashboardPage.charts.items} / {passesPct}%
              </span>
            </div>
            <Link
              href="/dashboard/passes"
              className="inline-flex items-center gap-1.5 text-[14px] font-medium text-brand-teal hover:underline"
            >
              {t.dashboardPage.charts.viewPassed}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>

          {/* Fail Card */}
          <div className="flex flex-col justify-between rounded-[16px] bg-white p-5 shadow-xs border border-gray-40/30">
            <div className="flex items-center gap-2 text-[14px] font-medium text-gray-100">
              <span className="h-3 w-3 rounded-full bg-[var(--color-status-violation)]" />
              {t.dashboardPage.charts.violations}
            </div>
            <div className="my-3 flex items-baseline gap-2 flex-wrap">
              <span className="text-[26px] font-bold leading-none text-gray-100">
                {summary.violations}
              </span>
              <span className="text-[14px] text-gray-80">
                {t.dashboardPage.charts.items} / {failPct}%
              </span>
            </div>
            <Link
              href="/dashboard/fail"
              className="inline-flex items-center gap-1.5 text-[14px] font-medium text-brand-teal hover:underline"
            >
              {t.dashboardPage.charts.viewFailed}
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>

        </div>
      </div>
    </div>
  );
}
