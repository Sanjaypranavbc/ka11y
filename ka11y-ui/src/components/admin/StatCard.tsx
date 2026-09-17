"use client";

import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { StatTrend } from "@/lib/admin/data";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  /** Full-precision value read to screen readers when `value` is compacted (e.g. "42.8K"). */
  valueLabel?: string;
  icon: ReactNode;
  iconTone?: "teal" | "amber" | "green";
  trend?: StatTrend;
  note?: string;
}

const TONE: Record<NonNullable<StatCardProps["iconTone"]>, string> = {
  teal: "bg-adm-completed-bg text-adm-completed",
  amber: "bg-adm-review-bg text-adm-review",
  green: "bg-adm-completed-bg text-adm-completed",
};

export function StatCard({ label, value, valueLabel, icon, iconTone = "teal", trend, note }: StatCardProps) {
  const { t } = useLanguage();
  const trendText =
    trend &&
    `${trend.direction === "up" ? t.admin.overview.stats.trendUp : trend.direction === "down" ? t.admin.overview.stats.trendDown : t.admin.overview.stats.trendFlat} ${t.admin.overview.stats.thisMonth(trend.value)}`;
  const TrendIcon = trend?.direction === "down" ? ArrowDown : trend?.direction === "flat" ? Minus : ArrowUp;

  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-adm-border bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <span aria-hidden="true" className={cn("inline-flex h-11 w-11 items-center justify-center rounded-full", TONE[iconTone])}>
        {icon}
      </span>
      <div>
        <h3 className="text-[14px] font-medium leading-5 text-gray-80">{label}</h3>
        <p className="mt-1 text-[28px] font-semibold leading-9 text-gray-100">
          {valueLabel ? (
            <>
              <span aria-hidden="true">{value}</span>
              <span className="sr-only">{valueLabel}</span>
            </>
          ) : (
            value
          )}
        </p>
      </div>
      {trend && trendText && (
        <p className="flex items-center gap-1 text-[13px] leading-4 text-adm-completed">
          <TrendIcon size={14} aria-hidden="true" />
          <span aria-hidden="true">{t.admin.overview.stats.thisMonth(trend.value)}</span>
          <span className="sr-only">{trendText}</span>
        </p>
      )}
      {note && <p className="text-[13px] leading-4 text-gray-80">{note}</p>}
    </li>
  );
}
