"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { AdminNavKey } from "@/lib/admin/nav";
import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { useLanguage } from "@/components/dashboard/LanguageContext";

export function AdminPlaceholderPage({ navKey }: { navKey: AdminNavKey }) {
  const { t } = useLanguage();
  const title = t.admin.nav[navKey];
  return (
    <>
      <AdminPageHeader title={title} />
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-3 rounded-2xl border border-adm-border bg-white p-6 text-center">
        <p className="text-[18px] font-medium leading-6 text-gray-100">{t.admin.placeholder.comingSoon(title)}</p>
        <p className="max-w-md text-[14px] leading-5 text-gray-80">{t.admin.placeholder.body}</p>
        <Link
          href="/admin"
          className="mt-2 inline-flex min-h-11 items-center gap-2 rounded-lg border border-brand-green-80 px-4 text-[14px] font-medium text-brand-green-80 hover:bg-adm-completed-bg"
        >
          <ArrowLeft size={16} aria-hidden="true" />
          {t.admin.placeholder.backToOverview}
        </Link>
      </div>
    </>
  );
}
