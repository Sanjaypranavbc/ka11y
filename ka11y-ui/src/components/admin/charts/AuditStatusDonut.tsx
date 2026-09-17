"use client";

import { useId } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import type { AuditStatusSlice } from "@/lib/admin/data";
import { formatNumber, formatPercent } from "@/lib/admin/format";
import { useLanguage } from "@/components/dashboard/LanguageContext";

const COLOR: Record<AuditStatusSlice["status"], string> = {
  completed: "var(--color-adm-chart-completed)",
  running: "var(--color-adm-chart-running)",
  failed: "var(--color-adm-chart-failed)",
  cancelled: "var(--color-adm-chart-cancelled)",
};

/**
 * Donut + a real table. The SVG is aria-hidden and not focusable; the table
 * beside it is the accessible equivalent (WCAG 1.1.1 / 1.4.1) and doubles as
 * the visible legend, so sighted and AT users read the same numbers.
 */
export function AuditStatusDonut({ slices }: { slices: AuditStatusSlice[] }) {
  const { t, lang } = useLanguage();
  const headingId = useId();
  const total = slices.reduce((sum, s) => sum + s.count, 0);
  const data = slices.map((s) => ({ ...s, name: t.admin.status[s.status], fill: COLOR[s.status] }));

  return (
    <section aria-labelledby={headingId} className="flex flex-col rounded-2xl border border-adm-border bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <h2 id={headingId} className="text-[17px] font-semibold leading-6 text-gray-100">
        {t.admin.overview.auditStatus.title}
      </h2>
      <p className="mt-0.5 text-[13px] leading-5 text-gray-80">{t.admin.overview.auditStatus.description(formatNumber(total, lang))}</p>
      <div className="mt-4 flex flex-col items-center gap-6 sm:flex-row">
        <div aria-hidden="true" className="admin-chart relative h-44 w-44 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart accessibilityLayer={false} tabIndex={-1}>
              <Pie
                data={data}
                dataKey="count"
                nameKey="name"
                innerRadius="68%"
                outerRadius="100%"
                stroke="#ffffff"
                strokeWidth={3}
                startAngle={90}
                endAngle={-270}
                isAnimationActive={false}
                // The pie group is focusable by default; the table is the accessible surface.
                rootTabIndex={-1}
              >
                {data.map((d) => (
                  <Cell key={d.status} fill={d.fill} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[22px] font-semibold leading-7 text-gray-100">{formatNumber(total, lang)}</span>
            <span className="text-[12px] leading-4 text-gray-80">{t.admin.overview.auditStatus.totalAudits}</span>
          </div>
        </div>
        <table className="w-full text-[14px] leading-5">
          <caption className="sr-only">{t.admin.overview.auditStatus.tableCaption}</caption>
          <thead className="sr-only">
            <tr>
              <th scope="col">{t.admin.overview.auditStatus.status}</th>
              <th scope="col">{t.admin.overview.auditStatus.count}</th>
              <th scope="col">{t.admin.overview.auditStatus.share}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.status} className="border-b border-adm-border last:border-0">
                <th scope="row" className="py-2 pr-3 text-left font-normal text-gray-100">
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.fill }} />
                    {d.name}
                  </span>
                </th>
                <td className="py-2 pr-3 text-right font-medium tabular-nums text-gray-100">{formatNumber(d.count, lang)}</td>
                <td className="py-2 text-right tabular-nums text-gray-80">{formatPercent(d.count, total, lang)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
