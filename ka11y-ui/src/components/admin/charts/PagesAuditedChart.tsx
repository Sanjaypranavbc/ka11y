"use client";

import { useId } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { PagesPerDayPoint } from "@/lib/admin/data";
import { formatDate, formatNumber } from "@/lib/admin/format";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import type { Lang } from "@/lib/i18n/translations";

const LINE = "var(--color-adm-chart-completed)";

/** "2026-09-24" -> local-independent Date at UTC midnight, so the label is the day the API meant. */
function dayIso(date: string) {
  return `${date}T00:00:00Z`;
}

function shortDay(date: string, lang: Lang) {
  return new Intl.DateTimeFormat(lang === "jp" ? "ja-JP" : "en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(
    new Date(dayIso(date)),
  );
}

function longDay(date: string, lang: Lang) {
  return new Intl.DateTimeFormat(lang === "jp" ? "ja-JP" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(dayIso(date)));
}

/**
 * Pages audited per day, last 30 days. One series, so the title names it and
 * there is no legend. The SVG is decorative (aria-hidden); the visually hidden
 * table below is the accessible equivalent, and the summary line gives sighted
 * and AT users the same headline numbers (WCAG 1.1.1 / 1.4.1).
 */
export function PagesAuditedChart({ points }: { points: PagesPerDayPoint[] }) {
  const { t, lang } = useLanguage();
  const headingId = useId();
  const c = t.admin.overview.pagesPerDay;
  const total = points.reduce((sum, p) => sum + p.pages, 0);
  const peak = points.reduce<PagesPerDayPoint | null>((best, p) => (best === null || p.pages > best.pages ? p : best), null);
  const data = points.map((p) => ({ ...p, label: shortDay(p.date, lang) }));

  return (
    // `relative` contains the visually hidden table (position: absolute) and
    // the recharts tooltip wrapper inside this card. The title/subtitle sit in
    // their own block so they stack in normal flow no matter how the flex
    // column or the chart's ResizeObserver measure — they were reported as
    // rendering on top of each other in some environments.
    <section aria-labelledby={headingId} className="relative flex flex-col rounded-2xl border border-adm-border bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="block shrink-0">
        <h2 id={headingId} className="block text-[17px] font-semibold leading-6 text-gray-100">
          {c.title}
        </h2>
        <p className="mt-0.5 block text-[13px] leading-5 text-gray-80">{c.description}</p>
      </div>
      {/* Fixed-height, clipped box: the SVG can never spill over the header. */}
      <div aria-hidden="true" className="admin-chart relative mt-4 h-44 w-full shrink-0 overflow-hidden">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} accessibilityLayer={false} tabIndex={-1} margin={{ top: 8, right: 28, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-adm-border)" />
            {/* First and last day always labelled; the rest thin out as the card narrows. */}
            <XAxis
              dataKey="date"
              tickFormatter={(v: string) => shortDay(v, lang)}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-gray-80)", fontSize: 12 }}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              allowDecimals={false}
              width={36}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "var(--color-gray-80)", fontSize: 12 }}
              tickFormatter={(v: number) => formatNumber(v, lang)}
            />
            <Tooltip
              cursor={{ stroke: "var(--color-gray-60)", strokeWidth: 1, strokeDasharray: "3 3" }}
              isAnimationActive={false}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as PagesPerDayPoint;
                return (
                  <div className="rounded-lg border border-adm-border bg-white px-3 py-2 text-[13px] leading-5 shadow-[0_4px_12px_rgba(0,0,0,0.1)]">
                    <p className="text-gray-80">{longDay(p.date, lang)}</p>
                    <p className="font-semibold tabular-nums text-gray-100">{c.pagesValue(formatNumber(p.pages, lang))}</p>
                  </div>
                );
              }}
            />
            <Line
              type="monotone"
              dataKey="pages"
              stroke={LINE}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, fill: LINE, stroke: "#ffffff", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 border-t border-adm-border pt-3 text-[14px] leading-5 text-gray-100">
        <span className="font-semibold tabular-nums">{formatNumber(total, lang)}</span> {c.summaryTotal}
        {peak && peak.pages > 0 && (
          <>
            {" · "}
            {c.summaryPeak(formatNumber(peak.pages, lang), formatDate(dayIso(peak.date), lang))}
          </>
        )}
      </p>
      <table className="sr-only bottom-0 left-0">
        <caption>{c.tableCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{c.date}</th>
            <th scope="col">{c.pages}</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.date}>
              <th scope="row">
                <time dateTime={p.date}>{longDay(p.date, lang)}</time>
              </th>
              <td>{formatNumber(p.pages, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
