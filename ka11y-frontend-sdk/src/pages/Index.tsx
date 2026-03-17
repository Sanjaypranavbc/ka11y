import { useState } from "react";
import { useAudit } from "@/hooks/useAudit";
import { AuditSidebar } from "@/components/audit/AuditSidebar";
import { DashboardHeader } from "@/components/audit/DashboardHeader";
import { DashboardTab } from "@/components/audit/DashboardTab";
import { ViolationsTab } from "@/components/audit/ViolationsTab";
import { NeedsReviewTab } from "@/components/audit/NeedsReviewTab";
import { PassesTab } from "@/components/audit/PassesTab";
import { SettingsTab } from "@/components/audit/SettingsTab";
import { Skeleton } from "@/components/ui/skeleton";
import { TabValue } from "@/types/audit";
import { AlertTriangle } from "lucide-react";

const Index = () => {
  const [activeTab, setActiveTab] = useState<TabValue>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { result, jobStatus, error, runAudit, exportJSON } = useAudit();

  const isLoading = jobStatus === "pending" || jobStatus === "running";

  return (
    <div className="h-screen flex bg-background overflow-hidden">
      <AuditSidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onRunAudit={runAudit}
        jobStatus={jobStatus}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <DashboardHeader
          url={result.url}
          generatedAt={result.generated_at}
          onExportJSON={exportJSON}
          onToggleSidebar={() => setSidebarOpen(true)}
        />

        <main className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="p-6 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-24 rounded-lg" />)}
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Skeleton className="h-72 rounded-lg" />
                <Skeleton className="h-72 rounded-lg" />
              </div>
              <Skeleton className="h-48 rounded-lg" />
            </div>
          ) : jobStatus === "failed" ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center space-y-3">
                <AlertTriangle className="h-12 w-12 text-destructive mx-auto" />
                <h2 className="text-lg font-semibold text-foreground">Audit Failed</h2>
                <p className="text-sm text-muted-foreground max-w-md">{error || "An unknown error occurred."}</p>
              </div>
            </div>
          ) : (
            <>
              {activeTab === "dashboard" && <DashboardTab result={result} />}
              {activeTab === "violations" && <ViolationsTab violations={result.violations} />}
              {activeTab === "needs-review" && <NeedsReviewTab items={result.needs_review} />}
              {activeTab === "passes" && <PassesTab passes={result.passes} />}
              {activeTab === "settings" && <SettingsTab />}
            </>
          )}
        </main>
      </div>
    </div>
  );
};

export default Index;
