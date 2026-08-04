"use client";

import { PageHeader } from "@/components/dashboard/PageHeader";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
import { DownloadCsvButton } from "@/components/dashboard/DownloadActions";
import { ViolationsPieChart } from "@/components/dashboard/charts/ViolationsPieChart";
import { PerformanceGauge } from "@/components/dashboard/charts/PerformanceGauge";
import { WcagLevelBarChart } from "@/components/dashboard/charts/WcagLevelBarChart";
import { TopFailingCriteriaChart } from "@/components/dashboard/charts/TopFailingCriteriaChart";
import { FindingsTable } from "@/components/dashboard/FindingsTable";
import { useAuditData } from "@/components/dashboard/AuditDataContext";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import {
  getDashboardSummary,
  getLevelBreakdown,
  getTopFailingCriteria,
  getDashboardPageFindings,
} from "@/lib/wcagAudit";

export default function DashboardPage() {
  const { auditData } = useAuditData();
  const { t } = useLanguage();

  return (
    <>
      <PageHeader
        title="A11Y"
        target={auditData?.url}
        actions={
          <>
            <LanguageToggle />
            <DownloadCsvButton />
          </>
        }
      />

      <main className="flex flex-col gap-6 px-4 py-6 sm:px-8 sm:py-8">
        {!auditData ? (
          <div className="flex min-h-[50vh] items-center justify-center rounded-2xl bg-gray-10">
            <p className="text-[16px] leading-6 text-gray-60">{t.dashboardPage.emptyState}</p>
          </div>
        ) : (
          <>
            <div className="grid gap-6 lg:grid-cols-2">
              <ViolationsPieChart summary={getDashboardSummary(auditData)} />
              <PerformanceGauge score={getDashboardSummary(auditData).score} />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <WcagLevelBarChart breakdown={getLevelBreakdown(auditData)} />
              <TopFailingCriteriaChart criteria={getTopFailingCriteria(auditData)} />
            </div>

            <FindingsTable rows={getDashboardPageFindings(auditData)} />
          </>
        )}
      </main>
    </>
  );
}
