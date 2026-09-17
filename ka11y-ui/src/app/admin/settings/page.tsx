"use client";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { useLanguage } from "@/components/dashboard/LanguageContext";
import { loadSettings } from "@/lib/admin/api";
import { formatDateTime } from "@/lib/admin/format";
import { useAdminResource } from "@/lib/admin/useAdminResource";

export default function AdminSettingsPage() {
  const { t, lang } = useLanguage();
  const p = t.admin.pages.settings;
  const common = t.admin.pages.common;
  const { data, status, retry } = useAdminResource(loadSettings);

  return (
    <>
      <AdminPageHeader title={p.title} subtitle={p.subtitle} />
      <div role="status" aria-live="polite" className={status === "ready" ? "sr-only" : "mb-4 text-[14px] leading-5 text-gray-80"}>
        {status === "loading" && common.loading}
        {status === "error" && (
          <>
            {common.loadError}{" "}
            <button type="button" onClick={retry} className="min-h-11 rounded-md px-2 font-medium text-brand-green-80 underline underline-offset-4">
              {common.retry}
            </button>
          </>
        )}
      </div>
      {data && (
        <>
          <p className="mb-4 text-[13px] leading-5 text-gray-80">
            {p.readOnly} · {common.lastUpdated(formatDateTime(data.generatedAt, lang))}
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {data.sections.map((section) => (
              <section key={section.key} aria-labelledby={`settings-${section.key}`} className="rounded-2xl border border-adm-border bg-white p-5">
                <h2 id={`settings-${section.key}`} className="text-[15px] font-semibold leading-6 text-gray-100">
                  {p.sections[section.key]}
                </h2>
                <dl className="mt-3 divide-y divide-adm-border">
                  {section.items.map((item) => (
                    <div key={item.label} className="grid gap-1 py-2.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:gap-4">
                      <dt className="text-[13px] text-gray-80">{item.label}</dt>
                      <dd className="break-words text-[14px] text-gray-100">{item.value}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}
          </div>
        </>
      )}
    </>
  );
}
