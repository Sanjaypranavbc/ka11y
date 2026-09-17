"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { useAdminConsole } from "@/components/admin/AdminShell";
import { RecentAuditsTable } from "@/components/admin/RecentAuditsTable";
import { useLanguage } from "@/components/dashboard/LanguageContext";

export default function AdminAuditsPage() {
  const { t } = useLanguage();
  const { data, status } = useAdminConsole();

  return (
    <>
      <AdminPageHeader title={t.admin.nav.audits} subtitle={t.admin.overview.recentAudits.subtitle} />
      <div role="status" aria-live="polite" className={status === "ready" ? "sr-only" : "mb-4 text-[14px] leading-5 text-gray-80"}>
        {status === "loading" && t.admin.overview.loading}
        {status === "error" && t.admin.overview.loadError}
      </div>
      {data && <RecentAuditsTable jobs={data.recentAudits} title={t.admin.nav.audits} />}
    </>
  );
}
