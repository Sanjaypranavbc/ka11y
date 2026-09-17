"use client";

import { useId } from "react";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import type { SeverityCount } from "@/lib/admin/data";
import { formatCompact, formatNumber } from "@/lib/admin/format";
import { useLanguage } from "@/components/dashboard/LanguageContext";

const COLOR: Record<SeverityCount["severity"], string> = {
  critical: "var(--color-adm-sev-critical)",
  serious: "var(--color-adm-sev-serious)",
  moderate: "var(--color-adm-sev-moderate)",
  minor: "var(--color-adm-sev-minor)",
};

export function FailsBySeverityChart({ counts }: { counts: SeverityCount[] }) {
  const { t, lang } = useLanguage();
  const headingId = useId();
  const data = counts.map((c) => ({
    ...c,
    name: t.admin.severity[c.severity],
    label: formatCompact(c.count, lang),
    fill: COLOR[c.severity],
  }));

  return (
    <section aria-labelledby={headingId} className="flex flex-col rounded-2xl border border-adm-border bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <h2 id={headingId} className="text-[17px] font-semibold leading-6 text-gray-100">
        {t.admin.overview.severity.title}
      </h2>
      <p className="mt-0.5 text-[13px] leading-5 text-gray-80">{t.admin.overview.severity.description}</p>
      <div aria-hidden="true" className="admin-chart mt-4 h-44 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} accessibilityLayer={false} tabIndex={-1} margin={{ top: 20, right: 8, left: 8, bottom: 0 }} barCategoryGap="28%">
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "var(--color-gray-80)", fontSize: 12 }} />
            <YAxis hide domain={[0, "dataMax"]} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.severity} fill={d.fill} />
              ))}
              <LabelList dataKey="label" position="top" style={{ fill: "var(--color-gray-100)", fontSize: 12, fontWeight: 600 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="mt-3 w-full text-[14px] leading-5">
        <caption className="sr-only">{t.admin.overview.severity.tableCaption}</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">{t.admin.overview.severity.severity}</th>
            <th scope="col">{t.admin.overview.severity.fails}</th>
          </tr>
        </thead>
        <tbody className="grid grid-cols-1 gap-x-4 min-[420px]:grid-cols-2 sm:grid-cols-4">
          {data.map((d) => (
            <tr key={d.severity} className="flex items-center justify-between gap-2 border-t border-adm-border py-2 sm:flex-col sm:items-start sm:gap-0.5">
              <th scope="row" className="font-normal text-gray-80">
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: d.fill }} />
                  {d.name}
                </span>
              </th>
              <td className="font-semibold tabular-nums text-gray-100">{formatNumber(d.count, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
