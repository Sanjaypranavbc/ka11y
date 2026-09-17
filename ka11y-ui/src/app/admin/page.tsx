"use client";

import { useState } from "react";
import { AlertTriangle, Play, ShieldCheck, Users } from "lucide-react";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { useAdminConsole } from "@/components/admin/AdminShell";
import { StatCard } from "@/components/admin/StatCard";
import { AuditStatusDonut } from "@/components/admin/charts/AuditStatusDonut";
import { FailsBySeverityChart } from "@/components/admin/charts/FailsBySeverityChart";
import { RecentAuditsTable } from "@/components/admin/RecentAuditsTable";
import { LiveActivityFeed } from "@/components/admin/LiveActivityFeed";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { formatCompact, formatNumber } from "@/lib/admin/format";

export default function AdminOverviewPage() {
  const { t, lang } = useLanguage();
  const { data, status, reload } = useAdminConsole();
  const [feedPaused, setFeedPaused] = useState(false);
  const s = t.admin.overview.stats;

  return (
    <>
      <AdminPageHeader
        title={t.admin.overview.title}
        subtitle={t.admin.overview.subtitle}
        systemHealth={data?.stats.systemHealth}
      />

      {/* Load state is announced once; the widgets below do not use live regions. */}
      <div role="status" aria-live="polite" className={status === "ready" ? "sr-only" : "mb-4 text-[14px] leading-5 text-gray-80"}>
        {status === "loading" && t.admin.overview.loading}
        {status === "error" && (
          <span className="inline-flex flex-wrap items-center gap-3">
            {t.admin.overview.loadError}
            <button
              type="button"
              onClick={reload}
              className="inline-flex min-h-11 items-center rounded-lg border border-brand-green-80 px-3 font-medium text-brand-green-80"
            >
              {t.admin.overview.retry}
            </button>
          </span>
        )}
      </div>

      {data && (
        <div className="flex flex-col gap-5">
          <section aria-labelledby="admin-key-metrics">
            <h2 id="admin-key-metrics" className="sr-only">
              {t.admin.overview.keyMetrics}
            </h2>
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard
                label={s.totalUsers}
                value={formatNumber(data.stats.totalUsers, lang)}
                icon={<Users size={22} />}
                trend={data.stats.totalUsersTrend}
              />
              <StatCard
                label={s.totalAudits}
                value={formatNumber(data.stats.totalAudits, lang)}
                icon={<Play size={22} />}
                trend={data.stats.totalAuditsTrend}
              />
              <StatCard
                label={s.totalFails}
                value={formatCompact(data.stats.totalFails, lang)}
                valueLabel={formatNumber(data.stats.totalFails, lang)}
                icon={<AlertTriangle size={22} />}
                iconTone="amber"
                trend={data.stats.totalFailsTrend}
              />
              <StatCard
                label={s.systemHealth}
                value={data.stats.systemHealth === "healthy" ? s.healthy : s.degraded}
                icon={<ShieldCheck size={22} />}
                iconTone="green"
                note={data.stats.systemHealth === "healthy" ? s.allServices : s.someServices}
              />
            </ul>
          </section>

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <AuditStatusDonut slices={data.auditStatus} />
            <FailsBySeverityChart counts={data.severity} />
          </div>

          <RecentAuditsTable
            jobs={data.recentAudits}
            title={t.admin.overview.recentAudits.title}
            subtitle={t.admin.overview.recentAudits.subtitle}
            viewAllHref="/admin/audits"
          />

          <LiveActivityFeed items={data.activity} paused={feedPaused} onTogglePaused={() => setFeedPaused((v) => !v)} />
        </div>
      )}
    </>
  );
}
