import { PageHeader } from "@/components/dashboard/PageHeader";
import { LanguageToggle } from "@/components/dashboard/LanguageToggle";
// Download CSV/PDF not scoped for this sprint — commented out, not removed.
// import { DownloadCsvButton, DownloadPdfButton } from "@/components/dashboard/DownloadActions";
import { ViolationsPieChart } from "@/components/dashboard/charts/ViolationsPieChart";
import { PerformanceGauge } from "@/components/dashboard/charts/PerformanceGauge";
import { WcagLevelBarChart } from "@/components/dashboard/charts/WcagLevelBarChart";
import { TopFailingCriteriaChart } from "@/components/dashboard/charts/TopFailingCriteriaChart";
import { FindingsTable } from "@/components/dashboard/FindingsTable";
import { auditTarget } from "@/lib/dashboardData";

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        title="A11Y"
        target={auditTarget}
        actions={
          <>
            <LanguageToggle />
            {/* <DownloadCsvButton /> */}
            {/* <DownloadPdfButton /> */}
          </>
        }
      />

      <main className="flex flex-col gap-6 px-4 py-6 sm:px-8 sm:py-8">
        <div className="grid gap-6 lg:grid-cols-2">
          <ViolationsPieChart />
          <PerformanceGauge />
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <WcagLevelBarChart />
          <TopFailingCriteriaChart />
        </div>

        <FindingsTable />
      </main>
    </>
  );
}
